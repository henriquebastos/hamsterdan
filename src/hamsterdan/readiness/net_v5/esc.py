"""The escalation loop: the ladder — rerun once, then repair once, per
fingerprint PER LINEAGE, then surface for the human.

Owns the Ladder baton. A rerun round HOLDS the baton: `decide` consumes
it into the RerunReq's `mem` and the terminal folds recreate it, so no
second decision can race an in-flight rerun. Moved burns no budget and
echoes a recheck to CI (the failure may still stand under the fresh
authority). A faulted rerun is FAIL-CLOSED: an unproven rung never
authorizes the next (mutating!) rung; the recovery door reissues the
EXACT retained request (A2) and lookup-first reconciles.
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    ChecksFailure,
    CloseFact,
    EscMoved,
    GateFact,
    Ladder,
    LadderEnded,
    MutationRequest,
    MutationSettled,
    RecoverFact,
    RerunFault,
    RerunLanded,
    RerunMoved,
    RerunReq,
)
from hamsterdan.readiness.net_v5.folding import revive, route, values

GATES = {"esc.rerun_gate": ("rerun_gate", ("RerunLanded", "RerunMoved", "RerunFault"))}

# -- folds ---------------------------------------------------------------


def _decide(binding, outputs):
    failure, ladder = values(binding, ChecksFailure, Ladder)
    if ladder.closing is not None:
        # no new rung after close: late evidence is absorbed
        return route(outputs, {"esc.ladder": (ladder,)})
    fp = failure.fingerprint
    key = f"{failure.lineage}:{fp}"
    evidence = (failure.run_id, failure.attempt)
    rung = ladder.reruns.get(key)  # None | {"state": "done", evidence}
    # | {"state": "fault"} (in-flight reruns hold the ladder baton, so
    # decide cannot race one)
    if rung is None:
        # the ladder is HELD through the rerun round (folds recreate it)
        req = RerunReq(
            fingerprint=key,
            fp=fp,
            op=f"rerun:{key}",
            head=failure.head,
            base=failure.base,
            policy=failure.policy,
            incarnation=failure.incarnation,
            run_id=failure.run_id,
            attempt=failure.attempt,
            mem=ladder.dump(),
        )
        return route(outputs, {"esc.rerun_req": (req,)})
    if rung["state"] == "fault":
        # FAIL-CLOSED: the rerun's terminal is unknown — the provider may
        # or may not hold it. An unproven rung must never authorize the
        # next (mutating!) rung. Surface for the human; the esc.recover
        # door reissues the SAME operation, and lookup-first reconciles.
        # The newest blocked failure is RETAINED on the fault so recovery
        # can replay it — evidence consumed here must not be lost.
        held = ladder.rerun_faults[key]
        blocked = held.get("blocked")
        if blocked is None or evidence > (blocked["run_id"], blocked["attempt"]):
            retained = {**held, "blocked": failure.dump()}
            ladder = ladder.validated_update(rerun_faults={**ladder.rerun_faults, key: retained})
        fact = GateFact(
            kind="human_needed",
            incarnation=failure.incarnation,
            body={"fingerprint": fp, "head": failure.head, "why": "rerun-fault"},
        )
        return route(outputs, {"esc.ladder": (ladder,), "dash.facts": (fact,)})
    if evidence <= (rung["run_id"], rung["attempt"]):
        # the rerun rung already answered this evidence: a duplicate
        # mail (assess and a moved-echo reissue can race) is the SAME
        # observation, never proof the rerun failed — absorb it
        return route(outputs, {"esc.ladder": (ladder,)})
    entry = ladder.repairs.get(key)
    if entry is None:
        # the pending entry retains the raw fp, ATTEMPTED authority, and
        # evidence so a moved settle can echo a recheck to CI
        # (order-independence) and later mails can be deduplicated
        pending = {
            "state": "pending",
            "fp": fp,
            "head": failure.head,
            "base": failure.base,
            "policy": failure.policy,
            "incarnation": failure.incarnation,
            "run_id": failure.run_id,
            "attempt": failure.attempt,
        }
        held = ladder.validated_update(repairs={**ladder.repairs, key: pending})
        req = MutationRequest(
            op=f"repair:{key}",
            rid=f"repair:{key}",  # the rung key IS the request identity
            head=failure.head,
            base=failure.base,
            policy=failure.policy,
            incarnation=failure.incarnation,
            source="escalation",
        )
        return route(outputs, {"esc.ladder": (held,), "mut.requests": (req,)})
    if entry["state"] == "pending":
        # a repair for this rung is ALREADY out: wait, don't escalate.
        # The repair's settle decides the next move; a duplicate failure
        # observation while it is in flight is evidence of the same
        # breakage, not grounds for a second push or a human page.
        return route(outputs, {"esc.ladder": (ladder,)})
    if evidence <= (entry["run_id"], entry["attempt"]):
        # the repair rung already answered this evidence — absorb
        return route(outputs, {"esc.ladder": (ladder,)})
    # the ladder is exhausted (repair consumed, STRICTLY newer evidence
    # still failing)
    fact = GateFact(
        kind="human_needed",
        incarnation=failure.incarnation,
        body={"fingerprint": fp, "head": failure.head},
    )
    return route(outputs, {"esc.ladder": (ladder,), "dash.facts": (fact,)})


def _recover(binding, outputs):
    """The recovery door (A2): a faulted RERUN is reissued as ONE fresh
    occurrence under the SAME operation identity; the rerun gate
    reconciles lookup-first, so a rerun the provider already holds lands
    without a duplicate effect. The fault entry (with any blocked
    failure) STAYS in the held ladder — the landed fold consumes it."""
    fact, ladder = values(binding, RecoverFact, Ladder)
    faults = ladder.rerun_faults
    key = next((k for k, v in faults.items() if v["op"] == fact.op), None)
    if (
        ladder.closing is not None  # no reissue after close
        or fact.target != "esc"
        or key is None
        or ladder.reruns.get(key, {}).get("state") != "fault"
    ):
        return route(outputs, {"esc.ladder": (ladder,)})
    held = faults[key]
    cleared = ladder.validated_update(
        reruns={k: v for k, v in ladder.reruns.items() if k != key},
    )
    req = RerunReq(
        fingerprint=key,
        fp=held["fp"],
        op=held["op"],  # the EXACT retained operation identity
        head=held["head"],
        base=held["base"],
        policy=held["policy"],
        incarnation=held["incarnation"],
        run_id=held["run_id"],
        attempt=held["attempt"],
        mem=cleared.dump(),
    )
    # the ladder baton is HELD through the reissued round (folds recreate it)
    return route(outputs, {"esc.rerun_req": (req,)})


def _fold_rerun_landed(binding, outputs):
    (out,) = values(binding, RerunLanded)
    mem = revive(Ladder, out.mem)
    key = out.fingerprint
    watermark = (out.run_id, out.attempt)
    held = mem.rerun_faults.get(key)
    blocked = None if held is None else held.get("blocked")
    faults = {k: v for k, v in mem.rerun_faults.items() if k != key}
    if out.disposition == "requested":
        # the rerun was issued in THIS round: evidence observed before
        # the request — the gate's pre-request cut, which covers mail
        # still queued while the gate was in flight, and any failure
        # retained on a fault entry — can never prove it failed.
        # Advance the watermark to absorb all of it; the fresh rerun's
        # own outcome arrives later as strictly newer evidence.
        watermark = max(watermark, (out.cut_run_id, out.cut_attempt))
        if blocked is not None:
            watermark = max(watermark, (blocked["run_id"], blocked["attempt"]))
    rung = {"state": "done", "run_id": watermark[0], "attempt": watermark[1]}
    ladder = mem.validated_update(reruns={**mem.reruns, key: rung}, rerun_faults=faults)
    routes: dict = {"esc.ladder": (ladder,)}
    if held is not None:
        # the landed fold consumed a fault entry: the settle CLEARS the
        # operation-keyed fault, so readiness never stays fail-closed
        # after the human's recovery actually succeeded
        resolved = GateFact(
            kind="fault", incarnation=0, body={"where": "rerun", "op": held["op"], "status": "resolved"}
        )
        routes["ready.facts"] = (resolved,)
        routes["dash.facts"] = (resolved,)
    if blocked is not None and out.disposition == "existing":
        # the provider held the rerun all along — the blocked failure
        # may well BE its outcome: replay it through the normal path,
        # where it now finds the rung done and can advance the ladder
        routes["esc.failures"] = (revive(ChecksFailure, blocked),)
    return route(outputs, routes)


def _fold_rerun_moved(binding, outputs):
    (out,) = values(binding, RerunMoved)
    mem = revive(Ladder, out.mem)
    # moved burns NO budget — and the failure may still stand under the
    # fresh authority, so echo a recheck to CI instead of losing it
    echo = EscMoved(
        fp=out.fp,
        head=out.head,
        base=out.base,
        policy=out.policy,
        incarnation=out.incarnation,
    )
    routes: dict = {"ci.echo": (echo,)}
    held = mem.rerun_faults.get(out.fingerprint)
    if held is not None:
        # a RECOVERY round settled moved: lookup-first found no existing
        # rerun and the gate refused the stale claim, so the operation
        # provably issued no effect. Consume the retained fault and mail
        # the operation-keyed resolution — readiness must not stay
        # fail-closed forever when the echo lands on a CI that already
        # turned green (no later landed fold would ever clear it). The
        # retained blocked failure is superseded by the echo's fresh
        # recheck under the current authority.
        mem = mem.validated_update(
            rerun_faults={k: v for k, v in mem.rerun_faults.items() if k != out.fingerprint},
        )
        resolved = GateFact(
            kind="fault", incarnation=0, body={"where": "rerun", "op": held["op"], "status": "resolved"}
        )
        routes["ready.facts"] = (resolved,)
        routes["dash.facts"] = (resolved,)
    routes["esc.ladder"] = (mem,)
    return route(outputs, routes)


def _fold_rerun_fault(binding, outputs):
    (out,) = values(binding, RerunFault)
    mem = revive(Ladder, out.mem)
    # A2: Faulted retains the EXACT request (operation identity, raw
    # fingerprint, full authority claim) so recovery can reissue it
    retained = {
        "op": out.op,
        "reason": out.reason,
        "fp": out.fp,
        "head": out.head,
        "base": out.base,
        "policy": out.policy,
        "incarnation": out.incarnation,
        "run_id": out.run_id,
        "attempt": out.attempt,
        # a re-faulted RECOVERY round must not lose the blocked failure
        "blocked": mem.rerun_faults.get(out.fingerprint, {}).get("blocked"),
    }
    ladder = mem.validated_update(
        reruns={**mem.reruns, out.fingerprint: {"state": "fault"}},
        rerun_faults={**mem.rerun_faults, out.fingerprint: retained},
    )
    # the operation identity keys the fault so the landed fold's
    # resolution can clear EXACTLY this entry in readiness
    fact = GateFact(kind="fault", incarnation=0, body={"where": "rerun", "op": out.op, "reason": out.reason})
    return route(
        outputs,
        {"esc.ladder": (ladder,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _pending_repairs(repairs: dict) -> bool:
    return any(entry["state"] == "pending" for entry in repairs.values())


def _retire(ladder: Ladder, repairs: dict, reason: str, outputs):
    ended = LadderEnded(reruns=ladder.reruns, repairs=repairs, reason=reason)
    return route(outputs, {"esc.done": (ended,)})


def _drain_recover(binding, outputs):
    # a recovery note admitted while running can be applied AFTER the
    # ladder retired: close wins, the note is inert — never stranded
    _, ended = values(binding, RecoverFact, LadderEnded)
    return route(outputs, {"esc.done": (ended,)})


def _fold_settled(binding, outputs):
    settled, ladder = values(binding, MutationSettled, Ladder)
    key = settled.fingerprint
    if not key or key not in ladder.repairs or settled.op != f"repair:{key}":
        return route(outputs, {"esc.ladder": (ladder,)})  # not ours: inert
    entry = ladder.repairs[key]
    repairs = dict(ladder.repairs)
    if settled.outcome == "landed":
        repairs[key] = {**entry, "state": "done"}
    elif settled.outcome == "declined":
        # the mutation loop refused to push (policy, not failure): the
        # rung is consumed with a KNOWN terminal — strictly newer
        # failing evidence goes straight to the human
        repairs[key] = {**entry, "state": "declined"}
    elif settled.outcome == "moved":
        # the world did not change: refund the budget AND echo a recheck
        # (the failure may still stand under the fresh authority)
        del repairs[key]
        if ladder.closing is not None and not _pending_repairs(repairs):
            # closing: the world is done — no recheck, retire instead
            return _retire(ladder, repairs, ladder.closing, outputs)
        echo = EscMoved(
            fp=entry["fp"],
            head=entry["head"],
            base=entry["base"],
            policy=entry["policy"],
            incarnation=entry["incarnation"],
        )
        return route(
            outputs,
            {"esc.ladder": (ladder.validated_update(repairs=repairs),), "ci.echo": (echo,)},
        )
    else:
        # A2: a FAULTED rung retains the exact entry (raw fp + attempted
        # authority), not a bare marker — mutation custody may reissue
        # the exact operation later, and if authority moved meanwhile the
        # settle classifies MOVED: the refund branch above then needs the
        # entry's fields to echo the recheck (a bare string would strand
        # the custody and crash the fold)
        repairs[key] = {**entry, "state": "fault"}
    if ladder.closing is not None and not _pending_repairs(repairs):
        # the settlement this close was waiting for: retire NOW
        return _retire(ladder, repairs, ladder.closing, outputs)
    return route(outputs, {"esc.ladder": (ladder.validated_update(repairs=repairs),)})


def _end(binding, outputs):
    close, ladder = values(binding, CloseFact, Ladder)
    if _pending_repairs(ladder.repairs):
        # a repair is in mutation custody: its settlement WILL arrive
        # (mutation settles every mailboxed request, even after its own
        # close). Retiring now would strand it and record a lie — hold
        # the ladder in `closing` until the last settlement folds.
        return route(outputs, {"esc.ladder": (ladder.validated_update(closing=close.reason),)})
    ended = LadderEnded(reruns=ladder.reruns, repairs=ladder.repairs, reason=close.reason)
    return route(outputs, {"esc.done": (ended,)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    esc = s.esc
    esc.p.failures(ChecksFailure)
    esc.p.closed(CloseFact)
    esc.p.recover(RecoverFact)
    esc.p.settled(MutationSettled)
    esc.p.ladder(Ladder)
    esc.p.rerun_req(RerunReq)
    esc.p.rerun_landed(RerunLanded)
    esc.p.rerun_moved(RerunMoved)
    esc.p.rerun_fault(RerunFault)
    esc.p.done(LadderEnded)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    s = net.s
    esc, ci, mut, dash, ready = s.esc, s.ci, s.mut, s.dash, s.ready

    (
        (esc.p.failures, esc.p.ladder)
        >> esc.t.decide(handler=petri_handler(_decide))
        >> (
            esc.p.ladder,
            esc.p.rerun_req,
            mut.p.requests,
            dash.p.facts,
        )
    )
    (
        esc.p.rerun_req
        >> esc.t.rerun_gate(handler="rerun_gate")
        >> (
            esc.p.rerun_landed,
            esc.p.rerun_moved,
            esc.p.rerun_fault,
        )
    )
    (
        esc.p.rerun_landed
        >> esc.t.fold_rerun_landed(handler=petri_handler(_fold_rerun_landed))
        >> (
            esc.p.ladder,
            esc.p.failures,  # a recovery round replays the blocked failure
            ready.p.facts,  # a recovery round's settle clears the fault
            dash.p.facts,
        )
    )
    (
        esc.p.rerun_moved
        >> esc.t.fold_rerun_moved(handler=petri_handler(_fold_rerun_moved))
        >> (
            esc.p.ladder,
            ci.p.echo,
            ready.p.facts,  # a moved recovery round's settle clears the fault
            dash.p.facts,
        )
    )
    (
        esc.p.rerun_fault
        >> esc.t.fold_rerun_fault(handler=petri_handler(_fold_rerun_fault))
        >> (
            esc.p.ladder,
            ready.p.facts,
            dash.p.facts,
        )
    )
    (
        (esc.p.settled, esc.p.ladder)
        >> esc.t.fold_settled(handler=petri_handler(_fold_settled))
        >> (
            esc.p.ladder,
            ci.p.echo,
            esc.p.done,  # a closing ladder retires on its last settlement
        )
    )
    # the exact-recovery door (A2): a faulted rerun reissues under the
    # SAME operation identity; the ladder baton is held through the round
    (
        (esc.p.recover, esc.p.ladder)
        >> esc.t.recovery(handler=petri_handler(_recover))
        >> (
            esc.p.ladder,
            esc.p.rerun_req,
        )
    )
    # end retires immediately, or holds the ladder in `closing` while a
    # repair settlement is still owed by the mutation loop
    ((esc.p.closed, esc.p.ladder) >> esc.t.end(handler=petri_handler(_end)) >> (esc.p.done, esc.p.ladder))
    # post-close drain: a recovery note whose apply lost the race with
    # close is absorbed by the retired ladder's done baton, never stranded
    ((esc.p.recover, esc.p.done) >> esc.t.drain_recover(handler=petri_handler(_drain_recover)) >> esc.p.done)


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = Ladder(reruns={}, repairs={}, rerun_faults={})
    return {NetPath("esc.ladder"): (Token("Ladder", baton.dump()),)}
