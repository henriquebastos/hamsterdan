"""JSON-faithful values for the replacement PR-readiness workflow."""

from __future__ import annotations

import json
from dataclasses import field
from typing import Any, Literal

from pydantic import ConfigDict, TypeAdapter
from pydantic.dataclasses import dataclass


class WorkflowModel:
    """Strict, frozen, JSON-faithful workflow value."""

    def dump(self) -> dict[str, Any]:
        """Return the canonical JSON payload for a workflow value."""
        return TypeAdapter(type(self)).dump_python(self, mode="json")

    def validated_update(self, **changes: object):
        """Return a fully revalidated update rather than an unchecked model copy."""
        payload = self.dump() | {
            key: TypeAdapter(type(value)).dump_python(value, mode="json") if isinstance(value, WorkflowModel) else value
            for key, value in changes.items()
        }
        return TypeAdapter(type(self)).validate_json(json.dumps(payload))


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Seed(WorkflowModel):
    repository_id: str
    pr_number: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Admission(WorkflowModel):
    repository_id: str
    pr_number: int
    head: str
    base_head: str
    strict_base: bool
    base_current: bool = True
    policy_digest: str = ""
    required_checks: list[str] = field(default_factory=list)
    required_approvals: int = 0
    conversation_resolution: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class GenerationStart(WorkflowModel):
    repository_id: str
    pr_number: int
    epoch: int
    generation: int
    relation: Literal["new", "confirmed", "superseded", "resumed"]
    head: str
    base_head: str
    strict_base: bool
    base_current: bool = True
    policy_digest: str = ""
    required_checks: list[str] = field(default_factory=list)
    required_approvals: int = 0
    conversation_resolution: bool = False
    prior_findings: list[dict] = field(default_factory=list)
    prior_lineage: list[dict] = field(default_factory=list)
    repair_used: bool = False
    repair_fingerprint: str = ""


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class GenerationStop(WorkflowModel):
    repository_id: str
    pr_number: int
    last_epoch: int
    generation: int
    status: Literal["draft", "merged", "closed"]
    head: str
    active: bool


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class GenerationCommit(WorkflowModel):
    generation: int
    boundary: Literal["start", "stop"]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Authority(WorkflowModel):
    repository_id: str
    pr_number: int
    epoch: int
    head: str
    base_head: str
    strict_base: bool
    base_current: bool
    policy_digest: str = ""
    required_checks: list[str] = field(default_factory=list)
    required_approvals: int = 0
    conversation_resolution: bool = False
    admission_relation: Literal["new", "confirmed", "superseded", "same_head", "same_head_basis_changed"] = "new"


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ActionsState(WorkflowModel):
    actions: Literal[
        "discovering",
        "capability_unavailable",
        "running",
        "waiting",
        "green",
        "flaky_green",
        "failed",
        "reproduced",
        "rerun_requested",
        "queued",
        "requested",
        "canceled",
        "unavailable",
    ] = "discovering"
    run_id: str = ""
    attempt: int = 0
    rerun_requested: bool = False
    rerun_attempt: int = 0
    fingerprint: str = ""
    actions_observation: str = ""
    actions_operation: str = ""
    actions_capability_blocking: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewState(WorkflowModel):
    review: Literal["pending", "clear", "blocking", "unable"] = "pending"
    findings: list[dict] = field(default_factory=list)
    finding_lineage: list[dict] = field(default_factory=list)
    review_operation: str = ""
    review_attempts: int = 0


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HumanState(WorkflowModel):
    observation_sequence: int = 0
    human_requested: bool = False
    human_approved: bool = False
    changes_requested: bool = False
    unresolved_conversations: int = 0
    distinct_reviewer_required: bool = False
    distinct_reviewer_approved: bool = False
    mergeable: bool = False
    conflict: bool = False
    reminder_snoozed: bool = False
    reminder_recipient: str = ""
    author: str = ""
    human_capability_blocking: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MutationState(WorkflowModel):
    provisional_head: str = ""
    repair_lineage: str = ""
    repair_used: bool = False
    repair_fingerprint: str = ""
    provisional: bool = False
    change_in_flight: bool = False
    repair_in_flight: bool = False
    repair_recovery_required: bool = False
    mutation_operation: str = ""


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class FindingPublicationState(WorkflowModel):
    findings_published: bool = False
    finding_publication_requested: bool = False
    finding_operation: str | None = None
    finding_capability_blocking: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ConversationPublicationState(WorkflowModel):
    conversation_requested: bool = False
    conversation_operation: str | None = None
    conversation_recovery: ConversationPublicationRequest | None = None
    conversation_capability_blocking: bool = False
    conversation_publication_fault: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashboardPublicationState(WorkflowModel):
    dashboard_projection: str = ""
    dashboard_requested_projection: str = ""
    dashboard_requested: bool = False
    dashboard_operation: str | None = None
    dashboard_recovery: DashboardPublicationRequest | None = None
    dashboard_format: int = 0
    dashboard_capability_blocking: bool = False
    dashboard_publication_fault: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReadinessPublicationState(WorkflowModel):
    readiness_capability_blocking: bool = False
    readiness_publication_fault: bool = False
    readiness_operation: str | None = None
    readiness_recovery: ReadinessCommand | None = None
    readiness_requested: bool = False
    announced: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReadinessSnapshot(WorkflowModel):
    repository_id: str
    pr_number: int
    epoch: int
    head: str
    base_head: str
    strict_base: bool
    base_current: bool
    policy_digest: str = ""
    required_checks: list[str] = field(default_factory=list)
    required_approvals: int = 0
    conversation_resolution: bool = False
    admission_relation: Literal["new", "confirmed", "superseded", "same_head", "same_head_basis_changed"] = "new"
    provisional_head: str = ""
    actions: Literal[
        "discovering",
        "capability_unavailable",
        "running",
        "waiting",
        "green",
        "flaky_green",
        "failed",
        "reproduced",
        "rerun_requested",
        "queued",
        "requested",
        "canceled",
        "unavailable",
    ] = "discovering"
    run_id: str = ""
    attempt: int = 0
    rerun_requested: bool = False
    rerun_attempt: int = 0
    fingerprint: str = ""
    repair_lineage: str = ""
    repair_used: bool = False
    repair_fingerprint: str = ""
    actions_observation: str = ""
    review: Literal["pending", "clear", "blocking", "unable"] = "pending"
    findings: list[dict] = field(default_factory=list)
    finding_lineage: list[dict] = field(default_factory=list)
    findings_published: bool = False
    finding_publication_requested: bool = False
    observation_sequence: int = 0
    human_requested: bool = False
    human_approved: bool = False
    changes_requested: bool = False
    unresolved_conversations: int = 0
    distinct_reviewer_required: bool = False
    distinct_reviewer_approved: bool = False
    mergeable: bool = False
    conflict: bool = False
    provisional: bool = False
    change_in_flight: bool = False
    repair_in_flight: bool = False
    repair_recovery_required: bool = False
    dashboard_current: bool = False
    dashboard_projection: str = ""
    dashboard_requested_projection: str = ""
    dashboard_requested: bool = False
    dashboard_operation: str | None = None
    dashboard_format: int = 0
    conversation_requested: bool = False
    conversation_operation: str | None = None
    conversation_capability_blocking: bool = False
    conversation_publication_fault: bool = False
    review_operation: str = ""
    review_attempts: int = 0
    actions_operation: str = ""
    finding_operation: str | None = None
    mutation_operation: str = ""
    reminder_snoozed: bool = False
    reminder_recipient: str = ""
    author: str = ""
    actions_capability_blocking: bool = False
    human_capability_blocking: bool = False
    dashboard_capability_blocking: bool = False
    dashboard_publication_fault: bool = False
    finding_capability_blocking: bool = False
    readiness_capability_blocking: bool = False
    readiness_publication_fault: bool = False
    readiness_operation: str | None = None
    readiness_requested: bool = False
    announced: bool = False
    wait: str = "actions, coordinating review, and human review"


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Dormant(WorkflowModel):
    repository_id: str
    pr_number: int
    last_epoch: int
    head: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Terminal(WorkflowModel):
    status: Literal["success", "abort"]
    last_epoch: int
    head: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str
    strict_base: bool
    base_current: bool
    policy: dict
    prior_findings: list[dict]
    prior_lineage: list[dict]
    sequence: int = 0


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ActionsDiscoveryRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ActionsRerunRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str
    actions: ActionsObservation


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewResult(WorkflowModel):
    epoch: int
    head: str
    status: Literal["clear", "blocking", "unable"]
    findings: list[dict]
    lineage: list[dict]
    operation: str = ""


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ActionsObservation(WorkflowModel):
    epoch: int
    head: str
    run_id: str
    attempt: int
    conclusion: Literal[
        "unavailable", "queued", "requested", "waiting", "in_progress", "success", "failure", "canceled"
    ]
    fingerprint: str = ""
    capability_available: bool = True
    observation: str = ""
    operation: str = ""
    base_head: str = ""
    policy_digest: str = ""

    def __post_init__(self) -> None:
        if not self.observation:
            object.__setattr__(self, "observation", f"{self.run_id}:{self.attempt}:{self.conclusion}")


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HumanObservation(WorkflowModel):
    epoch: int
    head: str
    requested: bool
    approved: bool
    changes_requested: bool
    unresolved_conversations: int
    distinct_required: bool
    distinct_approved: bool
    mergeable: bool
    conflict: bool
    base_current: bool
    reviewer: str = ""
    author: str = ""
    capability_available: bool = True


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class AdmittedConversation(WorkflowModel):
    delivery_id: str
    comment_id: int
    actor_id: int
    actor_login: str
    association: str
    text: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ConversationObservation(WorkflowModel):
    epoch: int
    head: str
    authorized: bool
    text: str
    comment_id: int = 0
    actor_id: int = 0
    actor_login: str = ""
    association: str = ""


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Intent(WorkflowModel):
    epoch: int
    head: str
    kind: Literal[
        "reply",
        "status",
        "acknowledge",
        "dismiss",
        "defer",
        "snooze",
        "resume",
        "reassign",
        "change",
        "update_base",
        "resolve_conflict",
        "recover_publication",
    ]
    digest: str
    authorized: bool
    blocking: bool
    arguments: dict = field(default_factory=dict)
    base_head: str = ""
    policy_digest: str = ""


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class IntentBatch(WorkflowModel):
    epoch: int
    head: str
    intents: list[Intent]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ConversationClassificationRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str
    comment: ConversationObservation
    control: ReadinessSnapshot


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ConversationPublicationRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str
    intent: Intent


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class FindingPublicationRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str
    findings: list[dict]
    lineage: list[dict]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ChangeRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str
    intent: Intent
    lineage: list[dict] = field(default_factory=list)


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RepairRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str
    actions: ActionsObservation
    lineage: list[dict] = field(default_factory=list)


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashboardPublicationRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str
    control: ReadinessSnapshot


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReminderPublicationRequest(WorkflowModel):
    epoch: int
    head: str
    operation: str
    base_head: str
    policy_digest: str
    sequence: int
    reviewer: str
    author: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ConversationPublicationResult(WorkflowModel):
    epoch: int
    head: str
    ok: bool
    operation: str = ""
    capability_available: bool = True
    faulted: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class FindingPublicationResult(WorkflowModel):
    epoch: int
    head: str
    ok: bool
    operation: str = ""
    capability_available: bool = True
    references: list[dict] = field(default_factory=list)


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ChangeResult(WorkflowModel):
    epoch: int
    head: str
    ok: bool
    provisional_head: str = ""
    fingerprint: str = ""
    lineage: str = ""
    operation: str = ""
    publication_category: str = ""
    agent_result_category: str = ""
    agent_cleanup_category: str = ""


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RepairResult(WorkflowModel):
    epoch: int
    head: str
    ok: bool
    provisional_head: str = ""
    fingerprint: str = ""
    lineage: str = ""
    operation: str = ""
    publication_category: str = ""
    agent_result_category: str = ""
    agent_cleanup_category: str = ""


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashboardPublicationResult(WorkflowModel):
    epoch: int
    head: str
    ok: bool
    operation: str = ""
    capability_available: bool = True
    faulted: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReminderPublicationResult(WorkflowModel):
    epoch: int
    head: str
    ok: bool
    operation: str = ""
    capability_available: bool = True


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReadinessPublicationResult(WorkflowModel):
    epoch: int
    head: str
    ok: bool
    operation: str = ""
    capability_available: bool = True
    faulted: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Reminder(WorkflowModel):
    epoch: int
    head: str
    sequence: int = 0


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReadinessCommand(WorkflowModel):
    epoch: int
    head: str
    operation: str = ""
    base_head: str = ""
    policy_digest: str = ""


