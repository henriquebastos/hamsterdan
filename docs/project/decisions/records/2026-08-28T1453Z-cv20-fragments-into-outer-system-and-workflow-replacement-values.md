---
status: Decided
raised: 2026-08-28
decided: 2026-08-28
recorded: 2026-08-28T1453Z
deciders:
  - Henrique (Navigator)
supersedes:
  - 2026-08-27T1604Z-composable-hamsterdan-is-the-planned-replacement-architecture.md
supersedes_in_part:
  - 2026-08-27T1925Z-cv20-delivers-through-vertical-tracer-bullets.md
  - 2026-08-28T1114Z-cv20-accepts-production-subnets-locally-inside-vertical-tracers.md
related:
  - CV20
  - CV21
  - CV22
  - 2026-08-23T2152Z-v5-is-the-only-runtime-and-retired-topology-state-fails-closed.md
  - 2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md
  - 2026-08-28T0153Z-configured-repository-recovery-discovers-unknown-open-pull-requests.md
  - 2026-08-28T1113Z-dashboard-closure-converges-before-generation-close.md
---

# CV20 fragments into outer-system and workflow-replacement Values

## Decision

CV20's complete-replacement delivery plan is superseded before implementation.
Its records remain intact as the historical integrated design and review
evidence, but its Value and Delivery Stories are dropped from the pullable
roadmap.

The replacement now proceeds through two planned Values:

1. **CV21** builds the non-selectable `hamsterdan2` outer system around the
   current working V5 Petri Net. One temporary bridge is the only new module
   allowed to import the current workflow package. It translates between final
   Hamsterdan2 workflow-boundary values and current Net tokens without deciding
   workflow behavior. It mounts the current Net, seed, and workflow gate
   declarations, not the current application, host, effects, custody, timers,
   provider, or agent implementation.
2. **CV22** replaces the workflow behind that boundary with independently
   executable production subnets, proves the complete composition, removes the
   bridge and current implementation, and performs the separately approved
   final cutover to canonical Hamsterdan.

The current V5 application remains the sole operational runtime until CV22's
final cutover. CV21 and pre-cutover CV22 code use fresh disposable construction
state, remain unavailable through runtime configuration and deployment, and do
not read, migrate, convert, or write current runtime state.

## Bridge boundary

Only the CV21 legacy-workflow bridge may directly import these current
workflow entry points:

- `hamsterdan.readiness.net_v5.topology`;
- `hamsterdan.readiness.net_v5.gating`; and
- `hamsterdan.contracts.readiness_v5`.

The retained workflow's transitive implementation closure is
`hamsterdan.readiness.net_v5`, `hamsterdan.contracts.readiness_v5`, and the
`WorkflowModel` base currently defined in `hamsterdan.contracts.readiness`.
No other `hamsterdan2` production or test module may import, inspect, patch, or
construct anything from that closure. No current type, exception, topology
name, schema value, or operation wrapper may cross the bridge into a new owner.

The bridge may perform pure representation conversion required by the new
typed boundary. It may not invent an observation, Activity request, terminal,
ordering, retry, authority, lifecycle, or closure decision absent from the
current Net. Each translation family requires exact correspondence scenarios
against the mounted production Net and an architecture census enforcing the
allowlist.

## Contract disposition

- CV20's accepted outer ownership, source-neutral admission, authority,
  custody, bounded execution, discovery, fairness, Timeline/DST, quality-gate,
  and vertical-tracer contracts govern CV21 after being restated in CV21's
  self-contained owners.
- CV20's workflow topology, loop, dashboard, closure, production-subnet, and
  workflow-local deterministic contracts govern CV22 after being restated in
  CV22's self-contained owners.
- The vertical-tracer rule remains active in both Values. CV21 applies it to
  outer behavior through the real bridge-mounted Net. CV22 applies it after
  accepting each exact production subnet locally.
- CV20's pending-rulings register and concept analysis remain evidence, not
  accepted design. Successor Values must disposition their relevant questions
  rather than silently promote recommendations or vocabulary.

## Recursive subnet direction

CV22 must make every production subnet independently constructible,
executable, inspectable, crashable, reconstructible, replayable, and
deterministically checked. The same production assembly mounts unchanged at
subnet-local, workflow-owner, and root-composition scales, recursively when a
subnet contains other subnets.

Parent or root development may use a typed abstract child boundary before the
child internals exist only after CV22 rules the boundary and the evidence that
proves abstract/concrete conformance. This decision does not equate an arbitrary
subnet with one transition: concurrency, intermediate observable state,
multiple ports, Activities, cancellation, and failure may make that contraction
unsound. CV22 must settle composition order and equivalence before detailing or
pulling its implementation Delivery Stories.

## Consequences

- CV20 and CV20.DS1–DS13 use Ariad lifecycle status `Dropped` with
  “superseded before implementation” as the reason. Their bodies remain
  historical evidence and comparison surfaces.
- CV21 has twelve progressively deepened outer-system tracers and no cutover.
  No tracer implements a replacement workflow loop or subnet.
- CV22 is Planned with a low-detail story for each known workflow concern plus
  root composition, replacement qualification and final cutover. The manifest
  records known work; detailed expansion, pull order and implementation wait
  for the typed subnet-boundary and conformance ruling. The accepted dashboard
  subnet is its first concrete workflow design, not a reason to guess the
  general hierarchy.
- The bridge is deliberate construction scaffolding, not a supported
  compatibility lane. Its deletion is a CV22 acceptance condition.
- At decision time, CV19 remained the only Active Value. This planning decision
  authorized no runtime selection, deployment, state action, external effect,
  commit, push, or release.

## Subsequent delivery movement

Later on 2026-08-28, the Navigator paused CV19 before production launch and
selected CV21 as the Active Value. This changes delivery focus, not runtime
authority: V5 remains the sole runtime, CV21 remains non-selectable construction,
and no deployment, state action, external effect, or release was authorized.
