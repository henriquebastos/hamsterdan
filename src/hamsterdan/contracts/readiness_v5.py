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
ReviewStatus = Literal["pending", "clear", "blocking", "unable"]
ReviewUnableCategory = Literal[
    "runtime_lifecycle",
    "output_schema",
    "correlation",
    "unchanged",
    "unable",
    "workspace_reconciliation",
    "canceled",
    "timed_out",
    "cleanup_unverified",
    "protocol",
]


# -- ingress observations (host-normalized) --------------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HeadSeen(WorkflowModel):
    head: str
    base: str
    mergeable: bool
    policy: str
    # Defaults keep pre-DS4 durable tokens readable but fail closed until
    # the host refreshes them with explicit base-policy evidence.
    strict_base: bool = True
    base_current: bool = False


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
class ReminderTimer(WorkflowModel):
    """One actor-owned reminder generation."""

    id: str
    incarnation: int
    sequence: int
    head: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class TimerDue(WorkflowModel):
    """An identified host maturity for one exact timer generation."""

    timer: ReminderTimer
    due_at: str
    matured_at: str


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
    reminder_delay_s: int
    strict_base: bool = True
    base_current: bool = False


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

    `subject` is the host-supplied globally unique workflow identity;
    the loop combines it with the head and incarnation to mint a
    settleable Agenticus operation. `head`, `incarnation`, and `status`
    scope later dismissals to the exact review whose findings they
    recount and prevent a dismissal from reopening an unable round.
    `reviewed` accumulates every head that completed an agent round,
    recorded at judge time (never at settlement), membership-unique.
    `provisional` retains findings whose publication MOVED — they
    republish under the next refreshed authority (or feed the next
    agent round) instead of being lost. An open publication takes
    EXCLUSIVE custody: provisional is empty while a pending, blocked,
    or faulted descriptor holds the attempted content. `findings` is
    the full validated current open set from the last successful agent
    round; `lineage` is that round's finding lineage.
    `dismissed` holds finding ids the human waved off; they never
    republish — a dismissal touching a retained blocked/faulted
    operation CANCELS it (recovery goes inert; the descriptor stays
    for audit). Dismissal-filtered publication content stays in the
    publication token/descriptor rather than weakening the retained
    agent evidence. `pub` is the publication descriptor: `{"phase":
    "idle"}` or a durable pending/blocked/faulted/cancelled record
    retaining the operation identity (A2) so recovery can reissue the
    SAME effect.
    """

    subject: str
    head: str
    incarnation: int
    status: ReviewStatus
    reviewed: tuple[str, ...]
    provisional: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    lineage: tuple[dict[str, Any], ...]
    dismissed: tuple[str, ...]
    pub: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MutState(WorkflowModel):
    """The mutation loop's baton: the serialization IS the baton.

    While a push round is in flight the baton is HELD (no token in the
    place), so a second request waits visibly in the mailbox — one
    mutation at a time by construction. `idle` carries empty retention
    fields; `faulted` retains the EXACT operation identity, the FULL
    attempted authority claim, and the change payload (kind,
    instruction, CI evidence identity) so the recovery door can reissue
    the same operation byte-for-byte (A2), and declines every further
    request fail-closed.
    """

    state: Literal["idle", "faulted"]
    op_key: str
    op: str
    head: str
    base: str
    policy: str
    incarnation: int
    reason: str
    kind: str
    instruction: str
    run_id: int
    attempt: int


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

    CV17.DS2.0: the request carries the CHANGE itself, credential-free —
    `kind` names the coding request, `instruction` is the human's text
    for conversation ops ("" otherwise), and `run_id`/`attempt` carry
    the indicting evidence identity for repairs ((0, 0) otherwise) — so
    the real git gate (coding agent + CAS push as one classified
    activity) needs no state outside History.
    """

    op: str
    rid: str
    head: str
    base: str
    policy: str
    incarnation: int
    source: str
    kind: Literal["repair", "change", "update_base", "resolve_conflict"]
    instruction: str
    run_id: int
    attempt: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class MutationSettled(WorkflowModel):
    """Mutation -> escalation: a repair push settled.
    `fingerprint` is the composite budget key. `op_key` is the round's
    stable operation identity: consumers that clear a pending round
    match on it, never on the semantic `op` — two "change" comments
    look identical by op (CV17.DS2.0)."""

    op: str
    op_key: str
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
    """Conversation -> reminders: a human snoozed or resumed (`clear`)."""

    mode: Literal["snooze", "clear"]
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

    operation: str
    head: str
    base: str
    policy: str
    incarnation: int
    prior_findings: list[dict[str, Any]]
    prior_lineage: list[dict[str, Any]]
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class AgentReview(WorkflowModel):
    """The agent gate's output: raw findings for one head, unjudged."""

    head: str
    base: str
    policy: str
    incarnation: int
    findings: list[dict[str, Any]]
    lineage: list[dict[str, Any]]
    mem: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RoundUnable(WorkflowModel):
    """A clean, classified inability to complete one agent round."""

    head: str
    incarnation: int
    category: ReviewUnableCategory
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

    CV17.DS2.0: `kind`, `instruction`, and `run_id`/`attempt` carry the
    credential-free change payload (see MutationRequest) so the real
    gate can reconstruct the coding request from the token alone.
    """

    op: str
    op_key: str
    head: str
    base: str
    policy: str
    incarnation: int
    lineage: str
    kind: str
    instruction: str
    run_id: int
    attempt: int


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
    op_key: str
    head: str
    incarnation: int
    observed: str
    observed_base: str
    observed_policy: str
    observed_incarnation: int
    observed_phase: Phase


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class FaultM(WorkflowModel):
    """Unknown provider terminal: the push may or may not have landed.
    A2: retains the EXACT operation, the FULL authority claim, and the
    change payload so the recovery door can reissue the same operation
    identity with the same content."""

    op: str
    op_key: str
    head: str
    base: str
    policy: str
    reason: str
    incarnation: int
    kind: str
    instruction: str
    run_id: int
    attempt: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DeclinedM(WorkflowModel):
    """The round produced no push and the branch state is fully known:
    the coding agent investigated and declined (unable, unchanged, or a
    malformed result). Not a fault — the baton returns idle — and not a
    move — authority stood. Settles `declined`, which the escalation
    ladder already consumes as a known rung terminal (CV17.DS2.0)."""

    op: str
    op_key: str
    head: str
    incarnation: int
    category: str
    reason: str


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


# -- the dashboard baton, gate work, and typed terminals ----------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashMemory(WorkflowModel):
    """The dashboard loop's baton — a mutable singleton projection.

    `entries` is the accumulated projection log and `digest` the newest
    fact's identity: the board republishes on digest drift ONLY. The
    board tracks the DESIRED state (entries + digest, the dedup key)
    and the LANDED digest (what the board actually shows) separately —
    the self-heal decision compares the FULL desired snapshot against
    what landed, never the digest alone: a cyclic drift (A→B→A) returns
    to the retained digest with MORE entries. Custody is a held baton:
    memory leaves the place while an upsert is in flight, so publication is
    single-flight by construction. `blocked` retains the exact
    retry-exhausted request and `faulted` the exact request plus reason
    (A2) — both recover through the `dash.recover` door under the SAME
    digest identity, while `entries`/`digest` keep tracking the evolving
    desired state fail-closed.
    """

    entries: tuple[str, ...]
    digest: str
    landed: str
    blocked: dict[str, Any]
    faulted: dict[str, Any]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashReq(WorkflowModel):
    """One dashboard upsert: the EXACT effect to execute (a recovery
    reissues a retained request verbatim) plus the DESIRED state the
    loop wants on the board. For a live publish they coincide; for a
    recovery reissue the desired state may have drifted while the fault
    was held, and the landed fold self-heals the drift."""

    entries: list[str]
    digest: str
    desired_entries: list[str]
    desired_digest: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashLanded(WorkflowModel):
    """The upsert landed: the board shows `digest` (idempotent overwrite)."""

    entries: list[str]
    digest: str
    desired_entries: list[str]
    desired_digest: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashBlocked(WorkflowModel):
    """Retryable exhaustion: the exact request is retained for recovery."""

    entries: list[str]
    digest: str
    desired_entries: list[str]
    desired_digest: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashFault(WorkflowModel):
    """Unknown provider terminal: the upsert may or may not be shown.
    Retains the exact effect (entries + digest) and reason (A2)."""

    entries: list[str]
    digest: str
    desired_entries: list[str]
    desired_digest: str
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashHeal(WorkflowModel):
    """A poke from the landed fold to the self-heal transition: the board
    landed an exact-but-drifted recovery request. Carries the full
    desired snapshot the poke was minted for — the digest alone cannot
    detect a cyclic drift that returned to the retained digest (A→B→A)
    with more entries. The transition consumes the memory baton, so the
    reissue cycle stays baton-serialized."""

    entries: tuple[str, ...]
    digest: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DashEnded(WorkflowModel):
    """The dashboard loop's terminal record at close."""

    entries: tuple[str, ...]
    reason: str


