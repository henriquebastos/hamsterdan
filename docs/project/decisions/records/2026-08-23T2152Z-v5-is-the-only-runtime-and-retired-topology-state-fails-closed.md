---
status: Decided
raised: 2026-08-23
decided: 2026-08-23
recorded: 2026-08-23T2152Z
deciders:
  - Henrique (Navigator)
supersedes:
  - 2026-08-18T1425Z-non-sharded-v5-replaces-the-parallel-production-topology.md
related:
  - CV17
  - CV18
  - CV19
---

# V5 is the only runtime and retired topology state fails closed

## Decision

Non-sharded V5 is Hamsterdan's only runtime topology. The host constructs V5
directly; no runtime descriptor, selector, former production composition, or
sharded composition remains available.

The retired `HAMSTERDAN_READINESS_TOPOLOGY` setting is rejected whenever it is
present, including values that previously meant `production` or `v5`. A durable
root explicitly bound to topology identity `v5` may be resumed. A root bound to
the former production topology, or an unlabeled root, fails closed without
mutation and requires a separately designed migration or deliberate
replacement.

The durable identity remains `v5` for the first production release. Existing
resumable V5 histories retain their input-only `ready.facts` migration lane;
that V5-internal compatibility does not make another topology selectable.

## Consequences

- Runtime code and tests have one composition and one set of semantic journeys.
- Operators configure no topology setting; stale settings prevent launch rather
  than being interpreted as a migration request.
- Existing former or unlabeled state cannot be tested against production by
  accident and cannot be silently rewritten as V5.
- CV17's parallel comparison remains historical acceptance evidence. Its former
  topology is not retained as executable compatibility code.
- Sharded V5 remains an unselected historical exploration, not a deployment
  option.
