---
code: CV20.DS3
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS2 and a public bounded Petrus one-occurrence seam; not pulled
updated: 2026-08-28
related:
  - index.md
  - cv20-ds2-admit-fold-pr-observation.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
  - ../../decisions/records/2026-08-28T1113Z-dashboard-closure-converges-before-generation-close.md
---

# CV20.DS3 — Exercise the dashboard subnet and expose one Activity

## Outcome

First make the exact production dashboard subnet independently executable and
inspectable. Then deepen the admitted PR path until that same workflow subnet
declares its first external request: one immutable `DashboardPublication`.
Readiness records the exact Petrus Activity occurrence and exposes bounded
waiting posture while Dispatch holds the request. No provider adapter executes
it in this tracer.

## Navigator-facing User Story

As the Navigator, I want to feed typed events and outcomes to the production
dashboard subnet, step it one action at a time, inspect its values, marking,
arcs, History and pending publication, and crash/reconstruct/replay it, so that
I can accept its behavior and vocabulary before reviewing the complete PR path.

Given one named dashboard scenario, when the standalone runner executes or
steps it, then its before/after values, enabled action, resulting marking,
Activity evidence, resource use and local checker result are inspectable; an
Arx/Graphviz view contains only the exact production dashboard assembly; and a
fresh-object replay reaches the same result.

## Required paths

Standalone subnet review:

```text
typed DashboardEvent or DashboardPublicationOutcome
  -> exact production dashboard subnet
  -> DashboardProjection fold and publication decision
  -> held DashboardPublication Activity or settled projection
  -> marking/arc/History/Dispatch/checker inspection
```

Delivery Story vertical path:

```text
real retained PR observation
  -> host one-subject step
  -> readiness bounded workflow advancement
  -> real lifecycle/dashboard folds
  -> workflow MANIFEST-declared DashboardPublication
  -> Petrus ActivityRequested plus Dispatch occurrence
  -> detached waiting posture and host inspection
```

After acceptance, the production system can explain exactly what external work
the workflow wants, with stable identity and durable occurrence, while doing no
external mutation.

## Component Technical Stories

1. Rule and implement `DashboardEvent`, `DashboardProjection`,
   `DashboardPublication` and the closed `DashboardPublicationOutcome` family
   without mixing workflow state into Activity work.
2. Make the dashboard module independently constructible from the same exact
   production assembly used by root workflow topology; add explicit token,
   port, manifest and topology validation.
3. Add the standalone dashboard scenario runner, focused Arx/Graphviz view,
   local checker, crash/reconstruction, exact replay and resource evidence.
4. Complete the workflow fact/Activity manifest substrate and manifest-driven
   gate wiring needed by the lifecycle and dashboard loops.
5. Qualify public Petrus/Motus request and one-occurrence reconstruction seams.
6. Extend readiness runtime to advance once and surface a pending Activity in
   detached posture without executing it.
7. Mount the accepted production subnet unchanged in workflow-owner/root
   simulation and add cross checkers with durable History/Dispatch evidence.

## Initial owned paths

```text
src/hamsterdan2/workflow/{values,facts,activities}.py
src/hamsterdan2/workflow/net/{folding,gating,topology,dashboard}.py
src/hamsterdan2/readiness/{application,runtime,ports}.py
implemented workflow/readiness/host simulations and tests
Petrus/Motus public request/reconstruction seam and dependency pin, if needed
```

## Fixed design

- `workflow` alone decides that a dashboard publication is needed and creates
  `DashboardPublication`; readiness and simulation cannot construct an equal
  substitute.
- `DashboardEvent` is one internal workflow fact relevant to the dashboard;
  provider observations reach it only through their owning workflow fold.
- `DashboardProjection` owns desired, landed, one exact pending publication and
  retained failure state. History/Dispatch remain authoritative for occurrence
  and execution custody.
- `DashboardPublication` is one immutable exact external command. It does not
  carry held projection state, and the same operation never identifies changed
  bytes.
- `DashboardPublicationOutcome` is the closed typed result family matched to the
  exact pending work/operation before it may change the projection.
- Publication is single-flight. New events may change and coalesce desired state
  while one publication is unresolved, but cannot create concurrent work. Once
  the old work settles, a new publication is emitted only when desired differs
  from landed.
- A closure observation becomes an ordinary closed dashboard event carrying its
  evidence-owned close instant. It supersedes unissued desired documents,
  reconciles already-issued work first, then causes one final closed
  publication before lifecycle generation close. Later facts cannot reopen it.
- The dashboard scenario runner mounts exact production construction and folds.
  It may inject typed terminal outcomes but cannot copy semantics or execute a
  provider implementation.
- `MANIFEST` declares gate, request type, closed terminal variants, execution
  lane, operation derivation and blocked mapping exactly once.
- The request carries stable business operation identity; correlation and
  idempotency equal it. Engine assigns the occurrence.
- Readiness retains and exposes occurrence, activity, operation, correlation,
  idempotency and exact decoded work from History/Dispatch evidence.
