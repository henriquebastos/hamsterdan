"""Executable contracts for the provider-backed V5 publication gates.

CV17.DS2.1a: the five CommentPublisher-backed gates (reply, reminder,
announce, dashboard, findings publish) against duck-typed provider
fakes, per host test conventions. Each gate classifies its own outcome
into the exact typed terminals the V5 topology routes by color; the
fake-world harness in tests/unit/readiness/net_v5 is the semantic spec
these implementations must match:

- lookup-first reconciliation happens BEFORE any fence or failure mode
  (a crash after the provider held the effect reconciles landed);
- an effect-identity collision with DIFFERENT content fails closed;
- GitHubBoundaryError (retryable exhaustion) classifies Blocked;
- any unknown provider terminal classifies Fault;
- fenced gates (announce, findings) compare EVERY claimed authority
  field — the live provider fields AND the host grant — via the claim
  port; reply, reminder, and dashboard carry no fence by design.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

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
    PublicationDeferred,
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
from hamsterdan.github_app.effects import CommentPublisher
from hamsterdan.github_app.models import CommentReference, GitHubBoundaryError, PublicationResult
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.gates import UnstagedCustodyError, V5PublicationGates

CLAIM = CurrentClaim(phase="running", incarnation=1, head="h1", base="b1", policy="p1")
REFERENCE = CommentReference(1, "https://example.test/c/1")


class FakePublisher:
    """Duck-typed CommentPublisher: records calls, classifies by mode.

    mode: None (created) | "existing" | "boundary" | "collision" |
    "unknown" (raised RuntimeError) | "capability" (definitive denial,
    returned not raised) | "unclassified" (unrecognized returned
    status). `found` simulates a prior held effect for `find`.
    """

    def __init__(self, mode: str | None = None, found: bool = False, collide: bool = False):
        self.mode, self.found, self.collide = mode, found, collide
        self.calls: list[tuple] = []
        self.compatible_calls: list[tuple[str, tuple[str, ...]]] = []

    def find(self, kind, operation, head, body, *, compatible_bodies=()):
        self.calls.append(("find", kind, operation, head, body))
        self.compatible_calls.append(("find", compatible_bodies))
        if self.collide:
            raise ValueError("stable publication operation collided with a different payload")
        if self.found:
            return PublicationResult("existing", REFERENCE)
        return None

    def _outcome(self):
        if self.mode == "existing":
            return PublicationResult("existing", REFERENCE)
        if self.mode == "boundary":
            raise GitHubBoundaryError("GitHub did not prove comment publication")
        if self.mode == "collision":
            raise ValueError("stable publication operation collided with a different payload")
        if self.mode == "unknown":
            raise RuntimeError("provider returned an unclassifiable terminal")
        if self.mode == "capability":
            return PublicationResult("capability_unavailable", None, False)
        if self.mode == "unclassified":
            return PublicationResult("banana", REFERENCE)
        return PublicationResult("created", REFERENCE)

    def immutable(self, kind, operation, epoch, head, body, *, authority_operation=None, compatible_bodies=()):
        self.calls.append(("immutable", kind, operation, head, body))
        self.compatible_calls.append(("immutable", compatible_bodies))
        return self._outcome()

    def immutable_operation(self, kind, operation, body, *, context, compatible_bodies=()):
        # operation-scoped reconciliation happens BEFORE the write
        # context is consulted: a held effect never reads the claim
        if self.found:
            self.calls.append(("immutable_operation", kind, operation, None, body))
            return PublicationResult("existing", REFERENCE)
        _epoch, head = context()
        self.calls.append(("immutable_operation", kind, operation, head, body))
        return self._outcome()

    def dashboard(self, operation, epoch, head, body):
        self.calls.append(("dashboard", operation, head, body))
        return self._outcome()

    def finding_find(self, operation, head):
        self.calls.append(("finding_find", operation, head))
        if self.found:
            return PublicationResult("existing", REFERENCE, inline=True)
        return None

    def finding(
        self,
        operation,
        epoch,
        head,
        text,
        *,
        path="",
        line=0,
        related_locations=(),
        suggestion="",
        link="",
        authority_operation=None,
    ):
        self.calls.append(
            ("finding", operation, head, text, path, line, related_locations, suggestion, authority_operation)
        )
        return self._outcome()

    def findings(self, epoch, head, findings, *, authority_operation):
        self.calls.append(("findings", head, findings, authority_operation))
        return tuple(self._outcome() for _finding in findings)

    def reminder_operation(self, operation, *, context):
        # presence-only reconciliation BEFORE claim/recipient reads
        if self.found:
            self.calls.append(("reminder_operation", operation, None, None))
            return PublicationResult("existing", REFERENCE)
        _epoch, _head, reviewer, author = context()
        self.calls.append(("reminder_operation", operation, reviewer, author))
        return self._outcome()


def gates(publisher: FakePublisher, claim: CurrentClaim = CLAIM) -> V5PublicationGates:
    return V5PublicationGates(
        publisher=publisher,
        claim=lambda: claim,
        recipients=lambda: ("the-reviewer", "the-author"),
        dashboard_phase=lambda: claim.phase,
    )


def _unreadable() -> CurrentClaim:
    raise GitHubBoundaryError("claim unreadable")


def gates_without_context(publisher: FakePublisher) -> V5PublicationGates:
    """Gates whose claim AND recipients ports fail: only an effect that
    reconciles BEFORE reading write context can land through these."""

    def no_recipients() -> tuple[str | None, str]:
        raise GitHubBoundaryError("recipients unreadable")

    return V5PublicationGates(publisher=publisher, claim=_unreadable, recipients=no_recipients)


def moved(**changes) -> CurrentClaim:
    values = {
        "phase": CLAIM.phase,
        "incarnation": CLAIM.incarnation,
        "head": CLAIM.head,
        "base": CLAIM.base,
        "policy": CLAIM.policy,
        **changes,
    }
    return CurrentClaim(**values)


class TestReplyGate:
    """Replies carry NO authority fence by design — a human may talk to
    a drafted or closed PR, and the answer still lands."""

    WORK = ReplyReq(id="c1", text="the answer")

    def test_a_reply_lands_under_its_operation_scoped_identity(self) -> None:
        publisher = FakePublisher()
        assert gates(publisher).reply_gate(self.WORK) == Replied(id="c1", text="the answer")
        # operation-scoped publication (A2): the real marker embeds the
        # head, so reply reconciliation must search (kind, operation)
        # across heads — never repost after a head move. "conversation"
        # is the real publisher's marker kind for replies.
        [(_, kind, operation, _, body)] = [c for c in publisher.calls if c[0] == "immutable_operation"]
        assert (kind, operation) == ("conversation", "reply:c1")
        assert "the answer" in body

    def test_an_already_held_reply_reconciles_landed(self) -> None:
        publisher = FakePublisher(mode="existing")
        assert gates(publisher).reply_gate(self.WORK) == Replied(id="c1", text="the answer")

    def test_a_held_reply_reconciles_even_when_the_claim_is_unreadable(self) -> None:
        # A2 ordering: operation lookup precedes ANY write-context read,
        # so a landed reply reconciles when claim() itself fails
        publisher = FakePublisher(found=True)
        assert gates_without_context(publisher).reply_gate(self.WORK) == Replied(id="c1", text="the answer")

    def test_retryable_exhaustion_classifies_blocked_with_the_text_retained(self) -> None:
        publisher = FakePublisher(mode="boundary")
        assert gates(publisher).reply_gate(self.WORK) == ReplyBlocked(id="c1", text="the answer")

    def test_an_identity_collision_fails_closed(self) -> None:
        publisher = FakePublisher(mode="collision")
        result = gates(publisher).reply_gate(self.WORK)
        assert isinstance(result, ReplyFault) and result.id == "c1" and result.text == "the answer"

    def test_an_unknown_terminal_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unknown")
        result = gates(publisher).reply_gate(self.WORK)
        assert isinstance(result, ReplyFault) and result.reason

    def test_a_proven_capability_denial_classifies_blocked_not_landed(self) -> None:
        publisher = FakePublisher(mode="capability")
        assert gates(publisher).reply_gate(self.WORK) == ReplyBlocked(id="c1", text="the answer")

    def test_an_unrecognized_returned_status_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unclassified")
        result = gates(publisher).reply_gate(self.WORK)
        assert isinstance(result, ReplyFault) and "banana" in result.reason


class TestReminderGate:
    """Reminders carry NO authority fence by design — a nudge is a
    human-facing note, corrected by conversation, never fenced."""

    WORK = RemReq(timer_id="t1")

    def test_a_nudge_lands_under_its_operation_scoped_timer_identity(self) -> None:
        publisher = FakePublisher()
        assert gates(publisher).reminder_gate(self.WORK) == RemLanded(timer_id="t1")
        # A2: reminder reconciliation is (kind, operation) across heads —
        # a recovery reissue after a head move must not repost the nudge.
        [(_, operation, reviewer, author)] = [c for c in publisher.calls if c[0] == "reminder_operation"]
        assert operation == "reminder:t1"
        assert (reviewer, author) == ("the-reviewer", "the-author")

    def test_a_held_nudge_reconciles_even_when_context_is_unreadable(self) -> None:
        # A2 ordering: presence-only lookup precedes claim/recipient
        # reads, so a landed nudge reconciles when both ports fail
        publisher = FakePublisher(found=True)
        assert gates_without_context(publisher).reminder_gate(self.WORK) == RemLanded(timer_id="t1")

    def test_retryable_exhaustion_classifies_blocked(self) -> None:
        publisher = FakePublisher(mode="boundary")
        assert gates(publisher).reminder_gate(self.WORK) == RemBlocked(timer_id="t1")

    def test_an_unknown_terminal_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unknown")
        result = gates(publisher).reminder_gate(self.WORK)
        assert isinstance(result, RemFault) and result.timer_id == "t1" and result.reason

    def test_a_proven_capability_denial_classifies_blocked_not_landed(self) -> None:
        publisher = FakePublisher(mode="capability")
        assert gates(publisher).reminder_gate(self.WORK) == RemBlocked(timer_id="t1")

    def test_an_unrecognized_returned_status_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unclassified")
        result = gates(publisher).reminder_gate(self.WORK)
        assert isinstance(result, RemFault) and "banana" in result.reason


class TestAnnounceGate:
    """The announce gate fences EVERY claimed authority field (A1.5):
    only the grant incarnation exposes a stale announce whose
    head/base/policy tuple is identical (draft -> resume)."""

    WORK = AnnounceReq(
        op="ready:h1:i1",
        incarnation=1,
        head="h1",
        base="b1",
        policy="p1",
        strict_base=True,
        base_current=True,
    )

    def test_an_announcement_lands_under_a_standing_claim(self) -> None:
        publisher = FakePublisher()
        assert gates(publisher).announce_gate(self.WORK) == ALanded(incarnation=1, head="h1")
        [(_, kind, operation, _, _)] = [c for c in publisher.calls if c[0] == "immutable"]
        assert (kind, operation) == ("readiness", "ready:h1:i1")

    @pytest.mark.parametrize(
        "drift",
        [
            {"phase": "terminal"},
            {"phase": "quiescent"},
            {"incarnation": 2},
            {"head": "h2"},
            {"base": "b2"},
            {"policy": "p2"},
        ],
    )
    def test_any_moved_claim_field_refuses_the_post(self, drift: dict) -> None:
        publisher = FakePublisher()
        observed = moved(**drift)
        result = gates(publisher, claim=observed).announce_gate(self.WORK)
        assert result == AMoved(
            incarnation=1,
            observed_head=observed.head,
            observed_base=observed.base,
            observed_policy=observed.policy,
            observed_incarnation=observed.incarnation,
            observed_phase=observed.phase,
        )
        assert not [c for c in publisher.calls if c[0] == "immutable"]  # never posted

    def test_lookup_first_reconciles_landed_even_after_the_claim_moved(self) -> None:
        # a crash AFTER the provider held the announcement must
        # reconcile landed, never AMoved: the effect already happened
        publisher = FakePublisher(found=True)
        result = gates(publisher, claim=moved(incarnation=2)).announce_gate(self.WORK)
        assert result == ALanded(incarnation=1, head="h1")

    def test_a_legacy_unlanded_announcement_fails_closed_as_moved(self) -> None:
        publisher = FakePublisher()
        legacy = AnnounceReq(op="ready:h1:i1", incarnation=1, head="h1", base="b1", policy="p1")

        result = gates(publisher).announce_gate(legacy)

        assert isinstance(result, AMoved)
        assert not [call for call in publisher.calls if call[0] == "immutable"]

    def test_a_legacy_announcement_still_reconciles_when_it_already_landed(self) -> None:
        publisher = FakePublisher(found=True)
        legacy = AnnounceReq(op="ready:h1:i1", incarnation=1, head="h1", base="b1", policy="p1")

        assert gates(publisher).announce_gate(legacy) == ALanded(incarnation=1, head="h1")

    def test_retryable_exhaustion_retains_the_exact_request(self) -> None:
        publisher = FakePublisher(mode="boundary")
        assert gates(publisher).announce_gate(self.WORK) == ABlocked(incarnation=1, head="h1", base="b1", policy="p1")

    def test_unstaged_custody_defers_the_exact_request_without_a_provider_call(self) -> None:
        blocker = "2c60edc8-6ba8-4cd7-bd89-e1638d70329d"

        def unstaged() -> CurrentClaim:
            raise UnstagedCustodyError(blocker)

        publisher = FakePublisher()
        result = V5PublicationGates(
            publisher=publisher,
            claim=unstaged,
            recipients=lambda: ("the-reviewer", "the-author"),
            dashboard_phase=lambda: "running",
        ).announce_gate(self.WORK)

        assert result == ADeferred(
            op=self.WORK.op,
            incarnation=self.WORK.incarnation,
            head=self.WORK.head,
            base=self.WORK.base,
            policy=self.WORK.policy,
            strict_base=self.WORK.strict_base,
            base_current=self.WORK.base_current,
            blocker=blocker,
        )
        assert not [call for call in publisher.calls if call[0] == "immutable"]

    def test_an_identity_collision_fails_closed(self) -> None:
        publisher = FakePublisher(mode="collision")
        result = gates(publisher).announce_gate(self.WORK)
        assert isinstance(result, AFault) and result.op == "ready:h1:i1"

    def test_an_unknown_terminal_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unknown")
        result = gates(publisher).announce_gate(self.WORK)
        assert isinstance(result, AFault) and result.reason

    def test_a_proven_capability_denial_classifies_blocked_not_landed(self) -> None:
        publisher = FakePublisher(mode="capability")
        assert gates(publisher).announce_gate(self.WORK) == ABlocked(incarnation=1, head="h1", base="b1", policy="p1")

    def test_an_unrecognized_returned_status_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unclassified")
        result = gates(publisher).announce_gate(self.WORK)
        assert isinstance(result, AFault) and "banana" in result.reason


class TestDashGate:
    """The dashboard is authority-orthogonal by design (A5): no fence —
    a stale board row is corrected by the next upsert; the upsert is an
    idempotent overwrite, so no lookup-first ledger either."""

    WORK = DashReq(entries=["row1", "row2"], digest="d1", desired_entries=["row1", "row2"], desired_digest="d1")

    def test_a_dormant_pr_defers_without_a_provider_effect(self) -> None:
        publisher = FakePublisher()
        result = gates(publisher, claim=moved(phase="quiescent")).dash_gate(self.WORK)
        assert result == DashDeferred(
            entries=["row1", "row2"], digest="d1", desired_entries=["row1", "row2"], desired_digest="d1"
        )
        assert publisher.calls == []

    def test_an_upsert_lands_and_echoes_the_desired_state(self) -> None:
        publisher = FakePublisher()
        assert gates(publisher).dash_gate(self.WORK) == DashLanded(
            entries=["row1", "row2"], digest="d1", desired_entries=["row1", "row2"], desired_digest="d1"
        )
        [(_, operation, _, body)] = [c for c in publisher.calls if c[0] == "dashboard"]
        # `dash:{digest}` matches the V5 recovery door's durable identity
        # so DS2.2 composition needs no operation aliases.
        assert operation == "dash:d1"
        assert "row1" in body and "row2" in body

    def test_an_upsert_never_reads_authority(self) -> None:
        publisher = FakePublisher()

        def forbidden_claim() -> CurrentClaim:
            raise AssertionError("the authority-orthogonal dashboard must not read a claim")

        gate = V5PublicationGates(
            publisher=publisher,
            claim=forbidden_claim,
            recipients=lambda: ("the-reviewer", "the-author"),
        )

        assert isinstance(gate.dash_gate(self.WORK), DashLanded)

    def test_retryable_exhaustion_retains_the_exact_effect(self) -> None:
        publisher = FakePublisher(mode="boundary")
        result = gates(publisher).dash_gate(self.WORK)
        assert result == DashBlocked(
            entries=["row1", "row2"], digest="d1", desired_entries=["row1", "row2"], desired_digest="d1"
        )

    def test_an_unknown_terminal_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unknown")
        result = gates(publisher).dash_gate(self.WORK)
        assert isinstance(result, DashFault) and result.digest == "d1" and result.reason

    def test_a_proven_capability_denial_classifies_blocked_not_landed(self) -> None:
        publisher = FakePublisher(mode="capability")
        result = gates(publisher).dash_gate(self.WORK)
        assert result == DashBlocked(
            entries=["row1", "row2"], digest="d1", desired_entries=["row1", "row2"], desired_digest="d1"
        )

    def test_an_unrecognized_returned_status_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unclassified")
        result = gates(publisher).dash_gate(self.WORK)
        assert isinstance(result, DashFault) and "banana" in result.reason

    def test_an_updated_board_is_a_proven_landing(self) -> None:
        publisher = FakePublisher(mode="existing")
        result = gates(publisher).dash_gate(self.WORK)
        assert isinstance(result, DashLanded)


class TestPublishGate:
    """Each finding publishes as its own anchored effect
    (`findings:{head}:i{n}:{finding_id}`): presence-only lookup first,
    one full claim fence before any post, exclusive custody in mem.
    Content collisions surface from the publisher's per-finding
    payload comparison."""

    WORK = Publishable(
        head="h1",
        base="b1",
        policy="p1",
        incarnation=1,
        findings=[
            {
                "id": "f1",
                "blocking": True,
                "body": "The TTL is read as minutes.",
                "path": "src/gate.py",
                "line": 10,
                "suggestion": "    return issued_at + timedelta(seconds=ttl_seconds)",
                "related_locations": [{"path": "src/models.py", "line": 18}],
            },
            {"id": "f2", "blocking": True, "body": "Only true approvals may count."},
        ],
        effect="findings:h1:i1",
        op="findings:h1:i1",
        mem={"reviewed": [], "provisional": [], "findings": [], "dismissed": [], "pub": {}},
    )

    def test_each_finding_lands_under_its_own_anchored_identity(self) -> None:
        publisher = FakePublisher()
        result = gates(publisher).publish_gate(self.WORK)
        assert result == ReviewLanded(
            head="h1", incarnation=1, findings=self.WORK.findings, effect="findings:h1:i1", mem=self.WORK.mem
        )
        lookups = [c for c in publisher.calls if c[0] == "finding_find"]
        assert [operation for _, operation, _head in lookups] == ["findings:h1:i1:f1", "findings:h1:i1:f2"]
        [batch] = [c for c in publisher.calls if c[0] == "findings"]
        assert batch[1] == "h1" and batch[3] == "findings:h1:i1"
        [anchored] = batch[2]
        assert (
            anchored.operation,
            anchored.text,
            anchored.path,
            anchored.line,
            anchored.related_locations,
            anchored.suggestion,
        ) == (
            "findings:h1:i1:f1",
            "The TTL is read as minutes.",
            "src/gate.py",
            10,
            (("src/models.py", 18),),
            "    return issued_at + timedelta(seconds=ttl_seconds)",
        )
        [plain] = [c for c in publisher.calls if c[0] == "finding"]
        assert plain[1] == "findings:h1:i1:f2" and plain[4] == "" and plain[5] == 0

    def test_all_anchored_findings_share_one_native_review_mutation(self) -> None:
        work = replace(
            self.WORK,
            findings=[
                *self.WORK.findings[:1],
                {
                    "id": "f2",
                    "blocking": True,
                    "body": "Only true approvals may count.",
                    "path": "src/gate.py",
                    "line": 16,
                },
            ],
        )
        publisher = FakePublisher()

        result = gates(publisher).publish_gate(work)

        assert isinstance(result, ReviewLanded)
        [batch] = [call for call in publisher.calls if call[0] == "findings"]
        assert [finding.operation for finding in batch[2]] == ["findings:h1:i1:f1", "findings:h1:i1:f2"]
        assert not [call for call in publisher.calls if call[0] == "finding"]

    def test_a_clear_review_resolves_findings_from_the_superseded_head(self) -> None:
        work = replace(self.WORK, findings=[])
        publisher = FakePublisher()
        resolved: list[str] = []
        gate = V5PublicationGates(
            publisher,
            lambda: CLAIM,
            lambda: ("reviewer", "author"),
            resolve_stale_threads=lambda head: resolved.append(head) or 3,
        )

        result = gate.publish_gate(work)

        assert isinstance(result, ReviewLanded)
        assert resolved == ["h1"]
        assert not [call for call in publisher.calls if call[0] in {"finding", "findings", "finding_find"}]

    def test_a_clear_review_defers_behind_unstaged_webhook_custody(self) -> None:
        work = replace(self.WORK, findings=[])
        publisher = FakePublisher()
        gate = V5PublicationGates(
            publisher,
            lambda: (_ for _ in ()).throw(UnstagedCustodyError("delivery-1")),
            lambda: ("reviewer", "author"),
            resolve_stale_threads=lambda _head: 0,
        )

        result = gate.publish_gate(work)

        assert result == PublicationDeferred(
            operation="findings:h1:i1",
            head="h1",
            base="b1",
            policy="p1",
            incarnation=1,
            findings=[],
            effect="findings:h1:i1",
            mem=work.mem,
            attempt=1,
            blocker="delivery-1",
        )

    def test_an_unmarkable_finding_id_degrades_to_its_digest(self) -> None:
        work = Publishable(
            head="h1",
            base="b1",
            policy="p1",
            incarnation=1,
            findings=[{"id": "spaced finding id", "blocking": True, "body": "b"}],
            effect="findings:h1:i1",
            op="findings:h1:i1",
            mem=self.WORK.mem,
        )
        publisher = FakePublisher()
        gates(publisher).publish_gate(work)
        [(_, operation, _head)] = [c for c in publisher.calls if c[0] == "finding_find"]
        assert operation.startswith("findings:h1:i1:") and " " not in operation

    def test_a_held_finding_reconciles_without_a_fence_claim_or_post(self) -> None:
        head = "a" * 40
        operation = f"findings:{head}:i1"
        work = Publishable(
            head=head,
            base="b" * 40,
            policy="p1",
            incarnation=1,
            findings=[{"id": "f1", "blocking": True, "body": "The TTL is read as minutes."}],
            effect=operation,
            op=operation,
            mem=self.WORK.mem,
        )
        marker = CommentPublisher.marker("finding", f"{operation}:f1", head)

        class HeldInlineComment:
            def __init__(self) -> None:
                self.requests: list[tuple[str, str]] = []

            def pages(self, path: str):
                if path == "/repos/owner/repo/pulls/7/comments?per_page=100":
                    return (
                        {
                            "id": 7,
                            "html_url": "https://github.com/owner/repo/pull/7#discussion_r7",
                            "body": f"The TTL is read as minutes.\n\n{marker}",
                            "user": {"login": "hamsterdan[bot]"},
                        },
                    )
                assert path == "/repos/owner/repo/issues/7/comments?per_page=100"
                return ()

            def request(self, method: str, path: str, body=None):
                self.requests.append((method, path))
                raise AssertionError("a held finding must not be posted again")

        transport = HeldInlineComment()
        fences: list[tuple] = []
        claims: list[str] = []
        publisher = CommentPublisher(
            transport,  # type: ignore[arg-type]
            "owner/repo",
            7,
            "hamsterdan[bot]",
            lambda *args: fences.append(args),
        )
        gate = V5PublicationGates(
            publisher,
            lambda: claims.append("read") or CurrentClaim("running", 1, head, "b" * 40, "p1"),
            lambda: ("reviewer", "author"),
        )

        assert gate.publish_gate(work) == ReviewLanded(
            head=head,
            incarnation=1,
            findings=work.findings,
            effect=operation,
            mem=work.mem,
        )
        assert claims == fences == transport.requests == []

    def test_lookup_first_reconciles_landed_even_after_the_claim_moved(self) -> None:
        publisher = FakePublisher(found=True)
        result = gates(publisher, claim=moved(head="h2")).publish_gate(self.WORK)
        assert isinstance(result, ReviewLanded) and result.effect == "findings:h1:i1"

    def test_a_content_collision_fails_closed(self) -> None:
        publisher = FakePublisher(mode="collision")
        result = gates(publisher).publish_gate(self.WORK)
        assert isinstance(result, ReviewFault) and "collided" in result.reason

    def test_a_moved_claim_reports_the_complete_observed_authority(self) -> None:
        publisher = FakePublisher()
        observed = moved(incarnation=2, phase="quiescent")
        result = gates(publisher, claim=observed).publish_gate(self.WORK)
        assert result == ReviewMoved(
            head="h1",
            observed=observed.head,
            observed_base=observed.base,
            observed_policy=observed.policy,
            observed_incarnation=2,
            observed_phase="quiescent",
            findings=self.WORK.findings,
            mem=self.WORK.mem,
        )
        assert not [c for c in publisher.calls if c[0] == "finding"]

    def test_retryable_exhaustion_retains_the_exact_operation(self) -> None:
        publisher = FakePublisher(mode="boundary")
        result = gates(publisher).publish_gate(self.WORK)
        assert result == ReviewBlocked(
            head="h1",
            base="b1",
            policy="p1",
            incarnation=1,
            findings=self.WORK.findings,
            effect="findings:h1:i1",
            op="findings:h1:i1",
            failure_class="transport_ambiguity",
            provider_status=None,
            provider_detail="none",
            mem=self.WORK.mem,
        )

    def test_an_unknown_terminal_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unknown")
        result = gates(publisher).publish_gate(self.WORK)
        assert isinstance(result, ReviewFault) and result.reason

    def test_a_proven_capability_denial_classifies_blocked_not_landed(self) -> None:
        publisher = FakePublisher(mode="capability")
        result = gates(publisher).publish_gate(self.WORK)
        assert isinstance(result, ReviewBlocked) and result.op == "findings:h1:i1"
        assert (result.failure_class, result.provider_status, result.provider_detail) == (
            "capability_denial",
            None,
            "none",
        )

    def test_an_unrecognized_returned_status_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unclassified")
        result = gates(publisher).publish_gate(self.WORK)
        assert isinstance(result, ReviewFault) and "banana" in result.reason


class TestStaleThreadResolution:
    """A fresh finding publication or readiness announcement also
    retires the App's finding threads from superseded heads (ruled
    2026-09-02); held reconciles stay effect-free, so recovery paths
    never mutate threads."""

    def _gates(self, publisher: FakePublisher, resolved: list[str]) -> V5PublicationGates:
        return V5PublicationGates(
            publisher=publisher,
            claim=lambda: CLAIM,
            recipients=lambda: ("the-reviewer", "the-author"),
            resolve_stale_threads=lambda head: resolved.append(head) or 0,
        )

    def test_a_fresh_finding_publication_resolves_stale_threads_for_its_head(self) -> None:
        resolved: list[str] = []
        result = self._gates(FakePublisher(), resolved).publish_gate(TestPublishGate.WORK)
        assert isinstance(result, ReviewLanded)
        assert resolved == ["h1"]

    def test_a_held_finding_reconcile_never_touches_threads(self) -> None:
        resolved: list[str] = []
        result = self._gates(FakePublisher(found=True), resolved).publish_gate(TestPublishGate.WORK)
        assert isinstance(result, ReviewLanded)
        assert resolved == []

    def test_a_fresh_announcement_resolves_stale_threads_for_its_head(self) -> None:
        resolved: list[str] = []
        work = AnnounceReq(
            op="ready:h1:i1", incarnation=1, head="h1", base="b1", policy="p1", strict_base=False, base_current=True
        )
        result = self._gates(FakePublisher(), resolved).announce_gate(work)
        assert result == ALanded(incarnation=1, head="h1")
        assert resolved == ["h1"]

    def test_a_held_announcement_reconcile_never_touches_threads(self) -> None:
        resolved: list[str] = []
        work = AnnounceReq(
            op="ready:h1:i1", incarnation=1, head="h1", base="b1", policy="p1", strict_base=False, base_current=True
        )
        result = self._gates(FakePublisher(found=True), resolved).announce_gate(work)
        assert result == ALanded(incarnation=1, head="h1")
        assert resolved == []
