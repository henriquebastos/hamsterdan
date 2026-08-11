---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-005 — Unify per-Instance host activation

## Existing field refined

RS-002 and RS-003 established one Engine/History per PR, one shared Worker, and
host-owned runnable hints. The host still advanced that state through separate
webhook, timer/terminal, and sweep paths. Each path reconstructed, settled,
reconciled, recorded scheduling posture, and finalized webhook custody in a
different order. That duplication obscured the canonical boundary and once
allowed custody acknowledgment before post-activation settlement.

The post-RS-004 dependency review also reconsidered `ActionsState` and
`MutationState`. `ActionsState` observation and rerun fields participate in one
protocol across both halves; splitting it would replace one owner with five
cross-token joins. `MutationState` is the exact mutual-exclusion boundary among
change, repair, and provisional-head recovery; splitting it would recreate a
lock in transitions. Both remain intact.

## Refinement boundary

Converge every production activation source on one host method. Preserve the
Net and its 46 places, 69 transitions, 309 arcs, and 17 retirements. Do not add
HA, PostgreSQL, Petrus behavior, a generic actor runtime, or distributed
scheduling.

```text
direct webhook process ─┐
runnable due/timer ─────┼─> HostService._activate_instance(instance, ...)
Activity terminal wake ─┤       one per-Instance lock
startup/periodic sweep ─┘       pre-settle frozen terminals
                                apply custody OR reconcile provider
                                post-settle after work
                                record runnable posture
                                acknowledge custody
```

`PrReadinessApplication.activate(trigger, *, comment=None)` is the one
application activation operation. It reconciles provider truth exactly once
and then optionally delivers a strict host-normalized `NormalizedComment`.
The older `reconcile` and `route_comment` entry points remain thin direct-test
and compatibility surfaces rather than alternate host paths.

## Custody and recovery contract

- Non-actionable, untrusted, and inactive observations become terminal without
  constructing an application.
- Actionable custody is acknowledged only after pre-settlement, activation,
  post-settlement, and runnable-posture persistence succeed under the Instance
  lock. Failure durably schedules retry before it reaches a direct caller or
  scheduler health boundary.
- Mixed delivery batches isolate failed observations, finalize successful
  observations, and still surface the first retained failure to `run_due`.
- Trigger-only sweep reconciliation is forbidden while any custody for the PR
  remains pending, including deferred retries and observations beyond a bounded
  due batch. Webhook custody supplies subject-filtered due retrieval and an
  uncapped existence fence.
- Runnable hints remain reconstructible and noncanonical. Due activation
  reconstructs uncached active Instances and strictly bound inactive Instances
  to settle durable terminals without provider work. Startup/periodic sweep
  performs the same strict-bound inactive repair if a hint was consumed before
  a crash.
- Route authority is checked again inside the Instance lock immediately before
  provider work. Deactivation permits settlement and custody retirement but no
  new reconciliation.

## Validation

Focused host application/service evidence passed 108 tests. New regressions
cover acknowledgment after posture, settlement/posture/open failures, mixed PR
retry isolation, one-reconciliation comments, uncached active and inactive
restart settlement, route deactivation during pre-settlement, lost runnable
hints, deferred comments, and both unrelated and same-Instance 1,000-row
custody boundaries.

`scripts/check full` passed lint, formatting, type, package, and relay gates;
540 Python tests passed with one explicit external route deselected.
Independent adversarial review returned `APPROVE` after each discovered custody
or restart gap was closed.

## Consequences and next boundary

- Host scheduling now has one call stack and one custody-commit point.
- The Net did not change; the refinement clarified the infrastructure around
  it rather than forcing workflow state to compensate for host mechanics.
- `ActionsState` and `MutationState` are retained as real business ownership
  boundaries, not postponed aggregate cleanup.
- HA and concurrent activation remain explicitly deferred. The current contract
  assumes one `HostService` process and its serial production worker.
- The next conceptual-clarity pass can inspect the application/provider
  projection boundary without reopening execution, lifecycle, or publication
  ownership already settled by RS-002 through RS-005.
