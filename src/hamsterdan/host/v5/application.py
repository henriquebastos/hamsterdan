"""Provider-normalized, custody-backed application for the V5 topology."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from petrus.motus.activity import ActivityDefinition, activity

from hamsterdan.agents.protocol import AgentProtocolError, AgentRunner, ConversationRequest
from hamsterdan.contracts.readiness import AdmittedConversation
from hamsterdan.contracts.readiness_v5 import AWake, CommentSeen, RoundWake
from hamsterdan.github_app.effects import CommentPublisher, CommentRerunBroker, EffectFault
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.github_app.models import GitHubBoundaryError
from hamsterdan.github_app.webhooks import Observation
from hamsterdan.host.binding import ensure_instance_binding
from hamsterdan.host.git_publish import HostGitPublisher
from hamsterdan.host.protocol import DurableActivityResolver
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.gates import UnstagedCustodyError, V5PublicationGates
from hamsterdan.host.v5.ingress import IngressEntry, V5IngressNormalizer, V5IngressStore
from hamsterdan.host.v5.mutation import V5MutationGate
from hamsterdan.host.v5.rerun import V5RerunGate
from hamsterdan.host.v5.review import V5ReviewGate, V5ReviewRequestStore
from hamsterdan.host.v5.runtime import V5Runtime
from hamsterdan.host.v5.timers import V5TimerStore
from hamsterdan.readiness.net_v5.gating import VariantPayloadConverter

_MUTATIONS = frozenset({"change", "update_base", "resolve_conflict"})
_ALLOWED = (
    "reply",
    "status",
    "acknowledge",
    "dismiss",
    "defer",
    "snooze",
    "resume",
    "reassign",
    "recover_publication",
    *_MUTATIONS,
)
_UNFENCED_PREFIXES = ("reply:", "reminder:", "dash:")
_RECOVERY_OPERATION = re.compile(r"[!-~]{1,256}\Z")


class PrReadinessV5Application:
    """One non-sharded V5 PR actor family behind the host protocol."""

    def __init__(
        self,
        root: Path,
        instance_id: str,
        authority: GitHubAuthority,
        runner: AgentRunner,
        *,
        agent_settle: Callable[[set[str]], None],
        bot_login: str,
        public_clone_url: str,
        custody_path: Path,
        workflow_path: str = ".github/workflows/ci.yml",
        reminder_delay: float = 3 * 24 * 60 * 60,
        publication_fault: EffectFault | None = None,
        dispatch_path: Path | None = None,
        timer_clock_us: Callable[[], int] | None = None,
        durable_activity_resolver: DurableActivityResolver | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if (
            isinstance(reminder_delay, bool)
            or not isinstance(reminder_delay, (int, float))
            or not math.isfinite(reminder_delay)
            or reminder_delay < 1
            or reminder_delay > 2_147_483_647
            or not float(reminder_delay).is_integer()
        ):
            raise ValueError("V5 reminder delay must be a positive bounded whole second count")
        reminder_delay_s = int(reminder_delay)
        self.root, self.instance_id = root, instance_id
        self.authority, self.runner = authority, runner
        self.public_clone_url, self.workflow_path = public_clone_url, workflow_path
        self.agent_settle = agent_settle
        self._bind_state_root()
        self.ingress = V5IngressStore(custody_path)
        self.review_requests = V5ReviewRequestStore(root / "review-requests.sqlite3")
        self.normalizer = V5IngressNormalizer(authority, workflow_path)
        self.runtime: V5Runtime | None = None

        publisher = CommentPublisher(
            authority.transport,
            authority.repository,
            authority.pr_number,
            bot_login,
            self._publisher_fence,
            publication_fault,
        )
        publications = V5PublicationGates(
            publisher,
            self.current_claim,
            self._recipients,
            lambda: self.ingress.claim(self.instance_id).phase,
        )
        rerun = V5RerunGate(
            CommentRerunBroker(authority, publisher),
            lambda head: authority.workflow_runs(workflow_path, head),
            self.current_claim,
        )
        review = V5ReviewGate(
            authority.repository,
            authority.pr_number,
            authority,
            runner,
            public_clone_url,
            workflow_path,
            self.current_claim,
            self.review_requests,
            lambda: self.ingress.unstaged_custody_id(self.instance_id),
        )
        mutation = V5MutationGate(
            authority.repository,
            authority.pr_number,
            runner,
            HostGitPublisher(authority, public_clone_url),
            public_clone_url,
            self.current_claim,
        )
        converter = VariantPayloadConverter()
        implementations = {
            "rerun_gate": rerun.rerun_gate,
            "review_agent": review.review_agent,
            "publish_gate": publications.publish_gate,
            "git_gate": mutation.git_gate,
            "reply_gate": publications.reply_gate,
            "dash_gate": publications.dash_gate,
            "reminder_gate": publications.reminder_gate,
            "announce_gate": publications.announce_gate,
        }
        definitions: dict[str, ActivityDefinition] = {
            name: activity(implementation, name=name, converter=converter)
            for name, implementation in implementations.items()
        }
        self.runtime = V5Runtime.open(
            root,
            instance_id,
            definitions,
            dispatch_path=dispatch_path,
            agent_settle=agent_settle,
            mutation_operation=lambda op_key: f"mutation:{authority.repository}:pr:{authority.pr_number}:{op_key}",
            reminder_delay_s=reminder_delay_s,
            durable_activity_resolver=durable_activity_resolver,
        )
        selected_timer_clock = timer_clock_us or (None if clock is None else lambda: int(clock() * 1_000_000))
        timer_options = {} if selected_timer_clock is None else {"clock_us": selected_timer_clock}
        self.timers = V5TimerStore.open(
            root / "timers.sqlite3",
            instance_id,
            history=self.runtime.timer_history(),
            outstanding=self.runtime.timer_command(),
            **timer_options,
        )

    def _bind_state_root(self) -> None:
        try:
            ensure_instance_binding(
                self.root,
                "v5",
                self.instance_id,
                self.authority.repository,
                self.authority.pr_number,
            )
        except RuntimeError as error:
            raise RuntimeError(f"V5 {error}") from None

    def current_claim(self) -> CurrentClaim:
        if (blocker := self.ingress.unstaged_custody_id(self.instance_id)) is not None:
            raise UnstagedCustodyError(blocker)
        grant = self.ingress.claim(self.instance_id)
        pull = self.authority.pull_request()
        policy = self.authority.policy(pull.base_ref)
        if (blocker := self.ingress.unstaged_custody_id(self.instance_id)) is not None:
            raise UnstagedCustodyError(blocker)
        phase = "terminal" if pull.closed or pull.merged else ("quiescent" if pull.draft else "running")
        if (phase, pull.head, pull.base, policy.digest) != (grant.phase, grant.head, grant.base, grant.policy):
            raise GitHubBoundaryError("fresh provider authority is not staged in the V5 host grant")
        return CurrentClaim(grant.phase, grant.incarnation, pull.head, pull.base, policy.digest)

    def _publisher_fence(self, repository: str, pr: int, incarnation: int, head: str, operation: str) -> None:
        if repository != self.authority.repository or pr != self.authority.pr_number:
            raise RuntimeError("V5 publication escaped its configured PR")
        if operation.startswith(_UNFENCED_PREFIXES):
            return
        runtime = self._runtime()
        expected = runtime.active_claim(operation)
        if expected is None or (incarnation, head) != (expected.incarnation, expected.head):
            raise RuntimeError("V5 publication has no active full authority claim")
        if self.current_claim() != expected:
            raise RuntimeError("V5 publication authority moved before the provider effect")

    def _recipients(self) -> tuple[str | None, str]:
        pull = self.authority.pull_request()
        review = self.authority.human_review()
        return (review.requested_reviewers[0] if review.requested_reviewers else None, pull.author)

    def process_observation(
        self,
        observation: Observation,
        *,
        conversation: AdmittedConversation | None = None,
    ) -> None:
        route_operation: str | None = None
        if conversation is not None:
            if conversation.delivery_id != observation.delivery_id:
                raise ValueError("conversation differs from its custodied delivery")
            route_operation = self._conversation_operation(conversation.delivery_id)
        manifest = self.ingress.manifest(observation.delivery_id, self.instance_id)
        if manifest is None:
            entries = self.normalizer.project(
                observation.delivery_id,
                event=observation.event,
                action=observation.action,
            )
            if conversation is not None:
                target = self.ingress.preview(self.instance_id, entries)
                classified = self._classify(conversation, target)
                entries = (
                    *entries,
                    IngressEntry.from_value(
                        "on_comment",
                        classified,
                        f"github-delivery:{observation.delivery_id}:on_comment",
                    ),
                )
            manifest = self.ingress.stage(observation.delivery_id, self.instance_id, entries)
        if route_operation is not None:
            # The immutable manifest now owns the classifier result.
            # Settlement is idempotently replayed after a crash in the
            # narrow manifest-commit/route-settle window.
            self.agent_settle({route_operation})
        runtime = self._runtime()
        self._deliver_manifest(runtime, manifest.entries)

    @staticmethod
    def _deliver_manifest(runtime: V5Runtime, entries: tuple[IngressEntry, ...]) -> None:
        """Preserve the host grant's canonical door order in the actor loop."""
        for entry in entries:
            runtime.deliver(entry)
            runtime.fold_ingress(entry)

    def _classify(self, conversation: AdmittedConversation, claim: CurrentClaim) -> CommentSeen:
        operation = self._conversation_operation(conversation.delivery_id)
        declarations = self._intent_declarations()
        request = ConversationRequest(
            repository=self.authority.repository,
            pull_request=self.authority.pr_number,
            epoch=claim.incarnation,
            head=claim.head,
            base=claim.base,
            comment_context={
                "id": conversation.comment_id,
                "body": conversation.text,
                "author_association": conversation.association,
            },
            actor={"id": conversation.actor_id, "login": conversation.actor_login},
            dashboard={"phase": claim.phase, "head": claim.head},
            gates=[],
            findings=[],
            allowed_intents=declarations,
        )
        try:
            result = self.runner.converse(
                self.public_clone_url,
                request,
                operation=operation,
                attempt=1,
                # Classification precedes the atomic manifest/grant
                # stage. Fence against fresh provider truth here; the
                # host incarnation becomes authoritative at stage.
                is_current=lambda: self._provider_matches(claim),
            )
            if len(result.intents) != 1:
                raise AgentProtocolError("conversation must select exactly one intent")
            raw = result.intents[0]
            kind = raw.get("type")
            arguments = raw.get("arguments", {})
            if not isinstance(kind, str) or kind not in _ALLOWED or not isinstance(arguments, dict):
                raise AgentProtocolError("conversation selected an invalid intent")
            arg = self._intent_arg(kind, cast(dict[str, Any], arguments), conversation.text)
            value = CommentSeen(
                id=str(conversation.comment_id),
                kind=kind,
                arg=arg,
                authorized=True,
            )
        except AgentProtocolError:
            value = CommentSeen(
                id=str(conversation.comment_id),
                kind="",
                arg="",
                authorized=False,
            )
        return value

    def _conversation_operation(self, delivery_id: str) -> str:
        return f"conversation:{self.authority.repository}:pr:{self.authority.pr_number}:delivery:{delivery_id}"

    def _provider_matches(self, expected: CurrentClaim) -> bool:
        pull = self.authority.pull_request()
        policy = self.authority.policy(pull.base_ref)
        phase = "terminal" if pull.closed or pull.merged else ("quiescent" if pull.draft else "running")
        return (phase, pull.head, pull.base, policy.digest) == (
            expected.phase,
            expected.head,
            expected.base,
            expected.policy,
        )

    @staticmethod
    def _intent_arg(kind: str, arguments: dict[str, Any], comment: str) -> str:
        if kind in _MUTATIONS:
            return str(arguments.get("request", ""))
        if kind in {"dismiss", "acknowledge", "defer"}:
            findings = arguments.get("findings", [])
            if isinstance(findings, list) and findings:
                return str(findings[0])
        if kind == "recover_publication":
            operation = arguments.get("operation")
            if (
                set(arguments) != {"operation"}
                or not isinstance(operation, str)
                or _RECOVERY_OPERATION.fullmatch(operation) is None
                or operation not in comment
            ):
                raise AgentProtocolError("publication recovery operation was not explicitly named")
            return operation
        if kind == "reassign":
            return str(arguments.get("assignee", ""))
        return ""

    @staticmethod
    def _intent_declarations() -> list[dict[str, object]]:
        arguments = {
            "reply": ["message"],
            "status": [],
            "acknowledge": ["findings"],
            "dismiss": ["findings"],
            "defer": ["findings"],
            "snooze": [],
            "resume": [],
            "reassign": ["assignee"],
            "recover_publication": ["operation"],
            "change": ["request"],
            "update_base": ["request"],
            "resolve_conflict": ["request"],
        }
        return [
            {
                "type": name,
                "mutation": name in _MUTATIONS,
                "arguments": arguments[name],
                "requires_explicit": name in _MUTATIONS or name == "recover_publication",
            }
            for name in _ALLOWED
        ]

    def reconcile(self, reason: str) -> bool:
        del reason  # wake metadata never enters reconciliation identity
        runtime = self._runtime()
        frozen = self.ingress.latest_reconciliation(self.instance_id)
        if frozen is not None:
            accepted = runtime.manifest_accepted(frozen.entries)
            if self.ingress.has_pending_custody(self.instance_id):
                return False
            self._deliver_manifest(runtime, frozen.entries)
            if not accepted:
                return True
        if self.ingress.has_pending_custody(self.instance_id):
            return False
        projected = self.normalizer.project_reconciliation()
        manifest = self.ingress.stage_reconciliation(self.instance_id, projected)
        if manifest is None or self.ingress.has_pending_custody(self.instance_id):
            return False
        runtime.manifest_accepted(manifest.entries)
        self._deliver_manifest(runtime, manifest.entries)
        return True

    def settle(self):
        runtime = self._runtime()
        for _ in range(500):
            outcome = runtime.drain()
            if self._wake_deferred(runtime):
                continue
            if (ack := self.timers.pending_ack()) is not None:
                runtime.deliver_timer_ack(ack, self.timers.ack_identity(ack.operation))
                self.timers.mark_ack_delivered(ack.operation)
                continue
            if (command := runtime.timer_command()) is not None:
                self.timers.apply(command)
                continue
            if (maturity := self.timers.pending_maturity()) is not None:
                runtime.deliver_timer_due(maturity.value, maturity.identity)
                self.timers.mark_maturity_delivered(maturity.value.timer.id)
                continue
            if (maturity := self.timers.claim_due()) is not None:
                runtime.deliver_timer_due(maturity.value, maturity.identity)
                self.timers.mark_maturity_delivered(maturity.value.timer.id)
                continue
            return replace(outcome, next_maturation=self.timers.next_due())
        raise RuntimeError("V5 timer settlement did not reach an external wait")

    def _wake_deferred(self, runtime: V5Runtime) -> bool:
        delivered = False
        if (deferred := runtime.review_deferred()) is not None and self.ingress.unstaged_custody_id(
            self.instance_id
        ) is None:
            wake = RoundWake(
                operation=deferred.operation,
                attempt=deferred.attempt,
                blocker=deferred.blocker,
            )
            runtime.deliver_review_wake(wake, runtime.review_wake_identity(wake))
            delivered = True
        if (deferred_announce := runtime.announce_deferred()) is not None and self._barrier_cleared(
            runtime, deferred_announce.blocker
        ):
            wake = AWake(**deferred_announce.dump())
            runtime.deliver_announce_wake(wake, runtime.announce_wake_identity(wake))
            delivered = True
        return delivered

    def _barrier_cleared(self, runtime: V5Runtime, blocker: str) -> bool:
        manifest = self.ingress.manifest(blocker, self.instance_id)
        if manifest is not None:
            return runtime.manifest_folded(manifest.entries)
        return self.ingress.custody_terminal(self.instance_id, blocker)

    def activity(self, name: str):
        return self._runtime().activity(name)

    def has_unresolved_publication(self) -> bool:
        return self._runtime().has_unresolved_publication()

    def run_durable_activities(self, limit: int) -> int:
        return self._runtime().run_durable_activities(limit)

    def stop_durable_activities(self) -> None:
        self._runtime().stop_durable_activities()

    def detached_state(self) -> dict[str, object]:
        """Expose diagnostics without leaking the mutable V5 runtime graph."""
        return {"ready": None, "snapshot": self._runtime().engine.snapshot()}

    def _runtime(self) -> V5Runtime:
        if self.runtime is None:
            raise RuntimeError("V5 runtime is not bound")
        return self.runtime

    def close(self) -> None:
        runtime = self.runtime
        try:
            if runtime is not None:
                runtime.close()
        finally:
            try:
                self.timers.close()
            finally:
                try:
                    self.review_requests.close()
                finally:
                    self.ingress.close()


__all__ = ["PrReadinessV5Application"]
