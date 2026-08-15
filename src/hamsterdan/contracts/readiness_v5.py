"""JSON-faithful values for the V5 actor-loop PR-readiness workflow.

V5 tokens fall into three families, mirroring the ES-007 discipline:

- ingress observations: host-normalized events delivered through doors;
- batons: one private memory value per concern loop;
- directed facts: dedicated colors mailed loop-to-loop through mailbox
  places — the only cross-loop influence that exists.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from hamsterdan.contracts.readiness import WorkflowModel

Phase = Literal["running", "quiescent", "terminal"]
HeadRelation = Literal["new", "superseded", "confirmed", "resumed", "refreshed"]
RunConclusion = Literal["queued", "in_progress", "success", "failure"]


# -- ingress observations (host-normalized) --------------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HeadSeen(WorkflowModel):
    head: str
    base: str
    mergeable: bool
    policy: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DraftSeen(WorkflowModel):
    pass


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReadySeen(WorkflowModel):
    pass


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CloseSeen(WorkflowModel):
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CommentSeen(WorkflowModel):
    id: str
    kind: str
    arg: str
    authorized: bool


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HumanSeen(WorkflowModel):
    approval: bool
    changes_requested: bool
    unresolved: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RunSeen(WorkflowModel):
    """A host-normalized run observation.

    `(run_id, attempt)` is the evidence IDENTITY and its lexicographic
    order is the freshness order: the host guarantees run ids increase
    over a head's life (GitHub's do); a provider without that guarantee
    must have its host substitute a normalized ordinal here. The same
    identity may be observed more than once as the run progresses
    (queued/in_progress -> terminal conclusion).
    """

    head: str
    run_id: int
    attempt: int
    conclusion: RunConclusion
    fingerprint: str


# -- batons (one private memory value per loop) -----------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class LifeState(WorkflowModel):
    phase: Phase
    incarnation: int
    head: str
    base: str
    mergeable: bool
    policy: str
    expected: str
    expected_op: str
    lineage: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CiState(WorkflowModel):
    """The CI loop's baton: newest exact-head evidence plus budget lineage.

    `lineage` scopes the escalation ladder budget: fresh on new or
    superseded code, kept across our own confirmed repair and a resume.
    `best` is `[run_id, attempt]` of the winning run (empty until one
    lands). `parked` holds fingerprints whose escalation MOVED under the
    currently-held authority; the next refresh reissues them.
    """

    head: str
    base: str
    policy: str
    lineage: str
    incarnation: int
    best: tuple[int, int] | tuple[()]
    status: str
    fingerprint: str
    parked: tuple[str, ...]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Ladder(WorkflowModel):
    """The escalation loop's baton: rerun/repair budgets per rung key.

    Keys are `{lineage}:{fingerprint}` — the budget is per fingerprint
    PER LINEAGE. Every consumed rung records the run EVIDENCE
    (`run_id`/`attempt`) it answered; only strictly newer evidence
    advances the ladder, so duplicate mails never burn a rung. `reruns`
    values are `{"state": "done", "run_id", "attempt"}` or
    `{"state": "fault"}`; an in-flight rerun HOLDS the baton, so no
    marker is needed. `repairs` values are retained entry dicts (state
    pending|done|declined|fault plus the raw fingerprint, ATTEMPTED
    authority, and evidence, so a moved settle can echo a recheck).
    `rerun_faults` retains the EXACT faulted request (A2) so the
    recovery door can reissue the same operation identity.
    """

    reruns: dict[str, Any]
    repairs: dict[str, Any]
    rerun_faults: dict[str, dict[str, Any]]


# -- directed facts (loop -> loop, dedicated colors) -------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HeadWork(WorkflowModel):
    incarnation: int
    head: str
    base: str
    policy: str
    relation: HeadRelation
    lineage: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class IntentFact(WorkflowModel):
    id: str
    kind: str
    arg: str
    authorized: bool
    phase: Phase
    provisional: bool
    incarnation: int
    head: str
    base: str
    policy: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CloseFact(WorkflowModel):
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RunWork(WorkflowModel):
    incarnation: int
    head: str
    run_id: int
    attempt: int
    conclusion: RunConclusion
    fingerprint: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ProvisionalHead(WorkflowModel):
    expected: str
    op: str
    lineage: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class GateFact(WorkflowModel):
    kind: str
    incarnation: int
    body: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ChecksFailure(WorkflowModel):
    """CI -> escalation: the newest run failed under this authority claim.

    The ladder budget is per fingerprint PER LINEAGE: the same flake on
    genuinely new code earns a fresh ladder; our own repair does not
    reset it. `run_id`/`attempt` carry the EVIDENCE identity: a rung
    only advances the ladder on strictly newer evidence, so a duplicate
    mail (assess and a moved-echo reissue can race) never burns a rung.
    """

    fingerprint: str
    head: str
    base: str
    policy: str
    lineage: str
    incarnation: int
    run_id: int
    attempt: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class EscMoved(WorkflowModel):
    """Escalation -> CI echo: an escalation effect classified MOVED.

    Carries the ATTEMPTED authority tuple (head, base, policy, and the
    grant incarnation) so CI can decide between reissuing under an
    already-fresher admitted tuple and parking until the refresh folds.
    """

    fp: str
    head: str
    base: str
    policy: str
    incarnation: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CiEnded(WorkflowModel):
    """The CI loop's terminal record: final verdict at close."""

    status: str
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MutationRequest(WorkflowModel):
    """Escalation/conversation -> mutation: push work under a full claim.

    The gate compares ALL claim fields at effect time (A1.5); the fold
    that mints the request never re-checks the world.
    """

    op: str
    head: str
    base: str
    policy: str
    incarnation: int
    source: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MutationSettled(WorkflowModel):
    """Mutation -> escalation: a repair push settled.
    `fingerprint` is the composite budget key."""

    op: str
    outcome: Literal["landed", "declined", "moved", "faulted"]
    incarnation: int
    fingerprint: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RecoverFact(WorkflowModel):
    """Conversation -> owning loop: a human asked to reissue a faulted
    publication under the SAME operation identity (A2)."""

    target: str
    op: str


