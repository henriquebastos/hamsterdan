"""The readiness loop: the all-gates advisory projection and announce.

Owns the Snapshot baton — the sole readiness projection — and consumes
each sibling-mailed decision fact through its own typed mailbox. It
never merges; it announces exactly once per incarnation on the
not-ready -> ready edge, through an
authority-fenced gate under the stable identity `ready:{head}:i{n}`.
A stale state fact never rolls the projection back; a mismatched
incarnation is inert (A1.4); announce-once is recorded on
ACKNOWLEDGMENT, per the terminal's incarnation (A1.6).

The ready edge is a two-step decision: the fold that sees it emits a
REVOCABLE candidate, and a separate `authorize` fold — inhibited while
any typed sibling mailbox holds an unfolded fact — re-derives the whole
decision from the caught-up snapshot before minting the announce
request. A fact already mailed when the edge was seen (a queued
mutation's pending, a sibling's fault) therefore always folds first and
revokes a stale candidate; the announce request is never issued over an
unfolded mailbox.

Faults are a keyed ledger: a faulted sibling publication fail-closes
readiness until its owner mails an operation-keyed resolution. Blocked
announcements
recover through `ready.recover` under the SAME identity, lookup-first
at the gate; a faulted announcement is fail-closed by settled terminal
policy. Close defers while the gate is out (A3); post-close mail drains
into the terminal record so no token strands.
"""

from __future__ import annotations

from petrus.impetus.dsl import arc, petri_handler
from petrus.impetus.petrinet import Cel, NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    ABlocked,
    ADeferred,
    AFault,
    ALanded,
    AMoved,
    AnnounceCandidate,
    AnnounceReq,
    AWake,
    ChecksFact,
    CloseFact,
    FaultClearedFact,
    FaultRaisedFact,
    FindingsFact,
    GateFact,
    HumanFact,
    MutationPendingFact,
    MutationSettledFact,
    ReadyEnded,
    RecoverFact,
    ReviewFact,
    Snapshot,
    StateFact,
)
from hamsterdan.readiness.net_v5.folding import revive, route, values

GATES = {"ready.gate": ("announce_gate", ("ALanded", "ADeferred", "ABlocked", "AMoved", "AFault"))}

# -- folds ---------------------------------------------------------------


def _ready(snap: Snapshot) -> bool:
    return (
        snap.phase == "running"
        and snap.checks == "success"
        and snap.review == "clear"
        and snap.findings_blocking == 0
        and snap.approval
        and not snap.changes_requested
        and snap.unresolved == 0
        and snap.mergeable
        and (not snap.strict_base or snap.base_current)
        and not snap.pending
        and not snap.faults
    )


def _announce_viable(snap: Snapshot) -> bool:
    return (
        _ready(snap)
        and snap.incarnation not in snap.announced
        and not snap.announcing
        and not snap.blocked  # a blocked announce reopens only via recovery
        and snap.closing is None
    )


def _announce_open(snap: Snapshot) -> dict:
    """Re-evaluate the announce decision for the CURRENT snapshot (pure).

    Called after every fact fold AND after every announce terminal, so
    a new-authority readiness suppressed while an old announcement was
    in flight reopens the moment the old terminal settles (A2). Emits a
    REVOCABLE candidate, never the request itself: the authorize fold
    mints the request only from a caught-up snapshot."""
    if _announce_viable(snap) and not snap.candidate:
        held = snap.validated_update(candidate=True)
        sentinel = AnnounceCandidate(incarnation=snap.incarnation, head=snap.head)
        return {"ready.snap": (held,), "ready.candidate": (sentinel,)}
    return {"ready.snap": (snap,)}


