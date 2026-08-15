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
    drive,
    one,
    projection,
    release_one,
    see_head,
    spawn,
    spawn_held,
    tokens,
    world_of,
)


def state(engine) -> dict:
    return one(engine, "rem.state")


def nudges(world: dict) -> list[str]:
    return [c["key"] for c in world["comments"] if c["kind"] == "reminder"]


def mature(engine, due: dict | None = None) -> tuple[str, dict]:
    if due is None:
        if state(engine)["clock"]["kind"] == "none":
            see_head(engine, "h1")
        if state(engine)["clock"]["kind"] == "arming":
            acknowledge_arm(engine)
        clock = state(engine)["clock"]
        due = {
            "timer": clock["timer"],
            "due_at": clock["due_at"],
            "matured_at": "2026-08-16T00:00:01Z",
        }
    deliver(engine, "on_timer", "TimerDue", due)
    return due["timer"]["id"], due


def mature_held(engine, dispatch, definitions, due: dict | None = None, *, hold=frozenset()) -> tuple[str, dict]:
    if due is None:
        if state(engine)["clock"]["kind"] == "none":
            deliver_held(
                engine,
                dispatch,
                definitions,
                "on_head",
                "HeadSeen",
                {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
                hold=hold,
            )
        issued = command(engine)
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_timer_command_applied",
            "TimerCommandApplied",
            {
                "operation": issued["operation"],
                "result": {
                    "kind": "armed",
                    "timer": issued["command"]["timer"],
                    "due_at": "2026-08-16T00:00:00Z",
                },
            },
            hold=hold,
        )
        clock = state(engine)["clock"]
        due = {
            "timer": clock["timer"],
            "due_at": clock["due_at"],
            "matured_at": "2026-08-16T00:00:01Z",
        }
    deliver_held(engine, dispatch, definitions, "on_timer", "TimerDue", due, hold=hold)
    return due["timer"]["id"], due


def command(engine) -> dict:
    return one(engine, "rem.commands")


def acknowledge_arm(engine, *, due_at: str = "2026-08-16T00:00:00Z") -> dict:
    issued = command(engine)
    assert issued["command"]["kind"] == "arm"
    deliver(
        engine,
        "on_timer_command_applied",
        "TimerCommandApplied",
        {
            "operation": issued["operation"],
            "result": {
                "kind": "armed",
                "timer": issued["command"]["timer"],
                "due_at": due_at,
            },
        },
    )
    return issued["command"]["timer"]


def acknowledge_cancel(engine) -> dict:
    issued = command(engine)
    assert issued["command"]["kind"] == "cancel"
    deliver(
        engine,
        "on_timer_command_applied",
        "TimerCommandApplied",
        {
            "operation": issued["operation"],
            "result": {"kind": "cancelled", "timer": issued["command"]["timer"]},
        },
    )
    return issued["command"]["timer"]


def acknowledge_held(engine, dispatch, definitions, *, hold=frozenset()) -> str:
    issued = command(engine)
    kind = issued["command"]["kind"]
    result = {"kind": "cancelled", "timer": issued["command"]["timer"]}
    if kind == "arm":
        result = {**result, "kind": "armed", "due_at": "2026-08-17T00:00:00Z"}
    deliver_held(
        engine,
        dispatch,
        definitions,
        "on_timer_command_applied",
        "TimerCommandApplied",
        {"operation": issued["operation"], "result": result},
        hold=hold,
    )
    return kind


# -- durable host command protocol -------------------------------------------


