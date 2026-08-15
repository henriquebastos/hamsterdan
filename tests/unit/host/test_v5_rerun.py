"""Executable contracts for the provider-backed V5 rerun gate.

CV17.DS2.1b: the rerun gate against duck-typed broker/runs/claim fakes,
per host test conventions. The fake-world harness in
tests/unit/readiness/net_v5 is the semantic spec:

- lookup-first reconciliation happens BEFORE any fence, claim read, or
  failure mode (a crash after the provider held the rerun reconciles
  landed with the answered evidence echoed);
- the gate compares EVERY claimed authority field (A1.5) — the live
  provider fields AND the host grant — via the claim port before the
  effect: any drift classifies Moved with the attempted tuple echoed;
- proven pre-effect movement (a vanished indicted run, the broker's
  currency refusal) classifies Moved, never Fault;
- the pre-request evidence cut comes from the broker's FINAL provider
  run read immediately before issuance;
- the rerun ladder has NO blocked rung: every unproven outcome —
  lookup failure, unreadable claim, unreadable runs, boundary loss
  mid-request, capability denial, unclassifiable terminal — classifies
  Fault, which retains the EXACT request for the recovery door (A2).
"""

from __future__ import annotations

import pytest

from hamsterdan.contracts.readiness_v5 import RerunFault, RerunLanded, RerunMoved, RerunReq
from hamsterdan.github_app.models import (
    ActionsRunSnapshot,
    CommentReference,
    GitHubBoundaryError,
    PublicationResult,
    RerunIssue,
    RerunRefusedError,
)
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.rerun import V5RerunGate

CLAIM = CurrentClaim(phase="running", incarnation=1, head="h1", base="b1", policy="p1")
REFERENCE = CommentReference(1, "https://example.test/c/1")
MEM = {"baton": "ladder"}
INDICTED = ActionsRunSnapshot(5, "h1", "ci.yml", 1, "completed", "failure")
NEWER = ActionsRunSnapshot(7, "h1", "ci.yml", 2, "completed", "failure")


class FakeBroker:
    """Duck-typed CommentRerunBroker: records calls, classifies by mode.

    mode: None (requested) | "existing" (race: issue found the marker) |
    "refused" (raised RerunRefusedError: proven pre-effect movement) |
    "boundary" (raised: the POST may or may not have landed) |
    "unknown" (raised RuntimeError) | "capability" (definitive denial,
    returned not raised) | "unclassified" (unrecognized returned
    status). `found` simulates a prior held rerun for `held`;
    `lookup_error` makes the lookup itself fail. The cut echoes the
    broker's FINAL run read, newer than the gate's own listing.
    """

    def __init__(self, mode: str | None = None, found: bool = False, lookup_error: bool = False):
        self.mode, self.found, self.lookup_error = mode, found, lookup_error
        self.cut = (9, 1)
        self.calls: list[tuple] = []

    def held(self, run_id: int, head: str, operation: str) -> PublicationResult | None:
        self.calls.append(("held", run_id, head, operation))
        if self.lookup_error:
            raise GitHubBoundaryError("comment listing unavailable")
        if self.found:
            return PublicationResult("existing", REFERENCE)
        return None

    def issue(self, run: ActionsRunSnapshot, *, epoch: int, operation: str) -> RerunIssue:
        self.calls.append(("issue", run.id, run.attempt, epoch, operation))
        if self.mode == "existing":
            return RerunIssue(PublicationResult("existing", REFERENCE), *self.cut)
        if self.mode == "refused":
            raise RerunRefusedError("rerun request does not belong to the configured repository and exact head")
        if self.mode == "boundary":
            raise GitHubBoundaryError("GitHub did not prove rerun broker publication")
        if self.mode == "unknown":
            raise RuntimeError("provider returned an unclassifiable terminal")
        if self.mode == "capability":
            return RerunIssue(PublicationResult("capability_unavailable", None, False), *self.cut)
        if self.mode == "unclassified":
            return RerunIssue(PublicationResult("banana", REFERENCE), *self.cut)
        return RerunIssue(PublicationResult("requested", REFERENCE), *self.cut)


def req(**changes) -> RerunReq:
    values = {
        "fingerprint": "lin:fp1",
        "fp": "fp1",
        "op": "rerun:lin:fp1",
        "head": "h1",
        "base": "b1",
        "policy": "p1",
        "incarnation": 1,
        "run_id": 5,
        "attempt": 1,
        "mem": MEM,
        **changes,
    }
    return RerunReq(**values)


def gate(
    broker: FakeBroker,
    claim: CurrentClaim = CLAIM,
    runs: tuple[ActionsRunSnapshot, ...] = (NEWER, INDICTED),
) -> V5RerunGate:
    return V5RerunGate(broker=broker, runs=lambda head: runs, claim=lambda: claim)


def _unreadable_claim() -> CurrentClaim:
    raise GitHubBoundaryError("claim unreadable")


def _unreadable_runs(head: str) -> tuple[ActionsRunSnapshot, ...]:
    raise GitHubBoundaryError("workflow runs unavailable")


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


def _assert_fault_retains_the_exact_request(out: object) -> None:
    assert isinstance(out, RerunFault)
    assert out.fingerprint == "lin:fp1" and out.op == "rerun:lin:fp1" and out.fp == "fp1"
    assert (out.head, out.base, out.policy, out.incarnation) == ("h1", "b1", "p1", 1)
    assert (out.run_id, out.attempt) == (5, 1)
    assert out.mem == MEM


