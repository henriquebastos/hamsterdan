"""ES-004 AX9 — time as typed ingress: the reminder without 9 read arcs.

Production's `reminder_due` (topology.py:1611-1624) is a transition
with `timers=(Delay(3 days),)` plus NINE read arcs joining the cohort
for its guard `_reminder_due` (topology.py:1184-1198). A `Reminder`
token cycles: seeded at generation start (topology.py:537), consumed
at firing, re-armed via `t.rearm` back to `reminder.p.timer` — each
re-entry resets the Delay anchor, giving "a reminder every ≥3 days
while due".

What Petrus gets RIGHT and this spike keeps: the Delay mechanism is
pure and replay-safe — maturation is derived per binding from the
token's recorded entry instant against a clock watermark, never
stored ("timers-keyed-per-firing-binding-age-anchored",
petrus/impetus/petrinet/enabledness.py:27-34). No coroutine, no timer
state. The engine even derives the wakeup it owes (`next_maturation`).
The timer is NOT the accidental part.

The accidental part is the guard join: 9 read arcs re-assembling the
marking to decide due-ness. AX8 already folds those facts into one
snapshot. So AX9's question: can time arrive as one more typed ingress
— `TimerDue`, a settled fact from a scheduler provider — folding
`timer_matured` into the snapshot, with the reminder decision joining
AX8's pure `decide`?

Semantics preserved from production, verbatim where possible:

- `_reminder_due`'s predicate — snoozed, review-satisfied
  (`human_approved and (recipient or distinct_reviewer_approved or
  human_requested)`), changes requested, dashboard current, actions
  green, review clear, conflict — is `reminder_wanted` below.
  Authority currency and the in-flight flags drop for the AX8
  reasons: generation scoping fences staleness; in-flight is an
  unfolded exit.
- A guard-suppressed matured timer fires the moment conditions
  return (production: the matured binding just sits there until the
  guard passes). Here: `timer_matured` is a durable folded fact; the
  reminder emits whenever matured AND wanted.
- Sequence numbering and operation identity:
  `operation("reminder", ..., sequence=n)` becomes
  `reminder:{epoch}:{head}:{n}`.

One deliberate divergence, named: production re-arms at FIRING
(`_remind` routes `Reminder(seq+1)` to rearm before the publication
result returns). Here re-arm folds at ACKNOWLEDGMENT — the AX3 gate
already dedups the in-flight window by operation identity, and
anchoring the next delay to the published instant keeps "≥ delay
between reminders the reviewer actually saw".

The scheduler is a provider like GitHub: `ArmTimer` is ordinary
at-least-once work with operation identity; `TimerDue` is ordinary
typed ingress carrying the instant as part of the fact. `fold` and
`decide` never read a clock.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

DELAY = 3 * 24 * 60 * 60  # production default: build_net(reminder_delay=...)


# -- the folded snapshot (AX8's, restricted to the reminder-relevant facts) ----------------


@dataclass(frozen=True)
class Snapshot:
    epoch: int
    head: str
    started_at: float  # generation admission instant — anchors sequence 0
    # concern facts (folded by AX8's exits; defaults are the not-yet-settled states)
    actions: str = "unknown"
    review: str = "unknown"
    human_approved: bool = False
    human_requested: bool = False
    changes_requested: bool = False
    conflict: bool = False
    dashboard_current: bool = False
    distinct_reviewer_approved: bool = False
    reminder_recipient: str = ""
    reminder_snoozed: bool = False  # AX7 durable note (snooze/resume intents)
    # timer facts
    timer_sequence: int = 0
    timer_due_at: float = -1.0  # sentinel: derived lazily from started_at
    timer_matured: bool = False

    @property
    def due_at(self) -> float:
        return self.started_at + DELAY if self.timer_due_at < 0 else self.timer_due_at


# -- typed ingress and completions ---------------------------------------------------------


@dataclass(frozen=True)
class TimerDue:
    """The scheduler's fact: armed timer (epoch, head, sequence) matured
    at instant `at`. The instant is part of the event, so replay never
    consults a wall clock."""

    epoch: int
    head: str
    sequence: int
    at: float


@dataclass(frozen=True)
class ReminderAcknowledged:
    """AX3 gate completion: reminder `sequence` was published at `at`."""

    sequence: int
    at: float


type Exit = TimerDue | ReminderAcknowledged


def fold(snapshot: Snapshot, exit_value: Exit) -> Snapshot:
    match exit_value:
        case TimerDue(epoch, head, sequence, at):
            stale = epoch != snapshot.epoch or head != snapshot.head
            wrong_sequence = sequence != snapshot.timer_sequence
            early = at < snapshot.due_at  # scheduler fault; due_at is our truth
            if stale or wrong_sequence or early or snapshot.timer_matured:
                return snapshot  # inert, deterministically
            return replace(snapshot, timer_matured=True)
        case ReminderAcknowledged(sequence, at):
            if sequence != snapshot.timer_sequence:
                return snapshot  # stale ack — already re-armed past it
            return replace(
                snapshot,
                timer_matured=False,
                timer_sequence=sequence + 1,
                timer_due_at=at + DELAY,
            )


# -- the pure decision ---------------------------------------------------------------------


def review_satisfied(snapshot: Snapshot) -> bool:
    """`_reminder_due`'s review_satisfied, verbatim (topology.py:1185-1187)."""
    return snapshot.human_approved and (
        bool(snapshot.reminder_recipient) or snapshot.distinct_reviewer_approved or snapshot.human_requested
    )


def reminder_wanted(snapshot: Snapshot) -> bool:
    """`_reminder_due` (topology.py:1188-1198) minus authority currency
    (generation scoping) and in-flight flags (AX8 finding 1)."""
    return all(
        (
            not snapshot.reminder_snoozed,
            not review_satisfied(snapshot),
            not snapshot.changes_requested,
            snapshot.dashboard_current,
            snapshot.actions in {"green", "flaky_green"},
            snapshot.review == "clear",
            not snapshot.conflict,
        )
    )


@dataclass(frozen=True)
class ArmTimer:
    operation: str
    due_at: float


@dataclass(frozen=True)
class RemindWork:
    operation: str
    sequence: int
    reviewer: str


def decide(snapshot: Snapshot) -> tuple[ArmTimer | RemindWork, ...]:
    """Pure; no clock. Identity dedups (AX8 finding 2): the same folded
    state can only emit the same operations, and the gates absorb
    replays lookup-first."""
    scope = f"{snapshot.epoch}:{snapshot.head}:{snapshot.timer_sequence}"
    if not snapshot.timer_matured:
        return (ArmTimer(f"timer:{scope}", snapshot.due_at),)
    if reminder_wanted(snapshot):
        return (RemindWork(f"reminder:{scope}", snapshot.timer_sequence, snapshot.reminder_recipient),)
    return ()  # matured but unwanted: the fact keeps; fires the moment conditions return
