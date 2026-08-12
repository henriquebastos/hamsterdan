"""AX13 — sibling amortization: the change-intent concern grown onto the
AX11 fragment, verified place-for-place against a production-style oracle
extended with the verbatim `authorize_change`/`change_basis` retire wiring.

The economics question lives in the index: this file proves the marginal
authoring is *correct*, the index measures what it *cost*.
"""

from __future__ import annotations

import dataclasses

from ax11_compiler import CompiledFragment, compile_fragment
from ax11_fragment import conversation_intents
from ax13_fragment import CHANGE_LANE_BODY, MUTATION_STATE, conversation_intents_with_change
from petrus.engine import Engine
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.dsl import NetSpec, arc, petri_handler, typed_guard
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, NetPath, Token
from test_ax11_fragment import (
    AUTHORITY_VALUE,
    PRODUCTION_PLACES,
    REVIEW_SEED,
    classification_request,
    classify_conversation,
    dispatch,
    drive_bounded,
    intent,
    place_data,
)

from hamsterdan.contracts.readiness import (
    Authority,
    ChangeRequest,
    ConversationClassificationRequest,
    ConversationPublicationState,
    HumanState,
    Intent,
    IntentBatch,
    MutationState,
    ReviewState,
)
from hamsterdan.readiness.net.topology import (
    _accept_intent,
    _authorize_change,
    _authorize_reply,
    _current,
    _guard,
    _mutation,
    _replyable,
    _unpack_intents,
    _valid_reply,
)
from hamsterdan.readiness.payloads import PydanticPayloadConverter

AX13_PLACES = {
    **PRODUCTION_PLACES,
    "mutation_state": "mutation_state",
    "work_change": "work.change",
}


# -- the production oracle: AX11's oracle plus the verbatim change concern --


def production_fragment_with_change():
    net = NetSpec("conversation-intents-change-production")
    p, t = net.p, net.t
    work, execute, retire_scope = net.s.work, net.s.execute, net.s.retire
    classify = execute.t.conversation(handler="classify_conversation")
    work.p.conversation(ConversationClassificationRequest) >> classify >> p.intent_batch(IntentBatch)
    (
        p.intent_batch
        >> t.unpack_intents(handler=petri_handler(_unpack_intents))
        >> (p.change_basis(Intent), p.intent_result(Intent), p.reply_basis(Intent), p.recovery_basis(Intent))
    )
    for name, owner_type, owner, kinds in (
        ("finding_intent", ReviewState, p.review_state(ReviewState), {"acknowledge", "dismiss", "defer"}),
        ("reminder_intent", HumanState, p.human_state(HumanState), {"snooze", "resume", "reassign"}),
    ):
        tr = getattr(t, f"accept_{name}")(
            handler=petri_handler(lambda b, o, typ=owner_type: _accept_intent(b, o, typ)),
            guards=_guard(
                lambda a, state, value, selected=kinds: (
                    _current(a, value) and value.authorized and value.kind in selected
                )
            ),
        )
        p.authority(Authority) >> arc.read() >> tr
        (owner, p.intent_result) >> tr >> owner
    authorize_reply = t.authorize_reply(
        handler=petri_handler(_authorize_reply),
        guards=typed_guard(_replyable, converter=PydanticPayloadConverter()),
    )
    p.authority >> arc.read() >> authorize_reply
    (
        (p.conversation_publication_state(ConversationPublicationState), p.reply_basis)
        >> authorize_reply
        >> (p.conversation_publication_state, work.p.conversation_reply)
    )
    reply_retire = retire_scope.t.reply_basis(guards=_guard(lambda a, v: not _valid_reply(a, v)))
    p.authority >> arc.read() >> reply_retire
    p.reply_basis >> reply_retire
    # -- marginal production wiring for the change concern (verbatim style) --
    authorize_change = t.authorize_change(
        handler=petri_handler(_authorize_change),
        guards=typed_guard(_mutation, converter=PydanticPayloadConverter()),
    )
    p.authority >> arc.read() >> authorize_change
    (
        (p.mutation_state(MutationState), p.change_basis)
        >> authorize_change
        >> (p.mutation_state, work.p.change(ChangeRequest))
    )
    change_retire = retire_scope.t.change_basis(guards=_guard(lambda a, m, v: not _mutation(a, m, v)))
    (p.authority, p.mutation_state) >> arc.read() >> change_retire
    p.change_basis >> change_retire
    return net.build(), abs(classify)


