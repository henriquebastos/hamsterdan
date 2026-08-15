"""Executable contract tests for the V5 reminders loop.

The reminders loop owns the RemState baton. Every TimerDue is recorded
as a durable maturity fact; snooze and close suppress only the nudge
DECISION. Custody is per-timer data in the baton (A2): pending marks a
nudge in flight — single-flight per timer, yet the baton stays
available so a snooze folds mid-flight. Blocked timers recover through
the `rem.recover` door under the same effect identity; faulted timers
stay fail-closed and never reopen by maturity alone. Close defers while
terminals are outstanding (A3) and the LAST terminal fold finalizes.
"""

from harness import (
    comment,
    deliver,
    deliver_held,
    one,
    projection,
    release_one,
    spawn,
    spawn_held,
    tokens,
    world_of,
)


def state(engine) -> dict:
    return one(engine, "rem.state")


def nudges(world: dict) -> list[str]:
    return [c["key"] for c in world["comments"] if c["kind"] == "reminder"]


def mature(engine, timer_id: str) -> None:
    deliver(engine, "on_timer", "TimerDue", {"timer_id": timer_id})


def mature_held(engine, dispatch, definitions, timer_id: str, *, hold=frozenset()) -> None:
    deliver_held(engine, dispatch, definitions, "on_timer", "TimerDue", {"timer_id": timer_id}, hold=hold)


# -- maturity and the nudge ----------------------------------------------------


class TestMaturity:
    def test_a_matured_timer_nudges_exactly_once(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        mature(engine, "t1")
        st = state(engine)
        assert st["matured"] == ["t1"]  # the fact is durable
        assert st["pending"] == {}  # the round settled
        assert nudges(world) == ["reminder:t1"]
        # the landed nudge is a dashboard fact
        assert {"kind": "reminder", "body": {"timer_id": "t1"}} in projection(engine)

    def test_a_repeated_maturity_reconciles_lookup_first(self) -> None:
        # at-least-once delivery: the SAME timer matures again after the
        # nudge landed — the gate finds the effect and never reposts
        engine, _ = spawn()
        world = world_of(engine)
        mature(engine, "t1")
        mature(engine, "t1")
        st = state(engine)
        assert st["matured"] == ["t1", "t1"]  # both facts recorded
        assert nudges(world) == ["reminder:t1"]  # one effect

    def test_pending_custody_is_single_flight_and_the_baton_stays_available(self) -> None:
        # while a nudge is in flight the baton records Pending: a
        # duplicate maturity cannot double the effect, yet the baton
        # stays available — a snooze still folds mid-flight
        engine, _, dispatch, definitions = spawn_held()
        hold = frozenset({"reminder_gate"})
        mature_held(engine, dispatch, definitions, "t1", hold=hold)
        assert state(engine)["pending"] == {"t1": True}
        # duplicate maturity while in flight: recorded, NOT re-requested
        mature_held(engine, dispatch, definitions, "t1", hold=hold)
        # the baton is available mid-flight: a snooze folds NOW
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_comment",
            "CommentSeen",
            {"id": "c1", "kind": "snooze", "arg": "t1", "authorized": True},
            hold=hold,
        )
        st = state(engine)
        assert st["matured"] == ["t1", "t1"]  # the fact is durable, twice
        assert st["snoozed"] is True  # folded while the gate was held
        pending = [i for i in dispatch.pending.values() if i.activity == "reminder_gate"]
        assert len(pending) == 1  # exactly ONE in-flight reminder effect
        release_one(engine, dispatch, definitions, "reminder_gate")
        assert state(engine)["pending"] == {}
        assert nudges(world_of(engine)) == ["reminder:t1"]


# -- snooze / clear / defer ------------------------------------------------------