- One advancement may record one `ActivityRequested`; it cannot execute an
  effect inline.
- Pending work produces a bounded waiting posture and remains pending across
  fresh reconstruction.
- Wrong gate, duplicate manifest/token, malformed work or identity collision
  fails before an Activity is considered executable.
- Local subnet acceptance stabilizes its language and invariants but cannot
  close DS3 without the real DS2→workflow→History/Dispatch waiting path.

## Required standalone scenarios

The Navigator-facing runner presents concrete before/after values, imperative
steps and the invariant proved by each numbered scenario:

1. **First publication** — one event changes an empty projection and creates one
   exact pending publication.
2. **Desired drift while pending** — later events update desired state without
   creating concurrent work; settlement emits only the newest needed work.
3. **Request-time crash** — fresh reconstruction exposes the same occurrence,
   operation and immutable publication without requesting another one.
4. **Closure while pending** — close supersedes unissued desired state, waits
   for exact settlement, then emits one final closed publication; the close
   instant is replay-stable evidence, not wall-clock calculation.
5. **Wrong or unsuccessful outcome** — mismatched work/operation is refused;
   an admitted inability remains explicit retained state rather than pretending
   that desired and landed agree.

Scenario 4 proves isolated dashboard behavior only in DS3. DS4 supplies real
provider settlement, and DS9 later composes provider closure through final
dashboard convergence into committed lifecycle close.

## Known implementation blocker

Pinned Petrus `44cac5ff48ac371ebae56323941983f30db13c0d` exposes broad in-flight,
snapshot and paged-History inspection, but no public bounded seam that
reconstructs and repairs one selected unresolved occurrence. First advancement
after load reconciles every unresolved Activity, projection-pending and pure
occurrence in the rebuilt instance.

DS3 cannot honestly prove one-occurrence reconstruction, waiting posture or
unrelated-work bounds until Petrus supplies that public seam and Hamsterdan
updates its pin deliberately. Private `Instance` access, scanning complete
History as authority, or driving all unresolved work is not an acceptable
workaround. This blocker is distinct from DS2's accepted-but-unfolded
occurrence-resume requirement.

## API-strengthening checkpoint

Review the real observation→Activity call tree and settle:

- concrete `DashboardEvent` variants and dashboard document representation;
- `DashboardProjection`, `DashboardPublication` and
  `DashboardPublicationOutcome` fields plus stable operation grammar;
- exact standalone subnet construction, scenario command/observation and
  focused render/trace surfaces;
- `MANIFEST` entry, token registry, `build_net`, `seed_marking` and `wire_gates`
  signatures needed by the implemented loops;
- public Petrus request/replay/one-occurrence structures and errors;
- readiness advancement and pending-Activity/posture projections;
- History/Dispatch identities, correlation diagnostics and request-byte limits;
- local/cross checker evidence and resource gauges; and
- any compact workflow names that should be strengthened before first use.

Record all ruled values/signatures in [the API contract](api-contracts.md).
Workflow ownership, manifest completeness, exact identity and no-inline-effect
behavior are fixed.

## Tracer acceptance

Given the accepted DS2 observation, when bounded host/readiness advancement
runs, then the production workflow emits exactly one manifest-declared
`DashboardPublication`; History and Dispatch retain the same occurrence, work,
operation, correlation and idempotency; and inspection reports bounded waiting.

Before that vertical acceptance, the Navigator accepts the standalone
production dashboard subnet through the five numbered scenarios, focused
topology/marking inspection and fresh-object replay. Acceptance also proves
request-time crash/reconstruction, wrong
occurrence/operation/variant refusal before completion, a work-substitution
cross-checker counterexample, exact replay, lowered pending/History/byte limits,
and direct correspondence through the real Petrus Net/Engine/History/Dispatch
path. No provider call is permitted in the canonical artifact.

## Done condition

The dashboard subnet is accepted locally and the real DS2 input reaches one
durable production workflow request through that same production assembly in
the actual composed path. Pure workflow tests, a shadow scenario model or a
simulation-created request are necessary but insufficient.

## Stop conditions

Stop if the standalone runner cannot mount the exact production subnet, the
request requires copied folds, simulation-only workflow semantics, private
Petrus inspection, a readiness-authored `DashboardPublication`, inline provider
execution, or unbounded advancement past unrelated eligible actions.

## Rollback

Remove dashboard subnet/Activity behavior and its runtime/simulation growth.
DS2 still admits and folds one observation without requesting external work.

## Validation

Run standalone dashboard scenarios and focused topology rendering, workflow
vocabulary/topology/manifest tests, real Engine request paths, request
reconstruction, identity/variant failures, no-provider-call assertions,
local/cross sensitivity, replay, resource bounds and project gates.

## Expansion boundary

Expand pure workflow, runtime seam and evidence work as Technical Stories, but
keep the DS open until the admitted observation produces the real durable
Activity and bounded host-visible wait.