# -- engine plumbing --------------------------------------------------------


def seed_marking(places: dict[str, str], request, publication=None, mutation=None) -> Marking:
    seeds = {
        "authority": AUTHORITY_VALUE,
        "review_state": REVIEW_SEED,
        "human_state": HumanState(),
        "conversation_publication_state": publication or ConversationPublicationState(),
        "mutation_state": mutation or MutationState(),
        "work_conversation": request,
    }
    return Marking(
        {NetPath(places[name]): (Token(type(value).__name__, value.dump()),) for name, value in seeds.items()}
    )


def run_compiled(request, mutation=None, history=None, instance="ax13-authored") -> tuple[Engine, CompiledFragment]:
    compiled = compile_fragment(conversation_intents_with_change())
    engine = Engine.create(
        compiled.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=dispatch(),
        marking=seed_marking({name: str(path) for name, path in compiled.places.items()}, request, mutation=mutation),
        handlers=dict(compiled.handlers),
        guards=dict(compiled.built.guards),
        activities=compiled.activities,
    )
    drive_bounded(engine)
    return engine, compiled


def run_production(request, mutation=None) -> Engine:
    built, classify = production_fragment_with_change()
    handlers = dict(built.handlers)
    uri = built.net.handler_uri(classify)
    assert uri is not None
    handlers[uri] = DerivedActivityHandler(built.net, classify, classify_conversation)
    engine = Engine.create(
        built.net,
        "ax13-production",
        history=InMemoryHistoryStore(),
        dispatch=dispatch(),
        marking=seed_marking(AX13_PLACES, request, mutation=mutation),
        handlers=handlers,
        guards=dict(built.guards),
        activities=(classify_conversation.declaration,),
    )
    drive_bounded(engine)
    return engine


def assert_equivalent(authored: Engine, compiled: CompiledFragment, production: Engine) -> None:
    for logical, production_path in AX13_PLACES.items():
        assert place_data(authored, str(compiled.places[logical])) == place_data(production, production_path), (
            f"place {logical!r} diverged from production"
        )


# -- behavior parity for the marginal concern -------------------------------


class TestChangeConcernParity:
    def test_blocking_change_on_idle_concern_is_authorized(self) -> None:
        request = classification_request([{**intent("change"), "blocking": True}])
        authored, compiled = run_compiled(request)
        production = run_production(request)
        assert_equivalent(authored, compiled, production)
        [mutation] = place_data(authored, str(compiled.places["mutation_state"]))
        assert mutation["change_in_flight"] is True
        assert mutation["mutation_operation"].startswith("change:")
        [work] = place_data(authored, str(compiled.places["work_change"]))
        assert work["intent"]["kind"] == "change"
        assert place_data(authored, str(compiled.places["change_basis"])) == []

    def test_busy_mutation_concern_retires_the_change_not_parks_it(self) -> None:
        # Production semantics preserved verbatim: `not _mutation` includes
        # "concern busy", so — unlike the reply lane — a valid change intent
        # against an in-flight mutation is RETIRED, not parked.
        request = classification_request([{**intent("change"), "blocking": True}])
        busy = MutationState(change_in_flight=True, mutation_operation="prior-op")
        authored, compiled = run_compiled(request, mutation=busy)
        production = run_production(request, mutation=busy)
        assert_equivalent(authored, compiled, production)
        assert place_data(authored, str(compiled.places["change_basis"])) == []
        assert place_data(authored, str(compiled.places["work_change"])) == []
        [mutation] = place_data(authored, str(compiled.places["mutation_state"]))
        assert mutation["mutation_operation"] == "prior-op"

    def test_non_blocking_change_is_retired(self) -> None:
        request = classification_request([intent("change")])  # blocking=False default
        authored, compiled = run_compiled(request)
        production = run_production(request)
        assert_equivalent(authored, compiled, production)
        assert place_data(authored, str(compiled.places["change_basis"])) == []
        assert place_data(authored, str(compiled.places["work_change"])) == []

    def test_stale_change_is_retired(self) -> None:
        request = classification_request([{**intent("change", epoch=2), "blocking": True}])
        authored, compiled = run_compiled(request)
        production = run_production(request)
        assert_equivalent(authored, compiled, production)
        assert place_data(authored, str(compiled.places["change_basis"])) == []

    def test_mixed_batch_exercises_all_lanes_together(self) -> None:
        request = classification_request(
            [
                intent("acknowledge", arguments={"findings": ["F1"]}),
                intent("reply", arguments={"message": "hi"}),
                {**intent("update_base"), "blocking": True},
                intent("status"),
            ]
        )
        authored, compiled = run_compiled(request)
        production = run_production(request)
        assert_equivalent(authored, compiled, production)
        [work] = place_data(authored, str(compiled.places["work_change"]))
        assert work["intent"]["kind"] == "update_base"
        assert place_data(authored, str(compiled.places["work_conversation_reply"])) != []


