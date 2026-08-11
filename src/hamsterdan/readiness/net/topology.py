"""Concern-oriented executable topology for one PR-readiness Instance."""

from __future__ import annotations

import hashlib
import json

from petrus.impetus.dsl import BuiltNet, NetSpec, arc, direct, petri_guard, petri_handler
from petrus.impetus.petrinet import Delay, Token
from pydantic import TypeAdapter

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
    ConversationPublicationState,
    DashboardPublicationRequest,
    DashboardPublicationResult,
    DashboardPublicationState,
    Dormant,
    FindingPublicationRequest,
    FindingPublicationResult,
    FindingPublicationState,
    GenerationCommit,
    GenerationStart,
    GenerationStop,
    HumanObservation,
    HumanState,
    Intent,
    IntentBatch,
    MutationState,
    ReadinessCommand,
    ReadinessPublicationResult,
    ReadinessPublicationState,
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
    dashboard_projection_digest,
    project_readiness,
    workflow_gates_ready,
)
from hamsterdan.readiness.payloads import PydanticPayloadConverter

DASHBOARD_FORMAT = 2
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
        GenerationCommit,
        GenerationStart,
        GenerationStop,
        Authority,
        ActionsState,
        ReviewState,
        HumanState,
        MutationState,
        FindingPublicationState,
        ConversationPublicationState,
        DashboardPublicationState,
        ReadinessPublicationState,
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
_TOKEN_ADAPTERS = {name: TypeAdapter(value_type) for name, value_type in _TOKEN_TYPES.items()}


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
            values.append(
                _TOKEN_ADAPTERS[token.color].validate_json(
                    json.dumps(token.data, sort_keys=True, separators=(",", ":"))
                )
            )
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


def _unpack_intents(binding, outputs):
    """Route each classified intent only to the workflow that can consume it."""
    selected = {
        "change_basis": {"change", "update_base", "resolve_conflict"},
        "intent_result": {"acknowledge", "dismiss", "defer", "snooze", "resume", "reassign"},
        "reply_basis": {"reply"},
        "recovery_basis": {"recover_publication"},
    }
    intents = tuple(Intent(**raw) for raw in binding.tokens[0].data["intents"])
    return {
        output.target: tuple(Token(output.color, intent.dump()) for intent in intents if intent.kind in kinds)
        for output in outputs
        if (kinds := selected.get(str(output.target))) is not None
    }


def _current(authority: Authority, value) -> bool:
    if authority.epoch != value.epoch or authority.head != value.head:
        return False
    return (not getattr(value, "base_head", "") or value.base_head == authority.base_head) and (
        not getattr(value, "policy_digest", "") or value.policy_digest == authority.policy_digest
    )


def _snapshot(a, ac, r, h, m, fp, cp, dp, rp):
    return project_readiness(a, ac, r, h, m, fp, cp, dp, rp)


def _snapshot_values(*values):
    types = (
        Authority,
        ActionsState,
        ReviewState,
        HumanState,
        MutationState,
        FindingPublicationState,
        ConversationPublicationState,
        DashboardPublicationState,
        ReadinessPublicationState,
    )
    return _snapshot(*(next(value for value in values if isinstance(value, kind)) for kind in types))


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
    return not _new_actions(a, s, value)


