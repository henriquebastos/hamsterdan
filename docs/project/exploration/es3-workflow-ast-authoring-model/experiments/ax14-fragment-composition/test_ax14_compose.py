"""AX14 focused tests — fragment composition by explicit named-port identity.

Two oracles, both already proven:

- the AX13 **monolith** (`conversation_intents_with_change()`): if
  composition works, composing AX11's untouched base with the change
  hand-off fragment must produce the *same net*;
- the AX13 **production oracle** (`run_production`): the composed net
  must behave scenario-for-scenario like the verbatim production wiring.
"""

from __future__ import annotations

import pytest
from ax11_ast import WorkflowShapeError, case, choice, port, retire, state_port
from ax11_compiler import LoweringError, compile_fragment
from ax11_fragment import AUTHORITY, CHANGE_BASIS, RECOVERY_BASIS, conversation_intents
from ax11_predicates import on
from ax13_fragment import CHANGE_LANE_BODY, MUTATION_STATE, conversation_intents_with_change
from ax14_compose import WAIT, ComposedNet, CompositionError, compose, handoff_fragment
from ax14_fragments import change_concern, composed_conversation_and_change
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Net
from test_ax11_fragment import classification_request, dispatch, drive_bounded, intent, place_data
from test_ax13_fragment import AX13_PLACES, run_production, seed_marking

from hamsterdan.contracts.readiness import Authority, ChangeRequest, MutationState

# -- engine plumbing ---------------------------------------------------------


def run_composed(request, mutation=None, history=None, instance="ax14-composed") -> tuple[Engine, ComposedNet]:
    composed = composed_conversation_and_change()
    engine = Engine.create(
        composed.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=dispatch(),
        marking=seed_marking({name: str(path) for name, path in composed.places.items()}, request, mutation=mutation),
        handlers=dict(composed.handlers),
        guards=dict(composed.built.guards),
        activities=composed.activities,
    )
    drive_bounded(engine)
    return engine, composed


def assert_matches_production(composed_engine: Engine, composed: ComposedNet, production: Engine) -> None:
    for logical, production_path in AX13_PLACES.items():
        assert place_data(composed_engine, str(composed.places[logical])) == place_data(production, production_path), (
            f"place {logical!r} diverged from production"
        )


def definition_bytes(net: Net) -> bytes:
    return serialize_net_definition(project_net_definition(net))


def element_sets(net: Net):
    """Order-insensitive net shape: arcs lose their positions, nothing else."""
    body = project_net_definition(net).definition
    return (
        {p.model_dump_json() for p in body.places},
        {t.model_dump_json() for t in body.transitions},
        {a.model_dump_json(exclude={"position"}) for a in body.arcs},
    )


# -- the central identity claim ----------------------------------------------


class TestComposedNetIdentity:
    def test_composition_equals_the_ax13_monolith_byte_for_byte(self) -> None:
        # The strongest possible oracle: composing AX11's untouched base
        # with the hand-off concern serializes identically to AX13's
        # restated monolith. Composition is not "similar" — it is the
        # same net.
        composed = composed_conversation_and_change()
        monolith = compile_fragment(conversation_intents_with_change())
        assert definition_bytes(composed.built.net) == definition_bytes(monolith.built.net)

    def test_composition_is_deterministic(self) -> None:
        assert definition_bytes(composed_conversation_and_change().built.net) == definition_bytes(
            composed_conversation_and_change().built.net
        )

    def test_fragment_order_is_explicit_and_only_permutes_arc_positions(self) -> None:
        # The compose() argument list is the deterministic order. Reversing
        # it yields the same places, transitions, guards, and arcs — only
        # serialized arc *positions* move, so byte identity requires the
        # authored order to be part of the composition's definition.
        forward = compose("conversation-intents-change", conversation_intents(), change_concern())
        reverse = compose("conversation-intents-change", change_concern(), conversation_intents())
        assert element_sets(forward.built.net) == element_sets(reverse.built.net)
        assert definition_bytes(forward.built.net) != definition_bytes(reverse.built.net)


# -- sources are values --------------------------------------------------------


class TestSourcesStayUntouched:
    def test_compose_mutates_neither_fragment(self) -> None:
        base = conversation_intents()
        concern = change_concern()
        compose("conversation-intents-change", base, concern)
        assert base == conversation_intents()
        assert concern == change_concern()

    def test_base_still_compiles_alone_with_its_exit_lane_open(self) -> None:
        base = compile_fragment(conversation_intents())
        assert "mutation_state" not in base.places
        assert "authorize_change" not in base.generated_by


# -- identity rules: what merges, what stays apart, what fails ----------------


