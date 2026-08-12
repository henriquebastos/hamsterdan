"""AX15 focused tests — the recovery concern against production wiring.

The oracle extends AX13's production-style oracle with the verbatim
`recover_publication` loop and `reject_recovery` retire from
`topology.py` (~1520–1569): same `_typed_guard` closures over the shared
`_recoverable_publication`, same read-everything wiring, same
`_recover_publication` binding handler. The authored net is the full
triple composition (AX11 base + AX14 change concern + recovery concern).
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from ax11_compiler import compile_fragment
from ax11_fragment import _intent, conversation_intents
from ax11_predicates import (
    PredicateEvaluationError,
    PredicateTypeError,
    holds,
    on,
    validate_null_safety,
)
from ax13_fragment import conversation_intents_with_change
from ax14_compose import ComposedNet, compose
from ax14_fragments import change_concern
from ax15_recovery import composed_full, recovery_concern
from petrus.engine import Engine
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.dsl import NetSpec, arc, petri_handler
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from test_ax11_fragment import (
    AUTHORITY_VALUE,
    REVIEW_SEED,
    SNAPSHOT,
    classification_request,
    classify_conversation,
    dispatch,
    drive_bounded,
    intent,
    place_data,
)
from test_ax13_fragment import AX13_PLACES

from hamsterdan.contracts.readiness import (
    Authority,
    ChangeRequest,
    ConversationClassificationRequest,
    ConversationPublicationRequest,
    ConversationPublicationState,
    DashboardPublicationRequest,
    DashboardPublicationState,
    HumanState,
    Intent,
    IntentBatch,
    MutationState,
    ReadinessCommand,
    ReadinessPublicationState,
    ReviewState,
)
from hamsterdan.readiness.net.topology import (
    _accept_intent,
    _authorize_change,
    _authorize_reply,
    _current,
    _guard,
    _mutation,
    _recover_publication,
    _recoverable_publication,
    _replyable,
    _typed_guard,
    _unpack_intents,
    _valid_reply,
)

AX15_PLACES = {
    **AX13_PLACES,
    "dashboard_publication_state": "dashboard_publication_state",
    "readiness_publication_state": "readiness_publication_state",
    "work_dashboard": "work.dashboard",
    "command_readiness": "command.readiness",
}


# -- the production oracle: AX13's oracle plus the verbatim recovery wiring --


def production_oracle():
    net = NetSpec("conversation-intents-full-production")
    p, t = net.p, net.t
    work, execute, retire_scope, command = net.s.work, net.s.execute, net.s.retire, net.s.command
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
        guards=_typed_guard((Authority, ConversationPublicationState, Intent), _replyable),
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
    authorize_change = t.authorize_change(
        handler=petri_handler(_authorize_change),
        guards=_typed_guard((Authority, MutationState, Intent), _mutation),
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
    # -- verbatim recovery wiring (topology.py ~1520–1569) --------------------
    recovery_owners = (
        ("conversation", p.conversation_publication_state, work.p.conversation_reply),
        ("dashboard", p.dashboard_publication_state(DashboardPublicationState), work.p.dashboard),
        ("readiness", p.readiness_publication_state(ReadinessPublicationState), command.p.readiness),
    )
    work.p.dashboard(DashboardPublicationRequest)
    command.p.readiness(ReadinessCommand)
    recovery = net.s.recover_publication
    guard_types = (
        Authority,
        ConversationPublicationState,
        DashboardPublicationState,
        ReadinessPublicationState,
        Intent,
    )
    for target, owner, exact_work in recovery_owners:
        recover_publication = getattr(recovery.t, target)(
            handler=petri_handler(_recover_publication),
            guards=_typed_guard(
                guard_types,
                lambda authority, conversation, dashboard, readiness, value, selected=target: (
                    value.arguments.get("target") == selected
                    and _recoverable_publication(authority, conversation, dashboard, readiness, value)
                ),
            ),
        )
        p.authority >> arc.read() >> recover_publication
        for concern in (p.conversation_publication_state, p.dashboard_publication_state, p.readiness_publication_state):
            if concern is not owner:
                concern >> arc.read() >> recover_publication
        (owner, p.recovery_basis) >> recover_publication >> (owner, exact_work)
    reject_recovery = retire_scope.t.recovery_basis(
        guards=_typed_guard(
            guard_types,
            lambda authority, conversation, dashboard, readiness, value: (
                not _recoverable_publication(authority, conversation, dashboard, readiness, value)
            ),
        )
    )
    for place in (
        p.authority,
        p.conversation_publication_state,
        p.dashboard_publication_state,
        p.readiness_publication_state,
    ):
        place >> arc.read() >> reject_recovery
    p.recovery_basis >> reject_recovery
    return net.build(), abs(classify)


# -- seeds --------------------------------------------------------------------


def parked_conversation(operation: str = "op-r", *, epoch: int = 3) -> ConversationPublicationState:
    return ConversationPublicationState(
        conversation_capability_blocking=True,
        conversation_operation=operation,
        conversation_recovery=ConversationPublicationRequest(
            epoch=epoch,
            head="h3",
            operation=operation,
            base_head="b1",
            policy_digest="pd",
            intent=Intent(**intent("reply")),
        ),
    )


def parked_dashboard(operation: str = "op-d") -> DashboardPublicationState:
    return DashboardPublicationState(
        dashboard_capability_blocking=True,
        dashboard_operation=operation,
        dashboard_recovery=DashboardPublicationRequest(
            epoch=3, head="h3", operation=operation, base_head="b1", policy_digest="pd", control=SNAPSHOT
        ),
    )


def parked_readiness(operation: str = "op-n") -> ReadinessPublicationState:
    return ReadinessPublicationState(
        readiness_capability_blocking=True,
        readiness_operation=operation,
        readiness_recovery=ReadinessCommand(
            epoch=3, head="h3", operation=operation, base_head="b1", policy_digest="pd"
        ),
    )


def recover(target: str, operation: str) -> dict:
    return intent("recover_publication", arguments={"target": target, "operation": operation})


def seed_marking(places: dict[str, str], request, *, cp=None, dp=None, rp=None) -> Marking:
    seeds = {
        "authority": AUTHORITY_VALUE,
        "review_state": REVIEW_SEED,
        "human_state": HumanState(),
        "conversation_publication_state": cp or ConversationPublicationState(),
        "dashboard_publication_state": dp or DashboardPublicationState(),
        "readiness_publication_state": rp or ReadinessPublicationState(),
        "mutation_state": MutationState(),
        "work_conversation": request,
    }
    return Marking(
        {NetPath(places[name]): (Token(type(value).__name__, value.dump()),) for name, value in seeds.items()}
    )


def run_composed(request, *, cp=None, dp=None, rp=None, history=None, instance="ax15") -> tuple[Engine, ComposedNet]:
    composed = composed_full()
    engine = Engine.create(
        composed.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=dispatch(),
        marking=seed_marking({name: str(path) for name, path in composed.places.items()}, request, cp=cp, dp=dp, rp=rp),
        handlers=dict(composed.handlers),
        guards=dict(composed.built.guards),
        activities=composed.activities,
    )
    drive_bounded(engine)
    return engine, composed


def run_production(request, *, cp=None, dp=None, rp=None) -> Engine:
    built, classify = production_oracle()
    handlers = dict(built.handlers)
    uri = built.net.handler_uri(classify)
    assert uri is not None
    handlers[uri] = DerivedActivityHandler(built.net, classify, classify_conversation)
    engine = Engine.create(
        built.net,
        "ax15-production",
        history=InMemoryHistoryStore(),
        dispatch=dispatch(),
        marking=seed_marking(AX15_PLACES, request, cp=cp, dp=dp, rp=rp),
        handlers=handlers,
        guards=dict(built.guards),
        activities=(classify_conversation.declaration,),
    )
    drive_bounded(engine)
    return engine


def assert_matches_production(composed_engine: Engine, composed: ComposedNet, production: Engine) -> None:
    for logical, production_path in AX15_PLACES.items():
        assert place_data(composed_engine, str(composed.places[logical])) == place_data(production, production_path), (
            f"place {logical!r} diverged from production"
        )


# -- behavior parity: the hardest guard, per target ---------------------------


class TestRecoveryParity:
    def test_conversation_recovery_reissues_the_parked_request(self) -> None:
        request = classification_request([recover("conversation", "op-r")])
        engine, composed = run_composed(request, cp=parked_conversation("op-r"))
        assert_matches_production(engine, composed, run_production(request, cp=parked_conversation("op-r")))
        [work] = place_data(engine, str(composed.places["work_conversation_reply"]))
        assert work["operation"] == "op-r"
        [state] = place_data(engine, str(composed.places["conversation_publication_state"]))
        assert state["conversation_capability_blocking"] is False
        assert place_data(engine, str(composed.places["recovery_basis"])) == []

    def test_dashboard_recovery_targets_its_own_concern(self) -> None:
        request = classification_request([recover("dashboard", "op-d")])
        engine, composed = run_composed(request, dp=parked_dashboard("op-d"))
        assert_matches_production(engine, composed, run_production(request, dp=parked_dashboard("op-d")))
        [work] = place_data(engine, str(composed.places["work_dashboard"]))
        assert work["operation"] == "op-d"
        assert place_data(engine, str(composed.places["work_conversation_reply"])) == []

    def test_readiness_recovery_emits_the_command(self) -> None:
        request = classification_request([recover("readiness", "op-n")])
        engine, composed = run_composed(request, rp=parked_readiness("op-n"))
        assert_matches_production(engine, composed, run_production(request, rp=parked_readiness("op-n")))
        [command] = place_data(engine, str(composed.places["command_readiness"]))
        assert command["operation"] == "op-n"

    def test_wrong_owned_operation_is_retired(self) -> None:
        request = classification_request([recover("conversation", "other-op")])
        engine, composed = run_composed(request, cp=parked_conversation("op-r"))
        assert_matches_production(engine, composed, run_production(request, cp=parked_conversation("op-r")))
        assert place_data(engine, str(composed.places["recovery_basis"])) == []
        assert place_data(engine, str(composed.places["work_conversation_reply"])) == []
        [state] = place_data(engine, str(composed.places["conversation_publication_state"]))
        assert state["conversation_capability_blocking"] is True

    def test_missing_target_argument_is_retired_not_parked(self) -> None:
        # Exercises has() on the open map inside the generated complement.
        request = classification_request([intent("recover_publication", arguments={"operation": "op-r"})])
        engine, composed = run_composed(request, cp=parked_conversation("op-r"))
        assert_matches_production(engine, composed, run_production(request, cp=parked_conversation("op-r")))
        assert place_data(engine, str(composed.places["recovery_basis"])) == []

    def test_stale_recovery_request_is_retired(self) -> None:
        # The nested optional identity comparison decides: parked request
        # minted under epoch 2, authority at epoch 3.
        stale = parked_conversation("op-r", epoch=2)
        request = classification_request([recover("conversation", "op-r")])
        engine, composed = run_composed(request, cp=stale)
        assert_matches_production(engine, composed, run_production(request, cp=stale))
        assert place_data(engine, str(composed.places["recovery_basis"])) == []
        [state] = place_data(engine, str(composed.places["conversation_publication_state"]))
        assert state["conversation_capability_blocking"] is True

    def test_recovery_unblocks_a_parked_reply_in_one_run(self) -> None:
        # The WAIT semantics observable across the seam: the reply intent
        # parks because the conversation concern is blocked; the recovery
        # intent clears the block; the parked reply then authorizes. Both
        # producers emit into the shared work_conversation_reply place,
        # and the change concern authorizes its intent in the same run.
        request = classification_request(
            [
                intent("acknowledge", arguments={"findings": ["F1"]}),
                intent("reply", arguments={"message": "hi"}),
                {**intent("update_base"), "blocking": True},
                recover("conversation", "op-r"),
            ]
        )
        engine, composed = run_composed(request, cp=parked_conversation("op-r"))
        assert_matches_production(engine, composed, run_production(request, cp=parked_conversation("op-r")))
        emitted = place_data(engine, str(composed.places["work_conversation_reply"]))
        assert len(emitted) == 2  # the reissued recovery request AND the new reply
        [change] = place_data(engine, str(composed.places["work_change"]))
        assert change["intent"]["kind"] == "update_base"


# -- shape: the specialized predicates need fewer arcs than production --------


class TestShape:
    def test_marginal_recovery_growth(self) -> None:
        def stats(net):
            arcs = sum(len(net.inputs(t)) + len(net.outputs(t)) for t in net.transitions)
            return len(tuple(net.places)), len(tuple(net.transitions)), arcs

        base_with_change = compile_fragment(conversation_intents_with_change()).built.net
        full = composed_full().built.net
        production, _ = production_oracle()
        # Authored marginal: +4 places, +4 transitions, +23 arcs. Production
        # marginal: +4/+4/+26 — its generic 5-parameter guard forces every
        # recover transition to read all three states; the per-target
        # predicates bind only what they judge (ordered-exclusivity widening
        # included: dashboard reads cp, readiness reads cp+dp).
        assert stats(base_with_change) == (13, 8, 31)
        assert stats(full) == (17, 12, 54)
        assert stats(production.net) == (17, 12, 56)

    def test_retire_reads_match_production_reject_recovery(self) -> None:
        composed = composed_full()
        retire_inputs = {
            str(a.source): a.mode.value for a in composed.built.net.inputs(NetPath("retire_recovery_basis_otherwise"))
        }
        assert retire_inputs == {
            "authority": "read",
            "conversation_publication_state": "read",
            "dashboard_publication_state": "read",
            "readiness_publication_state": "read",
            "recovery_basis": "consume",
        }

    def test_emit_port_seam_has_two_producers(self) -> None:
        composed = composed_full()
        target = composed.places["work_conversation_reply"]
        producers = {
            str(t)
            for t in composed.built.net.transitions
            if any(a.target == target for a in composed.built.net.outputs(t))
        }
        assert producers == {"authorize_reply", "recover_conversation"}


# -- determinism and replay ----------------------------------------------------


class TestReplay:
    def test_composition_is_deterministic(self) -> None:
        from petrus.impetus.net_definition import project_net_definition, serialize_net_definition

        assert serialize_net_definition(project_net_definition(composed_full().built.net)) == (
            serialize_net_definition(project_net_definition(composed_full().built.net))
        )

    def test_replay_over_recomposed_net_reaches_same_marking(self) -> None:
        request = classification_request([recover("conversation", "op-r")])
        history = InMemoryHistoryStore()
        original, composed = run_composed(request, cp=parked_conversation("op-r"), history=history, instance="ax15-r")
        recomposed = composed_full()
        resumed = Engine.load(
            recomposed.built.net,
            "ax15-r",
            history=history,
            dispatch=dispatch(),
            handlers=dict(recomposed.handlers),
            guards=dict(recomposed.built.guards),
            activities=recomposed.activities,
        )
        for name, path in composed.places.items():
            assert place_data(resumed, str(recomposed.places[name])) == place_data(original, str(path))


# -- predicate-DSL edges the recovery guard exposed ------------------------------


class TestPredicateEdges:
    def test_nested_optional_parent_access_escapes_validation(self) -> None:
        # THE HOLE: child refs do not inherit parent optionality, so an
        # unguarded read through `conversation_recovery` (Optional) passes
        # validation — yet is undecidable when the parent is absent. The
        # recovery guard is sound only because `.present()` precedes the
        # nested access and CEL && short-circuits. Refinement recorded in
        # the experiment index: inherit parent optionality.
        naked = on(ConversationPublicationState).conversation_recovery.epoch == 3
        validate_null_safety(naked)  # passes today — should not
        with pytest.raises(PredicateEvaluationError, match="absent"):
            holds(naked, {"ConversationPublicationState": ConversationPublicationState()})

    def test_left_optional_field_is_refused_unguarded(self) -> None:
        with pytest.raises(PredicateTypeError, match="may be absent"):
            validate_null_safety(on(ConversationPublicationState).conversation_operation == "op")

    def test_right_optional_field_escapes_validation(self) -> None:
        # The asymmetry: null-safety checks only the left ref of a
        # comparison. The recovery guard sidesteps it by conjoining
        # `owned.present()` first; the checker should cover both sides.
        asymmetric = on(Authority).head == on(ConversationPublicationState).conversation_operation
        validate_null_safety(asymmetric)  # passes today — should not

    def test_guard_orders_presence_before_nested_access(self) -> None:
        composed = composed_full()
        guard = composed.source_map[composed.generated_by["recover_conversation"]].guard_cel
        assert guard is not None
        presence = guard.index("!(conversation_publication_state[0].data.conversation_recovery == null)")
        nested = guard.index("conversation_publication_state[0].data.conversation_recovery.operation")
        assert presence < nested


# -- the celpy null dialect: why presence renders as !(x == null) ------------


class TestCelNullDialect:
    """AX15-discovered runtime evidence, proven on Petrus's own guard path.

    celpy's frozen dialect defines `== null` for every value shape but
    `!= null` only for scalars: a present struct-typed field raises
    `CELEvalError`, which enabledness reads as not-satisfied — the binding
    parks *silently*. Earlier compile-only probes could not see this; the
    recovery guard is the exploration's first *executed* null check over
    a struct-typed optional field.
    """

    _PLACE = NetPath("conversation_publication_state")
    _SCOPE: ClassVar[dict[str, str]] = {"ConversationPublicationState": "conversation_publication_state[0].data"}

    def _evaluate(self, expression: str, state: ConversationPublicationState) -> bool:
        from petrus.impetus.binding.cel import compile_guard
        from petrus.impetus.petrinet import Binding, Cel

        guard = compile_guard(Cel(expression), NetPath("probe"), (self._PLACE,))
        binding = Binding(
            NetPath("probe"),
            consumed=(),
            read=((self._PLACE, (Token("ConversationPublicationState", state.dump()),)),),
        )
        return guard(binding)

    def test_struct_presence_evaluates_true_when_parked(self) -> None:
        rendered = on(ConversationPublicationState).conversation_recovery.present().cel(self._SCOPE)
        assert rendered == "!(conversation_publication_state[0].data.conversation_recovery == null)"
        assert self._evaluate(rendered, parked_conversation()) is True

    def test_struct_absence_evaluates_false_not_error(self) -> None:
        rendered = on(ConversationPublicationState).conversation_recovery.present().cel(self._SCOPE)
        assert self._evaluate(rendered, ConversationPublicationState()) is False

    def test_the_rejected_spelling_raises_on_present_structs(self) -> None:
        import celpy

        with pytest.raises(celpy.CELEvalError):
            self._evaluate(
                "conversation_publication_state[0].data.conversation_recovery != null",
                parked_conversation(),
            )

    def test_map_key_presence_still_distinguishes_missing_keys(self) -> None:
        from petrus.impetus.binding.cel import compile_guard
        from petrus.impetus.petrinet import Binding, Cel

        place = NetPath("recovery_basis")
        rendered = _intent.arguments["target"].present().cel({"Intent": "recovery_basis[0].data"})
        guard = compile_guard(Cel(rendered), NetPath("probe"), (place,))

        def probe(arguments: dict) -> bool:
            data = intent("recover_publication", arguments=arguments)
            return guard(Binding(NetPath("probe"), consumed=((place, (Token("Intent", data),)),)))

        assert probe({"target": "conversation", "operation": "op-r"}) is True
        assert probe({"operation": "op-r"}) is False


# -- traceability -----------------------------------------------------------------


class TestTraceability:
    def test_recovery_transitions_map_to_their_authoring_site(self) -> None:
        composed = composed_full()
        for name in ("recover_conversation", "recover_dashboard", "recover_readiness"):
            address = composed.generated_by[name]
            assert address.startswith("/recovery-intents")
            origin = composed.source_map[address].origin
            assert origin is not None and "ax15_recovery.py" in origin

    def test_three_way_composition_leaves_all_sources_untouched(self) -> None:
        base, change, recovery = conversation_intents(), change_concern(), recovery_concern()
        compose("conversation-intents-full", base, change, recovery)
        assert base == conversation_intents()
        assert change == change_concern()
        assert recovery == recovery_concern()
