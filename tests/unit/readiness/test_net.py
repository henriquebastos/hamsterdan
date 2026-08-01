"""Executable contract tests for the replacement PR-readiness topology."""

from dataclasses import asdict, replace
from types import SimpleNamespace

from petrus.engine import Engine, SimulatedClock
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import DataclassPayloadConverter, activity
from petrus.motus.dispatch import InlineDispatch, InMemoryDispatch

from hamsterdan.contracts.readiness import (
    ActionsObservation,
    Admission,
    Control,
    ConversationObservation,
    EffectResult,
    HumanObservation,
    Intent,
    IntentBatch,
    Lifecycle,
    ReadinessCommand,
    Reminder,
    ReviewResult,
    Seed,
    Work,
    workflow_gates_ready,
    workflow_wait,
)
from hamsterdan.readiness.net.topology import (
    ACTIVITY_TRANSITIONS,
    DASHBOARD_FORMAT,
    MAX_REVIEW_ATTEMPTS,
    _basis_done,
    _effect_matches,
    _guard,
    _mutation,
    _reminder_due,
    _repairable,
    _request_dashboard,
    _retry_review,
    _retryable_review,
    build_net,
    fold_actions,
    fold_effect,
    fold_intent,
    fold_review,
    ready,
)


def token(value) -> Token:
    return Token(type(value).__name__, asdict(value))


@activity(name="review", converter=DataclassPayloadConverter())
def review(work: Work) -> ReviewResult:
    return ReviewResult(work.epoch, work.head, "clear", [], [], work.operation)


@activity(name="actions_discovery", converter=DataclassPayloadConverter())
def actions_discovery(work: Work) -> ActionsObservation:
    return action_result(work, "run", 1, "success")


@activity(name="actions_rerun", converter=DataclassPayloadConverter())
def actions_rerun(work: Work) -> ActionsObservation:
    return action_result(work, "rerun", 2, "success")


@activity(name="conversation", converter=DataclassPayloadConverter())
def conversation(work: Work) -> IntentBatch:
    intent = Intent(work.epoch, work.head, "read", "digest", True, True, False)
    return IntentBatch(work.epoch, work.head, [asdict(intent)])


def _effect(name: str):
    @activity(name=name, converter=DataclassPayloadConverter())
    def perform(work: Work) -> EffectResult:
        return EffectResult(
            name.removesuffix("_publish"),
            work.epoch,
            work.head,
            True,
            provisional_head="next" if name in {"change", "repair"} else "",
            operation=work.operation,
        )

    return perform


repair = _effect("repair")
change = _effect("change")
conversation_publish = _effect("conversation_publish")
finding_publish = _effect("finding_publish")
dashboard_publish = _effect("dashboard_publish")
reminder_publish = _effect("reminder_publish")


@activity(name="readiness_publish", converter=DataclassPayloadConverter())
def readiness_publish(command: ReadinessCommand) -> EffectResult:
    return EffectResult("readiness", command.epoch, command.head, True, operation=command.operation)


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


def asynchronous_engine(*, reminder_delay: int = 10, definitions=ACTIVITIES) -> tuple[Engine, InMemoryDispatch]:
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
            clock=SimulatedClock(),
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
    dispatch.complete(occurrence, asdict(result))
    return occurrence


def work_input(invocation) -> Work:
    return Work(**invocation.input["work"])


