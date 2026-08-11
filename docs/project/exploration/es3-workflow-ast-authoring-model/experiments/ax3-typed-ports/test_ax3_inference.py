"""AX3 focused tests — inference safety, multi-input execution, ambiguity, ports."""

from dataclasses import asdict, dataclass

import pytest
from ax3_inference import InferenceError, PlaceBoundActivityHandler, infer_ports
from petrus.engine import Engine
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.dsl import NetSpec
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import (
    DataclassPayloadConverter,
)
from petrus.motus.activity import (
    activity as motus_activity,
)
from petrus.motus.activity import (
    async_activity as motus_async_activity,
)
from petrus.motus.dispatch import InlineDispatch


@dataclass(frozen=True)
class Order:
    sku: str


@dataclass(frozen=True)
class CreditReport:
    score: int


@dataclass(frozen=True)
class Decision:
    approved: bool
    basis: int


@motus_activity(converter=DataclassPayloadConverter())
def underwrite(order: Order, credit: CreditReport) -> Decision:
    return Decision(approved=credit.score > 700, basis=credit.score)


@motus_activity(converter=DataclassPayloadConverter())
def assess(primary: CreditReport, secondary: CreditReport) -> Decision:
    # The asymmetric basis proves role assignment is not accidental.
    return Decision(approved=True, basis=primary.score * 1000 + secondary.score)


def drive_bounded(subject: Engine, limit: int = 50) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


class TestSafeInference:
    def test_single_input_single_output(self) -> None:
        @motus_activity(converter=DataclassPayloadConverter())
        def score(order: Order) -> CreditReport:
            return CreditReport(score=1)

        ports = infer_ports(score)
        assert dict(ports.inputs) == {"order": "Order"}
        assert ports.result == "CreditReport"

    def test_multiple_inputs_infer_one_color_each(self) -> None:
        ports = infer_ports(underwrite)
        assert dict(ports.inputs) == {"order": "Order", "credit": "CreditReport"}

    def test_none_return_is_a_sink_signal_not_a_color(self) -> None:
        @motus_activity(converter=DataclassPayloadConverter())
        def audit(decision: Decision) -> None:
            return None

        assert infer_ports(audit).result is None

    def test_async_definition_infers_identically(self) -> None:
        @motus_async_activity(converter=DataclassPayloadConverter())
        async def score(order: Order) -> CreditReport:
            return CreditReport(score=1)

        ports = infer_ports(score)
        assert dict(ports.inputs) == {"order": "Order"}
        assert ports.result == "CreditReport"


class TestRefusedInference:
    def test_union_output_is_refused_toward_branching(self) -> None:
        @motus_activity(converter=DataclassPayloadConverter())
        def evaluate(order: Order) -> Decision | CreditReport:
            return Decision(approved=True, basis=0)

        with pytest.raises(InferenceError, match="union.*one typed output place per\\s+variant"):
            infer_ports(evaluate)

    def test_optional_output_is_refused_as_a_union(self) -> None:
        @motus_activity(converter=DataclassPayloadConverter())
        def maybe(order: Order) -> Decision | None:
            return None

        with pytest.raises(InferenceError, match="union"):
            infer_ports(maybe)

    def test_generic_collection_is_refused_with_remedy(self) -> None:
        @motus_activity(converter=DataclassPayloadConverter())
        def batch(order: Order) -> list[Decision]:
            return []

        with pytest.raises(InferenceError, match="erases the parameter.*wrap the collection in a named dataclass"):
            infer_ports(batch)

    def test_none_input_is_refused(self) -> None:
        @motus_activity(converter=DataclassPayloadConverter())
        def source(nothing: None) -> Decision:
            return Decision(approved=True, basis=0)

        with pytest.raises(InferenceError, match="input must carry a token"):
            infer_ports(source)


