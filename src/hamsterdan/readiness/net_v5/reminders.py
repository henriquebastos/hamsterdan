"""The reminders loop: host-armed timers mature into human nudges.

Owns the RemState baton and the `on_timer` door. Every TimerDue is
recorded as a durable maturity fact — snooze and close suppress only
the nudge DECISION, never the fact. Custody is per-timer DATA in the
baton (A2), not a held baton: `pending` makes each timer single-flight
while the baton stays available, so a snooze folds mid-flight. Blocked
nudges recover through the `rem.recover` door under the SAME effect
identity `reminder:{timer_id}`, lookup-first at the gate; faulted
nudges are fail-closed — not proven un-landed, so maturity alone never
reopens them. Close defers while terminals are outstanding (A3): the
LAST terminal fold finalizes, and post-close mail drains into the
terminal record so no token strands.
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    CloseFact,
    GateFact,
    RecoverFact,
    RemBlocked,
    RemEnded,
    RemFault,
    RemLanded,
    RemReq,
    RemState,
    SnoozeFact,
    TimerDue,
)
from hamsterdan.readiness.net_v5.folding import route, values

GATES = {"rem.gate": ("reminder_gate", ("RemLanded", "RemBlocked", "RemFault"))}

# -- folds ---------------------------------------------------------------


def _mature(binding, outputs):
    due, st = values(binding, TimerDue, RemState)
    st = st.validated_update(matured=(*st.matured, due.timer_id))  # the FACT is durable
    if st.snoozed or st.closing is not None:
        return route(outputs, {"rem.state": (st,)})  # only the DECISION is suppressed
    if due.timer_id in st.pending or due.timer_id in st.blocked or due.timer_id in st.faulted:
        # single-flight per timer: a duplicate maturity never doubles
        # the effect — and a faulted timer never reopens by maturity
        return route(outputs, {"rem.state": (st,)})
    # A2: record Pending custody as DATA (the baton stays available so
    # snoozes and closes still fold while the nudge is in flight)
    st = st.validated_update(pending={**st.pending, due.timer_id: True})
    return route(outputs, {"rem.state": (st,), "rem.pub_req": (RemReq(timer_id=due.timer_id),)})


def _snooze(binding, outputs):
    fact, st = values(binding, SnoozeFact, RemState)
    if fact.mode == "snooze":
        st = st.validated_update(snoozed=True)
    elif fact.mode == "clear":
        st = st.validated_update(snoozed=False)
    else:  # defer: the host arms the timer; the net records the request
        st = st.validated_update(deferred=(*st.deferred, fact.arg))
    return route(outputs, {"rem.state": (st,)})


def _settle(st: RemState, outputs, extra: dict):
    """After a terminal folds: finish a deferred close (A3) once the
    LAST outstanding terminal has settled, else return the baton."""
    if st.closing is not None and not st.pending:
        done = RemEnded(matured=st.matured, reason=st.closing)
        return route(outputs, {**extra, "rem.done": (done,)})
    return route(outputs, {**extra, "rem.state": (st,)})


def _fold_landed(binding, outputs):
    out, st = values(binding, RemLanded, RemState)
    st = st.validated_update(
        pending={k: v for k, v in st.pending.items() if k != out.timer_id},
        blocked={k: v for k, v in st.blocked.items() if k != out.timer_id},
    )
    fact = GateFact(kind="reminder", incarnation=0, body={"timer_id": out.timer_id})
    return _settle(st, outputs, {"dash.facts": (fact,)})


def _fold_blocked(binding, outputs):
    out, st = values(binding, RemBlocked, RemState)
    st = st.validated_update(
        pending={k: v for k, v in st.pending.items() if k != out.timer_id},
        blocked={**st.blocked, out.timer_id: True},
    )
    return _settle(st, outputs, {})


def _fold_fault(binding, outputs):
    out, st = values(binding, RemFault, RemState)
    # A2: Faulted retains the timer and reason in the baton, fail-closed
    st = st.validated_update(
        pending={k: v for k, v in st.pending.items() if k != out.timer_id},
        faulted={**st.faulted, out.timer_id: out.reason},
    )
    fact = GateFact(kind="fault", incarnation=0, body={"where": "reminder", "reason": out.reason})
    return _settle(st, outputs, {"dash.facts": (fact,)})


def _recover(binding, outputs):
    fact, st = values(binding, RecoverFact, RemState)
    if (
        fact.target != "reminder"
        or not fact.op.startswith("reminder:")  # the EXACT operation syntax
        or (timer_id := fact.op.removeprefix("reminder:")) not in st.blocked
        or st.closing is not None
    ):
        # blocked-only by SETTLED TERMINAL POLICY: an unknown publication
        # terminal is a nonrecoverable workflow fault — retained with its
        # reason and surfaced on the dashboard for the human, never
        # reissued by this door
        return route(outputs, {"rem.state": (st,)})
    # blocked -> pending: one fresh occurrence, the SAME effect identity
    st = st.validated_update(
        pending={**st.pending, timer_id: True},
        blocked={k: v for k, v in st.blocked.items() if k != timer_id},
    )
    return route(outputs, {"rem.state": (st,), "rem.pub_req": (RemReq(timer_id=timer_id),)})


def _end(binding, outputs):
    close, st = values(binding, CloseFact, RemState)
    if st.pending:
        # A3: nudge gates are outstanding — record the close INTENT; the
        # last terminal fold finalizes, so late terminals still settle
        return route(outputs, {"rem.state": (st.validated_update(closing=close.reason),)})
    return route(outputs, {"rem.done": (RemEnded(matured=st.matured, reason=close.reason),)})


def _drain_timer(binding, outputs):
    # the host cancels timers at close, but at-least-once means a late
    # maturity can still arrive: the FACT is recorded on the terminal
    # record, the decision is gone, and the token never strands
    due, ended = values(binding, TimerDue, RemEnded)
    updated = ended.validated_update(matured=(*ended.matured, due.timer_id))
    return route(outputs, {"rem.done": (updated,)})


def _drain_snooze(binding, outputs):
    _, ended = values(binding, SnoozeFact, RemEnded)
    return route(outputs, {"rem.done": (ended,)})


def _drain_recover(binding, outputs):
    _, ended = values(binding, RecoverFact, RemEnded)
    return route(outputs, {"rem.done": (ended,)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    rem = s.rem
    rem.p.timers(TimerDue)
    rem.p.snoozes(SnoozeFact)
    rem.p.recover(RecoverFact)
    rem.p.closed(CloseFact)
    rem.p.state(RemState)
    rem.p.pub_req(RemReq)
    rem.p.rlanded(RemLanded)
    rem.p.rblocked(RemBlocked)
    rem.p.rfault(RemFault)
    rem.p.done(RemEnded)


def wire(net) -> None:
    """Wire this loop's door and transitions (sibling places must exist)."""
    rem, dash = net.s.rem, net.s.dash

    # the timer door: host-armed timers mature straight into this loop —
    # reminders are authority-orthogonal, so no lifecycle admission
    net.t.on_timer >> rem.p.timers

    (
        (rem.p.timers, rem.p.state)
        >> rem.t.mature(handler=petri_handler(_mature))
        >> (
            rem.p.state,
            rem.p.pub_req,
        )
    )
    ((rem.p.snoozes, rem.p.state) >> rem.t.snooze(handler=petri_handler(_snooze)) >> rem.p.state)
    (
        rem.p.pub_req
        >> rem.t.gate(handler="reminder_gate")
        >> (
            rem.p.rlanded,
            rem.p.rblocked,
            rem.p.rfault,
        )
    )
    (
        (rem.p.rlanded, rem.p.state)
        >> rem.t.fold_landed(handler=petri_handler(_fold_landed))
        >> (
            rem.p.state,
            dash.p.facts,
            rem.p.done,
        )
    )
    (
        (rem.p.rblocked, rem.p.state)
        >> rem.t.fold_blocked(handler=petri_handler(_fold_blocked))
        >> (
            rem.p.state,
            rem.p.done,
        )
    )
    (
        (rem.p.rfault, rem.p.state)
        >> rem.t.fold_fault(handler=petri_handler(_fold_fault))
        >> (
            rem.p.state,
            dash.p.facts,
            rem.p.done,
        )
    )
    # the exact-recovery door (A2): a blocked nudge reissues under the
    # SAME effect identity; the gate reconciles lookup-first
    (
        (rem.p.recover, rem.p.state)
        >> rem.t.recovery(handler=petri_handler(_recover))
        >> (
            rem.p.state,
            rem.p.pub_req,
        )
    )
    ((rem.p.closed, rem.p.state) >> rem.t.end(handler=petri_handler(_end)) >> (rem.p.state, rem.p.done))
    # post-close drains: mail that lost the race with close is absorbed
    # by the retired loop's persistent done record, never stranded
    ((rem.p.timers, rem.p.done) >> rem.t.drain_timer(handler=petri_handler(_drain_timer)) >> rem.p.done)
    ((rem.p.snoozes, rem.p.done) >> rem.t.drain_snooze(handler=petri_handler(_drain_snooze)) >> rem.p.done)
    ((rem.p.recover, rem.p.done) >> rem.t.drain_recover(handler=petri_handler(_drain_recover)) >> rem.p.done)


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = RemState(matured=(), snoozed=False, deferred=(), pending={}, blocked={}, faulted={}, closing=None)
    return {NetPath("rem.state"): (Token("RemState", baton.dump()),)}
