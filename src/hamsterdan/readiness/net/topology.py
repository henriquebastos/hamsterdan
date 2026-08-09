"""Executable topology for one PR-readiness Instance.

Every obligation crosses a named Activity transition with an exact request and result contract.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from petrus.impetus.dsl import BuiltNet, NetSpec, arc, direct, petri_guard, petri_handler
from petrus.impetus.petrinet import Delay, Token

from hamsterdan.contracts.readiness import (
    ActionsDiscoveryRequest,
    ActionsObservation,
    ActionsRerunRequest,
    Admission,
    ChangeRequest,
    ChangeResult,
    Control,
    ConversationClassificationRequest,
    ConversationObservation,
    ConversationPublicationRequest,
    ConversationPublicationResult,
    DashboardPublicationRequest,
    DashboardPublicationResult,
    Dormant,
    FindingPublicationRequest,
    FindingPublicationResult,
    HumanObservation,
    Intent,
    IntentBatch,
    Lifecycle,
    ReadinessCommand,
    ReadinessPublicationResult,
    Reminder,
    ReminderPublicationRequest,
    ReminderPublicationResult,
    RepairRequest,
    RepairResult,
    ReviewRequest,
    ReviewResult,
    Seed,
    Terminal,
    update,
    workflow_gates_ready,
)

DASHBOARD_FORMAT = 2
MAX_CONVERSATION_ATTEMPTS = 3
MAX_REVIEW_ATTEMPTS = 3

# Public composition surface: path -> (typed input, typed output).  A host binds
# each path to a same-signature ActivityDefinition with DerivedActivityHandler.
ACTIVITY_TRANSITIONS = {
    "execute.review": (ReviewRequest, ReviewResult),
    "execute.actions_discovery": (ActionsDiscoveryRequest, ActionsObservation),
    "execute.actions_rerun": (ActionsRerunRequest, ActionsObservation),
    "execute.conversation": (ConversationClassificationRequest, IntentBatch),
    "execute.conversation_publish": (ConversationPublicationRequest, ConversationPublicationResult),
    "execute.repair": (RepairRequest, RepairResult),
    "execute.change": (ChangeRequest, ChangeResult),
    "execute.finding_publish": (FindingPublicationRequest, FindingPublicationResult),
    "execute.dashboard_publish": (DashboardPublicationRequest, DashboardPublicationResult),
    "execute.reminder_publish": (ReminderPublicationRequest, ReminderPublicationResult),
    "execute.readiness_publish": (ReadinessCommand, ReadinessPublicationResult),
}


def operation(
    kind: str,
    control: Control,
    *,
    payload: dict | None = None,
    sequence: int = 0,
) -> str:
    """Name one immutable effect/work lease from its complete current basis."""
    value = {
        "kind": kind,
        "repository_id": control.repository_id,
        "pr_number": control.pr_number,
        "epoch": control.epoch,
        "head": control.head,
        "base_head": control.base_head,
        "policy_digest": control.policy_digest,
        "payload": payload or {},
        "sequence": sequence,
    }
    digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"{kind}:{digest}"


def effect_payload(control: Control, payload: dict | None = None) -> dict:
    return {"base_head": control.base_head, "policy_digest": control.policy_digest, **(payload or {})}


def _guard(predicate):
    """Use the advanced guard flavor for identity-polymorphic retirement."""

    def evaluate(binding):
        selections = (*binding.read, *binding.consumed)
        result_types = {
            value.__name__: value
            for value in (
                ConversationPublicationResult,
                RepairResult,
                ChangeResult,
                FindingPublicationResult,
                DashboardPublicationResult,
                ReminderPublicationResult,
                ReadinessPublicationResult,
            )
        }
        values = []
        for _, selected in selections:
            for token in selected:
                value_type = result_types.get(token.color)
                values.append(
                    Control(**token.data)
                    if "revision" in token.data
                    else value_type(**token.data)
                    if value_type is not None
                    else SimpleNamespace(**token.data)
                )
        return predicate(*values)

    return petri_guard(evaluate)


def _control_value(binding, value_type):
    """Read a Control and companion value independent of consume/read arc order."""
    values = [token.data for token in binding.peeked]
    control = next(value for value in values if "revision" in value)
    companion = next(value for value in values if value is not control)
    return Control(**control), value_type(**companion)


def _current(control: Control, value) -> bool:
    if control.epoch != value.epoch or control.head != value.head:
        return False
    base = getattr(value, "base_head", "")
    policy = getattr(value, "policy_digest", "")
    return (not base or base == control.base_head) and (not policy or policy == control.policy_digest)


def _review_matches(control: Control, value: ReviewResult) -> bool:
    return _current(control, value) and value.operation == control.review_operation


def _actions_matches(control: Control, value: ActionsObservation) -> bool:
    return _current(control, value) and value.operation == control.actions_operation


def _new_actions(control: Control, value: ActionsObservation) -> bool:
    return (
        _actions_matches(control, value)
        and value.observation != control.actions_observation
        and value.attempt >= control.attempt
        and not (control.rerun_requested and value.conclusion == "failure" and value.attempt <= control.rerun_attempt)
    )


def _duplicate_actions(control: Control, value: ActionsObservation) -> bool:
    return _current(control, value) and (
        not _actions_matches(control, value)
        or value.observation == control.actions_observation
        or value.attempt < control.attempt
        or control.rerun_requested
        and value.conclusion == "failure"
        and value.attempt <= control.rerun_attempt
    )


def _effect_matches(control: Control, value) -> bool:
    if isinstance(value, ConversationPublicationResult):
        return (
            bool(control.conversation_pending)
            and _current(control, value)
            and value.operation == control.conversation_pending.get("operation")
        )
    if isinstance(value, ReminderPublicationResult):
        return _current(control, value)
    expected = (
        control.dashboard_operation
        if isinstance(value, DashboardPublicationResult)
        else control.finding_operation
        if isinstance(value, FindingPublicationResult)
        else control.mutation_operation
        if isinstance(value, (ChangeResult, RepairResult))
        else control.readiness_operation
        if isinstance(value, ReadinessPublicationResult)
        else None
    )
    return _current(control, value) and expected is not None and value.operation == expected


def _stale(control: Control, value) -> bool:
    return not _current(control, value)


def _subject(prior, admission: Admission) -> bool:
    return (prior.repository_id, prior.pr_number) == (admission.repository_id, admission.pr_number)


def _different(control: Control, admission: Admission) -> bool:
    return _subject(control, admission) and control.head != admission.head


def _same(control: Control, admission: Admission) -> bool:
    return _subject(control, admission) and control.head == admission.head


def _same_basis(control: Control, admission: Admission) -> bool:
    return _same(control, admission) and (
        control.base_head,
        control.strict_base,
        control.policy_digest,
    ) == (admission.base_head, admission.strict_base, admission.policy_digest)


def _changed_basis(control: Control, admission: Admission) -> bool:
    return _same(control, admission) and not _same_basis(control, admission)


def _retryable_review(control: Control, admission: Admission) -> bool:
    return (
        _same_basis(control, admission)
        and control.review == "unable"
        and max(control.review_attempts, 1) < MAX_REVIEW_ATTEMPTS
    )


def _refreshable_admission(control: Control, admission: Admission) -> bool:
    return _same_basis(control, admission) and not _retryable_review(control, admission)


def _admit(binding, outputs):
    values = [token.data for token in binding.tokens]
    raw = next(value for value in values if "base_head" in value and "epoch" not in value)
    prior = next(value for value in values if value is not raw)
    epoch = prior.get("epoch", prior.get("last_epoch", 0)) + 1
    admission = Admission(**raw)
    confirms = isinstance(prior, dict) and admission.head == prior.get("provisional_head")
    control = Control(
        repository_id=admission.repository_id,
        pr_number=admission.pr_number,
        epoch=epoch,
        head=admission.head,
        base_head=admission.base_head,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy_digest=admission.policy_digest,
        required_checks=admission.required_checks,
        required_approvals=admission.required_approvals,
        conversation_resolution=admission.conversation_resolution,
        admission_relation="confirmed" if confirms else "superseded" if prior.get("epoch") else "new",
        repair_used=prior.get("repair_used", False) if confirms else False,
        repair_fingerprint=prior.get("repair_fingerprint", "") if confirms else "",
    )
    review_payload = {
        "base_head": admission.base_head,
        "strict_base": admission.strict_base,
        "base_current": admission.base_current,
        "policy_digest": admission.policy_digest,
        "policy": {
            "strict_base": admission.strict_base,
            "required_checks": admission.required_checks,
            "required_approvals": admission.required_approvals,
            "conversation_resolution": admission.conversation_resolution,
            "digest": admission.policy_digest,
        },
        "prior_findings": prior.get("findings", []),
        "prior_lineage": prior.get("finding_lineage", []),
    }
    review_work = ReviewRequest(
        epoch=epoch,
        head=admission.head,
        operation=operation("review", control, payload=review_payload),
        base_head=admission.base_head,
        policy_digest=admission.policy_digest,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy=review_payload["policy"],
        prior_findings=prior.get("findings", []),
        prior_lineage=prior.get("finding_lineage", []),
    )
    actions_payload = {
        "base_head": admission.base_head,
        "policy_digest": admission.policy_digest,
    }
    actions_work = ActionsDiscoveryRequest(
        epoch=epoch,
        head=admission.head,
        operation=operation("actions_discovery", control, payload=actions_payload),
        **actions_payload,
    )
    control = update(
        control,
        review_operation=review_work.operation,
        review_attempts=1,
        actions_operation=actions_work.operation,
    )
    routed = {}
    for output in outputs:
        target = str(output.target)
        if target == "current":
            value = control
        elif target == "reminder.timer":
            value = Reminder(epoch, admission.head)
        else:
            value = review_work if target == "work.review" else actions_work
        routed[output.target] = (Token(output.color, (value).dump()),)
    return routed


@direct
def refresh_admission(control: Control, admission: Admission) -> Control:
    return update(
        control,
        base_head=admission.base_head,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy_digest=admission.policy_digest,
        required_checks=admission.required_checks,
        required_approvals=admission.required_approvals,
        conversation_resolution=admission.conversation_resolution,
        admission_relation="same_head",
    )


def _retry_review(binding, outputs):
    control, admission = _control_value(binding, Admission)
    # Histories written before review attempts were recorded deserialize as zero;
    # an unable result proves that generation has already spent its first attempt.
    attempt = max(control.review_attempts, 1) + 1
    payload = effect_payload(
        control,
        {
            "strict_base": admission.strict_base,
            "base_current": admission.base_current,
            "prior_findings": control.findings,
            "prior_lineage": control.finding_lineage,
            "policy": {
                "strict_base": admission.strict_base,
                "required_checks": admission.required_checks,
                "required_approvals": admission.required_approvals,
                "conversation_resolution": admission.conversation_resolution,
                "digest": admission.policy_digest,
            },
            "review_attempt": attempt,
        },
    )
    work = ReviewRequest(
        epoch=control.epoch,
        head=control.head,
        operation=operation("review", control, payload=payload, sequence=attempt),
        sequence=attempt,
        base_head=control.base_head,
        policy_digest=control.policy_digest,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy=payload["policy"],
        prior_findings=control.findings,
        prior_lineage=control.finding_lineage,
        review_attempt=attempt,
    )
    changed = update(
        control,
        base_head=admission.base_head,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy_digest=admission.policy_digest,
        required_checks=admission.required_checks,
        required_approvals=admission.required_approvals,
        conversation_resolution=admission.conversation_resolution,
        admission_relation="same_head",
        review="pending",
        review_attempts=attempt,
        review_operation=work.operation,
    )
    return {
        outputs[0].target: (Token(outputs[0].color, (changed).dump()),),
        outputs[1].target: (Token(outputs[1].color, (work).dump()),),
    }


def _refresh_basis(binding, outputs):
    control, admission = _control_value(binding, Admission)
    changed = update(
        control,
        base_head=admission.base_head,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy_digest=admission.policy_digest,
        required_checks=admission.required_checks,
        required_approvals=admission.required_approvals,
        conversation_resolution=admission.conversation_resolution,
        admission_relation="same_head_basis_changed",
        actions="discovering",
        run_id="",
        attempt=0,
        rerun_requested=False,
        rerun_attempt=0,
        fingerprint="",
        actions_observation="",
        review="pending",
        review_attempts=1,
        findings_published=False,
        finding_publication_requested=False,
        announced=False,
        readiness_operation="",
        readiness_requested=False,
        wait="actions and coordinating review after authority change",
    )
    review_payload = effect_payload(
        changed,
        {
            "strict_base": admission.strict_base,
            "base_current": admission.base_current,
            "prior_findings": control.findings,
            "prior_lineage": control.finding_lineage,
            "policy": {
                "strict_base": admission.strict_base,
                "required_checks": admission.required_checks,
                "required_approvals": admission.required_approvals,
                "conversation_resolution": admission.conversation_resolution,
                "digest": admission.policy_digest,
            },
        },
    )
    review = ReviewRequest(
        epoch=changed.epoch,
        head=changed.head,
        operation=operation("review", changed, payload=review_payload),
        base_head=changed.base_head,
        policy_digest=changed.policy_digest,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy=review_payload["policy"],
        prior_findings=control.findings,
        prior_lineage=control.finding_lineage,
    )
    actions_payload = effect_payload(changed)
    actions = ActionsDiscoveryRequest(
        epoch=changed.epoch,
        head=changed.head,
        operation=operation("actions_discovery", changed, payload=actions_payload),
        **actions_payload,
    )
    changed = update(
        changed,
        review_operation=review.operation,
        actions_operation=actions.operation,
    )
    routed = {}
    for output in outputs:
        value = (
            changed if str(output.target) == "current" else review if str(output.target) == "work.review" else actions
        )
        routed[output.target] = (Token(output.color, (value).dump()),)
    return routed


@direct
def fold_review(control: Control, result: ReviewResult) -> Control:
    dispositions = {item.get("finding_id"): item.get("state") for item in result.lineage}
    findings = [
        {**finding, "disposition": dispositions.get(finding.get("id"), finding.get("disposition", "new"))}
        for finding in result.findings
    ]
    open_findings = [finding for finding in findings if finding.get("disposition") in {"new", "still_open"}]
    blocking = any(finding.get("blocking") for finding in open_findings)
    return update(
        control,
        review="blocking" if blocking else "clear" if result.status != "unable" else "unable",
        findings=findings,
        finding_lineage=result.lineage,
        findings_published=not open_findings,
        finding_publication_requested=bool(open_findings),
    )


def _accept_review(binding, outputs):
    control, result = _control_value(binding, ReviewResult)
    folded = fold_review.implementation(control, result)
    routed = {outputs[0].target: (Token(outputs[0].color, (folded).dump()),)}
    publishable = [finding for finding in folded.findings if finding.get("disposition") in {"new", "still_open"}]
    if publishable:
        out = outputs[1]
        payload = effect_payload(folded, {"findings": publishable, "lineage": result.lineage})
        work = FindingPublicationRequest(
            epoch=control.epoch,
            head=control.head,
            operation=operation("finding", folded, payload=payload),
            findings=publishable,
            lineage=result.lineage,
            base_head=folded.base_head,
            policy_digest=folded.policy_digest,
        )
        folded = update(folded, finding_operation=work.operation)
        routed[outputs[0].target] = (Token(outputs[0].color, (folded).dump()),)
        routed[out.target] = (Token(out.color, (work).dump()),)
    return routed


@direct
def fold_actions(control: Control, value: ActionsObservation) -> Control:
    if not value.capability_available:
        return update(
            control,
            actions="capability_unavailable",
            actions_capability_blocking=True,
            actions_observation=value.observation,
            wait="Actions capability",
        )
    if value.conclusion in {"queued", "requested", "waiting", "in_progress"}:
        return update(
            control,
            actions="running" if value.conclusion == "in_progress" else "waiting",
            run_id=value.run_id,
            attempt=value.attempt,
            actions_observation=value.observation,
            actions_capability_blocking=False,
            wait="GitHub Actions",
        )
    if value.conclusion == "success":
        return update(
            control,
            actions="flaky_green" if value.attempt > 1 and control.rerun_requested else "green",
            run_id=value.run_id,
            attempt=value.attempt,
            actions_observation=value.observation,
            repair_in_flight=False,
            actions_capability_blocking=False,
        )
    if value.conclusion != "failure":
        return update(
            control,
            actions=value.conclusion,
            run_id=value.run_id,
            attempt=value.attempt,
            actions_observation=value.observation,
            wait=f"Actions {value.conclusion}",
        )
    repeated_same_fingerprint = value.attempt > 1 and value.fingerprint == control.repair_fingerprint
    state = "reproduced" if control.rerun_requested else "failed"
    wait = (
        "same-head rerun"
        if not control.rerun_requested
        else "human repair authorization"
        if repeated_same_fingerprint or control.repair_used
        else "repair"
    )
    return update(
        control,
        actions=state,
        run_id=value.run_id,
        attempt=value.attempt,
        fingerprint=value.fingerprint,
        actions_observation=value.observation,
        repair_in_flight=False,
        actions_capability_blocking=False,
        wait=wait,
    )


@direct
def fold_human(control: Control, value: HumanObservation) -> Control:
    return update(
        control,
        human_requested=value.requested,
        human_approved=value.approved,
        changes_requested=value.changes_requested,
        unresolved_conversations=value.unresolved_conversations,
        distinct_reviewer_required=value.distinct_required,
        distinct_reviewer_approved=value.distinct_approved,
        mergeable=value.mergeable,
        conflict=value.conflict,
        base_current=value.base_current,
        reminder_recipient=value.reviewer,
        author=value.author,
        human_capability_blocking=not value.capability_available,
    )


@direct
def fold_intent(control: Control, value: Intent) -> Control:
    if not value.authorized:
        return control
    if value.kind in {"acknowledge", "dismiss", "defer"}:
        selected = set(value.arguments.get("findings", []))
        findings = [
            {**finding, "disposition": value.kind} if finding.get("id") in selected else finding
            for finding in control.findings
        ]
        open_blocker = any(
            finding.get("blocking") and finding.get("disposition") in {"new", "still_open"} for finding in findings
        )
        review = "blocking" if open_blocker else "clear" if control.review in {"blocking", "clear"} else control.review
        return update(control, findings=findings, review=review)
    if value.kind == "snooze":
        return update(control, reminder_snoozed=True, wait="reminder snoozed")
    if value.kind == "resume":
        return update(
            control,
            reminder_snoozed=False,
            wait="conflict resolution" if control.conflict else "human review",
        )
    if value.kind == "reassign":
        assignee = value.arguments.get("assignee", "")
        return update(
            control,
            reminder_recipient=assignee,
            wait="conflict resolution" if control.conflict else f"human review assigned to {assignee}",
        )
    mutation = value.blocking and value.kind in {"change", "update_base", "resolve_conflict"}
    if not mutation:
        return control
    # Mutation work is authorized from the parallel intent basis in this same
    # cycle. Control remains unchanged here; there is no staged confirmation.
    return control


def fold_effect(control: Control, result) -> Control:
    if isinstance(result, ConversationPublicationResult) and result.ok:
        return update(
            control,
            conversation_pending={},
            conversation_attempts=0,
            conversation_capability_blocking=False,
        )
    if isinstance(result, ConversationPublicationResult) and not result.capability_available:
        return update(control, conversation_capability_blocking=True, wait="conversation reply capability")
    if isinstance(result, ConversationPublicationResult):
        return update(
            control,
            conversation_pending={},
            conversation_attempts=0,
            conversation_capability_blocking=False,
        )
    if isinstance(result, (ChangeResult, RepairResult)):
        repair = isinstance(result, RepairResult)
        if result.ok:
            return update(
                control,
                provisional=True,
                provisional_head=result.provisional_head,
                change_in_flight=False,
                repair_in_flight=False,
                repair_recovery_required=False,
                repair_used=control.repair_used or repair,
                repair_fingerprint=result.fingerprint or control.fingerprint if repair else control.repair_fingerprint,
                repair_lineage=result.lineage or control.repair_lineage,
                wait="verified head admission",
            )
        return update(
            control,
            change_in_flight=False,
            repair_in_flight=False,
            repair_recovery_required=repair,
            repair_used=control.repair_used or repair,
            repair_fingerprint=(result.fingerprint or control.fingerprint) if repair else control.repair_fingerprint,
            repair_lineage=result.lineage or control.repair_lineage,
            wait=f"{'repair' if repair else 'change'} recovery",
        )
    if isinstance(result, FindingPublicationResult) and result.ok:
        references = {item.get("finding_id"): item.get("url", "") for item in result.references}
        findings = [
            {**finding, "comment_url": references.get(finding.get("id"), finding.get("comment_url", ""))}
            for finding in control.findings
        ]
        return update(
            control,
            findings=findings,
            findings_published=True,
            finding_publication_requested=False,
            finding_operation="",
            finding_capability_blocking=False,
        )
    if isinstance(result, FindingPublicationResult) and not result.capability_available:
        return update(control, finding_capability_blocking=True, wait="finding publication capability")
    if isinstance(result, DashboardPublicationResult) and result.ok:
        return update(
            control,
            preserve_dashboard_request=True,
            revision=control.revision,
            dashboard_current=True,
            dashboard_requested=False,
            dashboard_operation="",
            dashboard_format=DASHBOARD_FORMAT,
            dashboard_capability_blocking=False,
        )
    if isinstance(result, DashboardPublicationResult) and not result.capability_available:
        return update(
            control,
            preserve_dashboard_request=True,
            dashboard_capability_blocking=True,
            wait="dashboard update capability",
        )
    if isinstance(result, ReadinessPublicationResult) and not result.capability_available:
        return update(control, readiness_capability_blocking=True, wait="readiness publication capability")
    if isinstance(result, ReadinessPublicationResult) and result.ok:
        return update(
            control,
            readiness_requested=False,
            announced=True,
            readiness_capability_blocking=False,
            wait="terminal lifecycle",
        )
    # Reminder and readiness acknowledgements are audit facts, not gate changes.
    return control


@direct
def fold_conversation_effect(control: Control, result: ConversationPublicationResult) -> Control:
    return fold_effect(control, result)


@direct
def fold_repair_effect(control: Control, result: RepairResult) -> Control:
    return fold_effect(control, result)


@direct
def fold_change_effect(control: Control, result: ChangeResult) -> Control:
    return fold_effect(control, result)


@direct
def fold_finding_effect(control: Control, result: FindingPublicationResult) -> Control:
    return fold_effect(control, result)


@direct
def fold_dashboard_effect(control: Control, result: DashboardPublicationResult) -> Control:
    return fold_effect(control, result)


@direct
def fold_reminder_effect(control: Control, result: ReminderPublicationResult) -> Control:
    return fold_effect(control, result)


@direct
def fold_readiness_effect(control: Control, result: ReadinessPublicationResult) -> Control:
    return fold_effect(control, result)


def _first_failure(c: Control, value: ActionsObservation) -> bool:
    return (
        _current(c, value)
        and c.actions == "failed"
        and not c.rerun_requested
        and c.actions_observation == value.observation
        and value.conclusion == "failure"
        and not any((c.provisional, c.change_in_flight, c.repair_in_flight))
    )


def _repairable(c: Control, value: ActionsObservation) -> bool:
    return (
        _current(c, value)
        and value.conclusion == "failure"
        and c.rerun_requested
        and value.attempt > c.rerun_attempt
        and not c.repair_used
        and not c.provisional
        and not c.change_in_flight
        and not c.repair_in_flight
        and c.actions == "reproduced"
        and c.actions_observation == value.observation
        and value.fingerprint != c.repair_fingerprint
    )


def _basis_done(c: Control, value: ActionsObservation) -> bool:
    if _stale(c, value) or not _actions_matches(c, value) or value.attempt < c.attempt:
        return True
    if c.rerun_requested and value.conclusion == "failure" and value.attempt <= c.rerun_attempt:
        return True
    if c.actions_observation != value.observation:
        return False
    if value.conclusion != "failure":
        return True
    if not c.rerun_requested:
        return False
    return c.repair_in_flight or c.repair_used or value.fingerprint == c.repair_fingerprint


@direct
def rerun_work(c: Control, value: ActionsObservation) -> ActionsRerunRequest:
    payload = effect_payload(c, {"actions": value.dump()})
    return ActionsRerunRequest(
        epoch=value.epoch,
        head=value.head,
        operation=operation("actions-rerun", c, payload=payload),
        base_head=c.base_head,
        policy_digest=c.policy_digest,
        actions=value,
    )


def _rerun(binding, outputs):
    c, value = _control_value(binding, ActionsObservation)
    payload = effect_payload(c, {"actions": (value).dump()})
    work = ActionsRerunRequest(
        epoch=value.epoch,
        head=value.head,
        operation=operation("actions-rerun", c, payload=payload),
        base_head=c.base_head,
        policy_digest=c.policy_digest,
        actions=value,
    )
    changed = update(
        c,
        actions="rerun_requested",
        rerun_requested=True,
        rerun_attempt=c.attempt,
        actions_operation=work.operation,
        wait="same-head rerun",
    )
    return {
        outputs[0].target: (Token(outputs[0].color, (changed).dump()),),
        outputs[1].target: (Token(outputs[1].color, (work).dump()),),
    }


def _repair(binding, outputs):
    c, value = _control_value(binding, ActionsObservation)
    payload = effect_payload(c, {"actions": (value).dump()})
    operation_id = operation("repair", c, payload=payload)
    changed = update(c, repair_in_flight=True, mutation_operation=operation_id, wait="repair")
    return {
        outputs[0].target: (Token(outputs[0].color, (changed).dump()),),
        outputs[1].target: (
            Token(
                outputs[1].color,
                RepairRequest(
                    epoch=value.epoch,
                    head=value.head,
                    operation=operation_id,
                    base_head=c.base_head,
                    policy_digest=c.policy_digest,
                    actions=value,
                ).dump(),
            ),
        ),
    }


def _mutation(c: Control, value: Intent) -> bool:
    return (
        _current(c, value)
        and value.authorized
        and value.blocking
        and value.kind in {"change", "update_base", "resolve_conflict"}
        and not any((c.provisional, c.change_in_flight, c.repair_in_flight))
    )


def _authorize_change(binding, outputs):
    c, value = _control_value(binding, Intent)
    payload = effect_payload(c, {"intent": (value).dump()})
    operation_id = operation("change", c, payload=payload)
    changed = update(
        c,
        change_in_flight=True,
        mutation_operation=operation_id,
        wait="change",
    )
    return {
        outputs[0].target: (Token(outputs[0].color, (changed).dump()),),
        outputs[1].target: (
            Token(
                outputs[1].color,
                ChangeRequest(
                    epoch=value.epoch,
                    head=value.head,
                    operation=operation_id,
                    base_head=c.base_head,
                    policy_digest=c.policy_digest,
                    intent=value,
                ).dump(),
            ),
        ),
    }


def _replyable(c: Control, value: Intent) -> bool:
    return _current(c, value) and value.authorized and value.kind == "reply" and bool(value.arguments.get("message"))


def _authorize_reply(binding, outputs):
    c, value = _control_value(binding, Intent)
    payload = effect_payload(c, {"intent": (value).dump()})
    work = ConversationPublicationRequest(
        epoch=value.epoch,
        head=value.head,
        operation=operation("conversation-reply", c, payload=payload),
        base_head=c.base_head,
        policy_digest=c.policy_digest,
        intent=value,
    )
    changed = update(
        c,
        conversation_pending=(work).dump(),
        conversation_attempts=1,
        conversation_capability_blocking=False,
    )
    return {
        outputs[0].target: (Token(outputs[0].color, (changed).dump()),),
        outputs[1].target: (Token(outputs[1].color, (work).dump()),),
    }


def _retry_reply(c: Control) -> bool:
    return (
        c.conversation_capability_blocking
        and bool(c.conversation_pending)
        and c.conversation_attempts < MAX_CONVERSATION_ATTEMPTS
    )


def _reissue_reply(binding, outputs):
    c = Control(**binding.tokens[0].data)
    pending = dict(c.conversation_pending)
    pending["intent"] = Intent(**pending["intent"])
    work = ConversationPublicationRequest(**pending)
    changed = update(
        c,
        conversation_attempts=c.conversation_attempts + 1,
        conversation_capability_blocking=False,
        wait="conversation reply",
    )
    return {
        outputs[0].target: (Token(outputs[0].color, (changed).dump()),),
        outputs[1].target: (Token(outputs[1].color, (work).dump()),),
    }


def _conversation(c: Control, value: ConversationObservation) -> bool:
    return _current(c, value) and value.authorized


def _unpack_intents(binding, outputs):
    raw = binding.tokens[0].data
    batch = IntentBatch(raw["epoch"], raw["head"], [Intent(**item) for item in raw["intents"]])
    return {output.target: tuple(Token(output.color, item.dump()) for item in batch.intents) for output in outputs}


@direct
def conversation_work(c: Control, value: ConversationObservation) -> ConversationClassificationRequest:
    payload = effect_payload(c, {"comment": (value).dump(), "control": (c).dump()})
    return ConversationClassificationRequest(
        epoch=value.epoch,
        head=value.head,
        operation=operation("conversation", c, payload=payload),
        base_head=c.base_head,
        policy_digest=c.policy_digest,
        comment=value,
        control=c,
    )


def ready(c: Control) -> bool:
    return all(
        (
            workflow_gates_ready(c),
            c.dashboard_current,
            not c.readiness_requested,
            not c.announced,
        )
    )


def _request_dashboard(c: Control) -> bool:
    return (not c.dashboard_current or c.dashboard_format < DASHBOARD_FORMAT) and not c.dashboard_requested


def _dashboard(binding, outputs):
    c = Control(**binding.tokens[0].data)
    payload = effect_payload(c, {"control": (c).dump(), "projected_revision": c.revision + 1})
    operation_id = operation("dashboard", c, payload=payload)
    changed = update(c, preserve_dashboard_request=True, dashboard_requested=True, dashboard_operation=operation_id)
    return {
        outputs[0].target: (Token(outputs[0].color, (changed).dump()),),
        outputs[1].target: (
            Token(
                outputs[1].color,
                (
                    DashboardPublicationRequest(
                        epoch=c.epoch,
                        head=c.head,
                        operation=operation_id,
                        base_head=changed.base_head,
                        policy_digest=changed.policy_digest,
                        control=changed,
                    )
                ).dump(),
            ),
        ),
    }


def _announce(binding, outputs):
    c = Control(**binding.tokens[0].data)
    operation_id = operation("readiness", c, payload={"revision": c.revision})
    changed = update(
        c,
        preserve_dashboard_request=True,
        revision=c.revision,
        dashboard_current=c.dashboard_current,
        readiness_requested=True,
        readiness_operation=operation_id,
        wait="readiness publication",
    )
    return {
        outputs[0].target: (Token(outputs[0].color, (changed).dump()),),
        outputs[1].target: (
            Token(
                outputs[1].color,
                (
                    ReadinessCommand(
                        epoch=c.epoch,
                        head=c.head,
                        operation=operation_id,
                        base_head=c.base_head,
                        policy_digest=c.policy_digest,
                    )
                ).dump(),
            ),
        ),
    }


@direct
def to_dormant(c: Control, lifecycle: Lifecycle) -> Dormant:
    return Dormant(c.repository_id, c.pr_number, c.epoch, lifecycle.head)


@direct
def terminate_active(c: Control, lifecycle: Lifecycle) -> Terminal:
    return Terminal("success" if lifecycle.status == "merged" else "abort", c.epoch, lifecycle.head)


@direct
def terminate_dormant(c: Dormant, lifecycle: Lifecycle) -> Terminal:
    return Terminal("success" if lifecycle.status == "merged" else "abort", c.last_epoch, lifecycle.head)


def _draft(c, lifecycle):
    del c
    return lifecycle.status == "draft"


def _terminal(c, lifecycle):
    del c
    return lifecycle.status in {"merged", "closed"}


def _irrelevant(c, lifecycle):
    del c
    return lifecycle.status not in {"draft", "merged", "closed"}


def _reminder_due(c: Control, timer: Reminder) -> bool:
    busy = c.actions not in {"green", "flaky_green"} or c.review != "clear"
    review_satisfied = c.human_approved and (
        bool(c.reminder_recipient) or c.distinct_reviewer_approved or c.human_requested
    )
    return (
        _current(c, timer)
        and not c.reminder_snoozed
        and not review_satisfied
        and not c.changes_requested
        and c.dashboard_current
        and not any(
            (
                busy,
                c.provisional,
                c.change_in_flight,
                c.repair_in_flight,
                c.conflict,
            )
        )
    )


def _timer_stale(c: Control, timer: Reminder) -> bool:
    return _stale(c, timer)


def _remind(binding, outputs):
    values = [token.data for token in binding.peeked]
    timer = Reminder(**next(value for value in values if "sequence" in value))
    control = Control(**next(value for value in values if "repository_id" in value))
    nxt = Reminder(timer.epoch, timer.head, timer.sequence + 1)
    payload = effect_payload(
        control,
        {
            "sequence": timer.sequence,
            "reviewer": control.reminder_recipient,
            "author": control.author,
        },
    )
    work = ReminderPublicationRequest(
        epoch=timer.epoch,
        head=timer.head,
        operation=operation("reminder", control, payload=payload, sequence=timer.sequence),
        base_head=control.base_head,
        policy_digest=control.policy_digest,
        sequence=timer.sequence,
        reviewer=control.reminder_recipient,
        author=control.author,
    )
    return {
        outputs[0].target: (Token(outputs[0].color, (nxt).dump()),),
        outputs[1].target: (Token(outputs[1].color, (work).dump()),),
    }


@direct
def _rearm(timer: Reminder) -> Reminder:
    return timer


def build_net(reminder_delay: float = 3 * 24 * 60 * 60) -> BuiltNet:
    net = NetSpec("pr-readiness-next")
    p, t = net.p, net.t
    work, execute, retire, admit = net.s.work, net.s.execute, net.s.retire, net.s.admit
    reminder, command = net.s.reminder, net.s.command
    t.verified_admission >> p.admission(Admission)
    t.lifecycle_observation >> p.lifecycle(Lifecycle)
    t.human_observation >> p.human_result(HumanObservation)
    t.actions_observation >> (p.actions_result(ActionsObservation), p.actions_basis(ActionsObservation))
    t.conversation_observation >> p.conversation_basis(ConversationObservation)

    # Named Activity transitions. No result place is an ingress/source.
    work.p.review(ReviewRequest) >> execute.t.review(handler="review") >> p.review_result(ReviewResult)
    (
        work.p.actions_discovery(ActionsDiscoveryRequest)
        >> execute.t.actions_discovery(handler="actions_discovery")
        >> (p.actions_result(ActionsObservation), p.actions_basis(ActionsObservation))
    )
    (
        work.p.actions_rerun(ActionsRerunRequest)
        >> execute.t.actions_rerun(handler="actions_rerun")
        >> (p.actions_result, p.actions_basis)
    )
    (
        work.p.conversation(ConversationClassificationRequest)
        >> execute.t.conversation(handler="conversation")
        >> p.intent_batch(IntentBatch)
    )
    (
        work.p.conversation_reply(ConversationPublicationRequest)
        >> execute.t.conversation_publish(handler="conversation_publish")
        >> p.conversation_result(ConversationPublicationResult)
    )
    work.p.repair(RepairRequest) >> execute.t.repair(handler="repair") >> p.repair_result(RepairResult)
    work.p.change(ChangeRequest) >> execute.t.change(handler="change") >> p.change_result(ChangeResult)
    (
        work.p.finding(FindingPublicationRequest)
        >> execute.t.finding_publish(handler="finding_publish")
        >> p.finding_result(FindingPublicationResult)
    )
    (
        work.p.dashboard(DashboardPublicationRequest)
        >> execute.t.dashboard_publish(handler="dashboard_publish")
        >> p.dashboard_result(DashboardPublicationResult)
    )
    (
        work.p.reminder(ReminderPublicationRequest)
        >> execute.t.reminder_publish(handler="reminder_publish")
        >> p.reminder_result(ReminderPublicationResult)
    )
    (
        command.p.readiness(ReadinessCommand)
        >> execute.t.readiness_publish(handler="readiness_publish")
        >> p.readiness_result(ReadinessPublicationResult)
    )

    # Admission is atomic; same-head verification refreshes mutable base facts.
    for name, prior, guard in (
        ("initial", p.seed(Seed), _subject),
        ("supersede", p.current(Control), _different),
        ("resume", p.dormant(Dormant), _subject),
    ):
        options = {"handler": petri_handler(_admit), "guards": _guard(guard)}
        tr = getattr(admit.t, name)(**options)
        (prior, p.admission) >> tr >> (p.current, work.p.review, work.p.actions_discovery, reminder.p.timer(Reminder))
    (
        (p.current, p.admission)
        >> t.refresh_basis(handler=petri_handler(_refresh_basis), guards=_guard(_changed_basis))
        >> (p.current, work.p.review, work.p.actions_discovery)
    )
    (
        (p.current, p.admission)
        >> t.retry_review(handler=petri_handler(_retry_review), guards=_guard(_retryable_review))
        >> (p.current, work.p.review)
    )
    (
        (p.current, p.admission)
        >> t.refresh_admission(handler=refresh_admission, guards=_guard(_refreshable_admission))
        >> p.current
    )

    (
        (p.current, p.review_result)
        >> t.accept_review(handler=petri_handler(_accept_review), guards=_guard(_review_matches))
        >> (p.current, work.p.finding)
    )
    (
        (p.current, p.actions_result)
        >> t.accept_actions(
            handler=fold_actions,
            guards=_guard(_new_actions),
        )
        >> p.current
    )
    (p.current, p.human_result) >> t.accept_human(handler=fold_human, guards=_guard(_current)) >> p.current
    (p.current, p.intent_result) >> t.accept_intent(handler=fold_intent, guards=_guard(_current)) >> p.current
    effect_places = (
        p.conversation_result,
        p.repair_result,
        p.change_result,
        p.finding_result,
        p.dashboard_result,
        p.reminder_result,
        p.readiness_result,
    )
    effect_folders = (
        fold_conversation_effect,
        fold_repair_effect,
        fold_change_effect,
        fold_finding_effect,
        fold_dashboard_effect,
        fold_reminder_effect,
        fold_readiness_effect,
    )
    for index, (place, folder) in enumerate(zip(effect_places, effect_folders, strict=True)):
        (
            (p.current, place)
            >> getattr(t, f"accept_effect_{index}")(handler=folder, guards=_guard(_effect_matches))
            >> p.current
        )

    (
        (p.current, p.actions_basis)
        >> t.authorize_rerun(handler=petri_handler(_rerun), guards=_guard(_first_failure))
        >> (p.current, work.p.actions_rerun)
    )
    (
        (p.current, p.actions_basis)
        >> t.authorize_repair(handler=petri_handler(_repair), guards=_guard(_repairable))
        >> (p.current, work.p.repair)
    )
    p.current >> arc.read() >> retire.t.actions_basis(guards=_guard(_basis_done))
    p.actions_basis >> retire.t.actions_basis
    p.current >> arc.read() >> t.start_conversation(handler=conversation_work, guards=_guard(_conversation))
    p.conversation_basis >> t.start_conversation >> work.p.conversation
    (
        p.intent_batch
        >> t.unpack_intents(handler=petri_handler(_unpack_intents))
        >> (
            p.intent_result(Intent),
            p.change_basis(Intent),
            p.reply_basis(Intent),
        )
    )
    p.current >> arc.read() >> retire.t.conversation_basis(guards=_guard(lambda c, x: not _conversation(c, x)))
    p.conversation_basis >> retire.t.conversation_basis
    (
        (p.current, p.change_basis)
        >> t.authorize_change(handler=petri_handler(_authorize_change), guards=_guard(_mutation))
        >> (p.current, work.p.change)
    )
    p.current >> arc.read() >> retire.t.change_basis(guards=_guard(lambda c, x: not _mutation(c, x)))
    p.change_basis >> retire.t.change_basis
    (
        (p.current, p.reply_basis)
        >> t.authorize_reply(handler=petri_handler(_authorize_reply), guards=_guard(_replyable))
        >> (p.current, work.p.conversation_reply)
    )
    p.current >> arc.read() >> retire.t.reply_basis(guards=_guard(lambda c, x: not _replyable(c, x)))
    p.reply_basis >> retire.t.reply_basis
    (
        p.current
        >> t.reissue_reply(handler=petri_handler(_reissue_reply), guards=_guard(_retry_reply))
        >> (p.current, work.p.conversation_reply)
    )

    (p.current, p.lifecycle) >> t.draft(handler=to_dormant, guards=_guard(_draft)) >> p.dormant
    (
        (p.current, p.lifecycle)
        >> t.terminal_active(handler=terminate_active, guards=_guard(_terminal))
        >> p.terminal(Terminal)
    )
    (p.dormant, p.lifecycle) >> t.terminal_dormant(handler=terminate_dormant, guards=_guard(_terminal)) >> p.terminal
    p.current >> arc.read() >> retire.t.lifecycle_active(guards=_guard(_irrelevant))
    p.lifecycle >> retire.t.lifecycle_active
    p.dormant >> arc.read() >> retire.t.lifecycle_dormant(guards=_guard(lambda d, x: not _terminal(d, x)))
    p.lifecycle >> retire.t.lifecycle_dormant

    due = t.reminder_due(handler=petri_handler(_remind), guards=_guard(_reminder_due), timers=(Delay(reminder_delay),))
    p.current >> arc.read() >> due
    reminder.p.timer >> due >> (reminder.p.rearm(Reminder), work.p.reminder)
    reminder.p.rearm >> t.rearm(handler=_rearm) >> reminder.p.timer
    p.current >> arc.read() >> retire.t.timer_stale(guards=_guard(_timer_stale))
    reminder.p.timer >> retire.t.timer_stale

    (
        p.current
        >> t.request_dashboard(handler=petri_handler(_dashboard), guards=_guard(_request_dashboard))
        >> (p.current, work.p.dashboard)
    )
    (
        p.current
        >> t.authorize_readiness(handler=petri_handler(_announce), guards=_guard(ready))
        >> (p.current, command.p.readiness)
    )

    stale_places = (
        p.review_result,
        p.actions_result,
        p.human_result,
        p.intent_result,
        p.intent_batch,
        *effect_places,
        p.actions_basis,
        p.change_basis,
        p.reply_basis,
        p.conversation_basis,
        reminder.p.timer,
        work.p.review,
        work.p.actions_discovery,
        work.p.actions_rerun,
        work.p.conversation,
        work.p.conversation_reply,
        work.p.repair,
        work.p.change,
        work.p.finding,
        work.p.dashboard,
        work.p.reminder,
        command.p.readiness,
    )
    for index, place in enumerate(stale_places):
        tr = getattr(retire.t, f"stale_{index}")(guards=_guard(_stale))
        p.current >> arc.read() >> tr
        place >> tr
        dr = getattr(retire.t, f"dormant_{index}")
        p.dormant >> arc.read() >> dr
        place >> dr
        term = getattr(retire.t, f"terminal_{index}")
        p.terminal >> arc.read() >> term
        place >> term
    # Same-generation duplicate or superseded operation envelopes are stale too.
    for name, place, guard in (
        ("review_operation", p.review_result, lambda c, x: not _review_matches(c, x)),
        (
            "actions_duplicate",
            p.actions_result,
            _duplicate_actions,
        ),
    ):
        tr = getattr(retire.t, name)(guards=_guard(guard))
        p.current >> arc.read() >> tr
        place >> tr
    for index, place in enumerate(effect_places):
        if place == p.reminder_result:
            continue
        tr = getattr(retire.t, f"effect_operation_{index}")(guards=_guard(lambda c, x: not _effect_matches(c, x)))
        p.current >> arc.read() >> tr
        place >> tr
    p.dormant >> arc.read() >> retire.t.dormant_admission(guards=_guard(lambda d, a: not _subject(d, a)))
    p.admission >> retire.t.dormant_admission
    p.seed >> arc.read() >> retire.t.seed_admission(guards=_guard(lambda s, a: not _subject(s, a)))
    p.admission >> retire.t.seed_admission
    p.current >> arc.read() >> retire.t.current_admission(guards=_guard(lambda c, a: not _subject(c, a)))
    p.admission >> retire.t.current_admission
    p.terminal >> arc.read() >> retire.t.terminal_admission
    p.admission >> retire.t.terminal_admission
    # Terminal authority is read-only and absorbs arbitrary late lifecycle/human facts.
    for index, place in enumerate(
        (
            p.lifecycle,
            p.human_result,
            p.conversation_basis,
            p.actions_result,
            p.review_result,
            p.intent_result,
            *effect_places,
        )
    ):
        tr = getattr(retire.t, f"terminal_fact_{index}")
        p.terminal >> arc.read() >> tr
        place >> tr
    return net.build()