def _effect_matches(a: Authority, owner, value) -> bool:
    if not _current(a, value):
        return False
    if isinstance(value, ConversationPublicationResult):
        return owner.conversation_requested and value.operation == owner.conversation_operation
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
        observation_sequence=state.observation_sequence + 1,
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
        if result.faulted:
            return owner.validated_update(
                conversation_capability_blocking=False,
                conversation_publication_fault=True,
            )
        if not result.capability_available:
            return owner.validated_update(conversation_capability_blocking=True)
        return owner.validated_update(
            conversation_requested=False,
            conversation_operation=None,
            conversation_recovery=None,
            conversation_capability_blocking=False,
            conversation_publication_fault=False,
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
        if result.faulted:
            return owner.validated_update(
                dashboard_capability_blocking=False,
                dashboard_publication_fault=True,
            )
        if not result.capability_available:
            return owner.validated_update(dashboard_capability_blocking=True)
        if result.ok:
            return owner.validated_update(
                dashboard_projection=owner.dashboard_requested_projection,
                dashboard_requested_projection="",
                dashboard_requested=False,
                dashboard_operation=None,
                dashboard_recovery=None,
                dashboard_format=DASHBOARD_FORMAT,
                dashboard_capability_blocking=False,
                dashboard_publication_fault=False,
            )
    if isinstance(result, ReadinessPublicationResult):
        if result.faulted:
            return owner.validated_update(
                readiness_capability_blocking=False,
                readiness_publication_fault=True,
            )
        if not result.capability_available:
            return owner.validated_update(readiness_capability_blocking=True)
        if result.ok:
            return owner.validated_update(
                readiness_requested=False,
                readiness_operation=None,
                readiness_recovery=None,
                announced=True,
                readiness_capability_blocking=False,
                readiness_publication_fault=False,
            )
    return owner


@direct
def fold_conversation_effect(
    p: ConversationPublicationState, r: ConversationPublicationResult
) -> ConversationPublicationState:
    return fold_effect(p, r)


@direct
def fold_repair_effect(m: MutationState, r: RepairResult) -> MutationState:
    return fold_effect(m, r)


@direct
def fold_change_effect(m: MutationState, r: ChangeResult) -> MutationState:
    return fold_effect(m, r)


@direct
def fold_dashboard_effect(p: DashboardPublicationState, r: DashboardPublicationResult) -> DashboardPublicationState:
    return fold_effect(p, r)


@direct
def fold_readiness_effect(p: ReadinessPublicationState, r: ReadinessPublicationResult) -> ReadinessPublicationState:
    return fold_effect(p, r)


def _begin_generation(binding, outputs):
    start = _values(binding, GenerationStart)[0]
    authority = Authority(
        start.repository_id,
        start.pr_number,
        start.epoch,
        start.head,
        start.base_head,
        start.strict_base,
        start.base_current,
        start.policy_digest,
        start.required_checks,
        start.required_approvals,
        start.conversation_resolution,
        "new" if start.relation in {"new", "resumed"} else start.relation,
    )
    policy = {
        "strict_base": start.strict_base,
        "required_checks": start.required_checks,
        "required_approvals": start.required_approvals,
        "conversation_resolution": start.conversation_resolution,
        "digest": start.policy_digest,
    }
    review_payload = effect_payload(
        authority,
        {
            "strict_base": start.strict_base,
            "base_current": start.base_current,
            "policy": policy,
            "prior_findings": start.prior_findings,
            "prior_lineage": start.prior_lineage,
        },
    )
    review_work = ReviewRequest(
        epoch=start.epoch,
        head=start.head,
        operation=operation("review", authority, payload=review_payload),
        base_head=start.base_head,
        policy_digest=start.policy_digest,
        strict_base=start.strict_base,
        base_current=start.base_current,
        policy=policy,
        prior_findings=start.prior_findings,
        prior_lineage=start.prior_lineage,
    )
    actions_payload = effect_payload(authority)
    actions_work = ActionsDiscoveryRequest(
        epoch=start.epoch,
        head=start.head,
        operation=operation("actions_discovery", authority, payload=actions_payload),
        **actions_payload,
    )
    by_target = {
        "authority": authority,
        "actions_state": ActionsState(actions_operation=actions_work.operation),
        "review_state": ReviewState(review_operation=review_work.operation, review_attempts=1),
        "human_state": HumanState(),
        "mutation_state": MutationState(
            repair_used=start.repair_used,
            repair_fingerprint=start.repair_fingerprint,
        ),
        "finding_publication_state": FindingPublicationState(),
        "conversation_publication_state": ConversationPublicationState(),
        "dashboard_publication_state": DashboardPublicationState(),
        "readiness_publication_state": ReadinessPublicationState(),
        "work.review": review_work,
        "work.actions_discovery": actions_work,
        "reminder.timer": Reminder(start.epoch, start.head),
    }
    return {out.target: (Token(out.color, by_target[str(out.target)].dump()),) for out in outputs}


def _stop_generation(stop: GenerationStop):
    if stop.status == "draft":
        return Dormant(stop.repository_id, stop.pr_number, stop.last_epoch, stop.head)
    return Terminal("success" if stop.status == "merged" else "abort", stop.last_epoch, stop.head)


def _route_generation_stop(binding, outputs):
    value = _stop_generation(*_values(binding, GenerationStop))
    return _route(outputs, {"dormant" if isinstance(value, Dormant) else "terminal": value})


def _subject(prior, admission):
    return (prior.repository_id, prior.pr_number) == (admission.repository_id, admission.pr_number)


def _same(a, admission):
    return _subject(a, admission) and a.head == admission.head


def _same_basis(a, admission):
    return _same(a, admission) and (a.base_head, a.strict_base, a.policy_digest) == (
        admission.base_head,
        admission.strict_base,
        admission.policy_digest,
    )


def _refresh_admission(binding, outputs):
    a, _r, admission = _values(binding, Authority, ReviewState, Admission)
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
    return _route(outputs, {"authority": a})


def _retryable_review(a, r, admission):
    return _same_basis(a, admission) and r.review == "unable" and max(r.review_attempts, 1) < MAX_REVIEW_ATTEMPTS


def _retry_review(binding, outputs):
    a, r, admission = _values(binding, Authority, ReviewState, Admission)
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
    )
    a = a.validated_update(base_current=admission.base_current, admission_relation="same_head")
    r = r.validated_update(review="pending", review_attempts=attempt, review_operation=work.operation)
    return _route(outputs, {"authority": a, "review_state": r, "work.review": work})