class TestExplicitIdentity:
    def test_same_color_ports_stay_distinct_places(self) -> None:
        # Four Intent-colored ports; only the *named* hand-off is shared.
        composed = composed_conversation_and_change()
        intent_places = {"intent_result", "reply_basis", "change_basis", "recovery_basis"}
        assert intent_places <= set(composed.places)
        assert len({str(composed.places[name]) for name in intent_places}) == 4

    def test_shared_name_with_different_color_fails(self) -> None:
        impostor = handoff_fragment(
            "change-impostor",
            entry=port("change_basis", ChangeRequest),
            body=choice(case(when=on(ChangeRequest).epoch == 0, then=retire()), otherwise=WAIT),
        )
        with pytest.raises(CompositionError, match=r"port 'change_basis'.*Port\[ChangeRequest\].*Port\[Intent\]"):
            compose("bad", conversation_intents(), impostor)

    def test_shared_name_with_different_kind_fails(self) -> None:
        # Same name, same color, but StatePort (consume/re-produce) versus
        # the base's ReadPort: silently unifying these would change arc
        # semantics, so it must refuse.
        impostor = handoff_fragment(
            "change-state-authority",
            entry=CHANGE_BASIS,
            states=(state_port("authority", Authority), MUTATION_STATE),
            body=CHANGE_LANE_BODY,
        )
        with pytest.raises(CompositionError, match=r"port 'authority'.*StatePort\[Authority\].*ReadPort\[Authority\]"):
            compose("bad", conversation_intents(), impostor)

    def test_duplicate_transition_names_across_fragments_fail(self) -> None:
        # A second concern reusing the same lane body would generate a
        # second `authorize_change` transition: one namespace, loud failure.
        twin = handoff_fragment(
            "recovery-as-change",
            entry=RECOVERY_BASIS,
            reads=(AUTHORITY,),
            states=(MUTATION_STATE,),
            body=CHANGE_LANE_BODY,
        )
        with pytest.raises(LoweringError, match="duplicate transition 'authorize_change'"):
            compose("bad", conversation_intents(), change_concern(), twin)

    def test_missing_required_context_port_fails(self) -> None:
        # The concern's guard reads Authority; forgetting the read port is
        # caught by AX11's existing resolution error, at compose time.
        blind = handoff_fragment("change-blind", entry=CHANGE_BASIS, states=(MUTATION_STATE,), body=CHANGE_LANE_BODY)
        with pytest.raises(LoweringError, match="reads Authority, but the fragment declares no port of that type"):
            compose("bad", blind)

    def test_duplicate_fragment_names_fail(self) -> None:
        with pytest.raises(CompositionError, match="unique names"):
            compose("bad", change_concern(), change_concern())

    def test_handoff_body_must_be_a_choice(self) -> None:
        with pytest.raises(WorkflowShapeError, match="body= needs choice"):
            handoff_fragment("bad", entry=CHANGE_BASIS, body=retire())


# -- behavior parity against the production oracle ----------------------------


class TestComposedBehaviorParity:
    def test_blocking_change_on_idle_concern_is_authorized(self) -> None:
        request = classification_request([{**intent("change"), "blocking": True}])
        engine, composed = run_composed(request)
        assert_matches_production(engine, composed, run_production(request))
        [work] = place_data(engine, str(composed.places["work_change"]))
        assert work["intent"]["kind"] == "change"
        [mutation] = place_data(engine, str(composed.places["mutation_state"]))
        assert mutation["change_in_flight"] is True

    def test_busy_mutation_concern_retires_the_change(self) -> None:
        request = classification_request([{**intent("change"), "blocking": True}])
        busy = MutationState(change_in_flight=True, mutation_operation="prior-op")
        engine, composed = run_composed(request, mutation=busy)
        assert_matches_production(engine, composed, run_production(request, mutation=busy))
        assert place_data(engine, str(composed.places["work_change"])) == []
        assert place_data(engine, str(composed.places["change_basis"])) == []

    def test_mixed_batch_crosses_the_composition_seam_in_one_run(self) -> None:
        # Findings and replies handled by the base fragment, the change by
        # the composed concern, "status" dropped — one batch, one net.
        request = classification_request(
            [
                intent("acknowledge", arguments={"findings": ["F1"]}),
                intent("reply", arguments={"message": "hi"}),
                {**intent("update_base"), "blocking": True},
                intent("status"),
            ]
        )
        engine, composed = run_composed(request)
        assert_matches_production(engine, composed, run_production(request))
        [work] = place_data(engine, str(composed.places["work_change"]))
        assert work["intent"]["kind"] == "update_base"
        assert place_data(engine, str(composed.places["work_conversation_reply"])) != []


# -- replay --------------------------------------------------------------------


class TestReplay:
    def test_replay_over_recomposed_net_reaches_same_marking(self) -> None:
        request = classification_request([{**intent("change"), "blocking": True}])
        history = InMemoryHistoryStore()
        original, composed = run_composed(request, history=history, instance="ax14-replay")
        recomposed = composed_conversation_and_change()
        resumed = Engine.load(
            recomposed.built.net,
            "ax14-replay",
            history=history,
            dispatch=dispatch(),
            handlers=dict(recomposed.handlers),
            guards=dict(recomposed.built.guards),
            activities=recomposed.activities,
        )
        for name, path in composed.places.items():
            assert place_data(resumed, str(recomposed.places[name])) == place_data(original, str(path))


# -- traceability across the seam ----------------------------------------------


class TestTraceability:
    def test_every_transition_maps_to_its_owning_fragment_and_file(self) -> None:
        composed = composed_conversation_and_change()
        expectations = {
            "authorize_change": ("/change-intents", "ax13_fragment.py"),
            "retire_change_basis": ("/change-intents", None),
            "authorize_reply": ("/conversation-intents", "ax11_fragment.py"),
            "classify_conversation": ("/conversation-intents", "ax11_fragment.py"),
        }
        for name, (prefix, filename) in expectations.items():
            address = composed.generated_by[name]
            assert address.startswith(prefix), f"{name} mapped to {address}"
            origin = composed.source_map[address].origin
            if filename is not None:
                assert origin is not None and filename in origin

    def test_handoff_wait_policy_is_recorded(self) -> None:
        composed = composed_conversation_and_change()
        entry = composed.source_map["/change-intents/body/0/otherwise"]
        assert "WAIT" in entry.node
