"""The dashboard loop: a mutable singleton projection of the PR's state.

Owns the DashMemory baton. Every sibling loop mails GateFacts here; the
fold accumulates them into the projection log and republishes the board
on digest drift ONLY — drift is a DECISION (fold), the upsert an
effect. Successful publication releases workflow startup. The projection
remains authority-orthogonal (A5): a stale board row is corrected by
the next upsert, never fenced.

Custody is a held baton: memory leaves its place while an upsert is in
flight, so publication is single-flight by construction and facts
arriving mid-flight wait in the mailbox. Blocked and faulted upserts
retain the EXACT attempted request (entries + digest) while memory
keeps tracking the evolving DESIRED state fail-closed; recovery
reissues the retained request verbatim through the `dash.recover` door,
and the landed fold self-heals any drift with a follow-up upsert of the
desired state (A2).
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    CloseFact,
    DashBlocked,
    DashDeferred,
    DashEnded,
    DashFault,
    DashHeal,
    DashLanded,
    DashMemory,
    DashReq,
    GateFact,
    RecoverFact,
    SummaryPublished,
)
from hamsterdan.readiness.net_v5.folding import route, values

GATES = {"dash.publish": ("dash_gate", ("DashLanded", "DashDeferred", "DashBlocked", "DashFault"))}

# -- folds ---------------------------------------------------------------


def _digest(fact: GateFact) -> str:
    """The fact's projection identity: kind + canonicalized body. The
    grant incarnation is deliberately absent — the board shows WHAT the
    PR looks like, not which incarnation last said so."""
    return f"{fact.kind}:{sorted(fact.body.items())!r}"


def _live_req(entries: list[str], digest: str, mem: DashMemory) -> DashReq:
    """A live publish IS the desired state."""
    return DashReq(
        entries=entries,
        digest=digest,
        desired_entries=entries,
        desired_digest=digest,
        landed=mem.landed,
        blocked=mem.blocked,
        faulted=mem.faulted,
    )


def _fold(binding, outputs):
    fact, mem = values(binding, GateFact, DashMemory)
    digest = _digest(fact)
    if digest == mem.digest:  # republish on digest drift ONLY
        return route(outputs, {"dash.memory": (mem,)})
    entries = [*mem.entries, f"{fact.kind}:{fact.body}"]
    if mem.blocked or mem.faulted:
        # fail-closed while blocked/faulted: accumulate the DESIRED
        # state (entries + digest); the retained blocked/faulted request
        # stays EXACTLY as attempted, and recovery reconciles the two
        return route(outputs, {"dash.memory": (mem.validated_update(entries=entries, digest=digest),)})
    # memory is HELD through the upsert round; the landed fold recreates it
    return route(outputs, {"dash.pub_req": (_live_req(entries, digest, mem),)})


def _fold_landed(binding, outputs):
    (out,) = values(binding, DashLanded)
    mem = DashMemory(
        entries=tuple(out.desired_entries),
        digest=out.desired_digest,
        landed=out.digest,
        blocked={},
        faulted={},
    )
    emitted = {
        "dash.memory": (mem,),
        "startup.published": (SummaryPublished(digest=out.digest),),
    }
    if out.desired_digest != out.digest or list(out.desired_entries) != list(out.entries):
        # a recovery landed the EXACT retained request, but the desired
        # state drifted while the fault was held: poke the self-heal
        # transition (which consumes the baton — every reissue cycle
        # passes through a baton-consuming transition). Entries are
        # compared too: a cyclic drift (A→B→A) returns to the retained
        # digest with MORE entries, and the digest alone would hide it.
        heal = DashHeal(entries=tuple(out.desired_entries), digest=out.desired_digest)
        emitted["dash.heal"] = (heal,)
    return route(outputs, emitted)


def _fold_deferred(binding, outputs):
    (out,) = values(binding, DashDeferred)
    return route(
        outputs,
        {
            "dash.memory": (
                DashMemory(
                    entries=tuple(out.desired_entries),
                    digest=out.desired_digest,
                    landed=out.landed,
                    blocked=out.blocked,
                    faulted=out.faulted,
                ),
            )
        },
    )


def _selfheal(binding, outputs):
    heal, mem = values(binding, DashHeal, DashMemory)
    if mem.blocked or mem.faulted or (mem.entries, mem.digest) != (heal.entries, heal.digest):
        # the loop is fail-closed again, or memory moved past the poke's
        # snapshot — a drifted fold already went through its own publish
        # round (which carried the full desired state): the poke is inert
        return route(outputs, {"dash.memory": (mem,)})
    # memory is HELD through the healing upsert round. The snapshot
    # comparison — never `digest == landed` — decides staleness: after a
    # cyclic drift the desired digest EQUALS the landed one while the
    # board still misses entries.
    return route(outputs, {"dash.pub_req": (_live_req(list(mem.entries), mem.digest, mem),)})


def _fold_blocked(binding, outputs):
    (out,) = values(binding, DashBlocked)
    # A2: custody retains the EXACT attempted request (entries + digest),
    # while memory keeps tracking the evolving DESIRED state
    mem = DashMemory(
        entries=tuple(out.desired_entries),
        digest=out.desired_digest,
        landed="",  # the attempted upsert did NOT land
        blocked={"entries": list(out.entries), "digest": out.digest},
        faulted={},
    )
    return route(outputs, {"dash.memory": (mem,)})


def _fold_fault(binding, outputs):
    (out,) = values(binding, DashFault)
    # A2: Faulted retains the EXACT effect (entries + digest) and reason,
    # while memory keeps tracking the evolving DESIRED state. The fault
    # is recoverable through the dash.recover door — it is NOT a
    # readiness fact, and a dash→ready edge would braid the two
    # projections into a batonless cycle.
    mem = DashMemory(
        entries=tuple(out.desired_entries),
        digest=out.desired_digest,
        landed="",  # the attempted upsert is NOT PROVEN landed (unknown terminal)
        blocked={},
        faulted={"entries": list(out.entries), "digest": out.digest, "reason": out.reason},
    )
    return route(outputs, {"dash.memory": (mem,)})


def _recover(binding, outputs):
    fact, mem = values(binding, RecoverFact, DashMemory)
    held = mem.blocked or mem.faulted
    if fact.target != "dashboard" or not held or fact.op != f"dash:{held['digest']}":
        return route(outputs, {"dash.memory": (mem,)})
    # ONE fresh occurrence reissuing the EXACT retained request — same
    # entries, same digest identity. The desired state travels
    # alongside; if it drifted while the fault was held, the landed fold
    # self-heals with a follow-up upsert of the desired state. The
    # memory baton is HELD through the recovery round — returning it
    # here would let concurrent facts extend `entries` and then be
    # overwritten by the landed fold's snapshot (a real lost-entry race).
    req = DashReq(
        entries=list(held["entries"]),
        digest=held["digest"],
        desired_entries=list(mem.entries),
        desired_digest=mem.digest,
        landed=mem.landed,
        blocked=mem.blocked,
        faulted=mem.faulted,
    )
    return route(outputs, {"dash.pub_req": (req,)})


def _end(binding, outputs):
    close, mem = values(binding, CloseFact, DashMemory)
    return route(outputs, {"dash.done": (DashEnded(entries=mem.entries, reason=close.reason),)})


def _drain_fact(binding, outputs):
    # the conversation loop NEVER ends and other loops settle late mail
    # after close (mutation's drain declines queued requests, a reply
    # fault resolves): the EXTERNAL board froze at close, but the
    # terminal record keeps the fact — settled history is never lost to
    # the close race, and the token never strands
    fact, ended = values(binding, GateFact, DashEnded)
    updated = ended.validated_update(entries=[*ended.entries, f"{fact.kind}:{fact.body}"])
    return route(outputs, {"dash.done": (updated,)})


def _drain_recover(binding, outputs):
    _, ended = values(binding, RecoverFact, DashEnded)
    return route(outputs, {"dash.done": (ended,)})


def _drain_heal(binding, outputs):
    # close can win the baton race against a self-heal poke emitted by
    # an upsert that landed while close waited: the poke is inert
    _, ended = values(binding, DashHeal, DashEnded)
    return route(outputs, {"dash.done": (ended,)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    dash = s.dash
    dash.p.facts(GateFact)
    dash.p.closed(CloseFact)
    dash.p.recover(RecoverFact)
    dash.p.memory(DashMemory)
    dash.p.pub_req(DashReq)
    dash.p.landed(DashLanded)
    dash.p.deferred(DashDeferred)
    dash.p.dblocked(DashBlocked)
    dash.p.dfault(DashFault)
    dash.p.heal(DashHeal)
    dash.p.done(DashEnded)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    dash = net.s.dash

    (
        (dash.p.facts, dash.p.memory)
        >> dash.t.fold(handler=petri_handler(_fold))
        >> (
            dash.p.memory,
            dash.p.pub_req,
        )
    )
    (
        dash.p.pub_req
        >> dash.t.publish(handler="dash_gate")
        >> (
            dash.p.landed,
            dash.p.deferred,
            dash.p.dblocked,
            dash.p.dfault,
        )
    )
    (
        dash.p.landed
        >> dash.t.fold_landed(handler=petri_handler(_fold_landed))
        >> (
            dash.p.memory,
            dash.p.heal,
            net.s.startup.p.published,
        )
    )
    # self-heal after a recovery landed an exact-but-drifted retained
    # request: the transition consumes the BATON, so the reissue cycle
    # stays baton-serialized like every other cycle in the net
    (
        (dash.p.heal, dash.p.memory)
        >> dash.t.selfheal(handler=petri_handler(_selfheal))
        >> (
            dash.p.memory,
            dash.p.pub_req,
        )
    )
    (dash.p.deferred >> dash.t.fold_deferred(handler=petri_handler(_fold_deferred)) >> dash.p.memory)
    (dash.p.dblocked >> dash.t.fold_blocked(handler=petri_handler(_fold_blocked)) >> dash.p.memory)
    (dash.p.dfault >> dash.t.fold_fault(handler=petri_handler(_fold_fault)) >> dash.p.memory)
    # the exact-recovery door (A2): a blocked or faulted upsert reissues
    # the retained request verbatim under the SAME digest identity
    (
        (dash.p.recover, dash.p.memory)
        >> dash.t.recovery(handler=petri_handler(_recover))
        >> (
            dash.p.memory,
            dash.p.pub_req,
        )
    )
    ((dash.p.closed, dash.p.memory) >> dash.t.end(handler=petri_handler(_end)) >> dash.p.done)
    # post-close drains: mail that lost the race with close is absorbed
    # by the retired board's persistent done baton, never stranded
    ((dash.p.facts, dash.p.done) >> dash.t.drain_fact(handler=petri_handler(_drain_fact)) >> dash.p.done)
    ((dash.p.recover, dash.p.done) >> dash.t.drain_recover(handler=petri_handler(_drain_recover)) >> dash.p.done)
    ((dash.p.heal, dash.p.done) >> dash.t.drain_heal(handler=petri_handler(_drain_heal)) >> dash.p.done)


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = DashMemory(entries=(), digest="", landed="", blocked={}, faulted={})
    return {NetPath("dash.memory"): (Token("DashMemory", baton.dump()),)}