# -- the reminders baton, gate work, and typed terminals ----------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReminderCycleStarted(WorkflowModel):
    incarnation: int
    head: str
    delay_s: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReminderCyclePaused(WorkflowModel):
    incarnation: int
    head: str
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class NoReminderClock(WorkflowModel):
    kind: Literal["none"]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ArmingReminderClock(WorkflowModel):
    kind: Literal["arming"]
    timer: ReminderTimer
    operation: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ArmedReminderClock(WorkflowModel):
    kind: Literal["armed"]
    timer: ReminderTimer
    due_at: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CancellingReminderClock(WorkflowModel):
    kind: Literal["cancelling"]
    timer: ReminderTimer
    operation: str
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class OverdueReminderClock(WorkflowModel):
    kind: Literal["overdue"]
    timer: ReminderTimer
    due_at: str
    matured_at: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ArmReminder(WorkflowModel):
    kind: Literal["arm"]
    timer: ReminderTimer
    delay_s: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CancelReminder(WorkflowModel):
    kind: Literal["cancel"]
    timer: ReminderTimer
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class TimerCommand(WorkflowModel):
    operation: str
    command: ArmReminder | CancelReminder


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class TimerArmed(WorkflowModel):
    kind: Literal["armed"]
    timer: ReminderTimer
    due_at: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class TimerCancelled(WorkflowModel):
    kind: Literal["cancelled"]
    timer: ReminderTimer


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class TimerCommandApplied(WorkflowModel):
    operation: str
    result: TimerArmed | TimerCancelled


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RemState(WorkflowModel):
    """The reminders loop's baton.

    `clock` and `desired_timer` form a serialized Net↔host timer
    protocol: lifecycle changes may alter intent while one persistent
    command is awaiting acknowledgement, but never create a second
    outstanding command. `matured` records every delivered maturity;
    stale generations are facts but cannot trigger a nudge.
    """

    subject: str
    lifecycle_incarnation: int
    lifecycle_head: str
    lifecycle_active: bool
    desired_timer: ReminderTimer | None
    clock: NoReminderClock | ArmingReminderClock | ArmedReminderClock | CancellingReminderClock | OverdueReminderClock
    command_generation: int
    delay_s: int
    matured: tuple[str, ...]
    snoozed: bool
    pending: dict[str, Any]
    blocked: dict[str, Any]
    faulted: dict[str, Any]
    closing: str | None = None


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RemReq(WorkflowModel):
    """One nudge for the reminder gate; `reminder:{timer_id}` is the
    stable effect identity the gate reconciles lookup-first (A2)."""

    timer_id: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RemLanded(WorkflowModel):
    """The nudge landed (or lookup-first found it already posted)."""

    timer_id: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RemBlocked(WorkflowModel):
    """Bounded classified retry exhausted; the timer is retained for
    the `rem.recover` door under the SAME effect identity."""

    timer_id: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RemFault(WorkflowModel):
    """Unknown provider terminal: the nudge is NOT PROVEN landed. The
    timer and reason are retained fail-closed (A2); maturity alone
    never reopens a faulted timer."""

    timer_id: str
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RemEnded(WorkflowModel):
    """The reminders loop's terminal record at close."""

    matured: tuple[str, ...]
    reason: str