def _assert_moved_echoes_the_attempted_tuple(out: object) -> None:
    assert isinstance(out, RerunMoved)
    assert (out.fp, out.head, out.base, out.policy, out.incarnation) == ("fp1", "h1", "b1", "p1", 1)
    assert out.fingerprint == "lin:fp1" and out.op == "rerun:lin:fp1" and out.mem == MEM


class TestRerunGate:
    """One rung of the escalation ladder: request, never observe."""

    def test_a_rerun_lands_with_the_brokers_final_read_as_its_cut(self) -> None:
        broker = FakeBroker()
        out = gate(broker).rerun_gate(req())
        assert isinstance(out, RerunLanded) and out.disposition == "requested"
        assert (out.run_id, out.attempt) == (5, 1)
        # the cut is the broker's FINAL provider run read immediately
        # before the POST — newer than the gate's own listing, so a run
        # appearing between the two reads can never outrun the cut
        assert (out.cut_run_id, out.cut_attempt) == (9, 1)
        assert out.mem == MEM
        # the request targeted the EXACT indicted run under the grant
        assert broker.calls == [("held", 5, "h1", "rerun:lin:fp1"), ("issue", 5, 1, 1, "rerun:lin:fp1")]

    def test_an_already_held_rerun_reconciles_landed_before_any_read(self) -> None:
        # claim AND runs are unreadable: only lookup-first BEFORE any
        # other read can land this — a crash after the provider held
        # the rerun must reconcile, never fault or repeat
        broker = FakeBroker(found=True)
        subject = V5RerunGate(broker=broker, runs=_unreadable_runs, claim=_unreadable_claim)
        out = subject.rerun_gate(req())
        assert isinstance(out, RerunLanded) and out.disposition == "existing"
        # an existing landing echoes the answered evidence as its cut
        assert (out.run_id, out.attempt) == (5, 1)
        assert (out.cut_run_id, out.cut_attempt) == (5, 1)
        assert out.mem == MEM
        assert broker.calls == [("held", 5, "h1", "rerun:lin:fp1")]

    @pytest.mark.parametrize(
        "drift",
        [
            {"phase": "quiescent"},
            {"incarnation": 2},
            {"head": "h2"},
            {"base": "b2"},
            {"policy": "p2"},
        ],
    )
    def test_any_moved_claim_field_refuses_the_request(self, drift: dict) -> None:
        broker = FakeBroker()
        out = gate(broker, claim=moved(**drift)).rerun_gate(req())
        # the ATTEMPTED tuple travels back so CI can park or reissue
        _assert_moved_echoes_the_attempted_tuple(out)
        assert all(call[0] != "issue" for call in broker.calls)

    def test_a_vanished_indicted_run_classifies_moved(self) -> None:
        # the provider no longer reports the indicted run for this head:
        # proven movement, nothing issued, no budget burns — CI parks
        # the fingerprint until fresher ingress arrives
        broker = FakeBroker()
        out = gate(broker, runs=(NEWER,)).rerun_gate(req())
        _assert_moved_echoes_the_attempted_tuple(out)
        assert all(call[0] != "issue" for call in broker.calls)

    def test_the_brokers_own_currency_refusal_classifies_moved(self) -> None:
        # the broker verified currency and refused BEFORE any effect:
        # proven movement even when the gate's fence already passed
        out = gate(FakeBroker(mode="refused")).rerun_gate(req())
        _assert_moved_echoes_the_attempted_tuple(out)

    def test_a_race_found_existing_request_reconciles_landed(self) -> None:
        broker = FakeBroker(mode="existing")
        out = gate(broker).rerun_gate(req())
        assert isinstance(out, RerunLanded) and out.disposition == "existing"
        assert (out.cut_run_id, out.cut_attempt) == (5, 1)

    def test_a_lookup_failure_fails_closed(self) -> None:
        # the lookup failing means a PRIOR crashed round may still hold
        # the rerun: issuing anyway could repeat the effect
        out = gate(FakeBroker(lookup_error=True)).rerun_gate(req())
        _assert_fault_retains_the_exact_request(out)

    def test_an_unreadable_claim_fails_closed(self) -> None:
        broker = FakeBroker()
        subject = V5RerunGate(broker=broker, runs=lambda head: (INDICTED,), claim=_unreadable_claim)
        out = subject.rerun_gate(req())
        _assert_fault_retains_the_exact_request(out)
        assert all(call[0] != "issue" for call in broker.calls)

    def test_a_runs_read_failure_fails_closed(self) -> None:
        broker = FakeBroker()
        subject = V5RerunGate(broker=broker, runs=_unreadable_runs, claim=lambda: CLAIM)
        out = subject.rerun_gate(req())
        _assert_fault_retains_the_exact_request(out)
        assert all(call[0] != "issue" for call in broker.calls)

    def test_an_issuance_boundary_failure_fails_closed(self) -> None:
        # the POST may or may not have landed: A2 retains the EXACT
        # request so the recovery door reissues the SAME operation and
        # lookup-first reconciles
        out = gate(FakeBroker(mode="boundary")).rerun_gate(req())
        _assert_fault_retains_the_exact_request(out)

    def test_an_unknown_terminal_fails_closed(self) -> None:
        out = gate(FakeBroker(mode="unknown")).rerun_gate(req())
        _assert_fault_retains_the_exact_request(out)

    def test_a_capability_denial_fails_closed(self) -> None:
        # the ladder has NO blocked rung by design: a proven denial
        # still surfaces through the fault door, never as landed
        out = gate(FakeBroker(mode="capability")).rerun_gate(req())
        _assert_fault_retains_the_exact_request(out)

    def test_an_unrecognized_returned_status_fails_closed(self) -> None:
        out = gate(FakeBroker(mode="unclassified")).rerun_gate(req())
        _assert_fault_retains_the_exact_request(out)
