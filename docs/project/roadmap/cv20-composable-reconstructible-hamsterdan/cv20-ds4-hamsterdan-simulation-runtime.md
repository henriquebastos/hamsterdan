---
code: CV20.DS4
level: Delivery Story
status: Planned
status_reason: Waits for CV20.DS1 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds1-replacement-tree-gate.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS4 — Deliver the Hamsterdan simulation runtime

## Outcome

Implement CV20's semantic-free Timeline across runtime, logical clock,
scheduling, faults, artifacts, and replay, preserving the public
Timeline/internal coroutine-stepper boundary and one artifact version.

## CV20 contract

This story creates the deterministic mechanics defined in
[the API contract](api-contracts.md) and used by every later local and composed
simulation. It owns scheduling, faults, bounds, artifacts and replay—not
Hamsterdan commands, observations, checkers or orchestration.

## Owned paths

```text
src/hamsterdan2/simulation/clock.py
src/hamsterdan2/simulation/scheduling.py
src/hamsterdan2/simulation/faults.py
src/hamsterdan2/simulation/runtime.py
src/hamsterdan2/simulation/artifacts.py
src/hamsterdan2/simulation/replay.py
tests2/simulation/test_runtime.py
```

`simulation/hamsterdan.py` remains a construction placeholder until DS9.
Owner-local `*/simulation` packages remain placeholders until DS9.

## Fixed design

- All time is injected integer microseconds. No wall-clock read is allowed.
- `Timeline` is the public API; its coroutine stepper is an internal mechanism.
- Scheduling choices are deterministic for a seed and are recorded as ordered
  draws; replay consumes those draws exactly.
- One bounded step executes at most one leaf and exposes offered, executed and
  idle positions rather than draining implicitly.
- Faults are named cuts, not arbitrary callbacks or monkey patches.
- Resource use is measured at operation, retained-record and byte boundaries;
  overflow is a typed failure.
- The artifact envelope is namespaced/versioned and records commands,
  observations, faults, interleaving draws, local/cross reports, generation,
  resource peaks and digest.
- Replay rebuilds fresh state and compares exact observations, reports,
  operations, generation, peaks and digest.
- The root runtime imports no GitHub, agent, workflow, readiness or host domain
  type. It learns domain behavior only through explicit callbacks supplied by
  DS9 composition.

## Position and predecessors

Requires CV20.DS1. Owner-local simulations do not enter this story; DS9 adds
them after their production owners exist.

## Implementation sequence

1. Rule the exact mechanics-only protocols and error/result values below.
2. Implement integer-microsecond clock and deterministic draw source.
3. Implement one-leaf Timeline stepping and named fault injection.
4. Add measured operation/retention/byte budgets and fail-closed overflow.
5. Define the namespaced artifact codec and canonical digest.
6. Implement fresh reconstruction and exact replay comparison.
7. Prove with synthetic non-Hamsterdan systems that scheduling, cuts, bounds
   and replay work without domain imports.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- clock, schedule and fault collaborator names plus the supporting signatures
  around the fixed `Timeline` and `Artifact` APIs;
- the closed one-step result variants and quiescence/exhaustion distinction;
- deterministic draw representation and seed/draw precedence on replay;
- budget key, peak and overflow error schemas;
- canonical artifact field order, codec and digest contract; and
- version compatibility policy inside this replacement family.

Names and field layout may be strengthened. Mechanics-only ownership, explicit
bounded stepping and exact fresh replay are fixed.

## Done condition

The runtime executes one leaf per step, exposes offered/executed/idle crash
positions, loses process-local state by generation, enforces every finite
budget, rejects malformed/oversized artifacts, and exactly replays success and
failure without domain semantics.

## Rollback

Remove root simulation mechanics. Production imports no simulation module.

## Validation

Run the independent-pair proof, crash/equal-time/one-leaf cases, every budget
boundary, strict artifact decoder and byte refusal, exact failure replay, and
static semantic-independence audit.

## Expansion boundary

Expand into runtime stepping and artifact/replay Technical Stories with one
shared public contract; do not split by semantic owner. The ruled mechanics API
must be recorded in CV20 before DS9 composes domain modules through it.
