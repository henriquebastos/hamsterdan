"""Independent expected-readiness model for deterministic simulation.

This module deliberately knows only normalized external facts. It does not
import either readiness topology, Petrus, or the host projections being judged.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import field
from typing import Any, Literal, Self

from pydantic import ConfigDict, TypeAdapter
from pydantic.dataclasses import dataclass

Lifecycle = Literal["active", "draft", "merged", "closed"]
CheckStatus = Literal["queued", "running", "success", "failure", "canceled", "unavailable"]
CiRecovery = Literal["none", "automatic", "human_authorization", "blocked"]
ReviewStatus = Literal["pending", "clear", "blocking", "unable"]
FindingDisposition = Literal["open", "dismissed", "resolved"]
MutationStatus = Literal["idle", "requested", "in_flight", "accepted_pending_admission", "ambiguous", "blocked"]
ChangeIntent = Literal["change", "repair"]
EffectKind = Literal[
    "dashboard",
    "findings",
    "conversation",
    "reminder",
    "readiness",
    "rerun",
    "git_mutation",
    "agent_review",
    "coding",
]
EffectStatus = Literal["requested", "accepted", "ambiguous", "blocked", "rejected", "settled", "canceled"]
TimerStatus = Literal["scheduled", "due", "acknowledged", "canceled"]
ReadinessDisposition = Literal["ready", "progressing", "human_wait", "external_wait", "terminal", "quarantined"]
LivenessDisposition = Literal["not_applicable", "in_progress", "converged", "livelock"]


class StrictValue:
    """Frozen, strict, JSON-faithful simulation value."""

    def dump(self) -> dict[str, Any]:
        return TypeAdapter(type(self)).dump_python(self, mode="json")

    @classmethod
    def load(cls, encoded: str) -> Self:
        return TypeAdapter(cls).validate_json(encoded)


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class AuthorityClaim(StrictValue):
    """One normalized provider or admitted authority snapshot."""

    installation: int
    repository: int
    pull_request: int
    head: str
    base: str
    policy: str
    lifecycle: Lifecycle
    strict_base: bool
    base_current: bool
    mergeable: bool

    def __post_init__(self) -> None:
        if min(self.installation, self.repository, self.pull_request) <= 0:
            raise ValueError("authority identities must be positive")


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class AuthorityFacts(StrictValue):
    """Current provider truth beside the latest admitted generation."""

    generation: int
    admitted: AuthorityClaim | None
    provider: AuthorityClaim

    def __post_init__(self) -> None:
        if self.generation < 0 or (self.admitted is None) != (self.generation == 0):
            raise ValueError("generation zero must have no admitted authority")


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CheckFacts(StrictValue):
    """Latest provider truth for one policy-required CI check."""

    name: str
    status: CheckStatus


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CiFacts(StrictValue):
    head: str = ""
    required_checks: tuple[str, ...] = ()
    checks: tuple[CheckFacts, ...] = ()
    recovery: CiRecovery = "none"


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Finding(StrictValue):
    identity: str
    blocking: bool
    disposition: FindingDisposition


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewFacts(StrictValue):
    head: str = ""
    status: ReviewStatus = "pending"
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HumanFacts(StrictValue):
    approvals: int = 0
    required_approvals: int = 0
    changes_requested: bool = False
    unresolved_conversations: int = 0
    distinct_reviewer_required: bool = False
    distinct_reviewer_approved: bool = False

    def __post_init__(self) -> None:
        if min(self.approvals, self.required_approvals, self.unresolved_conversations) < 0:
            raise ValueError("human fact counts cannot be negative")


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ChangeAuthorization(StrictValue):
    """One admitted human grant for an exact operation and authority."""

    identity: str
    operation: str
    authority: AuthorityClaim
    intent: ChangeIntent
    intent_digest: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MutationFacts(StrictValue):
    status: MutationStatus = "idle"
    operation: str = ""
    head: str = ""
    result_head: str = ""
    authorization: ChangeAuthorization | None = None

    def __post_init__(self) -> None:
        if self.status != "idle" and (not self.operation or not self.head):
            raise ValueError("active mutation facts require an operation and head")
        if self.result_head and self.status not in {"accepted_pending_admission", "ambiguous"}:
            raise ValueError("only an accepted or ambiguous mutation may declare a result head")


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class EffectObligation(StrictValue):
    kind: EffectKind
    operation: str
    authority: AuthorityClaim
    content_digest: str
    status: EffectStatus
    provider_authority_at_acceptance: AuthorityClaim | None = None
    authorization: str | None = None
    blocks_readiness: bool = True

    def __post_init__(self) -> None:
        if self.status in {"accepted", "settled"} and self.provider_authority_at_acceptance is None:
            raise ValueError("accepted effects require provider authority at acceptance")


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class TimerObligation(StrictValue):
    identity: str
    status: TimerStatus
    blocks_readiness: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReadinessFacts(StrictValue):
    """Topology-neutral facts from authored world truth and admitted events."""

    subject: str
    authority: AuthorityFacts
    admitted_observations: tuple[str, ...] = ()
    ci: CiFacts = field(default_factory=CiFacts)
    review: ReviewFacts = field(default_factory=ReviewFacts)
    human: HumanFacts = field(default_factory=HumanFacts)
    mutation: MutationFacts = field(default_factory=MutationFacts)
    effects: tuple[EffectObligation, ...] = ()
    timers: tuple[TimerObligation, ...] = ()

    def __post_init__(self) -> None:
        provider = self.authority.provider
        expected = f"github:{provider.installation}:{provider.repository}:pr:{provider.pull_request}"
        if self.subject != expected:
            raise ValueError("readiness subject must match provider authority")
        admitted = self.authority.admitted
        if admitted is not None and (
            admitted.installation,
            admitted.repository,
            admitted.pull_request,
        ) != (provider.installation, provider.repository, provider.pull_request):
            raise ValueError("admitted and provider authority must describe one pull request")


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReadinessExpectation(StrictValue):
    subject: str
    generation: int
    ready: bool
    disposition: ReadinessDisposition
    blockers: tuple[str, ...]
    violations: tuple[str, ...]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class FairEnvironment(StrictValue):
    """Conditions under which exhausted progress is a runtime liveness bug."""

    generated_faults_stopped: bool
    authority_stable: bool
    workers_available: bool
    logical_time_advances: bool
    durable_stores_readable: bool

    @property
    def declared(self) -> bool:
        return all(
            (
                self.generated_faults_stopped,
                self.authority_stable,
                self.workers_available,
                self.logical_time_advances,
                self.durable_stores_readable,
            )
        )


class ReadinessModel:
    """Calculate expected readiness from independent normalized facts."""

    def evaluate(self, facts: ReadinessFacts) -> ReadinessExpectation:
        blockers = self._blockers(facts)
        violations = self._violations(facts, blockers)
        disposition = self._disposition(facts, blockers, violations)
        return ReadinessExpectation(
            subject=facts.subject,
            generation=facts.authority.generation,
            ready=disposition == "ready",
            disposition=disposition,
            blockers=blockers,
            violations=violations,
        )

    def _blockers(self, facts: ReadinessFacts) -> tuple[str, ...]:
        authority_boundary = self._authority_boundary(facts.authority)
        if authority_boundary is not None:
            return authority_boundary
        admitted = facts.authority.admitted
        if admitted is None:
            return ("current_authority_admission",)
        return (
            *self._authority_gate_blockers(admitted),
            *self._ci_blockers(facts.ci, admitted.head),
            *self._review_blockers(facts.review, admitted.head),
            *self._human_blockers(facts.human),
            *self._work_blockers(facts),
        )

    def _authority_boundary(self, authority: AuthorityFacts) -> tuple[str, ...] | None:
        admitted = authority.admitted
        if admitted is None or admitted != authority.provider:
            return ("current_authority_admission",)
        if admitted.lifecycle in {"merged", "closed"}:
            return ()
        if admitted.lifecycle == "draft":
            return ("pull_request_draft",)
        return None

    def _authority_gate_blockers(self, admitted: AuthorityClaim) -> tuple[str, ...]:
        blockers = []
        if admitted.strict_base and not admitted.base_current:
            blockers.append("current_base")
        if not admitted.mergeable:
            blockers.append("mergeability")
        return tuple(blockers)

    def _ci_blockers(self, ci: CiFacts, current_head: str) -> tuple[str, ...]:
        if ci.head != current_head:
            return ("current_ci_evidence",)
        blockers = []
        checks = {check.name: check.status for check in ci.checks}
        for name in ci.required_checks:
            status = checks.get(name)
            if status is None:
                blockers.append(f"required_ci_missing:{name}")
            elif status == "failure":
                prefix = "ci_repair_authorization" if ci.recovery == "human_authorization" else "ci_failed"
                blockers.append(f"{prefix}:{name}")
            elif status in {"unavailable", "canceled"}:
                blockers.append(f"ci_capability:{name}")
            elif status != "success":
                blockers.append(f"ci_terminal:{name}")
        return tuple(blockers)

    def _review_blockers(self, review: ReviewFacts, current_head: str) -> tuple[str, ...]:
        if review.head != current_head:
            return ("current_review_evidence",)
        if review.status == "pending":
            return ("review_pending",)
        if review.status == "unable":
            return ("review_capability",)
        if review.status == "blocking" or any(
            finding.blocking and finding.disposition == "open" for finding in review.findings
        ):
            return ("blocking_findings",)
        return ()

    def _human_blockers(self, human: HumanFacts) -> tuple[str, ...]:
        blockers = []
        if human.changes_requested:
            blockers.append("changes_requested")
        if human.unresolved_conversations:
            blockers.append("unresolved_conversations")
        if human.approvals < human.required_approvals or (
            human.distinct_reviewer_required and not human.distinct_reviewer_approved
        ):
            blockers.append("human_approval")
        return tuple(blockers)

    def _work_blockers(self, facts: ReadinessFacts) -> tuple[str, ...]:
        blockers = []
        if facts.mutation.status != "idle":
            blockers.append(
                {
                    "requested": "mutation_requested",
                    "in_flight": "mutation_in_flight",
                    "accepted_pending_admission": "mutation_admission",
                    "ambiguous": "mutation_ambiguous",
                    "blocked": "mutation_blocked",
                }[facts.mutation.status]
            )

        for effect in facts.effects:
            if effect.blocks_readiness and effect.status not in {"settled", "canceled"}:
                blockers.append(f"effect_{effect.status}:{effect.operation}")
        for timer in facts.timers:
            if timer.blocks_readiness and timer.status not in {"acknowledged", "canceled"}:
                blockers.append(f"timer_{timer.status}:{timer.identity}")
        return tuple(blockers)

    def _violations(self, facts: ReadinessFacts, blockers: tuple[str, ...]) -> tuple[str, ...]:
        return (
            *self._admission_violations(facts),
            *self._change_authorization_violations(facts),
            *self._effect_violations(facts, blockers),
        )

    def _admission_violations(self, facts: ReadinessFacts) -> tuple[str, ...]:
        violations = []
        for identity, count in sorted(Counter(facts.admitted_observations).items()):
            if count > 1:
                violations.append(f"duplicate_admission:{identity}")
        return tuple(violations)

    def _change_authorization_violations(self, facts: ReadinessFacts) -> tuple[str, ...]:
        change_effects = tuple(
            effect
            for effect in facts.effects
            if effect.kind in {"coding", "git_mutation"} and effect.status != "canceled"
        )
        if facts.mutation.status == "idle" and not change_effects:
            return ()

        operations = {effect.operation for effect in change_effects}
        if facts.mutation.status != "idle":
            operations.add(facts.mutation.operation)
        authorization = facts.mutation.authorization
        current = facts.authority.provider
        authority_is_admitted = facts.authority.admitted == current
        violations = []
        for operation in sorted(operations):
            bound_effects = tuple(effect for effect in change_effects if effect.operation == operation)
            self_push = (
                authorization is not None
                and facts.mutation.operation == operation
                and facts.mutation.status in {"accepted_pending_admission", "ambiguous"}
                and facts.mutation.result_head == current.head
                and facts.authority.admitted in {authorization.authority, current}
                and self._same_authority_except_head(authorization.authority, current)
            )
            authorized = (
                authorization is not None
                and authorization.operation == operation
                and authorization.identity in facts.admitted_observations
                and authorization.authority.lifecycle == "active"
                and ((authorization.authority == current and authority_is_admitted) or self_push)
                and all(
                    effect.authority == authorization.authority and effect.authorization == authorization.identity
                    for effect in bound_effects
                )
                and (
                    facts.mutation.status == "idle"
                    or facts.mutation.operation != operation
                    or facts.mutation.head == authorization.authority.head
                )
            )
            if not authorized:
                violations.append(f"unauthorized_change:{operation}")
        return tuple(violations)

    @staticmethod
    def _same_authority_except_head(left: AuthorityClaim, right: AuthorityClaim) -> bool:
        left_value, right_value = left.dump(), right.dump()
        left_value.pop("head")
        right_value.pop("head")
        return left_value == right_value

    def _effect_violations(self, facts: ReadinessFacts, blockers: tuple[str, ...]) -> tuple[str, ...]:
        violations = []
        digests: dict[str, set[str]] = defaultdict(set)
        for effect in facts.effects:
            digests[effect.operation].add(effect.content_digest)
        for operation in sorted(operation for operation, values in digests.items() if len(values) > 1):
            violations.append(f"effect_identity_collision:{operation}")

        for effect in facts.effects:
            if (
                effect.kind not in {"dashboard", "conversation", "reminder"}
                and effect.provider_authority_at_acceptance is not None
                and effect.authority != effect.provider_authority_at_acceptance
            ):
                violations.append(f"stale_effect_settled:{effect.operation}")

        gate_blockers = tuple(blocker for blocker in blockers if not blocker.startswith(("effect_", "timer_")))
        for effect in facts.effects:
            if effect.kind != "readiness" or effect.status not in {"accepted", "settled"}:
                continue
            if effect.authority.lifecycle != "active":
                violations.append(f"readiness_published_outside_active_lifecycle:{effect.operation}")
            if (
                (
                    facts.authority.admitted == facts.authority.provider
                    or effect.authority != effect.provider_authority_at_acceptance
                )
                and effect.provider_authority_at_acceptance == facts.authority.provider
                and gate_blockers
            ):
                violations.append(f"readiness_published_with_closed_gates:{effect.operation}")
        return tuple(violations)

    def _disposition(
        self,
        facts: ReadinessFacts,
        blockers: tuple[str, ...],
        violations: tuple[str, ...],
    ) -> ReadinessDisposition:
        if violations:
            return "quarantined"
        admitted = facts.authority.admitted
        if admitted is not None and admitted.lifecycle in {"merged", "closed"}:
            return "terminal"
        if not blockers:
            return "ready"
        if any(blocker.startswith("effect_rejected:") for blocker in blockers):
            return "quarantined"
        human = {
            "pull_request_draft",
            "blocking_findings",
            "changes_requested",
            "unresolved_conversations",
            "human_approval",
        }
        if human.intersection(blockers) or any(blocker.startswith("ci_repair_authorization:") for blocker in blockers):
            return "human_wait"
        external = {"current_base", "mergeability", "review_capability"}
        if external.intersection(blockers) or any(
            blocker.startswith(
                ("required_ci_missing:", "ci_terminal:", "ci_capability:", "effect_blocked:", "timer_scheduled:")
            )
            for blocker in blockers
        ):
            return "external_wait"
        return "progressing"


def evaluate_liveness(
    expectation: ReadinessExpectation,
    environment: FairEnvironment,
    *,
    budget_exhausted: bool,
) -> LivenessDisposition:
    """Classify bounded convergence without blaming an unfair environment."""

    if not environment.declared or expectation.disposition in {"human_wait", "external_wait"}:
        return "not_applicable"
    if expectation.disposition in {"ready", "terminal", "quarantined"}:
        return "converged"
    return "livelock" if budget_exhausted else "in_progress"
