---
code: CV17.DS3
level: Delivery Story
status: Active
status_reason: Durable publication claim expiry converges safely; the remaining V5 restart portfolio is next
updated: 2026-08-16
---

# CV17.DS3 — Durable V5 recovery

## Scope

Prove that the selected non-sharded V5 topology recovers from process death
using canonical Petrus History and the host's durable custody stores. Recovery
must converge from retained evidence without silently repeating an external
effect. Production remains untouched and default.

## Delivered slice

### DS3.0 — Durable publication claim expiry

Reply, dashboard, and readiness-announcement Activities now freeze their
provider operation as Motus correlation and idempotency and explicitly permit
one attempt. If a worker dies after claiming that attempt, LocalDispatch's
`DeadlineExceeded` terminal projects from the original immutable request to
`ReplyBlocked`, `DashBlocked`, or `ABlocked`. The original occurrence completes
through its typed terminal and is never automatically requeued. Every other
failure kind stays projection-pending and fails loudly.

The owning actor loop retains the exact request. Only an authorized
`recover_publication` command creates a fresh occurrence; that occurrence
preserves the same provider identity and full original authority claim, so the
existing gate performs lookup-first reconciliation before any fence or write.
Repeated restart before recovery is history-stable.

Tests exercise all three gates through real SQLite LocalDispatch claim expiry,
JSONL History reload, typed folding, a second stable reload, and explicit
recovery. `scripts/check full` passes with 1,015 Python tests, nine Bun relay
tests, formatting, Ruff, typing, and package builds. Oracle boundary review
returned `clear to commit`.

## Remaining recovery portfolio

- Prove unresolved inline review, rerun, and mutation Activities redispatch
  from canonical History and converge lookup-first across pre-effect and
  post-effect process death.
- Prove Agenticus operation-route repair, reminder timer custody, custodied
  webhook/reconciliation replay, and runnable-index wake reconstruction across
  host restart.
- Assemble the bounded kill/restart/converge portfolio through the selected V5
  HostService route. Torn JSONL repair remains an operator concern and is not a
  workflow recovery behavior.

## Done condition

Every durable V5 custody boundary has deterministic restart evidence, no
unproven external effect is repeated automatically, and the selected host route
converges through the complete non-sharded recovery portfolio.

## Boundaries

- Production topology, wiring, and behavior are not modified.
- Unknown terminal failures remain loud; DS3 does not introduce a generic
  requeue or retry API.
- Sharding and the courier remain outside CV17.