def action_result(
    work: Work,
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
        base_head=str(work.payload["base_head"]),
        policy_digest=str(work.payload["policy_digest"]),
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
    control = values(subject, "current")[0]
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
                result = EffectResult(kind, work.epoch, work.head, True, operation=work.operation)
            dispatch.complete(occurrence, asdict(result))
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


def admit(subject: Engine, head: str, identity: str) -> None:
    deliver(subject, "verified_admission", Admission("repo", 7, head, "base", True), identity)


def requests(subject: Engine) -> list[ActivityRequested]:
    return [record for record in subject.records if isinstance(record, ActivityRequested)]


def test_every_obligation_is_a_real_typed_activity_and_readiness_is_end_to_end() -> None:
    subject = engine()
    admit(subject, "h1", "admit")
    deliver(
        subject,
        "human_observation",
        HumanObservation(1, "h1", True, True, False, 0, True, True, True, False, True),
        "human",
    )
    names = [record.activity for record in requests(subject)]
    assert {"review", "actions_discovery", "dashboard_publish", "readiness_publish"} <= set(names)
    control = values(subject, "current")[0]
    assert control["announced"] is True
    assert not values(subject, "command.readiness")
    assert all(
        NetPath(path) in build_net(2).net.places
        for path in ("review_result", "actions_result", "intent_result", "effect_result")
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
    assert values(subject, "current")[0]["epoch"] == 1
    for epoch in range(1, 11):
        admit(subject, f"h{epoch}", f"a{epoch}")
    assert values(subject, "current")[0]["epoch"] == 11
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
        control = values(subject, "current")[0]
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
    control = values(subject, "current")[0]
    assert control["review_attempts"] == MAX_REVIEW_ATTEMPTS
    assert control["wait"] == "coordinating review capability"


def test_legacy_unable_review_without_attempt_count_resumes_at_attempt_two() -> None:
    control = Control("repo", 7, 1, "h1", "base", True, True, review="unable")
    admission = Admission("repo", 7, "h1", "base", True)

    assert _retryable_review(control, admission)
    outputs = (SimpleNamespace(target="current", color="control"), SimpleNamespace(target="work", color="work"))
    binding = SimpleNamespace(peeked=[token(control), token(admission)])
    routed = _retry_review(binding, outputs)

    assert routed[outputs[0].target][0].data["review_attempts"] == 2
    assert routed[outputs[1].target][0].data["sequence"] == 2


def test_review_retry_atomically_refreshes_admission_authority() -> None:
    control = Control(
        "repo",
        7,
        1,
        "h1",
        "base",
        True,
        False,
        review="unable",
        review_attempts=1,
    )
    admission = Admission("repo", 7, "h1", "base", True, base_current=True)
    outputs = (SimpleNamespace(target="current", color="control"), SimpleNamespace(target="work", color="work"))
    binding = SimpleNamespace(peeked=[token(control), token(admission)])

    routed = _retry_review(binding, outputs)

    changed = routed[outputs[0].target][0].data
    work = routed[outputs[1].target][0].data
    assert changed["base_current"] is True
    assert changed["review_attempts"] == 2
    assert work["payload"]["base_current"] is True
    assert len(routed[outputs[1].target]) == 1


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
    assert values(subject, "current")[0]["review_attempts"] == 1

    subject.deliver("verified_admission", token(Admission("repo", 7, "h2", "base", True)), identity="new-head")
    _, invocation = drive_until_activity(subject, dispatch, "review")
    new_work = work_input(invocation)
    assert (new_work.epoch, new_work.head) == (2, "h2")
    assert values(subject, "current")[0]["review_attempts"] == 1


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


def test_failed_conversation_publication_reissues_the_same_fenced_operation() -> None:
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
        1,
        "h1",
        "reply",
        "status",
        True,
        True,
        False,
        {"message": "Safe status"},
        "base",
    )
    dispatch.complete(conversation_occurrence, asdict(IntentBatch(1, "h1", [asdict(reply)])))
    drive_bounded(subject)

    first_occurrence, first_invocation = drive_until_activity(subject, dispatch, "conversation_publish")
    first_work = work_input(first_invocation)
    dispatch.complete(
        first_occurrence,
        asdict(
            EffectResult(
                "conversation",
                first_work.epoch,
                first_work.head,
                False,
                operation=first_work.operation,
                capability_available=False,
            )
        ),
    )
    drive_bounded(subject)

    second_occurrence, second_invocation = drive_until_activity(subject, dispatch, "conversation_publish")
    second_work = work_input(second_invocation)
    control = values(subject, "current")[0]
    assert second_occurrence != first_occurrence
    assert second_work == first_work
    assert control["conversation_attempts"] == 2
    assert control["conversation_pending"]["operation"] == first_work.operation

    dispatch.complete(
        second_occurrence,
        asdict(EffectResult("conversation", 1, "h1", True, operation=second_work.operation)),
    )
    drive_bounded(subject)
    control = values(subject, "current")[0]
    assert control["conversation_pending"] == {}
    assert control["conversation_attempts"] == 0
    assert control["conversation_capability_blocking"] is False
    assert conversation_work.operation != first_work.operation


def test_conversation_publication_exhaustion_is_bounded_and_blocks_readiness() -> None:
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
        1,
        "h1",
        "reply",
        "status",
        True,
        True,
        False,
        {"message": "Safe status"},
        "base",
    )
    dispatch.complete(conversation_occurrence, asdict(IntentBatch(1, "h1", [asdict(reply)])))
    drive_bounded(subject)

    first_work = None
    for attempt in range(1, 4):
        occurrence, invocation = drive_until_activity(subject, dispatch, "conversation_publish")
        work = work_input(invocation)
        first_work = first_work or work
        assert work == first_work
        dispatch.complete(
            occurrence,
            asdict(
                EffectResult(
                    "conversation",
                    work.epoch,
                    work.head,
                    False,
                    operation=work.operation,
                    capability_available=False,
                )
            ),
        )
        drive_bounded(subject)
        if attempt < 3:
            assert values(subject, "current")[0]["conversation_attempts"] == attempt + 1

    control = values(subject, "current")[0]
    assert pending_all(dispatch, "conversation_publish") == []
    assert control["conversation_attempts"] == 3
    assert control["conversation_capability_blocking"] is True
    assert control["conversation_pending"]["operation"] == first_work.operation
    assert workflow_gates_ready(Control(**control)) is False
    otherwise_ready = Control(
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
    assert values(subject, "dormant")[0]["last_epoch"] == 1
    admit(subject, "h1", "resume")
    assert values(subject, "current")[0]["epoch"] == 2
    deliver(subject, "lifecycle_observation", Lifecycle("merged", "provider-head"), "merged")
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


def test_same_head_refreshes_verified_base_without_creating_a_generation() -> None:
    subject = engine()
    admit(subject, "h1", "first")
    dashboards = len([item for item in requests(subject) if item.activity == "dashboard_publish"])
    deliver(subject, "verified_admission", Admission("repo", 7, "h1", "base-2", False, False), "refresh")
    control = values(subject, "current")[0]
    assert (control["epoch"], control["base_head"], control["strict_base"], control["base_current"]) == (
        1,
        "base-2",
        False,
        False,
    )
    assert control["admission_relation"] == "same_head_basis_changed"
    assert len([item for item in requests(subject) if item.activity == "dashboard_publish"]) == dashboards + 1


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
    control = Control("repo", 7, 1, "h", "base", True, True, actions_operation="actions")
    failure = ActionsObservation(1, "h", "run", 1, "failure", "fp", operation="actions", observation="new")
    assert _basis_done(control, failure) is False

    folded = fold_actions.implementation(control, failure)
    assert _basis_done(folded, failure) is False
    duplicate_after_rerun = replace(folded, rerun_requested=True, rerun_attempt=1)
    assert _basis_done(duplicate_after_rerun, failure) is True


def test_advanced_guards_hydrate_defaults_for_replayed_control_tokens() -> None:
    old_control = asdict(Control("repo", 7, 1, "h", "base", True, True))
    old_control.pop("rerun_attempt")
    old_control.pop("review_attempts")
    companion = asdict(ActionsObservation(1, "h", "run", 1, "failure"))
    binding = SimpleNamespace(
        consumed=(("actions", (Token("ActionsObservation", companion),)),),
        read=(("current", (Token("Control", old_control),)),),
    )
    guard = _guard(lambda control, value: control.rerun_attempt == 0 and value.attempt == 1)
    assert guard.implementation(binding) is True


def test_irrelevant_lifecycle_fact_is_retired_while_dormant() -> None:
    subject = engine()
    admit(subject, "h1", "admit")
    deliver(subject, "lifecycle_observation", Lifecycle("draft", "h1"), "draft")
    deliver(subject, "lifecycle_observation", Lifecycle("open", "h1"), "irrelevant")

    assert values(subject, "dormant")
    assert not values(subject, "lifecycle")
    assert not values(subject, "terminal")


def test_failed_repair_spends_the_automatic_budget() -> None:
    control = Control(
        "repo",
        7,
        1,
        "h",
        "base",
        True,
        True,
        actions="reproduced",
        fingerprint="fp",
        repair_in_flight=True,
        mutation_operation="repair",
    )
    failed = fold_effect.implementation(
        control,
        EffectResult("repair", 1, "h", False, fingerprint="fp", lineage="repair", operation="repair"),
    )
    assert failed.repair_used is True
    assert failed.repair_fingerprint == "fp"
    assert failed.wait == "repair recovery"


def test_terminal_finding_lineage_stays_visible_without_republication() -> None:
    control = Control(
        "repo",
        7,
        2,
        "h",
        "base",
        True,
        True,
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

    folded = fold_review.implementation(control, result)

    assert folded.review == "clear"
    assert folded.findings == [
        {"id": "finding-1", "title": "Old", "blocking": True, "comment_url": "url", "disposition": "resolved"}
    ]
    assert folded.findings_published is True
    assert folded.finding_publication_requested is False


def test_conflict_is_the_named_wait_after_independent_review_and_actions_finish() -> None:
    control = Control("repo", 7, 1, "h", "base", True, True, conflict=True, actions="green")

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

    control = values(subject, "current")[0]
    assert (control["actions"], control["attempt"], control["rerun_attempt"]) == ("reproduced", 2, 1)
    assert len([item for item in requests(subject) if item.activity == "repair"]) == 1


def test_provisional_blocks_authorized_change_and_stale_dashboard_operation_cannot_ack() -> None:
    control = Control(
        "repo",
        7,
        1,
        "h1",
        "base",
        True,
        True,
        provisional=True,
        mutation_pending=True,
        pending_intent_digest="d",
    )
    intent = Intent(1, "h1", "change", "d", True, True, True, base_head="base")
    assert _mutation(control, intent) is False
    requested = Control(
        "repo",
        7,
        1,
        "h1",
        "base",
        True,
        True,
        revision=4,
        dashboard_requested=True,
        dashboard_operation="dashboard:1:4",
    )
    stale = EffectResult("dashboard", 1, "h1", True, operation="dashboard:1:3")
    assert _effect_matches(requested, stale) is False

    conversation = replace(
        requested,
        conversation_pending=asdict(Work("conversation", 1, "h1", "conversation:1")),
    )
    assert (
        _effect_matches(
            conversation,
            EffectResult("conversation", 1, "h1", True, operation="conversation:stale"),
        )
        is False
    )
    assert (
        _effect_matches(
            conversation,
            EffectResult("conversation", 1, "h1", True, operation="conversation:1"),
        )
        is True
    )
    assert (
        _effect_matches(
            replace(conversation, conversation_pending={}),
            EffectResult("conversation", 1, "h1", True, operation="conversation:1"),
        )
        is False
    )


def test_used_repair_fingerprint_names_human_wait_and_cannot_repair_again() -> None:
    control = Control(
        "repo",
        7,
        2,
        "h2",
        "base",
        True,
        True,
        actions="reproduced",
        actions_observation="obs",
        repair_used=True,
        repair_fingerprint="fp",
        wait="human repair authorization",
    )
    observation = ActionsObservation(2, "h2", "run", 2, "failure", "fp", observation="obs")
    assert _repairable(control, observation) is False
    assert control.wait == "human repair authorization"


def test_intent_arguments_are_isolated_and_only_authorized_settled_controls_fold() -> None:
    one = Intent(1, "h", "dismiss", "a", True, True, False)
    two = Intent(1, "h", "dismiss", "b", True, True, False)
    one.arguments["findings"] = ["f1"]
    assert two.arguments == {}
    control = Control("repo", 7, 1, "h", "base", True, True, findings=[{"id": "f1", "disposition": "new"}])
    denied = Intent(1, "h", "dismiss", "x", False, True, False, {"findings": ["f1"]})
    assert fold_intent.implementation(control, denied).findings[0]["disposition"] == "new"
    assert fold_intent.implementation(control, one).findings[0]["disposition"] == "dismiss"
    snoozed = fold_intent.implementation(control, Intent(1, "h", "snooze", "s", True, True, False))
    assert snoozed.reminder_snoozed is True
    assert (
        fold_intent.implementation(snoozed, Intent(1, "h", "resume", "r", True, True, False)).reminder_snoozed is False
    )

    unavailable = Control("repo", 7, 1, "h", "base", True, True, review="unable")
    disposed = fold_intent.implementation(
        unavailable,
        Intent(1, "h", "dismiss", "d", True, True, False, {"findings": ["missing"]}),
    )
    assert disposed.review == "unable"


def test_real_delay_reminder_rearms_and_pauses_for_approval_and_snooze() -> None:
    @activity(name="conversation", converter=DataclassPayloadConverter())
    def reminder_intent(work: Work) -> IntentBatch:
        kind = work.payload["comment"]["text"]
        intent = Intent(work.epoch, work.head, kind, kind, True, True, False)
        return IntentBatch(work.epoch, work.head, [asdict(intent)])

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
    dispatch.complete(occurrence, asdict(EffectResult("dashboard", 1, "h1", True, operation=work.operation)))
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
    dispatch.complete(first_occurrence, asdict(EffectResult("reminder", 1, "h1", True)))
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
    dispatch.complete(occurrence, asdict(EffectResult("reminder", 1, "h1", True)))
    subject.deliver("conversation_observation", token(ConversationObservation(1, "h1", True, "snooze")), identity="s")
    drive_bounded(subject)
    drive_until_activity(subject, dispatch, "conversation")
    complete(
        dispatch,
        "conversation",
        IntentBatch(1, "h1", [asdict(Intent(1, "h1", "snooze", "s", True, True, False))]),
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
        IntentBatch(1, "h1", [asdict(Intent(1, "h1", "resume", "r", True, True, False))]),
    )
    drive_bounded(subject)
    drive_until_activity(subject, dispatch, "reminder_publish")
    assert work_input(pending(dispatch, "reminder_publish")[1]).sequence == 2


def test_reminder_asks_for_assignment_but_pauses_for_mutation_and_stops_after_real_approval() -> None:
    control = Control(
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
    assert not _reminder_due(replace(control, mutation_pending=True), timer)
    assert not _reminder_due(replace(control, distinct_reviewer_approved=True), timer)


def test_dashboard_format_upgrade_requests_one_fresh_projection() -> None:
    old = Control("repo", 7, 1, "head", "base", True, True, dashboard_current=True)
    assert _request_dashboard(old)
    assert not _request_dashboard(replace(old, dashboard_format=DASHBOARD_FORMAT))


def test_quiescent_control_projects_one_priority_ordered_external_wait() -> None:
    ready_control = Control(
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
    assert workflow_wait(replace(ready_control, mutation_pending=True)) == "mutation confirmation"
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
        asdict(
            ReviewResult(
                1,
                "h1",
                "blocking",
                [{"id": "old", "blocking": True}],
                [],
                work_input(review_invocation).operation,
            )
        ),
    )
    drive_bounded(subject)
    control = values(subject, "current")[0]
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
                result = EffectResult(
                    invocation.activity.removesuffix("_publish"), work.epoch, work.head, True, operation=work.operation
                )
            dispatch.complete(occurrence, asdict(result))
    assert values(subject, "terminal")[0]["status"] == "abort" and not values(subject, "review_result")


def test_late_authorized_change_cannot_make_a_superseding_head_provisional() -> None:
    @activity(name="conversation", converter=DataclassPayloadConverter())
    def change_intent(work: Work) -> IntentBatch:
        intent = Intent(
            work.epoch,
            work.head,
            "change",
            "authorized",
            True,
            False,
            True,
            base_head=str(work.payload["base_head"]),
            policy_digest=str(work.payload["policy_digest"]),
        )
        return IntentBatch(work.epoch, work.head, [asdict(intent)])

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
            [asdict(Intent(1, "h1", "change", "authorized", True, False, True, base_head="base"))],
        ),
    )
    drive_bounded(subject)
    assert values(subject, "current")[0]["mutation_pending"] is True
    subject.deliver(
        "conversation_observation",
        token(ConversationObservation(1, "h1", True, "confirm")),
        identity="confirm-change",
    )
    drive_until_activity(subject, dispatch, "conversation")
    complete(
        dispatch,
        "conversation",
        IntentBatch(
            1,
            "h1",
            [asdict(Intent(1, "h1", "change", "authorized", True, True, True, base_head="base"))],
        ),
    )
    drive_bounded(subject)
    occurrence, invocation = pending(dispatch, "change")
    subject.deliver("verified_admission", token(Admission("repo", 7, "human-head", "base", True)), identity="human")
    drive_bounded(subject)
    dispatch.complete(
        occurrence,
        asdict(
            EffectResult(
                "change", 1, "h1", True, provisional_head="agent-head", operation=work_input(invocation).operation
            )
        ),
    )
    drive_bounded(subject)
    control = values(subject, "current")[0]
    assert (control["head"], control["provisional"], control["provisional_head"]) == ("human-head", False, "")


def test_repair_budget_survives_provisional_admission_and_blocks_same_fingerprint() -> None:
    subject, dispatch = asynchronous_engine()
    subject.deliver("verified_admission", token(Admission("repo", 7, "h1", "base", True)), identity="a1")
    drive_bounded(subject)
    dashboard_occurrence, dashboard_invocation = drive_until_activity(subject, dispatch, "dashboard_publish")
    dashboard_work = work_input(dashboard_invocation)
    dispatch.complete(
        dashboard_occurrence,
        asdict(EffectResult("dashboard", 1, "h1", True, operation=dashboard_work.operation)),
    )
    drive_bounded(subject)
    first = observed_actions(subject, "external", 1, "failure", "fp", observation="failure-1")
    subject.deliver("actions_observation", token(first), identity="failure")
    drive_bounded(subject)
    rerun_occurrence, rerun_invocation = drive_until_activity(subject, dispatch, "actions_rerun")
    second = action_result(work_input(rerun_invocation), "rerun", 2, "failure", "fp", observation="failure-2")
    dispatch.complete(rerun_occurrence, asdict(second))
    drive_bounded(subject)
    repair_occurrence, repair_invocation = pending(dispatch, "repair")
    dispatch.complete(
        repair_occurrence,
        asdict(
            EffectResult(
                "repair",
                1,
                "h1",
                True,
                provisional_head="h2",
                fingerprint="fp",
                operation=work_input(repair_invocation).operation,
            )
        ),
    )
    drive_bounded(subject)
    assert values(subject, "current")[0]["provisional_head"] == "h2"
    subject.deliver("verified_admission", token(Admission("repo", 7, "h2", "base", True)), identity="confirm")
    drive_bounded(subject)
    assert values(subject, "current")[0]["repair_used"] is True
    for _ in range(20):
        control = values(subject, "current")[0]
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
                result = EffectResult(
                    invocation.activity.removesuffix("_publish"), work.epoch, work.head, True, operation=work.operation
                )
            dispatch.complete(occurrence, asdict(result))
    else:
        raise AssertionError("new generation did not finish initial review and discovery")
    for dashboard_occurrence, dashboard_invocation in pending_all(dispatch, "dashboard_publish"):
        dashboard_work = work_input(dashboard_invocation)
        dispatch.complete(
            dashboard_occurrence,
            asdict(EffectResult("dashboard", 2, "h2", True, operation=dashboard_work.operation)),
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
        asdict(action_result(work_input(rerun_invocation), "rerun-2", 2, "failure", "fp", observation="new-2")),
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
                result = EffectResult(
                    invocation.activity.removesuffix("_publish"), work.epoch, work.head, True, operation=work.operation
                )
            dispatch.complete(occurrence, asdict(result))
        drive_bounded(subject)
    assert not values(subject, "work.repair") and not values(subject, "actions_basis")
    assert values(subject, "current")[0]["wait"] == "human repair authorization"


def test_activity_topology_has_complete_retirement_and_no_authority_outputs() -> None:
    net = build_net(1).net
    assert all("merge" not in str(transition) for transition in net.transitions)
    authority = {"current", "admission", "terminal"}
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
            assert any(name.startswith("retire.stale_") for name in names)
            assert any(name.startswith("retire.dormant_") for name in names)
            assert any(name.startswith("retire.terminal_") for name in names)
            if result:
                assert any(
                    name in {"accept_review", "accept_actions", "accept_intent", "accept_effect", "unpack_intents"}
                    or name in {"authorize_rerun", "authorize_repair", "authorize_change"}
                    or name.startswith("retire.")
                    and any(word in name for word in ("operation", "duplicate"))
                    for name in names
                )


def test_confirmation_requires_the_exact_pending_intent_and_authority_basis() -> None:
    confirmed = Intent(
        1,
        "h1",
        "change",
        "intent-digest",
        True,
        True,
        True,
        base_head="base-1",
        policy_digest="policy-1",
    )
    no_pending = Control("repo", 7, 1, "h1", "base-1", True, True, "policy-1")
    assert _mutation(no_pending, confirmed) is False

    pending = Control(
        "repo",
        7,
        1,
        "h1",
        "base-1",
        True,
        True,
        "policy-1",
        mutation_pending=True,
        pending_intent_digest="intent-digest",
    )
    assert _mutation(pending, confirmed) is True
    stale_basis = Control(
        "repo",
        7,
        1,
        "h1",
        "base-2",
        True,
        True,
        "policy-2",
        mutation_pending=True,
        pending_intent_digest="intent-digest",
    )
    assert _mutation(stale_basis, confirmed) is False


def test_external_second_attempt_is_green_but_only_an_impetus_rerun_is_flaky() -> None:
    control = Control("repo", 7, 1, "h1", "base", True, True, actions_operation="actions")
    external = ActionsObservation(1, "h1", "run", 2, "success", operation="actions")
    assert fold_actions.implementation(control, external).actions == "green"
    rerun = Control(
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
    control = Control(
        "repo",
        7,
        1,
        "h1",
        "base",
        True,
        True,
        dashboard_requested=True,
        dashboard_operation="dashboard",
    )
    result = EffectResult("dashboard", 1, "h1", False, operation="dashboard", capability_available=False)
    blocked = fold_effect.implementation(control, result)
    assert blocked.dashboard_current is False
    assert blocked.dashboard_capability_blocking is True
    assert blocked.wait == "dashboard update capability"


def test_non_capability_conversation_failure_clears_pending_without_retry() -> None:
    work = Work("conversation", 1, "h1", "conversation:1")
    control = Control(
        "repo",
        7,
        1,
        "h1",
        "base",
        True,
        True,
        conversation_pending=asdict(work),
        conversation_attempts=1,
    )

    cleared = fold_effect.implementation(
        control,
        EffectResult("conversation", 1, "h1", False, operation=work.operation),
    )

    assert cleared.conversation_pending == {}
    assert cleared.conversation_attempts == 0
    assert cleared.conversation_capability_blocking is False


def test_readiness_ack_invalidates_dashboard_before_latching_announcement() -> None:
    control = Control(
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
        dashboard_current=True,
        readiness_requested=True,
        readiness_operation="readiness",
    )
    assert ready(control) is False
    acknowledged = fold_effect.implementation(
        control,
        EffectResult("readiness", 1, "h1", True, operation="readiness"),
    )
    assert acknowledged.announced is True
    assert acknowledged.dashboard_current is False


def test_mismatched_subject_admission_cannot_rebind_an_instance() -> None:
    subject = engine()
    admit(subject, "h1", "first")
    deliver(subject, "verified_admission", Admission("other", 99, "h2", "base", True), "misrouted")
    control = values(subject, "current")[0]
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
        asdict(EffectResult("dashboard", 1, "h1", True, operation=work_input(old_invocation).operation)),
    )
    drive_bounded(subject)
    assert values(subject, "current")[0]["dashboard_current"] is False
    current_occurrence, current_invocation = pending(dispatch, "dashboard_publish")
    dispatch.complete(
        current_occurrence,
        asdict(EffectResult("dashboard", 1, "h1", True, operation=work_input(current_invocation).operation)),
    )
    drive_bounded(subject)
    assert values(subject, "current")[0]["dashboard_current"] is True