def _refresh_basis(binding, outputs):
    a, ac, r, fp, cp, dp, rp, admission = _values(
        binding,
        Authority,
        ActionsState,
        ReviewState,
        FindingPublicationState,
        ConversationPublicationState,
        DashboardPublicationState,
        ReadinessPublicationState,
        Admission,
    )
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
    fp = fp.validated_update(
        findings_published=False,
        finding_publication_requested=False,
        finding_operation=None,
        finding_capability_blocking=False,
    )
    cp = cp.validated_update(
        conversation_requested=False,
        conversation_operation=None,
        conversation_recovery=None,
        conversation_capability_blocking=False,
        conversation_publication_fault=False,
    )
    dp = dp.validated_update(
        dashboard_requested_projection="",
        dashboard_requested=False,
        dashboard_operation=None,
        dashboard_recovery=None,
        dashboard_capability_blocking=False,
        dashboard_publication_fault=False,
    )
    rp = rp.validated_update(
        announced=False,
        readiness_operation=None,
        readiness_recovery=None,
        readiness_requested=False,
        readiness_capability_blocking=False,
        readiness_publication_fault=False,
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
            fp,
            cp,
            dp,
            rp,
            rw,
            aw,
        ),
    )


def _accept_review(binding, outputs):
    a, r, p, result = _values(binding, Authority, ReviewState, FindingPublicationState, ReviewResult)
    r = fold_review.implementation(r, result)
    publishable = [f for f in r.findings if f.get("disposition") in {"new", "still_open"}]
    p = p.validated_update(
        findings_published=not publishable,
        finding_publication_requested=bool(publishable),
    )
    routed = {"review_state": r, "finding_publication_state": p}
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
        routed.update({"finding_publication_state": p, "work.finding": work})
    return _route(outputs, routed)


def _finding_effect(binding, outputs):
    r, p, result = _values(binding, ReviewState, FindingPublicationState, FindingPublicationResult)
    if result.ok:
        refs = {x.get("finding_id"): x.get("url", "") for x in result.references}
        r = r.validated_update(
            findings=[{**f, "comment_url": refs.get(f.get("id"), f.get("comment_url", ""))} for f in r.findings]
        )
        p = p.validated_update(
            findings_published=True,
            finding_publication_requested=False,
            finding_operation=None,
            finding_capability_blocking=False,
        )
    elif not result.capability_available:
        p = p.validated_update(finding_capability_blocking=True)
    return _put(outputs, (r, p))


def _accept_actions(binding, outputs):
    _a, state, value = _values(binding, Authority, ActionsState, ActionsObservation)
    return _route(
        outputs,
        {"actions_state": fold_actions.implementation(state, value), "actions_basis": value},
    )


@direct(converter=PydanticPayloadConverter())
def _accept_human(authority: Authority, state: HumanState, value: HumanObservation) -> HumanState:
    del authority
    return fold_human.implementation(state, value)


@direct(converter=PydanticPayloadConverter())
def _accept_change(authority: Authority, state: MutationState, result: ChangeResult) -> MutationState:
    del authority
    return fold_change_effect.implementation(state, result)


@direct(converter=PydanticPayloadConverter())
def _accept_repair(
    authority: Authority, actions: ActionsState, state: MutationState, result: RepairResult
) -> MutationState:
    del authority
    if not result.fingerprint:
        result = result.validated_update(fingerprint=actions.fingerprint)
    return fold_repair_effect.implementation(state, result)


@direct(converter=PydanticPayloadConverter())
def _accept_conversation(
    authority: Authority, state: ConversationPublicationState, result: ConversationPublicationResult
) -> ConversationPublicationState:
    del authority
    return fold_conversation_effect.implementation(state, result)


@direct(converter=PydanticPayloadConverter())
def _accept_dashboard(
    authority: Authority, state: DashboardPublicationState, result: DashboardPublicationResult
) -> DashboardPublicationState:
    del authority
    return fold_dashboard_effect.implementation(state, result)


