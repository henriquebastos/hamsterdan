"""ES-004 AX9 focused tests — time as typed ingress.

Claims under test:

- The schedule is derived from the snapshot: arming is idempotent
  work with operation identity, re-derivable after a scheduler loss.
- The fold fences every delivery fault deterministically: duplicate,
  early, stale-sequence, and stale-generation `TimerDue` are inert.
- Production's guard-suppressed-but-matured semantic survives:
  a matured timer fires the moment conditions return (snooze/resume).
- Re-arm on acknowledgment gives "every ≥ DELAY" with sequence-scoped
  operation identity and no flag places.
- Replay is a refold: same events, same snapshot, same decisions,
  no wall clock anywhere.
"""

from __future__ import annotations

from ax9_timer import (
    DELAY,
    ArmTimer,
    ReminderAcknowledged,
    RemindWork,
    Snapshot,
    TimerDue,
    decide,
    fold,
)

T0 = 1_000_000.0

DUE_STATE = dict(
    actions="green",
    review="clear",
    dashboard_current=True,
)


def snap(**kw) -> Snapshot:
    return Snapshot(epoch=3, head="h2", started_at=T0, **kw)


def matured(base: Snapshot) -> Snapshot:
    return fold(base, TimerDue(base.epoch, base.head, base.timer_sequence, base.due_at))


# -- schedule derived from the snapshot -----------------------------------------------------


def test_fresh_generation_arms_sequence_zero_from_admission_instant():
    assert decide(snap()) == (ArmTimer("timer:3:h2:0", T0 + DELAY),)


def test_arming_is_idempotent_and_rederivable_after_scheduler_loss():
    # the scheduler holds no authoritative state: the same snapshot
    # re-emits the same ArmTimer, and the gate dedups by operation id
    assert decide(snap()) == decide(snap())


# -- delivery faults are inert at the fold boundary ------------------------------------------


def test_duplicate_delivery_is_inert():
    once = matured(snap(**DUE_STATE))
    assert fold(once, TimerDue(3, "h2", 0, T0 + DELAY)) == once


def test_early_delivery_is_inert_and_timer_stays_armed():
    early = fold(snap(**DUE_STATE), TimerDue(3, "h2", 0, T0 + DELAY - 1))
    assert not early.timer_matured
    assert decide(early) == (ArmTimer("timer:3:h2:0", T0 + DELAY),)


def test_late_delivery_matures_normally():
    late = fold(snap(**DUE_STATE), TimerDue(3, "h2", 0, T0 + 10 * DELAY))
    assert late.timer_matured


def test_stale_generation_and_stale_sequence_timers_are_inert():
    base = snap(**DUE_STATE)
    assert fold(base, TimerDue(2, "h1", 0, T0 + DELAY)) == base  # prior generation
    assert fold(base, TimerDue(3, "h2", 7, T0 + DELAY)) == base  # never-armed sequence


# -- due-ness is the production predicate over folded facts ----------------------------------


def test_matured_and_wanted_emits_the_reminder_with_sequence_identity():
    ready = matured(snap(**DUE_STATE, reminder_recipient="alice"))
    assert decide(ready) == (RemindWork("reminder:3:h2:0", 0, "alice"),)


def test_review_satisfied_suppresses_the_reminder():
    # human approved + recipient assigned = production's review_satisfied
    satisfied = matured(snap(**DUE_STATE, human_approved=True, reminder_recipient="alice"))
    assert decide(satisfied) == ()


def test_red_states_suppress_the_reminder():
    for regression in (
        dict(actions="failed"),
        dict(review="blocking"),
        dict(dashboard_current=False),
        dict(changes_requested=True),
        dict(conflict=True),
    ):
        state = matured(snap(**{**DUE_STATE, **regression}))
        assert decide(state) == (), regression


# -- cancellation by state change keeps production's matured-guard semantic -------------------


def test_snoozed_matured_timer_fires_the_moment_resume_folds():
    """Production: a matured binding suppressed by its guard fires as
    soon as the guard passes. Here maturity is a durable fact; snooze
    only suppresses the decision."""
    snoozed = matured(snap(**DUE_STATE, reminder_snoozed=True))
    assert decide(snoozed) == ()  # cancelled by state, not by losing the timer
    resumed = fold(snoozed, ReminderAcknowledged(99, T0))  # stale ack — still snoozed
    assert resumed == snoozed
    from dataclasses import replace

    awake = replace(snoozed, reminder_snoozed=False)  # AX7 resume intent folds
    assert decide(awake) == (RemindWork("reminder:3:h2:0", 0, ""),)


# -- repetition, idempotency, recovery -------------------------------------------------------


def test_acknowledgment_rearms_next_sequence_anchored_to_publication():
    fired = matured(snap(**DUE_STATE))
    published_at = T0 + DELAY + 60
    rearmed = fold(fired, ReminderAcknowledged(0, published_at))
    assert not rearmed.timer_matured
    assert rearmed.timer_sequence == 1
    assert decide(rearmed) == (ArmTimer("timer:3:h2:1", published_at + DELAY),)
    # the retired sequence can never fire again:
    assert fold(rearmed, TimerDue(3, "h2", 0, published_at + DELAY)) == rearmed


def test_three_reminders_three_distinct_operations():
    state, operations = snap(**DUE_STATE), []
    for _ in range(3):
        state = matured(state)
        [work] = decide(state)
        operations.append(work.operation)
        state = fold(state, ReminderAcknowledged(work.sequence, state.due_at + 60))
    assert operations == ["reminder:3:h2:0", "reminder:3:h2:1", "reminder:3:h2:2"]


def test_replay_is_a_refold_with_no_wall_clock():
    events = [
        TimerDue(3, "h2", 0, T0 + DELAY),
        ReminderAcknowledged(0, T0 + DELAY + 60),
        TimerDue(3, "h2", 1, T0 + 2 * DELAY + 60),
    ]

    def run():
        state = snap(**DUE_STATE, reminder_recipient="bob")
        return [(state := fold(state, e), decide(state))[1] for e in events]

    assert run() == run()  # deterministic: instants live in the events
    assert run()[-1] == (RemindWork("reminder:3:h2:1", 1, "bob"),)
