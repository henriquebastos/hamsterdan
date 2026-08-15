"""Provider-backed rerun gate for the V5 topology (CV17.DS2.1b).

The gate executes ONE same-head whole-run rerun request against the
real ``CommentRerunBroker`` surface and classifies its own outcome into
the exact typed terminals the escalation loop routes by color. The
fake-world harness (tests/unit/readiness/net_v5/harness.py) is the
semantic spec:

1. lookup-first reconciliation (A2) happens BEFORE any fence, claim
   read, or failure mode — a crash after the provider held the rerun
   reconciles landed with the answered evidence echoed as its cut;
2. the gate compares EVERY claimed authority field (A1.5): the live
   provider fields (head, base, policy) AND the host grant (phase,
   incarnation), via the claim port — any drift classifies Moved with
   the attempted tuple echoed so CI can park or reissue;
3. proven pre-effect movement also classifies Moved: an indicted run
   the provider no longer reports, or the broker's own currency
   refusal (RerunRefusedError) — nothing was issued, no budget burns,
   and CI parks the fingerprint until fresher ingress arrives;
4. the pre-request evidence cut is the NEWEST run identity the broker
   observes in its FINAL provider run read immediately before the POST
   (no run can appear between the cut and the effect) — evidence at or
   below the cut can never prove the fresh rerun failed;
5. the ladder has NO blocked rung by design: every unproven outcome —
   lookup failure, unreadable claim, unreadable runs, boundary loss
   mid-request, definitive capability denial, identity collision, or
   an unclassifiable terminal — classifies Fault, which retains the
   EXACT request so the recovery door reissues the SAME operation
   identity and lookup-first reconciles (A2).

Classified outcomes never raise into Motus: they return as typed
terminals the loop folds, so the durable History carries the
classification. Only a genuinely unclassified exception (a bug)
propagates as an activity failure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from hamsterdan.contracts.readiness_v5 import RerunFault, RerunLanded, RerunMoved, RerunReq
from hamsterdan.github_app.models import (
    ActionsRunSnapshot,
    GitHubBoundaryError,
    PublicationResult,
    RerunIssue,
    RerunRefusedError,
)
from hamsterdan.host.v5.claim import ClaimReader, CurrentClaim

RunsReader = Callable[[str], tuple[ActionsRunSnapshot, ...]]
"""A one-argument port yielding the provider's current runs for a head."""


class RerunBroker(Protocol):
    """The CommentRerunBroker surface the gate binds to (duck-typed in tests)."""

    def held(self, run_id: int, head: str, operation: str) -> PublicationResult | None: ...

    def issue(self, run: ActionsRunSnapshot, *, epoch: int, operation: str) -> RerunIssue: ...


def _reason(error: Exception) -> str:
    return str(error) or repr(error)


@dataclass(frozen=True)
class V5RerunGate:
    """One rung of the escalation ladder: request, never observe.

    ``claim`` returns a fresh, complete ``CurrentClaim`` per call.
    ``runs`` returns the provider's current runs for a head (the
    composition binds the workflow path) and serves ONLY to locate the
    indicted snapshot — the broker's final read owns the evidence cut.
    """

    broker: RerunBroker
    runs: RunsReader
    claim: ClaimReader

    def rerun_gate(self, work: RerunReq) -> RerunLanded | RerunMoved | RerunFault:
        # an existing landing echoes the answered evidence as its cut
        existing = RerunLanded(
            fingerprint=work.fingerprint,
            op=work.op,
            run_id=work.run_id,
            attempt=work.attempt,
            disposition="existing",
            cut_run_id=work.run_id,
            cut_attempt=work.attempt,
            mem=work.mem,
        )
        moved = RerunMoved(
            fingerprint=work.fingerprint,
            fp=work.fp,
            head=work.head,
            base=work.base,
            policy=work.policy,
            incarnation=work.incarnation,
            op=work.op,
            mem=work.mem,
        )
        try:
            # lookup-first: a prior crashed round may hold the rerun —
            # reconcile BEFORE any claim or runs read can refuse it
            if self.broker.held(work.run_id, work.head, work.op) is not None:
                return existing
            current = self.claim()
        except (GitHubBoundaryError, RuntimeError, ValueError) as error:
            return self._fault(work, _reason(error))
        expected = CurrentClaim(
            phase="running", incarnation=work.incarnation, head=work.head, base=work.base, policy=work.policy
        )
        if current != expected:
            return moved
        try:
            reported = self.runs(work.head)
        except (GitHubBoundaryError, RuntimeError, ValueError) as error:
            return self._fault(work, _reason(error))
        run = next((candidate for candidate in reported if candidate.id == work.run_id), None)
        if run is None:
            # the provider no longer reports the indicted run: proven
            # movement, nothing issued — CI parks the fingerprint until
            # fresher ingress arrives
            return moved
        try:
            issued = self.broker.issue(run, epoch=work.incarnation, operation=work.op)
        except RerunRefusedError:
            # the broker's own currency check refused BEFORE any effect:
            # proven movement, never a fault
            return moved
        except (GitHubBoundaryError, RuntimeError, ValueError) as error:
            # the POST may or may not have landed: fail closed — the
            # recovery door reissues and lookup-first reconciles
            return self._fault(work, _reason(error))
        result = issued.result
        if not result.capability_available:
            return self._fault(work, "the provider proved it cannot publish the rerun request")
        if result.status == "existing":
            return existing
        if result.status != "requested":
            return self._fault(work, f"unclassified rerun status {result.status!r}")
        return RerunLanded(
            fingerprint=work.fingerprint,
            op=work.op,
            run_id=work.run_id,
            attempt=work.attempt,
            disposition="requested",
            cut_run_id=issued.cut_run_id,
            cut_attempt=issued.cut_attempt,
            mem=work.mem,
        )

    @staticmethod
    def _fault(work: RerunReq, reason: str) -> RerunFault:
        # A2: the fault retains the EXACT request for the recovery door
        return RerunFault(
            fingerprint=work.fingerprint,
            op=work.op,
            reason=reason,
            fp=work.fp,
            head=work.head,
            base=work.base,
            policy=work.policy,
            incarnation=work.incarnation,
            run_id=work.run_id,
            attempt=work.attempt,
            mem=work.mem,
        )