def _authorize(binding, outputs):
    """Candidate -> announcing, from the CURRENT snapshot only.

    Inhibited while any typed fact mailbox holds anything unfolded, so
    every fact mailed before this instant has already folded. The
    decision is re-derived whole — the candidate carries no authority worth
    trusting; a snapshot a fact just invalidated simply drops it, and
    the next ready edge emits a fresh one."""
    _, snap = values(binding, AnnounceCandidate, Snapshot)
    snap = snap.validated_update(candidate=False)
    if not _announce_viable(snap):
        return route(outputs, {"ready.snap": (snap,)})
    req = AnnounceReq(
        op=f"ready:{snap.head}:i{snap.incarnation}",
        incarnation=snap.incarnation,
        head=snap.head,
        base=snap.base,
        policy=snap.policy,
        strict_base=snap.strict_base,
        base_current=snap.base_current,
    )
    # A2: `announcing` retains the EXACT in-flight request
    held = snap.validated_update(announcing=req.dump())
    return route(outputs, {"ready.snap": (held,), "ready.announce_req": (req,)})


def _current(snap: Snapshot, incarnation: int) -> bool:
    """A1.4: only global facts (incarnation 0) or current facts apply."""
    return incarnation in (0, snap.incarnation)


def _apply_state(snap: Snapshot, fact: StateFact) -> Snapshot | None:
    if fact.incarnation < snap.incarnation:
        # a STALE state fact must never roll the projection back
        return None
    if fact.incarnation != snap.incarnation:
        # new authority: the per-incarnation gates reset; human review
        # state persists — approvals and unresolved threads outlive a push
        snap = snap.validated_update(
            incarnation=fact.incarnation,
            checks="pending",
            review="pending",
            findings_blocking=0,
            pending=(),
        )
    body = fact.body
    return snap.validated_update(
        phase=body.phase,
        head=body.head,
        base=body.base,
        mergeable=body.mergeable,
        policy=body.policy,
        strict_base=body.strict_base,
        base_current=body.base_current,
    )


def _apply_checks(snap: Snapshot, fact: ChecksFact) -> Snapshot | None:
    return snap.validated_update(checks=fact.body.status) if _current(snap, fact.incarnation) else None


def _apply_review(snap: Snapshot, fact: ReviewFact) -> Snapshot | None:
    return snap.validated_update(review=fact.body.status) if _current(snap, fact.incarnation) else None


def _apply_findings(snap: Snapshot, fact: FindingsFact) -> Snapshot | None:
    return snap.validated_update(findings_blocking=fact.body.blocking) if _current(snap, fact.incarnation) else None


def _apply_human(snap: Snapshot, fact: HumanFact) -> Snapshot | None:
    if not _current(snap, fact.incarnation):
        return None
    return snap.validated_update(
        approval=fact.body.approval,
        changes_requested=fact.body.changes_requested,
        unresolved=fact.body.unresolved,
    )


def _apply_mutation_pending(snap: Snapshot, fact: MutationPendingFact) -> Snapshot | None:
    if not _current(snap, fact.incarnation):
        return None
    # the pending gate is an identity ledger (op_key), never the display
    # op: a settlement must clear exactly ITS OWN round (CV17.DS2.0)
    return snap.validated_update(pending=(*snap.pending, fact.body.op_key))


def _apply_mutation_settled(snap: Snapshot, fact: MutationSettledFact) -> Snapshot | None:
    if not _current(snap, fact.incarnation):
        return None
    return snap.validated_update(pending=tuple(key for key in snap.pending if key != fact.body.op_key))


def _apply_fault_raised(snap: Snapshot, fact: FaultRaisedFact) -> Snapshot:
    key = f"{fact.body.where}:{fact.body.op}"
    return snap.validated_update(faults={**snap.faults, key: fact.body.reason})


def _apply_fault_cleared(snap: Snapshot, fact: FaultClearedFact) -> Snapshot:
    key = f"{fact.body.where}:{fact.body.op}"
    return snap.validated_update(faults={name: reason for name, reason in snap.faults.items() if name != key})


def _fold_applied(snap: Snapshot, applied: Snapshot | None, outputs):
    if applied is None:
        return route(outputs, {"ready.snap": (snap,)})
    return route(outputs, _announce_open(applied))


