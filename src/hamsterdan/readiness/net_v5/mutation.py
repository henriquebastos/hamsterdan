"""The mutation loop: every write to the branch goes through one baton.

Owns the MutState baton — the baton IS the one-at-a-time serialization:
`start` consumes it into the round and only a terminal fold returns it,
so a second request waits visibly in its mailbox. The git gate fences
the head by server-side CAS and base/policy/grant by a fresh read
(A1.5), under a stable operation identity reconciled lookup-first (A2).
A landed push mails the settlement to escalation AND the provisional
head to lifecycle, so our own push is later admitted as `confirmed`
(same budget lineage) instead of `superseded`. A faulted round is
FAIL-CLOSED: the baton retains the exact operation and declines every
further request until the human recovers or the PR closes.

ACCEPTED RACE (ruled): the gate's fresh read of base/policy/grant
narrows but cannot close the window between the read and the head CAS —
no provider primitive makes them atomic. The head CAS is the only
atomic fence. A push that lands just after a close or base move is an
accepted external cost (a branch write); the net stays coherent because
the terminal still settles, close waits for the in-flight round, and
the provisional note's from_head fence keeps lifecycle honest.
"""

from __future__ import annotations

from typing import Literal

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    CloseFact,
    DeclinedM,
    FaultM,
    GateFact,
    MovedM,
    MutationRequest,
    MutationSettled,
    MutEnded,
    MutState,
    MutWork,
    ProvisionalHead,
    Pushed,
    RecoverFact,
)
from hamsterdan.readiness.net_v5.folding import route, values

GATES = {"mut.git_gate": ("git_gate", ("Pushed", "MovedM", "FaultM", "DeclinedM"))}

_IDLE = MutState(
    state="idle",
    op_key="",
    op="",
    head="",
    base="",
    policy="",
    incarnation=0,
    reason="",
    kind="",
    instruction="",
    run_id=0,
    attempt=0,
)

# -- folds ---------------------------------------------------------------


def _budget_key(op: str) -> str:
    """The escalation budget key for a repair op ('' for human ops)."""
    return op.removeprefix("repair:") if op.startswith("repair:") else ""


def _lineage(op: str) -> str:
    """The budget lineage a pushed head inherits when confirmed: repair
    keys are `{lineage}:{fingerprint}`; human ops start no lineage."""
    key = _budget_key(op)
    return key.split(":", 1)[0] if key else ""


def _op_key(req: MutationRequest) -> str:
    """The round's stable operation identity: built from the REQUEST
    identity (rid), not the semantic op — two distinct requests of the
    same kind at the same head must not reconcile onto each other."""
    return f"push:{req.rid}:{req.head}:i{req.incarnation}"


def _settled(
    op: str, op_key: str, outcome: Literal["landed", "declined", "moved", "faulted"], incarnation: int
) -> MutationSettled:
    return MutationSettled(op=op, op_key=op_key, outcome=outcome, incarnation=incarnation, fingerprint=_budget_key(op))


def _settled_fact(settled: MutationSettled) -> GateFact:
    return GateFact(kind="mutation_settled", incarnation=settled.incarnation, body=settled.dump())


def _start(binding, outputs):
    req, st = values(binding, MutationRequest, MutState)
    if st.state == "faulted":
        # FAIL-CLOSED: an unresolved push terminal means the branch's
        # true head is unknown — no further mutation may claim it. The
        # request settles `declined` BEFORE any gate attempt.
        settled = _settled(req.op, _op_key(req), "declined", req.incarnation)
        fact = _settled_fact(settled)
        return route(
            outputs,
            {"mut.state": (st,), "esc.settled": (settled,), "ready.facts": (fact,), "dash.facts": (fact,)},
        )
    # the baton is HELD until a terminal fold returns it: one at a time
    work = MutWork(
        op=req.op,
        op_key=_op_key(req),
        head=req.head,
        base=req.base,
        policy=req.policy,
        incarnation=req.incarnation,
        lineage=_lineage(req.op),
        kind=req.kind,
        instruction=req.instruction,
        run_id=req.run_id,
        attempt=req.attempt,
    )
    fact = GateFact(kind="mutation_pending", incarnation=req.incarnation, body={"op": req.op, "op_key": work.op_key})
    return route(outputs, {"mut.work": (work,), "ready.facts": (fact,), "dash.facts": (fact,)})