def workflow_wait(control: ReadinessSnapshot) -> str:
    """Project the single highest-priority external wait from current gates."""
    if control.provisional:
        return "verified head admission"
    if control.conflict:
        return "conflict resolution"
    if control.change_in_flight:
        return "change result"
    if control.repair_in_flight:
        return "repair result"
    if control.repair_recovery_required:
        return "repair recovery"
    if control.actions_capability_blocking:
        return "Actions capability"
    if control.actions not in {"green", "flaky_green"}:
        return {
            "failed": "same-head rerun",
            "reproduced": "human repair authorization" if control.repair_used else "repair",
            "capability_unavailable": "Actions capability",
        }.get(control.actions, "GitHub Actions")
    if control.review == "pending":
        return "coordinating agent review"
    if control.review == "unable":
        return "coordinating review capability"
    if control.review == "blocking":
        return "finding disposition or change"
    if not control.findings_published:
        return "finding publication"
    if control.changes_requested:
        return "requested changes"
    if control.unresolved_conversations:
        return "conversation resolution"
    if control.human_capability_blocking:
        return "human-review capability"
    if not control.human_approved or (control.distinct_reviewer_required and not control.distinct_reviewer_approved):
        return "human review"
    if control.strict_base and not control.base_current:
        return "base update"
    if not control.mergeable:
        return "GitHub mergeability"
    if control.finding_capability_blocking:
        return "finding publication capability"
    if control.dashboard_publication_fault:
        return "dashboard publication fault"
    if control.dashboard_capability_blocking:
        return "dashboard update capability"
    if control.conversation_publication_fault:
        return "conversation publication fault"
    if control.conversation_capability_blocking:
        return "conversation reply capability"
    if control.readiness_publication_fault:
        return "readiness publication fault"
    if control.readiness_capability_blocking:
        return "readiness publication capability"
    return "terminal lifecycle"


