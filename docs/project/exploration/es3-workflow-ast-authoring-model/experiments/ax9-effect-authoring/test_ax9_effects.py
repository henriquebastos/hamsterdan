"""AX9 focused tests — journaled interpretation (A) vs traced lowering (B)."""

import json
from dataclasses import asdict, dataclass, field

import pytest
from ax9_effects import (
    JOURNAL_KEY,
    EffectHandler,
    EffectProgramError,
    EffectRuntime,
    NondeterministicEffectProgram,
    effect_activity,
    run_effect_program,
)
from ax9_tracing import Ref, TraceBranchError, lower_effect_graph, trace_effect_program
from petrus.engine import Engine
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.dsl import NetSpec
from petrus.impetus.history import ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, Token
from petrus.motus.activity import ActivityError, ActivityInvocation, ExecutionPolicy
from petrus.motus.dispatch import InlineDispatch
from petrus.motus.dispatch.local import LocalDispatch
from petrus.motus.worker import Worker

# --- Domain and effect vocabulary -----------------------------------------


@dataclass(frozen=True)
class Payment:
    account_id: str
    amount: int


@dataclass(frozen=True)
class Reservation:
    reservation_id: str


@dataclass(frozen=True)
class PaymentResult:
    reference: str


@dataclass(frozen=True)
class Settlement:
    reference: str


@dataclass(frozen=True)
class ReserveFunds:
    account_id: str
    amount: int


@dataclass(frozen=True)
class SendPayment:
    reservation_id: str


@dataclass(frozen=True)
class EmitEvent:
    name: str
    reference: str


def settle_payment(payment: Payment) -> Settlement:
    """The effect program under test — yields effect values, returns a result."""
    reservation = yield ReserveFunds(payment.account_id, payment.amount)
    result = yield SendPayment(reservation.reservation_id)
    yield EmitEvent("payment_settled", result.reference)
    return Settlement(reference=result.reference)


class Ledger:
    """Counts real side effects so re-performance is observable."""

    def __init__(self) -> None:
        self.performed: list[tuple[str, str]] = []

    def count(self, kind: str) -> int:
        return sum(1 for name, _ in self.performed if name == kind)


def make_runtime(ledger: Ledger, *, send_failures: int = 0) -> EffectRuntime:
    remaining = {"failures": send_failures}

    def reserve(effect: ReserveFunds) -> Reservation:
        ledger.performed.append(("ReserveFunds", effect.account_id))
        return Reservation(reservation_id=f"res-{effect.account_id}")

    def send(effect: SendPayment) -> PaymentResult:
        ledger.performed.append(("SendPayment", effect.reservation_id))
        if remaining["failures"] > 0:
            remaining["failures"] -= 1
            raise ActivityError("payment provider timeout", retryable=True)
        return PaymentResult(reference=f"pay-{effect.reservation_id}")

    def emit(effect: EmitEvent) -> None:
        ledger.performed.append(("EmitEvent", effect.name))

    return EffectRuntime(
        {
            ReserveFunds: EffectHandler(reserve, Reservation),
            SendPayment: EffectHandler(send, PaymentResult),
            EmitEvent: EffectHandler(emit, None),
        }
    )


@dataclass
class FakeContext:
    """Stand-in for the frozen ActivityExecutionContext protocol."""

    latest_details: object = None
    attempt_id: str = "fake-1"
    epoch: str = "1"
    claimant: str = "fake"
    instance: str | None = None
    heartbeats: list = field(default_factory=list)
    fail_on_heartbeat: int | None = None

    def heartbeat(self, *, details: object = None) -> object:
        if self.fail_on_heartbeat is not None and len(self.heartbeats) + 1 == self.fail_on_heartbeat:
            raise ConnectionError("worker died between perform and checkpoint")
        snapshot = json.loads(json.dumps(details))
        self.heartbeats.append(snapshot)
        self.latest_details = snapshot
        return snapshot


PAYMENT = Payment(account_id="acct", amount=50)


# --- Interpretation A: journaled interpreter -------------------------------


