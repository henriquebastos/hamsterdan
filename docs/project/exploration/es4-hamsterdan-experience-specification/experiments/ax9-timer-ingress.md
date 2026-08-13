# AX9 — Time as typed ingress: the reminder without nine read arcs

## Question

AX5's MISSED list included timers/reminders: the independent spec had
no story for time. Production's `reminder_due` transition
(`readiness/net/topology.py:1611-1624`) carries `timers=(Delay(3
days),)` plus **nine read arcs** joining the cohort for its guard
`_reminder_due` (`topology.py:1184-1198`). Question: is time a
special citizen requiring marking-wide reads, or just one more
external provider whose facts fold into the AX8 snapshot?

Spike: [ax9-timer-ingress/](ax9-timer-ingress/) — 13 tests, all
passing; no production code touched.

## What Petrus gets right — the timer is NOT the accidental part

Before proposing anything: Petrus's timer model is already pure and
replay-safe, and this experiment *keeps its principle*:

> A binding is enabled only when every declared timer has matured
> against the clock watermark — a not-yet-matured binding is not
> enabled, purely, with no timer state stored.
> — `petrus/impetus/petrinet/enabledness.py:27-34`, DR 2026-07-08
> "timers-keyed-per-firing-binding-age-anchored"

`Delay` anchors to the token's recorded entry instant; maturation is
derived, never stored; `next_maturation` tells the adapter the wakeup
it owes. No coroutine frames, no wall-clock nondeterminism in replay.
This is the *same* discipline as the fold: time-as-fact, decisions
derived. The accidental part is only the guard join — nine read arcs
re-assembling the marking to decide due-ness.

## Production today: a timer token cycle plus a marking join

```text
generation start seeds Reminder(epoch, head, seq=0)     (topology.py:537)
        │
        ▼
reminder.p.timer ──▶ t.reminder_due ──▶ work.p.reminder (publish)
   ▲                 │ Delay(3d) anchored to      │
   │                 │ token entry               └▶ reminder.p.rearm
   │                 │ guard: _reminder_due over        │
   │                 │ NINE read arcs                   ▼
   └──────────────────────────────────────────── t.rearm (re-enter resets anchor)
```

```python
# topology.py:1184-1198 — the guard joins nine places
def _reminder_due(snapshot, timer):
    review_satisfied = snapshot.human_approved and (
        bool(snapshot.reminder_recipient) or snapshot.distinct_reviewer_approved
        or snapshot.human_requested)
    return (_current(authority, timer) and not snapshot.reminder_snoozed
        and not review_satisfied and not snapshot.changes_requested
        and snapshot.dashboard_current
        and snapshot.actions in {"green", "flaky_green"}
        and snapshot.review == "clear"
        and not any((snapshot.provisional, snapshot.change_in_flight,
                     snapshot.repair_in_flight, snapshot.conflict)))
```

A load-bearing production semantic to preserve: a matured binding
suppressed by its guard **fires the moment conditions return** — the
timer does not restart when the guard is false.

## The model: the scheduler is a provider like GitHub

```text
production                              proposed
──────────────────────────────          ──────────────────────────────
Reminder token + Delay + 9 reads        ArmTimer work (operation id)  →  scheduler
guard over live marking                 TimerDue(epoch, head, seq, at) ingress
fire → rearm token cycle                fold: timer_matured = True (a settled fact)
                                        decide(snapshot): matured AND wanted → RemindWork
                                        ack folds → rearm seq+1, due_at = ack.at + DELAY
```

```python
# ax9_timer.py (abridged)
case TimerDue(epoch, head, sequence, at):
    stale = epoch != snapshot.epoch or head != snapshot.head
    wrong_sequence = sequence != snapshot.timer_sequence
    early = at < snapshot.due_at          # due_at is our truth, not the scheduler's
    if stale or wrong_sequence or early or snapshot.timer_matured:
        return snapshot                    # inert, deterministically
    return replace(snapshot, timer_matured=True)

def decide(snapshot):
    if not snapshot.timer_matured:
        return (ArmTimer(f"timer:{scope}", snapshot.due_at),)
    if reminder_wanted(snapshot):          # _reminder_due verbatim, minus the AX8-eliminated flags
        return (RemindWork(f"reminder:{scope}", snapshot.timer_sequence, ...),)
    return ()   # matured but unwanted: the fact keeps; fires when conditions return
```

