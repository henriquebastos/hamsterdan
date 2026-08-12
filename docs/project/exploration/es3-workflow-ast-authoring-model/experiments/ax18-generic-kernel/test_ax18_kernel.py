"""AX18 focused tests — the net-agnostic kernel under the domain sugar.

Three claims, each falsifiable:

1. The kernel IR expresses arbitrary-net shapes the AX11 vocabulary has
   no words for (same-color place pairs, cycles, handler-less guarded
   competition, disconnected places) and the frozen runtime executes
   them unchanged.
2. Desugaring the real AX13 fragment through the kernel reproduces the
   AX11 compiler's net **byte-for-byte** — the domain vocabulary is
   sugar over the kernel, not a parallel semantics.
3. Source mapping survives both stages, and the kernel honestly loses
   what it cannot represent (policy-only records like WAIT/EXIT lanes).
"""

from __future__ import annotations

import pytest
from ax11_compiler import compile_fragment
from ax13_fragment import conversation_intents_with_change
from ax18_desugar import compile_via_kernel, desugar_fragment
from ax18_kernel import (
    KernelPlace,
    KernelShapeError,
    KernelTransition,
    consume,
    kernel_net,
    lower_kernel,
    produce,
)
from ax18_neutral import shuttle_net
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, Net, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import (
    AUTHORITY_VALUE,
    REVIEW_SEED,
    classification_request,
    dispatch,
    drive_bounded,
    intent,
    place_data,
)

from hamsterdan.contracts.readiness import (
    ConversationPublicationState,
    HumanState,
    MutationState,
)

# -- helpers --------------------------------------------------------------------


def definition_bytes(net: Net) -> bytes:
    return serialize_net_definition(project_net_definition(net))


# -- claim 0: the kernel refuses impossible shapes at declaration time ------------


class TestKernelShape:
    def test_arcs_must_reference_declared_places(self) -> None:
        with pytest.raises(KernelShapeError, match="undeclared place 'nowhere'"):
            kernel_net("bad", KernelTransition(name="t", arcs=(consume("nowhere"),)))

    def test_place_names_are_identity_and_must_be_unique(self) -> None:
        with pytest.raises(KernelShapeError, match="duplicate place 'p'"):
            kernel_net("bad", KernelPlace("p", "A"), KernelPlace("p", "B"))

    def test_transition_names_must_be_unique(self) -> None:
        with pytest.raises(KernelShapeError, match="duplicate transition 't'"):
            kernel_net(
                "bad",
                KernelPlace("p", "A"),
                KernelTransition(name="t", arcs=(consume("p"),)),
                KernelTransition(name="t", arcs=(consume("p"),)),
            )

    def test_a_transition_without_arcs_is_meaningless(self) -> None:
        with pytest.raises(KernelShapeError, match="no arcs"):
            kernel_net("bad", KernelTransition(name="t", arcs=()))

    def test_place_names_must_be_cel_safe_identifiers(self) -> None:
        with pytest.raises(KernelShapeError, match="bare identifier"):
            kernel_net("bad", KernelPlace("not a name", "A"))

    def test_same_color_places_are_distinct_by_name(self) -> None:
        # The AX3 ruling, structural: color never identifies a place.
        net = kernel_net(
            "ok",
            KernelPlace("left", "Slot"),
            KernelPlace("right", "Slot"),
            KernelTransition(name="move", arcs=(consume("left"), produce("right"))),
        )
        lowered = lower_kernel(net)
        assert str(lowered.places["left"]) == "left"
        assert str(lowered.places["right"]) == "right"


# -- claim 1: the neutral net runs on the frozen engine ---------------------------


def run_shuttle(*, enabled: bool, fuel: int) -> Engine:
    lowered = lower_kernel(shuttle_net())
    marking = Marking(
        {
            NetPath("left"): (Token("Slot", {"id": "s1"}),),
            NetPath("spare"): (Token("Slot", {"id": "unused"}),),
            NetPath("fuel"): tuple(Token("Pellet", {"n": i}) for i in range(fuel)),
            NetPath("meter"): (Token("Meter", {"enabled": enabled}),),
        }
    )
    engine = Engine.create(
        lowered.built.net,
        "ax18-neutral",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=marking,
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )
    drive_bounded(engine)
    return engine


class TestNeutralNet:
    def test_the_cycle_fires_until_the_fuel_marking_bounds_it(self) -> None:
        # left -> right burns a pellet; right -> left is free: with three
        # pellets the cycle laps three times and quiesces with the slot
        # home on `left`. Liveness is bounded by *marking*, not guards —
        # no handler anywhere in the net.
        engine = run_shuttle(enabled=True, fuel=3)
        assert place_data(engine, "left") == [{"id": "s1"}]
        assert place_data(engine, "right") == []
        assert place_data(engine, "fuel") == []

    def test_the_guard_reads_the_meter_and_routes_the_competition(self) -> None:
        # `shuttle_right` and `drain` compete for `left`; the read-arc
        # guard on `meter.enabled` decides, with zero Python code.
        engine = run_shuttle(enabled=False, fuel=3)
        assert place_data(engine, "left") == []  # drained
        assert place_data(engine, "right") == []
        assert len(place_data(engine, "fuel")) == 3  # never burned

    def test_the_disconnected_place_is_legal_and_untouched(self) -> None:
        engine = run_shuttle(enabled=True, fuel=1)
        assert place_data(engine, "spare") == [{"id": "unused"}]

    def test_passthrough_drops_tokens_no_output_arc_admits(self) -> None:
        # The consumed Pellet has no admitting output arc on
        # `shuttle_right`: frozen `route` documents the drop. The kernel
        # inherits this semantics — a consume with no same-color produce
        # is a retire *for that color*.
        engine = run_shuttle(enabled=True, fuel=1)
        assert place_data(engine, "fuel") == []
        assert place_data(engine, "right") == []  # slot lapped back home
        assert place_data(engine, "left") == [{"id": "s1"}]