class TestJournaledInterpreter:
    def test_happy_path_performs_all_effects_in_order(self) -> None:
        ledger = Ledger()
        context = FakeContext()
        result = run_effect_program(settle_payment, {"payment": PAYMENT}, runtime=make_runtime(ledger), context=context)
        assert result == Settlement(reference="pay-res-acct")
        assert ledger.performed == [
            ("ReserveFunds", "acct"),
            ("SendPayment", "res-acct"),
            ("EmitEvent", "payment_settled"),
        ]
        assert len(context.heartbeats) == 3
        assert len(context.latest_details[JOURNAL_KEY]) == 3

    def test_resume_replays_journal_without_reperforming(self) -> None:
        first = Ledger()
        full = FakeContext()
        run_effect_program(settle_payment, {"payment": PAYMENT}, runtime=make_runtime(first), context=full)
        # A successor attempt inherits the first two journaled effects.
        partial = {JOURNAL_KEY: full.latest_details[JOURNAL_KEY][:2]}
        second = Ledger()
        resumed = FakeContext(latest_details=partial)
        result = run_effect_program(settle_payment, {"payment": PAYMENT}, runtime=make_runtime(second), context=resumed)
        assert result == Settlement(reference="pay-res-acct")
        assert second.performed == [("EmitEvent", "payment_settled")]

    def test_crash_between_perform_and_checkpoint_reperforms_one_effect(self) -> None:
        """The at-least-once boundary is per effect: a crash after perform but
        before the journal heartbeat re-performs exactly that effect. Effect
        handlers carry the same idempotency duty activities already carry."""
        ledger = Ledger()
        crashing = FakeContext(fail_on_heartbeat=2)
        with pytest.raises(ConnectionError):
            run_effect_program(settle_payment, {"payment": PAYMENT}, runtime=make_runtime(ledger), context=crashing)
        resumed = FakeContext(latest_details=crashing.latest_details)
        result = run_effect_program(settle_payment, {"payment": PAYMENT}, runtime=make_runtime(ledger), context=resumed)
        assert result == Settlement(reference="pay-res-acct")
        assert ledger.count("ReserveFunds") == 1
        assert ledger.count("SendPayment") == 2  # the re-performed effect
        assert ledger.count("EmitEvent") == 1

    def test_nondeterministic_program_fails_loudly(self) -> None:
        mood = {"flip": False}

        def moody(payment: Payment) -> Settlement:
            if mood["flip"]:
                yield SendPayment("premature")
            else:
                yield ReserveFunds(payment.account_id, payment.amount)
            return Settlement(reference="never")

        ledger = Ledger()
        first = FakeContext()
        run_effect_program(moody, {"payment": PAYMENT}, runtime=make_runtime(ledger), context=first)
        mood["flip"] = True
        replay = FakeContext(latest_details=first.latest_details)
        with pytest.raises(NondeterministicEffectProgram, match="replay diverged at effect 0"):
            run_effect_program(moody, {"payment": PAYMENT}, runtime=make_runtime(ledger), context=replay)

    def test_unknown_effect_is_refused_with_known_effects_listed(self) -> None:
        @dataclass(frozen=True)
        class Teleport:
            where: str

        def rogue(payment: Payment) -> Settlement:
            yield Teleport("elsewhere")
            return Settlement(reference="never")

        with pytest.raises(EffectProgramError, match="no effect handler for 'Teleport'"):
            run_effect_program(rogue, {"payment": PAYMENT}, runtime=make_runtime(Ledger()), context=FakeContext())

    def test_journal_is_json_faithful_and_holds_no_frames(self) -> None:
        context = FakeContext()
        run_effect_program(settle_payment, {"payment": PAYMENT}, runtime=make_runtime(Ledger()), context=context)
        journal = context.latest_details[JOURNAL_KEY]
        assert json.loads(json.dumps(journal)) == journal
        assert journal[0] == {
            "effect": 'ReserveFunds:{"account_id":"acct","amount":50}',
            "result": {"reservation_id": "res-acct"},
        }
        assert journal[2]["result"] is None

    def test_plain_function_is_refused(self) -> None:
        def not_a_program(payment: Payment) -> Settlement:
            return Settlement(reference="direct")

        with pytest.raises(TypeError, match="requires a generator function"):
            effect_activity(not_a_program, runtime=make_runtime(Ledger()))


# --- Interpretation A on the frozen runtime --------------------------------


def single_transition_net(definition):
    spec = NetSpec("pay")
    scope = spec.s["a"]
    entry = scope.p.entry("Payment")
    transition = scope.t.settle(handler=definition.declaration.name)
    exit_place = scope.p.exit("Settlement")
    entry >> transition >> exit_place
    built = spec.build()
    handlers = dict(built.handlers)
    uri = built.net.handler_uri(abs(transition))
    handlers[uri] = DerivedActivityHandler(built.net, abs(transition), definition)
    return built, abs(entry), abs(exit_place), handlers


