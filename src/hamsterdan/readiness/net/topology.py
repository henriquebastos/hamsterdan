"""Concern-oriented executable topology for one PR-readiness Instance."""

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
    Dormant,
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
    Terminal,
    project_readiness,
    workflow_gates_ready,
)

DASHBOARD_FORMAT = 2
MAX_CONVERSATION_ATTEMPTS = 3
MAX_REVIEW_ATTEMPTS = 3

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

_TOKEN_TYPES = {
    value.__name__: value
    for value in (
        Seed,
        Admission,
        Lifecycle,
        Authority,
        ActionsState,
        ReviewState,
        HumanState,
        MutationState,
        PublicationState,
        ReadinessSnapshot,
        Dormant,
        Terminal,
        ReviewResult,
        ActionsObservation,
        HumanObservation,
        ConversationObservation,
        Intent,
        IntentBatch,
        ConversationPublicationResult,
        RepairResult,
        ChangeResult,
        FindingPublicationResult,
        DashboardPublicationResult,
        ReminderPublicationResult,
        ReadinessPublicationResult,
        Reminder,
        ReviewRequest,
        ActionsDiscoveryRequest,
        ActionsRerunRequest,
        ConversationClassificationRequest,
        ConversationPublicationRequest,
        RepairRequest,
        ChangeRequest,
        FindingPublicationRequest,
        DashboardPublicationRequest,
        ReminderPublicationRequest,
        ReadinessCommand,
    )
}


def operation(kind: str, authority: Authority, *, payload: dict | None = None, sequence: int = 0) -> str:
    """Name one immutable operation from the canonical authority basis."""
    value = {
        "kind": kind,
        "repository_id": authority.repository_id,
        "pr_number": authority.pr_number,
        "epoch": authority.epoch,
        "head": authority.head,
        "base_head": authority.base_head,
        "policy_digest": authority.policy_digest,
        "payload": payload or {},
        "sequence": sequence,
    }
    digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"{kind}:{digest}"


def effect_payload(authority: Authority, payload: dict | None = None) -> dict:
    return {"base_head": authority.base_head, "policy_digest": authority.policy_digest, **(payload or {})}


def _hydrate(binding):
    values = []
    for _, selected in (*binding.read, *binding.consumed):
        for token in selected:
            try:
                values.append(_TOKEN_TYPES[token.color](**token.data))
            except TypeError, ValueError:
                # Retirement needs only envelope identity; nested strict values are
                # deliberately not reconstructed outside their owning handler.
                values.append(SimpleNamespace(**token.data))
    return values


def _guard(predicate):
    return petri_guard(lambda binding: predicate(*_hydrate(binding)))


def _typed_guard(types, predicate):
    def evaluate(*values):
        selected = tuple(next(value for value in values if isinstance(value, kind)) for kind in types)
        return predicate(*selected)

    return _guard(evaluate)


def _values(binding, *types):
    hydrated = _hydrate(binding)
    return tuple(next(value for value in hydrated if isinstance(value, kind)) for kind in types)


def _put(outputs, values):
    return {out.target: (Token(out.color, value.dump()),) for out, value in zip(outputs, values, strict=True)}


def _route(outputs, values):
    """Route heterogeneous optional outputs by their target rather than position."""
    return {
        out.target: (Token(out.color, values[str(out.target)].dump()),) for out in outputs if str(out.target) in values
    }


def _fold_owned(binding, outputs, owner_type, result_type, folder):
    owner, result = _values(binding, owner_type, result_type)
    implementation = getattr(folder, "implementation", folder)
    return _put(outputs, (implementation(owner, result),))


def _current(authority: Authority, value) -> bool:
    if authority.epoch != value.epoch or authority.head != value.head:
        return False
    return (not getattr(value, "base_head", "") or value.base_head == authority.base_head) and (
        not getattr(value, "policy_digest", "") or value.policy_digest == authority.policy_digest
    )


def _invalidate(publication: PublicationState, *, increment: int = 1, **changes) -> PublicationState:
    """Invalidate only publication state, retaining legacy revision/request semantics."""
    changes.setdefault("revision", publication.revision + increment)
    changes.setdefault("dashboard_current", False)
    changes.setdefault("dashboard_requested", False)
    changes.setdefault("dashboard_operation", "")
    return publication.validated_update(**changes)


def _snapshot(a, ac, r, h, m, p):
    return project_readiness(a, ac, r, h, m, p)


def _review_matches(a: Authority, r: ReviewState, value: ReviewResult) -> bool:
    return _current(a, value) and value.operation == r.review_operation


def _actions_matches(a: Authority, s: ActionsState, value: ActionsObservation) -> bool:
    return _current(a, value) and value.operation == s.actions_operation


def _new_actions(a: Authority, s: ActionsState, value: ActionsObservation) -> bool:
    return (
        _actions_matches(a, s, value)
        and value.observation != s.actions_observation
        and value.attempt >= s.attempt
        and not (s.rerun_requested and value.conclusion == "failure" and value.attempt <= s.rerun_attempt)
    )


def _duplicate_actions(a: Authority, s: ActionsState, value: ActionsObservation) -> bool:
    return _current(a, value) and (
        not _actions_matches(a, s, value)
        or value.observation == s.actions_observation
        or value.attempt < s.attempt
        or s.rerun_requested
        and value.conclusion == "failure"
        and value.attempt <= s.rerun_attempt
    )


def _effect_matches(a: Authority, owner, value) -> bool:
    if not _current(a, value):
        return False
    if isinstance(value, ConversationPublicationResult):
        return bool(owner.conversation_pending) and value.operation == owner.conversation_pending.get("operation")
    if isinstance(value, ReminderPublicationResult):
        return True
    field = (
        "mutation_operation"
        if isinstance(value, (ChangeResult, RepairResult))
        else (
            "finding_operation"
            if isinstance(value, FindingPublicationResult)
            else "dashboard_operation"
            if isinstance(value, DashboardPublicationResult)
            else "readiness_operation"
        )
    )
    return value.operation == getattr(owner, field)


