"""Verified GitHub reconciliation into one durable PR-readiness Instance."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

from hamsterdan.agents import AgentRunner
from hamsterdan.contracts.readiness import (
    ActionsObservation,
    Admission,
    AdmittedConversation,
    ConversationObservation,
    GenerationCommit,
    GenerationStart,
    GenerationStop,
    HumanObservation,
    ReadinessSnapshot,
)
from hamsterdan.github_app.effects import CommentPublisher, CommentRerunBroker, EffectFault
from hamsterdan.github_app.gateway import GitHubAuthority

from .activities import AgentFault, PrReadinessActivities
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
        agent_dispatch: Callable[[str, int], None],
        agent_settle: Callable[[set[str]], None],
        bot_login: str,
        public_clone_url: str,
        workflow_path: str = ".github/workflows/ci.yml",
        reminder_delay: float = 3 * 24 * 60 * 60,
        publication_fault: EffectFault | None = None,
        agent_fault: AgentFault | None = None,
        dispatch_path: Path | None = None,
    ):
        self.root, self.instance_id, self.authority, self.runner = root, instance_id, authority, runner
        normalized_login = bot_login.strip().casefold()
        if not normalized_login or not normalized_login.endswith("[bot]"):
            raise ValueError("bot login must be the exact GitHub App bot login")
        self.bot_login = normalized_login
        self.public_clone_url, self.workflow_path = public_clone_url, workflow_path
        self.reminder_delay = reminder_delay
        self.publication_fault, self.agent_fault = publication_fault, agent_fault
        self.agent_dispatch, self.agent_settle = agent_dispatch, agent_settle
        self.dispatch_path = dispatch_path
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
                self.publication_fault,
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
                self.agent_dispatch,
                git,
                lease.is_current,
                self.agent_fault,
            )

        return PrReadinessHost.open(
            self.root,
            self.instance_id,
            self.authority,
            operations,
            reminder_delay=self.reminder_delay,
            agent_settle=self.agent_settle,
            dispatch_path=self.dispatch_path,
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

    def _reconcile(self, trigger: str) -> None:
        self._repair_generation_boundary()
        pull = self.authority.pull_request()
        if pull.closed or pull.merged:
            if self.host is not None:
                status = "merged" if pull.merged else "closed"
                if not self.host.place("terminal"):
                    self._stop_generation(status, pull.head, f"{trigger}:{status}:{pull.head}")
            return
        if pull.draft:
            if self.host is not None and (self.host.snapshot is not None or self.host.place("seed")):
                epoch = self.host.snapshot.epoch if self.host.snapshot is not None else 0
                self._stop_generation("draft", pull.head, f"{trigger}:draft:{epoch}:{pull.head}")
            return

        policy = self.authority.policy(pull.base_ref)
        base_current = self.authority.base_current(pull)
        if self.host is None:
            self.host = self._open_host()
        elif (
            self.host.snapshot is None
            and (self.host.place("seed") or self.host.place("dormant"))
            and self.host.generation_scope is None
        ):
            self.host.open_generation()
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
        control = self.host.snapshot
        started = control is None or control.head != pull.head
        if started:
            self._start_generation(admission, target_epoch, control)
            control = self.host.snapshot
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
        if not started and (current_basis != admission_basis or review_attempt):
            self._deliver(
                "verified_admission",
                admission,
                (
                    f"reconcile:admission:{target_epoch}:{_digest(current_basis)}:"
                    f"{_digest(admission_basis)}:{review_attempt}"
                ),
            )
        control = self.host.snapshot
        if control is None:
            return

        review = self.authority.human_review()
        approvals = tuple(name for name in review.approvals if name.casefold() != pull.author.casefold())
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
        # Authority owns base_current; compare human-owned observation fields only.
        current_human = (
            control.human_requested,
            control.human_approved,
            control.changes_requested,
            control.unresolved_conversations,
            control.distinct_reviewer_required,
            control.distinct_reviewer_approved,
            control.mergeable,
            control.conflict,
            control.reminder_recipient,
            control.author,
            not control.human_capability_blocking,
        )
        observed_human = (
            human.requested,
            human.approved,
            human.changes_requested,
            human.unresolved_conversations,
            human.distinct_required,
            human.distinct_approved,
            human.mergeable,
            human.conflict,
            human.reviewer,
            human.author,
            human.capability_available,
        )
        if current_human != observed_human:
            self._deliver(
                "human_observation",
                human,
                f"reconcile:human:{control.epoch}:{control.head}:"
                f"{_digest({'sequence': control.observation_sequence, 'prior': current_human, 'observed': human.dump()})}",
            )
        current = self.host.snapshot
        if current is not None:
            self._observe_actions(current, policy.required_checks)
        return

    def activate(self, trigger: str, *, conversation: AdmittedConversation | None = None) -> None:
        """Reconcile provider truth once, then optionally deliver a conversation."""
        self._reconcile(trigger)
        if conversation is None:
            return
        if self.host is None or self.host.control is None:
            return
        control = self.host.control
        value = ConversationObservation(
            control.epoch,
            control.head,
            True,
            conversation.text,
            conversation.comment_id,
            conversation.actor_id,
            conversation.actor_login,
            conversation.association,
        )
        self._deliver("conversation_observation", value, f"github-delivery:{conversation.delivery_id}")

    def _observe_actions(self, control, required_checks: tuple[str, ...]) -> None:
        run = self.authority.select_run(self.workflow_path, control.head)
        if run is None:
            return
        evidence = self.authority.actions_evidence(run, required_checks)
        run, conclusion = evidence.run, evidence.conclusion
        fingerprint = _digest(evidence.failed_required_jobs) if conclusion == "failure" else ""
        observation = _digest({"run": asdict(run), "conclusion": conclusion})
        value = ActionsObservation(
            control.epoch,
            control.head,
            str(run.id),
            run.attempt,
            cast(Any, conclusion),
            fingerprint,
            True,
            observation,
            control.actions_operation,
            control.base_head,
            control.policy_digest,
        )
        self._deliver("actions_observation", value, f"reconcile:actions:{control.epoch}:{_digest(value.dump())}")

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

    def _start_generation(self, admission: Admission, epoch: int, prior: ReadinessSnapshot | None) -> None:
        assert self.host is not None
        scope = self.host.generation_scope
        if scope is None:
            raise RuntimeError("generation start has no active lifecycle scope")
        generation = scope.generation + (prior is not None)
        if prior is None:
            relation = "resumed" if self.host.place("dormant") else "new"
        else:
            relation = "confirmed" if admission.head == prior.provisional_head else "superseded"
            self.host.drain()
        confirmed = relation == "confirmed"
        start = GenerationStart(
            admission.repository_id,
            admission.pr_number,
            epoch,
            generation,
            relation,
            admission.head,
            admission.base_head,
            admission.strict_base,
            admission.base_current,
            admission.policy_digest,
            admission.required_checks,
            admission.required_approvals,
            admission.conversation_resolution,
            [] if prior is None else prior.findings,
            [] if prior is None else prior.finding_lineage,
            bool(prior is not None and confirmed and prior.repair_used),
            "" if prior is None or not confirmed else prior.repair_fingerprint,
        )
        identity = f"generation:start:{epoch}:{relation}:{_digest(start.dump())}"
        self.host.deliver("begin_generation", start, identity)
        if prior is not None:
            self.host.reset_generation()
        self._deliver("commit_generation", GenerationCommit(generation, "start"), f"{identity}:commit")

    def _stop_generation(self, status: Literal["draft", "merged", "closed"], head: str, identity: str) -> None:
        assert self.host is not None
        self.host.drain()
        control = self.host.snapshot
        dormant = self.host.place("dormant")
        if control is not None:
            repository_id, pr_number, last_epoch, active = (
                control.repository_id,
                control.pr_number,
                control.epoch,
                True,
            )
        elif dormant:
            repository_id, pr_number, last_epoch, active = (
                str(dormant[0]["repository_id"]),
                int(dormant[0]["pr_number"]),
                int(dormant[0]["last_epoch"]),
                False,
            )
        elif seed := self.host.place("seed"):
            repository_id, pr_number, last_epoch, active = (
                str(seed[0]["repository_id"]),
                int(seed[0]["pr_number"]),
                0,
                False,
            )
        else:
            raise RuntimeError("lifecycle stop has no active or dormant PR generation")
        generation = self.host.generation_scope.generation if self.host.generation_scope else last_epoch
        stop = GenerationStop(repository_id, pr_number, last_epoch, generation, status, head, active)
        self.host.deliver("end_generation", stop, identity)
        if self.host.generation_scope is not None:
            self.host.close_generation()
        self.host.deliver("commit_generation", GenerationCommit(generation, "stop"), f"{identity}:commit")
        self.host.drain()

    def _repair_generation_boundary(self) -> None:
        if self.host is None:
            return
        stops = self.host.place("generation_stop")
        if stops:
            stop = GenerationStop(**stops[0])
            if self.host.place("generation_commit"):
                self.host.drain()
                return
            scope = self.host.generation_scope
            if scope is not None:
                if scope.generation != stop.generation:
                    raise RuntimeError("pending generation stop does not match active lifecycle scope")
                self.host.close_generation()
            self.host.deliver(
                "commit_generation",
                GenerationCommit(stop.generation, "stop"),
                f"generation:stop:{stop.generation}:{_digest(stop.dump())}:commit",
            )
            self.host.drain()
        starts = self.host.place("generation_start")
        if starts:
            start = GenerationStart(**starts[0])
            if self.host.place("generation_commit"):
                self.host.drain()
                return
            scope = self.host.generation_scope
            if scope is None:
                scope = self.host.open_generation()
            elif scope.generation < start.generation:
                scope = self.host.reset_generation()
            if scope.generation != start.generation:
                raise RuntimeError("pending generation start does not match active lifecycle scope")
            self.host.deliver(
                "commit_generation",
                GenerationCommit(start.generation, "start"),
                f"generation:start:{start.generation}:{_digest(start.dump())}:commit",
                scope=scope,
            )
            self.host.drain()

    def _deliver(self, source: str, value, identity: str) -> None:
        assert self.host is not None
        self.host.deliver(source, value, identity, scope=self.host.generation_scope)
        self.host.drain()

    def close(self) -> None:
        if self.host is not None:
            self.host.close()

    def settle(self):
        """Collect Activity terminals without requiring a provider observation."""
        if self.host is not None:
            return self.host.drain()
        return None

    def activity(self, name: str):
        return None if self.host is None else self.host.activity(name)

    def has_unresolved_publication(self) -> bool:
        return self.host is not None and self.host.has_unresolved_publication()


__all__ = ["PrReadinessApplication"]