`fold` and `decide` never read a clock: the instant is **part of the
event** (`TimerDue.at`, `ReminderAcknowledged.at`), so replay is a
refold with zero wall-clock nondeterminism — the same property Petrus's
watermark gives, kept at the fold layer.

## Findings

1. **Time is ordinary ingress.** `TimerDue` folds exactly like
   `ActionsSettled`: a typed settled fact from an external provider.
   The reminder decision joins AX8's `decide` as one more pure
   function. No timer place, no read arcs, no new machinery — the 9
   reads land in the same ACCIDENTAL class as AX8's 25.
2. **Maturity is a durable fact, and that preserves the
   guard-suppression semantic.** Production's matured-but-suppressed
   binding waits in the marking; here `timer_matured=True` waits in
   the snapshot. Snooze cancels the *decision*, never the *fact*;
   resume fires immediately (tested).
3. **Sequence is the fence.** `timer:{epoch}:{head}:{seq}` /
   `reminder:{epoch}:{head}:{seq}` make duplicate, early, stale-
   sequence, and stale-generation deliveries inert at the fold
   boundary — the same shape as AX6's epoch fencing and AX8's
   operation identity. The scheduler holds no authoritative state:
   after a scheduler loss, the same snapshot re-derives the same
   `ArmTimer` (tested).
4. **One deliberate divergence, named.** Production re-arms at firing
   (`_remind` routes `Reminder(seq+1)` before the publication result);
   the model re-arms at acknowledgment. The AX3 gate dedups the
   in-flight window, and anchoring the next delay to the *published*
   instant means "≥ DELAY between reminders the reviewer actually
   saw". If firing-anchored cadence ever matters, fold the re-arm on
   `RemindWork` emission instead — same machinery.

## Failure modes

| Mode | Behavior |
| --- | --- |
| duplicate `TimerDue` | inert: already matured (tested) |
| early delivery (scheduler fault) | inert: `at < due_at`; stays armed (tested) |
| late delivery | matures normally; lateness visible in the event (tested) |
| stale generation / stale sequence | inert at fold boundary (tested) |
| scheduler loses its state | `decide` re-emits the same `ArmTimer`; gate dedups (tested) |
| publication fails, no ack | still matured+wanted → same `RemindWork` re-emitted; gate retries or faults |
| conditions regress while matured | decision suppressed; fact kept; fires on return (tested) |
| replay | refold of the event list; instants live in events; no clock (tested) |

## What this deliberately defers

Who *is* the scheduler — Petrus's own `next_maturation` wakeup driving
a degenerate one-place timer subnet, or an external cron/queue — is a
deployment choice, not a semantic one: both deliver `TimerDue`-shaped
facts. The spike also keeps AX8's simplification of
`dashboard_current` as a folded boolean rather than the digest
comparison; the composition is unchanged.

## Divergence classification

```text
9 reminder read arcs           ACCIDENTAL — the join is mechanism (AX8's class)
Reminder token + rearm cycle   ACCIDENTAL — sequence/due_at as snapshot facts suffice
Delay purity / watermark       REQUIREMENT-GRADE DESIGN — kept as time-as-fact ingress
matured-fires-on-guard-return  REQUIREMENT — kept as durable maturity fact (tested)
reminder cadence predicate     REQUIREMENT — kept verbatim
re-arm at fire vs at ack       OPEN (minor) — model chose ack; both expressible
```

## Verdict

**Promising; continue.** Time needs no special citizenship: a
scheduler is a provider, `TimerDue` is ingress, maturity is a folded
fact, and the reminder is one more pure decision over the AX8
snapshot. The second MISSED item closes. Next: AX10, the actions
rerun → repair loop — the one place where production's cycle is real
domain structure, not accidental topology.