@direct
def fold_review(state: ReviewState, result: ReviewResult) -> ReviewState:
    dispositions = {item.get("finding_id"): item.get("state") for item in result.lineage}
    findings = [
        {**f, "disposition": dispositions.get(f.get("id"), f.get("disposition", "new"))} for f in result.findings
    ]
    blocking = any(f.get("blocking") and f.get("disposition") in {"new", "still_open"} for f in findings)
    return state.validated_update(
        review="unable" if result.status == "unable" else "blocking" if blocking else "clear",
        findings=findings,
        finding_lineage=result.lineage,
    )


@direct
def fold_actions(state: ActionsState, value: ActionsObservation) -> ActionsState:
    common = {"run_id": value.run_id, "attempt": value.attempt, "actions_observation": value.observation}
    if not value.capability_available:
        return state.validated_update(actions="capability_unavailable", actions_capability_blocking=True, **common)
    if value.conclusion in {"queued", "requested", "waiting", "in_progress"}:
        return state.validated_update(
            actions="running" if value.conclusion == "in_progress" else "waiting",
            actions_capability_blocking=False,
            **common,
        )
    if value.conclusion == "success":
        return state.validated_update(
            actions="flaky_green" if value.attempt > 1 and state.rerun_requested else "green",
            actions_capability_blocking=False,
            **common,
        )
    if value.conclusion == "failure":
        return state.validated_update(
            actions="reproduced" if state.rerun_requested else "failed",
            fingerprint=value.fingerprint,
            actions_capability_blocking=False,
            **common,
        )
    return state.validated_update(actions=value.conclusion, **common)


@direct
def fold_intent(state, value: Intent):
    if not value.authorized:
        return state
    if isinstance(state, ReviewState) and value.kind in {"acknowledge", "dismiss", "defer"}:
        selected = set(value.arguments.get("findings", []))
        findings = [
            {**finding, "disposition": value.kind} if finding.get("id") in selected else finding
            for finding in state.findings
        ]
        blocked = any(
            finding.get("blocking") and finding.get("disposition") in {"new", "still_open"} for finding in findings
        )
        review = "blocking" if blocked else "clear" if state.review in {"blocking", "clear"} else state.review
        return state.validated_update(findings=findings, review=review)
    if isinstance(state, HumanState):
        if value.kind == "snooze":
            return state.validated_update(reminder_snoozed=True)
        if value.kind == "resume":
            return state.validated_update(reminder_snoozed=False)
        if value.kind == "reassign":
            return state.validated_update(reminder_recipient=value.arguments.get("assignee", ""))
    return state


@direct
def fold_human(state: HumanState, value: HumanObservation) -> HumanState:
    # Base currency belongs to admission/Authority, never to human observation.
    return state.validated_update(
        human_requested=value.requested,
        human_approved=value.approved,
        changes_requested=value.changes_requested,
        unresolved_conversations=value.unresolved_conversations,
        distinct_reviewer_required=value.distinct_required,
        distinct_reviewer_approved=value.distinct_approved,
        mergeable=value.mergeable,
        conflict=value.conflict,
        reminder_recipient=value.reviewer,
        author=value.author,
        human_capability_blocking=not value.capability_available,
    )


def fold_effect(owner, result):
    if isinstance(result, ConversationPublicationResult):
        if not result.capability_available:
            return owner.validated_update(conversation_capability_blocking=True)
        return owner.validated_update(
            conversation_pending={}, conversation_attempts=0, conversation_capability_blocking=False
        )
    if isinstance(result, (ChangeResult, RepairResult)):
        repair = isinstance(result, RepairResult)
        if result.ok:
            return owner.validated_update(
                provisional=True,
                provisional_head=result.provisional_head,
                change_in_flight=False,
                repair_in_flight=False,
                repair_recovery_required=False,
                repair_used=owner.repair_used or repair,
                repair_fingerprint=(result.fingerprint or owner.repair_fingerprint)
                if repair
                else owner.repair_fingerprint,
                repair_lineage=result.lineage or owner.repair_lineage,
            )
        return owner.validated_update(
            change_in_flight=False,
            repair_in_flight=False,
            repair_recovery_required=repair,
            repair_used=owner.repair_used or repair,
            repair_fingerprint=(result.fingerprint or owner.repair_fingerprint) if repair else owner.repair_fingerprint,
            repair_lineage=result.lineage or owner.repair_lineage,
        )
    if isinstance(result, DashboardPublicationResult):
        if not result.capability_available:
            return _invalidate(
                owner,
                dashboard_requested=owner.dashboard_requested,
                dashboard_operation=owner.dashboard_operation,
                dashboard_capability_blocking=True,
            )
        if result.ok:
            return owner.validated_update(
                dashboard_current=True,
                dashboard_requested=False,
                dashboard_operation="",
                dashboard_format=DASHBOARD_FORMAT,
                dashboard_capability_blocking=False,
            )
    if isinstance(result, ReadinessPublicationResult):
        if not result.capability_available:
            return _invalidate(owner, readiness_capability_blocking=True)
        if result.ok:
            return _invalidate(owner, readiness_requested=False, announced=True, readiness_capability_blocking=False)
    return owner


@direct
def fold_conversation_effect(p: PublicationState, r: ConversationPublicationResult) -> PublicationState:
    return _invalidate(fold_effect(p, r))


@direct
def fold_repair_effect(m: MutationState, r: RepairResult) -> MutationState:
    return fold_effect(m, r)


@direct
def fold_change_effect(m: MutationState, r: ChangeResult) -> MutationState:
    return fold_effect(m, r)


@direct
def fold_dashboard_effect(p: PublicationState, r: DashboardPublicationResult) -> PublicationState:
    return fold_effect(p, r)


@direct
def fold_readiness_effect(p: PublicationState, r: ReadinessPublicationResult) -> PublicationState:
    return fold_effect(p, r)


