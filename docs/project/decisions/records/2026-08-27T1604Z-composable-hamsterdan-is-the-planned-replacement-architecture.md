---
status: Superseded
raised: 2026-08-27
decided: 2026-08-27
recorded: 2026-08-27T1604Z
superseded_by: 2026-08-28T1453Z-cv20-fragments-into-outer-system-and-workflow-replacement-values.md
superseded_in_part_by:
  - 2026-08-28T0153Z-configured-repository-recovery-discovers-unknown-open-pull-requests.md
deciders:
  - Henrique (Navigator)
related:
  - ES-010
  - CV20
  - 2026-08-22T0107Z-v5-durable-decisions-are-explicit-topology.md
  - 2026-08-23T2152Z-v5-is-the-only-runtime-and-retired-topology-state-fails-closed.md
  - 2026-08-26T2012Z-timeline-and-coroutine-stepper-share-bounded-execution.md
---

# Composable Hamsterdan is the planned replacement architecture

> **Superseded 2026-08-28:** CV20's integrated replacement was not
> implemented. CV21 now owns the outer-system reconstruction over one temporary
> current-Net bridge, and CV22 owns the workflow replacement, bridge removal,
> and final cutover. This record preserves the original integrated strategy.

## Decision

Promote ES-010's accepted architecture as CV20, a Planned replacement for the
current Hamsterdan implementation. The replacement is built under temporary
`src/hamsterdan2` and `tests2` namespaces so every Delivery Story can remain
green and reversible without creating a selectable second runtime.

The current V5-only decision remains operationally active through CV20.DS1–DS11.
No replacement code reads or migrates current V5 state, and no selector, alias,
compatibility reader, dual writer, or dual runtime is introduced.

CV20.DS12 is a separate cutover decision and operator action. Once its
predecessors and correspondence gates are accepted, it may receive explicit
Navigator approval to stop the current service, preserve old state only for
bounded rollback, rename the replacement to canonical `hamsterdan`, switch
packaging and deployment, and remove the current implementation. After that
cutover there is one Hamsterdan: neither “Hamsterdan2” nor “V5” remains an
active runtime, schema, path, selector, compatibility, or operator concept.

Durable workflow decisions remain explicit in the workflow topology. The
accepted Timeline/coroutine bounded-execution ruling remains active. The final
cutover decision, not this planning decision, will supersede the current
V5-only operational decision.

## Consequences

- CV20 and all twelve Delivery Stories enter the roadmap as `Planned`; none is
  pulled by this decision.
- CV19 remains the only active Value and V5 remains the only current runtime.
- `hamsterdan2` is a temporary construction name, not a product version or
  runtime identity.
- The replacement uses fresh stores and one artifact family; old-state or
  artifact compatibility is not delivery work or debt.
- CV20's local architecture, API, sequence, ledger, and selected Delivery Story
  are the self-contained implementation contract. ES-010/S12 remain provenance,
  not a source from which implementers must recover design choices.
- DS12 must remove both implementation generations' temporary labels: the old
  V5 implementation is deleted and the replacement is named simply Hamsterdan.
- Shared deployment, state, provider, commit, push, and release actions retain
  separate explicit approval boundaries.

## Partial supersession

The configured-repository recovery decision inserts a distinct DS10 discovery
tracer. Current CV20 therefore has twelve tracers plus DS13 cutover. This record's
replacement strategy, non-selectability and no-compatibility rulings remain in
force; only its tracer count and DS12 cutover number are superseded.