def _fold_state(binding, outputs):
    fact, snap = values(binding, StateFact, Snapshot)
    return _fold_applied(snap, _apply_state(snap, fact), outputs)


def _fold_checks(binding, outputs):
    fact, snap = values(binding, ChecksFact, Snapshot)
    return _fold_applied(snap, _apply_checks(snap, fact), outputs)


def _fold_review(binding, outputs):
    fact, snap = values(binding, ReviewFact, Snapshot)
    return _fold_applied(snap, _apply_review(snap, fact), outputs)


def _fold_findings(binding, outputs):
    fact, snap = values(binding, FindingsFact, Snapshot)
    return _fold_applied(snap, _apply_findings(snap, fact), outputs)


def _fold_human(binding, outputs):
    fact, snap = values(binding, HumanFact, Snapshot)
    return _fold_applied(snap, _apply_human(snap, fact), outputs)


def _fold_mutation_pending(binding, outputs):
    fact, snap = values(binding, MutationPendingFact, Snapshot)
    return _fold_applied(snap, _apply_mutation_pending(snap, fact), outputs)


def _fold_mutation_settled(binding, outputs):
    fact, snap = values(binding, MutationSettledFact, Snapshot)
    return _fold_applied(snap, _apply_mutation_settled(snap, fact), outputs)


def _fold_fault_raised(binding, outputs):
    fact, snap = values(binding, FaultRaisedFact, Snapshot)
    return _fold_applied(snap, _apply_fault_raised(snap, fact), outputs)


def _fold_fault_cleared(binding, outputs):
    fact, snap = values(binding, FaultClearedFact, Snapshot)
    return _fold_applied(snap, _apply_fault_cleared(snap, fact), outputs)


def _migrate_legacy(binding, outputs, fact_type, mailbox: str):
    """Convert one pre-specialization envelope without deciding its kind."""
    (fact,) = values(binding, GateFact)
    return route(outputs, {mailbox: (revive(fact_type, fact.dump()),)})


def _migrate_state(binding, outputs):
    return _migrate_legacy(binding, outputs, StateFact, "ready.state_facts")


def _migrate_checks(binding, outputs):
    return _migrate_legacy(binding, outputs, ChecksFact, "ready.checks_facts")


def _migrate_review(binding, outputs):
    return _migrate_legacy(binding, outputs, ReviewFact, "ready.review_facts")


def _migrate_findings(binding, outputs):
    return _migrate_legacy(binding, outputs, FindingsFact, "ready.findings_facts")


def _migrate_human(binding, outputs):
    return _migrate_legacy(binding, outputs, HumanFact, "ready.human_facts")


def _migrate_mutation_pending(binding, outputs):
    return _migrate_legacy(binding, outputs, MutationPendingFact, "ready.mutation_pending_facts")


def _migrate_mutation_settled(binding, outputs):
    return _migrate_legacy(binding, outputs, MutationSettledFact, "ready.mutation_settled_facts")


def _migrate_fault_raised(binding, outputs):
    return _migrate_legacy(binding, outputs, FaultRaisedFact, "ready.fault_raised_facts")


def _migrate_fault_cleared(binding, outputs):
    return _migrate_legacy(binding, outputs, FaultClearedFact, "ready.fault_cleared_facts")


def _ended(snap: Snapshot) -> ReadyEnded:
    return ReadyEnded(announced=snap.announced, faults=snap.faults, reason=snap.closing or "")


def _settle(snap: Snapshot, outputs, extra: dict):
    """After an announce terminal folds: finish a deferred close (A3),
    otherwise re-evaluate the current snapshot."""
    if snap.closing is not None:
        return route(outputs, {**extra, "ready.done": (_ended(snap),)})
    return route(outputs, {**extra, **_announce_open(snap)})


def _fold_alanded(binding, outputs):
    out, snap = values(binding, ALanded, Snapshot)
    # A1.6: announce-once is recorded on ACKNOWLEDGMENT — per the
    # TERMINAL's incarnation, so a stale landing never marks the
    # current incarnation announced
    snap = snap.validated_update(announced=(*snap.announced, out.incarnation), announcing={})
    fact = GateFact(kind="announced", incarnation=out.incarnation, body={"head": out.head})
    return _settle(snap, outputs, {"dash.facts": (fact,)})


