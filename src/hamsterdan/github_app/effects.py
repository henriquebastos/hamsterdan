"""Lookup-first, fenced GitHub PR comment effects."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast
from urllib.parse import quote

from .gateway import GitHubAuthority
from .models import (
    ActionsRunSnapshot,
    CommentReference,
    GitHubBoundaryError,
    PublicationResult,
    Transport,
    WireResponse,
)

Fence = Callable[[str, int, int, str, str], None]
EffectFault = Callable[[str, str, int, str, str], None]
_MARKER_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_HEAD = re.compile(r"[0-9a-f]{40}")
_MARKER_KINDS = frozenset({"conversation", "finding", "readiness", "reminder"})
_INLINE_UNAVAILABLE_MESSAGES = frozenset(
    {"line is not in diff", "pull request review thread line must be part of the diff"}
)


class CommentPublisher:
    """Lookup-first comments with an immediate pre-effect stale fence."""

    def __init__(
        self,
        transport: Transport,
        repository: str,
        pr_number: int,
        bot_login: str,
        fence: Fence,
        fault: EffectFault | None = None,
    ):
        normalized_login = bot_login.strip().casefold()
        if not normalized_login or not normalized_login.endswith("[bot]"):
            raise ValueError("bot login must be the configured GitHub App bot login")
        self.transport, self.repository, self.pr_number, self.bot_login, self.fence, self.fault = (
            transport,
            repository,
            pr_number,
            normalized_login,
            fence,
            fault,
        )
        self.root = f"/repos/{repository}/issues/{pr_number}/comments"
        self.edit_root = f"/repos/{repository}/issues/comments"
        self.review_root = f"/repos/{repository}/pulls/{pr_number}/comments"

    @staticmethod
    def marker(kind: str, operation: str, head: str) -> str:
        if kind not in _MARKER_KINDS or not _MARKER_OPERATION.fullmatch(operation) or not _HEAD.fullmatch(head):
            raise ValueError("publication marker identity is malformed")
        return f"<!-- hamsterdan:{kind} operation={operation} head={head} -->"

    def _comments(self) -> tuple[dict[str, Any], ...]:
        return self.transport.pages(f"{self.root}?per_page=100")

    def _find(self, marker: str) -> Mapping[str, Any] | None:
        return next(
            (
                item
                for item in self._comments()
                if _login(item) == self.bot_login and _final_marker(str(item.get("body", "")), marker)
            ),
            None,
        )

    def _review_comments(self) -> tuple[dict[str, Any], ...]:
        return self.transport.pages(f"{self.review_root}?per_page=100")

    def _find_review(self, marker: str) -> Mapping[str, Any] | None:
        return next(
            (
                item
                for item in self._review_comments()
                if _login(item) == self.bot_login and _final_marker(str(item.get("body", "")), marker)
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
        compatible_bodies: tuple[str, ...] = (),
    ) -> PublicationResult:
        marker = self.marker(kind, operation, head)
        payload = f"{body}\n\n{marker}"
        compatible_payloads = {f"{value}\n\n{marker}" for value in compatible_bodies}
        existing = self._find(marker)
        if existing:
            if existing.get("body") != payload and existing.get("body") not in compatible_payloads:
                raise ValueError("stable publication operation collided with a different payload")
            return PublicationResult("existing", _reference(existing))
        for attempt in range(2):
            self.fence(self.repository, self.pr_number, epoch, head, authority_operation or operation)
            try:
                if self.fault is not None:
                    self.fault("before_call", self.repository, self.pr_number, kind, operation)
                response = self.transport.request("POST", self.root, {"body": payload})
                if self.fault is not None:
                    self.fault("after_call", self.repository, self.pr_number, kind, operation)
            except GitHubBoundaryError:
                recovered = self._recover(marker, payload)
                if recovered is not None:
                    return recovered
                if attempt:
                    raise
                continue
            if response.status == 201:
                try:
                    return PublicationResult("created", _reference(_response_mapping(response.body)))
                except KeyError, TypeError, ValueError, OverflowError:
                    pass
            recovered = self._recover(marker, payload)
            if recovered is not None:
                return recovered
            if response.status == 201:
                raise GitHubBoundaryError("GitHub did not prove comment publication")
            outcome = _comment_rejection(response.status, "comment publication")
            if outcome is not None:
                return outcome
            if attempt:
                raise GitHubBoundaryError("GitHub did not prove comment publication")
        raise AssertionError("bounded comment recovery exhausted without an outcome")

    def _recover(self, marker: str, payload: str) -> PublicationResult | None:
        existing = self._find(marker)
        if existing is None:
            return None
        if existing.get("body") != payload:
            raise ValueError("stable publication operation collided with a different payload")
        return PublicationResult("existing", _reference(existing))

    def _find_operation(self, kind: str, operation: str) -> tuple[Mapping[str, Any], str] | None:
        """Find the bot's final marker for (kind, operation) under ANY head."""
        pattern = re.compile(
            rf"<!-- hamsterdan:{re.escape(kind)} operation={re.escape(operation)} head=([0-9a-f]{{40}}) -->"
        )
        for item in self._comments():
            if _login(item) != self.bot_login:
                continue
            body = str(item.get("body", ""))
            tail = body.rsplit("\n\n", 1)[-1]
            matched = pattern.fullmatch(tail)
            if matched:
                return item, matched.group(1)
        return None

    def immutable_operation(
        self,
        kind: str,
        operation: str,
        body: str,
        *,
        context: Callable[[], tuple[int, str]],
        compatible_bodies: tuple[str, ...] = (),
    ) -> PublicationResult:
        """Immutable publication whose A2 identity is (kind, operation)
        across heads: authority-orthogonal comments (replies) must
        reconcile a comment landed under an EARLIER head instead of
        reposting, because the marker embeds the head. Reconciliation
        happens BEFORE ``context`` is consulted, so a held effect
        reconciles even when the current epoch/head cannot be read.
        Content collision under the held identity still fails closed."""
        found = self._find_operation(kind, operation)
        if found is not None:
            item, held_head = found
            marker = self.marker(kind, operation, held_head)
            payload = f"{body}\n\n{marker}"
            compatible_payloads = {f"{value}\n\n{marker}" for value in compatible_bodies}
            if item.get("body") != payload and item.get("body") not in compatible_payloads:
                raise ValueError("stable publication operation collided with a different payload")
            return PublicationResult("existing", _reference(item))
        epoch, head = context()
        return self.immutable(kind, operation, epoch, head, body, compatible_bodies=compatible_bodies)

    def reminder_operation(
        self, operation: str, *, context: Callable[[], tuple[int, str, str | None, str]]
    ) -> PublicationResult:
        """Operation-scoped reminder (A2): presence of the (reminder,
        operation) marker under ANY head proves the nudge landed —
        reconciliation is presence-only (the harness spec) because the
        body legitimately drifts with addressing and the dashboard
        link, and the identity has a single writer. ``context`` — the
        current (epoch, head, reviewer, author) — is consulted only
        when a new write is needed."""
        found = self._find_operation("reminder", operation)
        if found is not None:
            item, _held_head = found
            return PublicationResult("existing", _reference(item))
        epoch, head, reviewer, author = context()
        return self.reminder(operation, epoch, head, reviewer=reviewer, author=author)

    def find(
        self,
        kind: str,
        operation: str,
        head: str,
        body: str,
        *,
        compatible_bodies: tuple[str, ...] = (),
    ) -> PublicationResult | None:
        """Lookup-first reconciliation WITHOUT an effect: None when the
        operation was never held, the existing result when it landed with
        the same (or a compatible) payload, and the collision invariant
        when the identity is held with different content."""
        marker = self.marker(kind, operation, head)
        payload = f"{body}\n\n{marker}"
        compatible_payloads = {f"{value}\n\n{marker}" for value in compatible_bodies}
        existing = self._find(marker)
        if existing is None:
            return None
        if existing.get("body") != payload and existing.get("body") not in compatible_payloads:
            raise ValueError("stable publication operation collided with a different payload")
        return PublicationResult("existing", _reference(existing))

    def dashboard(self, operation: str, epoch: int, head: str, body: str) -> PublicationResult:
        marker = "<!-- hamsterdan:dashboard -->"
        existing = self._find(marker)
        payload = f"{body}\n\n{marker}"
        if existing is None:
            self.fence(self.repository, self.pr_number, epoch, head, operation)
            try:
                response = self.transport.request("POST", self.root, {"body": payload})
            except GitHubBoundaryError:
                recovered = self._recover(marker, payload)
                if recovered is not None:
                    return recovered
                raise
            if response.status == 201:
                try:
                    return PublicationResult("created", _reference(_response_mapping(response.body)))
                except KeyError, TypeError, ValueError, OverflowError:
                    pass
            else:
                recovered = self._recover(marker, payload)
                if recovered is not None:
                    return recovered
                outcome = _comment_rejection(response.status, "dashboard publication")
                if outcome is not None:
                    return outcome
            recovered = self._recover(marker, payload)
            if recovered is not None:
                return recovered
            raise GitHubBoundaryError("GitHub did not prove dashboard publication")
        if existing.get("body") == payload:
            return PublicationResult("existing", _reference(existing))
        self.fence(self.repository, self.pr_number, epoch, head, operation)
        try:
            response = self.transport.request("PATCH", f"{self.edit_root}/{existing['id']}", {"body": payload})
        except GitHubBoundaryError:
            recovered = self._recover_dashboard(marker, payload)
            if recovered is not None:
                return recovered
            raise
        if response.status == 200:
            try:
                return PublicationResult("updated", _reference(_response_mapping(response.body)))
            except KeyError, TypeError, ValueError, OverflowError:
                pass
        else:
            recovered = self._recover_dashboard(marker, payload)
            if recovered is not None:
                return recovered
            outcome = _comment_rejection(response.status, "dashboard update", reference=_reference(existing))
            if outcome is not None:
                return outcome
        recovered = self._recover_dashboard(marker, payload)
        if recovered is not None:
            return recovered
        raise GitHubBoundaryError("GitHub did not prove dashboard update")

    def _recover_dashboard(self, marker: str, payload: str) -> PublicationResult | None:
        existing = self._find(marker)
        if existing is None or existing.get("body") != payload:
            return None
        return PublicationResult("existing", _reference(existing))

    def finding(
        self,
        operation: str,
        epoch: int,
        head: str,
        text: str,
        *,
        path: str = "",
        line: int = 0,
        related_locations: tuple[tuple[str, int], ...] = (),
        suggestion: str = "",
        link: str = "",
        authority_operation: str | None = None,
    ) -> PublicationResult:
        marker = self.marker("finding", operation, head)
        location = f"`{path}:{line}`" if path and line > 0 else ""
        related = (
            "Related locations:\n"
            + "\n".join(
                f"- [`{related_path}:{related_line}`]"
                f"(https://github.com/{self.repository}/blob/{head}/{quote(related_path, safe='/')}#L{related_line})"
                for related_path, related_line in related_locations
            )
            if related_locations
            else ""
        )
        suggestion_block = f"```suggestion\n{suggestion}\n```" if suggestion else ""
        detail = "\n\n".join(
            item
            for item in (
                text,
                f"Primary location: {location}" if location else "",
                related,
                suggestion_block,
                f"Link: {link}" if link else "",
            )
            if item
        )
        payload = f"{detail}\n\n{marker}"
        legacy_detail = "\n".join(
            item
            for item in (text, f"Location: {path}:{line}" if location else "", f"Link: {link}" if link else "")
            if item
        )
        legacy_payload = f"{legacy_detail}\n\n{marker}"
        existing_review = self._find_review(marker) if location else None
        if existing_review is not None:
            if existing_review.get("body") != payload:
                raise ValueError("stable publication operation collided with a different payload")
            return PublicationResult("existing", _reference(existing_review), inline=True)
        existing_issue = self._find(marker)
        if existing_issue is not None:
            compatible_legacy = (
                not suggestion and not related_locations and existing_issue.get("body") == legacy_payload
            )
            if existing_issue.get("body") != payload and not compatible_legacy:
                raise ValueError("stable publication operation collided with a different payload")
            return PublicationResult("existing", _reference(existing_issue), inline=False)
        if location:
            result = self._inline_finding(
                operation,
                epoch,
                head,
                detail,
                path,
                line,
                authority_operation=authority_operation,
            )
            if result.capability_available:
                return result
        result = self.immutable("finding", operation, epoch, head, detail, authority_operation=authority_operation)
        return PublicationResult(result.status, result.reference, result.capability_available, inline=False)

    def _inline_finding(
        self,
        operation: str,
        epoch: int,
        head: str,
        body: str,
        path: str,
        line: int,
        *,
        authority_operation: str | None,
    ) -> PublicationResult:
        marker = self.marker("finding", operation, head)
        payload = f"{body}\n\n{marker}"
        for attempt in range(2):
            self.fence(self.repository, self.pr_number, epoch, head, authority_operation or operation)
            try:
                if self.fault is not None:
                    self.fault("before_call", self.repository, self.pr_number, "finding", operation)
                response = self.transport.request(
                    "POST",
                    self.review_root,
                    {"body": payload, "commit_id": head, "path": path, "line": line, "side": "RIGHT"},
                )
                if self.fault is not None:
                    self.fault("after_call", self.repository, self.pr_number, "finding", operation)
            except GitHubBoundaryError:
                recovered = self._find_review(marker)
                if recovered is not None:
                    if recovered.get("body") != payload:
                        raise ValueError("stable publication operation collided with a different payload")
                    return PublicationResult("existing", _reference(recovered), inline=True)
                if attempt:
                    raise
                continue
            if response.status == 201 and isinstance(response.body, dict):
                return PublicationResult("created", _reference(_response_mapping(response.body)), inline=True)
            recovered = self._find_review(marker)
            if recovered is not None:
                if recovered.get("body") != payload:
                    raise ValueError("stable publication operation collided with a different payload")
                return PublicationResult("existing", _reference(recovered), inline=True)
            if _inline_unavailable(response):
                return PublicationResult("inline_unavailable", capability_available=False)
            raise GitHubBoundaryError("GitHub did not prove inline finding publication")
        raise AssertionError("bounded inline finding recovery exhausted without an outcome")

    def reminder(
        self, operation: str, epoch: int, head: str, *, reviewer: str | None, author: str, maintainer: str | None = None
    ) -> PublicationResult:
        target = reviewer or maintainer or author
        action = "Please review this PR" if reviewer else "Please assign a reviewer for this PR"
        dashboard = self._find("<!-- hamsterdan:dashboard -->")
        state = str(dashboard.get("html_url", "")) if dashboard is not None else ""
        link = f" [See current readiness state.]({state})" if state else ""
        legacy = f"@{target.lstrip('@')}, {'please review this PR' if reviewer else 'please assign a reviewer for this PR'}.{link}"
        return self.immutable(
            "reminder",
            operation,
            epoch,
            head,
            f"@{target.lstrip('@')}, this PR and I have gotten to know each other quite well. {action}.{link}",
            compatible_bodies=(legacy,),
        )

    @property
    def reviewer_assignment_available(self) -> bool:
        return False


def _comment_rejection(
    status: int, operation: str, *, reference: CommentReference | None = None
) -> PublicationResult | None:
    """Classify a proven HTTP outcome without retaining provider diagnostics."""
    if status in {403, 404}:
        return PublicationResult("capability_unavailable", reference, False)
    if status == 429 or status >= 500:
        raise GitHubBoundaryError(f"GitHub did not prove {operation}")
    raise ValueError(f"GitHub rejected {operation}")


def _reference(value: Mapping[str, Any]) -> CommentReference:
    return CommentReference(int(value["id"]), str(value.get("html_url", "")))


def _response_mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value)


def _inline_unavailable(response: WireResponse) -> bool:
    if response.status != 422 or not isinstance(response.body, Mapping):
        return False
    message = response.body.get("message")
    return isinstance(message, str) and message.strip().casefold() in _INLINE_UNAVAILABLE_MESSAGES


def _final_marker(body: str, marker: str) -> bool:
    return body == marker or body.endswith(f"\n\n{marker}")


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