def _fold_pushed(binding, outputs):
    (out,) = values(binding, Pushed)
    settled = _settled(out.op, out.op_key, "landed", out.incarnation)
    fact = _settled_fact(settled)
    # from_head is the causal fence: lifecycle installs the expectation
    # only while it still stands on the head this push moved FROM
    note = ProvisionalHead(expected=out.new_head, from_head=out.head, op=out.op, lineage=out.lineage)
    return route(
        outputs,
        {
            "mut.state": (_IDLE,),
            "life.provisional": (note,),
            "esc.settled": (settled,),
            "ready.facts": (fact,),
            "dash.facts": (fact,),
        },
    )


def _fold_moved(binding, outputs):
    (out,) = values(binding, MovedM)
    # the world did not change: the gate refused the write. Escalation
    # refunds the budget and echoes a recheck through CI.
    settled = _settled(out.op, out.op_key, "moved", out.incarnation)
    fact = _settled_fact(settled)
    return route(
        outputs,
        {"mut.state": (_IDLE,), "esc.settled": (settled,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _fold_declined(binding, outputs):
    (out,) = values(binding, DeclinedM)
    # the agent investigated and produced no change: nothing was pushed,
    # the branch's true head is fully known — the baton returns IDLE
    # (not fail-closed) and the rung is consumed with a known terminal
    settled = _settled(out.op, out.op_key, "declined", out.incarnation)
    fact = _settled_fact(settled)
    return route(
        outputs,
        {"mut.state": (_IDLE,), "esc.settled": (settled,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _fold_fault(binding, outputs):
    (out,) = values(binding, FaultM)
    settled = _settled(out.op, out.op_key, "faulted", out.incarnation)
    fact = GateFact(kind="fault", incarnation=0, body={"where": "mutation", "op": out.op_key, "reason": out.reason})
    # A2: Faulted retains the exact operation identity and the FULL
    # authority claim so recovery reissues the SAME operation
    faulted = MutState(
        state="faulted",
        op_key=out.op_key,
        op=out.op,
        head=out.head,
        base=out.base,
        policy=out.policy,
        incarnation=out.incarnation,
        reason=out.reason,
        kind=out.kind,
        instruction=out.instruction,
        run_id=out.run_id,
        attempt=out.attempt,
    )
    return route(
        outputs,
        {"mut.state": (faulted,), "esc.settled": (settled,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _recover(binding, outputs):
    fact, st = values(binding, RecoverFact, MutState)
    if fact.target != "mutation" or st.state != "faulted" or fact.op != st.op_key:
        return route(outputs, {"mut.state": (st,)})
    # ONE fresh occurrence, SAME operation identity; the gate reconciles
    # lookup-first (a crash after the push landed must not push twice).
    # The baton is HELD again until a terminal fold returns it.
    work = MutWork(
        op=st.op,
        op_key=st.op_key,
        head=st.head,
        base=st.base,
        policy=st.policy,
        incarnation=st.incarnation,
        lineage=_lineage(st.op),
        kind=st.kind,
        instruction=st.instruction,
        run_id=st.run_id,
        attempt=st.attempt,
    )
    pending = GateFact(kind="mutation_pending", incarnation=st.incarnation, body={"op": st.op, "op_key": st.op_key})
    # the reissue CLEARS the operation-keyed fault: readiness never
    # stays fail-closed after the human ruled — and it cannot announce
    # during the reopened round either, because `pending` holds the op
    # until the terminal settles; a re-fault restores the entry
    resolved = GateFact(kind="fault", incarnation=0, body={"where": "mutation", "op": st.op_key, "status": "resolved"})
    return route(outputs, {"mut.work": (work,), "ready.facts": (pending, resolved), "dash.facts": (pending, resolved)})


def _end(binding, outputs):
    close, st = values(binding, CloseFact, MutState)
    return route(outputs, {"mut.done": (MutEnded(state=st.state, reason=close.reason),)})


def _drain_recover(binding, outputs):
    # a recovery note admitted while running can be applied AFTER the
    # baton retired: close wins, the note is inert — never stranded
    _, ended = values(binding, RecoverFact, MutEnded)
    return route(outputs, {"mut.done": (ended,)})


def _drain(binding, outputs):
    # after close, every mailboxed request still SETTLES (declined):
    # escalation's closing ladder waits on exactly these settlements —
    # a silently parked request would strand it forever
    req, ended = values(binding, MutationRequest, MutEnded)
    settled = _settled(req.op, _op_key(req), "declined", req.incarnation)
    fact = _settled_fact(settled)
    return route(
        outputs,
        {"mut.done": (ended,), "esc.settled": (settled,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    mut = s.mut
    mut.p.requests(MutationRequest)
    mut.p.closed(CloseFact)
    mut.p.recover(RecoverFact)
    mut.p.state(MutState)
    mut.p.work(MutWork)
    mut.p.pushed(Pushed)
    mut.p.movedm(MovedM)
    mut.p.faultm(FaultM)
    mut.p.declinedm(DeclinedM)
    mut.p.done(MutEnded)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    s = net.s
    mut, life, esc, ready, dash = s.mut, s.life, s.esc, s.ready, s.dash

    (
        (mut.p.requests, mut.p.state)
        >> mut.t.start(handler=petri_handler(_start))
        >> (
            mut.p.state,
            mut.p.work,
            esc.p.settled,
            ready.p.facts,
            dash.p.facts,
        )
    )
    (
        mut.p.work
        >> mut.t.git_gate(handler="git_gate")
        >> (
            mut.p.pushed,
            mut.p.movedm,
            mut.p.faultm,
            mut.p.declinedm,
        )
    )
    (
        mut.p.pushed
        >> mut.t.fold_pushed(handler=petri_handler(_fold_pushed))
        >> (
            mut.p.state,
            life.p.provisional,
            esc.p.settled,
            ready.p.facts,
            dash.p.facts,
        )
    )
    (
        mut.p.movedm
        >> mut.t.fold_moved(handler=petri_handler(_fold_moved))
        >> (
            mut.p.state,
            esc.p.settled,
            ready.p.facts,
            dash.p.facts,
        )
    )
    (
        mut.p.declinedm
        >> mut.t.fold_declined(handler=petri_handler(_fold_declined))
        >> (
            mut.p.state,
            esc.p.settled,
            ready.p.facts,
            dash.p.facts,
        )
    )
    (
        mut.p.faultm
        >> mut.t.fold_fault(handler=petri_handler(_fold_fault))
        >> (
            mut.p.state,
            esc.p.settled,
            ready.p.facts,
            dash.p.facts,
        )
    )
    # the exact-recovery door (A2): a faulted push reissues under the
    # SAME operation identity; the baton is held through the round
    (
        (mut.p.recover, mut.p.state)
        >> mut.t.recovery(handler=petri_handler(_recover))
        >> (
            mut.p.state,
            mut.p.work,
            ready.p.facts,
            dash.p.facts,
        )
    )
    ((mut.p.closed, mut.p.state) >> mut.t.end(handler=petri_handler(_end)) >> mut.p.done)
    # post-close drain: requests that lost the race with close still
    # settle declined (mut.done is the closed loop's persistent baton)
    (
        (mut.p.requests, mut.p.done)
        >> mut.t.drain(handler=petri_handler(_drain))
        >> (
            mut.p.done,
            esc.p.settled,
            ready.p.facts,
            dash.p.facts,
        )
    )
    # a recovery note that lost the race with close is inert — never
    # stranded (unlike requests, it owes nobody a settlement)
    ((mut.p.recover, mut.p.done) >> mut.t.drain_recover(handler=petri_handler(_drain_recover)) >> mut.p.done)


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    return {NetPath("mut.state"): (Token("MutState", _IDLE.dump()),)}
