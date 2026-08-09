"""JSON-faithful values for the replacement PR-readiness workflow."""

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
        return type(self)(**(self.dump() | changes))


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
class Lifecycle(WorkflowModel):
    status: Literal["draft", "merged", "closed"]
    head: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Control(WorkflowModel):
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
    revision: int = 0
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
    dashboard_requested: bool = False
    dashboard_operation: str = ""
    dashboard_format: int = 0
    conversation_pending: dict = field(default_factory=dict)
    conversation_attempts: int = 0
    conversation_capability_blocking: bool = False
    review_operation: str = ""
    review_attempts: int = 0
    actions_operation: str = ""
    finding_operation: str = ""
    mutation_operation: str = ""
    reminder_snoozed: bool = False
    reminder_recipient: str = ""
    author: str = ""
    actions_capability_blocking: bool = False
    human_capability_blocking: bool = False
    dashboard_capability_blocking: bool = False
    finding_capability_blocking: bool = False
    readiness_capability_blocking: bool = False
    readiness_operation: str = ""
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
class Work(WorkflowModel):
    kind: Literal[
        "review",
        "actions_discovery",
        "actions_rerun",
        "finding",
        "conversation",
        "change",
        "repair",
        "dashboard",
        "reminder",
    ]
    epoch: int
    head: str
    operation: str = ""
    sequence: int = 0
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.operation:
            object.__setattr__(self, "operation", f"{self.kind}:{self.epoch}:{self.head}:{self.sequence}")


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
    intents: list[dict]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class EffectResult(WorkflowModel):
    kind: Literal["finding", "conversation", "change", "repair", "dashboard", "reminder", "readiness"]
    epoch: int
    head: str
    ok: bool
    provisional_head: str = ""
    fingerprint: str = ""
    lineage: str = ""
    operation: str = ""
    capability_available: bool = True
    references: list[dict] = field(default_factory=list)
    publication_category: str = ""
    agent_result_category: str = ""
    agent_cleanup_category: str = ""


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


def workflow_wait(control: Control) -> str:
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
    if control.dashboard_capability_blocking:
        return "dashboard update capability"
    if control.conversation_capability_blocking:
        return "conversation reply capability"
    if control.readiness_capability_blocking:
        return "readiness publication capability"
    return "terminal lifecycle"


def update(control: Control, *, preserve_dashboard_request: bool = False, **changes: object) -> Control:
    """Update authority, invalidate its projection, and normalize its external wait."""
    changes.setdefault("revision", control.revision + 1)
    changes.setdefault("dashboard_current", False)
    if not preserve_dashboard_request:
        changes.setdefault("dashboard_requested", False)
        changes.setdefault("dashboard_operation", "")
    changed = control.validated_update(**changes)
    if "wait" not in changes:
        changed = changed.validated_update(wait=workflow_wait(changed))
    return changed


def workflow_gates_ready(control: Control) -> bool:
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
            not control.finding_capability_blocking,
            not control.conversation_capability_blocking,
            not control.readiness_capability_blocking,
        )
    )