# -- claim 2: desugared AX13 fragment is byte-identical ---------------------------


class TestDesugaredEquivalence:
    def test_the_kernel_pipeline_reproduces_the_ax11_net_byte_for_byte(self) -> None:
        direct = compile_fragment(conversation_intents_with_change())
        via_kernel = compile_via_kernel(conversation_intents_with_change())
        assert definition_bytes(via_kernel.built.net) == definition_bytes(direct.built.net)

    def test_places_and_transition_attribution_agree(self) -> None:
        direct = compile_fragment(conversation_intents_with_change())
        via_kernel = compile_via_kernel(conversation_intents_with_change())
        assert dict(via_kernel.places) == dict(direct.places)
        assert dict(via_kernel.generated_by) == dict(direct.generated_by)

    def test_every_generated_guard_matches_the_ax11_rendering(self) -> None:
        direct = compile_fragment(conversation_intents_with_change())
        via_kernel = compile_via_kernel(conversation_intents_with_change())
        direct_guards = {
            address: entry.guard_cel for address, entry in direct.source_map.items() if entry.transition is not None
        }
        kernel_guards = {address: entry.guard_cel for address, entry in via_kernel.source_map.items()}
        assert kernel_guards == direct_guards

    def test_the_kernel_ir_is_data_places_transitions_arcs_and_nothing_else(self) -> None:
        net = desugar_fragment(conversation_intents_with_change())
        kinds = {type(node).__name__ for node in net.nodes}
        assert kinds == {"KernelPlace", "KernelTransition"}
        # 13 authored/generated places, 8 transitions — the same counts
        # the AX13 net serializes, now visible pre-build as plain data.
        assert len([n for n in net.nodes if isinstance(n, KernelPlace)]) == 13
        assert len([n for n in net.nodes if isinstance(n, KernelTransition)]) == 8


# -- claim 2b: behavior equivalence on the real change scenario -------------------


def seed(places, request) -> Marking:
    values = {
        "authority": AUTHORITY_VALUE,
        "review_state": REVIEW_SEED,
        "human_state": HumanState(),
        "conversation_publication_state": ConversationPublicationState(),
        "mutation_state": MutationState(),
        "work_conversation": request,
    }
    return Marking({places[name]: (Token(type(v).__name__, v.dump()),) for name, v in values.items()})


def run(compiled, request, instance: str) -> Engine:
    engine = Engine.create(
        compiled.built.net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=dispatch(),
        marking=seed(compiled.places, request),
        handlers=dict(compiled.handlers),
        guards=dict(compiled.built.guards),
        activities=compiled.activities,
    )
    drive_bounded(engine)
    return engine


class TestDesugaredBehavior:
    def test_the_change_scenario_lands_identically_place_by_place(self) -> None:
        request = classification_request([{**intent("update_base"), "blocking": True}])
        direct = compile_fragment(conversation_intents_with_change())
        via_kernel = compile_via_kernel(conversation_intents_with_change())
        direct_engine = run(direct, request, "ax18-direct")
        kernel_engine = run(via_kernel, request, "ax18-kernel")
        for name in direct.places:
            assert place_data(kernel_engine, str(via_kernel.places[name])) == place_data(
                direct_engine, str(direct.places[name])
            ), name
        [work] = place_data(kernel_engine, str(via_kernel.places["work_change"]))
        assert work["operation"].startswith("change:")
        [state] = place_data(kernel_engine, str(via_kernel.places["mutation_state"]))
        assert state["change_in_flight"] is True


# -- claim 3: source mapping and its honest boundary -------------------------------


class TestSourceMapping:
    def test_the_change_case_maps_through_both_stages_to_its_authoring_site(self) -> None:
        via_kernel = compile_via_kernel(conversation_intents_with_change())
        entry = via_kernel.source_map["/body/1/lanes/change_basis/cases/0"]
        assert entry.transition == "authorize_change"
        assert entry.origin is not None and "ax13_fragment.py" in entry.origin
        assert entry.guard_cel is not None and "change_in_flight == false" in entry.guard_cel
        assert via_kernel.generated_by["authorize_change"] == "/body/1/lanes/change_basis/cases/0"

    def test_policy_only_records_do_not_survive_into_the_kernel(self) -> None:
        # AX11's source map records WAIT gap policies and EXIT lanes as
        # transition-less entries. The kernel has no transition-less
        # notions — that knowledge belongs to the authoring layer, and
        # this asymmetry is the layer boundary, stated.
        direct = compile_fragment(conversation_intents_with_change())
        via_kernel = compile_via_kernel(conversation_intents_with_change())
        policy_only = {address for address, entry in direct.source_map.items() if entry.transition is None}
        assert "/body/1/lanes/recovery_basis" in policy_only  # the EXIT lane
        assert policy_only.isdisjoint(via_kernel.source_map.keys())
