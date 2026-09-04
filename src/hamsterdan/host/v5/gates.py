"""Provider-backed publication gates for the V5 topology (CV17.DS2.1).

Each gate executes ONE comment publication against the real
``CommentPublisher`` surface and classifies its own outcome into the
exact typed terminals the V5 topology routes by color. The fake-world
harness (tests/unit/readiness/net_v5/harness.py) is the semantic spec:

1. lookup-first reconciliation (A2) happens BEFORE any fence or
   failure mode — a crash after the provider held the effect must
   reconcile landed, never refuse or repost;
2. fenced gates (announce, findings publish) compare EVERY claimed
   authority field (A1.5): the live provider fields (head, base,
   policy) AND the host grant (phase, incarnation), via the claim
   port; reply, reminder, and dashboard carry no fence by design;
3. the effect classifies fail-closed: ``GitHubBoundaryError``
   (bounded provider retries exhausted) is the gate's Blocked
   terminal; a definitive capability denial (the provider PROVED it
   cannot publish, e.g. 403/404) is also Blocked — the exact request
   is retained and may heal; any other classified provider outcome —
   identity collision (``ValueError``), an unclassifiable provider
   terminal (``RuntimeError``), or an unrecognized returned status —
   is the gate's Fault terminal;
4. reply and reminder identities are OPERATION-scoped (A2): the real
   marker embeds the head, so their reconciliation searches (kind,
   operation) across heads — a recovery reissue after a head move
   must find the landed comment, never post a duplicate.

Classified outcomes never raise into Motus: they return as typed
terminals the loop folds, so the durable History carries the
classification. Only a genuinely unclassified exception (a bug)
propagates as an activity failure.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from hamsterdan.contracts.readiness_v5 import (
    ABlocked,
    ADeferred,
    AFault,
    ALanded,
    AMoved,
    AnnounceReq,
    DashBlocked,
    DashDeferred,
    DashFault,
    DashLanded,
    DashReq,
    Publishable,
    RemBlocked,
    RemFault,
    RemLanded,
    RemReq,
    Replied,
    ReplyBlocked,
    ReplyFault,
    ReplyReq,
    ReviewBlocked,
    ReviewFault,
    ReviewLanded,
    ReviewMoved,
)
from hamsterdan.github_app.models import FindingPublication, GitHubBoundaryError, PublicationResult
from hamsterdan.host.v5.claim import ClaimReader, CurrentClaim
from hamsterdan.readiness.net_v5.board import render_board

Recipients = Callable[[], tuple[str | None, str]]
"""A zero-argument port yielding the current (reviewer, author)."""
DashboardPhase = Callable[[], str]
"""A host-grant-only port yielding the staged lifecycle phase."""


class UnstagedCustodyError(GitHubBoundaryError):
    """One exact same-PR custody row has not entered canonical History."""

    def __init__(self, blocker: str) -> None:
        self.blocker = blocker
        super().__init__("custodied authority is not staged in the V5 host grant")


_ANNOUNCE_BODY = (
    "## Hamsterdan readiness advisory\n\n"
    "All observed gates are ready. Clean. Humans keep merge authority; Dan never merges PRs."
)
_ANNOUNCE_COMPATIBLE = (
    "## Hamsterdan readiness advisory\n\nAll observed gates are ready. Advisory only; Hamsterdan does not merge PRs.",
)


class PublicationProvider(Protocol):
    """The CommentPublisher surface the gates bind to (duck-typed in tests)."""

    def find(
        self, kind: str, operation: str, head: str, body: str, *, compatible_bodies: tuple[str, ...] = ()
    ) -> PublicationResult | None: ...

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
    ) -> PublicationResult: ...

    def immutable_operation(
        self,
        kind: str,
        operation: str,
        body: str,
        *,
        context: Callable[[], tuple[int, str]],
        compatible_bodies: tuple[str, ...] = (),
    ) -> PublicationResult: ...

    def dashboard(self, operation: str, epoch: int, head: str, body: str) -> PublicationResult: ...

    def reminder_operation(
        self, operation: str, *, context: Callable[[], tuple[int, str, str | None, str]]
    ) -> PublicationResult: ...

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
    ) -> PublicationResult: ...

    def findings(
        self,
        epoch: int,
        head: str,
        findings: tuple[FindingPublication, ...],
        *,
        authority_operation: str,
    ) -> tuple[PublicationResult, ...]: ...

    def finding_find(self, operation: str, head: str) -> PublicationResult | None: ...


_HELD = frozenset({"created", "existing"})
_DASH_HELD = frozenset({"created", "existing", "updated"})


_FINDING_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def _finding_operation(op: str, finding: Mapping[str, Any]) -> str:
    """The per-finding publication identity: the round operation plus the
    finding's own id. An id the marker grammar cannot carry degrades to
    its digest instead of faulting the whole round."""
    identifier = str(finding.get("id", ""))
    candidate = f"{op}:{identifier}"
    if _FINDING_OPERATION.fullmatch(candidate) is None:
        candidate = f"{op}:{hashlib.sha256(identifier.encode()).hexdigest()[:16]}"
    return candidate


def _finding_arguments(finding: Mapping[str, Any]) -> dict[str, Any]:
    related = tuple(
        (str(item.get("path")), int(item.get("line")))
        for item in finding.get("related_locations", [])
        if isinstance(item, dict) and item.get("path") and item.get("line")
    )
    return {
        "path": str(finding.get("path") or ""),
        "line": int(finding.get("line") or 0),
        "related_locations": related,
        "suggestion": str(finding.get("suggestion") or ""),
    }


def _reason(error: Exception) -> str:
    return str(error) or repr(error)


def _unproven(result: PublicationResult, held: frozenset[str] = _HELD) -> str | None:
    """None when the effect is proven held; "blocked" for a definitive
    capability denial (request retained, may heal); otherwise the
    fail-closed fault reason for an unrecognized returned status."""
    if not result.capability_available:
        return "blocked"
    if result.status in held:
        return None
    return f"unclassified publication status {result.status!r}"


@dataclass(frozen=True)
class V5PublicationGates:
    """The five comment-publication gates, backed by one provider.

    ``claim`` returns a fresh, complete ``CurrentClaim`` per call —
    live provider fields plus the host grant, host-applied BEFORE the
    net observes displacing facts. ``recipients`` yields the reminder
    addressing (reviewer, author) at effect time.
    """

    publisher: PublicationProvider
    claim: ClaimReader
    recipients: Recipients
    dashboard_phase: DashboardPhase = lambda: "running"
    # ruled 2026-09-02: a fresh finding publication or readiness
    # announcement also retires the App's own finding threads from
    # superseded heads; held reconciles stay effect-free
    resolve_stale_threads: Callable[[str], int] | None = None

    # -- reply: unfenced, immutable, identity `reply:{id}` -------------

    def reply_gate(self, work: ReplyReq) -> Replied | ReplyBlocked | ReplyFault:
        def context() -> tuple[int, str]:
            current = self.claim()
            return current.incarnation, current.head

        try:
            # lazy write context: a held reply reconciles BEFORE any
            # claim read, so it lands even when the claim is unreadable
            result = self.publisher.immutable_operation("conversation", f"reply:{work.id}", work.text, context=context)
        except GitHubBoundaryError:
            return ReplyBlocked(id=work.id, text=work.text)
        except (RuntimeError, ValueError) as error:
            return ReplyFault(id=work.id, text=work.text, reason=_reason(error))
        unproven = _unproven(result)
        if unproven == "blocked":
            return ReplyBlocked(id=work.id, text=work.text)
        if unproven is not None:
            return ReplyFault(id=work.id, text=work.text, reason=unproven)
        return Replied(id=work.id, text=work.text)

    # -- reminder: unfenced, immutable, identity `reminder:{timer_id}` -

    def reminder_gate(self, work: RemReq) -> RemLanded | RemBlocked | RemFault:
        def context() -> tuple[int, str, str | None, str]:
            current = self.claim()
            reviewer, author = self.recipients()
            return current.incarnation, current.head, reviewer, author

        try:
            # lazy write context: a held nudge reconciles BEFORE any
            # claim or recipient read (presence-only, the harness spec)
            result = self.publisher.reminder_operation(f"reminder:{work.timer_id}", context=context)
        except GitHubBoundaryError:
            return RemBlocked(timer_id=work.timer_id)
        except (RuntimeError, ValueError) as error:
            return RemFault(timer_id=work.timer_id, reason=_reason(error))
        unproven = _unproven(result)
        if unproven == "blocked":
            return RemBlocked(timer_id=work.timer_id)
        if unproven is not None:
            return RemFault(timer_id=work.timer_id, reason=unproven)
        return RemLanded(timer_id=work.timer_id)

    # -- announce: FULL claim fence, immutable, identity in work.op ----

    def announce_gate(self, work: AnnounceReq) -> ALanded | ADeferred | AMoved | ABlocked | AFault:
        expected = CurrentClaim(
            phase="running", incarnation=work.incarnation, head=work.head, base=work.base, policy=work.policy
        )
        try:
            held = self.publisher.find(
                "readiness", work.op, work.head, _ANNOUNCE_BODY, compatible_bodies=_ANNOUNCE_COMPATIBLE
            )
            if held is not None:
                return ALanded(incarnation=work.incarnation, head=work.head)
            current = self.claim()
            if (work.strict_base and not work.base_current) or current != expected:
                return AMoved(
                    incarnation=work.incarnation,
                    observed_head=current.head,
                    observed_base=current.base,
                    observed_policy=current.policy,
                    observed_incarnation=current.incarnation,
                    observed_phase=current.phase,
                )
            result = self.publisher.immutable(
                "readiness",
                work.op,
                work.incarnation,
                work.head,
                _ANNOUNCE_BODY,
                compatible_bodies=_ANNOUNCE_COMPATIBLE,
            )
            if self.resolve_stale_threads is not None:
                self.resolve_stale_threads(work.head)
        except UnstagedCustodyError as error:
            return ADeferred(
                op=work.op,
                incarnation=work.incarnation,
                head=work.head,
                base=work.base,
                policy=work.policy,
                strict_base=work.strict_base,
                base_current=work.base_current,
                blocker=error.blocker,
            )
        except GitHubBoundaryError:
            return ABlocked(incarnation=work.incarnation, head=work.head, base=work.base, policy=work.policy)
        except (RuntimeError, ValueError) as error:
            return AFault(op=work.op, incarnation=work.incarnation, reason=_reason(error))
        unproven = _unproven(result)
        if unproven == "blocked":
            return ABlocked(incarnation=work.incarnation, head=work.head, base=work.base, policy=work.policy)
        if unproven is not None:
            return AFault(op=work.op, incarnation=work.incarnation, reason=unproven)
        return ALanded(incarnation=work.incarnation, head=work.head)

    # -- findings publish: FULL claim fence, one identity per finding --

    def publish_gate(self, work: Publishable) -> ReviewLanded | ReviewMoved | ReviewBlocked | ReviewFault:
        expected = CurrentClaim(
            phase="running", incarnation=work.incarnation, head=work.head, base=work.base, policy=work.policy
        )
        landed = ReviewLanded(
            head=work.head, incarnation=work.incarnation, findings=work.findings, effect=work.effect, mem=work.mem
        )

        def blocked(error: GitHubBoundaryError | None = None) -> ReviewBlocked:
            return ReviewBlocked(
                head=work.head,
                base=work.base,
                policy=work.policy,
                incarnation=work.incarnation,
                findings=work.findings,
                effect=work.effect,
                op=work.op,
                failure_class=error.failure_class if error is not None else "capability_denial",
                provider_status=error.provider_status if error is not None else None,
                provider_detail=error.provider_detail if error is not None else "none",
                mem=work.mem,
            )

        try:
            pending = [
                finding
                for finding in work.findings
                if self.publisher.finding_find(_finding_operation(work.op, finding), work.head) is None
            ]
            if pending:
                current = self.claim()
                if current != expected:
                    return ReviewMoved(
                        head=work.head,
                        observed=current.head,
                        observed_base=current.base,
                        observed_policy=current.policy,
                        observed_incarnation=current.incarnation,
                        observed_phase=current.phase,
                        findings=work.findings,
                        mem=work.mem,
                    )
                anchored = tuple(
                    FindingPublication(
                        operation=_finding_operation(work.op, finding),
                        text=str(finding.get("body", "")),
                        **_finding_arguments(finding),
                    )
                    for finding in pending
                    if finding.get("path") and finding.get("line")
                )
                for result in (
                    self.publisher.findings(
                        work.incarnation,
                        work.head,
                        anchored,
                        authority_operation=work.op,
                    )
                    if anchored
                    else ()
                ):
                    unproven = _unproven(result)
                    if unproven == "blocked":
                        return blocked()
                    if unproven is not None:
                        return ReviewFault(reason=unproven, mem=work.mem)
                for finding in pending:
                    if finding.get("path") and finding.get("line"):
                        continue
                    result = self.publisher.finding(
                        _finding_operation(work.op, finding),
                        work.incarnation,
                        work.head,
                        str(finding.get("body", "")),
                        authority_operation=work.op,
                        **_finding_arguments(finding),
                    )
                    unproven = _unproven(result)
                    if unproven == "blocked":
                        return blocked()
                    if unproven is not None:
                        return ReviewFault(reason=unproven, mem=work.mem)
                if self.resolve_stale_threads is not None:
                    self.resolve_stale_threads(work.head)
        except GitHubBoundaryError as error:
            return blocked(error)
        except (RuntimeError, ValueError) as error:
            return ReviewFault(reason=_reason(error), mem=work.mem)
        return landed

    # -- dashboard: unfenced idempotent upsert, digest identity --------

    def dash_gate(self, work: DashReq) -> DashLanded | DashDeferred | DashBlocked | DashFault:
        if self.dashboard_phase() == "quiescent":
            return DashDeferred(
                entries=work.entries,
                digest=work.digest,
                desired_entries=work.desired_entries,
                desired_digest=work.desired_digest,
                landed=work.landed,
                blocked=work.blocked,
                faulted=work.faulted,
            )
        try:
            # CommentPublisher retains an epoch/head-shaped signature,
            # but `dash:` operations explicitly bypass its authority
            # fence and the singleton marker embeds neither value. The
            # staged phase check above suppresses user-visible draft work
            # without reading mutable provider authority. Do not turn this
            # authority-orthogonal projection into a full claim read:
            # after our own push, provider head legitimately moves before
            # the next webhook stages that head in the host grant.
            result = self.publisher.dashboard(f"dash:{work.digest}", 0, "0" * 40, render_board(work.entries))
        except GitHubBoundaryError:
            return DashBlocked(
                entries=work.entries,
                digest=work.digest,
                desired_entries=work.desired_entries,
                desired_digest=work.desired_digest,
            )
        except (RuntimeError, ValueError) as error:
            return DashFault(
                entries=work.entries,
                digest=work.digest,
                desired_entries=work.desired_entries,
                desired_digest=work.desired_digest,
                reason=_reason(error),
            )
        unproven = _unproven(result, _DASH_HELD)
        if unproven == "blocked":
            return DashBlocked(
                entries=work.entries,
                digest=work.digest,
                desired_entries=work.desired_entries,
                desired_digest=work.desired_digest,
            )
        if unproven is not None:
            return DashFault(
                entries=work.entries,
                digest=work.digest,
                desired_entries=work.desired_entries,
                desired_digest=work.desired_digest,
                reason=unproven,
            )
        return DashLanded(
            entries=work.entries,
            digest=work.digest,
            desired_entries=work.desired_entries,
            desired_digest=work.desired_digest,
        )
