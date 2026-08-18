"""Modeled external truth and boundary-faithful adapters for readiness DST."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, cast

from petrus.testing.dst import ScenarioContext
from pydantic import JsonValue

from hamsterdan.agents import AgentProtocolError, CodingResult, ConversationResult, ReviewResult
from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.models import GitHubBoundaryError, RegistrationInventory, WireResponse
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
    body: str
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
        self.effects: list[_Effect] = []
        self.collisions: list[str] = []
        self.emitted: dict[str, _Emitted] = {}
        self.custodied: list[str] = []
        self.admitted: list[_Emitted] = []
        self.custody_actions: list[dict[str, JsonValue]] = []
        self.delivery_attempts: Counter[str] = Counter()
        self.agent_calls: list[dict[str, JsonValue]] = []
        self.agent_terminal: dict[str, JsonValue] | None = None
        self.calls: list[dict[str, JsonValue]] = []
        self.harness_errors: list[str] = []
        self.provider_truth_changes = 0

    def set_authority(self, authority: AuthorityClaim) -> None:
        self.authority = authority
        if authority != self.authorities[-1]:
            self.authorities.append(authority)

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
        attempted_authority = next(
            (authority for authority in reversed(self.authorities) if authority.head == head),
            self.authority,
        )
        existing = next((effect for effect in self.effects if effect.operation == operation), None)
        if existing is not None:
            if existing.content_digest != strict_digest(payload):
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
        effect = _Effect(
            kind,
            operation,
            head,
            strict_digest(payload),
            attempted_authority,
            payload,
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

    def observation(self) -> dict[str, JsonValue]:
        accepted = Counter(effect.kind for effect in self.effects)
        return {
            "accepted_by_kind": dict(sorted(accepted.items())),
            "effects": [
                {
                    "kind": effect.kind,
                    "operation": effect.operation,
                    "head": effect.head,
                    "content_digest": effect.content_digest,
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
            "collisions": sorted(self.collisions),
            "custody_actions": list(self.custody_actions),
        }

    def _provider_call(self) -> None:
        if len(self.calls) >= PROFILE_LIMITS["provider_calls"]:
            raise RuntimeError(
                f"readiness profile bound provider_calls exhausted at {PROFILE_LIMITS['provider_calls']}"
            )


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
        return RegistrationInventory(44, ((31, "owner/repo"),))

    def close(self) -> None:
        pass


class AgentRunner:
    def __init__(self, truth: ReadinessProviderTruth) -> None:
        self.truth = truth

    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        del repository_url
        if is_current is not None and not is_current():
            raise AgentProtocolError("modeled agent authority moved", canceled=True)
        terminal = self.truth.agent_terminal
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
        terminal = self.truth.agent_terminal
        if terminal is None or terminal.get("kind") != "conversation":
            message = "undeclared agent conversation operation"
            self.truth.harness_errors.append(message)
            raise AssertionError(message)
        self.truth.agent_calls.append(
            {"kind": "conversation", "operation": operation, "attempt": attempt, "head": request.head}
        )
        return ConversationResult(
            request.repository, request.pull_request, request.epoch, request.head, request.base, []
        )

    def code(self, repository_url, request, *, operation, attempt, is_current=None):
        del repository_url, is_current
        terminal = self.truth.agent_terminal
        if terminal is None or terminal.get("kind") != "coding":
            message = "undeclared agent coding operation"
            self.truth.harness_errors.append(message)
            raise AssertionError(message)
        self.truth.agent_calls.append(
            {"kind": "coding", "operation": operation, "attempt": attempt, "head": request.head}
        )
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
            "",
            [],
            [],
            "",
        )


def webhook_body(emitted: _Emitted) -> bytes:
    value: dict[str, object] = {
        "action": emitted.action,
        "installation": {"id": 44, "account": {"id": 23}},
        "repository": {"id": 31, "full_name": "owner/repo"},
        "pull_request": {"number": 7},
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