class TestTimerCommands:
    def test_new_cycle_issues_one_globally_scoped_arm_and_waits_for_ack(self) -> None:
        engine, _ = spawn(instance="owner/repo#42")
        see_head(engine, "h1")

        issued = command(engine)
        assert issued == {
            "operation": "timer-command:test:owner/repo#42:g1",
            "command": {
                "kind": "arm",
                "timer": {
                    "id": "timer:test:owner/repo#42:i1:s0",
                    "incarnation": 1,
                    "sequence": 0,
                    "head": "h1",
                },
                "delay_s": 259200,
            },
        }
        assert state(engine)["clock"]["kind"] == "arming"

        timer = acknowledge_arm(engine)
        assert tokens(engine, "rem.commands") == []
        assert state(engine)["clock"] == {
            "kind": "armed",
            "timer": timer,
            "due_at": "2026-08-16T00:00:00Z",
        }

    def test_draft_during_unacknowledged_arm_cancels_only_after_arm_ack(self) -> None:
        engine, _ = spawn(instance="owner/repo#42")
        see_head(engine, "h1")
        arm = command(engine)

        deliver(engine, "on_draft", "DraftSeen", {})
        assert command(engine) == arm  # one persistent command token
        assert state(engine)["desired_timer"] is None

        timer = acknowledge_arm(engine)
        cancel = command(engine)
        assert cancel["operation"] == "timer-command:test:owner/repo#42:g2"
        assert cancel["command"] == {"kind": "cancel", "timer": timer, "reason": "draft"}

    def test_defer_is_finding_disposition_not_timer_duration(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "defer", arg="finding-7")
        assert one(engine, "review.memory")["dismissed"] == ["finding-7"]
        assert command(engine)["command"]["kind"] == "arm"


class TestLifecycleMailOrdering:
    @staticmethod
    def cycle(incarnation: int, head: str) -> tuple[str, str, dict]:
        return (
            "rem.cycles",
            "ReminderCycleStarted",
            {"incarnation": incarnation, "head": head, "delay_s": 259200},
        )

    @staticmethod
    def pause(incarnation: int, head: str) -> tuple[str, str, dict]:
        return (
            "rem.pauses",
            "ReminderCyclePaused",
            {"incarnation": incarnation, "head": head, "reason": "draft"},
        )

    def test_pause_dominates_start_at_the_same_incarnation(self) -> None:
        for mail in (
            (self.cycle(1, "h1"), self.pause(1, "h1")),
            (self.pause(1, "h1"), self.cycle(1, "h1")),
        ):
            engine, _ = spawn(initial_mail=mail)
            drive(engine)
            st = state(engine)
            assert st["lifecycle_incarnation"] == 1
            assert st["lifecycle_active"] is False
            assert st["desired_timer"] is None

    def test_newer_resume_dominates_an_older_pause_in_either_mail_order(self) -> None:
        for mail in (
            (self.cycle(2, "h2"), self.pause(1, "h1")),
            (self.pause(1, "h1"), self.cycle(2, "h2")),
        ):
            engine, _ = spawn(initial_mail=mail)
            drive(engine)
            st = state(engine)
            assert (st["lifecycle_incarnation"], st["lifecycle_head"], st["lifecycle_active"]) == (2, "h2", True)
            assert st["desired_timer"]["id"].endswith(":i2:s0")

    def test_newest_start_wins_and_old_command_ack_reconciles_to_it(self) -> None:
        engine, _ = spawn(initial_mail=(self.cycle(1, "h1"), self.cycle(2, "h2")))
        drive(engine)
        assert state(engine)["desired_timer"]["id"].endswith(":i2:s0")
        first = command(engine)
        acknowledge_arm(engine)
        if first["command"]["timer"]["incarnation"] == 1:
            assert command(engine)["command"]["timer"]["incarnation"] == 2
        else:
            assert tokens(engine, "rem.commands") == []

        reversed_engine, _ = spawn(initial_mail=(self.cycle(2, "h2"), self.cycle(1, "h1")))
        drive(reversed_engine)
        assert state(reversed_engine)["desired_timer"]["id"].endswith(":i2:s0")
        assert command(reversed_engine)["command"]["timer"]["incarnation"] == 2


# -- maturity and the nudge ----------------------------------------------------


