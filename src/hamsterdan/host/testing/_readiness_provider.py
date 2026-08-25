"""Modeled external truth and boundary-faithful adapters for readiness DST."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, cast

from petrus.testing.dst import ScenarioContext
from pydantic import JsonValue

from hamsterdan.agents import AgentProtocolError, CodingResult, ConversationResult, ReviewResult
from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.models import GitHubBoundaryError, InstallationInventory, RegistrationInventory, WireResponse
from hamsterdan.host.git_publish import (
    GitPublishError,
    GitPublishResult,
    GitReconciliation,
    PublicationCategory,
)
from hamsterdan.testing.readiness import AuthorityClaim

from ._readiness_contract import (
    BASE,
    BOT,
    HEAD,
    PROFILE_LIMITS,
    READINESS_POLICY_DIGEST,
    strict_digest,
)

_EFFECT_MARKER = re.compile(
    r"<!-- hamsterdan:(conversation|finding|readiness|reminder) operation=([A-Za-z0-9._:-]+) head=([0-9a-f]{40}) -->"
)


@dataclass
class _Effect:
    kind: str
    operation: str
    head: str
    content_digest: str
    authority: AuthorityClaim
    provider_authority_at_acceptance: AuthorityClaim
    body: str
    accepted_at: int
    semantic_order: int
    visible: bool = True
    response_lost: bool = False
    recovered: bool = False
    reference: int = 0


@dataclass
class _Emitted:
    delivery: str
    event: str
    action: str
    authority: AuthorityClaim
    comment: dict[str, JsonValue] | None = None
    source_identity: str = ""
    instant: int = 0
    semantic_order: int = 0


@dataclass
class _GitPublication:
    operation: str
    payload_digest: str
    expected_head: str
    result_head: str
    authority: AuthorityClaim
    accepted_at: int
    semantic_order: int
    response_lost: bool = False
    recovered: bool = False
    recovery_identity: str = ""


class ReadinessProviderTruth:
    """Independent GitHub/agent truth with strict fail-closed request routing."""

    def __init__(self) -> None:
        self.authority = AuthorityClaim(
            44,
            31,
            7,
            HEAD,
            BASE,
            READINESS_POLICY_DIGEST,
            "active",
            True,
            True,
            True,
        )
        self.authorities = [self.authority]
        self.required_checks: tuple[str, ...] = ("build",)
        self.checks: list[dict[str, JsonValue]] = []
        self.review_head = ""
        self.review_status = "pending"
        self.findings: list[dict[str, JsonValue]] = []
        self.human_reviews: dict[str, tuple[str, str]] = {}
        self.review_threads: dict[str, bool] = {}
        self.comments: list[dict[str, Any]] = []
        self.human_comments: list[dict[str, JsonValue]] = []
        self.effects: list[_Effect] = []
        self.effect_authorities: dict[tuple[str, str], AuthorityClaim] = {}
        self.collisions: list[str] = []
        self.emitted: dict[str, _Emitted] = {}
        self.custodied: list[str] = []
        self.admitted: list[_Emitted] = []
        self.active_admission: _Emitted | None = None
        self.custody_actions: list[dict[str, JsonValue]] = []
        self.delivery_attempts: Counter[str] = Counter()
        self.agent_calls: list[dict[str, JsonValue]] = []
        self.agent_terminals: dict[str, dict[str, JsonValue]] = {}
        self.review_terminal: dict[str, JsonValue] | None = None
        self.git_publications: list[_GitPublication] = []
        self.git_reconciliations = 0
        self.git_proof_unavailable: set[str] = set()
        self.calls: list[dict[str, JsonValue]] = []
        self.harness_errors: list[str] = []
        self.provider_truth_changes = 0
        self._semantic_order = 0

    def set_authority(self, authority: AuthorityClaim) -> None:
        self.authority = authority
        if authority != self.authorities[-1]:
            self.authorities.append(authority)

    def bind_effect_authority(self, kind: str, operation: str, authority: AuthorityClaim) -> None:
        """Bind one provider operation to the full authority that authored it."""
        key = kind, operation
        existing = self.effect_authorities.get(key)
        if (
            existing is not None
            and existing != authority
            and any(effect.kind == kind and effect.operation == operation for effect in self.effects)
        ):
            raise ValueError("stable provider operation was reused under different authored authority")
        self.effect_authorities[key] = authority

    def admit(self, emitted: _Emitted, instant: int, authority: AuthorityClaim | None = None) -> None:
        self.admitted.append(
            _Emitted(
                delivery=emitted.delivery,
                event=emitted.event,
                action=emitted.action,
                authority=self.authority if authority is None else authority,
                comment=emitted.comment,
                source_identity=emitted.source_identity,
                instant=instant,
                semantic_order=self._next_semantic_order(),
            )
        )

    def set_human_comment(self, identity: int, author: str, fixture: str) -> None:
        if any(comment["id"] == identity for comment in self.human_comments):
            raise ValueError("human comment identity was reused")
        if fixture == "change":
            body = "@hamsterdan-test Apply the deterministic readiness change."
        elif fixture.startswith("recover:"):
            operation = fixture.removeprefix("recover:")
            body = f"@hamsterdan-test Recover publication {operation}."
        else:
            raise ValueError("unsupported human comment fixture")
        comment: dict[str, JsonValue] = {
            "id": identity,
            "body": body,
            "author": author,
            "fixture": fixture,
            "user": {"id": 701, "login": author, "type": "User"},
            "author_association": "OWNER",
        }
        self.human_comments.append(comment)
        self.comments.append(
            {
                "id": identity,
                "html_url": f"https://example.test/comments/{identity}",
                "body": body,
                "user": {"login": author},
                "visible": True,
            }
        )

    def admitted_recoveries(self) -> list[dict[str, JsonValue]]:
        recoveries: list[dict[str, JsonValue]] = []
        for event in self.admitted:
            fixture = None if event.comment is None else event.comment.get("fixture")
            if not isinstance(fixture, str) or not fixture.startswith("recover:"):
                continue
            recoveries.append(
                {
                    "operation": fixture.removeprefix("recover:"),
                    "identity": event.source_identity or f"github-delivery:{event.delivery}",
                }
            )
        return recoveries

    def recovery_identity(self, operation: str, *, include_active: bool = False) -> str:
        active = self.active_admission
        if include_active and active is not None and active.comment is not None:
            fixture = active.comment.get("fixture")
            if fixture == f"recover:{operation}":
                return active.source_identity or f"github-delivery:{active.delivery}"
        return next(
            (
                cast(str, recovery["identity"])
                for recovery in reversed(self.admitted_recoveries())
                if recovery["operation"] == operation
            ),
            "",
        )

    def request(
        self,
        method: str,
        path: str,
        body: object | None = None,
        *,
        context: ScenarioContext | None = None,
    ) -> WireResponse:
        self._provider_call()
        self.calls.append({"method": method, "path": path})
        root = "/repos/owner/repo"
        authority = self.authority
        if method == "GET" and path == f"{root}/pulls/7":
            state = "closed" if authority.lifecycle in {"closed", "merged"} else "open"
            return WireResponse(
                200,
                {
                    "state": state,
                    "draft": authority.lifecycle == "draft",
                    "mergeable": authority.mergeable,
                    "mergeable_state": "clean" if authority.mergeable else "dirty",
                    "merged": authority.lifecycle == "merged",
                    "html_url": "https://example.test/owner/repo/pull/7",
                    "user": {"login": "author"},
                    "head": {"sha": authority.head, "ref": "feature", "repo": {"full_name": "owner/repo"}},
                    "base": {"sha": authority.base, "ref": "main"},
                },
            )
        if method == "GET" and path == f"{root}/git/ref/heads/main":
            return WireResponse(200, {"object": {"sha": authority.base}})
        if method == "GET" and path == f"{root}/rules/branches/main":
            return WireResponse(
                200,
                [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "strict_required_status_checks_policy": authority.strict_base,
                            "required_status_checks": [{"context": name} for name in self.required_checks],
                        },
                    },
                    {
                        "type": "pull_request",
                        "parameters": {
                            "required_approving_review_count": 0,
                            "required_review_thread_resolution": False,
                        },
                    },
                ],
            )
        if method == "GET" and path == f"{root}/compare/{authority.base}...{authority.head}":
            return WireResponse(200, {"status": "ahead", "behind_by": 0 if authority.base_current else 1})
        if method == "GET" and path == f"{root}/pulls/7/requested_reviewers":
            return WireResponse(200, {"users": []})
        if method == "GET" and path.startswith(
            f"{root}/actions/workflows/.github%2Fworkflows%2Fci.yml/runs?event=pull_request&head_sha="
        ):
            runs: dict[tuple[int, int], list[dict[str, JsonValue]]] = {}
            for check in self.checks:
                runs.setdefault((cast(int, check["run"]), cast(int, check["attempt"])), []).append(check)
            values = []
            for (run, attempt), checks in sorted(runs.items()):
                statuses = {str(item["status"]) for item in checks}
                completed = statuses <= {"success", "failure", "canceled"}
                conclusion = (
                    "failure" if "failure" in statuses or "canceled" in statuses else "success" if completed else None
                )
                values.append(
                    {
                        "id": run,
                        "run_attempt": attempt,
                        "head_sha": self.review_head or authority.head,
                        "event": "pull_request",
                        "path": ".github/workflows/ci.yml",
                        "status": "completed" if completed else "in_progress",
                        "conclusion": conclusion,
                        "pull_requests": [{"number": 7}],
                    }
                )
            return WireResponse(200, {"total_count": len(values), "workflow_runs": values})
        jobs = re.fullmatch(
            rf"{re.escape(root)}/actions/runs/([1-9][0-9]*)/attempts/([1-9][0-9]*)/jobs\?per_page=100", path
        )
        if method == "GET" and jobs is not None:
            run, attempt = int(jobs.group(1)), int(jobs.group(2))
            values = []
            for index, check in enumerate(self.checks, start=1):
                if (check["run"], check["attempt"]) != (run, attempt):
                    continue
                status = str(check["status"])
                values.append(
                    {
                        "id": run * 100 + index,
                        "name": check["name"],
                        "status": "completed" if status in {"success", "failure", "canceled"} else "in_progress",
                        "conclusion": status
                        if status in {"success", "failure"}
                        else "failure"
                        if status == "canceled"
                        else None,
                    }
                )
            return WireResponse(200, {"total_count": len(values), "jobs": values})
        if (
            method == "POST"
            and path == "/graphql"
            and isinstance(body, dict)
            and "reviewThreads" in str(body.get("query"))
        ):
            return WireResponse(
                200,
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [
                                        {"id": identity, "isResolved": resolved}
                                        for identity, resolved in sorted(self.review_threads.items())
                                    ],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                }
                            }
                        }
                    }
                },
            )
        if method == "POST" and path == f"{root}/issues/7/comments" and isinstance(body, dict):
            return self._accept_comment(str(body.get("body", "")), context)
        dashboard = re.fullmatch(rf"{re.escape(root)}/issues/comments/([1-9][0-9]*)", path)
        if method == "PATCH" and dashboard is not None and isinstance(body, dict):
            identifier = int(dashboard.group(1))
            comment = next((item for item in self.comments if item["id"] == identifier), None)
            if comment is None:
                return WireResponse(404, {})
            comment["body"] = str(body.get("body", ""))
            return WireResponse(200, dict(comment))
        message = f"undeclared provider request: {method} {path}"
        self.harness_errors.append(message)
        raise AssertionError(message)

    def pages(self, path: str) -> tuple[dict[str, Any], ...]:
        root = "/repos/owner/repo"
        self._provider_call()
        self.calls.append({"method": "PAGES", "path": path})
        if path == f"{root}/issues/7/comments?per_page=100":
            for effect in self.effects:
                if effect.response_lost and effect.visible and not effect.recovered:
                    effect.recovered = True
            return tuple(dict(item) for item in self.comments if item.get("visible", True))
        if path == f"{root}/pulls/7/comments?per_page=100":
            return ()
        if path == f"{root}/pulls/7/reviews?per_page=100":
            return tuple(
                {
                    "id": index,
                    "submitted_at": submitted,
                    "state": state,
                    "user": {"login": reviewer},
                }
                for index, (reviewer, (submitted, state)) in enumerate(sorted(self.human_reviews.items()), start=1)
            )
        message = f"undeclared provider pages request: {path}"
        self.harness_errors.append(message)
        raise AssertionError(message)

    def _accept_comment(self, payload: str, context: ScenarioContext | None) -> WireResponse:
        marker = payload.rsplit("\n\n", 1)[-1]
        matched = _EFFECT_MARKER.fullmatch(marker)
        if (
            matched is None
            and marker != "<!-- hamsterdan:dashboard -->"
            and not marker.startswith("<!-- hamsterdan-rerun ")
        ):
            message = "undeclared provider comment payload"
            self.harness_errors.append(message)
            raise AssertionError(message)
        if matched is None:
            kind, operation, head = "dashboard", f"dashboard:{strict_digest(payload)[:24]}", self.authority.head
        else:
            kind, operation, head = matched.groups()
        attempted_authority = self.effect_authorities.get((kind, operation))
        if attempted_authority is None:
            if kind == "readiness":
                message = "readiness provider effect has no exact authored authority binding"
                self.harness_errors.append(message)
                raise AssertionError(message)
            attempted_authority = next(
                (authority for authority in reversed(self.authorities) if authority.head == head),
                self.authority,
            )
        existing = next((effect for effect in self.effects if effect.operation == operation), None)
        if existing is not None:
            if existing.content_digest != strict_digest(payload) or existing.authority != attempted_authority:
                raise ValueError("stable provider operation collided with different content")
            comment = next(item for item in self.comments if item["id"] == existing.reference)
            return WireResponse(201, dict(comment))
        faults = () if context is None else context.faults(f"effect:{kind}")
        cut = None
        for fault in faults:
            payload_value = cast(dict[str, JsonValue], fault.payload)
            cut = payload_value["cut"]
        if cut == "before_acceptance":
            return WireResponse(422, {})
        if cut == "identity_collision":
            self.collisions.append(operation)
            raise ValueError("modeled provider operation identity collision")
        if len(self.effects) >= PROFILE_LIMITS["effects"]:
            raise RuntimeError(f"readiness profile bound effects exhausted at {PROFILE_LIMITS['effects']}")
        identifier = len(self.comments) + 1
        response_lost = cut == "after_acceptance_before_response"
        visible = cut != "before_visibility"
        accepted_at = 0 if context is None else context.now()
        effect = _Effect(
            kind=kind,
            operation=operation,
            head=head,
            content_digest=strict_digest(payload),
            authority=attempted_authority,
            provider_authority_at_acceptance=self.authority,
            body=payload,
            accepted_at=accepted_at,
            semantic_order=self._next_semantic_order(),
            visible=visible,
            response_lost=response_lost,
            reference=identifier,
        )
        self.effects.append(effect)
        comment = {
            "id": identifier,
            "html_url": f"https://example.test/comments/{identifier}",
            "body": payload,
            "user": {"login": BOT},
            "visible": visible,
        }
        self.comments.append(comment)
        if response_lost:
            raise GitHubBoundaryError("modeled provider accepted but response was lost")
        return WireResponse(201, dict(comment))

    def retained_bytes(self) -> int:
        """Return the canonical size of all reconstructable modeled provider truth."""
        data = {
            "authority": self.authority.dump(),
            "authorities": [authority.dump() for authority in self.authorities],
            "required_checks": list(self.required_checks),
            "checks": self.checks,
            "review_head": self.review_head,
            "review_status": self.review_status,
            "findings": self.findings,
            "human_reviews": {key: list(value) for key, value in sorted(self.human_reviews.items())},
            "review_threads": dict(sorted(self.review_threads.items())),
            "comments": self.comments,
            "human_comments": self.human_comments,
            "effects": [
                {
                    "kind": effect.kind,
                    "operation": effect.operation,
                    "head": effect.head,
                    "content_digest": effect.content_digest,
                    "authority": effect.authority.dump(),
                    "provider_authority_at_acceptance": effect.provider_authority_at_acceptance.dump(),
                    "body": effect.body,
                    "accepted_at": effect.accepted_at,
                    "semantic_order": effect.semantic_order,
                    "visible": effect.visible,
                    "response_lost": effect.response_lost,
                    "recovered": effect.recovered,
                    "reference": effect.reference,
                }
                for effect in self.effects
            ],
            "effect_authorities": [
                {"kind": key[0], "operation": key[1], "authority": authority.dump()}
                for key, authority in sorted(self.effect_authorities.items())
            ],
            "collisions": self.collisions,
            "emitted": [
                {
                    "delivery": item.delivery,
                    "event": item.event,
                    "action": item.action,
                    "authority": item.authority.dump(),
                    "comment": item.comment,
                    "source_identity": item.source_identity,
                    "instant": item.instant,
                    "semantic_order": item.semantic_order,
                }
                for item in (self.emitted[key] for key in sorted(self.emitted))
            ],
            "custodied": self.custodied,
            "admitted": [
                {
                    "delivery": item.delivery,
                    "event": item.event,
                    "action": item.action,
                    "authority": item.authority.dump(),
                    "comment": item.comment,
                    "source_identity": item.source_identity,
                    "instant": item.instant,
                    "semantic_order": item.semantic_order,
                }
                for item in self.admitted
            ],
            "custody_actions": self.custody_actions,
            "delivery_attempts": dict(sorted(self.delivery_attempts.items())),
            "agent_calls": self.agent_calls,
            "agent_terminals": dict(sorted(self.agent_terminals.items())),
            "review_terminal": self.review_terminal,
            "git_publications": [self._git_publication_value(item) for item in self.git_publications],
            "git_reconciliations": self.git_reconciliations,
            "git_proof_unavailable": sorted(self.git_proof_unavailable),
            "calls": self.calls,
            "harness_errors": self.harness_errors,
            "provider_truth_changes": self.provider_truth_changes,
        }
        return len(json.dumps(data, allow_nan=False, sort_keys=True, separators=(",", ":")).encode())

    def observation(self) -> dict[str, JsonValue]:
        accepted = Counter(effect.kind for effect in self.effects)
        return {
            "accepted_by_kind": dict(sorted(accepted.items())),
            "effects": [
                {
                    "kind": effect.kind,
                    "operation": effect.operation,
                    "head": effect.head,
                    "authority": effect.authority.dump(),
                    "content_digest": effect.content_digest,
                    "provider_authority_at_acceptance": effect.provider_authority_at_acceptance.dump(),
                    "accepted_at": effect.accepted_at,
                    "semantic_order": effect.semantic_order,
                    "visible": effect.visible,
                    "response_lost": effect.response_lost,
                    "recovered": effect.recovered,
                }
                for effect in self.effects
            ],
            "response_losses": sorted({effect.kind for effect in self.effects if effect.response_lost}),
            "lookup_recoveries": sum(effect.recovered for effect in self.effects),
            "provider_calls": len(self.calls),
            "agent_calls": len(self.agent_calls),
            "agent_call_log": list(self.agent_calls),
            "git_publications": [self._git_publication_value(item) for item in self.git_publications],
            "git_reconciliations": self.git_reconciliations,
            "admitted_recoveries": self.admitted_recoveries(),
            "collisions": sorted(self.collisions),
            "custody_actions": list(self.custody_actions),
        }

    @staticmethod
    def _git_publication_value(item: _GitPublication) -> dict[str, JsonValue]:
        return {
            "operation": item.operation,
            "payload_digest": item.payload_digest,
            "expected_head": item.expected_head,
            "result_head": item.result_head,
            "authority": item.authority.dump(),
            "accepted_at": item.accepted_at,
            "semantic_order": item.semantic_order,
            "response_lost": item.response_lost,
            "recovered": item.recovered,
            "recovery_identity": item.recovery_identity,
        }

    def _provider_call(self) -> None:
        if len(self.calls) >= PROFILE_LIMITS["provider_calls"]:
            raise RuntimeError(
                f"readiness profile bound provider_calls exhausted at {PROFILE_LIMITS['provider_calls']}"
            )

    def _next_semantic_order(self) -> int:
        self._semantic_order += 1
        return self._semantic_order


class ModeledGitPublisher:
    """Deterministic Git ref truth behind the production V5 mutation gate."""

    def __init__(self, truth: ReadinessProviderTruth, context: dict[str, ScenarioContext | None]) -> None:
        self.truth, self.context = truth, context

    def reconcile(
        self,
        *,
        operation: str,
        payload_digest: str,
        expected_head: str,
        base_head: str,
        merge_base: bool = False,
    ) -> GitReconciliation:
        del base_head, merge_base
        if self.truth.git_reconciliations >= PROFILE_LIMITS["git_reconciliations"]:
            raise RuntimeError(
                f"readiness profile bound git_reconciliations exhausted at {PROFILE_LIMITS['git_reconciliations']}"
            )
        self.truth.git_reconciliations += 1
        existing = next((item for item in self.truth.git_publications if item.operation == operation), None)
        if existing is None:
            return GitReconciliation("absent", self.truth.authority.head)
        if existing.payload_digest != payload_digest or existing.expected_head != expected_head:
            raise GitPublishError(PublicationCategory.IDEMPOTENCY, "modeled Git operation identity collided")
        if operation in self.truth.git_proof_unavailable:
            self.truth.git_proof_unavailable.remove(operation)
            raise GitPublishError(PublicationCategory.BOUNDARY_UNAVAILABLE, "modeled Git proof is unavailable")
        existing.recovered = existing.response_lost or existing.recovered
        if existing.response_lost:
            existing.recovery_identity = self.truth.recovery_identity(operation, include_active=True)
        return GitReconciliation("existing", self.truth.authority.head, existing.result_head, (existing.expected_head,))

    def publish(
        self,
        result: CodingResult,
        *,
        operation: str,
        payload_digest: str,
        expected_head: str,
        base_head: str,
        merge_base: bool = False,
    ) -> GitPublishResult:
        del merge_base
        context = self.context["value"]
        if context is None:
            raise RuntimeError("modeled Git publication escaped its atomic profile operation")
        if (
            result.status != "changed"
            or result.head != expected_head
            or result.base != base_head
            or self.truth.authority.head != expected_head
            or self.truth.authority.base != base_head
        ):
            raise GitPublishError(PublicationCategory.CORRELATION, "modeled Git publication is stale")
        if any(item.operation == operation for item in self.truth.git_publications):
            raise GitPublishError(PublicationCategory.IDEMPOTENCY, "modeled Git operation was accepted twice")
        if len(self.truth.git_publications) >= PROFILE_LIMITS["git_publications"]:
            raise RuntimeError(
                f"readiness profile bound git_publications exhausted at {PROFILE_LIMITS['git_publications']}"
            )
        result_head = hashlib.sha256(f"{expected_head}\0{operation}\0{payload_digest}".encode()).hexdigest()[:40]
        faults = context.faults(f"git:{operation}")
        response_lost = False
        for fault in faults:
            payload = cast(dict[str, JsonValue], fault.payload)
            response_lost = payload["cut"] == "ref_cas"
        publication = _GitPublication(
            operation=operation,
            payload_digest=payload_digest,
            expected_head=expected_head,
            result_head=result_head,
            authority=self.truth.authority,
            accepted_at=context.now(),
            semantic_order=self.truth._next_semantic_order(),
            response_lost=response_lost,
        )
        self.truth.git_publications.append(publication)
        self.truth.set_authority(replace(self.truth.authority, head=result_head))
        if response_lost:
            self.truth.git_proof_unavailable.add(operation)
            raise GitPublishError(PublicationCategory.REF_CAS, "modeled Git ref update response was lost")
        return GitPublishResult(result_head)


class ProviderTransport:
    def __init__(self, truth: ReadinessProviderTruth, context: dict[str, ScenarioContext | None]) -> None:
        self.truth, self.context = truth, context

    def request(self, method: str, path: str, body: object | None = None) -> WireResponse:
        return self.truth.request(method, path, body, context=self.context["value"])

    def pages(self, path: str) -> tuple[dict[str, Any], ...]:
        return self.truth.pages(path)


class ProviderClients:
    def __init__(self) -> None:
        self.operation_client = object()

    def installation(self, installation_id: int, repository_ids: list[int] | tuple[int, ...]) -> object:
        if (installation_id, tuple(repository_ids)) != (44, (31,)):
            raise AssertionError("readiness world received undeclared installation authority")
        return self.operation_client

    def registration_inventory(self, config: HostConfig) -> RegistrationInventory:
        del config
        return RegistrationInventory((InstallationInventory(44, 23, ((31, "owner/repo"),)),))

    def close(self) -> None:
        pass


class AgentRunner:
    def __init__(self, truth: ReadinessProviderTruth) -> None:
        self.truth = truth

    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        del repository_url
        if is_current is not None and not is_current():
            raise AgentProtocolError("modeled agent authority moved", canceled=True)
        terminal = self.truth.agent_terminals.get(operation, self.truth.review_terminal)
        if terminal is None or terminal.get("kind") != "review":
            message = "undeclared agent review operation"
            self.truth.harness_errors.append(message)
            raise AssertionError(message)
        status = str(terminal["status"])
        findings = cast(list[dict[str, object]], terminal["findings"])
        self.truth.agent_calls.append(
            {"kind": "review", "operation": operation, "attempt": attempt, "head": request.head, "status": status}
        )
        if status == "unable":
            raise AgentProtocolError("modeled agent unavailable")
        return ReviewResult(
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            status,
            findings,
            [{"finding_id": str(finding["id"]), "state": "new", "supersedes": None} for finding in findings],
        )

    def converse(self, repository_url, request, *, operation, attempt, is_current=None):
        del repository_url, is_current
        terminal = self.truth.agent_terminals.get(operation)
        if terminal is None or terminal.get("kind") not in {"conversation_change", "conversation_recover"}:
            message = "undeclared agent conversation operation"
            self.truth.harness_errors.append(message)
            raise AssertionError(message)
        self._require_terminal(terminal, operation, attempt)
        self.truth.agent_calls.append(
            {"kind": "conversation", "operation": operation, "attempt": attempt, "head": request.head}
        )
        intents: list[dict[str, object]]
        if terminal["kind"] == "conversation_change":
            intents = [
                {
                    "type": "change",
                    "arguments": {"request": "Apply the deterministic readiness change."},
                    "mutation": True,
                    "explicit": True,
                    "confidence": 1.0,
                }
            ]
        else:
            matched = re.search(r"Recover publication ([A-Za-z0-9._:-]+)\.", str(request.comment_context["body"]))
            if matched is None:
                raise AssertionError("modeled recovery conversation has no exact publication operation")
            intents = [
                {
                    "type": "recover_publication",
                    "arguments": {"operation": matched.group(1)},
                    "mutation": False,
                    "explicit": True,
                    "confidence": 1.0,
                }
            ]
        return ConversationResult(
            request.repository, request.pull_request, request.epoch, request.head, request.base, intents
        )

    def code(self, repository_url, request, *, operation, attempt, is_current=None):
        del repository_url, is_current
        terminal = self.truth.agent_terminals.get(operation)
        if terminal is None or terminal.get("kind") != "coding":
            message = "undeclared agent coding operation"
            self.truth.harness_errors.append(message)
            raise AssertionError(message)
        self._require_terminal(terminal, operation, attempt)
        self.truth.agent_calls.append(
            {"kind": "coding", "operation": operation, "attempt": attempt, "head": request.head}
        )
        changed = terminal["status"] == "changed"
        return CodingResult(
            request.kind,
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            request.ref,
            str(terminal["status"]),
            "not_attempted",
            ("diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-before\n+after\n")
            if changed
            else "",
            ["README.md"] if changed else [],
            [],
            "Apply deterministic readiness change" if changed else "",
        )

    @staticmethod
    def _require_terminal(terminal: dict[str, JsonValue], operation: str, attempt: int) -> None:
        if terminal.get("operation") != operation or terminal.get("attempt") != attempt:
            raise AssertionError("modeled agent terminal differs from the exact operation attempt")


def webhook_body(emitted: _Emitted) -> bytes:
    value: dict[str, object] = {
        "action": emitted.action,
        "installation": {"id": 44, "account": {"id": 23}},
        "repository": {"id": 31, "full_name": "owner/repo"},
        "pull_request": {"number": 7},
    }
    if emitted.event == "issue_comment" and emitted.comment is not None:
        value["issue"] = {
            "number": 7,
            "pull_request": {"url": "https://api.example.test/repos/owner/repo/pulls/7"},
        }
        value["comment"] = emitted.comment
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
