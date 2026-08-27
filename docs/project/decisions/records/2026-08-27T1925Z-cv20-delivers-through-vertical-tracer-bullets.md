---
status: Decided
raised: 2026-08-27
decided: 2026-08-27
recorded: 2026-08-27T1925Z
deciders:
  - Henrique (Navigator)
related:
  - CV20
  - 2026-08-27T1604Z-composable-hamsterdan-is-the-planned-replacement-architecture.md
---

# CV20 delivers through vertical tracer bullets

## Decision

Replace CV20's component-first Delivery Story sequence with eleven permanent,
production-shaped tracer bullets followed by the separately approved cutover.
Each tracer starts at an external, operator, or deterministic-simulation command
boundary; uses the real production composition and every owner relevant to that
behavior; and ends in a bounded visible posture, durable workflow request, or
accepted external effect.

Package-level implementation is Technical Story work inside the owning tracer.
A provider value, workflow fold, runtime adapter, host store, or simulation
module is not independently accepted Delivery merely because its local tests
pass. The Delivery Story closes only when the complete tracer path, its API
contracts, deterministic simulation, checker sensitivity, crash recovery,
observability, finite bounds, and applicable real-seam correspondence are
accepted together.

Concrete APIs are contract-first and call-site-proven. Fixed ownership,
identity, authority, recovery and package boundaries remain normative, while a
tracer rules concrete signatures with its real producer, consumer, simulation
seam and observation surface present. Internal replacement APIs may change
atomically during construction; they do not earn compatibility aliases.

The source/test trees remain reviewed initial maps rather than immutable file
inventories. Package ownership and forbidden/required edges are fixed. An
owning tracer may merge or split modules when the deletion test demonstrates a
clearer responsibility, provided CV20's architecture and ledger are updated
before implementation.

## Consequences

- DS1 establishes the first bounded one-PR lifecycle and includes the strict
  gate, minimal Petrus execution seam, production composition and deterministic
  runtime needed to prove that vertical pulse.
- DS2–DS11 thicken the same production spine through observation, Activity,
  GitHub effect, agent, mutation, CI, time, authority, multi-PR and qualification
  capabilities.
- Deterministic simulation testing, observability, resource measurement and
  correspondence accumulate from the first tracer instead of arriving in late
  integration stories.
- Each tracer introduces at most one major new effect family, custody state
  machine, authority policy, concurrency dimension, or causal chain. If a
  review must hold several new chains at once, the tracer is split.
- Fixed cross-cutting obligations required by that call site—identity,
  authority, recovery, bounds and observation—ship with the tracer rather than
  being deferred as later integration. They do not license a second policy or
  causal chain inside the same tracer.
- Component work may be independently green and reviewable in commits, but it
  remains unfinished Technical Story work until the tracer's vertical outcome
  is accepted.
- CV20 and every Delivery Story remain `Planned`; this decision pulls no work
  and does not alter the V5-only runtime or DS12 approval boundary.