class TestFrozenRuntime:
    def test_net_sees_one_activity_for_three_effects(self) -> None:
        ledger = Ledger()
        definition = effect_activity(settle_payment, runtime=make_runtime(ledger))
        built, entry, exit_place, handlers = single_transition_net(definition)
        engine = Engine.create(
            built.net,
            "ax9-a",
            history=InMemoryHistoryStore(),
            dispatch=InlineDispatch({definition.declaration.name: definition}),
            marking=Marking({entry: (Token("Payment", asdict(PAYMENT)),)}),
            handlers=handlers,
            activities=(definition.declaration,),
        )
        while engine.advance().ready:
            pass
        final = [token.data for token in engine.marking.place(exit_place)]
        assert final == [{"reference": "pay-res-acct"}]
        requested = [r for r in engine.records if isinstance(r, ActivityRequested)]
        assert len(requested) == 1  # three effects, one durable activity
        assert ledger.count("ReserveFunds") == 1

    def test_worker_crash_resumes_from_persisted_journal(self, tmp_path) -> None:
        """The decisive durability proof on the frozen dispatch: attempt 1
        journals ReserveFunds via heartbeat, then fails retryably inside
        SendPayment; attempt 2 (a fresh claim) receives the persisted journal
        as latest_details and resumes without re-reserving funds."""
        ledger = Ledger()
        definition = effect_activity(settle_payment, runtime=make_runtime(ledger, send_failures=1))
        dispatch = LocalDispatch(tmp_path / "custody.db", instance="ax9")
        dispatch.dispatch(
            1,
            ActivityInvocation(
                "settle_payment",
                input={"payment": asdict(PAYMENT)},
                policy=ExecutionPolicy(attempts=2),
            ),
        )
        worker = Worker(dispatch.worker(), {"settle_payment": definition}, worker_id="ax9-worker")
        processed = worker.run_available(limit=4)
        assert processed == 2  # the failed attempt and the resumed attempt
        [(occurrence, outcome)] = dispatch.collect()
        assert occurrence == 1
        assert outcome == {"reference": "pay-res-acct"}
        assert ledger.count("ReserveFunds") == 1  # journaled, never re-performed
        assert ledger.count("SendPayment") == 2  # failed once, succeeded once
        assert ledger.count("EmitEvent") == 1


# --- Interpretation B: traced lowering -------------------------------------


class TestTracedLowering:
    def test_trace_produces_the_static_step_graph(self) -> None:
        graph = trace_effect_program(settle_payment, runtime=make_runtime(Ledger()))
        assert [step.effect_type for step in graph.steps] == [
            ReserveFunds,
            SendPayment,
            EmitEvent,
        ]
        assert dict(graph.steps[0].arguments) == {
            "account_id": Ref("payment", ("account_id",)),
            "amount": Ref("payment", ("amount",)),
        }
        assert dict(graph.steps[1].arguments) == {"reservation_id": Ref("step_0", ("reservation_id",))}
        assert dict(graph.steps[2].arguments) == {
            "name": "payment_settled",
            "reference": Ref("step_1", ("reference",)),
        }
        assert graph.returns is Settlement
        assert dict(graph.return_arguments) == {"reference": Ref("step_1", ("reference",))}

    def test_data_dependent_branch_is_refused_loudly(self) -> None:
        def branching(payment: Payment) -> Settlement:
            reservation = yield ReserveFunds(payment.account_id, payment.amount)
            if reservation.reservation_id:
                yield SendPayment(reservation.reservation_id)
            return Settlement(reference="never")

        with pytest.raises(TraceBranchError, match="workflow combinators"):
            trace_effect_program(branching, runtime=make_runtime(Ledger()))

    def test_lowered_net_executes_but_costs_one_transition_per_effect(self) -> None:
        ledger = Ledger()
        runtime = make_runtime(ledger)
        graph = trace_effect_program(settle_payment, runtime=runtime)
        compiled = lower_effect_graph(graph, runtime=runtime)
        # enter + three effects + return projection: five durable transitions.
        assert len(compiled.built.net.transitions) == 5
        assert len(compiled.built.net.places) == 6
        engine = Engine.create(
            compiled.built.net,
            "ax9-b",
            history=InMemoryHistoryStore(),
            dispatch=InlineDispatch({d.declaration.name: d for d in compiled.definitions}),
            marking=Marking({compiled.entry: (Token("Payment", asdict(PAYMENT)),)}),
            handlers=dict(compiled.handlers),
            activities=compiled.activities,
        )
        while engine.advance().ready:
            pass
        final = [token.data for token in engine.marking.place(compiled.exit)]
        assert final == [{"reference": "pay-res-acct"}]
        requested = [r for r in engine.records if isinstance(r, ActivityRequested)]
        assert len(requested) == 5  # vs exactly 1 under Interpretation A
        # Intermediate tokens are erased to untyped environment dicts — the
        # typed places the workflow layer fights for disappear under B.
        env_colors = {
            place_def.color
            for place_def in compiled.built.net.places.values()
            if place_def.path not in (compiled.entry, compiled.exit)
        }
        assert env_colors == {"dict"}
