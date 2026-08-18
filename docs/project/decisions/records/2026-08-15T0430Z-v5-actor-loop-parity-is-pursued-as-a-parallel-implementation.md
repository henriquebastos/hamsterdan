---
status: Decided
raised: 2026-08-15
decided: 2026-08-15
superseded_by: 2026-08-18T1425Z-non-sharded-v5-replaces-the-parallel-production-topology.md
deciders:
  - Henrique (Navigator)
related:
  - CV17
  - ES-005
  - ES-007
---

# V5 actor-loop parity is pursued as a parallel implementation

> **Superseded 2026-08-18:** the accepted parity portfolio enabled the
> Navigator's later ruling that non-sharded V5 replaces the parallel
> production topology. This record preserves the constraints under which CV17
> established parity.

## Decision

Hamsterdan builds a second, complete implementation of the PR-readiness
workflow using the V5 actor-loop discipline proven in ES-007: one concern =
one loop = one memory baton plus mailbox places; cross-loop influence is
mailed facts only; zero guards, zero read arcs, zero unowned root places.

The V5 net is a parallel sibling of the production topology, not a
refactoring of it. Production remains the composed default and is not
modified. The host selects the topology explicitly at composition time and
fails closed to production. Parity is claimed per boundary scenario only
when the ES-005 chapter-17 scenario runs green through real host
composition — durable history, real dispatch, restart recovery — on both
topologies.

Sharding, the courier, and any Petrus promotion remain deferred deployment
and platform decisions outside this ruling. Replacement of the production
topology is a future ruling that requires an accepted parity portfolio; it
is not implied here.

## Consequences

- A new `readiness/net_v5` package owns the V5 topology under the same
  architecture contract as `readiness/net`: it owns workflow decisions and
  knows no GitHub or agent provider.
- The ES-007 exploration code is guidance, not source: DS1 is a clean TDD
  rewrite against the real `contracts/` types, with the AX4 structural
  census pinned as tests.
- Dormancy is modeled as a loop inside the net (as ES-007 AX1 did), not as
  a host mechanism.
- The parity harness becomes the acceptance instrument for any future
  replacement conversation; without it, no equivalence claim is durable.