def project_readiness(
    authority: Authority,
    actions: ActionsState,
    review: ReviewState,
    human: HumanState,
    mutation: MutationState,
    finding_publication: FindingPublicationState,
    conversation_publication: ConversationPublicationState,
    dashboard_publication: DashboardPublicationState,
    readiness_publication: ReadinessPublicationState,
) -> ReadinessSnapshot:
    """Merge independently owned state and derive its current external wait."""
    values: dict[str, Any] = {
        **authority.dump(),
        **actions.dump(),
        **review.dump(),
        **human.dump(),
        **mutation.dump(),
        **finding_publication.dump(),
        **{key: value for key, value in conversation_publication.dump().items() if key != "conversation_recovery"},
        **{key: value for key, value in dashboard_publication.dump().items() if key != "dashboard_recovery"},
        **{key: value for key, value in readiness_publication.dump().items() if key != "readiness_recovery"},
    }
    values["dashboard_current"] = (
        dashboard_projection_digest(
            authority,
            actions,
            review,
            human,
            mutation,
            finding_publication,
            conversation_publication,
            dashboard_publication,
            readiness_publication,
        )
        == dashboard_publication.dashboard_projection
        and not dashboard_publication.dashboard_requested
    )
    snapshot = ReadinessSnapshot(**values)
    return snapshot.validated_update(wait=workflow_wait(snapshot))


