"""AX4 focused tests — split shape, synchronization, failure, replay, hazards."""

from dataclasses import asdict, dataclass

import pytest
from ax4_compiler import LoweringError, compile_workflow
from ax4_workflow_ast import parallel, sequence, step
from petrus.engine import Engine, choose_throughput
from petrus.impetus.history import ActivityFailed, ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import DataclassPayloadConverter
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch, InMemoryDispatch


@dataclass(frozen=True)
class OrderDraft:
    sku: str


@dataclass(frozen=True)
class Order:
    sku: str


@dataclass(frozen=True)
class Reservation:
    sku: str


@dataclass(frozen=True)
class TaxQuote:
    sku: str
    amount: int


@dataclass(frozen=True)
class Receipt:
    sku: str
    taxed: int


@motus_activity(converter=DataclassPayloadConverter())
def receive_order(draft: OrderDraft) -> Order:
    return Order(sku=draft.sku)


@motus_activity(converter=DataclassPayloadConverter())
def reserve_inventory(order: Order) -> Reservation:
    return Reservation(sku=order.sku)


@motus_activity(converter=DataclassPayloadConverter())
def calculate_taxes(order: Order) -> TaxQuote:
    return TaxQuote(sku=order.sku, amount=7)


@motus_activity(converter=DataclassPayloadConverter())
def charge_customer(reservation: Reservation, taxes: TaxQuote) -> Receipt:
    return Receipt(sku=reservation.sku, taxed=taxes.amount)


DEFINITIONS = (receive_order, reserve_inventory, calculate_taxes, charge_customer)


def order_workflow():
    return sequence(
        step(receive_order),
        parallel(
            step(reserve_inventory),
            step(calculate_taxes),
        ),
        step(charge_customer),
    )


def drive_bounded(subject: Engine, limit: int = 100) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def make_engine(compiled, dispatch, seeds: tuple[object, ...] = (OrderDraft(sku="tea"),), **kwargs):
    return Engine.create(
        compiled.built.net,
        "ax4-instance",
        history=InMemoryHistoryStore(),
        dispatch=dispatch,
        marking=Marking({compiled.entry: tuple(Token(type(s).__name__, asdict(s)) for s in seeds)}),
        handlers=dict(compiled.handlers),
        guards=dict(compiled.built.guards),
        activities=compiled.activities,
        **kwargs,
    )


def inline() -> InlineDispatch:
    return InlineDispatch({d.declaration.name: d for d in DEFINITIONS})


def requested(subject: Engine) -> list[str]:
    return [r.activity for r in subject.records if isinstance(r, ActivityRequested)]


class TestLoweredShape:
    def test_split_and_join_are_observable_in_the_net(self) -> None:
        compiled = compile_workflow(order_workflow(), DEFINITIONS)
        net = compiled.built.net
        assert sorted(str(t) for t in net.transitions) == [
            "w.0.receive_order",
            "w.1.split",
            "w.1_0.reserve_inventory",
            "w.1_1.calculate_taxes",
            "w.2.charge_customer",
        ]
        assert sorted(str(p) for p in net.places) == [
            "w.0.out",
            "w.1_0.in",
            "w.1_0.out",
            "w.1_1.in",
            "w.1_1.out",
            "w.2.out",
            "w.entry",
        ]
        # The join is the charge transition's own input arcs — no hidden combiner.
        join_inputs = sorted((str(a.source), a.color) for a in net.inputs(NetPath("w.2.charge_customer")))
        assert join_inputs == [("w.1_0.out", "Reservation"), ("w.1_1.out", "TaxQuote")]
        # The split duplicates one Order to both branch entries.
        split_outputs = sorted((str(a.target), a.color) for a in net.outputs(NetPath("w.1.split")))
        assert split_outputs == [("w.1_0.in", "Order"), ("w.1_1.in", "Order")]

    def test_source_map_covers_split_and_join(self) -> None:
        compiled = compile_workflow(order_workflow(), DEFINITIONS)
        assert compiled.source_map["/1"].transition == "w.1.split"
        assert compiled.source_map["/1"].exit_places == ("w.1_0.out", "w.1_1.out")
        assert compiled.generated_by["w.1.split"] == "/1"
        assert compiled.generated_by["w.2.charge_customer"] == "/2"


