---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-009 — Remove false host-runtime surfaces

## Existing field refined

`HostService` treated terminal settlement and unresolved-publication detection
as optional application capabilities through dynamic `getattr` calls. Every
production application implements both operations, and activation ordering
depends on settlement before provider reconciliation and after activation. The
optional shape existed only for incomplete test doubles and made mandatory
custody behavior appear best-effort.

`AgentRouteStore` separately exposed `reconstruct_before_redispatch()` and
`resolve()` with no production callers. They wrapped the canonical `claim()` and
`settle()` operations and implied a second route-recovery protocol.

## Accepted boundary

`HostService` now calls application settlement and publication-state inspection
directly. Test doubles implement that mandatory production interface. No new
Protocol, adapter, or runtime accessor was introduced.

Route reconstruction continues through idempotent `claim(operation,
composition)`, which validates the active route, rejects resolved work, and
preserves exact persisted composition. Terminal route ownership is completed
through `settle(operations)`. The two unused wrappers were deleted.

## Validation and review

Focused evidence passed 56 service tests and 18 Agenticus route-custody tests.
`scripts/check quick` passed static, format, and production type checks.
`scripts/check full` passed package and relay gates, then 577 Python tests with
one explicitly external route deselected. Independent adversarial review
returned `APPROVE` with no release blocker.

## Consequences

- Terminal settlement and unresolved-publication repair are explicit mandatory
  host/application invariants.
- One route API owns claim/reconstruction and one owns terminal settlement.
- Production ordering, restart fencing, shutdown isolation, and worker behavior
  are unchanged.
- No Net, provider, lifecycle, Activity execution, scheduler, storage schema,
  or Petrus behavior changed.
