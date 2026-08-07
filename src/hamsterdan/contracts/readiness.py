"""JSON-faithful values for the replacement PR-readiness workflow."""

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Seed:
    repository_id: str
    pr_number: int


@dataclass(frozen=True)
class Admission:
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


@dataclass(frozen=True)
class Lifecycle:
    status: str
    head: str


@dataclass(frozen=True)
class Control:
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
    admission_relation: str = "new"
    provisional_head: str = ""
    actions: str = "discovering"
    run_id: str = ""
    attempt: int = 0
    rerun_requested: bool = False
    rerun_attempt: int = 0
    fingerprint: str = ""
    repair_lineage: str = ""
    repair_used: bool = False
    repair_fingerprint: str = ""
    actions_observation: str = ""
    review: str = "pending"
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
    mutation_pending: bool = False
    pending_intent_digest: str = ""
    pending_intent: dict = field(default_factory=dict)
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


@dataclass(frozen=True)
class Dormant:
    repository_id: str
    pr_number: int
    last_epoch: int
    head: str


@dataclass(frozen=True)
class Terminal:
    status: str
    last_epoch: int
    head: str


@dataclass(frozen=True)
class Work:
    kind: str
    epoch: int
    head: str
    operation: str = ""
    sequence: int = 0
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.operation:
            object.__setattr__(self, "operation", f"{self.kind}:{self.epoch}:{self.head}:{self.sequence}")


@dataclass(frozen=True)
class ReviewResult:
    epoch: int
    head: str
    status: str
    findings: list[dict]
    lineage: list[dict]
    operation: str = ""


@dataclass(frozen=True)
class ActionsObservation:
    epoch: int
    head: str
    run_id: str
    attempt: int
    conclusion: str
    fingerprint: str = ""
    capability_available: bool = True
    observation: str = ""
    operation: str = ""
    base_head: str = ""
    policy_digest: str = ""

    def __post_init__(self) -> None:
        if not self.observation:
            object.__setattr__(self, "observation", f"{self.run_id}:{self.attempt}:{self.conclusion}")


@dataclass(frozen=True)
class HumanObservation:
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


@dataclass(frozen=True)
class ConversationObservation:
    epoch: int
    head: str
    authorized: bool
    text: str
    comment_id: int = 0
    actor_id: int = 0
    actor_login: str = ""
    association: str = ""


@dataclass(frozen=True)
class Intent:
    epoch: int
    head: str
    kind: str
    digest: str
    authorized: bool
    confirmed: bool
    blocking: bool
    arguments: dict = field(default_factory=dict)
    base_head: str = ""
    policy_digest: str = ""


@dataclass(frozen=True)
class IntentBatch:
    epoch: int
    head: str
    intents: list[dict]


@dataclass(frozen=True)
class EffectResult:
    kind: str
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


@dataclass(frozen=True)
class Reminder:
    epoch: int
    head: str
    sequence: int = 0


@dataclass(frozen=True)
class ReadinessCommand:
    epoch: int
    head: str
    operation: str = ""
    base_head: str = ""
    policy_digest: str = ""


def workflow_wait(control: Control) -> str:
    """Project the single highest-priority external wait from current gates."""
    if control.provisional:
        return "verified head admission"
    if control.mutation_pending:
        return "mutation confirmation"
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
    changed = replace(control, **changes)
    if "wait" not in changes:
        changed = replace(changed, wait=workflow_wait(changed))
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
                    control.mutation_pending,
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
