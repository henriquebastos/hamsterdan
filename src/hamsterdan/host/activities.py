"""Complete typed Activity composition for the next PR-readiness net."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar, cast

from petrus.motus.activity import ActivityDefinition, ActivityError, activity

from hamsterdan import agents
from hamsterdan.contracts.readiness import (
    ActionsDiscoveryRequest,
    ActionsObservation,
    ActionsRerunRequest,
    ChangeRequest,
    ChangeResult,
    ConversationClassificationRequest,
    ConversationPublicationRequest,
    ConversationPublicationResult,
    DashboardPublicationRequest,
    DashboardPublicationResult,
    FindingPublicationRequest,
    FindingPublicationResult,
    Intent,
    IntentBatch,
    ReadinessCommand,
    ReadinessPublicationResult,
    ReadinessSnapshot,
    ReminderPublicationRequest,
    ReminderPublicationResult,
    RepairRequest,
    RepairResult,
    ReviewRequest,
    ReviewResult,
    workflow_gates_ready,
    workflow_wait,
)
from hamsterdan.github_app.effects import CommentPublisher, CommentRerunBroker
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.github_app.models import GitHubBoundaryError
from hamsterdan.readiness.payloads import PydanticPayloadConverter

from .git_publish import GitPublishError, HostGitPublisher, PublicationCategory, payload_digest

CurrentFence = Callable[[int, str, str, str, str], None]
Current = Callable[[int, str], bool]
_MUTATIONS = {"change", "update_base", "resolve_conflict"}
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
MAX_CODING_ATTEMPTS = 3
LOG = logging.getLogger(__name__)
CodeRequest = ChangeRequest | RepairRequest
PublicationRequest = (
    ConversationPublicationRequest
    | FindingPublicationRequest
    | DashboardPublicationRequest
    | ReminderPublicationRequest
    | ReadinessCommand
)
CodeResult = TypeVar("CodeResult", ChangeResult, RepairResult)


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class StaleAuthorityError(RuntimeError):
    """An operation no longer has exact marking and GitHub authority."""


def _publication_identity(request: CodeRequest) -> dict[str, Any]:
    """Project a typed coding request to its canonical publication identity payload."""
    value: dict[str, Any] = (
        {
            "base_head": request.base_head,
            "policy_digest": request.policy_digest,
            "intent": request.intent.dump(),
        }
        if isinstance(request, ChangeRequest)
        else {
            "base_head": request.base_head,
            "policy_digest": request.policy_digest,
            "actions": request.actions.dump(),
        }
    )
    if request.lineage:
        value["lineage"] = request.lineage
    return value


class PrReadinessActivities:
    """Petri-agnostic operations bound to exactly one repository and PR."""

    def __init__(
        self,
        repository: str,
        pr_number: int,
        authority: GitHubAuthority,
        publisher: CommentPublisher,
        reruns: CommentRerunBroker,
        runner: agents.AgentRunner,
        public_clone_url: str,
        workflow_path: str,
        current_fence: CurrentFence,
        git_publisher: HostGitPublisher | None = None,
        is_current: Current | None = None,
    ):
        if authority.repository != repository or authority.pr_number != pr_number:
            raise ValueError("GitHub authority differs from the configured repository/PR")
        self.repository, self.pr_number = repository, pr_number
        self.authority, self.publisher, self.reruns, self.runner = authority, publisher, reruns, runner
        self.public_clone_url, self.workflow_path = public_clone_url, workflow_path
        self.current_fence, self.git_publisher = current_fence, git_publisher
        self.current = is_current

    def _fence(
        self,
        value: CodeRequest
        | PublicationRequest
        | ReviewRequest
        | ActionsDiscoveryRequest
        | ActionsRerunRequest
        | ConversationClassificationRequest,
    ) -> None:
        base = value.base_head
        policy = value.policy_digest
        if not base or not policy:
            raise ValueError("effect lacks its complete authority fence")
        self.current_fence(value.epoch, value.head, value.operation, base, policy)

    def review(self, work: ReviewRequest) -> ReviewResult:
        comments = [
            {
                "id": item.get("id"),
                "url": item.get("html_url", ""),
                "body": str(item.get("body", ""))[:20_000],
                "author": item.get("user", {}).get("login", "") if isinstance(item.get("user"), dict) else "",
            }
            for item in self.authority.comments()[-100:]
        ]
        run = self.authority.select_run(self.workflow_path, work.head)
        actions_evidence = [] if run is None else [asdict(run)]
        request = agents.ReviewRequest(
            self.repository,
            self.pr_number,
            work.epoch,
            work.head,
            work.base_head,
            "diff.patch",
            policy=work.policy,
            review_lenses=["correctness", "security", "tests", "maintainability", "developer experience"],
            actions_evidence=actions_evidence,
            prior_findings=work.prior_findings[:100],
            prior_comments=comments,
            prior_replies=[],
            applied_changes=work.prior_lineage[:100],
        )
        try:
            result = self.runner.review(
                self.public_clone_url,
                request,
                operation=work.operation,
                attempt=1,
                is_current=lambda: self._is_current(work),
            )
        except agents.AgentProtocolError as error:
            self._log_agent_error("review", work, error)
            return ReviewResult(work.epoch, work.head, "unable", [], [], work.operation)
        current_ids = {str(finding.get("id", "")) for finding in result.findings}
        dispositions = {str(item.get("finding_id", "")): item.get("state") for item in result.lineage}
        terminal = [
            {**finding, "disposition": dispositions[str(finding.get("id", ""))]}
            for finding in request.prior_findings
            if str(finding.get("id", "")) not in current_ids
            and dispositions.get(str(finding.get("id", ""))) in {"resolved", "superseded", "withdrawn"}
        ]
        self._fence(work)
        return ReviewResult(
            work.epoch,
            work.head,
            cast(Any, result.status),
            [*result.findings, *terminal],
            result.lineage,
            work.operation,
        )

    def actions_discovery(self, work: ActionsDiscoveryRequest) -> ActionsObservation:
        self._fence(work)
        run = self.authority.select_run(self.workflow_path, work.head)
        if run is None:
            return ActionsObservation(
                work.epoch,
                work.head,
                "",
                0,
                "unavailable",
                capability_available=False,
                observation=f"absent:{self.workflow_path}:{work.head}",
                operation=work.operation,
                base_head=work.base_head,
                policy_digest=work.policy_digest,
            )
        policy = self.authority.policy(self.authority.pull_request().base_ref)
        evidence = self.authority.actions_evidence(run, policy.required_checks)
        run, conclusion = evidence.run, evidence.conclusion
        fingerprint = _digest(evidence.failed_required_jobs) if conclusion == "failure" else ""
        self._fence(work)
        return ActionsObservation(
            work.epoch,
            work.head,
            str(run.id),
            run.attempt,
            cast(Any, conclusion),
            fingerprint,
            operation=work.operation,
            base_head=work.base_head,
            policy_digest=work.policy_digest,
        )

    def actions_rerun(self, work: ActionsRerunRequest) -> ActionsObservation:
        value = work.actions
        try:
            run = next(
                (
                    item
                    for item in self.authority.workflow_runs(self.workflow_path, work.head)
                    if str(item.id) == value.run_id and item.attempt == value.attempt
                ),
                None,
            )
            if run is None:
                raise RuntimeError("the exact Actions run is no longer available")
            self._fence(work)
            self.reruns.request(run, epoch=work.epoch, operation=work.operation)
        except RuntimeError:
            return ActionsObservation(
                work.epoch,
                work.head,
                value.run_id,
                value.attempt,
                "canceled",
                observation=f"{value.run_id}:{value.attempt}:canceled",
                operation=work.operation,
                base_head=work.base_head,
                policy_digest=work.policy_digest,
            )
        return ActionsObservation(
            work.epoch,
            work.head,
            str(run.id),
            run.attempt,
            "requested",
            observation=f"{run.id}:{run.attempt}:requested",
            operation=work.operation,
            base_head=work.base_head,
            policy_digest=work.policy_digest,
        )

    def conversation(self, work: ConversationClassificationRequest) -> IntentBatch:
        comment, control = work.comment.dump(), work.control.dump()
        declarations = self._intent_declarations(control)
        request = agents.ConversationRequest(
            self.repository,
            self.pr_number,
            work.epoch,
            work.head,
            work.base_head,
            comment,
            {"id": comment.get("actor_id", 0), "login": comment.get("actor_login", "")},
            control,
            self._conversation_gates(control),
            list(control.get("findings", [])),
            declarations,
        )
        try:
            result = self.runner.converse(
                self.public_clone_url,
                request,
                operation=work.operation,
                attempt=1,
                is_current=lambda: self._is_current(work),
            )
            raw = result.intents
            if len(raw) != 1:
                raise agents.AgentProtocolError("conversation must select exactly one intent")
            if raw[0].get("type") == "status":
                raw = [{"type": "reply", "arguments": {"message": self._status(control)}}]
        except agents.AgentProtocolError as error:
            self._log_agent_error("conversation", work, error)
            if error.canceled:
                return IntentBatch(work.epoch, work.head, [])
            raw = [
                {
                    "type": "reply",
                    "arguments": {"message": "I couldn't interpret that request, so I made no workflow change."},
                    "mutation": False,
                    "explicit": False,
                    "confidence": 1,
                }
            ]
        intents = [self._intent(item, work, control) for item in raw]
        self._fence(work)
        return IntentBatch(work.epoch, work.head, intents)

    def conversation_publish(self, work: ConversationPublicationRequest) -> ConversationPublicationResult:
        message = str(work.intent.arguments.get("message", "Status acknowledged."))
        try:
            result = self._immutable("conversation", work, message)
        except GitHubBoundaryError as error:
            raise ActivityError(
                "GitHub publication boundary unavailable", kind="GitHubBoundaryError", retryable=True
            ) from error
        except ValueError as error:
            raise ActivityError("GitHub publication invariant failed", kind="ValueError", retryable=False) from error
        except StaleAuthorityError:
            return ConversationPublicationResult(work.epoch, work.head, False, operation=work.operation)
        return ConversationPublicationResult(
            work.epoch,
            work.head,
            result.capability_available,
            operation=work.operation,
            capability_available=result.capability_available,
        )

    def finding_publish(self, work: FindingPublicationRequest) -> FindingPublicationResult:
        try:
            self._fence(work)
            references: list[dict] = []
            for finding in work.findings:
                identity = str(finding.get("id", "unknown"))
                operation = f"{work.operation}:{identity}"
                lineage = next((x for x in work.lineage if x.get("finding_id") == identity), {})
                body = (
                    f"### {finding.get('title', identity)}\n\n{finding.get('body', '')}\n\n"
                    f"Generation: `{work.epoch}` · Head: `{work.head}`\n\nEvidence: {finding.get('evidence', '')}\n\n"
                    f"Lineage: `{json.dumps(lineage, sort_keys=True)}`"
                )
                related = tuple(
                    (str(location.get("path", "")), int(location.get("line", 0)))
                    for location in finding.get("related_locations", [])
                    if isinstance(location, dict)
                )
                published = self.publisher.finding(
                    operation,
                    work.epoch,
                    work.head,
                    body,
                    path=str(finding.get("path", "")),
                    line=int(finding.get("line", 0)),
                    related_locations=related,
                    suggestion=str(finding.get("suggestion", "")),
                    authority_operation=work.operation,
                )
                if published.reference is None:
                    raise RuntimeError("GitHub did not return a finding reference")
                references.append({"finding_id": identity, "url": published.reference.url, "inline": published.inline})
        except RuntimeError:
            return FindingPublicationResult(work.epoch, work.head, False, operation=work.operation)
        return FindingPublicationResult(work.epoch, work.head, True, operation=work.operation, references=references)

    def dashboard_publish(self, work: DashboardPublicationRequest) -> DashboardPublicationResult:
        control = work.control.dump()
        body = self._dashboard(control)
        try:
            self._fence(work)
            result = self.publisher.dashboard(work.operation, work.epoch, work.head, body)
        except GitHubBoundaryError as error:
            raise ActivityError(
                "GitHub publication boundary unavailable", kind="GitHubBoundaryError", retryable=True
            ) from error
        except ValueError as error:
            raise ActivityError("GitHub publication invariant failed", kind="ValueError", retryable=False) from error
        except StaleAuthorityError:
            return DashboardPublicationResult(work.epoch, work.head, False, operation=work.operation)
        return DashboardPublicationResult(
            work.epoch,
            work.head,
            result.capability_available,
            operation=work.operation,
            capability_available=result.capability_available,
        )

    def reminder_publish(self, work: ReminderPublicationRequest) -> ReminderPublicationResult:
        try:
            self._fence(work)
            result = self.publisher.reminder(
                work.operation,
                work.epoch,
                work.head,
                reviewer=work.reviewer or None,
                author=work.author,
            )
        except RuntimeError:
            return ReminderPublicationResult(work.epoch, work.head, False, operation=work.operation)
        return ReminderPublicationResult(
            work.epoch,
            work.head,
            result.capability_available,
            operation=work.operation,
            capability_available=result.capability_available,
        )

    def readiness_publish(self, command: ReadinessCommand) -> ReadinessPublicationResult:
        legacy = "## Hamsterdan readiness advisory\n\nAll observed gates are ready. Advisory only; Hamsterdan does not merge PRs."
        try:
            result = self._immutable(
                "readiness",
                command,
                "## Hamsterdan readiness advisory\n\n"
                "All observed gates are ready. Clean. Humans keep merge authority; Dan never merges PRs.",
                compatible_bodies=(legacy,),
            )
        except GitHubBoundaryError as error:
            raise ActivityError(
                "GitHub publication boundary unavailable", kind="GitHubBoundaryError", retryable=True
            ) from error
        except ValueError as error:
            raise ActivityError("GitHub publication invariant failed", kind="ValueError", retryable=False) from error
        except StaleAuthorityError:
            return ReadinessPublicationResult(command.epoch, command.head, False, operation=command.operation)
        return ReadinessPublicationResult(
            command.epoch,
            command.head,
            result.capability_available,
            operation=command.operation,
            capability_available=result.capability_available,
        )

    def repair(self, work: RepairRequest) -> RepairResult:
        return self._code(work, "repair", RepairResult)

    def change(self, work: ChangeRequest) -> ChangeResult:
        return self._code(work, "change", ChangeResult)

    def _code(self, work: CodeRequest, kind: str, result_type: type[CodeResult]) -> CodeResult:
        if self.git_publisher is None:
            raise RuntimeError("host Git publishing is not configured")
        intent = work.intent.dump() if isinstance(work, ChangeRequest) else {}
        intent_kind = str(intent.get("kind", kind))
        actions = work.actions.dump() if isinstance(work, RepairRequest) else {}
        request = agents.CodingRequest(
            kind,
            self.repository,
            self.pr_number,
            work.epoch,
            work.head,
            work.base_head,
            f"hamsterdan/{kind}/{work.operation[-16:]}",
            selected_work=[intent] if intent else [],
            failure_evidence=[actions] if actions else [],
            fingerprint=str(actions.get("fingerprint", "")),
            lineage=work.lineage,
            reproduction_status="unknown",
            merge_base=intent_kind in {"update_base", "resolve_conflict"},
        )
        result: agents.CodingResult | None = None
        for attempt in range(1, MAX_CODING_ATTEMPTS + 1):
            try:
                self._fence(work)
            except RuntimeError:
                LOG.warning(
                    "agent coding stopped kind=%s category=stale_authority attempt=%s epoch=%s head=%s operation=%s",
                    kind,
                    attempt,
                    work.epoch,
                    work.head,
                    work.operation,
                )
                break
            try:
                result = self.runner.code(
                    self.public_clone_url,
                    request,
                    operation=work.operation,
                    attempt=attempt,
                    is_current=lambda: self._is_current(work),
                )
            except agents.AgentProtocolError as error:
                self._log_agent_error(kind, work, error)
                if error.result_category is not None or error.cleanup_category is not None:
                    return result_type(
                        work.epoch,
                        work.head,
                        False,
                        fingerprint=request.fingerprint,
                        lineage=work.operation,
                        operation=work.operation,
                        agent_result_category=("" if error.result_category is None else error.result_category.value),
                        agent_cleanup_category=("" if error.cleanup_category is None else error.cleanup_category.value),
                    )
                if error.canceled:
                    break
                continue
            if result.status == "changed":
                break
            category = {
                "unchanged": agents.AgentResultCategory.UNCHANGED,
                "unable": agents.AgentResultCategory.UNABLE,
            }.get(result.status, agents.AgentResultCategory.OUTPUT_SCHEMA)
            LOG.warning(
                "agent coding attempt produced no change kind=%s category=%s attempt=%s epoch=%s head=%s operation=%s",
                kind,
                category.value,
                attempt,
                work.epoch,
                work.head,
                work.operation,
            )
            return result_type(
                work.epoch,
                work.head,
                False,
                fingerprint=request.fingerprint,
                lineage=work.operation,
                operation=work.operation,
                agent_result_category=category.value,
            )
        if result is None or result.status != "changed":
            return result_type(
                work.epoch,
                work.head,
                False,
                fingerprint=request.fingerprint,
                lineage=work.operation,
                operation=work.operation,
            )
        try:
            self._fence(work)
        except GitHubBoundaryError:
            LOG.warning(
                "agent coding result rejected kind=%s category=publication_boundary epoch=%s head=%s operation=%s",
                kind,
                work.epoch,
                work.head,
                work.operation,
            )
            return result_type(
                work.epoch,
                work.head,
                False,
                fingerprint=request.fingerprint,
                lineage=work.operation,
                operation=work.operation,
                publication_category=PublicationCategory.BOUNDARY_UNAVAILABLE.value,
            )
        except RuntimeError:
            LOG.warning(
                "agent coding result rejected kind=%s category=stale_authority epoch=%s head=%s operation=%s",
                kind,
                work.epoch,
                work.head,
                work.operation,
            )
            return result_type(
                work.epoch,
                work.head,
                False,
                fingerprint=request.fingerprint,
                lineage=work.operation,
                operation=work.operation,
                publication_category=PublicationCategory.CURRENT_AUTHORITY.value,
            )
        try:
            published = self.git_publisher.publish(
                result,
                operation=work.operation,
                payload_digest=payload_digest(_publication_identity(work)),
                expected_head=work.head,
                base_head=request.base,
                merge_base=request.merge_base,
            )
        except GitPublishError as error:
            LOG.warning(
                "agent coding result rejected kind=%s category=publication reason=%s epoch=%s head=%s operation=%s",
                kind,
                str(error),
                work.epoch,
                work.head,
                work.operation,
            )
            return result_type(
                work.epoch,
                work.head,
                False,
                fingerprint=request.fingerprint,
                lineage=work.operation,
                operation=work.operation,
                publication_category=error.category.value,
            )
        except RuntimeError as error:
            LOG.warning(
                "agent coding result rejected kind=%s category=publication_boundary error_type=%s "
                "epoch=%s head=%s operation=%s",
                kind,
                type(error).__name__,
                work.epoch,
                work.head,
                work.operation,
            )
            return result_type(
                work.epoch,
                work.head,
                False,
                fingerprint=request.fingerprint,
                lineage=work.operation,
                operation=work.operation,
                publication_category=PublicationCategory.BOUNDARY_UNAVAILABLE.value,
            )
        return result_type(
            work.epoch, work.head, True, published.head, request.fingerprint, work.operation, work.operation
        )

    def _is_current(self, work) -> bool:
        return self.current is None or self.current(work.epoch, work.head)

    def _intent(self, raw: dict, work: ConversationClassificationRequest, control: dict) -> Intent:
        kind, arguments = cast(Any, str(raw["type"])), dict(raw.get("arguments", {}))
        digest = _intent_digest(self.repository, self.pr_number, work, kind, arguments)
        return Intent(
            work.epoch,
            work.head,
            kind,
            digest,
            True,
            kind in _MUTATIONS,
            arguments,
            work.base_head,
            work.policy_digest,
        )

    def _intent_declarations(self, control: dict) -> list[dict]:
        arguments = {
            "reply": ["message"],
            "status": [],
            "acknowledge": ["findings"],
            "dismiss": ["findings"],
            "defer": ["findings"],
            "snooze": [],
            "resume": [],
            "reassign": ["assignee"],
            "change": ["request"],
            "update_base": ["request"],
            "resolve_conflict": ["request"],
            "recover_publication": ["target", "operation"],
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

    @staticmethod
    def _conversation_gates(control: dict) -> list[dict]:
        current = ReadinessSnapshot(**control)
        overall = workflow_gates_ready(current)
        findings_clear = current.review == "clear" and not any(
            finding.get("blocking") and finding.get("disposition") in {"new", "still_open"}
            for finding in current.findings
        )
        return [
            {"name": "overall", "ready": overall, "blocker": "" if overall else workflow_wait(current)},
            {"name": "actions", "ready": current.actions in {"green", "flaky_green"}, "state": current.actions},
            {"name": "findings", "ready": findings_clear, "state": current.review},
            {
                "name": "human_review",
                "ready": current.human_approved
                and not current.changes_requested
                and current.unresolved_conversations == 0
                and (not current.distinct_reviewer_required or current.distinct_reviewer_approved),
            },
            {"name": "base", "ready": current.base_current or not current.strict_base},
            {"name": "mergeability", "ready": current.mergeable and not current.conflict},
        ]

    @staticmethod
    def _status(control: dict) -> str:
        current = ReadinessSnapshot(**control)
        if workflow_gates_ready(current):
            return "Ready: every observed gate is clear. Clean. I'll keep one paw on the wheel."
        return f"Waiting for {workflow_wait(current)}. That's the next gate; I'm keeping watch."

    @staticmethod
    def _dashboard(c: dict) -> str:
        control = ReadinessSnapshot(**c)
        gates_ready = workflow_gates_ready(control)
        wait = workflow_wait(control)
        findings = c.get("findings", [])
        lines = [
            f"- `{x.get('id')}` {x.get('disposition', 'new')} — {x.get('title', '')}"
            + (f" ([detail]({x['comment_url']}))" if x.get("comment_url") else "")
            for x in findings
        ] or ["- None"]
        run = (
            f"[run {c.get('run_id')}](https://github.com/{c.get('repository_id')}/actions/runs/{c.get('run_id')})"
            if c.get("run_id")
            else "no adopted run"
        )
        capabilities = (
            f"Actions blocking={c.get('actions_capability_blocking')}; human blocking={c.get('human_capability_blocking')}; "
            f"dashboard blocking={c.get('dashboard_capability_blocking')}; "
            f"conversation reply blocking={c.get('conversation_capability_blocking')}; "
            f"finding publication blocking={c.get('finding_capability_blocking')}; "
            f"readiness publication blocking={c.get('readiness_capability_blocking')}"
        )
        return (
            f"## Hamsterdan PR readiness dashboard\n\nGeneration: `{c.get('epoch')}` · Head: `{c.get('head')}`\n\n"
            f"Actions: **{c.get('actions')}**, attempt {c.get('attempt')} (flaky={c.get('actions') == 'flaky_green'}) · {run}\n\n"
            f"Coordinating agent review: **{c.get('review')}**\n\n"
            f"### Findings / lineage\n" + "\n".join(lines) + f"\n\nHuman approved: {c.get('human_approved')} · "
            f"Review requested: {c.get('human_requested')} · Required approvals: {c.get('required_approvals')} · "
            f"Distinct approval: {c.get('distinct_reviewer_approved')}\n\n"
            f"Base policy: **{'strict / update required' if c.get('strict_base') else 'non-strict'}** · "
            f"Observed base: `{c.get('base_head')}` · Base current: {c.get('base_current')}\n\n"
            f"Mergeable: {c.get('mergeable')} · Conflict: {c.get('conflict')} · "
            f"Unresolved conversations: {c.get('unresolved_conversations')}\n\n"
            f"Mutation in flight: {c.get('change_in_flight')} · Provisional: {c.get('provisional')}\n\n"
            f"Capabilities: {capabilities}\n\nReadiness: **{'ready' if gates_ready else 'not ready'}** · "
            f"Waiting for: {wait}\n\nAdvisory only; humans keep merge authority. "
            "I keep the dashboard current, not the merge button."
        )

    @staticmethod
    def _log_agent_error(
        kind: str,
        work: CodeRequest | ReviewRequest | ConversationClassificationRequest,
        error: agents.AgentProtocolError,
    ) -> None:
        category = (
            error.result_category.value
            if error.result_category is not None
            else "canceled"
            if error.canceled
            else "timed_out"
            if error.timed_out
            else "protocol"
        )
        cleanup = "" if error.cleanup_category is None else error.cleanup_category.value
        LOG.warning(
            "agent activity unavailable kind=%s category=%s cleanup=%s epoch=%s head=%s operation=%s",
            kind,
            category,
            cleanup,
            work.epoch,
            work.head,
            work.operation,
        )

    def _immutable(
        self,
        kind: str,
        value: ConversationPublicationRequest | ReadinessCommand,
        body: str,
        *,
        compatible_bodies: tuple[str, ...] = (),
    ):
        self._fence(value)
        marker = self.publisher.marker(kind, value.operation, value.head)
        existing = self.publisher._find(marker)
        expected = f"{body}\n\n{marker}"
        compatible = {f"{item}\n\n{marker}" for item in compatible_bodies}
        if existing is not None and existing.get("body") != expected and existing.get("body") not in compatible:
            raise ValueError("stable publication operation collided with a different payload")
        return self.publisher.immutable(
            kind,
            value.operation,
            value.epoch,
            value.head,
            body,
            compatible_bodies=compatible_bodies,
        )


def _intent_digest(
    repository: str,
    pr: int,
    work: ConversationClassificationRequest,
    kind: str,
    arguments: dict,
) -> str:
    value = {
        "repository": repository,
        "pr": pr,
        "epoch": work.epoch,
        "head": work.head,
        "base": work.base_head,
        "policy": work.policy_digest,
        "source_operation": work.operation,
        "type": kind,
        "arguments": arguments,
    }
    return _digest(value)


def activity_definitions(operations: PrReadinessActivities) -> dict[str, ActivityDefinition]:
    names = (
        "review",
        "actions_discovery",
        "actions_rerun",
        "conversation",
        "conversation_publish",
        "repair",
        "change",
        "finding_publish",
        "dashboard_publish",
        "reminder_publish",
        "readiness_publish",
    )
    return {
        name: activity(getattr(operations, name), name=name, converter=PydanticPayloadConverter()) for name in names
    }
