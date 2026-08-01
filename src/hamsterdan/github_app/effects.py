"""Lookup-first, fenced GitHub PR comment effects."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast

from .gateway import GitHubAuthority
from .models import ActionsRunSnapshot, CommentReference, GitHubBoundaryError, PublicationResult, Transport

Fence = Callable[[str, int, int, str, str], None]


class CommentPublisher:
    """Lookup-first comments with an immediate pre-effect stale fence."""

    def __init__(self, transport: Transport, repository: str, pr_number: int, bot_login: str, fence: Fence):
        normalized_login = bot_login.strip().casefold()
        if not normalized_login or not normalized_login.endswith("[bot]"):
            raise ValueError("bot login must be the configured GitHub App bot login")
        self.transport, self.repository, self.pr_number, self.bot_login, self.fence = (
            transport,
            repository,
            pr_number,
            normalized_login,
            fence,
        )
        self.root = f"/repos/{repository}/issues/{pr_number}/comments"
        self.edit_root = f"/repos/{repository}/issues/comments"

    @staticmethod
    def marker(kind: str, operation: str, head: str) -> str:
        return f"<!-- hamsterdan:{kind} operation={operation} head={head} -->"

    def _comments(self) -> tuple[dict[str, Any], ...]:
        return self.transport.pages(f"{self.root}?per_page=100")

    def _find(self, marker: str) -> Mapping[str, Any] | None:
        return next(
            (
                item
                for item in self._comments()
                if _login(item) == self.bot_login and marker in str(item.get("body", ""))
            ),
            None,
        )

    def immutable(
        self,
        kind: str,
        operation: str,
        epoch: int,
        head: str,
        body: str,
        *,
        authority_operation: str | None = None,
    ) -> PublicationResult:
        marker = self.marker(kind, operation, head)
        existing = self._find(marker)
        if existing:
            return PublicationResult("existing", _reference(existing))
        payload = f"{body}\n\n{marker}"
        self.fence(self.repository, self.pr_number, epoch, head, authority_operation or operation)
        response = self.transport.request("POST", self.root, {"body": payload})
        if response.status != 201 or not isinstance(response.body, dict):
            raise GitHubBoundaryError("GitHub did not prove comment publication")
        return PublicationResult("created", _reference(_response_mapping(response.body)))

    def dashboard(self, operation: str, epoch: int, head: str, body: str) -> PublicationResult:
        marker = "<!-- hamsterdan:dashboard -->"
        existing = self._find(marker)
        payload = f"{body}\n\n{marker}"
        if existing is None:
            self.fence(self.repository, self.pr_number, epoch, head, operation)
            response = self.transport.request("POST", self.root, {"body": payload})
            if response.status != 201 or not isinstance(response.body, dict):
                raise GitHubBoundaryError("GitHub did not prove dashboard publication")
            return PublicationResult("created", _reference(_response_mapping(response.body)))
        if existing.get("body") == payload:
            return PublicationResult("existing", _reference(existing))
        self.fence(self.repository, self.pr_number, epoch, head, operation)
        response = self.transport.request("PATCH", f"{self.edit_root}/{existing['id']}", {"body": payload})
        if response.status in {403, 404}:
            return PublicationResult("update_unavailable", _reference(existing), False)
        if response.status != 200 or not isinstance(response.body, dict):
            raise GitHubBoundaryError("GitHub did not prove dashboard update")
        return PublicationResult("updated", _reference(_response_mapping(response.body)))

    def finding(
        self,
        operation: str,
        epoch: int,
        head: str,
        text: str,
        *,
        location: str = "",
        link: str = "",
        authority_operation: str | None = None,
    ) -> PublicationResult:
        detail = "\n".join(
            item
            for item in (text, f"Location: {location}" if location else "", f"Link: {link}" if link else "")
            if item
        )
        result = self.immutable(
            "finding",
            operation,
            epoch,
            head,
            detail,
            authority_operation=authority_operation,
        )
        return PublicationResult(result.status, result.reference, result.capability_available, inline=False)

    def reminder(
        self, operation: str, epoch: int, head: str, *, reviewer: str | None, author: str, maintainer: str | None = None
    ) -> PublicationResult:
        target = reviewer or maintainer or author
        action = "please review this PR" if reviewer else "please assign a reviewer for this PR"
        dashboard = self._find("<!-- hamsterdan:dashboard -->")
        state = str(dashboard.get("html_url", "")) if dashboard is not None else ""
        link = f" [See current readiness state.]({state})" if state else ""
        return self.immutable("reminder", operation, epoch, head, f"@{target.lstrip('@')}, {action}.{link}")

    @property
    def reviewer_assignment_available(self) -> bool:
        return False


def _reference(value: Mapping[str, Any]) -> CommentReference:
    return CommentReference(int(value["id"]), str(value.get("html_url", "")))


def _response_mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value)


def _login(value: Mapping[str, Any]) -> str | None:
    user = value.get("user")
    login = user.get("login") if isinstance(user, Mapping) else None
    return login.strip().casefold() if isinstance(login, str) else None


class RerunPort(Protocol):
    def request(self, run: ActionsRunSnapshot, *, epoch: int, operation: str) -> PublicationResult: ...


class CommentRerunBroker:
    """Requests, but never claims observation of, a same-head whole-run rerun."""

    def __init__(self, authority: GitHubAuthority, publisher: CommentPublisher):
        self.authority, self.publisher = authority, publisher

    def request(self, run: ActionsRunSnapshot, *, epoch: int, operation: str) -> PublicationResult:
        pull = self.authority.pull_request()
        known = {candidate.id: candidate for candidate in self.authority.workflow_runs(run.workflow, pull.head)}
        if pull.head != run.head or run.id not in known:
            raise GitHubBoundaryError("rerun request does not belong to the configured repository and exact head")
        marker = f"<!-- hamsterdan-rerun run={run.id} head={run.head} operation={operation} -->"
        existing = self.publisher._find(marker)
        if existing:
            return PublicationResult("existing", _reference(existing))
        # The broker marker is intentionally its complete strict grammar.
        self.publisher.fence(self.publisher.repository, self.publisher.pr_number, epoch, run.head, operation)
        response = self.publisher.transport.request("POST", self.publisher.root, {"body": marker})
        if response.status != 201 or not isinstance(response.body, dict):
            raise GitHubBoundaryError("GitHub did not prove rerun broker publication")
        return PublicationResult("requested", _reference(_response_mapping(response.body)))
