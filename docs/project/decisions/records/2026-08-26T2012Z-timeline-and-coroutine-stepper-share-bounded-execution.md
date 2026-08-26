---
status: Decided
raised: 2026-08-26
decided: 2026-08-26
recorded: 2026-08-26T2012Z
deciders:
  - Henrique (Navigator)
related:
  - ES-010
---

# Timeline and coroutine stepper share bounded execution

## Decision

`Timeline` is Hamsterdan's public deterministic simulation and debugging API.
An internal `CoroutineStepper` is the shared cross-layer execution mechanism
for Timeline and production. Production owners may use ordinary nested async
Python: one bounded owner step may yield one actual leaf callable, the stepper
may execute it once, and its result returns through the suspended call stack.
Production `step()` composes those phases, and production drains are finite,
budgeted loops over the same step operation.

Timeline may stop before the leaf executes, after execution but before its
result returns to the owner, or after normal owner return. Coroutine frames,
callables, and process-local results are never durable authority and never
appear in replay artifacts. Restart discards them and reconstructs a fresh
owner entry from durable module and adapter state. An ambiguous external effect
is recovered lookup-first under the same durable operation identity.

Durable owner state selects subjects, lanes, candidates, retries, timers, and
fairness positions. Timeline and CoroutineStepper route control and results;
they do not schedule domain work. More than one yielded leaf in an owner step
violates the bounded-step contract.

S9 owns Timeline's exact final API, including clock, journal, faults, crash
generations, artifacts, and replay. This decision authorizes no production
implementation and does not reopen the R2 workflow, port/adapter, readiness, or
host trees.

## Consequences

- Layered owners can remain normal executable code rather than manually
  encoding continuations as prepare/execute data values.
- Production and simulation share the mechanism that reaches effect-adjacent
  crash cuts; simulation does not wrap an opaque production drain.
- Correct recovery must never depend on a saved Python instruction pointer,
  local variable, callable identity, or held result.
- S9 may design the full Timeline API and replay contract from this boundary.
- Delivery still requires supported Petrus seams for bounded load with
  one-occurrence reconciliation and for separating Activity claim, effect
  observation, and terminal recording. Coroutine syntax must not conceal those
  coarse dependency calls behind finer simulated names.
