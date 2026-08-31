---
code: CV21.DS8
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV21.DS7 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv21-ds7-recover-ci-repair-effects.md
  - architecture.md
---

# CV21.DS8 — Recover timers and deferred work

## Outcome

Execute current-Net reminder and deferred-time behavior through new readiness
timer custody and the host-owned clock. Timer command, durable acknowledgement,
maturity claim, History acceptance, delivered mark, and resulting work are
distinct bounded cuts that reconstruct without duplicate delivery.

## Vertical path

```text
current timer request -> bridge typed command -> readiness timer custody
  -> host clock/deadline wake -> exact due fact -> bridge -> current fold
  -> detached posture or typed effect
```

## Owns

- typed timer command/due boundary and bridge mapping;
- readiness timer order, acknowledgement, maturity, delivery, and rebuild
  custody;
- host wall-clock/deadline capability and deterministic logical-time adapter;
  and
- timer crash schedules, exact replay, resource keys, and correspondence.

## Excludes

No new reminder/defer policy, workflow clock read, generic scheduler, hidden
sleep, or host-authored workflow due fact.

## Acceptance

- only host clock touches wall time or sleep;
- one timer generation has stable identity across every custody cut;
- oldest unfinished exact cut resumes before new timer work;
- early, duplicate, stale, moved, and canceled maturity fails closed;
- process death cannot lose an acknowledged command or double-deliver a due
  fact; and
- logical and real clock seams produce corresponding bounded observations.