@direct(converter=PydanticPayloadConverter())
def _accept_readiness(
    authority: Authority, state: ReadinessPublicationState, result: ReadinessPublicationResult
) -> ReadinessPublicationState:
    del authority
    return fold_readiness_effect.implementation(state, result)


def _accept_intent(binding, outputs, owner_type):
    owner, value = _values(binding, owner_type, Intent)
    owner = fold_intent.implementation(owner, value)
    return _route(
        outputs,
        {"review_state" if owner_type is ReviewState else "human_state": owner},
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
    a, s, value = _values(binding, Authority, ActionsState, ActionsObservation)
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
    return _route(outputs, {"actions_state": s, "work.actions_rerun": work})


def _repair(binding, outputs):
    a, _s, m, value = _values(binding, Authority, ActionsState, MutationState, ActionsObservation)
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
    return _route(outputs, {"mutation_state": m, "work.repair": work})


def _mutation(a: Authority, m: MutationState, value: Intent) -> bool:
    return (
        _current(a, value)
        and value.authorized
        and value.blocking
        and value.kind in {"change", "update_base", "resolve_conflict"}
        and not any((m.provisional, m.change_in_flight, m.repair_in_flight))
    )


def _authorize_change(binding, outputs):
    a, m, value = _values(binding, Authority, MutationState, Intent)
    payload = effect_payload(a, {"intent": value.dump()})
    op = operation("change", a, payload=payload)
    m = m.validated_update(change_in_flight=True, mutation_operation=op)
    work = ChangeRequest(
        epoch=value.epoch,
        head=value.head,
        operation=op,
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        intent=value,
    )
    return _put(outputs, (m, work))


def _valid_reply(a, value):
    return _current(a, value) and value.authorized and value.kind == "reply" and bool(value.arguments.get("message"))


def _replyable(a, p, value):
    return _valid_reply(a, value) and not p.conversation_requested and not p.conversation_capability_blocking


def _authorize_reply(binding, outputs):
    a, p, value = _values(binding, Authority, ConversationPublicationState, Intent)
    payload = effect_payload(a, {"intent": value.dump()})
    work = ConversationPublicationRequest(
        epoch=value.epoch,
        head=value.head,
        operation=operation("conversation-reply", a, payload=payload),
        base_head=a.base_head,
        policy_digest=a.policy_digest,
        intent=value,
    )
    p = p.validated_update(
        conversation_requested=True,
        conversation_operation=work.operation,
        conversation_recovery=work,
        conversation_capability_blocking=False,
    )
    return _route(outputs, {"conversation_publication_state": p, "work.conversation_reply": work})


def _recoverable_publication(
    a: Authority,
    cp: ConversationPublicationState,
    dp: DashboardPublicationState,
    rp: ReadinessPublicationState,
    value: Intent,
) -> bool:
    target = value.arguments.get("target")
    operation = value.arguments.get("operation")
    if not (_current(a, value) and value.authorized and value.kind == "recover_publication"):
        return False
    if not isinstance(target, str) or not isinstance(operation, str):
        return False
    if target == "conversation":
        blocked, owned, recovery = (
            cp.conversation_capability_blocking,
            cp.conversation_operation,
            cp.conversation_recovery,
        )
    elif target == "dashboard":
        blocked, owned, recovery = dp.dashboard_capability_blocking, dp.dashboard_operation, dp.dashboard_recovery
    elif target == "readiness":
        blocked, owned, recovery = rp.readiness_capability_blocking, rp.readiness_operation, rp.readiness_recovery
    else:
        return False
    return (
        blocked
        and owned == operation
        and recovery is not None
        and recovery.operation == operation
        and (
            recovery.epoch,
            recovery.head,
            recovery.base_head,
            recovery.policy_digest,
        )
        == (a.epoch, a.head, a.base_head, a.policy_digest)
    )


def _recover_publication(binding, outputs):
    cp, dp, rp, value = _values(
        binding, ConversationPublicationState, DashboardPublicationState, ReadinessPublicationState, Intent
    )
    target = value.arguments["target"]
    if target == "conversation":
        request = cp.conversation_recovery
        cp = cp.validated_update(conversation_capability_blocking=False)
        routed = {"conversation_publication_state": cp, "work.conversation_reply": request}
    elif target == "dashboard":
        request = dp.dashboard_recovery
        dp = dp.validated_update(dashboard_capability_blocking=False)
        routed = {"dashboard_publication_state": dp, "work.dashboard": request}
    else:
        request = rp.readiness_recovery
        rp = rp.validated_update(readiness_capability_blocking=False)
        routed = {"readiness_publication_state": rp, "command.readiness": request}
    return _route(outputs, routed)


def conversation_work(
    a: Authority,
    ac: ActionsState,
    r: ReviewState,
    h: HumanState,
    m: MutationState,
    fp: FindingPublicationState,
    cp: ConversationPublicationState,
    dp: DashboardPublicationState,
    rp: ReadinessPublicationState,
    value: ConversationObservation,
) -> ConversationClassificationRequest:
    snapshot = _snapshot(a, ac, r, h, m, fp, cp, dp, rp)
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
        FindingPublicationState,
        ConversationPublicationState,
        DashboardPublicationState,
        ReadinessPublicationState,
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
    a, ac, r, h, m, fp, cp, p, rp = _values(
        binding,
        Authority,
        ActionsState,
        ReviewState,
        HumanState,
        MutationState,
        FindingPublicationState,
        ConversationPublicationState,
        DashboardPublicationState,
        ReadinessPublicationState,
    )
    before = _snapshot(a, ac, r, h, m, fp, cp, p, rp)
    projection = dashboard_projection_digest(a, ac, r, h, m, fp, cp, p, rp)
    payload = effect_payload(a, {"control": before.dump(), "projection": projection})
    op = operation("dashboard", a, payload=payload)
    p = p.validated_update(
        dashboard_requested=True,
        dashboard_operation=op,
        dashboard_requested_projection=projection,
    )
    after = _snapshot(a, ac, r, h, m, fp, cp, p, rp)
    work = DashboardPublicationRequest(
        epoch=a.epoch, head=a.head, operation=op, base_head=a.base_head, policy_digest=a.policy_digest, control=after
    )
    p = p.validated_update(dashboard_recovery=work)
    return _route(
        outputs,
        {
            "dashboard_publication_state": p,
            "work.dashboard": work,
        },
    )


def _announce(binding, outputs):
    a, ac, r, h, m, fp, cp, dp, p = _values(
        binding,
        Authority,
        ActionsState,
        ReviewState,
        HumanState,
        MutationState,
        FindingPublicationState,
        ConversationPublicationState,
        DashboardPublicationState,
        ReadinessPublicationState,
    )
    projection = dashboard_projection_digest(a, ac, r, h, m, fp, cp, dp, p)
    op = operation("readiness", a, payload={"projection": projection})
    p = p.validated_update(readiness_requested=True, readiness_operation=op)
    work = ReadinessCommand(
        epoch=a.epoch, head=a.head, operation=op, base_head=a.base_head, policy_digest=a.policy_digest
    )
    p = p.validated_update(readiness_recovery=work)
    return _route(
        outputs,
        {
            "readiness_publication_state": p,
            "command.readiness": work,
        },
    )


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


def build_net(reminder_delay: float = 3 * 24 * 60 * 60) -> BuiltNet:
    net = NetSpec("pr-readiness-concerns")
    p, t = net.p, net.t
    work, execute, retire, reminder, command = (
        net.s.work,
        net.s.execute,
        net.s.retire,
        net.s.reminder,
        net.s.command,
    )
    # External observations enter exact typed places; Activities bridge only
    # their matching request and result places.
    t.verified_admission >> p.admission(Admission)
    t.begin_generation >> p.generation_start(GenerationStart)
    t.end_generation >> p.generation_stop(GenerationStop)
    t.commit_generation >> p.generation_commit(GenerationCommit)
    t.human_observation >> p.human_result(HumanObservation)
    t.actions_observation >> p.actions_result(ActionsObservation)
    t.conversation_observation >> p.conversation_basis(ConversationObservation)
    work.p.review(ReviewRequest) >> execute.t.review(handler="review") >> p.review_result(ReviewResult)
    (
        work.p.actions_discovery(ActionsDiscoveryRequest)
        >> execute.t.actions_discovery(handler="actions_discovery")
        >> p.actions_result
    )
    (work.p.actions_rerun(ActionsRerunRequest) >> execute.t.actions_rerun(handler="actions_rerun") >> p.actions_result)
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
    # Generation boundaries create or replace the complete concern cohort.
    cohort = (
        p.authority(Authority),
        p.actions_state(ActionsState),
        p.review_state(ReviewState),
        p.human_state(HumanState),
        p.mutation_state(MutationState),
        p.finding_publication_state(FindingPublicationState),
        p.conversation_publication_state(ConversationPublicationState),
        p.dashboard_publication_state(DashboardPublicationState),
        p.readiness_publication_state(ReadinessPublicationState),
    )
    generation = net.s.generation
    for name, prior, prior_type, relation in (
        ("initial", p.seed(Seed), Seed, "new"),
        ("resume", p.dormant(Dormant), Dormant, "resumed"),
    ):
        transition = getattr(generation.t, name)(
            handler=petri_handler(_begin_generation),
            guards=_typed_guard(
                (prior_type, GenerationStart, GenerationCommit),
                lambda control, start, commit, expected=relation: (
                    _subject(control, start)
                    and start.relation == expected
                    and commit.boundary == "start"
                    and commit.generation == start.generation
                ),
            ),
        )
        (
            (prior, p.generation_start, p.generation_commit)
            >> transition
            >> (
                *cohort,
                work.p.review,
                work.p.actions_discovery,
                reminder.p.timer(Reminder),
            )
        )
    (
        (p.generation_start, p.generation_commit)
        >> generation.t.supersede(
            handler=petri_handler(_begin_generation),
            guards=_typed_guard(
                (GenerationStart, GenerationCommit),
                lambda start, commit: (
                    start.relation in {"confirmed", "superseded"}
                    and commit.boundary == "start"
                    and commit.generation == start.generation
                ),
            ),
        )
        >> (*cohort, work.p.review, work.p.actions_discovery, reminder.p.timer)
    )
    (
        (p.generation_stop, p.generation_commit)
        >> generation.t.stop_active(
            handler=petri_handler(_route_generation_stop),
            guards=_typed_guard(
                (GenerationStop, GenerationCommit),
                lambda stop, commit: stop.active and commit.boundary == "stop" and commit.generation == stop.generation,
            ),
        )
        >> (p.dormant, p.terminal)
    )
    (
        (p.dormant, p.generation_stop, p.generation_commit)
        >> generation.t.stop_dormant(
            handler=petri_handler(_route_generation_stop),
            guards=_typed_guard(
                (Dormant, GenerationStop, GenerationCommit),
                lambda dormant, stop, commit: (
                    not stop.active
                    and stop.status in {"merged", "closed"}
                    and _subject(dormant, stop)
                    and dormant.last_epoch == stop.last_epoch
                    and commit.boundary == "stop"
                    and commit.generation == stop.generation
                ),
            ),
        )
        >> p.terminal
    )
    (
        (p.seed, p.generation_stop, p.generation_commit)
        >> generation.t.stop_seed(
            handler=petri_handler(_route_generation_stop),
            guards=_typed_guard(
                (Seed, GenerationStop, GenerationCommit),
                lambda seed, stop, commit: (
                    not stop.active
                    and stop.last_epoch == 0
                    and _subject(seed, stop)
                    and commit.boundary == "stop"
                    and commit.generation == stop.generation
                ),
            ),
        )
        >> (p.dormant, p.terminal)
    )
    (
        (
            p.authority,
            p.actions_state,
            p.review_state,
            p.finding_publication_state,
            p.conversation_publication_state,
            p.dashboard_publication_state,
            p.readiness_publication_state,
            p.admission,
        )
        >> t.refresh_basis(
            handler=petri_handler(_refresh_basis),
            guards=_typed_guard((Authority, Admission), lambda a, ad: _same(a, ad) and not _same_basis(a, ad)),
        )
        >> (
            p.authority,
            p.actions_state,
            p.review_state,
            p.finding_publication_state,
            p.conversation_publication_state,
            p.dashboard_publication_state,
            p.readiness_publication_state,
            work.p.review,
            work.p.actions_discovery,
        )
    )
    refresh = t.refresh_admission(
        handler=petri_handler(_refresh_admission),
        guards=_typed_guard(
            (Authority, ReviewState, Admission),
            lambda a, r, ad: _same_basis(a, ad) and not _retryable_review(a, r, ad),
        ),
    )
    p.review_state >> arc.read() >> refresh
    (p.authority, p.admission) >> refresh >> p.authority
    # Retry precedence is encoded by competition plus the refresh guard below.
    (
        (p.authority, p.review_state, p.admission)
        >> t.retry_review(
            handler=petri_handler(_retry_review),
            guards=_typed_guard((Authority, ReviewState, Admission), _retryable_review),
        )
        >> (p.authority, p.review_state, work.p.review)
    )
    # Routine observations fold only into the concern tokens they own.
    accept_actions = t.accept_actions(
        handler=petri_handler(_accept_actions),
        guards=_typed_guard((Authority, ActionsState, ActionsObservation), _new_actions),
    )
    p.authority >> arc.read() >> accept_actions
    (p.actions_state, p.actions_result) >> accept_actions >> (p.actions_state, p.actions_basis(ActionsObservation))
    accept_human = t.accept_human(handler=_accept_human, guards=_guard(lambda a, h, v: _current(a, v)))
    p.authority >> arc.read() >> accept_human
    (p.human_state, p.human_result) >> accept_human >> p.human_state
    accept_review = t.accept_review(
        handler=petri_handler(_accept_review),
        guards=_typed_guard((Authority, ReviewState, ReviewResult), _review_matches),
    )
    p.authority >> arc.read() >> accept_review
    (
        (p.review_state, p.finding_publication_state, p.review_result)
        >> accept_review
        >> (
            p.review_state,
            p.finding_publication_state,
            work.p.finding,
        )
    )
    accept_finding = t.accept_finding(
        handler=petri_handler(_finding_effect), guards=_guard(lambda a, r, pub, v: _effect_matches(a, pub, v))
    )
    p.authority >> arc.read() >> accept_finding
    (
        (p.review_state, p.finding_publication_state, p.finding_result)
        >> accept_finding
        >> (
            p.review_state,
            p.finding_publication_state,
        )
    )
    authorize_change = t.authorize_change(
        handler=petri_handler(_authorize_change),
        guards=_typed_guard((Authority, MutationState, Intent), _mutation),
    )
    p.authority >> arc.read() >> authorize_change
    (
        (p.mutation_state, p.change_basis(Intent))
        >> authorize_change
        >> (
            p.mutation_state,
            work.p.change,
        )
    )
    accept_conversation = t.accept_conversation(handler=_accept_conversation, guards=_guard(_effect_matches))
    p.authority >> arc.read() >> accept_conversation
    (p.conversation_publication_state, p.conversation_result) >> accept_conversation >> p.conversation_publication_state
    for name, owner, owner_type, place, result_type, handler in (
        (
            "dashboard",
            p.dashboard_publication_state,
            DashboardPublicationState,
            p.dashboard_result,
            DashboardPublicationResult,
            _accept_dashboard,
        ),
        (
            "readiness",
            p.readiness_publication_state,
            ReadinessPublicationState,
            p.readiness_result,
            ReadinessPublicationResult,
            _accept_readiness,
        ),
    ):
        tr = getattr(t, f"accept_{name}")(
            handler=handler,
            guards=_typed_guard((Authority, owner_type, result_type), _effect_matches),
        )
        p.authority >> arc.read() >> tr
        (owner, place) >> tr >> owner
    accept_reminder = t.accept_reminder(guards=_guard(lambda a, result: _current(a, result)))
    p.authority >> arc.read() >> accept_reminder
    p.reminder_result >> accept_reminder
    for name, place, result_type, handler in (
        ("repair", p.repair_result, RepairResult, _accept_repair),
        ("change", p.change_result, ChangeResult, _accept_change),
    ):
        tr = getattr(t, f"accept_{name}")(
            handler=handler,
            guards=_typed_guard(
                (Authority, MutationState, result_type),
                lambda authority, mutation, result: _effect_matches(authority, mutation, result),
            ),
        )
        p.authority >> arc.read() >> tr
        if result_type is RepairResult:
            p.actions_state >> arc.read() >> tr
        (p.mutation_state, place) >> tr >> p.mutation_state

    rerun = t.authorize_rerun(
        handler=petri_handler(_rerun),
        guards=_guard(lambda a, m, s, v: _first_failure(a, s, m, v)),
    )
    (p.authority, p.mutation_state) >> arc.read() >> rerun
    ((p.actions_state, p.actions_basis) >> rerun >> (p.actions_state, work.p.actions_rerun))
    repair_work = t.authorize_repair(
        handler=petri_handler(_repair),
        guards=_guard(lambda a, s, m, v: _repairable(a, s, m, v)),
    )
    (p.authority, p.actions_state) >> arc.read() >> repair_work
    ((p.mutation_state, p.actions_basis) >> repair_work >> (p.mutation_state, work.p.repair))
    basis_retire = retire.t.actions_basis(
        guards=_typed_guard((Authority, ActionsState, MutationState, ActionsObservation), _basis_done)
    )
    for place in (p.authority, p.actions_state, p.mutation_state):
        place >> arc.read() >> basis_retire
    p.actions_basis >> basis_retire
    # Conversation classification fans exact intents into independent mutation,
    # disposition, reminder, and reply paths.
    start = t.start_conversation(
        handler=petri_handler(_conversation_work),
        guards=_typed_guard(
            (Authority, ConversationObservation), lambda a, value: _current(a, value) and value.authorized
        ),
    )
    for place in cohort:
        place >> arc.read() >> start
    p.conversation_basis >> start >> work.p.conversation
    (
        p.intent_batch
        >> t.unpack_intents(handler=petri_handler(_unpack_intents))
        >> (p.change_basis, p.intent_result(Intent), p.reply_basis(Intent), p.recovery_basis(Intent))
    )
    for name, owner_type, owner, kinds in (
        ("finding_intent", ReviewState, p.review_state, {"acknowledge", "dismiss", "defer"}),
        ("reminder_intent", HumanState, p.human_state, {"snooze", "resume", "reassign"}),
    ):
        tr = getattr(t, f"accept_{name}")(
            handler=petri_handler(lambda b, o, typ=owner_type: _accept_intent(b, o, typ)),
            guards=_guard(
                lambda a, state, value, selected=kinds: (
                    _current(a, value) and value.authorized and value.kind in selected
                )
            ),
        )
        p.authority >> arc.read() >> tr
        (owner, p.intent_result) >> tr >> owner
    authorize_reply = t.authorize_reply(
        handler=petri_handler(_authorize_reply),
        guards=_typed_guard((Authority, ConversationPublicationState, Intent), _replyable),
    )
    p.authority >> arc.read() >> authorize_reply
    (
        (p.conversation_publication_state, p.reply_basis)
        >> authorize_reply
        >> (
            p.conversation_publication_state,
            work.p.conversation_reply,
        )
    )
    recovery_owners = (
        ("conversation", p.conversation_publication_state, work.p.conversation_reply),
        ("dashboard", p.dashboard_publication_state, work.p.dashboard),
        ("readiness", p.readiness_publication_state, command.p.readiness),
    )
    recovery = net.s.recover_publication
    for target, owner, exact_work in recovery_owners:
        recover_publication = getattr(recovery.t, target)(
            handler=petri_handler(_recover_publication),
            guards=_typed_guard(
                (
                    Authority,
                    ConversationPublicationState,
                    DashboardPublicationState,
                    ReadinessPublicationState,
                    Intent,
                ),
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
    reject_recovery = retire.t.recovery_basis(
        guards=_typed_guard(
            (
                Authority,
                ConversationPublicationState,
                DashboardPublicationState,
                ReadinessPublicationState,
                Intent,
            ),
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
    # Full snapshots are relational joins only at projection/gate boundaries.
    dashboard = t.request_dashboard(
        handler=petri_handler(_dashboard),
        guards=_guard(lambda *values: _request_dashboard(_snapshot_values(*values))),
    )
    announce = t.authorize_readiness(
        handler=petri_handler(_announce),
        guards=_guard(lambda *values: ready(_snapshot_values(*values))),
    )
    for place in (*cohort[:7], cohort[8]):
        place >> arc.read() >> dashboard
    for place in cohort[:8]:
        place >> arc.read() >> announce
    (
        p.dashboard_publication_state
        >> dashboard
        >> (
            p.dashboard_publication_state,
            work.p.dashboard,
        )
    )
    (
        p.readiness_publication_state
        >> announce
        >> (
            p.readiness_publication_state,
            command.p.readiness,
        )
    )
    due = t.reminder_due(
        handler=petri_handler(_remind),
        guards=_guard(
            lambda *values: _reminder_due(
                _snapshot_values(*values), next(value for value in values if isinstance(value, Reminder))
            )
        ),
        timers=(Delay(reminder_delay),),
    )
    for place in cohort:
        place >> arc.read() >> due
    reminder.p.timer >> due >> (reminder.p.rearm(Reminder), work.p.reminder)
    reminder.p.rearm >> t.rearm(handler=_rearm) >> reminder.p.timer
    # Lifecycle scopes discard generation-owned queued work and fence in-flight
    # Activities. The remaining retirement routes are same-generation business
    # ownership checks, not lifecycle cleanup.
    # Result envelopes retire against the exact operation owned by their concern;
    # these guards cover both stale authority and same-generation supersession.
    for name, place, owner, predicate in (
        ("review_operation", p.review_result, p.review_state, lambda a, owner, v: not _review_matches(a, owner, v)),
        ("actions_operation", p.actions_result, p.actions_state, lambda a, owner, v: _duplicate_actions(a, owner, v)),
        (
            "finding_operation",
            p.finding_result,
            p.finding_publication_state,
            lambda a, owner, v: not _effect_matches(a, owner, v),
        ),
        (
            "dashboard_operation",
            p.dashboard_result,
            p.dashboard_publication_state,
            lambda a, owner, v: not _effect_matches(a, owner, v),
        ),
        (
            "readiness_operation",
            p.readiness_result,
            p.readiness_publication_state,
            lambda a, owner, v: not _effect_matches(a, owner, v),
        ),
        (
            "conversation_operation",
            p.conversation_result,
            p.conversation_publication_state,
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
        ("reply_basis", p.reply_basis, lambda a, v: not _valid_reply(a, v)),
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
    return net.build()
