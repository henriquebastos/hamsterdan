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

    `closing` is the close reason while the ladder waits for pending
    repair settlements (None otherwise — a reason may be any string,
    including empty, so the sentinel must be distinct): close with a
    repair in custody
    must not retire the ladder before the mutation terminal folds, or
    the settlement would strand and the terminal record would lie
    `pending`. While closing, new evidence and recovery are absorbed —
    no new rung is ever opened after close.
    """

    reruns: dict[str, Any]
    repairs: dict[str, Any]
    rerun_faults: dict[str, dict[str, Any]]
    closing: str | None = None


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewMemory(WorkflowModel):
    """The review loop's baton: one durable review memory per PR.

    `reviewed` accumulates every head that completed an agent round,
    recorded at judge time (never at settlement), membership-unique.
    `provisional` retains findings whose publication MOVED — they
    republish under the next refreshed authority (or feed the next
    agent round) instead of being lost. An open publication takes
    EXCLUSIVE custody: provisional is empty while a pending, blocked,
    or faulted descriptor holds the attempted content. `findings` is
    the last landed/blocked findings list (the dashboard truth).
    `dismissed` holds finding ids the human waved off; they never
    republish — a dismissal touching a retained blocked/faulted
    operation CANCELS it (recovery goes inert; the descriptor stays
    for audit). `pub` is the publication descriptor: `{"phase":
    "idle"}` or a durable pending/blocked/faulted/cancelled record
    retaining the operation identity (A2) so recovery can reissue the
    SAME effect.
    """

    reviewed: tuple[str, ...]
    provisional: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    dismissed: tuple[str, ...]
    pub: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MutState(WorkflowModel):
    """The mutation loop's baton: the serialization IS the baton.

    While a push round is in flight the baton is HELD (no token in the
    place), so a second request waits visibly in the mailbox — one
    mutation at a time by construction. `idle` carries empty retention
    fields; `faulted` retains the EXACT operation identity and the FULL
    attempted authority claim (A2) so the recovery door can reissue the
    same operation, and declines every further request fail-closed.
    """

    state: Literal["idle", "faulted"]
    op_key: str
    op: str
    head: str
    base: str
    policy: str
    incarnation: int
    reason: str


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
    """Mutation -> lifecycle: expect our own push as the next head.

    `from_head` is the head the push moved FROM — the causal fence: the
    note only installs while lifecycle still stands on that head. A late
    note (recovery reconciled after the webhook already admitted the
    pushed head, or after the world moved further) is inert; the
    admission it would have upgraded already happened as `superseded`,
    an accepted lineage loss.
    """

    expected: str
    from_head: str
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

    `rid` is the producer's stable REQUEST identity, distinct from the
    semantic `op`: the rung key for escalation repairs (where the op IS
    the identity), the comment identity for conversation ops. Two
    distinct requests of the same kind at the same head must carry
    distinct rids, or the second would lookup-reconcile onto the first
    push's landed effect instead of reaching its own CAS refusal.
    """

    op: str
    rid: str
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


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DismissFact(WorkflowModel):
    """Conversation -> review: a human waved a finding off; it never
    counts against readiness and never republishes."""

    finding_id: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class SnoozeFact(WorkflowModel):
    """Conversation -> reminders: a human snoozed, resumed (`clear`),
    or deferred a reminder timer."""

    mode: Literal["snooze", "clear", "defer"]
    arg: str


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