class TestSnooze:
    def test_snooze_suppresses_the_decision_never_the_fact(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        comment(engine, "c1", "snooze", arg="all")
        mature(engine, "t1")
        st = state(engine)
        assert st["matured"] == ["t1"]  # the maturity is recorded
        assert nudges(world) == []  # the nudge is suppressed
        # resume: the NEXT maturity nudges again
        comment(engine, "c2", "resume", arg="all")
        mature(engine, "t2")
        assert nudges(world) == ["reminder:t2"]
        assert state(engine)["matured"] == ["t1", "t2"]

    def test_defer_records_the_request_for_the_host(self) -> None:
        # the host owns timer arming: the net records the deferral fact
        engine, _ = spawn()
        comment(engine, "c1", "defer", arg="t1:2d")
        st = state(engine)
        assert st["deferred"] == ["t1:2d"]
        assert st["snoozed"] is False  # deferring is not snoozing


# -- blocked / faulted custody and exact recovery ------------------------------


class TestBlockedAndRecovery:
    def test_retryable_exhaustion_blocks_and_recovers_under_the_same_identity(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        mature(engine, "t1")
        st = state(engine)
        assert st["blocked"] == {"t1": True}  # retained, fail-closed
        assert st["pending"] == {}
        assert nudges(world) == []
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", arg="reminder:t1")
        st = state(engine)
        assert st["blocked"] == {} and st["pending"] == {}
        assert nudges(world) == ["reminder:t1"]  # the SAME identity, once

    def test_unknown_terminal_faults_and_never_reopens_by_maturity(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        mature(engine, "t1")
        st = state(engine)
        assert st["faulted"] == {"t1": "unknown"}  # reason retained (A2)
        assert st["pending"] == {}
        # the fault is a dashboard fact
        assert {"kind": "fault", "body": {"where": "reminder", "reason": "unknown"}} in projection(engine)
        # an unrelated timer proceeds; the fault stays exactly as retained
        world["comments_mode"] = None
        mature(engine, "t2")
        st = state(engine)
        assert st["faulted"] == {"t1": "unknown"}
        assert nudges(world) == ["reminder:t2"]
        # a duplicate maturity of the FAULTED timer never reopens it
        mature(engine, "t1")
        assert nudges(world) == ["reminder:t2"]

    def test_recovery_requires_the_exact_operation_syntax(self) -> None:
        # a blocked timer literally named "reminder" must not be
        # recoverable by the malformed op "reminder" — only the exact
        # operation "reminder:reminder" names it
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        mature(engine, "reminder")
        assert state(engine)["blocked"] == {"reminder": True}
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", arg="reminder")
        assert state(engine)["blocked"] == {"reminder": True}  # inert
        assert nudges(world) == []
        comment(engine, "c2", "recover_publication", arg="reminder:reminder")
        assert state(engine)["blocked"] == {}
        assert nudges(world) == ["reminder:reminder"]

    def test_recovery_of_a_faulted_timer_is_a_blocked_only_door(self) -> None:
        # the recover door reopens BLOCKED timers only — settled
        # terminal policy: an unknown publication terminal is a
        # nonrecoverable workflow fault, retained with its reason and
        # surfaced on the dashboard for the human
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        mature(engine, "t1")
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", arg="reminder:t1")
        st = state(engine)
        assert st["faulted"] == {"t1": "unknown"}  # untouched
        assert nudges(world) == []


# -- close ----------------------------------------------------------------------


class TestClose:
    def test_close_retires_the_loop_with_the_maturity_log(self) -> None:
        engine, _ = spawn()
        mature(engine, "t1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        assert tokens(engine, "rem.state") == []  # the baton retired
        done = one(engine, "rem.done")
        assert done["reason"] == "merged"
        assert done["matured"] == ["t1"]

    def test_close_while_a_nudge_is_in_flight_settles_exactly_once(self) -> None:
        # A3: the terminal is outstanding — close records its intent and
        # the LAST terminal fold finalizes the loop, exactly once
        engine, _, dispatch, definitions = spawn_held()
        hold = frozenset({"reminder_gate"})
        mature_held(engine, dispatch, definitions, "t1", hold=hold)
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=hold)
        assert tokens(engine, "rem.done") == []  # deferred: terminal is out
        assert state(engine)["closing"] == "merged"
        release_one(engine, dispatch, definitions, "reminder_gate")
        [done] = tokens(engine, "rem.done")  # exactly one end
        assert done["reason"] == "merged"
        assert tokens(engine, "rem.state") == []  # no zombie custody
        # the terminal settled BEFORE the end: the effect landed
        assert nudges(world_of(engine)) == ["reminder:t1"]

    def test_close_with_an_empty_reason_still_settles_a_deferred_close(self) -> None:
        # an EMPTY close reason is still a close: the closing sentinel
        # must be distinct (None), or the deferred close would never
        # finalize after the outstanding terminal settles — the close
        # token is already consumed, and the loop would wedge forever
        engine, _, dispatch, definitions = spawn_held()
        hold = frozenset({"reminder_gate"})
        mature_held(engine, dispatch, definitions, "t1", hold=hold)
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": ""}, hold=hold)
        assert tokens(engine, "rem.done") == []  # deferred: terminal is out
        release_one(engine, dispatch, definitions, "reminder_gate")
        [done] = tokens(engine, "rem.done")  # settled, exactly once
        assert done["reason"] == ""
        assert tokens(engine, "rem.state") == []  # no zombie custody

    def test_a_matured_timer_after_close_is_recorded_never_nudged(self) -> None:
        # the host cancels timers at close, but at-least-once means a
        # late maturity can still arrive: it drains into the terminal
        # record — the fact is durable, the decision is gone
        engine, _ = spawn()
        world = world_of(engine)
        deliver(engine, "on_close", "CloseSeen", {"reason": "closed"})
        mature(engine, "t9")
        done = one(engine, "rem.done")
        assert done["matured"] == ["t9"]  # recorded on the record
        assert nudges(world) == []  # never nudged
        assert tokens(engine, "rem.timers") == []  # absorbed, not stranded

    def test_late_snoozes_and_recoveries_after_close_are_inert(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        mature(engine, "t1")  # blocked, retained
        world["comments_mode"] = None
        deliver(engine, "on_close", "CloseSeen", {"reason": "closed"})
        done_before = one(engine, "rem.done")
        comment(engine, "c1", "snooze", arg="all")
        comment(engine, "c2", "recover_publication", arg="reminder:t1")
        assert one(engine, "rem.done") == done_before  # nothing changed
        assert nudges(world) == []  # the abandoned block never reissues
        assert tokens(engine, "rem.snoozes") == []  # absorbed
        assert tokens(engine, "rem.recover") == []  # absorbed
