# 12 — Time

**Rely on this: the scheduler is a provider like any other — time
enters as typed events carrying their own instant, and nothing inside
ever reads a clock.**

## What it is

Timers are not a net feature and not a special power. Arming a timer
is an ordinary effect going out (`ArmTimer`); maturity is an ordinary
typed event coming in (`TimerDue`), delivered through the same
identified ingress as any webhook. The event carries its own
timestamp, so folds and decisions stay pure — replay has zero
wall-clock nondeterminism.

The one subtle rule that pays: **maturity is a durable fact, separate
from the decision about it.** "The reminder timer matured" is folded
and kept; whether to *act* on it is decided from the snapshot. Snooze
cancels the decision, never the fact — so a matured-but-suppressed
reminder fires the moment conditions return, with no re-arming
machinery.

## The idea

```python
# outbound, identified like any effect:
ArmTimer(at=..., identity=f"reminder:{epoch}:{sequence}")

# inbound, typed like any provider event:
TimerDue(epoch=..., sequence=..., at=...)     # the instant lives IN the event

snapshot = fold(snapshot, timer_due)          # maturity becomes durable fact
work     = decide(snapshot)                   # reminder_wanted(snapshot) → act or not
```

## What it does not do

- No `sleep` inside the net, no delays as hidden transition behavior —
  pacing between retry attempts (concept 7) is an armed timer whose
  `TimerDue` re-enters as ingress.
- No clock reads in `fold` or `decide`, ever — that would put
  nondeterminism back into replay.
- It does not displace the engine's own low-level delay watermark;
  that mechanism stays where it is. This is the *authoring-level*
  discipline.

## How it relates

- Concept 2: `ArmTimer` is an effect with identity like every other.
- Concept 10: an old-epoch `TimerDue` folds inert — snoozing across a
  resume needs no special case.
- Concept 11: maturity-as-fact is the fold pattern applied to time.

## Why trust it

ES-004 AX9 ran the scheduler-as-provider on the real engine: the
durable-maturity trick preserved production's subtlest reminder
semantic verbatim, and nine ambient read arcs collapsed into one
`reminder_wanted(snapshot)` predicate.
