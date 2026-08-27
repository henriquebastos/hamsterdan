---
code: CV20.DS8
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS7 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds7-recover-ci-repair-escalation.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS8 — Recover timers and deferred work

## Outcome

Deepen the one-PR lifecycle with deterministic time and durable timer custody.
Workflow timer commands are applied and acknowledged exactly once; mature facts
are delivered back through History; reminders, deferred review and deferred
announcement work wake through existing effect seams; and restart reconstructs
the next deadline without a process-local timer or hidden drain.

## Vertical path

```text
real workflow fold -> TimerCommand
  -> readiness applies one command and retains acknowledgement
  -> exact TimerCommandApplied accepted/folded/marked
  -> host records next deadline
  -> injected integer clock reaches due instant
  -> readiness claims one maturity and persists TimerDue
  -> exact maturity accepted/folded/marked
  -> reminder/deferred workflow Activity
  -> established provider or agent seam -> terminal -> new posture
```

This tracer introduces one custody state machine: workflow time intent to
readiness persistence to host wake. It adds no second scheduler or effect family.

## Component Technical Stories

1. Implement workflow timer command/applied/due values and reminder/deferred
   folds in integer microseconds.
2. Implement readiness ordered timer command, acknowledgement, maturity and
   delivery custody with bounded reconstruction.
3. Add host clock ownership and deadline/wake recording.
4. Route reminders/deferred review/announcement through existing Activity
   effect ports.
5. Extend Timeline advance, local/root modules, checker sensitivities and real
   SQLite/process correspondence.

## Initial owned paths

```text
src/hamsterdan2/workflow/net/{reminders,readiness,review}.py
src/hamsterdan2/readiness/custody/timers.py
src/hamsterdan2/readiness/application.py
src/hamsterdan2/host/clock.py and posture/wake owners
implemented owner-local/root simulation and tests
```

## Fixed design

- Workflow owns `TimerCommand`, `TimerCommandApplied` and `TimerDue`; readiness
  owns durable timer custody; host owns the sole production wall clock/sleep.
- Time is signed integer microseconds at every boundary. No float conversion or
  direct wall-clock read outside `host.clock` is allowed.
- Apply command, expose oldest acknowledgement, accept acknowledgement into
  History, mark it delivered, claim maturity, expose oldest maturity, accept it
  into History and mark it delivered are distinct bounded cuts.
- Construction receives retained state needed for reconstruction explicitly;
  it cannot hide an unbounded scan/drain.
- Ordering is deterministic by due instant and stable identity. Exact duplicate
  command/maturity is idempotent; conflicting identity fails closed.
- `WorkPosture.next_deadline` is a reconstructible hint. Durable timer custody
  remains authority if host wake hints are missing or corrupt.
- Reminder/deferred effects reuse existing lookup-first provider/agent seams and
  preserve original Activity/operation correlation.
- Each call applies/claims/marks at most one item and reports finite resources.

## API-strengthening checkpoint

Review command→acknowledgement and maturity→workflow call trees and settle:

- timer value fields, stable identities and integer-microsecond validation;
- timer custody apply/read/mark/claim/next-due transaction signatures;
- host clock/deadline/wake interfaces and posture fields;
- reminder/deferred request/terminal operation grammars;
- duplicate/collision/late/stale/overflow/storage error taxonomy;
- named command/ack/maturity/wake/Activity cuts and restart side; and
- retained timer/ack/maturity/wake rows/bytes plus logical-time/artifact limits.

Write the ruled contract into [the API contract](api-contracts.md). Ownership,
cut separation, integer time, deterministic order and one-item bounds are fixed.

## Tracer acceptance

Given one workflow timer command, when logical time advances past its due
instant, then exactly one command acknowledgement and one maturity fact return
through History, the intended reminder/deferred Activity uses an established
effect seam, and host posture reflects the next deadline or quiescence.

Acceptance crashes after every command, acknowledgement, maturity, History and
mark cut; deletes/corrupts host wake hints; reconstructs from fresh state; and
proves no lost/duplicate timer or effect. Time/identity substitution must leave
local checkers green and fail exactly the boundary checker. Exact replay,
lowered timer/wake/history/artifact bounds, SQLite transaction interruption and
fresh-process logical-clock correspondence are required.

## Done condition

The complete workflow→custody→clock→workflow→effect vertical is accepted. A
timer store or workflow reminder unit test alone cannot close the DS.

## Stop conditions

Stop if workflow reads a clock, host interprets timer meaning, wake hints become
authority, constructor drains retained timers, one call handles multiple mature
items, or restart requires a process-local callback/task.

## Rollback

Remove timer/reminder/deferred growth and fresh custody state. DS7's immediate
CI/repair paths remain accepted; current production is unchanged.

## Validation

Run command/ack/maturity ordering and duplicate cases, every named crash cut,
lost/corrupt wake reconstruction, reminder/deferred effects, local/cross
sensitivity, exact replay, lowered bounds, SQLite/process correspondence,
clock-import audit and project gates.

## Expansion boundary

Workflow protocol, custody, host wake and deferred behavior may be separate
Technical Stories. Keep the DS open until logical time drives the complete real
path and all durable cuts reconstruct.