def _admit(binding, outputs):
    values = _hydrate(binding)
    admission = next(v for v in values if isinstance(v, Admission))
    authority_prior = next((v for v in values if isinstance(v, Authority)), None)
    review_prior = next((v for v in values if isinstance(v, ReviewState)), None)
    mutation_prior = next((v for v in values if isinstance(v, MutationState)), None)
    prior = authority_prior or next(v for v in values if not isinstance(v, Admission))
    epoch = getattr(prior, "epoch", getattr(prior, "last_epoch", 0)) + 1
    confirms = admission.head == getattr(mutation_prior or prior, "provisional_head", "")
    authority = Authority(
        admission.repository_id,
        admission.pr_number,
        epoch,
        admission.head,
        admission.base_head,
        admission.strict_base,
        admission.base_current,
        admission.policy_digest,
        admission.required_checks,
        admission.required_approvals,
        admission.conversation_resolution,
        "confirmed" if confirms else "superseded" if hasattr(prior, "epoch") else "new",
    )
    actions = ActionsState()
    review = ReviewState(review_attempts=1)
    human = HumanState()
    mutation = MutationState(
        repair_used=getattr(mutation_prior or prior, "repair_used", False) if confirms else False,
        repair_fingerprint=getattr(mutation_prior or prior, "repair_fingerprint", "") if confirms else "",
    )
    publication = PublicationState(revision=1)
    policy = {
        "strict_base": admission.strict_base,
        "required_checks": admission.required_checks,
        "required_approvals": admission.required_approvals,
        "conversation_resolution": admission.conversation_resolution,
        "digest": admission.policy_digest,
    }

    review_payload = effect_payload(
        authority,
        {
            "strict_base": admission.strict_base,
            "base_current": admission.base_current,
            "policy": policy,
            "prior_findings": getattr(review_prior or prior, "findings", []),
            "prior_lineage": getattr(review_prior or prior, "finding_lineage", []),
        },
    )
    review_work = ReviewRequest(
        epoch=epoch,
        head=admission.head,
        operation=operation("review", authority, payload=review_payload),
        base_head=authority.base_head,
        policy_digest=authority.policy_digest,
        strict_base=authority.strict_base,
        base_current=authority.base_current,
        policy=policy,
        prior_findings=review_payload["prior_findings"],
        prior_lineage=review_payload["prior_lineage"],
    )
    actions_payload = effect_payload(authority)
    actions_work = ActionsDiscoveryRequest(
        epoch=epoch,
        head=authority.head,
        operation=operation("actions_discovery", authority, payload=actions_payload),
        **actions_payload,
    )
    review = review.validated_update(review_operation=review_work.operation)
    actions = actions.validated_update(actions_operation=actions_work.operation)
    by_target = {
        "authority": authority,
        "actions_state": actions,
        "review_state": review,
        "human_state": human,
        "mutation_state": mutation,
        "publication_state": publication,
        "work.review": review_work,
        "work.actions_discovery": actions_work,
        "reminder.timer": Reminder(epoch, authority.head),
    }
    return {out.target: (Token(out.color, by_target[str(out.target)].dump()),) for out in outputs}


def _subject(prior, admission):
    return (prior.repository_id, prior.pr_number) == (admission.repository_id, admission.pr_number)


def _different(a, admission):
    return _subject(a, admission) and a.head != admission.head


def _same(a, admission):
    return _subject(a, admission) and a.head == admission.head


def _same_basis(a, admission):
    return _same(a, admission) and (a.base_head, a.strict_base, a.policy_digest) == (
        admission.base_head,
        admission.strict_base,
        admission.policy_digest,
    )


def _refresh_admission(binding, outputs):
    a, _r, p, admission = _values(binding, Authority, ReviewState, PublicationState, Admission)
    a = a.validated_update(
        base_head=admission.base_head,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy_digest=admission.policy_digest,
        required_checks=admission.required_checks,
        required_approvals=admission.required_approvals,
        conversation_resolution=admission.conversation_resolution,
        admission_relation="same_head",
    )
    return _route(outputs, {"authority": a, "publication_state": _invalidate(p)})


def _retryable_review(a, r, admission):
    return _same_basis(a, admission) and r.review == "unable" and max(r.review_attempts, 1) < MAX_REVIEW_ATTEMPTS


def _retry_review(binding, outputs):
    a, r, p, admission = _values(binding, Authority, ReviewState, PublicationState, Admission)
    attempt = max(r.review_attempts, 1) + 1
    policy = {
        "strict_base": admission.strict_base,
        "required_checks": admission.required_checks,
        "required_approvals": admission.required_approvals,
        "conversation_resolution": admission.conversation_resolution,
        "digest": admission.policy_digest,
    }
    payload = effect_payload(
        a,
        {
            "strict_base": admission.strict_base,
            "base_current": admission.base_current,
            "prior_findings": r.findings,
            "prior_lineage": r.finding_lineage,
            "policy": policy,
            "review_attempt": attempt,
        },
    )
    work = ReviewRequest(
        epoch=a.epoch,
        head=a.head,
        operation=operation("review", a, payload=payload, sequence=attempt),
        sequence=attempt,
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy=policy,
        prior_findings=r.findings,
        prior_lineage=r.finding_lineage,
        review_attempt=attempt,
    )
    a = a.validated_update(base_current=admission.base_current, admission_relation="same_head")
    r = r.validated_update(review="pending", review_attempts=attempt, review_operation=work.operation)
    return _route(
        outputs, {"authority": a, "review_state": r, "publication_state": _invalidate(p), "work.review": work}
    )


