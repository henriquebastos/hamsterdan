"""AX8 focused tests — tree AST, cyclic net, durable counter, bounded loops."""

from dataclasses import asdict, dataclass

import pytest
from ax8_compiler import VariantPayloadConverter, compile_workflow
from ax8_workflow_ast import WorkflowShapeError, case, retry, step
from petrus.engine import Engine
from petrus.impetus.history import ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import DataclassPayloadConverter
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch


@dataclass(frozen=True)
class ChargeRequest:
    order_id: str
    attempt: int = 1


@dataclass(frozen=True)
class Confirmed:
    reference: str


@dataclass(frozen=True)
class Transient:
    order_id: str
    attempt: int


@dataclass(frozen=True)
class Fatal:
    reason: str


@dataclass(frozen=True)
class Receipt:
    summary: str


@motus_activity(converter=VariantPayloadConverter())
def charge(request: ChargeRequest) -> Confirmed | Transient | Fatal:
    """Deterministic per (order_id, attempt): the order id is the script."""
    if request.order_id == "fatal":
        return Fatal(reason="hard decline")
    if request.order_id.startswith("ok-at-"):
        succeeds_at = int(request.order_id.removeprefix("ok-at-"))
        if request.attempt >= succeeds_at:
            return Confirmed(reference=f"ref-{request.attempt}")
    return Transient(order_id=request.order_id, attempt=request.attempt)


@motus_activity(converter=DataclassPayloadConverter())
def record(confirmed: Confirmed) -> Receipt:
    return Receipt(summary=f"ok:{confirmed.reference}")


@motus_activity(converter=DataclassPayloadConverter())
def refund(fatal: Fatal) -> Receipt:
    return Receipt(summary=f"refunded:{fatal.reason}")


@motus_activity(converter=DataclassPayloadConverter())
def escalate(transient: Transient) -> Receipt:
    return Receipt(summary=f"escalated:{transient.attempt}")


DEFINITIONS = (charge, record, refund, escalate)


def rearm_charge(transient: Transient) -> ChargeRequest:
    return ChargeRequest(order_id=transient.order_id, attempt=transient.attempt + 1)


def forgetful_rearm(transient: Transient) -> ChargeRequest:
    """Type-correct but never increments — the loop that cannot end."""
    return ChargeRequest(order_id=transient.order_id, attempt=transient.attempt)


def charge_workflow(rearm=rearm_charge):
    return retry(
        charge,
        case(Confirmed, then=step(record)),
        case(Fatal, then=step(refund)),
        retryable=Transient,
        rearm=rearm,
        limit=3,
        exhausted=step(escalate),
    )


def drive_bounded(subject: Engine, limit: int = 100) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def make_engine(compiled, order_id: str, instance: str = "ax8", history=None) -> Engine:
    return Engine.create(
        compiled.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=InlineDispatch({d.declaration.name: d for d in DEFINITIONS}),
        marking=Marking({compiled.entry: (Token("ChargeRequest", asdict(ChargeRequest(order_id=order_id))),)}),
        handlers=dict(compiled.handlers),
        activities=compiled.activities,
    )


def requested(subject: Engine) -> list[str]:
    return [r.activity for r in subject.records if isinstance(r, ActivityRequested)]


class TestShapeValidation:
    def test_retryable_must_be_a_union_member(self) -> None:
        with pytest.raises(WorkflowShapeError, match="retryable 'Receipt' is not a union member"):
            retry(
                charge,
                case(Confirmed, then=step(record)),
                case(Fatal, then=step(refund)),
                retryable=Receipt,
                rearm=rearm_charge,
                limit=3,
                exhausted=step(escalate),
            )

    def test_retryable_variant_needs_the_counter_field(self) -> None:
        # Fatal is a union member but carries no attempt field: loop state
        # must live in token data, so this is unrepresentable.
        with pytest.raises(WorkflowShapeError, match="Fatal needs the counter field 'attempt'"):
            retry(
                charge,
                case(Confirmed, then=step(record)),
                case(Transient, then=step(escalate)),
                retryable=Fatal,
                rearm=rearm_charge,
                limit=3,
                exhausted=step(refund),
            )

    def test_rearm_parameter_must_be_the_retryable_variant(self) -> None:
        def wrong(request: ChargeRequest) -> ChargeRequest:
            return request

        with pytest.raises(WorkflowShapeError, match="'wrong' must take exactly one\\s+Transient parameter"):
            charge_workflow(rearm=wrong)

    def test_rearm_must_return_the_activity_input(self) -> None:
        def wrong(transient: Transient) -> Transient:
            return transient

        with pytest.raises(WorkflowShapeError, match="must return ChargeRequest .* to close the loop"):
            charge_workflow(rearm=wrong)

    def test_limit_must_be_positive(self) -> None:
        with pytest.raises(WorkflowShapeError, match="limit must be a positive int"):
            retry(
                charge,
                case(Confirmed, then=step(record)),
                case(Fatal, then=step(refund)),
                retryable=Transient,
                rearm=rearm_charge,
                limit=0,
                exhausted=step(escalate),
            )

    def test_cases_must_cover_the_non_retryable_variants(self) -> None:
        with pytest.raises(WorkflowShapeError, match="missing \\['Fatal'\\]"):
            retry(
                charge,
                case(Confirmed, then=step(record)),
                retryable=Transient,
                rearm=rearm_charge,
                limit=3,
                exhausted=step(escalate),
            )