class TestExecution:
    def test_both_branches_complete_and_join_fires(self) -> None:
        compiled = compile_workflow(order_workflow(), DEFINITIONS)
        subject = make_engine(compiled, inline())
        drive_bounded(subject)

        [exit_place] = compiled.exits
        final = [t.data for t in subject.marking.place(exit_place)]
        assert final == [{"sku": "tea", "taxed": 7}]
        names = requested(subject)
        assert names[0] == "receive_order"
        assert set(names[1:3]) == {"reserve_inventory", "calculate_taxes"}
        assert names[3] == "charge_customer"

    def test_join_waits_for_the_slower_branch(self) -> None:
        """Concurrent branch dispatch needs choose_throughput; the default
        conservative policy keeps at most one activity in flight (a driving
        concern, not topology — the split still creates both branch tokens)."""
        compiled = compile_workflow(order_workflow(), DEFINITIONS)
        dispatch = InMemoryDispatch()
        subject = make_engine(compiled, dispatch, policy=choose_throughput)
        drive_bounded(subject)

        def pending_by_name() -> dict[str, int]:
            return {inv.activity: occ for occ, inv in dispatch.pending.items()}

        dispatch.complete(pending_by_name()["receive_order"], asdict(Order(sku="tea")))
        drive_bounded(subject)
        assert set(pending_by_name()) == {"reserve_inventory", "calculate_taxes"}

        dispatch.complete(pending_by_name()["reserve_inventory"], asdict(Reservation(sku="tea")))
        drive_bounded(subject)
        # Reservation token waits on w.1_0.out; the join is not enabled.
        assert "charge_customer" not in requested(subject)
        assert [t.data for t in subject.marking.place(NetPath("w.1_0.out"))] == [{"sku": "tea"}]

        dispatch.complete(pending_by_name()["calculate_taxes"], asdict(TaxQuote(sku="tea", amount=7)))
        drive_bounded(subject)
        assert "charge_customer" in requested(subject)

    def test_one_branch_failure_halts_loud_and_leaves_join_unfired(self) -> None:
        """Terminal failure is stop-on-terminal-failure: ActivityFailed and
        FiringFailed commit, the drive halts with RuntimeError, and the
        Engine poisons itself — inspection continues through a fresh
        Engine.load over the same durable history."""
        history = InMemoryHistoryStore()
        compiled = compile_workflow(order_workflow(), DEFINITIONS)
        dispatch = InMemoryDispatch()
        subject = Engine.create(
            compiled.built.net,
            "ax4-failure",
            history=history,
            dispatch=dispatch,
            marking=Marking({compiled.entry: (Token("OrderDraft", asdict(OrderDraft(sku="tea"))),)}),
            handlers=dict(compiled.handlers),
            activities=compiled.activities,
            policy=choose_throughput,
        )
        drive_bounded(subject)

        by_name = {inv.activity: occ for occ, inv in dispatch.pending.items()}
        dispatch.complete(by_name["receive_order"], asdict(Order(sku="tea")))
        drive_bounded(subject)

        by_name = {inv.activity: occ for occ, inv in dispatch.pending.items()}
        dispatch.complete(by_name["reserve_inventory"], asdict(Reservation(sku="tea")))
        dispatch.fail(by_name["calculate_taxes"], "tax provider unreachable")
        with pytest.raises(RuntimeError, match="failed terminally: tax provider unreachable"):
            drive_bounded(subject)

        # The poisoned Engine refuses further doors; reload from history.
        resumed = Engine.load(
            compiled.built.net,
            "ax4-failure",
            history=history,
            dispatch=InMemoryDispatch(),
            handlers=dict(compiled.handlers),
            activities=compiled.activities,
        )
        assert any(isinstance(r, ActivityFailed) for r in resumed.records)
        assert "charge_customer" not in requested(resumed)
        # The completed branch's token is parked at the join, durable in History.
        assert [t.data for t in resumed.marking.place(NetPath("w.1_0.out"))] == [{"sku": "tea"}]

    def test_two_cases_in_one_instance_expose_the_pairing_hazard(self) -> None:
        """Petri-honest: the join pairs by place FIFO, not by workflow case."""
        compiled = compile_workflow(order_workflow(), DEFINITIONS)
        subject = make_engine(compiled, inline(), seeds=(OrderDraft(sku="tea"), OrderDraft(sku="rum")))
        drive_bounded(subject)

        [exit_place] = compiled.exits
        final = sorted(t.data["sku"] for t in subject.marking.place(exit_place))
        assert final == ["rum", "tea"]
        # Both receipts exist, but nothing *guaranteed* the reservation and tax
        # quote of one sku met at the join — correlation is the instance's job
        # (production runs one Engine instance per PR for exactly this reason).

    def test_crossed_completion_order_mispairs_cases_at_the_join(self) -> None:
        """Proof, not caution: place FIFO pairs whatever arrives first. Two
        cases in one instance, completed in crossed order, yield a receipt
        combining one case's reservation with the other case's taxes."""
        compiled = compile_workflow(order_workflow(), DEFINITIONS)
        dispatch = InMemoryDispatch()
        subject = make_engine(
            compiled,
            dispatch,
            seeds=(OrderDraft(sku="tea"), OrderDraft(sku="rum")),
            policy=choose_throughput,
        )
        drive_bounded(subject)

        def occurrence(name: str, sku: str) -> int:
            matches = [occ for occ, inv in dispatch.pending.items() if inv.activity == name and sku in str(inv.input)]
            assert len(matches) == 1, f"{name}/{sku}: {dispatch.pending}"
            return matches[0]

        dispatch.complete(occurrence("receive_order", "tea"), asdict(Order(sku="tea")))
        dispatch.complete(occurrence("receive_order", "rum"), asdict(Order(sku="rum")))
        drive_bounded(subject)

        # Crossed order: rum's reservation lands first, tea's taxes land first.
        dispatch.complete(occurrence("reserve_inventory", "rum"), asdict(Reservation(sku="rum")))
        dispatch.complete(occurrence("calculate_taxes", "tea"), asdict(TaxQuote(sku="tea", amount=1)))
        dispatch.complete(occurrence("reserve_inventory", "tea"), asdict(Reservation(sku="tea")))
        dispatch.complete(occurrence("calculate_taxes", "rum"), asdict(TaxQuote(sku="rum", amount=2)))
        drive_bounded(subject)
        while dispatch.pending:
            occ, inv = next(iter(dispatch.pending.items()))
            payload = dict(inv.input["reservation"], taxed=inv.input["taxes"]["amount"])
            dispatch.complete(occ, payload)
            drive_bounded(subject)

        [exit_place] = compiled.exits
        receipts = sorted((t.data["sku"], t.data["taxed"]) for t in subject.marking.place(exit_place))
        # rum's reservation was charged with tea's tax quote and vice versa.
        assert receipts == [("rum", 1), ("tea", 2)]

    def test_replay_over_recompiled_net_reaches_same_state(self) -> None:
        history = InMemoryHistoryStore()
        compiled = compile_workflow(order_workflow(), DEFINITIONS)
        subject = Engine.create(
            compiled.built.net,
            "ax4-replay",
            history=history,
            dispatch=inline(),
            marking=Marking({compiled.entry: (Token("OrderDraft", asdict(OrderDraft(sku="tea"))),)}),
            handlers=dict(compiled.handlers),
            activities=compiled.activities,
        )
        drive_bounded(subject)

        recompiled = compile_workflow(order_workflow(), DEFINITIONS)
        resumed = Engine.load(
            recompiled.built.net,
            "ax4-replay",
            history=history,
            dispatch=inline(),
            handlers=dict(recompiled.handlers),
            activities=recompiled.activities,
        )
        [exit_place] = recompiled.exits
        assert [t.data for t in resumed.marking.place(exit_place)] == [{"sku": "tea", "taxed": 7}]