# -- gate work and typed terminals (review) ----------------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RoundOpen(WorkflowModel):
    """The agent gate's work token; the review baton is HELD in `mem`.

    The agent sees only this token — never the world's credentials or
    the net's other tokens (no GitHub credential in agent territory).
    """

    head: str
    base: str
    policy: str
    incarnation: int
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class AgentReview(WorkflowModel):
    """The agent gate's output: raw findings for one head, unjudged."""

    head: str
    base: str
    policy: str
    incarnation: int
    findings: list[dict[str, Any]]
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Publishable(WorkflowModel):
    """The publish gate's work token: live findings under one authority
    claim, with the stable effect identity `findings:{head}:i{inc}`."""

    head: str
    base: str
    policy: str
    incarnation: int
    findings: list[dict[str, Any]]
    effect: str
    op: str
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class EmptyReview(WorkflowModel):
    """A round whose live findings all filtered out: nothing to post."""

    head: str
    incarnation: int
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewLanded(WorkflowModel):
    head: str
    incarnation: int
    findings: list[dict[str, Any]]
    effect: str
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewMoved(WorkflowModel):
    """The FULL authority the gate observed at effect time (grant +
    live) travels back so the fold can retain findings provisionally."""

    head: str
    observed: str
    observed_base: str
    observed_policy: str
    observed_incarnation: int
    observed_phase: Phase
    findings: list[dict[str, Any]]
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewBlocked(WorkflowModel):
    """Retryable exhaustion: the durable pub descriptor keeps the exact
    operation so the recovery door can reissue it (A2)."""

    head: str
    base: str
    policy: str
    incarnation: int
    findings: list[dict[str, Any]]
    effect: str
    op: str
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewFault(WorkflowModel):
    """Unknown provider terminal or effect-identity collision:
    fail-closed, surfaced for the human."""

    reason: str
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReviewEnded(WorkflowModel):
    """The review loop's terminal record at close."""

    reviewed: tuple[str, ...]
    pub_phase: str
    reason: str


# -- gate work and typed terminals (mutation) ---------------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MutWork(WorkflowModel):
    """The git gate's work token: one push under a FULL authority claim.

    `op_key` is the stable operation identity (`push:{rid}:{head}:i{inc}`,
    keyed by the producer's REQUEST identity, not the semantic op) for
    lookup-first reconciliation: a crash after the push landed but
    before acknowledgment must not push twice. The gate fences the head
    by server-side CAS and base/policy/grant by a fresh read (A1.5).
    `lineage` is the budget lineage the pushed head inherits when it is
    later confirmed — derived from the op, echoed by the gate.
    """

    op: str
    op_key: str
    head: str
    base: str
    policy: str
    incarnation: int
    lineage: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Pushed(WorkflowModel):
    """The push landed (or lookup-first found it already landed):
    `new_head` is the head the provider now reports for this operation."""

    op: str
    op_key: str
    head: str
    new_head: str
    incarnation: int
    lineage: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MovedM(WorkflowModel):
    """Authority moved under the push: CAS lost the head race, or the
    fresh read found a different base/policy/grant. The FULL observed
    authority travels back for the record."""

    op: str
    head: str
    incarnation: int
    observed: str
    observed_incarnation: int
    observed_phase: Phase


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class FaultM(WorkflowModel):
    """Unknown provider terminal: the push may or may not have landed.
    A2: retains the EXACT operation and the FULL authority claim so the
    recovery door can reissue the same operation identity."""

    op: str
    op_key: str
    head: str
    base: str
    policy: str
    reason: str
    incarnation: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MutEnded(WorkflowModel):
    """The mutation loop's terminal record at close."""

    state: str
    reason: str


# -- the conversation baton, gate work, and typed terminals -------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ConvMemory(WorkflowModel):
    """The conversation loop's baton — the loop NEVER ends.

    `served` records every classified comment identity: an edited or
    redelivered comment is answered once, ever. Replies are deliberately
    CONCURRENT, so custody is per-id data rather than a held baton:
    `pending` maps in-flight reply ids to their text, `blocked` retains
    the exact text of a retry-exhausted reply, and `faulted` retains
    text plus reason for an unknown provider terminal — both recover
    under the SAME effect identity `reply:{id}` (A2).
    """

    served: tuple[str, ...]
    pending: dict[str, str]
    blocked: dict[str, str]
    faulted: dict[str, dict[str, str]]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReplyReq(WorkflowModel):
    """One reply publication under the stable identity `reply:{id}`."""

    id: str
    text: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Replied(WorkflowModel):
    """The reply landed (or was lookup-first reconciled)."""

    id: str
    text: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReplyBlocked(WorkflowModel):
    """Retryable exhaustion: the reply text is retained for recovery."""

    id: str
    text: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReplyFault(WorkflowModel):
    """Unknown provider terminal: the reply may or may not be held.
    Retains the text so recovery reissues the SAME identity (A2)."""

    id: str
    text: str
    reason: str
