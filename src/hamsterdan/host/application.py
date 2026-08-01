"""Verified GitHub reconciliation into one durable PR-readiness Instance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hamsterdan.agents import AgentRunner
from hamsterdan.contracts.readiness import (
    ActionsObservation,
    Admission,
    ConversationObservation,
    HumanObservation,
    Lifecycle,
    workflow_wait,
)
from hamsterdan.github_app.effects import CommentPublisher, CommentRerunBroker
from hamsterdan.github_app.gateway import GitHubAuthority

from .activities import PrReadinessActivities
from .git_publish import HostGitPublisher
from .runtime import AuthorityLease, PrReadinessHost


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class PrReadinessApplication:
    """Own verified observations and lazily create the one-PR Instance."""

    def __init__(
        self,
        root: Path,
        instance_id: str,
        authority: GitHubAuthority,
        runner: AgentRunner,
        *,
        bot_login: str,
        public_clone_url: str,
        workflow_path: str = ".github/workflows/ci.yml",
        reminder_delay: float = 3 * 24 * 60 * 60,
        trusted_associations: frozenset[str] = frozenset({"OWNER", "MEMBER", "COLLABORATOR"}),
    ):
        self.root, self.instance_id, self.authority, self.runner = root, instance_id, authority, runner
        normalized_login = bot_login.strip().casefold()
        if not normalized_login or not normalized_login.endswith("[bot]"):
            raise ValueError("bot login must be the exact GitHub App bot login")
        self.bot_login = normalized_login
        self.trusted_associations = frozenset(value.upper() for value in trusted_associations)
        self.public_clone_url, self.workflow_path = public_clone_url, workflow_path
        self.reminder_delay = reminder_delay
        self.host: PrReadinessHost | None = None
        if (root / "history.jsonl").exists():
            self.host = self._open_host()

    def _open_host(self) -> PrReadinessHost:
        self._bind_state_root()

        def operations(lease: AuthorityLease) -> PrReadinessActivities:
            publisher = CommentPublisher(
                self.authority.transport,
                self.authority.repository,
                self.authority.pr_number,
                self.bot_login,
                lease.publisher_fence,
            )
            reruns = CommentRerunBroker(self.authority, publisher)
            git = HostGitPublisher(self.authority, self.public_clone_url)
            return PrReadinessActivities(
                self.authority.repository,
                self.authority.pr_number,
                self.authority,
                publisher,
                reruns,
                self.runner,
                self.public_clone_url,
                self.workflow_path,
                lease.fence,
                git,
                lease.is_current,
            )

        return PrReadinessHost.open(
            self.root,
            self.instance_id,
            self.authority,
            operations,
            reminder_delay=self.reminder_delay,
        )

    def _bind_state_root(self) -> None:
        expected = {
            "instance_id": self.instance_id,
            "repository": self.authority.repository,
            "pull_request": self.authority.pr_number,
        }
        binding = self.root / "binding.json"
        if binding.exists():
            try:
                observed = json.loads(binding.read_text(encoding="utf-8"))
            except OSError, json.JSONDecodeError:
                raise RuntimeError("replacement state binding is unreadable") from None
            if observed != expected:
                raise RuntimeError("replacement state root belongs to a different PR Instance")
            return
        if (self.root / "history.jsonl").exists():
            raise RuntimeError("replacement History has no subject binding")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = binding.with_suffix(".tmp")
        temporary.write_text(json.dumps(expected, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(binding)

    def reconcile(self, trigger: str = "poll") -> dict[str, object]:
        pull = self.authority.pull_request()
        if pull.closed or pull.merged:
            if self.host is not None:
                status = "merged" if pull.merged else "closed"
                self._deliver("lifecycle_observation", Lifecycle(status, pull.head), f"{trigger}:{status}:{pull.head}")
            return self.projection(pull.state)
        if pull.draft:
            if self.host is not None and self.host.control is not None:
                control = self.host.control
                assert control is not None
                self._deliver(
                    "lifecycle_observation",
                    Lifecycle("draft", pull.head),
                    f"{trigger}:draft:{control.epoch}:{pull.head}",
                )
            return self.projection(pull.state)

        policy = self.authority.policy(pull.base_ref)
        base_current = self.authority.base_current(pull)
        if self.host is None:
            self.host = self._open_host()
        target_epoch = self._target_epoch(pull.head)
        admission = Admission(
            self.authority.repository,
            self.authority.pr_number,
            pull.head,
            pull.base,
            policy.strict or policy.update_required,
            base_current,
            policy.digest,
            list(policy.required_checks),
            policy.required_approvals,
            policy.conversation_resolution,
        )
        control = self.host.control
        current_basis = None
        if control is not None:
            current_basis = {
                "head": control.head,
                "base_head": control.base_head,
                "strict_base": control.strict_base,
                "base_current": control.base_current,
                "policy_digest": control.policy_digest,
                "required_checks": control.required_checks,
                "required_approvals": control.required_approvals,
                "conversation_resolution": control.conversation_resolution,
            }
        admission_basis = {
            "head": admission.head,
            "base_head": admission.base_head,
            "strict_base": admission.strict_base,
            "base_current": admission.base_current,
            "policy_digest": admission.policy_digest,
            "required_checks": admission.required_checks,
            "required_approvals": admission.required_approvals,
            "conversation_resolution": admission.conversation_resolution,
        }
        review_attempt = max(control.review_attempts, 1) if control is not None and control.review == "unable" else 0
        if current_basis != admission_basis or review_attempt:
            self._deliver(
                "verified_admission",
                admission,
                (
                    f"reconcile:admission:{target_epoch}:{_digest(current_basis)}:"
                    f"{_digest(admission_basis)}:{review_attempt}"
                ),
            )
        control = self.host.control
        if control is None:
            return self.projection(pull.state)

        review = self.authority.human_review()
        approvals = tuple(name for name in review.approvals if name != pull.author)
        required_satisfied = len(approvals) >= policy.required_approvals
        requested_satisfied = not review.requested_reviewers
        threads_available = review.unresolved_threads is not None
        human = HumanObservation(
            control.epoch,
            control.head,
            bool(review.requested_reviewers) or policy.required_approvals > 0,
            required_satisfied and requested_satisfied and not review.changes_requested,
            bool(review.changes_requested),
            0 if review.unresolved_threads is None else review.unresolved_threads,
            policy.required_approvals > 0,
            bool(approvals),
            pull.mergeable is True,
            pull.mergeable is False or pull.mergeable_state == "dirty",
            base_current,
            review.requested_reviewers[0] if review.requested_reviewers else "",
            pull.author,
            threads_available or not policy.conversation_resolution,
        )
        self._deliver(
            "human_observation",
            human,
            f"reconcile:human:{control.epoch}:{_digest(asdict(human))}",
        )
        current = self.host.control
        if current is not None:
            self._observe_actions(current, policy.required_checks)
        return self.projection(pull.state)

    def route_comment(
        self,
        *,
        delivery_id: str,
        comment_id: int,
        actor_id: int,
        actor_login: str,
        actor_type: str,
        association: str,
        text: str,
    ) -> dict[str, object]:
        self.reconcile(f"comment-preflight:{delivery_id}")
        if self.host is None or self.host.control is None:
            return {"routed": False, "reason": "PR has no active reviewable generation"}
        control = self.host.control
        assert control is not None
        normalized_text = text.strip()
        is_bot = actor_login.strip().casefold() == self.bot_login
        addressed = self._addressed_text(normalized_text)
        authorized = actor_type == "User" and association.upper() in self.trusted_associations
        if is_bot or not authorized or addressed is None:
            return {"routed": False, "reason": "comment is not an authorized Hamsterdan conversation"}
        value = ConversationObservation(
            control.epoch,
            control.head,
            True,
            addressed,
            comment_id,
            actor_id,
            actor_login,
            association,
        )
        self._deliver("conversation_observation", value, f"github-delivery:{delivery_id}")
        return {"routed": True, "epoch": control.epoch, "head": control.head}

    def _addressed_text(self, text: str) -> str | None:
        """Strip the exact, case-insensitive configured App mention."""
        mention = f"@{self.bot_login.removesuffix('[bot]')}"
        folded = text.casefold()
        if folded == mention:
            return ""
        prefix = f"{mention} "
        if folded.startswith(prefix):
            return text[len(prefix) :].lstrip()
        return None

    def _observe_actions(self, control, required_checks: tuple[str, ...]) -> None:
        run = self.authority.select_run(self.workflow_path, control.head)
        if run is None:
            return
        run = self.authority.jobs(run, required_checks)
        result = self.authority.run_result(run)
        conclusion = str(result["conclusion"])
        if conclusion == "pending":
            conclusion = "in_progress" if run.status == "in_progress" else "queued"
        failed = sorted((job.name, job.conclusion) for job in run.jobs if job.required and job.conclusion != "success")
        fingerprint = _digest(failed) if conclusion == "failure" else ""
        observation = _digest({"run": asdict(run), "conclusion": conclusion})
        value = ActionsObservation(
            control.epoch,
            control.head,
            str(run.id),
            run.attempt,
            conclusion,
            fingerprint,
            True,
            observation,
            control.actions_operation,
            control.base_head,
            control.policy_digest,
        )
        self._deliver("actions_observation", value, f"reconcile:actions:{control.epoch}:{_digest(asdict(value))}")

    def _target_epoch(self, head: str) -> int:
        assert self.host is not None
        if self.host.control is not None:
            control = self.host.control
            assert control is not None
            return control.epoch + (control.head != head)
        dormant = self.host.place("dormant")
        if dormant:
            return int(dormant[0]["last_epoch"]) + 1
        return 1

    def _deliver(self, source: str, value, identity: str) -> None:
        assert self.host is not None
        self.host.deliver(source, value, identity)
        self.host.drain()

    def projection(self, provider_state: str = "unknown") -> dict[str, object]:
        if self.host is None:
            return {"instance": "absent", "provider_state": provider_state, "wait": "first ready observation"}
        if self.host.control is not None:
            control = self.host.control
            assert control is not None
            return {
                "instance": "active",
                "provider_state": provider_state,
                "epoch": control.epoch,
                "head": control.head,
                "actions": control.actions,
                "review": control.review,
                "human_approved": control.human_approved,
                "provisional": control.provisional,
                "announced": control.announced,
                "wait": workflow_wait(control),
            }
        dormant = self.host.place("dormant")
        if dormant:
            return {"instance": "dormant", "provider_state": provider_state, **dormant[0], "wait": "ready lifecycle"}
        terminal = self.host.place("terminal")
        if terminal:
            return {"instance": "terminal", "provider_state": provider_state, **terminal[0], "wait": "none"}
        return {"instance": "recovering", "provider_state": provider_state, "wait": "Engine reconciliation"}

    def close(self) -> None:
        if self.host is not None:
            self.host.close()


__all__ = ["PrReadinessApplication"]