class TestLoweringErrors:
    def test_branch_consuming_wrong_color_is_rejected(self) -> None:
        broken = sequence(
            step(receive_order),
            parallel(
                step(reserve_inventory),
                step(charge_customer),  # consumes Reservation + TaxQuote, not Order
            ),
        )
        with pytest.raises(LoweringError, match="branch 1 .* must consume exactly the split\\s+token color 'Order'"):
            compile_workflow(broken, DEFINITIONS)

    def test_same_color_branch_results_demand_ports(self) -> None:
        @motus_activity(converter=DataclassPayloadConverter())
        def reserve_backup(order: Order) -> Reservation:
            return Reservation(sku=order.sku)

        @motus_activity(converter=DataclassPayloadConverter())
        def pick(primary: Reservation, backup: Reservation) -> Receipt:
            return Receipt(sku=primary.sku, taxed=0)

        broken = sequence(
            step(receive_order),
            parallel(step(reserve_inventory), step(reserve_backup)),
            step(pick),
        )
        with pytest.raises(LoweringError, match="named ports are required"):
            compile_workflow(broken, DEFINITIONS + (reserve_backup, pick))

    def test_no_output_branch_terminates_but_cannot_feed_a_join(self) -> None:
        """A `-> None` branch still owns a NoneType-colored exit place, so it
        works as a terminal side-effect branch (workflow ends with multiple
        exits) but is rejected before a join: nothing can consume NoneType."""

        @motus_activity(converter=DataclassPayloadConverter())
        def audit(order: Order) -> None:
            return None

        terminal = sequence(
            step(receive_order),
            parallel(step(reserve_inventory), step(audit)),
        )
        compiled = compile_workflow(terminal, DEFINITIONS + (audit,))
        assert sorted(str(p) for p in compiled.exits) == ["w.1_0.out", "w.1_1.out"]
        colors = {str(a.target): a.color for a in compiled.built.net.arcs}
        assert colors["w.1_1.out"] == "NoneType"

        joined = sequence(
            step(receive_order),
            parallel(step(reserve_inventory), step(audit)),
            step(charge_customer),  # wants Reservation + TaxQuote, gets NoneType
        )
        with pytest.raises(LoweringError):
            compile_workflow(joined, DEFINITIONS + (audit,))

    def test_unconsumed_branch_output_is_rejected(self) -> None:
        @motus_activity(converter=DataclassPayloadConverter())
        def charge_reservation_only(reservation: Reservation) -> Receipt:
            return Receipt(sku=reservation.sku, taxed=0)

        broken = sequence(
            step(receive_order),
            parallel(step(reserve_inventory), step(calculate_taxes)),
            step(charge_reservation_only),
        )
        with pytest.raises(LoweringError, match="carry tokens\\s+this activity does not consume"):
            compile_workflow(broken, DEFINITIONS + (charge_reservation_only,))