def _announce_request(value: ADeferred | AWake) -> AnnounceReq:
    return AnnounceReq(
        op=value.op,
        incarnation=value.incarnation,
        head=value.head,
        base=value.base,
        policy=value.policy,
        strict_base=value.strict_base,
        base_current=value.base_current,
    )


def _fold_adeferred(binding, outputs):
    out, snap = values(binding, ADeferred, Snapshot)
    if snap.announcing != _announce_request(out).dump():
        raise ValueError("V5 deferred announcement differs from its in-flight request")
    return route(outputs, {"ready.snap": (snap,), "ready.deferred": (out,)})


def _wake_deferred(binding, outputs):
    deferred, wake, snap = values(binding, ADeferred, AWake, Snapshot)
    if deferred.dump() != wake.dump() or snap.announcing != _announce_request(deferred).dump():
        raise ValueError("V5 announcement wake differs from its deferred request")
    # The inhibitors below make every already-mailed fact (and close)
    # fold before the wake. A revocation drops the request; an authority
    # refresh that stays ready must retry the EXACT retained request so
    # the gate first settles its old claim MOVED. Only that typed terminal
    # may open a fresh-authority request from the current snapshot.
    snap = snap.validated_update(announcing={})
    if not _announce_viable(snap):
        return _settle(snap, outputs, {})
    req = _announce_request(deferred)
    return route(
        outputs,
        {
            "ready.snap": (snap.validated_update(announcing=req.dump()),),
            "ready.announce_req": (req,),
        },
    )


def _fold_ablocked(binding, outputs):
    _, snap = values(binding, ABlocked, Snapshot)
    # custody moves from in-flight to blocked, retaining the EXACT request
    snap = snap.validated_update(announcing={}, blocked=snap.announcing)
    if snap.closing is not None:
        # A3: close was deferred while the gate was out; a closed PR has
        # no announcement to recover, so the retained request is dropped
        return route(outputs, {"ready.done": (_ended(snap),)})
    return route(outputs, {"ready.snap": (snap,)})


def _fold_amoved(binding, outputs):
    out, snap = values(binding, AMoved, Snapshot)
    snap = snap.validated_update(announcing={})
    if snap.closing is not None:
        return route(outputs, {"ready.done": (_ended(snap),)})
    observed = (out.observed_head, out.observed_base, out.observed_policy, out.observed_incarnation, out.observed_phase)
    current = (snap.head, snap.base, snap.policy, snap.incarnation, snap.phase)
    if current == observed:
        # the displacing observation ALREADY folded while the gate was
        # out: the snapshot speaks with the gate's FULL observed
        # authority — grant included — so re-evaluate now
        return route(outputs, _announce_open(snap))
    # the displacing observation has NOT folded yet: reissuing the same
    # request would be refused identically forever (livelock). Park;
    # the pending state fact reopens the decision when it folds.
    return route(outputs, {"ready.snap": (snap,)})


def _fold_afault(binding, outputs):
    out, snap = values(binding, AFault, Snapshot)
    # A2: fault retention keeps the exact operation identity and reason
    snap = snap.validated_update(announcing={}, faults={**snap.faults, f"announce:{out.op}": out.reason})
    fact = GateFact(
        kind="fault",
        incarnation=0,
        body={"where": "announce", "op": out.op, "status": "faulted", "reason": out.reason},
    )
    return _settle(snap, outputs, {"dash.facts": (fact,)})