# -- readiness loop ---------------------------------------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Snapshot(WorkflowModel):
    """The readiness loop's baton: the sole gate projection.

    Folds sibling GateFacts into one all-gates snapshot. A stale state
    fact never rolls the projection back; a new incarnation resets the
    per-incarnation gates (checks, agent-review status, blocking
    findings, pending mutations) while human review state persists —
    provider approvals and unresolved threads outlive a push. `faults`
    is a keyed ledger
    (`{where}:{op}` -> reason): a faulted publication fail-closes
    readiness until its owner mails an operation-keyed resolution.
    Custody is A2 data: `candidate` marks a revocable ready-edge
    observation awaiting authorization, `announcing` retains the EXACT
    in-flight announce request, `blocked` a retry-exhausted one for the
    `ready.recover` door; announce-once is recorded per incarnation in
    `announced` on ACKNOWLEDGMENT, never on issuance (A1.6). `closing`
    retains a deferred close reason while a terminal is outstanding
    (A3); the sentinel is None — an EMPTY close reason is still a
    close.
    """

    incarnation: int
    phase: str
    head: str
    base: str
    policy: str
    mergeable: bool
    checks: str
    review: ReviewStatus
    findings_blocking: int
    approval: bool
    changes_requested: bool
    unresolved: int
    pending: tuple[str, ...]
    faults: dict[str, Any]
    announced: tuple[int, ...]
    candidate: bool
    announcing: dict[str, Any]
    blocked: dict[str, Any]
    strict_base: bool = True
    base_current: bool = False
    closing: str | None = None


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class AnnounceCandidate(WorkflowModel):
    """A revocable ready-edge observation — NOT an effect request.

    The fold that sees the not-ready -> ready edge emits this sentinel;
    a separate authorization step re-derives the WHOLE decision from
    the snapshot as it stands at authorization time and is inhibited
    while any sibling fact is still unfolded in `ready.facts`. A fact
    already mailed when the edge was seen therefore always folds first
    and revokes a stale candidate — the announce request itself is only
    ever minted from a fully caught-up snapshot."""

    incarnation: int
    head: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class AnnounceReq(WorkflowModel):
    """One readiness announcement for the announce gate.

    `ready:{head}:i{incarnation}` is the stable effect identity the
    gate reconciles lookup-first (A2); the gate fences EVERY claimed
    authority field — the live provider fields AND the host grant
    (A1.5) — because a draft-resume leaves head/base/policy identical
    and only the grant incarnation exposes the stale announce."""

    op: str
    incarnation: int
    head: str
    base: str
    policy: str
    # Missing evidence identifies a pre-DS4 request. It remains readable
    # but cannot publish unless lookup-first proves it already landed.
    strict_base: bool = True
    base_current: bool = False


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ALanded(WorkflowModel):
    """The announcement landed (or lookup-first found it already
    posted). Carries the TERMINAL's incarnation so a stale landing
    never marks the current incarnation announced (A1.6)."""

    incarnation: int
    head: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ABlocked(WorkflowModel):
    """Bounded classified retry exhausted; the exact request is
    retained for the `ready.recover` door under the SAME identity."""

    incarnation: int
    head: str
    base: str
    policy: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class AMoved(WorkflowModel):
    """Authority moved under the announce: the gate refused the post
    and reports the COMPLETE observed authority — live provider fields
    plus the host grant — so the fold can re-evaluate (the displacing
    observation already folded) or park (it has not; reissuing the
    identical request would be refused forever)."""

    incarnation: int
    observed_head: str
    observed_base: str
    observed_policy: str
    observed_incarnation: int
    observed_phase: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class AFault(WorkflowModel):
    """Unknown provider terminal: the announcement is NOT PROVEN
    landed. The operation and reason are retained fail-closed (A2);
    settled terminal policy — never reissued by the recovery door."""

    op: str
    incarnation: int
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReadyEnded(WorkflowModel):
    """The readiness loop's terminal record at close."""

    announced: tuple[int, ...]
    faults: dict[str, Any]
    reason: str