def _refresh_basis(binding, outputs):
    a, ac, r, p, admission = _values(binding, Authority, ActionsState, ReviewState, PublicationState, Admission)
    a = a.validated_update(
        base_head=admission.base_head,
        strict_base=admission.strict_base,
        base_current=admission.base_current,
        policy_digest=admission.policy_digest,
        required_checks=admission.required_checks,
        required_approvals=admission.required_approvals,
        conversation_resolution=admission.conversation_resolution,
        admission_relation="same_head_basis_changed",
    )
    ac = ActionsState()
    r = r.validated_update(review="pending", review_attempts=1)
    p = _invalidate(
        p,
        increment=2,
        findings_published=False,
        finding_publication_requested=False,
        announced=False,
        readiness_operation="",
        readiness_requested=False,
    )
    policy = {
        "strict_base": a.strict_base,
        "required_checks": a.required_checks,
        "required_approvals": a.required_approvals,
        "conversation_resolution": a.conversation_resolution,
        "digest": a.policy_digest,
    }
    payload = effect_payload(
        a,
        {
            "strict_base": a.strict_base,
            "base_current": a.base_current,
            "prior_findings": r.findings,
            "prior_lineage": r.finding_lineage,
            "policy": policy,
        },
    )
    rw = ReviewRequest(
        epoch=a.epoch,
        head=a.head,
        operation=operation("review", a, payload=payload),
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        strict_base=a.strict_base,
        base_current=a.base_current,
        policy=policy,
        prior_findings=r.findings,
        prior_lineage=r.finding_lineage,
    )
    ap = effect_payload(a)
    aw = ActionsDiscoveryRequest(
        epoch=a.epoch, head=a.head, operation=operation("actions_discovery", a, payload=ap), **ap
    )
    return _put(
        outputs,
        (
            a,
            ac.validated_update(actions_operation=aw.operation),
            r.validated_update(review_operation=rw.operation),
            p,
            rw,
            aw,
        ),
    )


def _accept_review(binding, outputs):
    a, r, p, result = _values(binding, Authority, ReviewState, PublicationState, ReviewResult)
    r = fold_review.implementation(r, result)
    publishable = [f for f in r.findings if f.get("disposition") in {"new", "still_open"}]
    p = _invalidate(
        p,
        increment=2 if publishable else 1,
        findings_published=not publishable,
        finding_publication_requested=bool(publishable),
    )
    routed = {"review_state": r, "publication_state": p}
    if publishable:
        payload = effect_payload(a, {"findings": publishable, "lineage": result.lineage})
        work = FindingPublicationRequest(
            epoch=a.epoch,
            head=a.head,
            operation=operation("finding", a, payload=payload),
            base_head=a.base_head,
            policy_digest=a.policy_digest,
            findings=publishable,
            lineage=result.lineage,
        )
        p = p.validated_update(finding_operation=work.operation)
        routed.update({"publication_state": p, "work.finding": work})
    return _route(outputs, routed)


def _finding_effect(binding, outputs):
    r, p, result = _values(binding, ReviewState, PublicationState, FindingPublicationResult)
    if result.ok:
        refs = {x.get("finding_id"): x.get("url", "") for x in result.references}
        r = r.validated_update(
            findings=[{**f, "comment_url": refs.get(f.get("id"), f.get("comment_url", ""))} for f in r.findings]
        )
        p = _invalidate(
            p,
            findings_published=True,
            finding_publication_requested=False,
            finding_operation="",
            finding_capability_blocking=False,
        )
    elif not result.capability_available:
        p = _invalidate(p, finding_capability_blocking=True)
    return _put(outputs, (r, p))


def _accept_actions(binding, outputs):
    _a, s, m, p, value = _values(binding, Authority, ActionsState, MutationState, PublicationState, ActionsObservation)
    s = fold_actions.implementation(s, value)
    if value.conclusion in {"success", "failure"}:
        m = m.validated_update(repair_in_flight=False)
    return _route(outputs, {"actions_state": s, "mutation_state": m, "publication_state": _invalidate(p)})


def _accept_human(binding, outputs):
    h, p, value = _values(binding, HumanState, PublicationState, HumanObservation)
    return _route(outputs, {"human_state": fold_human.implementation(h, value), "publication_state": _invalidate(p)})


def _accept_mutation_effect(binding, outputs, result_type):
    values = _hydrate(binding)
    m = next(v for v in values if isinstance(v, MutationState))
    p = next(v for v in values if isinstance(v, PublicationState))
    result = next(v for v in values if isinstance(v, result_type))
    if isinstance(result, RepairResult) and not result.fingerprint:
        actions = next(v for v in values if isinstance(v, ActionsState))
        result = result.validated_update(fingerprint=actions.fingerprint)
    m = fold_effect(m, result)
    return _route(outputs, {"mutation_state": m, "publication_state": _invalidate(p)})


def _accept_intent(binding, outputs, owner_type):
    owner, p, value = _values(binding, owner_type, PublicationState, Intent)
    owner = fold_intent.implementation(owner, value)
    return _route(
        outputs,
        {
            "review_state" if owner_type is ReviewState else "human_state": owner,
            "publication_state": _invalidate(p),
        },
    )


def _first_failure(a, s, m, value):
    return (
        _current(a, value)
        and s.actions == "failed"
        and not s.rerun_requested
        and s.actions_observation == value.observation
        and value.conclusion == "failure"
        and not any((m.provisional, m.change_in_flight, m.repair_in_flight))
    )


def _repairable(a, s, m, value):
    return (
        _current(a, value)
        and value.conclusion == "failure"
        and s.rerun_requested
        and value.attempt > s.rerun_attempt
        and not m.repair_used
        and not m.provisional
        and not m.change_in_flight
        and not m.repair_in_flight
        and s.actions == "reproduced"
        and s.actions_observation == value.observation
        and value.fingerprint != m.repair_fingerprint
    )


def _basis_done(a, s, m, value):
    if not _current(a, value) or not _actions_matches(a, s, value) or value.attempt < s.attempt:
        return True
    if s.rerun_requested and value.conclusion == "failure" and value.attempt <= s.rerun_attempt:
        return True
    if s.actions_observation != value.observation:
        return False
    if value.conclusion != "failure" or not s.rerun_requested:
        return value.conclusion != "failure"
    return m.repair_in_flight or m.repair_used or value.fingerprint == m.repair_fingerprint


