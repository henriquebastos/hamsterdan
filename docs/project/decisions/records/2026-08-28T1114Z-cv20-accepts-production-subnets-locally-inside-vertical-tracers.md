---
status: Decided
raised: 2026-08-28
decided: 2026-08-28
recorded: 2026-08-28T1114Z
superseded_in_part_by:
  - 2026-08-28T1453Z-cv20-fragments-into-outer-system-and-workflow-replacement-values.md
deciders:
  - Henrique (Navigator)
related:
  - CV20
  - CV20.DS3
  - 2026-08-27T1925Z-cv20-delivers-through-vertical-tracer-bullets.md
---

# CV20 accepts production subnets locally inside vertical tracers

## Decision

Each workflow concern introduced by CV20 must be independently constructible,
executable and inspectable as a subnet from its exact production assembly. Its
owner-local deterministic simulation exposes typed boundary injection,
one-action stepping, marking and arc inspection, pending Activity and History
evidence, typed terminal delivery, named crash/reconstruction cuts, exact replay
and local checker/resource reports. A review diagram or trace is generated from
that mounted production subnet; it is not a second behavioral model.

The Navigator may accept the subnet's local behavior through an explicit User
Story before reviewing the larger composed path. That acceptance stabilizes the
subnet's internal language and invariants, but does not close its Delivery
Story. The same production assembly must then mount unchanged in the owning
workflow simulation and root vertical tracer, where cross-owner checkers prove
the real producer, consumer, custody and effect edges.

Subnet isolation is therefore a development and review boundary inside CV20,
not a new Capability Value and not a horizontal integration phase. Work proceeds
one concern at a time: accept the production subnet locally, compose it into the
current tracer, accept the tracer, then deepen the next concern. CV20 does not
finish every isolated subnet before testing their edges.

## Consequences

- Deterministic evidence has three nested scales: subnet-local, workflow-owner,
  and root composition. Each larger scale mounts the same production component
  and narrows its checker to the contracts owned at that scale.
- “Done and forget” means callers may forget internal transitions while typed
  ports, local scenarios, invariants and edge-sensitive cross checks remain.
- A local simulation may supply typed Activity outcomes, but it does not move a
  provider implementation or credential into workflow. Real side-effect
  correspondence remains in the provider-owning tracer and root composition.
- DS3 first applies this rule to the dashboard subnet: the Navigator can run,
  step, render, crash, reconstruct and replay it before the accepted DS2 input is
  composed through that same subnet to a durable dashboard Activity.
- The existing vertical-tracer decision remains in force. Green component work
  is reviewable and locally acceptable, but insufficient Delivery evidence.

## Partial supersession

CV20 was later dropped before implementation. CV22 now owns this production-
subnet rule recursively, including subnets composed from other subnets. CV21
owns only adapter-local correspondence around the retained workflow and does not
implement a replacement production subnet.
