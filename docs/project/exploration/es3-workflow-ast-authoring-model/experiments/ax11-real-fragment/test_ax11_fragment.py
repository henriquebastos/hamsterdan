"""AX11 focused tests — the leading design against the production oracle.

The oracle is the production authoring style itself: the conversation-
intent wiring copied verbatim from `readiness/net/topology.py` (same
`NetSpec` fluent arcs, same binding handlers, same Python guards).
Both nets are driven from identical seeds through the frozen Engine and
their final markings compared place by place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from ax11_ast import (
    DROP,
    EXIT,
    WAIT,
    WorkflowShapeError,
    case,
    choice,
    fold,
    fragment,
    lane,
    port,
    retire,
    scatter,
    state_port,
    update,
)
from ax11_compiler import CompiledFragment, LoweringError, compile_fragment
from ax11_fragment import (
    AUTHORITY,
    CURRENT,
    ENTRY,
    HUMAN_STATE,
    INTENT_RESULT,
    PUBLICATION_STATE,
    REPLY_BASIS,
    REVIEW_STATE,
    accept_finding_intent,
    classify_conversation,
    conversation_intents,
    unpack_intents,
)
from ax11_predicates import PredicateTypeError, on
from petrus.engine import Engine
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.dsl import BuiltNet, NetSpec, arc, petri_handler, typed_guard
from petrus.impetus.history import ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch

from hamsterdan.contracts.readiness import (
    Authority,
    ConversationClassificationRequest,
    ConversationObservation,
    ConversationPublicationRequest,
    ConversationPublicationState,
    HumanState,
    Intent,
    IntentBatch,
    ReadinessSnapshot,
    ReviewState,
)
from hamsterdan.readiness.net.topology import (
    _accept_intent,
    _authorize_reply,
    _current,
    _guard,
    _replyable,
    _unpack_intents,
    _valid_reply,
)
from hamsterdan.readiness.payloads import PydanticPayloadConverter

# -- shared fixtures ------------------------------------------------------

AUTHORITY_VALUE = Authority(
    repository_id="r1",
    pr_number=7,
    epoch=3,
    head="h3",
    base_head="b1",
    strict_base=True,
    base_current=True,
    policy_digest="pd",
)

SNAPSHOT = ReadinessSnapshot(
    repository_id="r1",
    pr_number=7,
    epoch=3,
    head="h3",
    base_head="b1",
    strict_base=True,
    base_current=True,
)


def intent(kind: str, *, authorized: bool = True, epoch: int = 3, head: str = "h3", arguments: dict | None = None):
    return {
        "epoch": epoch,
        "head": head,
        "kind": kind,
        "digest": f"d-{kind}",
        "authorized": authorized,
        "blocking": False,
        "arguments": arguments or {},
        "base_head": "",
        "policy_digest": "",
    }


def classification_request(intents: list[dict]) -> ConversationClassificationRequest:
    return ConversationClassificationRequest(
        epoch=3,
        head="h3",
        operation="op-classify",
        base_head="b1",
        policy_digest="pd",
        comment=ConversationObservation(epoch=3, head="h3", authorized=True, text=json.dumps(intents)),
        control=SNAPSHOT,
    )


REVIEW_SEED = ReviewState(
    review="blocking",
    findings=[
        {"id": "F1", "blocking": True, "disposition": "new"},
        {"id": "F2", "blocking": False, "disposition": "new"},
    ],
)

# Logical port name -> production place path (the compiled net uses the
# logical names directly as flat root-scope places).
PRODUCTION_PLACES = {
    "work_conversation": "work.conversation",
    "intent_batch": "intent_batch",
    "intent_result": "intent_result",
    "reply_basis": "reply_basis",
    "change_basis": "change_basis",
    "recovery_basis": "recovery_basis",
    "review_state": "review_state",
    "human_state": "human_state",
    "conversation_publication_state": "conversation_publication_state",
    "authority": "authority",
    "work_conversation_reply": "work.conversation_reply",
}


# -- the production oracle: topology.py's own style, copied verbatim ------


@dataclass(frozen=True)
class ProductionNet:
    built: BuiltNet
    classify: NetPath


def production_fragment() -> ProductionNet:
    net = NetSpec("conversation-intents-production")
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
        >> (p.conversation_publication_state, work.p.conversation_reply(ConversationPublicationRequest))
    )
    reply_retire = retire_scope.t.reply_basis(guards=_guard(lambda a, v: not _valid_reply(a, v)))
    p.authority >> arc.read() >> reply_retire
    p.reply_basis >> reply_retire
    return ProductionNet(built=net.build(), classify=abs(classify))


# -- engine plumbing ------------------------------------------------------


def seed_marking(places: dict[str, str], request: ConversationClassificationRequest, publication=None) -> Marking:
    publication = publication or ConversationPublicationState()
    seeds = {
        "authority": AUTHORITY_VALUE,
        "review_state": REVIEW_SEED,
        "human_state": HumanState(),
        "conversation_publication_state": publication,
        "work_conversation": request,
    }
    return Marking(
        {NetPath(places[name]): (Token(type(value).__name__, value.dump()),) for name, value in seeds.items()}
    )


def dispatch() -> InlineDispatch:
    return InlineDispatch({"classify_conversation": classify_conversation})


def drive_bounded(subject: Engine, limit: int = 100) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def run_compiled(
    request: ConversationClassificationRequest,
    publication=None,
    history=None,
    instance: str = "ax11-authored",
) -> tuple[Engine, CompiledFragment]:
    compiled = compile_fragment(conversation_intents())
    engine = Engine.create(
        compiled.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=dispatch(),
        marking=seed_marking({name: str(path) for name, path in compiled.places.items()}, request, publication),
        handlers=dict(compiled.handlers),
        guards=dict(compiled.built.guards),
        activities=compiled.activities,
    )
    drive_bounded(engine)
    return engine, compiled


def run_production(request: ConversationClassificationRequest, publication=None) -> Engine:
    oracle = production_fragment()
    handlers = dict(oracle.built.handlers)
    uri = oracle.built.net.handler_uri(oracle.classify)
    assert uri is not None
    handlers[uri] = DerivedActivityHandler(oracle.built.net, oracle.classify, classify_conversation)
    engine = Engine.create(
        oracle.built.net,
        "ax11-production",
        history=InMemoryHistoryStore(),
        dispatch=dispatch(),
        marking=seed_marking(PRODUCTION_PLACES, request, publication),
        handlers=handlers,
        guards=dict(oracle.built.guards),
        activities=(classify_conversation.declaration,),
    )
    drive_bounded(engine)
    return engine


def place_data(engine: Engine, path: str) -> list[dict]:
    return [token.data for token in engine.marking.place(NetPath(path))]


def assert_equivalent(authored: Engine, compiled: CompiledFragment, production: Engine) -> None:
    for logical, production_path in PRODUCTION_PLACES.items():
        assert place_data(authored, str(compiled.places[logical])) == place_data(production, production_path), (
            f"place {logical!r} diverged from production"
        )


# -- behavior parity ------------------------------------------------------


class TestProductionParity:
    def test_mixed_batch_matches_production_place_for_place(self) -> None:
        request = classification_request(
            [
                intent("acknowledge", arguments={"findings": ["F1"]}),
                intent("snooze"),
                intent("reply", arguments={"message": "hi"}),
                intent("change"),
                intent("recover_publication", arguments={"target": "conversation"}),
                intent("status"),  # routed nowhere: rest=DROP / production's silent drop
                intent("dismiss", authorized=False),  # parks: otherwise=WAIT
            ]
        )
        authored, compiled = run_compiled(request)
        production = run_production(request)
        assert_equivalent(authored, compiled, production)

        [review] = place_data(authored, str(compiled.places["review_state"]))
        assert review["findings"][0]["disposition"] == "acknowledge"
        assert review["review"] == "clear"
        [human] = place_data(authored, str(compiled.places["human_state"]))
        assert human["reminder_snoozed"] is True
        [publication] = place_data(authored, str(compiled.places["conversation_publication_state"]))
        assert publication["conversation_requested"] is True
        [work] = place_data(authored, str(compiled.places["work_conversation_reply"]))
        assert work["operation"].startswith("conversation-reply:")
        assert [t["kind"] for t in place_data(authored, str(compiled.places["intent_result"]))] == ["dismiss"]
        assert [t["kind"] for t in place_data(authored, str(compiled.places["change_basis"]))] == ["change"]
        assert [t["kind"] for t in place_data(authored, str(compiled.places["recovery_basis"]))] == [
            "recover_publication"
        ]
        assert place_data(authored, str(compiled.places["reply_basis"])) == []

    def test_busy_publication_concern_parks_a_valid_reply(self) -> None:
        request = classification_request([intent("reply", arguments={"message": "hi"})])
        busy = ConversationPublicationState(conversation_requested=True, conversation_operation="prior-op")
        authored, compiled = run_compiled(request, publication=busy)
        production = run_production(request, publication=busy)
        assert_equivalent(authored, compiled, production)
        assert [t["kind"] for t in place_data(authored, str(compiled.places["reply_basis"]))] == ["reply"]
        assert place_data(authored, str(compiled.places["work_conversation_reply"])) == []

    def test_empty_message_reply_is_retired(self) -> None:
        request = classification_request([intent("reply", arguments={"message": ""})])
        authored, compiled = run_compiled(request)
        production = run_production(request)
        assert_equivalent(authored, compiled, production)
        assert place_data(authored, str(compiled.places["reply_basis"])) == []
        assert place_data(authored, str(compiled.places["work_conversation_reply"])) == []

    def test_missing_message_key_reply_is_retired_not_stuck(self) -> None:
        # The CEL has() presence guard: a reply whose arguments omit the key
        # entirely must be decidable, not a raising (silently parking) guard.
        request = classification_request([intent("reply")])
        authored, compiled = run_compiled(request)
        production = run_production(request)
        assert_equivalent(authored, compiled, production)
        assert place_data(authored, str(compiled.places["reply_basis"])) == []

    def test_stale_epoch_reply_is_retired(self) -> None:
        request = classification_request([intent("reply", epoch=2, arguments={"message": "hi"})])
        authored, compiled = run_compiled(request)
        production = run_production(request)
        assert_equivalent(authored, compiled, production)
        assert place_data(authored, str(compiled.places["reply_basis"])) == []


# -- replay and determinism ----------------------------------------------


class TestReplayAndDeterminism:
    def test_compilation_is_deterministic(self) -> None:
        first = compile_fragment(conversation_intents())
        second = compile_fragment(conversation_intents())
        assert serialize_net_definition(project_net_definition(first.built.net)) == serialize_net_definition(
            project_net_definition(second.built.net)
        )

    def test_replay_over_recompiled_net_reaches_same_marking(self) -> None:
        request = classification_request(
            [intent("acknowledge", arguments={"findings": ["F1"]}), intent("reply", arguments={"message": "hi"})]
        )
        history = InMemoryHistoryStore()
        original, compiled = run_compiled(request, history=history, instance="ax11-replay")

        recompiled = compile_fragment(conversation_intents())
        resumed = Engine.load(
            recompiled.built.net,
            "ax11-replay",
            history=history,
            dispatch=dispatch(),
            handlers=dict(recompiled.handlers),
            guards=dict(recompiled.built.guards),
            activities=recompiled.activities,
        )
        for name, path in compiled.places.items():
            assert place_data(resumed, str(recompiled.places[name])) == place_data(original, str(path))
        assert len([r for r in resumed.records if isinstance(r, ActivityRequested)]) == 1


# -- generated shape and source mapping ------------------------------------


class TestGeneratedShape:
    def test_net_shape_names_every_semantic_element(self) -> None:
        compiled = compile_fragment(conversation_intents())
        net = compiled.built.net
        assert sorted(str(t) for t in net.transitions) == [
            "accept_finding_intent",
            "accept_reminder_intent",
            "authorize_reply",
            "classify_conversation",
            "retire_reply_basis",
            "unpack_intents",
        ]
        assert sorted(str(p) for p in net.places) == sorted(PRODUCTION_PLACES)

    def test_ordered_exclusivity_widens_retire_scope_with_a_read_arc(self) -> None:
        # retire's own predicate never reads ConversationPublicationState, but
        # the negated authorize predecessor does: the compiler must bind it.
        compiled = compile_fragment(conversation_intents())
        net = compiled.built.net
        retire_inputs = {str(a.source): a.mode.value for a in net.inputs(NetPath("retire_reply_basis"))}
        assert retire_inputs["conversation_publication_state"] == "read"
        assert retire_inputs["reply_basis"] == "consume"
        [entry] = [e for e in compiled.source_map.values() if e.transition == "retire_reply_basis"]
        assert "scope widened by read arcs on ['ConversationPublicationState']" in entry.node
        assert "!(" in entry.guard_cel and "conversation_requested" in entry.guard_cel

    def test_every_transition_maps_back_to_an_authoring_site(self) -> None:
        compiled = compile_fragment(conversation_intents())
        for transition in compiled.built.net.transitions:
            address = compiled.generated_by[str(transition)]
            entry = compiled.source_map[address]
            if entry.origin is not None:
                assert "ax11_fragment.py" in entry.origin
        waits = [a for a, e in compiled.source_map.items() if "WAIT" in e.node]
        assert len(waits) == 2  # both park decisions are recorded, not implied

    def test_guards_compile_to_binding_scoped_cel(self) -> None:
        compiled = compile_fragment(conversation_intents())
        [authorize] = [e for e in compiled.source_map.values() if e.transition == "authorize_reply"]
        assert "(reply_basis[0].data.epoch == authority[0].data.epoch)" in authorize.guard_cel
        assert "has(reply_basis[0].data.arguments.message)" in authorize.guard_cel
        assert "(conversation_publication_state[0].data.conversation_requested == false)" in authorize.guard_cel


# -- error quality ---------------------------------------------------------


class TestErrorQuality:
    def test_unknown_field_lists_the_alternatives(self) -> None:
        with pytest.raises(PredicateTypeError, match="Intent has no field 'knd'.*kind"):
            _ = on(Intent).knd == "reply"

    def test_impossible_literal_is_refused_with_the_declared_values(self) -> None:
        with pytest.raises(PredicateTypeError, match="can never equal 'replyy'.*reply"):
            _ = on(Intent).kind == "replyy"

    def test_map_key_comparison_demands_a_presence_guard(self) -> None:
        with pytest.raises(PredicateTypeError, match="may be absent.*present"):
            case(when=on(Intent).arguments["message"] != "", then=retire())

    def test_overlapping_lanes_are_refused_at_construction(self) -> None:
        with pytest.raises(WorkflowShapeError, match="both claim 'reply'"):
            scatter(
                unpack_intents,
                lane(port("a", Intent), where=on(Intent).kind == "reply", then=EXIT),
                lane(port("b", Intent), where=on(Intent).kind.one_of("reply", "status"), then=EXIT),
                rest=DROP,
            )

    def test_scatter_demands_an_explicit_rest_policy(self) -> None:
        with pytest.raises(WorkflowShapeError, match="rest=DROP.*written down"):
            scatter(
                unpack_intents,
                lane(port("a", Intent), where=on(Intent).kind == "reply", then=EXIT),
                rest=None,  # type: ignore[arg-type]
            )

    def test_choice_demands_an_explicit_gap_policy(self) -> None:
        with pytest.raises(WorkflowShapeError, match="otherwise=WAIT.*otherwise=retire"):
            choice(
                case(when=on(Intent).kind == "reply", then=retire()),
                otherwise=None,  # type: ignore[arg-type]
            )

    def test_update_return_shape_is_checked_against_state_and_emits(self) -> None:
        def wrong(
            authority: Authority, state: ConversationPublicationState, value: Intent
        ) -> ConversationPublicationState:
            raise NotImplementedError

        with pytest.raises(
            WorkflowShapeError, match="tuple\\[ConversationPublicationState, ConversationPublicationRequest\\]"
        ):
            update(wrong, state=PUBLICATION_STATE, emits=(port("out", ConversationPublicationRequest),))

    def test_same_type_state_ports_make_type_resolution_ambiguous(self) -> None:
        shadow = state_port("review_shadow", ReviewState)
        broken = fragment(
            "ambiguous",
            entry=ENTRY,
            reads=(AUTHORITY,),
            states=(REVIEW_STATE, shadow, HUMAN_STATE, PUBLICATION_STATE),
            body=(
                activity_step_for_test(),
                scatter(
                    unpack_intents,
                    lane(
                        INTENT_RESULT,
                        where=on(Intent).kind == "acknowledge",
                        then=choice(
                            case(when=CURRENT, then=fold(accept_finding_intent, state=REVIEW_STATE)),
                            otherwise=WAIT,
                        ),
                    ),
                    rest=DROP,
                ),
            ),
        )
        with pytest.raises(LoweringError, match="types never identify places"):
            compile_fragment(broken)

    def test_predicate_over_an_undeclared_port_type_is_refused(self) -> None:
        broken = fragment(
            "missing-port",
            entry=ENTRY,
            reads=(),  # no Authority port, but CURRENT reads Authority
            states=(REVIEW_STATE, HUMAN_STATE, PUBLICATION_STATE),
            body=(
                activity_step_for_test(),
                scatter(
                    unpack_intents,
                    lane(
                        INTENT_RESULT,
                        where=on(Intent).kind == "acknowledge",
                        then=choice(
                            case(when=CURRENT, then=fold(accept_finding_intent, state=REVIEW_STATE)),
                            otherwise=WAIT,
                        ),
                    ),
                    rest=DROP,
                ),
            ),
        )
        with pytest.raises(LoweringError, match="declares no port of that type"):
            compile_fragment(broken)

    def test_port_names_must_be_cel_addressable(self) -> None:
        with pytest.raises(WorkflowShapeError, match="bare identifier"):
            port("work.reply", ConversationPublicationRequest)


def activity_step_for_test():
    from ax11_ast import activity_step

    return activity_step(classify_conversation, out=port("intent_batch", IntentBatch))


# -- authored fragment uses ports from ax11_fragment ------------------------


class TestAuthoredSurface:
    def test_fragment_constructs_and_reuses_shared_ports(self) -> None:
        flow = conversation_intents()
        assert flow.entry is ENTRY
        assert flow.reads == (AUTHORITY,)
        assert {p.name for p in flow.states} == {
            "review_state",
            "human_state",
            "conversation_publication_state",
        }
        assert HUMAN_STATE in flow.states and REPLY_BASIS.color == "Intent"