# -- gate work and typed terminals (escalation rerun) ------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RerunReq(WorkflowModel):
    """The rerun gate's work token; the ladder baton is HELD in `mem`."""

    fingerprint: str  # composite budget key "{lineage}:{fp}"
    fp: str  # the raw fingerprint (for the moved-echo recheck)
    op: str  # stable operation identity: "rerun:{key}" (lookup-first)
    head: str
    base: str  # full authority claim (A1.5)
    policy: str
    incarnation: int
    run_id: int  # the evidence this rung answers
    attempt: int
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RerunLanded(WorkflowModel):
    """`disposition` says HOW it landed: "requested" means the gate
    issued the effect in this round; "existing" means lookup-first found
    the provider already holding it (a crash-recovery reconciliation) —
    the rerun, and any evidence observed since, predate this round.

    `(cut_run_id, cut_attempt)` is the pre-request evidence CUT: the
    newest run identity the provider reported for this head immediately
    before the gate issued the rerun. Evidence at or below the cut can
    never prove the fresh rerun failed. Only meaningful for
    "requested"; an "existing" landing echoes the answered evidence."""

    fingerprint: str
    op: str
    run_id: int  # the answered evidence, recorded on the burned rung
    attempt: int
    disposition: Literal["requested", "existing"]
    cut_run_id: int
    cut_attempt: int
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RerunMoved(WorkflowModel):
    """The attempted tuple travels back so CI can park or reissue."""

    fingerprint: str
    fp: str
    head: str
    base: str
    policy: str
    incarnation: int  # the attempted GRANT (draft→resume changes only this)
    op: str
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RerunFault(WorkflowModel):
    """A2: the fault retains the EXACT request for the recovery door."""

    fingerprint: str
    op: str
    reason: str
    fp: str
    head: str
    base: str
    policy: str
    incarnation: int
    run_id: int
    attempt: int
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class LadderEnded(WorkflowModel):
    """The escalation loop's terminal record: budgets at close."""

    reruns: dict[str, Any]
    repairs: dict[str, Any]
    reason: str
