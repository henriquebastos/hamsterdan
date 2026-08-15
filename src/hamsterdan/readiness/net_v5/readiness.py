"""The readiness loop: the all-gates advisory projection and announce.

Owns the Snapshot baton — the sole readiness projection — and consumes
every sibling-mailed GateFact. It never merges; it announces exactly
once per incarnation on the not-ready -> ready edge, through an
authority-fenced gate under the stable identity `ready:{head}:i{n}`.
A stale state fact never rolls the projection back; a mismatched
incarnation is inert (A1.4); announce-once is recorded on
ACKNOWLEDGMENT, per the terminal's incarnation (A1.6).

The ready edge is a two-step decision: the fold that sees it emits a
REVOCABLE candidate, and a separate `authorize` fold — inhibited while
any sibling fact is still unfolded in `ready.facts` — re-derives the
whole decision from the caught-up snapshot before minting the announce
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
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    ABlocked,
    AFault,
    ALanded,
    AMoved,
    AnnounceCandidate,
    AnnounceReq,
    CloseFact,
    GateFact,
    ReadyEnded,
    RecoverFact,
    Snapshot,
)
from hamsterdan.readiness.net_v5.folding import revive, route, values

GATES = {"ready.gate": ("announce_gate", ("ALanded", "ABlocked", "AMoved", "AFault"))}

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

    Inhibited while `ready.facts` holds anything unfolded, so every
    fact mailed before this instant has already folded. The decision is
    re-derived whole — the candidate carries no authority worth
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
    )
    # A2: `announcing` retains the EXACT in-flight request
    held = snap.validated_update(announcing=req.dump())
    return route(outputs, {"ready.snap": (held,), "ready.announce_req": (req,)})


def _fault_key(body: dict) -> str:
    return f"{body.get('where', '')}:{body.get('op', '')}"


def _apply(snap: Snapshot, fact: GateFact) -> Snapshot | None:
    """Pure fact application: the next snapshot, or None when the fact
    is inert (stale, mismatched, or unknown) and must not reopen the
    announce decision."""
    kind, body = fact.kind, fact.body
    if kind == "state":
        if fact.incarnation < snap.incarnation:
            # a STALE state fact must never roll the projection back
            return None
        if fact.incarnation != snap.incarnation:
            # new authority: the per-incarnation gates reset; human
            # review state persists — approvals and unresolved threads
            # outlive a push until the provider says otherwise
            snap = snap.validated_update(
                incarnation=fact.incarnation,
                checks="pending",
                review="pending",
                findings_blocking=0,
                pending=(),
            )
        snap = snap.validated_update(
            phase=body["phase"],
            head=body["head"],
            base=body["base"],
            mergeable=body["mergeable"],
            policy=body["policy"],
        )
    elif fact.incarnation not in (0, snap.incarnation):
        return None  # A1.4: mismatched facts are inert
    elif kind == "checks":
        snap = snap.validated_update(checks=body["status"])
    elif kind == "review":
        snap = snap.validated_update(review=body["status"])
    elif kind == "findings":
        snap = snap.validated_update(findings_blocking=body["blocking"])
    elif kind == "human":
        snap = snap.validated_update(
            approval=body["approval"],
            changes_requested=body["changes_requested"],
            unresolved=body["unresolved"],
        )
    elif kind == "mutation_pending":
        # the pending gate is an identity ledger (op_key), never the
        # display op: a settlement must clear exactly ITS OWN round —
        # two "change" comments look identical by op (CV17.DS2.0)
        snap = snap.validated_update(pending=(*snap.pending, body["op_key"]))
    elif kind == "mutation_settled":
        snap = snap.validated_update(pending=tuple(k for k in snap.pending if k != body["op_key"]))
    elif kind == "fault":
        key = _fault_key(body)
        if body.get("status") in ("resolved", "cancelled"):
            # the owning loop settled or cancelled the retained
            # operation: readiness never stays fail-closed after the
            # recovery actually succeeded
            snap = snap.validated_update(faults={k: v for k, v in snap.faults.items() if k != key})
        else:
            snap = snap.validated_update(faults={**snap.faults, key: body.get("reason", "")})
    else:
        return None
    return snap


def _fold_fact(binding, outputs):
    fact, snap = values(binding, GateFact, Snapshot)
    applied = _apply(snap, fact)
    if applied is None:
        return route(outputs, {"ready.snap": (snap,)})
    return route(outputs, _announce_open(applied))


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


def _drain_fact(binding, outputs):
    # a sibling fact that lost the race with close (a post-close drain
    # settlement, a late resolution) is absorbed — never stranded
    _, ended = values(binding, GateFact, ReadyEnded)
    return route(outputs, {"ready.done": (ended,)})


def _drain_recover(binding, outputs):
    _, ended = values(binding, RecoverFact, ReadyEnded)
    return route(outputs, {"ready.done": (ended,)})


def _drain_candidate(binding, outputs):
    # a candidate that lost the race with close was never an effect
    # request — absorbed, never stranded
    _, ended = values(binding, AnnounceCandidate, ReadyEnded)
    return route(outputs, {"ready.done": (ended,)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    ready = s.ready
    ready.p.facts(GateFact)
    ready.p.closed(CloseFact)
    ready.p.recover(RecoverFact)
    ready.p.snap(Snapshot)
    ready.p.candidate(AnnounceCandidate)
    ready.p.announce_req(AnnounceReq)
    ready.p.alanded(ALanded)
    ready.p.ablocked(ABlocked)
    ready.p.amoved(AMoved)
    ready.p.afault(AFault)
    ready.p.done(ReadyEnded)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    ready, dash = net.s.ready, net.s.dash

    (
        (ready.p.facts, ready.p.snap)
        >> ready.t.fold(handler=petri_handler(_fold_fact))
        >> (
            ready.p.snap,
            ready.p.candidate,
        )
    )
    # candidate -> announcing, ONLY while the mailbox is quiet: the
    # inhibit arcs are loop-internal (readiness's own places), so every
    # fact mailed before this instant has folded into the snapshot the
    # authorization re-derives from — and a pending close wins outright
    (
        (ready.p.candidate, ready.p.snap)
        >> ready.t.authorize(handler=petri_handler(_authorize))
        >> (
            ready.p.snap,
            ready.p.announce_req,
        )
    )
    ready.p.facts >> arc.inhibit() >> ready.t.authorize
    ready.p.closed >> arc.inhibit() >> ready.t.authorize
    (
        ready.p.announce_req
        >> ready.t.gate(handler="announce_gate")
        >> (
            ready.p.alanded,
            ready.p.ablocked,
            ready.p.amoved,
            ready.p.afault,
        )
    )
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
    ((ready.p.facts, ready.p.done) >> ready.t.drain_fact(handler=petri_handler(_drain_fact)) >> ready.p.done)
    ((ready.p.recover, ready.p.done) >> ready.t.drain_recover(handler=petri_handler(_drain_recover)) >> ready.p.done)
    (
        (ready.p.candidate, ready.p.done)
        >> ready.t.drain_candidate(handler=petri_handler(_drain_candidate))
        >> ready.p.done
    )


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
        closing=None,
    )
    return {NetPath("ready.snap"): (Token("Snapshot", baton.dump()),)}
