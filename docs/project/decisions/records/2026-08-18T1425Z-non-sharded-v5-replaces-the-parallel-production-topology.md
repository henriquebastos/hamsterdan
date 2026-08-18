---
status: Decided
raised: 2026-08-18
decided: 2026-08-18
deciders:
  - Henrique (Navigator)
supersedes:
  - 2026-08-15T0430Z-v5-actor-loop-parity-is-pursued-as-a-parallel-implementation.md
related:
  - CV17
  - CV18
---

# Non-sharded V5 replaces the parallel production topology

## Decision

Accepted non-sharded V5 is Hamsterdan's one production
readiness topology. Default host construction and the historical
`production` selector value both resolve to V5. The former operator topology
switch is retired; `sharded-v5` and every other unknown value fail closed.

Existing state remains topology-bound. A root labeled for the former
production topology is not silently opened as V5 state; migration or deliberate
replacement owns that change. The former production descriptor may remain as
historical compatibility/test structure while references are retired, but it
is no longer a selectable runtime composition.

This ruling follows CV17's accepted parity portfolio. It does not reopen that
evidence and does not select the deferred sharded V5 design.

## Consequences

- `HostService` and configuration default to non-sharded V5.
- CV18 DST campaigns judge the real V5 host only; they do not maintain two
  application profiles or compare production/V5 traces.
- Operator setup requires no topology selector and rejects the retired switch.
- Historical records saying production remained the default remain true for
  their acceptance date but are superseded for current operation by this
  decision.