class TestMaturity:
    def test_a_matured_timer_nudges_exactly_once(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        timer_id, _ = mature(engine)
        st = state(engine)
        assert st["matured"] == [timer_id]  # the fact is durable
        assert st["pending"] == {}  # the round settled
        assert nudges(world) == [f"reminder:{timer_id}"]
        # the landed nudge is a dashboard fact
        assert {"kind": "reminder", "body": {"timer_id": timer_id}} in projection(engine)

    def test_a_repeated_maturity_reconciles_lookup_first(self) -> None:
        # at-least-once delivery: the SAME timer matures again after the
        # nudge landed — the gate finds the effect and never reposts
        engine, _ = spawn()
        world = world_of(engine)
        timer_id, due = mature(engine)
        mature(engine, due)
        st = state(engine)
        assert st["matured"] == [timer_id, timer_id]  # both facts recorded
        assert nudges(world) == [f"reminder:{timer_id}"]  # one effect

    def test_pending_custody_is_single_flight_and_the_baton_stays_available(self) -> None:
        # while a nudge is in flight the baton records Pending: a
        # duplicate maturity cannot double the effect, yet the baton
        # stays available — a snooze still folds mid-flight
        engine, _, dispatch, definitions = spawn_held()
        hold = frozenset({"reminder_gate"})
        timer_id, due = mature_held(engine, dispatch, definitions, hold=hold)
        assert state(engine)["pending"] == {timer_id: True}
        # duplicate maturity while in flight: recorded, NOT re-requested
        mature_held(engine, dispatch, definitions, due, hold=hold)
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
        assert st["matured"] == [timer_id, timer_id]  # the fact is durable, twice
        assert st["snoozed"] is True  # folded while the gate was held
        pending = [i for i in dispatch.pending.values() if i.activity == "reminder_gate"]
        assert len(pending) == 1  # exactly ONE in-flight reminder effect
        release_one(engine, dispatch, definitions, "reminder_gate")
        assert state(engine)["pending"] == {}
        assert nudges(world_of(engine)) == [f"reminder:{timer_id}"]


# -- snooze / clear / defer ------------------------------------------------------


class TestSnooze:
    def test_snooze_suppresses_the_decision_never_the_fact(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        comment(engine, "c1", "snooze", arg="all")
        timer_1, _ = mature(engine)
        st = state(engine)
        assert st["matured"] == [timer_1]  # the maturity is recorded
        assert nudges(world) == []  # the nudge is suppressed
        # resume publishes the held overdue reminder and rearms the next one
        comment(engine, "c2", "resume", arg="all")
        assert nudges(world) == [f"reminder:{timer_1}"]
        timer_2, _ = mature(engine)
        assert nudges(world) == [f"reminder:{timer_1}", f"reminder:{timer_2}"]
        assert state(engine)["matured"] == [timer_1, timer_2]

    def test_defer_does_not_change_the_reminder_clock(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        before = command(engine)
        comment(engine, "c1", "defer", arg="f-h1")
        assert command(engine) == before
        assert state(engine)["snoozed"] is False


# -- blocked / faulted custody and exact recovery ------------------------------


class TestBlockedAndRecovery:
    def test_retryable_exhaustion_blocks_and_recovers_under_the_same_identity(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        timer_id, _ = mature(engine)
        st = state(engine)
        assert st["blocked"] == {timer_id: True}  # retained, fail-closed
        assert st["pending"] == {}
        assert nudges(world) == []
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", arg=f"reminder:{timer_id}")
        st = state(engine)
        assert st["blocked"] == {} and st["pending"] == {}
        assert nudges(world) == [f"reminder:{timer_id}"]  # the SAME identity, once

    def test_unknown_terminal_faults_and_never_reopens_by_maturity(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        timer_1, due_1 = mature(engine)
        st = state(engine)
        assert st["faulted"] == {timer_1: "unknown"}  # reason retained (A2)
        assert st["pending"] == {}
        # the fault is a dashboard fact
        assert {"kind": "fault", "body": {"where": "reminder", "reason": "unknown"}} in projection(engine)
        # an unrelated timer proceeds; the fault stays exactly as retained
        world["comments_mode"] = None
        timer_2, _ = mature(engine)
        st = state(engine)
        assert st["faulted"] == {timer_1: "unknown"}
        assert nudges(world) == [f"reminder:{timer_2}"]
        # a duplicate maturity of the FAULTED timer never reopens it
        mature(engine, due_1)
        assert nudges(world) == [f"reminder:{timer_2}"]

    def test_recovery_requires_the_exact_operation_syntax(self) -> None:
        # a blocked timer is not recoverable by the malformed bare prefix
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        timer_id, _ = mature(engine)
        assert state(engine)["blocked"] == {timer_id: True}
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", arg="reminder")
        assert state(engine)["blocked"] == {timer_id: True}  # inert
        assert nudges(world) == []
        comment(engine, "c2", "recover_publication", arg=f"reminder:{timer_id}")
        assert state(engine)["blocked"] == {}
        assert nudges(world) == [f"reminder:{timer_id}"]

    def test_recovery_of_a_faulted_timer_is_a_blocked_only_door(self) -> None:
        # the recover door reopens BLOCKED timers only — settled
        # terminal policy: an unknown publication terminal is a
        # nonrecoverable workflow fault, retained with its reason and
        # surfaced on the dashboard for the human
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        timer_id, _ = mature(engine)
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", arg=f"reminder:{timer_id}")
        st = state(engine)
        assert st["faulted"] == {timer_id: "unknown"}  # untouched
        assert nudges(world) == []


# -- close ----------------------------------------------------------------------


class TestClose:
    def test_close_retires_the_loop_with_the_maturity_log(self) -> None:
        engine, _ = spawn()
        timer_id, _ = mature(engine)
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        acknowledge_arm(engine)
        acknowledge_cancel(engine)
        assert tokens(engine, "rem.state") == []  # the baton retired
        done = one(engine, "rem.done")
        assert done["reason"] == "merged"
        assert done["matured"] == [timer_id]

    def test_close_while_a_nudge_is_in_flight_settles_exactly_once(self) -> None:
        # A3: the terminal is outstanding — close records its intent and
        # the LAST terminal fold finalizes the loop, exactly once
        engine, _, dispatch, definitions = spawn_held()
        hold = frozenset({"reminder_gate"})
        timer_id, _ = mature_held(engine, dispatch, definitions, hold=hold)
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=hold)
        assert tokens(engine, "rem.done") == []  # deferred: terminal is out
        assert state(engine)["closing"] == "merged"
        release_one(engine, dispatch, definitions, "reminder_gate")
        assert acknowledge_held(engine, dispatch, definitions) == "arm"
        assert acknowledge_held(engine, dispatch, definitions) == "cancel"
        [done] = tokens(engine, "rem.done")  # exactly one end
        assert done["reason"] == "merged"
        assert tokens(engine, "rem.state") == []  # no zombie custody
        # the terminal settled BEFORE the end: the effect landed
        assert nudges(world_of(engine)) == [f"reminder:{timer_id}"]

    def test_close_with_an_empty_reason_still_settles_a_deferred_close(self) -> None:
        # an EMPTY close reason is still a close: the closing sentinel
        # must be distinct (None), or the deferred close would never
        # finalize after the outstanding terminal settles — the close
        # token is already consumed, and the loop would wedge forever
        engine, _, dispatch, definitions = spawn_held()
        hold = frozenset({"reminder_gate"})
        mature_held(engine, dispatch, definitions, hold=hold)
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": ""}, hold=hold)
        assert tokens(engine, "rem.done") == []  # deferred: terminal is out
        release_one(engine, dispatch, definitions, "reminder_gate")
        assert acknowledge_held(engine, dispatch, definitions) == "arm"
        assert acknowledge_held(engine, dispatch, definitions) == "cancel"
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
        stale = {
            "timer": {"id": "t9", "incarnation": 9, "sequence": 0, "head": "stale"},
            "due_at": "2026-08-16T00:00:00Z",
            "matured_at": "2026-08-16T00:00:01Z",
        }
        mature(engine, stale)
        done = one(engine, "rem.done")
        assert done["matured"] == ["t9"]  # recorded on the record
        assert nudges(world) == []  # never nudged
        assert tokens(engine, "rem.timers") == []  # absorbed, not stranded

    def test_late_snoozes_and_recoveries_after_close_are_inert(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        timer_id, _ = mature(engine)  # blocked, retained
        world["comments_mode"] = None
        deliver(engine, "on_close", "CloseSeen", {"reason": "closed"})
        acknowledge_arm(engine)
        acknowledge_cancel(engine)
        done_before = one(engine, "rem.done")
        comment(engine, "c1", "snooze", arg="all")
        comment(engine, "c2", "recover_publication", arg=f"reminder:{timer_id}")
        assert one(engine, "rem.done") == done_before  # nothing changed
        assert nudges(world) == []  # the abandoned block never reissues
        assert tokens(engine, "rem.snoozes") == []  # absorbed
        assert tokens(engine, "rem.recover") == []  # absorbed