def dashboard_projection_digest(
    authority: Authority,
    actions: ActionsState,
    review: ReviewState,
    human: HumanState,
    mutation: MutationState,
    finding_publication: FindingPublicationState,
    conversation_publication: ConversationPublicationState,
    dashboard_publication: DashboardPublicationState,
    readiness_publication: ReadinessPublicationState,
) -> str:
    """Return the canonical identity of facts rendered by readiness/dashboard views."""
    import hashlib
    import json

    excluded = {
        "observation_sequence",
        "dashboard_projection",
        "dashboard_requested_projection",
        "dashboard_requested",
        "dashboard_operation",
        "dashboard_recovery",
        "conversation_recovery",
        "readiness_recovery",
        "dashboard_format",
    }
    facts = {
        key: value
        for concern in (
            authority,
            actions,
            review,
            human,
            mutation,
            finding_publication,
            conversation_publication,
            dashboard_publication,
            readiness_publication,
        )
        for key, value in concern.dump().items()
        if key not in excluded
    }
    canonical = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def workflow_gates_ready(control: ReadinessSnapshot) -> bool:
    """Evaluate readiness gates that do not depend on publishing their projection."""
    findings_clear = control.review == "clear" and not any(
        finding.get("blocking") and finding.get("disposition") in {"new", "still_open"} for finding in control.findings
    )
    return all(
        (
            control.actions in {"green", "flaky_green"},
            findings_clear,
            control.findings_published,
            control.human_approved,
            not control.changes_requested,
            control.unresolved_conversations == 0,
            not control.distinct_reviewer_required or control.distinct_reviewer_approved,
            control.base_current or not control.strict_base,
            control.mergeable,
            not control.conflict,
            not any(
                (
                    control.provisional,
                    control.change_in_flight,
                    control.repair_in_flight,
                )
            ),
            not control.actions_capability_blocking,
            not control.human_capability_blocking,
            not control.dashboard_capability_blocking,
            not control.dashboard_publication_fault,
            not control.finding_capability_blocking,
            not control.conversation_capability_blocking,
            not control.conversation_publication_fault,
            not control.readiness_capability_blocking,
            not control.readiness_publication_fault,
        )
    )