def _recover(binding, outputs):
    fact, snap = values(binding, RecoverFact, Snapshot)
    if fact.target != "readiness" or not snap.blocked or fact.op != snap.blocked.get("op") or snap.closing is not None:
        # blocked-only by SETTLED TERMINAL POLICY: a faulted
        # announcement is not proven un-landed and is never reissued
        # by this door — retained with its reason for the human
        return route(outputs, {"ready.snap": (snap,)})
    # blocked -> announcing: one fresh occurrence, the SAME identity;
    # the gate reconciles lookup-first (A2)
    req = revive(AnnounceReq, snap.blocked)
    snap = snap.validated_update(announcing=snap.blocked, blocked={})
    return route(outputs, {"ready.snap": (snap,), "ready.announce_req": (req,)})


def _end(binding, outputs):
    close, snap = values(binding, CloseFact, Snapshot)
    snap = snap.validated_update(closing=close.reason)
    if snap.announcing:
        # A3: a terminal is outstanding — record the close INTENT and
        # let the terminal fold finalize, so the late terminal settles
        return route(outputs, {"ready.snap": (snap,)})
    return route(outputs, {"ready.done": (_ended(snap),)})


def _drain(binding, outputs, fact_type):
    # a sibling fact that lost the race with close (a post-close drain
    # settlement, a late resolution) is absorbed — never stranded
    _, ended = values(binding, fact_type, ReadyEnded)
    return route(outputs, {"ready.done": (ended,)})


def _drain_state(binding, outputs):
    return _drain(binding, outputs, StateFact)


def _drain_checks(binding, outputs):
    return _drain(binding, outputs, ChecksFact)


def _drain_review(binding, outputs):
    return _drain(binding, outputs, ReviewFact)


def _drain_findings(binding, outputs):
    return _drain(binding, outputs, FindingsFact)


def _drain_human(binding, outputs):
    return _drain(binding, outputs, HumanFact)


def _drain_mutation_pending(binding, outputs):
    return _drain(binding, outputs, MutationPendingFact)


def _drain_mutation_settled(binding, outputs):
    return _drain(binding, outputs, MutationSettledFact)


def _drain_fault_raised(binding, outputs):
    return _drain(binding, outputs, FaultRaisedFact)


def _drain_fault_cleared(binding, outputs):
    return _drain(binding, outputs, FaultClearedFact)


def _drain_recover(binding, outputs):
    _, ended = values(binding, RecoverFact, ReadyEnded)
    return route(outputs, {"ready.done": (ended,)})


def _drain_candidate(binding, outputs):
    # a candidate that lost the race with close was never an effect
    # request — absorbed, never stranded
    _, ended = values(binding, AnnounceCandidate, ReadyEnded)
    return route(outputs, {"ready.done": (ended,)})