# -- determinism, replay, and generated shape --------------------------------


class TestShapeAndReplay:
    def test_compilation_is_deterministic(self) -> None:
        first = compile_fragment(conversation_intents_with_change())
        second = compile_fragment(conversation_intents_with_change())
        assert serialize_net_definition(project_net_definition(first.built.net)) == serialize_net_definition(
            project_net_definition(second.built.net)
        )

    def test_replay_over_recompiled_net_reaches_same_marking(self) -> None:
        request = classification_request([{**intent("change"), "blocking": True}])
        history = InMemoryHistoryStore()
        original, compiled = run_compiled(request, history=history, instance="ax13-replay")
        recompiled = compile_fragment(conversation_intents_with_change())
        resumed = Engine.load(
            recompiled.built.net,
            "ax13-replay",
            history=history,
            dispatch=dispatch(),
            handlers=dict(recompiled.handlers),
            guards=dict(recompiled.built.guards),
            activities=recompiled.activities,
        )
        for name, path in compiled.places.items():
            assert place_data(resumed, str(recompiled.places[name])) == place_data(original, str(path))

    def test_marginal_net_growth_matches_production_exactly(self) -> None:
        # AX11: 11 places / 6 transitions / 23 arcs (production 22 — the
        # reply-retire widening arc). The change concern must add the same
        # elements on both sides: 2 places, 2 transitions, 8 arcs.
        def stats(net):
            arcs = sum(len(net.inputs(t)) + len(net.outputs(t)) for t in net.transitions)
            return len(tuple(net.places)), len(tuple(net.transitions)), arcs

        grown = compile_fragment(conversation_intents_with_change()).built.net
        base = compile_fragment(conversation_intents()).built.net
        production, _ = production_fragment_with_change()
        assert stats(base) == (11, 6, 23)
        assert stats(grown) == (13, 8, 31)
        assert stats(production.net) == (13, 8, 30)

    def test_change_retire_reads_match_production_no_extra_widening(self) -> None:
        # ~MUTATION's own roots already cover the negated predecessor's
        # roots, so — unlike the reply lane — ordered exclusivity adds no
        # arc production does not have.
        compiled = compile_fragment(conversation_intents_with_change())
        retire_inputs = {str(a.source): a.mode.value for a in compiled.built.net.inputs(NetPath("retire_change_basis"))}
        assert retire_inputs == {
            "authority": "read",
            "mutation_state": "read",
            "change_basis": "consume",
        }

    def test_every_marginal_transition_maps_to_ax13_source(self) -> None:
        compiled = compile_fragment(conversation_intents_with_change())
        for name in ("authorize_change", "retire_change_basis"):
            address = compiled.generated_by[name]
            entry = compiled.source_map[address]
            assert entry.origin is not None and "ax13_fragment.py" in entry.origin


# -- the AST-as-value property: growth is tree surgery ------------------------


class TestFragmentsAreValues:
    def test_surgery_on_ax11_fragment_equals_the_restated_fragment(self) -> None:
        # Because nodes are frozen values with non-identity origins, the
        # grown fragment can equally be produced by transforming AX11's
        # committed AST — same structure, byte-identical net.
        base = conversation_intents()
        [step, scatter_node] = base.body
        lanes = tuple(
            dataclasses.replace(l, then=CHANGE_LANE_BODY) if l.port.name == "change_basis" else l
            for l in scatter_node.lanes
        )
        surgery = dataclasses.replace(
            base,
            name="conversation-intents-change",
            states=(*base.states, MUTATION_STATE),
            body=(step, dataclasses.replace(scatter_node, lanes=lanes)),
        )
        restated = conversation_intents_with_change()
        assert surgery == restated
        assert serialize_net_definition(project_net_definition(compile_fragment(surgery).built.net)) == (
            serialize_net_definition(project_net_definition(compile_fragment(restated).built.net))
        )