def _rerun(binding, outputs):
    a, s, p, value = _values(binding, Authority, ActionsState, PublicationState, ActionsObservation)
    payload = effect_payload(a, {"actions": value.dump()})
    work = ActionsRerunRequest(
        epoch=value.epoch,
        head=value.head,
        operation=operation("actions-rerun", a, payload=payload),
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        actions=value,
    )
    s = s.validated_update(
        actions="rerun_requested", rerun_requested=True, rerun_attempt=s.attempt, actions_operation=work.operation
    )
    return _route(outputs, {"actions_state": s, "publication_state": _invalidate(p), "work.actions_rerun": work})


def _repair(binding, outputs):
    a, _s, m, p, value = _values(binding, Authority, ActionsState, MutationState, PublicationState, ActionsObservation)
    payload = effect_payload(a, {"actions": value.dump()})
    op = operation("repair", a, payload=payload)
    m = m.validated_update(repair_in_flight=True, mutation_operation=op)
    work = RepairRequest(
        epoch=value.epoch,
        head=value.head,
        operation=op,
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        actions=value,
        lineage=[],
    )
    return _route(outputs, {"mutation_state": m, "publication_state": _invalidate(p), "work.repair": work})


def _mutation(a: Authority, m: MutationState, value: Intent) -> bool:
    return (
        _current(a, value)
        and value.authorized
        and value.blocking
        and value.kind in {"change", "update_base", "resolve_conflict"}
        and not any((m.provisional, m.change_in_flight, m.repair_in_flight))
    )


def _authorize_change(binding, outputs):
    a, m, p, value = _values(binding, Authority, MutationState, PublicationState, Intent)
    payload = effect_payload(a, {"intent": value.dump()})
    op = operation("change", a, payload=payload)
    m = m.validated_update(change_in_flight=True, mutation_operation=op)
    p = _invalidate(p)
    work = ChangeRequest(
        epoch=value.epoch,
        head=value.head,
        operation=op,
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        intent=value,
    )
    return _put(outputs, (m, p, work))


def _replyable(a, value):
    return _current(a, value) and value.authorized and value.kind == "reply" and bool(value.arguments.get("message"))


def _authorize_reply(binding, outputs):
    a, p, value = _values(binding, Authority, PublicationState, Intent)
    payload = effect_payload(a, {"intent": value.dump()})
    work = ConversationPublicationRequest(
        epoch=value.epoch,
        head=value.head,
        operation=operation("conversation-reply", a, payload=payload),
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        intent=value,
    )
    p = _invalidate(
        p, conversation_pending=work.dump(), conversation_attempts=1, conversation_capability_blocking=False
    )
    return _route(outputs, {"publication_state": p, "work.conversation_reply": work})


def _retry_reply(p):
    return (
        p.conversation_capability_blocking
        and bool(p.conversation_pending)
        and p.conversation_attempts < MAX_CONVERSATION_ATTEMPTS
    )


def _reissue_reply(binding, outputs):
    p = _values(binding, PublicationState)[0]
    pending = dict(p.conversation_pending)
    pending["intent"] = Intent(**pending["intent"])
    work = ConversationPublicationRequest(**pending)
    p = _invalidate(p, conversation_attempts=p.conversation_attempts + 1, conversation_capability_blocking=False)
    return _route(outputs, {"publication_state": p, "work.conversation_reply": work})


def conversation_work(
    a: Authority,
    ac: ActionsState,
    r: ReviewState,
    h: HumanState,
    m: MutationState,
    p: PublicationState,
    value: ConversationObservation,
) -> ConversationClassificationRequest:
    snapshot = _snapshot(a, ac, r, h, m, p)
    payload = effect_payload(a, {"comment": value.dump(), "control": snapshot.dump()})
    return ConversationClassificationRequest(
        epoch=value.epoch,
        head=value.head,
        operation=operation("conversation", a, payload=payload),
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        comment=value,
        control=snapshot,
    )


def _conversation_work(binding, outputs):
    values = _values(
        binding,
        Authority,
        ActionsState,
        ReviewState,
        HumanState,
        MutationState,
        PublicationState,
        ConversationObservation,
    )
    return _put(outputs, (conversation_work(*values),))


def ready(snapshot: ReadinessSnapshot) -> bool:
    return (
        workflow_gates_ready(snapshot)
        and snapshot.dashboard_current
        and not snapshot.readiness_requested
        and not snapshot.announced
    )


def _request_dashboard(snapshot: ReadinessSnapshot) -> bool:
    return (
        not snapshot.dashboard_current or snapshot.dashboard_format < DASHBOARD_FORMAT
    ) and not snapshot.dashboard_requested


def _dashboard(binding, outputs):
    a, ac, r, h, m, p = _values(
        binding, Authority, ActionsState, ReviewState, HumanState, MutationState, PublicationState
    )
    before = _snapshot(a, ac, r, h, m, p)
    payload = effect_payload(a, {"control": before.dump(), "projected_revision": p.revision + 1})
    op = operation("dashboard", a, payload=payload)
    p = _invalidate(p).validated_update(dashboard_requested=True, dashboard_operation=op)
    after = _snapshot(a, ac, r, h, m, p)
    work = DashboardPublicationRequest(
        epoch=a.epoch, head=a.head, operation=op, base_head=a.base_head, policy_digest=a.policy_digest, control=after
    )
    return _put(outputs, (p, work))


def _announce(binding, outputs):
    a, _ac, _r, _h, _m, p = _values(
        binding, Authority, ActionsState, ReviewState, HumanState, MutationState, PublicationState
    )
    op = operation("readiness", a, payload={"revision": p.revision})
    p = p.validated_update(readiness_requested=True, readiness_operation=op)
    work = ReadinessCommand(
        epoch=a.epoch, head=a.head, operation=op, base_head=a.base_head, policy_digest=a.policy_digest
    )
    return _put(outputs, (p, work))


