"""The reminders actor loop and its durable Net↔host timer protocol.

Lifecycle mail changes the desired clock. The loop serializes that intent
through one persistent ``TimerCommand`` token and does not consider an arm or
cancel settled until the host returns an identified ``TimerCommandApplied``.
Timer maturity is separately identified ingress. Stale generations remain
durable facts but can never authorize a human nudge.
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    ArmedReminderClock,
    ArmingReminderClock,
    ArmReminder,
    CancellingReminderClock,
    CancelReminder,
    CloseFact,
    GateFact,
    NoReminderClock,
    OverdueReminderClock,
    RecoverFact,
    RemBlocked,
    RemEnded,
    RemFault,
    ReminderCyclePaused,
    ReminderCycleStarted,
    ReminderTimer,
    RemLanded,
    RemReq,
    RemState,
    SnoozeFact,
    TimerArmed,
    TimerCancelled,
    TimerCommand,
    TimerCommandApplied,
    TimerDue,
)
from hamsterdan.readiness.net_v5.folding import route, values

GATES = {"rem.gate": ("reminder_gate", ("RemLanded", "RemBlocked", "RemFault"))}


def _timer(st: RemState, incarnation: int, sequence: int, head: str) -> ReminderTimer:
    return ReminderTimer(
        id=f"timer:{st.subject}:i{incarnation}:s{sequence}",
        incarnation=incarnation,
        sequence=sequence,
        head=head,
    )


def _operation(st: RemState) -> tuple[str, int]:
    generation = st.command_generation + 1
    return f"timer-command:{st.subject}:g{generation}", generation


def _issue_arm(st: RemState, timer: ReminderTimer) -> tuple[RemState, TimerCommand]:
    operation, generation = _operation(st)
    command = TimerCommand(
        operation=operation,
        command=ArmReminder(kind="arm", timer=timer, delay_s=st.delay_s),
    )
    return (
        st.validated_update(
            clock=ArmingReminderClock(kind="arming", timer=timer, operation=operation),
            command_generation=generation,
        ),
        command,
    )


def _issue_cancel(st: RemState, timer: ReminderTimer, reason: str) -> tuple[RemState, TimerCommand]:
    operation, generation = _operation(st)
    command = TimerCommand(
        operation=operation,
        command=CancelReminder(kind="cancel", timer=timer, reason=reason),
    )
    return (
        st.validated_update(
            clock=CancellingReminderClock(
                kind="cancelling",
                timer=timer,
                operation=operation,
                reason=reason,
            ),
            command_generation=generation,
        ),
        command,
    )


def _done(st: RemState) -> RemEnded:
    assert st.closing is not None
    return RemEnded(matured=st.matured, reason=st.closing)


def _settle(st: RemState, outputs, extra: dict):
    if st.closing is not None and not st.pending and isinstance(st.clock, NoReminderClock):
        return route(outputs, {**extra, "rem.done": (_done(st),)})
    return route(outputs, {**extra, "rem.state": (st,)})


def _cycle(binding, outputs):
    fact, st = values(binding, ReminderCycleStarted, RemState)
    if st.closing is not None or fact.incarnation <= st.lifecycle_incarnation:
        return route(outputs, {"rem.state": (st,)})
    desired = _timer(st, fact.incarnation, 0, fact.head)
    st = st.validated_update(
        lifecycle_incarnation=fact.incarnation,
        lifecycle_head=fact.head,
        lifecycle_active=True,
        desired_timer=desired,
        delay_s=fact.delay_s,
    )
    if isinstance(st.clock, (ArmingReminderClock, CancellingReminderClock)):
        return route(outputs, {"rem.state": (st,)})
    if isinstance(st.clock, ArmedReminderClock) and st.clock.timer == desired:
        return route(outputs, {"rem.state": (st,)})
    st, command = _issue_arm(st, desired)
    return route(outputs, {"rem.state": (st,), "rem.commands": (command,)})


def _pause(binding, outputs):
    fact, st = values(binding, ReminderCyclePaused, RemState)
    if fact.incarnation < st.lifecycle_incarnation or (
        fact.incarnation == st.lifecycle_incarnation and not st.lifecycle_active
    ):
        return route(outputs, {"rem.state": (st,)})
    st = st.validated_update(
        lifecycle_incarnation=fact.incarnation,
        lifecycle_head=fact.head,
        lifecycle_active=False,
        desired_timer=None,
    )
    if isinstance(st.clock, ArmedReminderClock):
        st, command = _issue_cancel(st, st.clock.timer, fact.reason)
        return route(outputs, {"rem.state": (st,), "rem.commands": (command,)})
    if isinstance(st.clock, OverdueReminderClock):
        st = st.validated_update(clock=NoReminderClock(kind="none"))
    return _settle(st, outputs, {})


def _command_applied(binding, outputs):
    ack, issued, st = values(binding, TimerCommandApplied, TimerCommand, RemState)
    expected_timer = issued.command.timer
    if ack.operation != issued.operation or ack.result.timer != expected_timer:
        # A malformed/stale acknowledgement drains without stealing custody of
        # the one real command. The host can still return the exact ack later.
        return route(outputs, {"rem.state": (st,), "rem.commands": (issued,)})

    if isinstance(issued.command, ArmReminder) and isinstance(ack.result, TimerArmed):
        st = st.validated_update(
            clock=ArmedReminderClock(kind="armed", timer=ack.result.timer, due_at=ack.result.due_at)
        )
        if st.desired_timer == ack.result.timer and st.closing is None:
            return route(outputs, {"rem.state": (st,)})
        if st.desired_timer is None:
            reason = st.closing if st.closing is not None else "draft"
            st, command = _issue_cancel(st, ack.result.timer, reason)
        else:
            st, command = _issue_arm(st, st.desired_timer)
        return route(outputs, {"rem.state": (st,), "rem.commands": (command,)})

    if isinstance(issued.command, CancelReminder) and isinstance(ack.result, TimerCancelled):
        st = st.validated_update(clock=NoReminderClock(kind="none"))
        if st.desired_timer is not None and st.closing is None:
            st, command = _issue_arm(st, st.desired_timer)
            return route(outputs, {"rem.state": (st,), "rem.commands": (command,)})
        return _settle(st, outputs, {})

    return route(outputs, {"rem.state": (st,), "rem.commands": (issued,)})


def _next_after(st: RemState, timer: ReminderTimer) -> tuple[RemState, TimerCommand]:
    desired = _timer(st, timer.incarnation, timer.sequence + 1, timer.head)
    st = st.validated_update(desired_timer=desired)
    return _issue_arm(st, desired)


def _request_nudge(st: RemState, timer_id: str) -> tuple[RemState, RemReq | None]:
    if timer_id in st.pending or timer_id in st.blocked or timer_id in st.faulted:
        return st, None
    return st.validated_update(pending={**st.pending, timer_id: True}), RemReq(timer_id=timer_id)


def _mature(binding, outputs):
    due, st = values(binding, TimerDue, RemState)
    timer_id = due.timer.id
    st = st.validated_update(matured=(*st.matured, timer_id))
    if (
        not isinstance(st.clock, ArmedReminderClock)
        or st.clock.timer != due.timer
        or st.clock.due_at != due.due_at
        or st.closing is not None
    ):
        return route(outputs, {"rem.state": (st,)})

    if st.snoozed:
        st = st.validated_update(
            desired_timer=None,
            clock=OverdueReminderClock(
                kind="overdue",
                timer=due.timer,
                due_at=due.due_at,
                matured_at=due.matured_at,
            ),
        )
        return route(outputs, {"rem.state": (st,)})

    st, request = _request_nudge(st, timer_id)
    st, command = _next_after(st, due.timer)
    emitted = {"rem.state": (st,), "rem.commands": (command,)}
    if request is not None:
        emitted["rem.pub_req"] = (request,)
    return route(outputs, emitted)


def _snooze(binding, outputs):
    fact, st = values(binding, SnoozeFact, RemState)
    if fact.mode == "snooze":
        return route(outputs, {"rem.state": (st.validated_update(snoozed=True),)})

    st = st.validated_update(snoozed=False)
    if not isinstance(st.clock, OverdueReminderClock) or st.closing is not None:
        return route(outputs, {"rem.state": (st,)})
    timer = st.clock.timer
    st, request = _request_nudge(st, timer.id)
    st, command = _next_after(st, timer)
    emitted = {"rem.state": (st,), "rem.commands": (command,)}
    if request is not None:
        emitted["rem.pub_req"] = (request,)
    return route(outputs, emitted)


def _fold_landed(binding, outputs):
    out, st = values(binding, RemLanded, RemState)
    st = st.validated_update(
        pending={key: value for key, value in st.pending.items() if key != out.timer_id},
        blocked={key: value for key, value in st.blocked.items() if key != out.timer_id},
    )
    fact = GateFact(kind="reminder", incarnation=0, body={"timer_id": out.timer_id})
    return _settle(st, outputs, {"dash.facts": (fact,)})


def _fold_blocked(binding, outputs):
    out, st = values(binding, RemBlocked, RemState)
    st = st.validated_update(
        pending={key: value for key, value in st.pending.items() if key != out.timer_id},
        blocked={**st.blocked, out.timer_id: True},
    )
    return _settle(st, outputs, {})


def _fold_fault(binding, outputs):
    out, st = values(binding, RemFault, RemState)
    st = st.validated_update(
        pending={key: value for key, value in st.pending.items() if key != out.timer_id},
        faulted={**st.faulted, out.timer_id: out.reason},
    )
    fact = GateFact(kind="fault", incarnation=0, body={"where": "reminder", "reason": out.reason})
    return _settle(st, outputs, {"dash.facts": (fact,)})


def _recover(binding, outputs):
    fact, st = values(binding, RecoverFact, RemState)
    if (
        fact.target != "reminder"
        or not fact.op.startswith("reminder:")
        or (timer_id := fact.op.removeprefix("reminder:")) not in st.blocked
        or st.closing is not None
    ):
        return route(outputs, {"rem.state": (st,)})
    st = st.validated_update(
        pending={**st.pending, timer_id: True},
        blocked={key: value for key, value in st.blocked.items() if key != timer_id},
    )
    return route(outputs, {"rem.state": (st,), "rem.pub_req": (RemReq(timer_id=timer_id),)})


def _end(binding, outputs):
    close, st = values(binding, CloseFact, RemState)
    st = st.validated_update(closing=close.reason, desired_timer=None)
    if isinstance(st.clock, ArmedReminderClock):
        st, command = _issue_cancel(st, st.clock.timer, close.reason)
        return route(outputs, {"rem.state": (st,), "rem.commands": (command,)})
    if isinstance(st.clock, OverdueReminderClock):
        st = st.validated_update(clock=NoReminderClock(kind="none"))
    return _settle(st, outputs, {})


def _drain_timer(binding, outputs):
    due, ended = values(binding, TimerDue, RemEnded)
    return route(outputs, {"rem.done": (ended.validated_update(matured=(*ended.matured, due.timer.id)),)})


def _drain(binding, outputs, fact_type):
    _, ended = values(binding, fact_type, RemEnded)
    return route(outputs, {"rem.done": (ended,)})


def declare(s) -> None:
    rem = s.rem
    rem.p.cycles(ReminderCycleStarted)
    rem.p.pauses(ReminderCyclePaused)
    rem.p.timers(TimerDue)
    rem.p.acks(TimerCommandApplied)
    rem.p.commands(TimerCommand)
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
    rem, dash = net.s.rem, net.s.dash
    net.t.on_timer >> rem.p.timers
    net.t.on_timer_command_applied >> rem.p.acks

    ((rem.p.cycles, rem.p.state) >> rem.t.cycle(handler=petri_handler(_cycle)) >> (rem.p.state, rem.p.commands))
    (
        (rem.p.pauses, rem.p.state)
        >> rem.t.pause(handler=petri_handler(_pause))
        >> (rem.p.state, rem.p.commands, rem.p.done)
    )
    (
        (rem.p.acks, rem.p.commands, rem.p.state)
        >> rem.t.command_applied(handler=petri_handler(_command_applied))
        >> (rem.p.state, rem.p.commands, rem.p.done)
    )
    (
        (rem.p.timers, rem.p.state)
        >> rem.t.mature(handler=petri_handler(_mature))
        >> (rem.p.state, rem.p.pub_req, rem.p.commands)
    )
    (
        (rem.p.snoozes, rem.p.state)
        >> rem.t.snooze(handler=petri_handler(_snooze))
        >> (rem.p.state, rem.p.pub_req, rem.p.commands)
    )
    (rem.p.pub_req >> rem.t.gate(handler="reminder_gate") >> (rem.p.rlanded, rem.p.rblocked, rem.p.rfault))
    (
        (rem.p.rlanded, rem.p.state)
        >> rem.t.fold_landed(handler=petri_handler(_fold_landed))
        >> (rem.p.state, dash.p.facts, rem.p.done)
    )
    (
        (rem.p.rblocked, rem.p.state)
        >> rem.t.fold_blocked(handler=petri_handler(_fold_blocked))
        >> (rem.p.state, rem.p.done)
    )
    (
        (rem.p.rfault, rem.p.state)
        >> rem.t.fold_fault(handler=petri_handler(_fold_fault))
        >> (rem.p.state, dash.p.facts, rem.p.done)
    )
    ((rem.p.recover, rem.p.state) >> rem.t.recovery(handler=petri_handler(_recover)) >> (rem.p.state, rem.p.pub_req))
    ((rem.p.closed, rem.p.state) >> rem.t.end(handler=petri_handler(_end)) >> (rem.p.state, rem.p.commands, rem.p.done))

    ((rem.p.timers, rem.p.done) >> rem.t.drain_timer(handler=petri_handler(_drain_timer)) >> rem.p.done)
    (
        (rem.p.cycles, rem.p.done)
        >> rem.t.drain_cycle(handler=petri_handler(lambda b, o: _drain(b, o, ReminderCycleStarted)))
        >> rem.p.done
    )
    (
        (rem.p.pauses, rem.p.done)
        >> rem.t.drain_pause(handler=petri_handler(lambda b, o: _drain(b, o, ReminderCyclePaused)))
        >> rem.p.done
    )
    (
        (rem.p.snoozes, rem.p.done)
        >> rem.t.drain_snooze(handler=petri_handler(lambda b, o: _drain(b, o, SnoozeFact)))
        >> rem.p.done
    )
    (
        (rem.p.recover, rem.p.done)
        >> rem.t.drain_recover(handler=petri_handler(lambda b, o: _drain(b, o, RecoverFact)))
        >> rem.p.done
    )
    (
        (rem.p.acks, rem.p.done)
        >> rem.t.drain_ack(handler=petri_handler(lambda b, o: _drain(b, o, TimerCommandApplied)))
        >> rem.p.done
    )


def seed(subject: str = "unscoped") -> dict:
    baton = RemState(
        subject=subject,
        lifecycle_incarnation=0,
        lifecycle_head="",
        lifecycle_active=False,
        desired_timer=None,
        clock=NoReminderClock(kind="none"),
        command_generation=0,
        delay_s=3 * 24 * 60 * 60,
        matured=(),
        snoozed=False,
        pending={},
        blocked={},
        faulted={},
        closing=None,
    )
    return {NetPath("rem.state"): (Token("RemState", baton.dump()),)}
