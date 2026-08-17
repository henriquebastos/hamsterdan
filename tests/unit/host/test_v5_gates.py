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

import hashlib
import json

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
    """Findings publish under ONE batch effect identity
    (`findings:{head}:i{n}`): lookup-first with content comparison, a
    full claim fence before the post, exclusive custody in mem."""

    WORK = Publishable(
        head="h1",
        base="b1",
        policy="p1",
        incarnation=1,
        findings=[{"id": "f1", "note": "n1", "blocking": True}],
        effect="findings:h1:i1",
        op="findings:h1:i1",
        mem={"reviewed": [], "provisional": [], "findings": [], "dismissed": [], "pub": {}},
    )

    def test_findings_land_under_the_batch_identity(self) -> None:
        publisher = FakePublisher()
        result = gates(publisher).publish_gate(self.WORK)
        assert result == ReviewLanded(
            head="h1", incarnation=1, findings=self.WORK.findings, effect="findings:h1:i1", mem=self.WORK.mem
        )
        [(_, kind, operation, _, body)] = [c for c in publisher.calls if c[0] == "immutable"]
        # "finding" is the real publisher's marker kind for findings;
        # CommentPublisher.marker() rejects kinds outside its frozen set.
        assert (kind, operation) == ("finding", "findings:h1:i1")
        assert "f1" in body
        assert [name for name, _bodies in publisher.compatible_calls] == ["find", "immutable"]
        [find_compatible, immutable_compatible] = [bodies for _name, bodies in publisher.compatible_calls]
        assert find_compatible == immutable_compatible
        expected_legacy = (
            "## Hamsterdan review findings\n\n- `f1` (**blocking**): n1\n\n"
            "<!-- hamsterdan:findings-digest "
            f"{hashlib.sha256(json.dumps(self.WORK.findings, sort_keys=True, separators=(',', ':')).encode()).hexdigest()} -->"
        )
        assert find_compatible == (expected_legacy,)

    def test_lookup_first_accepts_the_pre_rendering_upgrade_body_without_a_fence_or_post(self) -> None:
        head = "a" * 40
        operation = f"findings:{head}:i1"
        work = Publishable(
            head=head,
            base="b" * 40,
            policy="p1",
            incarnation=1,
            findings=self.WORK.findings,
            effect=operation,
            op=operation,
            mem=self.WORK.mem,
        )
        digest = hashlib.sha256(json.dumps(work.findings, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        legacy_body = (
            "## Hamsterdan review findings\n\n- `f1` (**blocking**): n1\n\n"
            f"<!-- hamsterdan:findings-digest {digest} -->"
        )
        marker = CommentPublisher.marker("finding", operation, head)

        class HeldLegacyComment:
            def __init__(self) -> None:
                self.requests: list[tuple[str, str]] = []

            def pages(self, path: str):
                assert path == "/repos/owner/repo/issues/7/comments?per_page=100"
                return (
                    {
                        "id": 7,
                        "html_url": "https://github.com/owner/repo/pull/7#issuecomment-7",
                        "body": f"{legacy_body}\n\n{marker}",
                        "user": {"login": "hamsterdan[bot]"},
                    },
                )

            def request(self, method: str, path: str, body=None):
                self.requests.append((method, path))
                raise AssertionError("a held compatible finding must not be posted again")

        transport = HeldLegacyComment()
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
        publisher = FakePublisher(collide=True)
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
        assert not [c for c in publisher.calls if c[0] == "immutable"]

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

    def test_an_unrecognized_returned_status_fails_closed(self) -> None:
        publisher = FakePublisher(mode="unclassified")
        result = gates(publisher).publish_gate(self.WORK)
        assert isinstance(result, ReviewFault) and "banana" in result.reason

    def test_the_body_binds_the_complete_findings_payload(self) -> None:
        # two batches differing ONLY in a field the readable rendering
        # omits must still produce different bodies, so the provider's
        # stable-identity content comparison can fail closed (A2).
        first, second = FakePublisher(), FakePublisher()
        gates(first).publish_gate(self.WORK)
        variant = Publishable(
            head="h1",
            base="b1",
            policy="p1",
            incarnation=1,
            findings=[{"id": "f1", "note": "n1", "blocking": True, "extra": "field"}],
            effect="findings:h1:i1",
            op="findings:h1:i1",
            mem=self.WORK.mem,
        )
        gates(second).publish_gate(variant)
        [(_, _, _, _, body_a)] = [c for c in first.calls if c[0] == "immutable"]
        [(_, _, _, _, body_b)] = [c for c in second.calls if c[0] == "immutable"]
        assert body_a != body_b