def _reminder_due(snapshot: ReadinessSnapshot, timer: Reminder) -> bool:
    review_satisfied = snapshot.human_approved and (
        bool(snapshot.reminder_recipient) or snapshot.distinct_reviewer_approved or snapshot.human_requested
    )
    authority = Authority(**{k: snapshot.dump()[k] for k in Authority.__dataclass_fields__})
    return (
        _current(authority, timer)
        and not snapshot.reminder_snoozed
        and not review_satisfied
        and not snapshot.changes_requested
        and snapshot.dashboard_current
        and snapshot.actions in {"green", "flaky_green"}
        and snapshot.review == "clear"
        and not any((snapshot.provisional, snapshot.change_in_flight, snapshot.repair_in_flight, snapshot.conflict))
    )


def _remind(binding, outputs):
    a, h, timer = _values(binding, Authority, HumanState, Reminder)
    nxt = Reminder(timer.epoch, timer.head, timer.sequence + 1)
    payload = effect_payload(a, {"sequence": timer.sequence, "reviewer": h.reminder_recipient, "author": h.author})
    work = ReminderPublicationRequest(
        epoch=timer.epoch,
        head=timer.head,
        operation=operation("reminder", a, payload=payload, sequence=timer.sequence),
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        sequence=timer.sequence,
        reviewer=h.reminder_recipient,
        author=h.author,
    )
    return _route(outputs, {"reminder.rearm": nxt, "work.reminder": work})


@direct
def _rearm(timer: Reminder) -> Reminder:
    return timer


def _lifecycle(binding, outputs, terminal=False):
    values = _hydrate(binding)
    a = next(v for v in values if isinstance(v, Authority))
    lifecycle = next(v for v in values if isinstance(v, Lifecycle))
    value = (
        Terminal("success" if lifecycle.status == "merged" else "abort", a.epoch, lifecycle.head)
        if terminal
        else Dormant(a.repository_id, a.pr_number, a.epoch, lifecycle.head)
    )
    return _put(outputs, (value,))