def two_role_net():
    """Two input places sharing one color — the mandated ambiguity case."""
    spec = NetSpec("ax3")
    primary = spec.p.primary(CreditReport)
    secondary = spec.p.secondary(CreditReport)
    transition = spec.t.assess(handler="assess")
    decision = spec.p.decision(Decision)
    (primary, secondary) >> transition >> decision
    return spec.build()


def distinct_color_net():
    spec = NetSpec("ax3")
    order = spec.p.order(Order)
    credit = spec.p.credit(CreditReport)
    transition = spec.t.underwrite(handler="underwrite")
    decision = spec.p.decision(Decision)
    (order, credit) >> transition >> decision
    return spec.build()


def run(built, handler, seeds: dict[str, object], definitions) -> list[dict]:
    marking = Marking({NetPath(place): (Token(type(value).__name__, asdict(value)),) for place, value in seeds.items()})
    uri = built.net.handler_uri(NetPath(next(iter(built.net.transitions))))
    subject = Engine.create(
        built.net,
        "ax3-instance",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({d.declaration.name: d for d in definitions}),
        marking=marking,
        handlers={uri: handler},
        activities=tuple(d.declaration for d in definitions),
    )
    drive_bounded(subject)
    return [token.data for token in subject.marking.place(NetPath("decision"))]


class TestMultiInputExecution:
    def test_distinct_colors_derive_and_execute(self) -> None:
        built = distinct_color_net()
        handler = DerivedActivityHandler(built.net, NetPath("underwrite"), underwrite)
        found = run(
            built,
            handler,
            {"order": Order(sku="tea"), "credit": CreditReport(score=800)},
            (underwrite,),
        )
        assert found == [{"approved": True, "basis": 800}]

    def test_same_color_inputs_refuse_typed_derivation_loudly(self) -> None:
        built = two_role_net()
        with pytest.raises(
            ValueError, match="parameter 'primary' \\(CreditReport\\) requires exactly one matching input arc, found 2"
        ):
            DerivedActivityHandler(built.net, NetPath("assess"), assess)


class TestPlaceBoundPorts:
    def test_ports_disambiguate_same_color_roles(self) -> None:
        built = two_role_net()
        handler = PlaceBoundActivityHandler(
            net=built.net,
            transition=NetPath("assess"),
            activity=assess,
            bindings={"primary": "primary", "secondary": "secondary"},
            output=NetPath("decision"),
        )
        found = run(
            built,
            handler,
            {"primary": CreditReport(score=7), "secondary": CreditReport(score=2)},
            (assess,),
        )
        # 7 * 1000 + 2 proves each parameter got its named place's token.
        assert found == [{"approved": True, "basis": 7002}]

    def test_swapped_bindings_swap_roles_observably(self) -> None:
        built = two_role_net()
        handler = PlaceBoundActivityHandler(
            net=built.net,
            transition=NetPath("assess"),
            activity=assess,
            bindings={"primary": "secondary", "secondary": "primary"},
            output=NetPath("decision"),
        )
        found = run(
            built,
            handler,
            {"primary": CreditReport(score=7), "secondary": CreditReport(score=2)},
            (assess,),
        )
        assert found == [{"approved": True, "basis": 2007}]

    def test_binding_to_a_non_input_place_is_rejected(self) -> None:
        built = two_role_net()
        with pytest.raises(ValueError, match="parameter 'primary' binds to 'decision', which is not an input"):
            PlaceBoundActivityHandler(
                net=built.net,
                transition=NetPath("assess"),
                activity=assess,
                bindings={"primary": "decision", "secondary": "secondary"},
                output=NetPath("decision"),
            )

    def test_incomplete_bindings_are_rejected(self) -> None:
        built = two_role_net()
        with pytest.raises(ValueError, match="must cover parameters"):
            PlaceBoundActivityHandler(
                net=built.net,
                transition=NetPath("assess"),
                activity=assess,
                bindings={"primary": "primary"},
                output=NetPath("decision"),
            )