def _drain_wake(binding, outputs):
    _, ended = values(binding, AWake, ReadyEnded)
    return route(outputs, {"ready.done": (ended,)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    ready = s.ready
    # Input-only compatibility place: interrupted histories created before
    # the typed-mailbox promotion may retain a token at this exact path.
    ready.p.facts(GateFact)
    ready.p.state_facts(StateFact)
    ready.p.checks_facts(ChecksFact)
    ready.p.review_facts(ReviewFact)
    ready.p.findings_facts(FindingsFact)
    ready.p.human_facts(HumanFact)
    ready.p.mutation_pending_facts(MutationPendingFact)
    ready.p.mutation_settled_facts(MutationSettledFact)
    ready.p.fault_raised_facts(FaultRaisedFact)
    ready.p.fault_cleared_facts(FaultClearedFact)
    ready.p.closed(CloseFact)
    ready.p.recover(RecoverFact)
    ready.p.wakes(AWake)
    ready.p.snap(Snapshot)
    ready.p.candidate(AnnounceCandidate)
    ready.p.announce_req(AnnounceReq)
    ready.p.alanded(ALanded)
    ready.p.adeferred(ADeferred)
    ready.p.deferred(ADeferred)
    ready.p.ablocked(ABlocked)
    ready.p.amoved(AMoved)
    ready.p.afault(AFault)
    ready.p.done(ReadyEnded)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    ready, dash = net.s.ready, net.s.dash
    net.t.on_announce_wake >> ready.p.wakes

    # Pre-promotion GateFacts are a real same-type routing problem. Filtered
    # migration branches preserve crash-cut replay while every new producer
    # writes only the specialized places below.
    legacy_state = Cel('kind == "state"')
    legacy_fault_cleared = Cel(
        'kind == "fault" && has(body.status) && (body.status == "resolved" || body.status == "cancelled")'
    )
    (
        ready.p.facts
        >> arc(filter=legacy_state)
        >> ready.t.migrate_state(handler=petri_handler(_migrate_state))
        >> ready.p.state_facts
    )
    (
        ready.p.facts
        >> arc(filter=Cel('kind == "checks"'))
        >> ready.t.migrate_checks(handler=petri_handler(_migrate_checks))
        >> ready.p.checks_facts
    )
    (
        ready.p.facts
        >> arc(filter=Cel('kind == "review"'))
        >> ready.t.migrate_review(handler=petri_handler(_migrate_review))
        >> ready.p.review_facts
    )
    (
        ready.p.facts
        >> arc(filter=Cel('kind == "findings"'))
        >> ready.t.migrate_findings(handler=petri_handler(_migrate_findings))
        >> ready.p.findings_facts
    )
    (
        ready.p.facts
        >> arc(filter=Cel('kind == "human"'))
        >> ready.t.migrate_human(handler=petri_handler(_migrate_human))
        >> ready.p.human_facts
    )
    (
        ready.p.facts
        >> arc(filter=Cel('kind == "mutation_pending"'))
        >> ready.t.migrate_mutation_pending(handler=petri_handler(_migrate_mutation_pending))
        >> ready.p.mutation_pending_facts
    )
    (
        ready.p.facts
        >> arc(filter=Cel('kind == "mutation_settled"'))
        >> ready.t.migrate_mutation_settled(handler=petri_handler(_migrate_mutation_settled))
        >> ready.p.mutation_settled_facts
    )
    (
        ready.p.facts
        >> arc(filter=Cel('kind == "fault" && (!has(body.status) || body.status == "faulted")'))
        >> ready.t.migrate_fault_raised(handler=petri_handler(_migrate_fault_raised))
        >> ready.p.fault_raised_facts
    )
    (
        ready.p.facts
        >> arc(filter=legacy_fault_cleared)
        >> ready.t.migrate_fault_cleared(handler=petri_handler(_migrate_fault_cleared))
        >> ready.p.fault_cleared_facts
    )
    for migration in (
        ready.t.migrate_checks,
        ready.t.migrate_review,
        ready.t.migrate_findings,
        ready.t.migrate_human,
        ready.t.migrate_mutation_pending,
        ready.t.migrate_mutation_settled,
    ):
        ready.p.facts >> arc.inhibit(filter=legacy_state) >> migration
    ready.p.facts >> arc.inhibit(filter=Cel('kind == "mutation_pending"')) >> ready.t.migrate_mutation_settled
    ready.p.facts >> arc.inhibit(filter=legacy_fault_cleared) >> ready.t.migrate_fault_raised
    (
        (ready.p.state_facts, ready.p.snap)
        >> ready.t.fold_state(handler=petri_handler(_fold_state))
        >> (ready.p.snap, ready.p.candidate)
    )
    (
        (ready.p.checks_facts, ready.p.snap)
        >> ready.t.fold_checks(handler=petri_handler(_fold_checks))
        >> (ready.p.snap, ready.p.candidate)
    )
    (
        (ready.p.review_facts, ready.p.snap)
        >> ready.t.fold_review(handler=petri_handler(_fold_review))
        >> (ready.p.snap, ready.p.candidate)
    )
    (
        (ready.p.findings_facts, ready.p.snap)
        >> ready.t.fold_findings(handler=petri_handler(_fold_findings))
        >> (ready.p.snap, ready.p.candidate)
    )
    (
        (ready.p.human_facts, ready.p.snap)
        >> ready.t.fold_human(handler=petri_handler(_fold_human))
        >> (ready.p.snap, ready.p.candidate)
    )
    (
        (ready.p.mutation_pending_facts, ready.p.snap)
        >> ready.t.fold_mutation_pending(handler=petri_handler(_fold_mutation_pending))
        >> (ready.p.snap, ready.p.candidate)
    )
    (
        (ready.p.mutation_settled_facts, ready.p.snap)
        >> ready.t.fold_mutation_settled(handler=petri_handler(_fold_mutation_settled))
        >> (ready.p.snap, ready.p.candidate)
    )
    (
        (ready.p.fault_raised_facts, ready.p.snap)
        >> ready.t.fold_fault_raised(handler=petri_handler(_fold_fault_raised))
        >> (ready.p.snap, ready.p.candidate)
    )
    (
        (ready.p.fault_cleared_facts, ready.p.snap)
        >> ready.t.fold_fault_cleared(handler=petri_handler(_fold_fault_cleared))
        >> (ready.p.snap, ready.p.candidate)
    )
    # Authority facts fold before incarnation-scoped evidence. The former
    # shared FIFO guaranteed this ordering implicitly; the typed topology
    # makes it explicit so a new head cannot make already-mailed checks,
    # review, findings, human, or mutation evidence look mismatched.
    incarnation_folds = (
        ready.t.fold_checks,
        ready.t.fold_review,
        ready.t.fold_findings,
        ready.t.fold_human,
        ready.t.fold_mutation_pending,
        ready.t.fold_mutation_settled,
    )
    for fold in incarnation_folds:
        ready.p.state_facts >> arc.inhibit() >> fold
    # Splitting the former FIFO must not erase producer causality. A pending
    # identity exists before its settlement, and a recovery resolution exists
    # before that same reopened operation can fault again in one drive.
    ready.p.mutation_pending_facts >> arc.inhibit() >> ready.t.fold_mutation_settled
    ready.p.fault_cleared_facts >> arc.inhibit() >> ready.t.fold_fault_raised
    # candidate -> announcing, ONLY while every mailbox is quiet: the
    # inhibit arcs are loop-internal (readiness's own places), so each
    # fact mailed before this instant has folded into the snapshot that
    # authorization re-derives from — and a pending close wins outright
    (
        (ready.p.candidate, ready.p.snap)
        >> ready.t.authorize(handler=petri_handler(_authorize))
        >> (
            ready.p.snap,
            ready.p.announce_req,
        )
    )
    fact_mailboxes = (
        ready.p.facts,
        ready.p.state_facts,
        ready.p.checks_facts,
        ready.p.review_facts,
        ready.p.findings_facts,
        ready.p.human_facts,
        ready.p.mutation_pending_facts,
        ready.p.mutation_settled_facts,
        ready.p.fault_raised_facts,
        ready.p.fault_cleared_facts,
    )
    for mailbox in fact_mailboxes:
        mailbox >> arc.inhibit() >> ready.t.authorize
    ready.p.closed >> arc.inhibit() >> ready.t.authorize
    (
        ready.p.announce_req
        >> ready.t.gate(handler="announce_gate")
        >> (
            ready.p.alanded,
            ready.p.adeferred,
            ready.p.ablocked,
            ready.p.amoved,
            ready.p.afault,
        )
    )
    (
        (ready.p.adeferred, ready.p.snap)
        >> ready.t.fold_adeferred(handler=petri_handler(_fold_adeferred))
        >> (ready.p.deferred, ready.p.snap)
    )
    (
        (ready.p.deferred, ready.p.wakes, ready.p.snap)
        >> ready.t.wake_deferred(handler=petri_handler(_wake_deferred))
        >> (
            ready.p.snap,
            ready.p.done,
            ready.p.announce_req,
        )
    )
    for mailbox in fact_mailboxes:
        mailbox >> arc.inhibit() >> ready.t.wake_deferred
    ready.p.closed >> arc.inhibit() >> ready.t.wake_deferred
    (
        (ready.p.alanded, ready.p.snap)
        >> ready.t.fold_alanded(handler=petri_handler(_fold_alanded))
        >> (
            ready.p.snap,
            dash.p.facts,
            ready.p.done,
            ready.p.candidate,
        )
    )
    (
        (ready.p.ablocked, ready.p.snap)
        >> ready.t.fold_ablocked(handler=petri_handler(_fold_ablocked))
        >> (
            ready.p.snap,
            ready.p.done,
        )
    )
    (
        (ready.p.amoved, ready.p.snap)
        >> ready.t.fold_amoved(handler=petri_handler(_fold_amoved))
        >> (
            ready.p.snap,
            ready.p.done,
            ready.p.candidate,
        )
    )
    (
        (ready.p.afault, ready.p.snap)
        >> ready.t.fold_afault(handler=petri_handler(_fold_afault))
        >> (
            ready.p.snap,
            dash.p.facts,
            ready.p.done,
            ready.p.candidate,  # unreachable while the fault holds, but
        )  # structurally honest: _settle may route a candidate
    )
    # the exact-recovery door (A2): a blocked announcement reissues
    # under the SAME identity; the gate reconciles lookup-first
    (
        (ready.p.recover, ready.p.snap)
        >> ready.t.recovery(handler=petri_handler(_recover))
        >> (
            ready.p.snap,
            ready.p.announce_req,
        )
    )
    ((ready.p.closed, ready.p.snap) >> ready.t.end(handler=petri_handler(_end)) >> (ready.p.snap, ready.p.done))
    # post-close drains: mail that lost the race with close is absorbed
    # by the retired loop's persistent done record, never stranded
    ((ready.p.state_facts, ready.p.done) >> ready.t.drain_state(handler=petri_handler(_drain_state)) >> ready.p.done)
    ((ready.p.checks_facts, ready.p.done) >> ready.t.drain_checks(handler=petri_handler(_drain_checks)) >> ready.p.done)
    ((ready.p.review_facts, ready.p.done) >> ready.t.drain_review(handler=petri_handler(_drain_review)) >> ready.p.done)
    (
        (ready.p.findings_facts, ready.p.done)
        >> ready.t.drain_findings(handler=petri_handler(_drain_findings))
        >> ready.p.done
    )
    ((ready.p.human_facts, ready.p.done) >> ready.t.drain_human(handler=petri_handler(_drain_human)) >> ready.p.done)
    (
        (ready.p.mutation_pending_facts, ready.p.done)
        >> ready.t.drain_mutation_pending(handler=petri_handler(_drain_mutation_pending))
        >> ready.p.done
    )
    (
        (ready.p.mutation_settled_facts, ready.p.done)
        >> ready.t.drain_mutation_settled(handler=petri_handler(_drain_mutation_settled))
        >> ready.p.done
    )
    (
        (ready.p.fault_raised_facts, ready.p.done)
        >> ready.t.drain_fault_raised(handler=petri_handler(_drain_fault_raised))
        >> ready.p.done
    )
    (
        (ready.p.fault_cleared_facts, ready.p.done)
        >> ready.t.drain_fault_cleared(handler=petri_handler(_drain_fault_cleared))
        >> ready.p.done
    )
    ((ready.p.recover, ready.p.done) >> ready.t.drain_recover(handler=petri_handler(_drain_recover)) >> ready.p.done)
    (
        (ready.p.candidate, ready.p.done)
        >> ready.t.drain_candidate(handler=petri_handler(_drain_candidate))
        >> ready.p.done
    )
    ((ready.p.wakes, ready.p.done) >> ready.t.drain_wake(handler=petri_handler(_drain_wake)) >> ready.p.done)


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = Snapshot(
        incarnation=0,
        phase="",
        head="",
        base="",
        policy="",
        mergeable=False,
        checks="pending",
        review="pending",
        findings_blocking=0,
        approval=False,
        changes_requested=False,
        unresolved=0,
        pending=(),
        faults={},
        announced=(),
        candidate=False,
        announcing={},
        blocked={},
        strict_base=True,
        base_current=False,
        closing=None,
    )
    return {NetPath("ready.snap"): (Token("Snapshot", baton.dump()),)}