def build_net(reminder_delay: float = 3 * 24 * 60 * 60) -> BuiltNet:
    net = NetSpec("pr-readiness-concerns")
    p, t = net.p, net.t
    work, execute, retire, admit, reminder, command = (
        net.s.work,
        net.s.execute,
        net.s.retire,
        net.s.admit,
        net.s.reminder,
        net.s.command,
    )
    t.verified_admission >> p.admission(Admission)
    t.lifecycle_observation >> p.lifecycle(Lifecycle)
    t.human_observation >> p.human_result(HumanObservation)
    t.actions_observation >> (p.actions_result(ActionsObservation), p.actions_basis(ActionsObservation))
    t.conversation_observation >> p.conversation_basis(ConversationObservation)
    work.p.review(ReviewRequest) >> execute.t.review(handler="review") >> p.review_result(ReviewResult)
    (
        work.p.actions_discovery(ActionsDiscoveryRequest)
        >> execute.t.actions_discovery(handler="actions_discovery")
        >> (p.actions_result, p.actions_basis)
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
    cohort = (
        p.authority(Authority),
        p.actions_state(ActionsState),
        p.review_state(ReviewState),
        p.human_state(HumanState),
        p.mutation_state(MutationState),
        p.publication_state(PublicationState),
    )
    for name, prior, guard in (
        ("initial", p.seed(Seed), _subject),
        ("supersede", cohort, lambda a, ac, r, h, m, pub, ad: _different(a, ad)),
        ("resume", p.dormant(Dormant), _subject),
    ):
        tr = getattr(admit.t, name)(handler=petri_handler(_admit), guards=_guard(guard))
        sources = (*prior, p.admission) if isinstance(prior, tuple) else (prior, p.admission)
        sources >> tr >> (*cohort, work.p.review, work.p.actions_discovery, reminder.p.timer(Reminder))
    (
        (p.authority, p.actions_state, p.review_state, p.publication_state, p.admission)
        >> t.refresh_basis(
            handler=petri_handler(_refresh_basis),
            guards=_guard(lambda a, ac, r, pub, ad: _same(a, ad) and not _same_basis(a, ad)),
        )
        >> (p.authority, p.actions_state, p.review_state, p.publication_state, work.p.review, work.p.actions_discovery)
    )
    refresh = t.refresh_admission(
        handler=petri_handler(_refresh_admission),
        guards=_typed_guard(
            (Authority, ReviewState, Admission),
            lambda a, r, ad: _same_basis(a, ad) and not _retryable_review(a, r, ad),
        ),
    )
    p.review_state >> arc.read() >> refresh
    (p.authority, p.publication_state, p.admission) >> refresh >> (p.authority, p.publication_state)
    # Retry precedence is encoded by competition plus the refresh guard below.
    (
        (p.authority, p.review_state, p.publication_state, p.admission)
        >> t.retry_review(
            handler=petri_handler(_retry_review),
            guards=_typed_guard((Authority, ReviewState, Admission), _retryable_review),
        )
        >> (p.authority, p.review_state, p.publication_state, work.p.review)
    )
    accept_actions = t.accept_actions(
        handler=petri_handler(_accept_actions),
        guards=_typed_guard((Authority, ActionsState, ActionsObservation), _new_actions),
    )
    p.authority >> arc.read() >> accept_actions
    (
        (p.actions_state, p.mutation_state, p.publication_state, p.actions_result)
        >> accept_actions
        >> (p.actions_state, p.mutation_state, p.publication_state)
    )
    accept_human = t.accept_human(
        handler=petri_handler(_accept_human), guards=_guard(lambda a, h, pub, v: _current(a, v))
    )
    p.authority >> arc.read() >> accept_human
    (p.human_state, p.publication_state, p.human_result) >> accept_human >> (p.human_state, p.publication_state)
    accept_review = t.accept_review(
        handler=petri_handler(_accept_review),
        guards=_typed_guard((Authority, ReviewState, ReviewResult), _review_matches),
    )
    p.authority >> arc.read() >> accept_review
    (
        (p.review_state, p.publication_state, p.review_result)
        >> accept_review
        >> (
            p.review_state,
            p.publication_state,
            work.p.finding,
        )
    )
    accept_finding = t.accept_finding(
        handler=petri_handler(_finding_effect), guards=_guard(lambda a, r, pub, v: _effect_matches(a, pub, v))
    )
    p.authority >> arc.read() >> accept_finding
    (
        (p.review_state, p.publication_state, p.finding_result)
        >> accept_finding
        >> (
            p.review_state,
            p.publication_state,
        )
    )
    authorize_change = t.authorize_change(
        handler=petri_handler(_authorize_change),
        guards=_typed_guard((Authority, MutationState, Intent), _mutation),
    )
    p.authority >> arc.read() >> authorize_change
    (
        (p.mutation_state, p.publication_state, p.change_basis(Intent))
        >> authorize_change
        >> (
            p.mutation_state,
            p.publication_state,
            work.p.change,
        )
    )
    for name, place, result_type, owner, folder in (
        (
            "conversation",
            p.conversation_result,
            ConversationPublicationResult,
            p.publication_state,
            fold_conversation_effect,
        ),
        ("dashboard", p.dashboard_result, DashboardPublicationResult, p.publication_state, fold_dashboard_effect),
        ("readiness", p.readiness_result, ReadinessPublicationResult, p.publication_state, fold_readiness_effect),
    ):
        tr = getattr(t, f"accept_{name}")(
            handler=petri_handler(
                lambda b, o, result_type=result_type, fold=folder: _fold_owned(
                    b, o, PublicationState, result_type, fold
                )
            ),
            guards=_guard(_effect_matches),
        )
        p.authority >> arc.read() >> tr
        (owner, place) >> tr >> owner
    accept_reminder = t.accept_reminder(guards=_guard(lambda a, result: _current(a, result)))
    p.authority >> arc.read() >> accept_reminder
    p.reminder_result >> accept_reminder
    for name, place, result_type in (
        ("repair", p.repair_result, RepairResult),
        ("change", p.change_result, ChangeResult),
    ):
        tr = getattr(t, f"accept_{name}")(
            handler=petri_handler(lambda b, o, kind=result_type: _accept_mutation_effect(b, o, kind)),
            guards=_typed_guard(
                (Authority, MutationState, result_type),
                lambda authority, mutation, result: _effect_matches(authority, mutation, result),
            ),
        )
        p.authority >> arc.read() >> tr
        if result_type is RepairResult:
            p.actions_state >> arc.read() >> tr
        (p.mutation_state, p.publication_state, place) >> tr >> (p.mutation_state, p.publication_state)

    rerun = t.authorize_rerun(
        handler=petri_handler(_rerun),
        guards=_guard(lambda a, m, s, pub, v: _first_failure(a, s, m, v)),
    )
    (p.authority, p.mutation_state) >> arc.read() >> rerun
    (
        (p.actions_state, p.publication_state, p.actions_basis)
        >> rerun
        >> (p.actions_state, p.publication_state, work.p.actions_rerun)
    )
    repair_work = t.authorize_repair(
        handler=petri_handler(_repair),
        guards=_guard(lambda a, s, m, pub, v: _repairable(a, s, m, v)),
    )
    (p.authority, p.actions_state) >> arc.read() >> repair_work
    (
        (p.mutation_state, p.publication_state, p.actions_basis)
        >> repair_work
        >> (p.mutation_state, p.publication_state, work.p.repair)
    )
    basis_retire = retire.t.actions_basis(guards=_guard(_basis_done))
    for place in (p.authority, p.actions_state, p.mutation_state):
        place >> arc.read() >> basis_retire
    p.actions_basis >> basis_retire
    # Full snapshots are relational joins only at the approved projection/gate boundaries.
    start = t.start_conversation(
        handler=petri_handler(_conversation_work),
        guards=_guard(lambda a, ac, r, h, m, pub, v: _current(a, v) and v.authorized),
    )
    for place in cohort:
        place >> arc.read() >> start
    p.conversation_basis >> start >> work.p.conversation
    (
        p.intent_batch
        >> t.unpack_intents(
            handler=petri_handler(
                lambda b, outs: {
                    o.target: tuple(
                        Token(o.color, i.dump()) for i in (Intent(**raw) for raw in b.tokens[0].data["intents"])
                    )
                    for o in outs
                }
            )
        )
        >> (p.change_basis, p.intent_result(Intent), p.reply_basis(Intent))
    )
    for name, owner_type, owner, kinds in (
        ("finding_intent", ReviewState, p.review_state, {"acknowledge", "dismiss", "defer"}),
        ("reminder_intent", HumanState, p.human_state, {"snooze", "resume", "reassign"}),
    ):
        tr = getattr(t, f"accept_{name}")(
            handler=petri_handler(lambda b, o, typ=owner_type: _accept_intent(b, o, typ)),
            guards=_guard(
                lambda a, state, pub, value, selected=kinds: (
                    _current(a, value) and value.authorized and value.kind in selected
                )
            ),
        )
        p.authority >> arc.read() >> tr
        (owner, p.publication_state, p.intent_result) >> tr >> (owner, p.publication_state)
    authorize_reply = t.authorize_reply(
        handler=petri_handler(_authorize_reply),
        guards=_typed_guard((Authority, Intent), _replyable),
    )
    p.authority >> arc.read() >> authorize_reply
    (
        (p.publication_state, p.reply_basis)
        >> authorize_reply
        >> (
            p.publication_state,
            work.p.conversation_reply,
        )
    )
    (
        p.publication_state
        >> t.reissue_reply(handler=petri_handler(_reissue_reply), guards=_guard(_retry_reply))
        >> (p.publication_state, work.p.conversation_reply)
    )
    dashboard = t.request_dashboard(
        handler=petri_handler(_dashboard),
        guards=_guard(lambda a, ac, r, h, m, pub: _request_dashboard(_snapshot(a, ac, r, h, m, pub))),
    )
    announce = t.authorize_readiness(
        handler=petri_handler(_announce),
        guards=_guard(lambda a, ac, r, h, m, pub: ready(_snapshot(a, ac, r, h, m, pub))),
    )
    for place in cohort[:-1]:
        place >> arc.read() >> dashboard
        place >> arc.read() >> announce
    p.publication_state >> dashboard >> (p.publication_state, work.p.dashboard)
    p.publication_state >> announce >> (p.publication_state, command.p.readiness)
    due = t.reminder_due(
        handler=petri_handler(_remind),
        guards=_guard(lambda a, ac, r, h, m, pub, timer: _reminder_due(_snapshot(a, ac, r, h, m, pub), timer)),
        timers=(Delay(reminder_delay),),
    )
    for place in cohort:
        place >> arc.read() >> due
    reminder.p.timer >> due >> (reminder.p.rearm(Reminder), work.p.reminder)
    reminder.p.rearm >> t.rearm(handler=_rearm) >> reminder.p.timer
    # Lifecycle-wide movement alone consumes the complete active cohort.
    (
        (*cohort, p.lifecycle)
        >> t.draft(
            handler=petri_handler(lambda b, o: _lifecycle(b, o)),
            guards=_guard(lambda a, ac, r, h, m, pub, life: life.status == "draft"),
        )
        >> p.dormant
    )
    (
        (*cohort, p.lifecycle)
        >> t.terminal_active(
            handler=petri_handler(lambda b, o: _lifecycle(b, o, True)),
            guards=_guard(lambda a, ac, r, h, m, pub, life: life.status in {"merged", "closed"}),
        )
        >> p.terminal(Terminal)
    )
    (
        (p.dormant, p.lifecycle)
        >> t.terminal_dormant(
            handler=petri_handler(
                lambda b, o: _route(
                    o,
                    {
                        "terminal": Terminal(
                            "success" if _values(b, Lifecycle)[0].status == "merged" else "abort",
                            _values(b, Dormant)[0].last_epoch,
                            _values(b, Lifecycle)[0].head,
                        )
                    },
                )
            ),
            guards=_guard(lambda d, life: life.status in {"merged", "closed"}),
        )
        >> p.terminal
    )
    irrelevant = retire.t.lifecycle_active(
        guards=_guard(lambda a, life: life.status not in {"draft", "merged", "closed"})
    )
    p.authority >> arc.read() >> irrelevant
    p.lifecycle >> irrelevant
    dormant_irrelevant = retire.t.lifecycle_dormant(
        guards=_guard(lambda d, life: life.status not in {"merged", "closed"})
    )
    p.dormant >> arc.read() >> dormant_irrelevant
    p.lifecycle >> dormant_irrelevant
    # Generic authority staleness and dormant/terminal absorption leave no active residue.
    transient = (
        p.review_result,
        p.actions_result,
        p.human_result,
        p.intent_result,
        p.intent_batch,
        p.conversation_result,
        p.repair_result,
        p.change_result,
        p.finding_result,
        p.dashboard_result,
        p.reminder_result,
        p.readiness_result,
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
    for index, place in enumerate(transient):
        stale = getattr(retire.t, f"stale_{index}")(guards=_guard(lambda a, value: not _current(a, value)))
        p.authority >> arc.read() >> stale
        place >> stale
        for prefix, authority in (("dormant", p.dormant), ("terminal", p.terminal)):
            tr = getattr(retire.t, f"{prefix}_{index}")
            authority >> arc.read() >> tr
            place >> tr
    # Same-generation envelopes with superseded owner operation identity are retired.
    for name, place, owner, predicate in (
        ("review_operation", p.review_result, p.review_state, lambda a, owner, v: not _review_matches(a, owner, v)),
        ("actions_operation", p.actions_result, p.actions_state, lambda a, owner, v: _duplicate_actions(a, owner, v)),
        (
            "finding_operation",
            p.finding_result,
            p.publication_state,
            lambda a, owner, v: not _effect_matches(a, owner, v),
        ),
        (
            "dashboard_operation",
            p.dashboard_result,
            p.publication_state,
            lambda a, owner, v: not _effect_matches(a, owner, v),
        ),
        (
            "readiness_operation",
            p.readiness_result,
            p.publication_state,
            lambda a, owner, v: not _effect_matches(a, owner, v),
        ),
        (
            "conversation_operation",
            p.conversation_result,
            p.publication_state,
            lambda a, owner, v: not _effect_matches(a, owner, v),
        ),
        ("change_operation", p.change_result, p.mutation_state, lambda a, owner, v: not _effect_matches(a, owner, v)),
        ("repair_operation", p.repair_result, p.mutation_state, lambda a, owner, v: not _effect_matches(a, owner, v)),
    ):
        tr = getattr(retire.t, name)(guards=_guard(predicate))
        (p.authority, owner) >> arc.read() >> tr
        place >> tr
    for name, place, guard in (
        ("conversation_basis", p.conversation_basis, lambda a, v: not (_current(a, v) and v.authorized)),
        ("reply_basis", p.reply_basis, lambda a, v: not _replyable(a, v)),
        (
            "intent_noop",
            p.intent_result,
            lambda a, v: (
                not (
                    _current(a, v)
                    and v.authorized
                    and v.kind in {"acknowledge", "dismiss", "defer", "snooze", "resume", "reassign"}
                )
            ),
        ),
    ):
        tr = getattr(retire.t, name)(guards=_guard(guard))
        p.authority >> arc.read() >> tr
        place >> tr
    change_retire = retire.t.change_basis(guards=_guard(lambda a, m, v: not _mutation(a, m, v)))
    (p.authority, p.mutation_state) >> arc.read() >> change_retire
    p.change_basis >> change_retire
    for name, owner, guard in (
        ("seed_admission", p.seed, lambda prior, value: not _subject(prior, value)),
        ("dormant_admission", p.dormant, lambda prior, value: not _subject(prior, value)),
        ("active_admission", p.authority, lambda prior, value: not _subject(prior, value)),
    ):
        tr = getattr(retire.t, name)(guards=_guard(guard))
        owner >> arc.read() >> tr
        p.admission >> tr
    p.terminal >> arc.read() >> retire.t.terminal_admission
    p.admission >> retire.t.terminal_admission
    p.terminal >> arc.read() >> retire.t.terminal_lifecycle
    p.lifecycle >> retire.t.terminal_lifecycle
    return net.build()