class TestLoweredShape:
    def test_the_loop_back_arc_targets_the_entry_place(self) -> None:
        compiled = compile_workflow(charge_workflow(), DEFINITIONS, transforms=(rearm_charge,))
        net = compiled.built.net
        [loop_arc] = list(net.outputs(NetPath("w.rearm")))
        assert str(loop_arc.target) == "w.entry"  # the cycle, one arc
        assert loop_arc.color == "ChargeRequest"

    def test_loop_and_exhausted_filters_split_on_the_counter(self) -> None:
        compiled = compile_workflow(charge_workflow(), DEFINITIONS, transforms=(rearm_charge,))
        assert compiled.filters["w.rearm"] == "(attempt < 3)"
        assert compiled.filters["w.to_exhausted"] == "!(attempt < 3)"
        net = compiled.built.net
        retryable_arcs = sorted(
            (str(a.target), a.filter.expression) for a in net.arcs if a.source == NetPath("w.on_transient")
        )
        assert retryable_arcs == [
            ("w.rearm", "(attempt < 3)"),
            ("w.to_exhausted", "!(attempt < 3)"),
        ]

    def test_source_map_points_the_cycle_back_to_the_retry_node(self) -> None:
        compiled = compile_workflow(charge_workflow(), DEFINITIONS, transforms=(rearm_charge,))
        assert compiled.source_map["/"].node == "retry 'charge' x3"
        assert compiled.generated_by["w.rearm"] == "/"
        assert compiled.generated_by["w.to_exhausted"] == "/"
        assert compiled.generated_by["w.0_0.record"] == "/0/0"
        assert compiled.generated_by["w.2_0.escalate"] == "/2/0"


class TestExecution:
    def run(self, order_id: str, history=None, instance: str = "ax8") -> tuple[list[str], list[dict], Engine]:
        compiled = compile_workflow(charge_workflow(), DEFINITIONS, transforms=(rearm_charge,))
        subject = make_engine(compiled, order_id, history=history, instance=instance)
        drive_bounded(subject)
        [exit_place] = compiled.exits
        return requested(subject), [t.data for t in subject.marking.place(exit_place)], subject

    def test_success_after_one_retry(self) -> None:
        names, final, _ = self.run("ok-at-2")
        assert final == [{"summary": "ok:ref-2"}]
        # Two attempts are two durable activity round-trips, not one.
        assert names == ["charge", "charge", "record"]

    def test_immediate_fatal_takes_the_error_path(self) -> None:
        names, final, _ = self.run("fatal")
        assert final == [{"summary": "refunded:hard decline"}]
        assert names == ["charge", "refund"]

    def test_exhaustion_exits_after_exactly_limit_attempts(self) -> None:
        names, final, _ = self.run("never")
        assert final == [{"summary": "escalated:3"}]
        assert names == ["charge", "charge", "charge", "escalate"]

    def test_the_counter_is_visible_in_durable_history(self) -> None:
        subject = self.run("never")[2]
        attempts = [
            r.input["request"]["attempt"]
            for r in subject.records
            if isinstance(r, ActivityRequested) and r.activity == "charge"
        ]
        assert attempts == [1, 2, 3]

    def test_replay_over_recompiled_cyclic_net(self) -> None:
        history = InMemoryHistoryStore()
        self.run("ok-at-2", history=history, instance="ax8-replay")

        recompiled = compile_workflow(charge_workflow(), DEFINITIONS, transforms=(rearm_charge,))
        resumed = Engine.load(
            recompiled.built.net,
            "ax8-replay",
            history=history,
            dispatch=InlineDispatch({d.declaration.name: d for d in DEFINITIONS}),
            handlers=dict(recompiled.handlers),
            activities=recompiled.activities,
        )
        [exit_place] = recompiled.exits
        assert [t.data for t in resumed.marking.place(exit_place)] == [{"summary": "ok:ref-2"}]

    def test_a_rearm_that_never_increments_is_an_unbounded_loop(self) -> None:
        """Type-correct, construction-valid, and infinite: the compiler
        cannot prove the counter advances. Bounded driving is the honest
        diagnostic available today — the loop never quiesces."""
        compiled = compile_workflow(charge_workflow(rearm=forgetful_rearm), DEFINITIONS, transforms=(forgetful_rearm,))
        subject = make_engine(compiled, "never")
        with pytest.raises(AssertionError, match="did not quiesce"):
            drive_bounded(subject, limit=50)
