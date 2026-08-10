"""Executable contract tests for the replacement PR-readiness topology."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from petrus.engine import Engine, SimulatedClock
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import activity
from petrus.motus.dispatch import InlineDispatch, InMemoryDispatch
from pydantic import ValidationError

from hamsterdan.contracts.readiness import (
    ActionsDiscoveryRequest,
    ActionsObservation,
    ActionsRerunRequest,
    ActionsState,
    Admission,
    Authority,
    ChangeRequest,
    ChangeResult,
    ConversationClassificationRequest,
    ConversationObservation,
    ConversationPublicationRequest,
    ConversationPublicationResult,
    DashboardPublicationRequest,
    DashboardPublicationResult,
    FindingPublicationRequest,
    FindingPublicationResult,
    HumanObservation,
    HumanState,
    Intent,
    IntentBatch,
    Lifecycle,
    MutationState,
    PublicationState,
    ReadinessCommand,
    ReadinessPublicationResult,
    ReadinessSnapshot,
    Reminder,
    ReminderPublicationRequest,
    ReminderPublicationResult,
    RepairRequest,
    RepairResult,
    ReviewRequest,
    ReviewResult,
    ReviewState,
    Seed,
    dashboard_projection_digest,
    project_readiness,
    workflow_gates_ready,
    workflow_wait,
)
from hamsterdan.host.payloads import PydanticPayloadConverter
from hamsterdan.readiness.net.topology import (
    ACTIVITY_TRANSITIONS,
    DASHBOARD_FORMAT,
    MAX_REVIEW_ATTEMPTS,
    _basis_done,
    _effect_matches,
    _guard,
    _hydrate,
    _mutation,
    _reminder_due,
    _repairable,
    _request_dashboard,
    _retry_review,
    _retryable_review,
    _unpack_intents,
    build_net,
    fold_actions,
    fold_effect,
    fold_intent,
    fold_review,
    ready,
)

REQUEST_TYPES = {
    "review": ReviewRequest,
    "actions_discovery": ActionsDiscoveryRequest,
    "actions_rerun": ActionsRerunRequest,
    "conversation": ConversationPublicationRequest,
    "change": ChangeRequest,
    "repair": RepairRequest,
    "finding": FindingPublicationRequest,
    "dashboard": DashboardPublicationRequest,
    "reminder": ReminderPublicationRequest,
}
RESULT_TYPES = {
    "conversation": ConversationPublicationResult,
    "change": ChangeResult,
    "repair": RepairResult,
    "finding": FindingPublicationResult,
    "dashboard": DashboardPublicationResult,
    "reminder": ReminderPublicationResult,
    "readiness": ReadinessPublicationResult,
}


def request(kind, epoch, head, operation="", sequence=0, payload=None):
    values = dict(payload or {})
    values.setdefault("base_head", "base")
    values.setdefault("policy_digest", "policy")
    if kind == "conversation":
        values.setdefault("intent", Intent(epoch, head, "reply", "digest", True, False))
    return REQUEST_TYPES[kind](epoch=epoch, head=head, operation=operation, **values)


def effect_result(kind, epoch, head, ok, *args, **kwargs):
    return RESULT_TYPES[kind](epoch, head, ok, *args, **kwargs)


def token(value) -> Token:
    return Token(type(value).__name__, value.dump())


@activity(name="review", converter=PydanticPayloadConverter())
def review(work: ReviewRequest) -> ReviewResult:
    return ReviewResult(work.epoch, work.head, "clear", [], [], work.operation)


@activity(name="actions_discovery", converter=PydanticPayloadConverter())
def actions_discovery(work: ActionsDiscoveryRequest) -> ActionsObservation:
    return action_result(work, "run", 1, "success")


@activity(name="actions_rerun", converter=PydanticPayloadConverter())
def actions_rerun(work: ActionsRerunRequest) -> ActionsObservation:
    return action_result(work, "rerun", 2, "success")


@activity(name="conversation", converter=PydanticPayloadConverter())
def conversation(work: ConversationClassificationRequest) -> IntentBatch:
    intent = Intent(epoch=work.epoch, head=work.head, kind="reply", digest="digest", authorized=True, blocking=False)
    return IntentBatch(work.epoch, work.head, [intent])


def _effect(name: str, request_type, result_type):
    def perform(work):
        extra = {"provisional_head": "next"} if name in {"change", "repair"} else {}
        return effect_result(
            name.removesuffix("_publish"),
            work.epoch,
            work.head,
            True,
            operation=work.operation,
            **extra,
        )

    perform.__annotations__ = {"work": request_type, "return": result_type}
    return activity(name=name, converter=PydanticPayloadConverter())(perform)


repair = _effect("repair", RepairRequest, RepairResult)
change = _effect("change", ChangeRequest, ChangeResult)
conversation_publish = _effect("conversation_publish", ConversationPublicationRequest, ConversationPublicationResult)
finding_publish = _effect("finding_publish", FindingPublicationRequest, FindingPublicationResult)
dashboard_publish = _effect("dashboard_publish", DashboardPublicationRequest, DashboardPublicationResult)
reminder_publish = _effect("reminder_publish", ReminderPublicationRequest, ReminderPublicationResult)


@activity(name="readiness_publish", converter=PydanticPayloadConverter())
def readiness_publish(command: ReadinessCommand) -> ReadinessPublicationResult:
    return effect_result("readiness", command.epoch, command.head, True, operation=command.operation)


ACTIVITIES = (
    review,
    actions_discovery,
    actions_rerun,
    conversation,
    conversation_publish,
    repair,
    change,
    finding_publish,
    dashboard_publish,
    reminder_publish,
    readiness_publish,
)


class ManualClock:
    def __init__(self) -> None:
        self.instant = 0.0

    def now(self) -> float:
        return self.instant

    def observe(self, instant: float) -> float | None:
        return self.instant if self.instant >= instant else None


def engine() -> Engine:
    built = build_net(10**30)
    definitions = {item.declaration.name: item for item in ACTIVITIES}
    handlers = dict(built.handlers)
    for path in ACTIVITY_TRANSITIONS:
        name = path.removeprefix("execute.")
        handlers[name] = DerivedActivityHandler(built.net, NetPath(path), definitions[name])
    return Engine.create(
        built.net,
        "pr-7",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch(definitions),
        marking=Marking({NetPath("seed"): (token(Seed("repo", 7)),)}),
        handlers=handlers,
        guards=built.guards,
        activities=tuple(item.declaration for item in ACTIVITIES),
    )


def asynchronous_engine(
    *,
    reminder_delay: int = 10,
    definitions=ACTIVITIES,
    clock=None,
) -> tuple[Engine, InMemoryDispatch]:
    built = build_net(reminder_delay)
    dispatch = InMemoryDispatch()
    by_name = {item.declaration.name: item for item in definitions}
    handlers = dict(built.handlers)
    for path in ACTIVITY_TRANSITIONS:
        name = path.removeprefix("execute.")
        handlers[name] = DerivedActivityHandler(built.net, NetPath(path), by_name[name])
    return (
        Engine.create(
            built.net,
            "pr-7-async",
            history=InMemoryHistoryStore(),
            dispatch=dispatch,
            marking=Marking({NetPath("seed"): (token(Seed("repo", 7)),)}),
            handlers=handlers,
            guards=built.guards,
            activities=tuple(item.declaration for item in definitions),
            clock=clock or SimulatedClock(),
        ),
        dispatch,
    )


def drive_bounded(subject: Engine, limit: int = 200) -> None:
    """Drive until the engine asks its host to wait, with a livelock bound."""
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def pending(dispatch: InMemoryDispatch, activity_name: str) -> tuple[int, object]:
    matches = [
        (occurrence, invocation)
        for occurrence, invocation in dispatch.pending.items()
        if invocation.activity == activity_name
    ]
    assert len(matches) == 1, (activity_name, dispatch.pending)
    return matches[0]


def pending_all(dispatch: InMemoryDispatch, activity_name: str) -> list[tuple[int, object]]:
    return [
        (occurrence, invocation)
        for occurrence, invocation in dispatch.pending.items()
        if invocation.activity == activity_name
    ]


def complete(dispatch: InMemoryDispatch, activity_name: str, result) -> int:
    occurrence, _ = pending(dispatch, activity_name)
    dispatch.complete(occurrence, result.dump())
    return occurrence


def work_input(invocation):
    input_type = ACTIVITY_TRANSITIONS[f"execute.{invocation.activity}"][0]
    payload = invocation.input.get("work", invocation.input.get("command"))
    return PydanticPayloadConverter().decode(payload, input_type)


def action_result(
    work,
    run_id: str,
    attempt: int,
    conclusion: str,
    fingerprint: str = "",
    *,
    observation: str = "",
) -> ActionsObservation:
    return ActionsObservation(
        work.epoch,
        work.head,
        run_id,
        attempt,
        conclusion,
        fingerprint,
        observation=observation,
        operation=work.operation,
        base_head=str(work.base_head),
        policy_digest=str(work.policy_digest),
    )


def observed_actions(
    subject: Engine,
    run_id: str,
    attempt: int,
    conclusion: str,
    fingerprint: str = "",
    *,
    observation: str,
) -> ActionsObservation:
    control = snapshot(subject).dump()
    return ActionsObservation(
        control["epoch"],
        control["head"],
        run_id,
        attempt,
        conclusion,
        fingerprint,
        observation=observation,
        operation=control["actions_operation"],
        base_head=control["base_head"],
        policy_digest=control["policy_digest"],
    )


def drive_until_activity(subject: Engine, dispatch: InMemoryDispatch, activity_name: str) -> tuple[int, object]:
    """Reach one requested Activity, satisfying unrelated serial requests."""
    for _ in range(100):
        matches = pending_all(dispatch, activity_name)
        if matches:
            assert len(matches) == 1
            return matches[0]
        drive_bounded(subject)
        matches = pending_all(dispatch, activity_name)
        if matches:
            assert len(matches) == 1
            return matches[0]
        for occurrence, invocation in list(dispatch.pending.items()):
            work = work_input(invocation)
            if invocation.activity == "review":
                result = ReviewResult(work.epoch, work.head, "clear", [], [], work.operation)
            elif invocation.activity.startswith("actions_"):
                result = action_result(work, "run", 1, "success")
            elif invocation.activity == "conversation":
                result = IntentBatch(work.epoch, work.head, [])
            else:
                kind = invocation.activity.removesuffix("_publish")
                result = effect_result(kind, work.epoch, work.head, True, operation=work.operation)
            dispatch.complete(occurrence, result.dump())
    raise AssertionError(f"{activity_name} was not requested")


def drain(subject: Engine) -> None:
    for _ in range(200):
        outcome = subject.advance()
        if not outcome.ready:
            return
        pending = (
            "work.review",
            "work.actions_discovery",
            "work.actions_rerun",
            "work.conversation",
            "work.repair",
            "work.change",
            "work.finding",
            "work.dashboard",
            "work.reminder",
            "command.readiness",
            "review_result",
            "actions_result",
            "intent_result",
            "effect_result",
        )
        requested = {record.occurrence for record in subject.records if isinstance(record, ActivityRequested)}
        completed = {record.occurrence for record in subject.records if isinstance(record, ActivityCompleted)}
        retired = not values(subject, "actions_basis") and len(values(subject, "reminder.timer")) <= 1
        if (
            not outcome.firings
            and not any(values(subject, place) for place in pending)
            and requested <= completed
            and retired
        ):
            return
    raise AssertionError("net did not quiesce")


def deliver(subject: Engine, source: str, value, identity: str) -> None:
    subject.deliver(source, token(value), identity=identity)
    drain(subject)


def values(subject: Engine, place: str) -> list[dict]:
    return [item.data for item in subject.marking.place(NetPath(place))]


def state(subject: Engine, path: str, kind):
    """Hydrate the singleton token owned by one active concern."""
    found = values(subject, path)
    assert len(found) == 1, (path, found)
    return kind(**found[0])


def snapshot(subject: Engine) -> ReadinessSnapshot:
    """Join the six independently owned active concern tokens."""
    return project_readiness(
        state(subject, "authority", Authority),
        state(subject, "actions_state", ActionsState),
        state(subject, "review_state", ReviewState),
        state(subject, "human_state", HumanState),
        state(subject, "mutation_state", MutationState),
        state(subject, "publication_state", PublicationState),
    )


ACTIVE_CONCERNS = {
    "authority": Authority,
    "actions_state": ActionsState,
    "review_state": ReviewState,
    "human_state": HumanState,
    "mutation_state": MutationState,
    "publication_state": PublicationState,
}


def assert_active_cohort(subject: Engine) -> None:
    assert {path: len(values(subject, path)) for path in ACTIVE_CONCERNS} == dict.fromkeys(ACTIVE_CONCERNS, 1)


def assert_no_active_cohort(subject: Engine) -> None:
    assert not any(values(subject, path) for path in ACTIVE_CONCERNS)


def concern_state(**overrides):
    """Build six concern values from concise legacy-shaped test overrides."""
    dashboard_current = overrides.pop("dashboard_current", False)
    base = ReadinessSnapshot("repo", 7, 1, "h", "base", True, True).dump() | overrides
    concerns = tuple(
        kind(**{name: base[name] for name in kind.__dataclass_fields__})
        for kind in (Authority, ActionsState, ReviewState, HumanState, MutationState, PublicationState)
    )
    if dashboard_current:
        projection = dashboard_projection_digest(*concerns)
        concerns = (*concerns[:5], concerns[5].validated_update(dashboard_projection=projection))
    return concerns


def make_snapshot(
    repository_id="repo",
    pr_number=7,
    epoch=1,
    head="h",
    base_head="base",
    strict_base=True,
    base_current=True,
    policy_digest="",
    **overrides,
) -> ReadinessSnapshot:
    """Build a joined snapshot while keeping direct-helper setup concise."""
    return project_readiness(
        *concern_state(
            repository_id=repository_id,
            pr_number=pr_number,
            epoch=epoch,
            head=head,
            base_head=base_head,
            strict_base=strict_base,
            base_current=base_current,
            policy_digest=policy_digest,
            **overrides,
        )
    )


def admit(subject: Engine, head: str, identity: str) -> None:
    deliver(subject, "verified_admission", Admission("repo", 7, head, "base", True), identity)


def requests(subject: Engine) -> list[ActivityRequested]:
    return [record for record in subject.records if isinstance(record, ActivityRequested)]


def test_every_obligation_is_a_real_typed_activity_and_readiness_is_end_to_end() -> None:
    subject = engine()
    admit(subject, "h1", "admit")
    assert_active_cohort(subject)
    deliver(
        subject,
        "human_observation",
        HumanObservation(1, "h1", True, True, False, 0, True, True, True, False, True),
        "human",
    )
    names = [record.activity for record in requests(subject)]
    assert {"review", "actions_discovery", "dashboard_publish", "readiness_publish"} <= set(names)
    control = snapshot(subject).dump()
    assert control["announced"] is True
    assert not values(subject, "command.readiness")
    assert all(
        NetPath(path) in build_net(2).net.places
        for path in (
            "review_result",
            "actions_result",
            "intent_result",
            "conversation_result",
            "change_result",
            "repair_result",
            "finding_result",
            "dashboard_result",
            "reminder_result",
            "readiness_result",
        )
    )


def test_same_head_is_duplicate_distinct_head_supersedes_and_counts_stay_bounded() -> None:
    subject = engine()
    admit(subject, "h0", "a0")
    deliver(
        subject,
        "human_observation",
        HumanObservation(1, "h0", True, True, False, 0, False, False, False, False, True),
        "pause",
    )
    admit(subject, "h0", "duplicate")
    assert snapshot(subject).dump()["epoch"] == 1
    for epoch in range(1, 11):
        admit(subject, f"h{epoch}", f"a{epoch}")
        assert_active_cohort(subject)
    assert snapshot(subject).dump()["epoch"] == 11
    assert all(len(tokens) <= 1 for _, tokens in subject.marking)


def test_same_head_reconcile_retries_unable_review_twice_then_waits() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="admit")
    operations = []

    for attempt in range(1, MAX_REVIEW_ATTEMPTS + 1):
        _, invocation = drive_until_activity(subject, dispatch, "review")
        work = work_input(invocation)
        operations.append(work.operation)
        complete(dispatch, "review", ReviewResult(1, "h1", "unable", [], [], work.operation))
        drive_bounded(subject)
        control = snapshot(subject).dump()
        assert (control["review"], control["review_attempts"]) == ("unable", attempt)
        if attempt < MAX_REVIEW_ATTEMPTS:
            subject.deliver(
                "verified_admission",
                token(Admission("repo", 7, "h1", "base", True)),
                identity=f"reconcile-{attempt}",
            )
            drive_bounded(subject)

    assert len(set(operations)) == MAX_REVIEW_ATTEMPTS
    subject.deliver(
        "verified_admission",
        token(Admission("repo", 7, "h1", "base", True)),
        identity="reconcile-at-cap",
    )
    drive_bounded(subject)
    assert not pending_all(dispatch, "review")
    control = snapshot(subject).dump()
    assert control["review_attempts"] == MAX_REVIEW_ATTEMPTS
    assert control["wait"] == "coordinating review capability"


def test_legacy_unable_review_without_attempt_count_resumes_at_attempt_two() -> None:
    authority, _, review_state, _, _, publication = concern_state(head="h1", review="unable")
    admission = Admission("repo", 7, "h1", "base", True)

    assert _retryable_review(authority, review_state, admission)
    outputs = (
        SimpleNamespace(target="authority", color="Authority"),
        SimpleNamespace(target="review_state", color="ReviewState"),
        SimpleNamespace(target="publication_state", color="PublicationState"),
        SimpleNamespace(target="work.review", color="ReviewRequest"),
    )
    binding = SimpleNamespace(
        read=(),
        consumed=(("inputs", tuple(map(token, (authority, review_state, publication, admission)))),),
    )
    routed = _retry_review(binding, outputs)

    assert routed[outputs[1].target][0].data["review_attempts"] == 2
    assert routed[outputs[3].target][0].data["sequence"] == 2


def test_review_retry_atomically_refreshes_admission_authority() -> None:
    authority, _, review_state, _, _, publication = concern_state(
        head="h1",
        base_current=False,
        review="unable",
        review_attempts=1,
    )
    admission = Admission("repo", 7, "h1", "base", True, base_current=True)
    outputs = (
        SimpleNamespace(target="authority", color="Authority"),
        SimpleNamespace(target="review_state", color="ReviewState"),
        SimpleNamespace(target="publication_state", color="PublicationState"),
        SimpleNamespace(target="work.review", color="ReviewRequest"),
    )
    binding = SimpleNamespace(
        read=(),
        consumed=(("inputs", tuple(map(token, (authority, review_state, publication, admission)))),),
    )

    routed = _retry_review(binding, outputs)

    changed = routed[outputs[0].target][0].data
    changed_review = routed[outputs[1].target][0].data
    work = routed[outputs[3].target][0].data
    assert changed["base_current"] is True
    assert changed_review["review_attempts"] == 2
    assert work["base_current"] is True
    assert len(routed[outputs[3].target]) == 1


def test_same_head_reconcile_does_not_retry_clear_review_and_new_head_resets_attempts() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="admit")
    _, invocation = drive_until_activity(subject, dispatch, "review")
    work = work_input(invocation)
    complete(dispatch, "review", ReviewResult(1, "h1", "clear", [], [], work.operation))
    drive_bounded(subject)
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="same-head")
    drive_bounded(subject)
    assert not pending_all(dispatch, "review")
    assert snapshot(subject).dump()["review_attempts"] == 1

    subject.deliver("verified_admission", token(Admission("repo", 7, "h2", "base", True)), identity="new-head")
    _, invocation = drive_until_activity(subject, dispatch, "review")
    new_work = work_input(invocation)
    assert (new_work.epoch, new_work.head) == (2, "h2")
    assert snapshot(subject).dump()["review_attempts"] == 1


def test_unauthorized_conversation_and_read_only_intent_leave_no_residue() -> None:
    subject = engine()
    admit(subject, "h1", "a")
    deliver(
        subject,
        "human_observation",
        HumanObservation(1, "h1", True, True, False, 0, False, False, False, False, True),
        "pause",
    )
    deliver(
        subject,
        "conversation_observation",
        ConversationObservation(1, "h1", False, "ignore"),
        "unauthorized",
    )
    assert not values(subject, "conversation_basis") and not values(subject, "change_basis")
    deliver(
        subject,
        "conversation_observation",
        ConversationObservation(1, "h1", True, "status?"),
        "read",
    )
    assert not values(subject, "change_basis") and not values(subject, "work.change")


def test_terminal_conversation_publication_retains_one_logical_operation_without_reissue() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="admit")
    drive_bounded(subject)
    subject.deliver(
        "conversation_observation",
        token(ConversationObservation(1, "h1", True, "explain the blockers", comment_id=31)),
        identity="comment-31",
    )
    drive_bounded(subject)

    conversation_occurrence, conversation_invocation = drive_until_activity(subject, dispatch, "conversation")
    conversation_work = work_input(conversation_invocation)
    reply = Intent(
        epoch=1,
        head="h1",
        kind="reply",
        digest="status",
        authorized=True,
        blocking=False,
        arguments={"message": "Safe status"},
        base_head="base",
    )
    dispatch.complete(conversation_occurrence, IntentBatch(1, "h1", [reply]).dump())
    drive_bounded(subject)

    first_occurrence, first_invocation = drive_until_activity(subject, dispatch, "conversation_publish")
    first_work = work_input(first_invocation)
    dispatch.complete(
        first_occurrence,
        effect_result(
            "conversation",
            first_work.epoch,
            first_work.head,
            False,
            operation=first_work.operation,
            capability_available=False,
        ).dump(),
    )
    drive_bounded(subject)

    control = snapshot(subject).dump()
    assert pending_all(dispatch, "conversation_publish") == []
    assert control["conversation_requested"] is True
    assert control["conversation_operation"] == first_work.operation
    assert control["conversation_capability_blocking"] is True
    drive_bounded(subject)
    assert pending_all(dispatch, "conversation_publish") == []
    assert conversation_work.operation != first_work.operation


def test_dashboard_capability_terminal_retains_ownership_without_a_new_activity() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="admit")
    drive_bounded(subject)
    occurrence, invocation = drive_until_activity(subject, dispatch, "dashboard_publish")
    first_work = work_input(invocation)

    dispatch.complete(
        occurrence,
        effect_result(
            "dashboard",
            first_work.epoch,
            first_work.head,
            False,
            operation=first_work.operation,
            capability_available=False,
        ).dump(),
    )
    drive_bounded(subject)

    assert snapshot(subject).dashboard_capability_blocking is True
    assert snapshot(subject).dashboard_requested is True
    assert snapshot(subject).dashboard_operation == first_work.operation
    assert pending_all(dispatch, "dashboard_publish") == []
    drive_bounded(subject)
    assert pending_all(dispatch, "dashboard_publish") == []


def test_readiness_capability_terminal_retains_ownership_without_a_new_activity() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="admit")
    drive_bounded(subject)
    subject.deliver(
        "human_observation",
        token(HumanObservation(1, "h1", True, True, False, 0, False, False, True, False, True)),
        identity="approved",
    )
    drive_bounded(subject)
    occurrence, invocation = drive_until_activity(subject, dispatch, "readiness_publish")
    first_command = work_input(invocation)

    dispatch.complete(
        occurrence,
        effect_result(
            "readiness",
            first_command.epoch,
            first_command.head,
            False,
            operation=first_command.operation,
            capability_available=False,
        ).dump(),
    )
    drive_bounded(subject)

    assert snapshot(subject).readiness_capability_blocking is True
    assert snapshot(subject).readiness_requested is True
    assert snapshot(subject).readiness_operation == first_command.operation
    assert pending_all(dispatch, "readiness_publish") == []
    drive_bounded(subject)
    assert pending_all(dispatch, "readiness_publish") == []


def test_conversation_publication_terminal_exhaustion_latches_original_operation() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="admit")
    drive_bounded(subject)
    subject.deliver(
        "conversation_observation",
        token(ConversationObservation(1, "h1", True, "explain the blockers", comment_id=32)),
        identity="comment-32",
    )
    drive_bounded(subject)
    conversation_occurrence, _ = drive_until_activity(subject, dispatch, "conversation")
    reply = Intent(
        epoch=1,
        head="h1",
        kind="reply",
        digest="status",
        authorized=True,
        blocking=False,
        arguments={"message": "Safe status"},
        base_head="base",
    )
    dispatch.complete(conversation_occurrence, IntentBatch(1, "h1", [reply]).dump())
    drive_bounded(subject)

    occurrence, invocation = drive_until_activity(subject, dispatch, "conversation_publish")
    first_work = work_input(invocation)
    dispatch.complete(
        occurrence,
        effect_result(
            "conversation",
            first_work.epoch,
            first_work.head,
            False,
            operation=first_work.operation,
            capability_available=False,
        ).dump(),
    )
    drive_bounded(subject)

    control = snapshot(subject).dump()
    assert pending_all(dispatch, "conversation_publish") == []
    assert control["conversation_requested"] is True
    assert control["conversation_capability_blocking"] is True
    assert control["conversation_operation"] == first_work.operation
    assert workflow_gates_ready(ReadinessSnapshot(**control)) is False
    otherwise_ready = make_snapshot(
        "repo",
        7,
        1,
        "h1",
        "base",
        True,
        True,
        actions="green",
        review="clear",
        findings_published=True,
        human_approved=True,
        mergeable=True,
        conversation_capability_blocking=True,
    )
    assert workflow_wait(otherwise_ready) == "conversation reply capability"
    assert workflow_gates_ready(otherwise_ready) is False


def test_draft_resumes_new_epoch_and_terminal_absorbs_late_facts() -> None:
    subject = engine()
    admit(subject, "h1", "a")
    deliver(subject, "lifecycle_observation", Lifecycle("draft", "h1"), "draft")
    assert_no_active_cohort(subject)
    assert values(subject, "dormant")[0]["last_epoch"] == 1
    admit(subject, "h1", "resume")
    assert_active_cohort(subject)
    assert snapshot(subject).dump()["epoch"] == 2
    deliver(subject, "lifecycle_observation", Lifecycle("merged", "provider-head"), "merged")
    assert_no_active_cohort(subject)
    before = len(requests(subject))
    deliver(
        subject,
        "human_observation",
        HumanObservation(2, "h1", True, True, False, 0, False, False, True, False, True),
        "late",
    )
    assert values(subject, "terminal")[0]["status"] == "success"
    assert len(requests(subject)) == before and not values(subject, "human_result")


def test_closed_is_abort_and_activity_mapping_is_exact() -> None:
    subject = engine()
    admit(subject, "h1", "a")
    deliver(subject, "lifecycle_observation", Lifecycle("closed", "anything"), "closed")
    assert_no_active_cohort(subject)
    assert values(subject, "terminal")[0]["status"] == "abort"
    assert set(ACTIVITY_TRANSITIONS) == {
        "execute.review",
        "execute.actions_discovery",
        "execute.actions_rerun",
        "execute.conversation",
        "execute.conversation_publish",
        "execute.repair",
        "execute.change",
        "execute.finding_publish",
        "execute.dashboard_publish",
        "execute.reminder_publish",
        "execute.readiness_publish",
    }


def test_human_observation_changes_only_human_and_publication_concerns() -> None:
    subject = engine()
    admit(subject, "h1", "admit")
    before = {path: state(subject, path, kind).dump() for path, kind in ACTIVE_CONCERNS.items()}

    deliver(
        subject,
        "human_observation",
        HumanObservation(1, "h1", True, False, True, 2, True, False, False, True, True),
        "human",
    )

    after = {path: state(subject, path, kind).dump() for path, kind in ACTIVE_CONCERNS.items()}
    for path in ("authority", "actions_state", "review_state", "mutation_state"):
        assert after[path] == before[path]
    assert after["human_state"] != before["human_state"]


def test_same_head_refreshes_verified_base_without_creating_a_generation() -> None:
    subject = engine()
    admit(subject, "h1", "first")
    dashboards = len([item for item in requests(subject) if item.activity == "dashboard_publish"])
    deliver(subject, "verified_admission", Admission("repo", 7, "h1", "base-2", False, False), "refresh")
    assert_active_cohort(subject)
    control = snapshot(subject).dump()
    assert (control["epoch"], control["base_head"], control["strict_base"], control["base_current"]) == (
        1,
        "base-2",
        False,
        False,
    )
    assert control["admission_relation"] == "same_head_basis_changed"
    assert len([item for item in requests(subject) if item.activity == "dashboard_publish"]) == dashboards + 1


def test_same_head_basis_refresh_retires_stale_publication_result() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="first")
    drive_bounded(subject)
    old_occurrence, old_invocation = drive_until_activity(subject, dispatch, "dashboard_publish")
    old_work = work_input(old_invocation)

    subject.deliver(
        "verified_admission",
        token(Admission("repo", 7, "h1", "base-2", False, False)),
        identity="new-basis",
    )
    drive_bounded(subject)
    dispatch.complete(
        old_occurrence,
        effect_result("dashboard", 1, "h1", True, operation=old_work.operation).dump(),
    )
    drive_bounded(subject)

    assert not values(subject, "dashboard_result")
    _, new_invocation = drive_until_activity(subject, dispatch, "dashboard_publish")
    assert work_input(new_invocation).operation != old_work.operation


def test_same_head_basis_refresh_retires_stale_conversation_result() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="first")
    drive_bounded(subject)
    subject.deliver(
        "conversation_observation",
        token(ConversationObservation(1, "h1", True, "reply", comment_id=41)),
        identity="comment-41",
    )
    occurrence, _ = drive_until_activity(subject, dispatch, "conversation")
    reply = Intent(1, "h1", "reply", "reply-41", True, False, {"message": "first"}, "base")
    dispatch.complete(occurrence, IntentBatch(1, "h1", [reply]).dump())
    drive_bounded(subject)
    old_occurrence, old_invocation = drive_until_activity(subject, dispatch, "conversation_publish")
    old_work = work_input(old_invocation)

    subject.deliver(
        "verified_admission",
        token(Admission("repo", 7, "h1", "base-2", False, False)),
        identity="new-basis",
    )
    drive_bounded(subject)
    dispatch.complete(
        old_occurrence,
        effect_result("conversation", 1, "h1", True, operation=old_work.operation).dump(),
    )
    drive_bounded(subject)

    assert not values(subject, "conversation_result")
    control = snapshot(subject)
    assert not control.conversation_requested and control.conversation_operation == ""


def test_two_reply_intents_serialize_until_first_success() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="first")
    drive_bounded(subject)
    subject.deliver(
        "conversation_observation",
        token(ConversationObservation(1, "h1", True, "two replies", comment_id=42)),
        identity="comment-42",
    )
    occurrence, _ = drive_until_activity(subject, dispatch, "conversation")
    replies = [
        Intent(1, "h1", "reply", f"reply-{number}", True, False, {"message": f"reply {number}"}, "base")
        for number in (1, 2)
    ]
    dispatch.complete(occurrence, IntentBatch(1, "h1", replies).dump())
    drive_bounded(subject)

    first_occurrence, first_invocation = drive_until_activity(subject, dispatch, "conversation_publish")
    assert len(values(subject, "reply_basis")) == 1
    assert len(pending_all(dispatch, "conversation_publish")) == 1
    first_work = work_input(first_invocation)
    dispatch.complete(
        first_occurrence,
        effect_result("conversation", 1, "h1", True, operation=first_work.operation).dump(),
    )
    drive_bounded(subject)

    _, second_invocation = drive_until_activity(subject, dispatch, "conversation_publish")
    assert work_input(second_invocation).operation != first_work.operation
    assert not values(subject, "reply_basis")


def test_conversation_blocker_latch_keeps_second_reply_queued() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="first")
    drive_bounded(subject)
    subject.deliver(
        "conversation_observation",
        token(ConversationObservation(1, "h1", True, "two replies", comment_id=43)),
        identity="comment-43",
    )
    occurrence, _ = drive_until_activity(subject, dispatch, "conversation")
    replies = [
        Intent(1, "h1", "reply", f"blocked-{number}", True, False, {"message": f"reply {number}"}, "base")
        for number in (1, 2)
    ]
    dispatch.complete(occurrence, IntentBatch(1, "h1", replies).dump())
    drive_bounded(subject)
    first_occurrence, first_invocation = drive_until_activity(subject, dispatch, "conversation_publish")
    first_work = work_input(first_invocation)
    dispatch.complete(
        first_occurrence,
        effect_result(
            "conversation", 1, "h1", False, operation=first_work.operation, capability_available=False
        ).dump(),
    )
    drive_bounded(subject)

    assert snapshot(subject).conversation_capability_blocking
    assert len(values(subject, "reply_basis")) == 1
    assert pending_all(dispatch, "conversation_publish") == []


def test_external_actions_failure_is_deduplicated_and_authorizes_one_rerun() -> None:
    subject = engine()
    admit(subject, "h1", "first")
    failure = observed_actions(subject, "external", 1, "failure", "fp", observation="obs-1")
    deliver(subject, "actions_observation", failure, "delivery-1")
    reruns = len([item for item in requests(subject) if item.activity == "actions_rerun"])
    assert reruns == 1
    deliver(subject, "actions_observation", failure, "delivery-duplicate")
    assert len([item for item in requests(subject) if item.activity == "actions_rerun"]) == reruns
    assert not values(subject, "actions_basis") and not values(subject, "actions_result")


def test_actions_basis_cannot_retire_before_a_current_observation_is_folded() -> None:
    authority, actions, _, _, mutation, _ = concern_state(actions_operation="actions")
    failure = ActionsObservation(1, "h", "run", 1, "failure", "fp", operation="actions", observation="new")
    assert _basis_done(authority, actions, mutation, failure) is False

    folded = fold_actions.implementation(actions, failure)
    assert _basis_done(authority, folded, mutation, failure) is False
    duplicate_after_rerun = replace(folded, rerun_requested=True, rerun_attempt=1)
    assert _basis_done(authority, duplicate_after_rerun, mutation, failure) is True


def test_advanced_guards_hydrate_defaults_for_replayed_concern_tokens() -> None:
    old_actions = ActionsState().dump()
    old_actions.pop("rerun_attempt")
    companion = ActionsObservation(1, "h", "run", 1, "failure").dump()
    binding = SimpleNamespace(
        consumed=(("actions", (Token("ActionsObservation", companion),)),),
        read=(("actions_state", (Token("ActionsState", old_actions),)),),
    )
    guard = _guard(lambda actions, value: actions.rerun_attempt == 0 and value.attempt == 1)
    assert guard.implementation(binding) is True


def test_irrelevant_lifecycle_fact_is_retired_while_dormant() -> None:
    subject = engine()
    admit(subject, "h1", "admit")
    deliver(subject, "lifecycle_observation", Lifecycle("draft", "h1"), "draft")
    deliver(subject, "lifecycle_observation", Lifecycle(status="draft", head="other"), "irrelevant")

    assert values(subject, "dormant")
    assert not values(subject, "lifecycle")
    assert not values(subject, "terminal")


def test_failed_repair_spends_the_automatic_budget() -> None:
    concerns = concern_state(
        actions="reproduced",
        fingerprint="fp",
        repair_in_flight=True,
        mutation_operation="repair",
    )
    failed = fold_effect(
        concerns[4],
        effect_result("repair", 1, "h", False, fingerprint="fp", lineage="repair", operation="repair"),
    )
    assert failed.repair_used is True
    assert failed.repair_fingerprint == "fp"
    assert workflow_wait(project_readiness(*concerns[:4], failed, concerns[5])) == "repair recovery"


def test_terminal_finding_lineage_stays_visible_without_republication() -> None:
    _, _, review_state, _, _, publication = concern_state(
        epoch=2,
        findings=[{"id": "finding-1", "title": "Old", "blocking": True, "comment_url": "url"}],
    )
    result = ReviewResult(
        2,
        "h",
        "clear",
        [{"id": "finding-1", "title": "Old", "blocking": True, "comment_url": "url"}],
        [{"finding_id": "finding-1", "state": "resolved", "supersedes": None}],
        "review",
    )

    folded = fold_review.implementation(review_state, result)

    assert folded.review == "clear"
    assert folded.findings == [
        {"id": "finding-1", "title": "Old", "blocking": True, "comment_url": "url", "disposition": "resolved"}
    ]
    assert publication.findings_published is False
    assert publication.finding_publication_requested is False


def test_conflict_is_the_named_wait_after_independent_review_and_actions_finish() -> None:
    control = make_snapshot("repo", 7, 1, "h", "base", True, True, conflict=True, actions="green")

    reviewed = fold_review.implementation(control, ReviewResult(1, "h", "clear", [], [], "review"))
    observed = fold_actions.implementation(
        replace(reviewed, actions="running"),
        ActionsObservation(1, "h", "run", 1, "success", observation="green"),
    )

    assert reviewed.wait == "conflict resolution"
    assert observed.wait == "conflict resolution"


def test_rerun_failure_folds_after_the_same_attempt_was_observed_in_progress() -> None:
    subject = engine()
    admit(subject, "h1", "first")
    failure = observed_actions(subject, "run", 1, "failure", "first", observation="failure-1")
    deliver(subject, "actions_observation", failure, "failure")
    running = observed_actions(subject, "run", 2, "in_progress", observation="running-2")
    deliver(subject, "actions_observation", running, "running")
    assert not [item for item in requests(subject) if item.activity == "repair"]
    reproduced = observed_actions(subject, "run", 2, "failure", "reproduced", observation="failure-2")
    deliver(subject, "actions_observation", reproduced, "reproduced")

    control = snapshot(subject).dump()
    assert (control["actions"], control["attempt"], control["rerun_attempt"]) == ("reproduced", 2, 1)
    assert len([item for item in requests(subject) if item.activity == "repair"]) == 1


def test_provisional_blocks_authorized_change_and_stale_dashboard_operation_cannot_ack() -> None:
    authority, _, _, _, mutation, _ = concern_state(head="h1", provisional=True)
    intent = Intent(epoch=1, head="h1", kind="change", digest="d", authorized=True, blocking=True, base_head="base")
    assert _mutation(authority, mutation, intent) is False
    requested = make_snapshot(
        "repo",
        7,
        1,
        "h1",
        "base",
        True,
        True,
        dashboard_requested=True,
        dashboard_operation="dashboard:1:4",
    )
    stale = effect_result("dashboard", 1, "h1", True, operation="dashboard:1:3")
    requested_authority, *_, requested_publication = concern_state(**requested.dump())
    assert _effect_matches(requested_authority, requested_publication, stale) is False

    conversation = replace(requested, conversation_requested=True, conversation_operation="conversation:1")
    assert (
        _effect_matches(
            requested_authority,
            concern_state(**conversation.dump())[5],
            effect_result("conversation", 1, "h1", True, operation="conversation:stale"),
        )
        is False
    )
    assert (
        _effect_matches(
            requested_authority,
            concern_state(**conversation.dump())[5],
            effect_result("conversation", 1, "h1", True, operation="conversation:1"),
        )
        is True
    )
    assert (
        _effect_matches(
            requested_authority,
            concern_state(**replace(conversation, conversation_requested=False, conversation_operation="").dump())[5],
            effect_result("conversation", 1, "h1", True, operation="conversation:1"),
        )
        is False
    )


def test_used_repair_fingerprint_names_human_wait_and_cannot_repair_again() -> None:
    concerns = concern_state(
        epoch=2,
        head="h2",
        actions="reproduced",
        actions_observation="obs",
        repair_used=True,
        repair_fingerprint="fp",
    )
    observation = ActionsObservation(2, "h2", "run", 2, "failure", "fp", observation="obs")
    assert _repairable(concerns[0], concerns[1], concerns[4], observation) is False
    assert workflow_wait(project_readiness(*concerns)) == "human repair authorization"


def test_intent_arguments_are_isolated_and_only_authorized_settled_controls_fold() -> None:
    one = Intent(epoch=1, head="h", kind="dismiss", digest="a", authorized=True, blocking=False)
    two = Intent(epoch=1, head="h", kind="dismiss", digest="b", authorized=True, blocking=False)
    one.arguments["findings"] = ["f1"]
    assert two.arguments == {}
    review = ReviewState(findings=[{"id": "f1", "disposition": "new"}])
    denied = Intent(
        epoch=1, head="h", kind="dismiss", digest="x", authorized=False, blocking=False, arguments={"findings": ["f1"]}
    )
    assert fold_intent.implementation(review, denied).findings[0]["disposition"] == "new"
    assert fold_intent.implementation(review, one).findings[0]["disposition"] == "dismiss"
    human = HumanState()
    snoozed = fold_intent.implementation(
        human, Intent(epoch=1, head="h", kind="snooze", digest="s", authorized=True, blocking=False)
    )
    assert snoozed.reminder_snoozed is True
    assert (
        fold_intent.implementation(
            snoozed, Intent(epoch=1, head="h", kind="resume", digest="r", authorized=True, blocking=False)
        ).reminder_snoozed
        is False
    )

    unavailable = make_snapshot("repo", 7, 1, "h", "base", True, True, review="unable")
    disposed = fold_intent.implementation(
        unavailable,
        Intent(
            epoch=1,
            head="h",
            kind="dismiss",
            digest="d",
            authorized=True,
            blocking=False,
            arguments={"findings": ["missing"]},
        ),
    )
    assert disposed.review == "unable"


def test_intent_batch_routes_each_intent_only_to_its_applicable_workflow() -> None:
    intents = [
        Intent(1, "h", "change", "change", True, True),
        Intent(1, "h", "dismiss", "dismiss", True, False),
        Intent(1, "h", "reply", "reply", True, False),
        Intent(1, "h", "status", "status", True, False),
    ]
    binding = SimpleNamespace(tokens=(Token("IntentBatch", IntentBatch(1, "h", intents).dump()),))
    outputs = tuple(
        SimpleNamespace(target=NetPath(path), color="Intent")
        for path in ("change_basis", "intent_result", "reply_basis")
    )

    routed = _unpack_intents(binding, outputs)

    assert {str(path): [token.data["kind"] for token in tokens] for path, tokens in routed.items()} == {
        "change_basis": ["change"],
        "intent_result": ["dismiss"],
        "reply_basis": ["reply"],
    }


def test_real_delay_reminder_rearms_and_pauses_for_approval_and_snooze() -> None:
    @activity(name="conversation", converter=PydanticPayloadConverter())
    def reminder_intent(work: ConversationClassificationRequest) -> IntentBatch:
        kind = work.comment.text
        intent = Intent(epoch=work.epoch, head=work.head, kind=kind, digest=kind, authorized=True, blocking=False)
        return IntentBatch(work.epoch, work.head, [intent])

    definitions = tuple(reminder_intent if item.declaration.name == "conversation" else item for item in ACTIVITIES)
    subject, dispatch = asynchronous_engine(reminder_delay=5, definitions=definitions)
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="admit")
    drive_bounded(subject)
    _, review_invocation = drive_until_activity(subject, dispatch, "review")
    review_work = work_input(review_invocation)
    complete(dispatch, "review", ReviewResult(1, "h1", "clear", [], [], review_work.operation))
    drive_until_activity(subject, dispatch, "dashboard_publish")
    occurrence, invocation = pending(dispatch, "dashboard_publish")
    work = work_input(invocation)
    dispatch.complete(occurrence, effect_result("dashboard", 1, "h1", True, operation=work.operation).dump())
    drive_bounded(subject)
    subject.deliver(
        "human_observation",
        token(HumanObservation(1, "h1", True, False, False, 0, False, False, True, False, True)),
        identity="unapproved",
    )
    drive_bounded(subject)

    # The coordinator observes the timer maturity through its Engine clock.
    for _ in range(20):
        outcome = subject.advance()
        if pending_all(dispatch, "reminder_publish"):
            break
        assert outcome.ready
    else:
        raise AssertionError("reminder did not mature")
    first_occurrence, first_invocation = pending(dispatch, "reminder_publish")
    assert work_input(first_invocation).sequence == 0
    dispatch.complete(first_occurrence, effect_result("reminder", 1, "h1", True).dump())
    subject.deliver(
        "human_observation",
        token(HumanObservation(1, "h1", True, True, False, 0, False, False, True, False, True)),
        identity="approved",
    )
    drive_bounded(subject)
    assert values(subject, "reminder.timer")[0]["sequence"] == 1
    for _ in range(10):
        drive_bounded(subject)
    assert not pending_all(dispatch, "reminder_publish")
    subject.deliver(
        "human_observation",
        token(HumanObservation(1, "h1", True, False, False, 0, False, False, True, False, True)),
        identity="dismissed",
    )
    drive_bounded(subject)
    drive_until_activity(subject, dispatch, "reminder_publish")
    assert work_input(pending(dispatch, "reminder_publish")[1]).sequence == 1
    occurrence, _ = pending(dispatch, "reminder_publish")
    dispatch.complete(occurrence, effect_result("reminder", 1, "h1", True).dump())
    subject.deliver("conversation_observation", token(ConversationObservation(1, "h1", True, "snooze")), identity="s")
    drive_bounded(subject)
    drive_until_activity(subject, dispatch, "conversation")
    complete(
        dispatch,
        "conversation",
        IntentBatch(1, "h1", [Intent(epoch=1, head="h1", kind="snooze", digest="s", authorized=True, blocking=False)]),
    )
    drive_bounded(subject)
    for _ in range(10):
        drive_bounded(subject)
    assert not pending_all(dispatch, "reminder_publish")
    subject.deliver("conversation_observation", token(ConversationObservation(1, "h1", True, "resume")), identity="r")
    drive_bounded(subject)
    drive_until_activity(subject, dispatch, "conversation")
    complete(
        dispatch,
        "conversation",
        IntentBatch(1, "h1", [Intent(epoch=1, head="h1", kind="resume", digest="r", authorized=True, blocking=False)]),
    )
    drive_bounded(subject)
    drive_until_activity(subject, dispatch, "reminder_publish")
    assert work_input(pending(dispatch, "reminder_publish")[1]).sequence == 2


def test_reminder_asks_for_assignment_but_pauses_for_mutation_and_stops_after_real_approval() -> None:
    control = make_snapshot(
        "repo",
        7,
        1,
        "head",
        "base",
        True,
        True,
        actions="green",
        review="clear",
        findings_published=True,
        human_approved=True,
        mergeable=True,
        dashboard_current=True,
        author="author",
    )
    timer = Reminder(1, "head")

    # A zero-approval policy can be ready while the workflow still helps the
    # author obtain the desired human review rather than inventing a reviewer.
    assert _reminder_due(control, timer)
    assert not _reminder_due(replace(control, change_in_flight=True), timer)
    assert not _reminder_due(replace(control, distinct_reviewer_approved=True), timer)


def test_dashboard_format_upgrade_requests_one_fresh_projection() -> None:
    old = make_snapshot("repo", 7, 1, "head", "base", True, True, dashboard_current=True)
    assert _request_dashboard(old)
    assert not _request_dashboard(replace(old, dashboard_format=DASHBOARD_FORMAT))


def test_quiescent_control_projects_one_priority_ordered_external_wait() -> None:
    ready_control = make_snapshot(
        "repo",
        7,
        1,
        "head",
        "base",
        True,
        True,
        actions="green",
        review="clear",
        findings_published=True,
        human_approved=True,
        mergeable=True,
    )

    assert workflow_wait(ready_control) == "terminal lifecycle"
    assert workflow_wait(replace(ready_control, actions="waiting")) == "GitHub Actions"
    assert workflow_wait(replace(ready_control, change_in_flight=True)) == "change result"
    assert workflow_wait(replace(ready_control, conflict=True, actions="waiting")) == "conflict resolution"


def test_late_review_and_dashboard_results_retire_after_supersession_and_terminal() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="a1")
    drive_bounded(subject)
    old_review, review_invocation = drive_until_activity(subject, dispatch, "review")
    subject.deliver("verified_admission", token(Admission("repo", 7, "h2", "base", True)), identity="a2")
    drive_bounded(subject)
    publication_count = len(
        [record for record in requests(subject) if record.activity in {"finding_publish", "readiness_publish"}]
    )
    dispatch.complete(
        old_review,
        ReviewResult(
            1,
            "h1",
            "blocking",
            [{"id": "old", "blocking": True}],
            [],
            work_input(review_invocation).operation,
        ).dump(),
    )
    drive_bounded(subject)
    control = snapshot(subject).dump()
    assert (control["epoch"], control["head"], control["review"], control["dashboard_current"]) == (
        2,
        "h2",
        "pending",
        False,
    )
    assert (
        len([record for record in requests(subject) if record.activity in {"finding_publish", "readiness_publish"}])
        == publication_count
    )
    subject.deliver("lifecycle_observation", token(Lifecycle("closed", "h2")), identity="closed")
    for _ in range(20):
        drive_bounded(subject)
        if values(subject, "terminal"):
            break
        for occurrence, invocation in list(dispatch.pending.items()):
            work = work_input(invocation)
            if invocation.activity == "review":
                result = ReviewResult(work.epoch, work.head, "clear", [], [], work.operation)
            elif invocation.activity.startswith("actions_"):
                result = action_result(work, "run", 1, "success")
            elif invocation.activity == "conversation":
                result = IntentBatch(work.epoch, work.head, [])
            else:
                result = effect_result(
                    invocation.activity.removesuffix("_publish"), work.epoch, work.head, True, operation=work.operation
                )
            dispatch.complete(occurrence, result.dump())
    assert values(subject, "terminal")[0]["status"] == "abort" and not values(subject, "review_result")


def test_specialized_retirement_absorbs_stale_actions_result() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="a1")
    drive_bounded(subject)
    old_actions, invocation = drive_until_activity(subject, dispatch, "actions_discovery")

    subject.deliver("verified_admission", token(Admission("repo", 7, "h2", "base", True)), identity="a2")
    drive_bounded(subject)
    dispatch.complete(old_actions, action_result(work_input(invocation), "old-run", 1, "success").dump())
    drive_bounded(subject)

    assert (snapshot(subject).head, snapshot(subject).actions) == ("h2", "discovering")
    assert not values(subject, "actions_result")


def test_specialized_retirement_absorbs_stale_conversation_basis() -> None:
    subject = engine()
    admit(subject, "h1", "current")

    deliver(
        subject,
        "conversation_observation",
        ConversationObservation(0, "old", True, "please reply", comment_id=1),
        "stale-conversation",
    )

    assert not values(subject, "conversation_basis")
    assert not [
        item for item in requests(subject) if item.activity == "conversation" and work_input(item).head == "old"
    ]


def test_late_authorized_change_cannot_make_a_superseding_head_provisional() -> None:
    @activity(name="conversation", converter=PydanticPayloadConverter())
    def change_intent(work: ConversationClassificationRequest) -> IntentBatch:
        intent = Intent(
            epoch=work.epoch,
            head=work.head,
            kind="change",
            digest="authorized",
            authorized=True,
            blocking=True,
            base_head=str(work.base_head),
            policy_digest=str(work.policy_digest),
        )
        return IntentBatch(work.epoch, work.head, [intent])

    definitions = tuple(change_intent if item.declaration.name == "conversation" else item for item in ACTIVITIES)
    subject, dispatch = asynchronous_engine(definitions=definitions)
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="a1")
    drive_bounded(subject)
    subject.deliver(
        "conversation_observation", token(ConversationObservation(1, "h1", True, "change")), identity="change"
    )
    drive_bounded(subject)
    drive_until_activity(subject, dispatch, "conversation")
    complete(
        dispatch,
        "conversation",
        IntentBatch(
            1,
            "h1",
            [
                Intent(
                    epoch=1,
                    head="h1",
                    kind="change",
                    digest="authorized",
                    authorized=True,
                    blocking=True,
                    base_head="base",
                )
            ],
        ),
    )
    drive_bounded(subject)
    occurrence, invocation = pending(dispatch, "change")
    subject.deliver("verified_admission", token(Admission("repo", 7, "human-head", "base", True)), identity="human")
    drive_bounded(subject)
    dispatch.complete(
        occurrence,
        effect_result(
            "change", 1, "h1", True, provisional_head="agent-head", operation=work_input(invocation).operation
        ).dump(),
    )
    drive_bounded(subject)
    control = snapshot(subject).dump()
    assert (control["head"], control["provisional"], control["provisional_head"]) == ("human-head", False, "")


def test_repair_budget_survives_provisional_admission_and_blocks_same_fingerprint() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="a1")
    drive_bounded(subject)
    dashboard_occurrence, dashboard_invocation = drive_until_activity(subject, dispatch, "dashboard_publish")
    dashboard_work = work_input(dashboard_invocation)
    dispatch.complete(
        dashboard_occurrence,
        effect_result("dashboard", 1, "h1", True, operation=dashboard_work.operation).dump(),
    )
    drive_bounded(subject)
    first = observed_actions(subject, "external", 1, "failure", "fp", observation="failure-1")
    subject.deliver("actions_observation", token(first), identity="failure")
    drive_bounded(subject)
    rerun_occurrence, rerun_invocation = drive_until_activity(subject, dispatch, "actions_rerun")
    second = action_result(work_input(rerun_invocation), "rerun", 2, "failure", "fp", observation="failure-2")
    dispatch.complete(rerun_occurrence, second.dump())
    drive_bounded(subject)
    repair_occurrence, repair_invocation = pending(dispatch, "repair")
    dispatch.complete(
        repair_occurrence,
        effect_result(
            "repair",
            1,
            "h1",
            True,
            provisional_head="h2",
            fingerprint="fp",
            operation=work_input(repair_invocation).operation,
        ).dump(),
    )
    drive_bounded(subject)
    assert snapshot(subject).dump()["provisional_head"] == "h2"
    subject.deliver("verified_admission", token(Admission("repo", 7, "h2", "base", True)), identity="confirm")
    drive_bounded(subject)
    assert snapshot(subject).dump()["repair_used"] is True
    for _ in range(20):
        control = snapshot(subject).dump()
        if control["actions"] == "green" and control["review"] == "clear":
            break
        drive_bounded(subject)
        for occurrence, invocation in list(dispatch.pending.items()):
            work = work_input(invocation)
            if invocation.activity == "review":
                result = ReviewResult(work.epoch, work.head, "clear", [], [], work.operation)
            elif invocation.activity == "actions_discovery":
                result = action_result(work, "discovery", 1, "success")
            elif invocation.activity == "conversation":
                result = IntentBatch(work.epoch, work.head, [])
            else:
                result = effect_result(
                    invocation.activity.removesuffix("_publish"), work.epoch, work.head, True, operation=work.operation
                )
            dispatch.complete(occurrence, result.dump())
    else:
        raise AssertionError("new generation did not finish initial review and discovery")
    for dashboard_occurrence, dashboard_invocation in pending_all(dispatch, "dashboard_publish"):
        dashboard_work = work_input(dashboard_invocation)
        dispatch.complete(
            dashboard_occurrence,
            effect_result("dashboard", 2, "h2", True, operation=dashboard_work.operation).dump(),
        )
        drive_bounded(subject)

    subject.deliver(
        "actions_observation",
        token(observed_actions(subject, "external-2", 1, "failure", "fp", observation="new-1")),
        identity="new-failure",
    )
    drive_bounded(subject)
    rerun_occurrence, rerun_invocation = drive_until_activity(subject, dispatch, "actions_rerun")
    dispatch.complete(
        rerun_occurrence,
        action_result(work_input(rerun_invocation), "rerun-2", 2, "failure", "fp", observation="new-2").dump(),
    )
    drive_bounded(subject)
    assert not pending_all(dispatch, "repair")
    for _ in range(20):
        if not dispatch.pending:
            drive_bounded(subject)
            break
        for occurrence, invocation in list(dispatch.pending.items()):
            assert invocation.activity != "repair"
            work = work_input(invocation)
            if invocation.activity == "review":
                result = ReviewResult(work.epoch, work.head, "clear", [], [], work.operation)
            elif invocation.activity.startswith("actions_"):
                result = action_result(work, "run", 1, "success")
            elif invocation.activity == "conversation":
                result = IntentBatch(work.epoch, work.head, [])
            else:
                result = effect_result(
                    invocation.activity.removesuffix("_publish"), work.epoch, work.head, True, operation=work.operation
                )
            dispatch.complete(occurrence, result.dump())
        drive_bounded(subject)
    assert not values(subject, "work.repair") and not values(subject, "actions_basis")
    assert snapshot(subject).dump()["wait"] == "human repair authorization"


def test_terminal_actions_observation_does_not_release_a_pending_repair() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="admit")
    drive_bounded(subject)
    discovery_occurrence, discovery_invocation = drive_until_activity(subject, dispatch, "actions_discovery")
    discovery_work = work_input(discovery_invocation)
    dispatch.complete(discovery_occurrence, action_result(discovery_work, "initial", 1, "success").dump())
    drive_bounded(subject)
    first = observed_actions(subject, "external", 1, "failure", "fp", observation="failure-1")
    subject.deliver("actions_observation", token(first), identity="failure")
    drive_bounded(subject)
    rerun_occurrence, rerun_invocation = drive_until_activity(subject, dispatch, "actions_rerun")
    dispatch.complete(
        rerun_occurrence,
        action_result(work_input(rerun_invocation), "rerun", 2, "failure", "fp", observation="failure-2").dump(),
    )
    drive_bounded(subject)
    repair_occurrence, repair_invocation = pending(dispatch, "repair")
    repair_work = work_input(repair_invocation)
    assert snapshot(subject).repair_in_flight is True

    terminal = observed_actions(subject, "manual", 3, "success", observation="manual-success")
    subject.deliver("actions_observation", token(terminal), identity="manual-actions")
    drive_bounded(subject)

    authority = state(subject, "authority", Authority)
    mutation = state(subject, "mutation_state", MutationState)
    intent = Intent(1, "h1", "change", "change", True, True, base_head="base")
    assert mutation.repair_in_flight is True
    assert mutation.mutation_operation == repair_work.operation
    assert _mutation(authority, mutation, intent) is False

    dispatch.complete(
        repair_occurrence,
        effect_result("repair", 1, "h1", False, operation=repair_work.operation).dump(),
    )
    drive_bounded(subject)
    assert snapshot(subject).repair_in_flight is False


def test_activity_topology_has_complete_retirement_and_no_authority_outputs() -> None:
    net = build_net(1).net
    assert all("merge" not in str(transition) for transition in net.transitions)
    assert NetPath("current") not in net.places
    assert all(place.color != "Control" for place in net.places.values())
    refresh_inputs = {str(item.source): item.mode.value for item in net.inputs(NetPath("refresh_admission"))}
    assert refresh_inputs == {
        "review_state": "read",
        "authority": "consume",
        "admission": "consume",
    }
    assert {str(item.target) for item in net.outputs(NetPath("refresh_admission"))} == {"authority"}
    for transition in (
        "accept_actions",
        "accept_human",
        "authorize_rerun",
        "authorize_repair",
        "authorize_change",
    ):
        assert "publication_state" not in {str(item.source) for item in net.inputs(NetPath(transition))}
    assert "mutation_state" not in {str(item.source) for item in net.inputs(NetPath("accept_actions"))}
    assert {str(item.target) for item in net.outputs(NetPath("actions_observation"))} == {"actions_result"}
    assert {str(item.target) for item in net.outputs(NetPath("execute.actions_discovery"))} == {"actions_result"}
    assert {str(item.target) for item in net.outputs(NetPath("execute.actions_rerun"))} == {"actions_result"}
    assert {str(item.target) for item in net.outputs(NetPath("accept_actions"))} == {
        "actions_state",
        "actions_basis",
    }
    assert {str(item.target) for item in net.outputs(NetPath("unpack_intents"))} == {
        "change_basis",
        "intent_result",
        "reply_basis",
    }
    reminder_inputs = {str(item.source): item.mode.value for item in net.inputs(NetPath("accept_reminder"))}
    assert reminder_inputs == {"authority": "read", "reminder_result": "consume"}
    assert not net.outputs(NetPath("accept_reminder"))
    authority = {"authority", "admission", "terminal"}
    result_consumers = {
        "accept_review",
        "accept_actions",
        "unpack_intents",
        "authorize_rerun",
        "authorize_repair",
        "authorize_change",
        "accept_conversation",
        "accept_repair",
        "accept_change",
        "accept_finding",
        "accept_dashboard",
        "accept_reminder",
        "accept_readiness",
    }
    for path in ACTIVITY_TRANSITIONS:
        transition = NetPath(path)
        inputs = net.inputs(transition)
        outputs = net.outputs(transition)
        assert len(inputs) == 1
        input_place = inputs[0].source
        assert not ({str(arc.target) for arc in outputs} & authority)
        output_places = {arc.target for arc in outputs}
        for place, result in ((input_place, False), *((item, True) for item in output_places)):
            consumers = {arc.target for arc in net.arcs if arc.source == place}
            names = {str(item) for item in consumers}
            assert any(name.startswith("retire.dormant_") for name in names)
            assert any(name.startswith("retire.terminal_") for name in names)
            if not result:
                assert any(name.startswith("retire.stale_") for name in names)
            else:
                assert any(
                    name in result_consumers
                    or name.startswith("retire.")
                    and any(word in name for word in ("operation", "duplicate"))
                    for name in names
                )

    retirement_names = {str(path) for path in net.transitions if str(path).startswith("retire.")}
    assert "retire.intent_noop" not in retirement_names
    assert "retire.stale_work_dashboard" in retirement_names
    assert "retire.dormant_dashboard_result" in retirement_names
    assert "retire.terminal_dashboard_result" in retirement_names
    assert "retire.stale_dashboard_result" not in retirement_names
    assert (len(net.places), len(net.transitions), len(net.arcs)) == (40, 138, 412)
    assert NetPath("reissue_reply") not in net.transitions
    publication_paths = {str(path) for path in (*net.places, *net.transitions) if str(path).startswith("publication.")}
    assert not any(
        any(part in path for part in ("lease", "retry", "due", "reissue", "mature")) for path in publication_paths
    )
    for name in ("dashboard", "readiness"):
        accept = NetPath(f"accept_{name}")
        result = f"{name}_result"
        assert {str(item.source): item.mode.value for item in net.inputs(accept)} == {
            "authority": "read",
            "publication_state": "consume",
            result: "consume",
        }
        assert len(net.transitions[accept].timers) == 0


def test_topology_hydration_strictly_rejects_malformed_dashboard_request() -> None:
    snapshot_value = make_snapshot("repo", 7, 1, "head", "base", True, True)
    request = DashboardPublicationRequest(1, "head", "dashboard:1", "base", "policy", snapshot_value).dump()
    request["unexpected"] = True
    binding = SimpleNamespace(
        read=(), consumed=((NetPath("work.dashboard"), (Token("DashboardPublicationRequest", request),)),)
    )

    with pytest.raises(ValidationError):
        _hydrate(binding)


def test_mutation_requires_current_authority_basis() -> None:
    authorized = Intent(
        epoch=1,
        head="h1",
        kind="change",
        digest="intent-digest",
        authorized=True,
        blocking=True,
        base_head="base-1",
        policy_digest="policy-1",
    )
    authority, _, _, _, mutation, _ = concern_state(head="h1", base_head="base-1", policy_digest="policy-1")
    assert _mutation(authority, mutation, authorized) is True
    stale_authority, _, _, _, stale_mutation, _ = concern_state(head="h1", base_head="base-2", policy_digest="policy-2")
    assert _mutation(stale_authority, stale_mutation, authorized) is False


def test_external_second_attempt_is_green_but_only_an_impetus_rerun_is_flaky() -> None:
    control = make_snapshot("repo", 7, 1, "h1", "base", True, True, actions_operation="actions")
    external = ActionsObservation(1, "h1", "run", 2, "success", operation="actions")
    assert fold_actions.implementation(control, external).actions == "green"
    rerun = make_snapshot(
        "repo",
        7,
        1,
        "h1",
        "base",
        True,
        True,
        rerun_requested=True,
        actions_operation="actions",
    )
    assert fold_actions.implementation(rerun, external).actions == "flaky_green"


def test_dashboard_capability_denial_is_an_explicit_blocker_not_success() -> None:
    concerns = concern_state(
        head="h1",
        actions="green",
        review="clear",
        findings_published=True,
        human_approved=True,
        mergeable=True,
        dashboard_current=True,
        dashboard_requested=True,
        dashboard_operation="dashboard",
    )
    result = effect_result("dashboard", 1, "h1", False, operation="dashboard", capability_available=False)
    blocked = fold_effect(concerns[5], result)
    assert blocked.dashboard_capability_blocking is True
    assert blocked.dashboard_requested is True
    assert blocked.dashboard_operation == "dashboard"
    assert project_readiness(*concerns[:5], blocked).dashboard_current is False
    assert workflow_wait(project_readiness(*concerns[:5], blocked)) == "dashboard update capability"


@pytest.mark.parametrize(
    ("index", "changed"),
    [
        (1, ActionsState(actions="failed", attempt=1)),
        (3, HumanState(human_approved=False, mergeable=True)),
    ],
)
def test_concern_change_stales_dashboard_without_changing_publication_bytes(index, changed) -> None:
    concerns = concern_state(
        actions="green",
        review="clear",
        findings_published=True,
        human_approved=True,
        mergeable=True,
        dashboard_current=True,
    )
    publication_bytes = concerns[5].dump()
    changed_concerns = list(concerns)
    changed_concerns[index] = changed

    assert project_readiness(*concerns).dashboard_current is True
    assert project_readiness(*changed_concerns).dashboard_current is False
    assert changed_concerns[5].dump() == publication_bytes


def test_human_observation_lineage_does_not_change_dashboard_projection() -> None:
    concerns = concern_state(human_approved=True, mergeable=True)
    advanced = (*concerns[:3], concerns[3].validated_update(observation_sequence=9), *concerns[4:])

    assert dashboard_projection_digest(*advanced) == dashboard_projection_digest(*concerns)


def test_readiness_capability_denial_relationally_stales_its_ready_dashboard() -> None:
    concerns = concern_state(
        head="h1",
        actions="green",
        review="clear",
        findings_published=True,
        human_approved=True,
        mergeable=True,
        dashboard_current=True,
        readiness_requested=True,
        readiness_operation="readiness",
    )
    result = effect_result("readiness", 1, "h1", False, operation="readiness", capability_available=False)

    blocked = fold_effect(concerns[5], result)

    assert blocked.dashboard_requested is False
    assert blocked.readiness_capability_blocking is True
    assert project_readiness(*concerns[:5], blocked).dashboard_current is False
    assert workflow_wait(project_readiness(*concerns[:5], blocked)) == "readiness publication capability"


def test_capability_available_conversation_terminal_clears_operation() -> None:
    work = request("conversation", 1, "h1", "conversation:1")
    control = make_snapshot(
        "repo",
        7,
        1,
        "h1",
        "base",
        True,
        True,
        conversation_requested=True,
        conversation_operation=work.operation,
    )

    cleared = fold_effect(
        control,
        effect_result("conversation", 1, "h1", False, operation=work.operation),
    )

    assert cleared.conversation_requested is False
    assert cleared.conversation_operation == ""
    assert cleared.conversation_capability_blocking is False


def test_readiness_ack_relationally_stales_dashboard_before_latching_announcement() -> None:
    concerns = concern_state(
        repository_id="repo",
        pr_number=7,
        epoch=1,
        head="h1",
        base_head="base",
        strict_base=True,
        base_current=True,
        actions="green",
        review="clear",
        findings_published=True,
        human_approved=True,
        mergeable=True,
        dashboard_current=True,
        readiness_requested=True,
        readiness_operation="readiness",
    )
    control = project_readiness(*concerns)
    assert ready(control) is False
    acknowledged = fold_effect(
        concerns[5],
        effect_result("readiness", 1, "h1", True, operation="readiness"),
    )
    assert acknowledged.announced is True
    assert project_readiness(*concerns[:5], acknowledged).dashboard_current is False


def test_mismatched_subject_admission_cannot_rebind_an_instance() -> None:
    subject = engine()
    admit(subject, "h1", "first")
    deliver(subject, "verified_admission", Admission("other", 99, "h2", "base", True), "misrouted")
    control = snapshot(subject).dump()
    assert (control["repository_id"], control["pr_number"], control["head"], control["epoch"]) == (
        "repo",
        7,
        "h1",
        1,
    )
    assert not values(subject, "admission")


def test_same_generation_stale_dashboard_ack_cannot_ack_newer_projection() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="a")
    drive_bounded(subject)
    old_occurrence, old_invocation = drive_until_activity(subject, dispatch, "dashboard_publish")
    subject.deliver(
        "human_observation",
        token(HumanObservation(1, "h1", True, False, False, 0, False, False, False, False, True)),
        identity="invalidate",
    )
    drive_bounded(subject)
    dashboards = pending_all(dispatch, "dashboard_publish")
    assert dashboards == [(old_occurrence, old_invocation)]
    dispatch.complete(
        old_occurrence,
        effect_result("dashboard", 1, "h1", True, operation=work_input(old_invocation).operation).dump(),
    )
    drive_bounded(subject)
    assert snapshot(subject).dump()["dashboard_current"] is False
    assert not values(subject, "dashboard_result")
    current_occurrence, current_invocation = pending(dispatch, "dashboard_publish")
    dispatch.complete(
        current_occurrence,
        effect_result("dashboard", 1, "h1", True, operation=work_input(current_invocation).operation).dump(),
    )
    drive_bounded(subject)
    assert snapshot(subject).dump()["dashboard_current"] is True
