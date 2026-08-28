# DS3 concept extraction

## Source

- Delivery Story: [`../cv20-ds3-expose-workflow-activity.md`](../cv20-ds3-expose-workflow-activity.md)
- Cross-boundary contracts: [`../api-contracts.md`](../api-contracts.md),
  "Workflow Activity identity", "Activity manifest", "Dashboard subnet",
  "Standalone dashboard execution", "Workflow-runtime cuts" and "Readiness
  cuts"
- Cumulative sequence: [`../delivery-sequence.md`](../delivery-sequence.md),
  "DS3 — Dashboard subnet and one durable Activity"

Reviewed source revision: 2026-08-28 working tree after the accepted DS3
behavior and API review.

## Extracted behavior

DS3 first makes the exact production dashboard concern independently
constructible, step-able, renderable, crash/reconstructable, replayable and
checkable. The same `declare`/`wire`/`seed` construction is then mounted in the
whole workflow. This is a Navigator-facing acceptance boundary inside DS3, not
a separate CV and not a substitute for the vertical path.

The dashboard uses four durable token meanings rather than V5's mixed request
and recovery carriers:

1. `DashboardEvent` — internal workflow mail changing the desired dashboard;
2. `DashboardProjection` — desired, landed, one pending publication and one
   retained failure;
3. `DashboardPublication` — one immutable exact external command; and
4. `DashboardPublicationOutcome` — one exact-operation published, refused or
   uncertain terminal.

Those are also the only four dashboard colors. Entry/close and terminal
variants remain strict data inside event/outcome because they do not create
different custody or enabledness. The projection stays available while an
Activity is unresolved, so later events coalesce desired state while its exact
`pending` field enforces single flight.

Workflow alone creates `DashboardPublication`. Its stable operation hashes the
complete subject, document and exact rendered body, so cyclic event drift
cannot reuse an operation for changed bytes. Readiness preserves the exact
request and identity from History/Dispatch, exposes a bounded owner-local
`PendingActivity` plus a host-safe `ActivityWait`, and does not execute the
effect inline.

Closure is an evidence-timestamped normal dashboard event. It makes desired
state absorbing, reconciles one older pending publication, and then emits one
final closed publication. DS9 still owns the terminal-inability and lifecycle
generation-close policy.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| DS3 Outcome and User Story | Exact production dashboard construction is locally executable and inspectable before whole-flow acceptance | production subnet and owner-local acceptance are process vocabulary, not a shadow model |
| DS3 Fixed design and API contract / Dashboard subnet | Four meanings and four colors separate event, state, exact command and exact outcome | workflow Activity request remains distinct from workflow projection state |
| API contract / Dashboard subnet | Operation hashes complete subject/document/body; outcome must match exact pending operation | Activity identity contains work and operation; an operation cannot identify changed bytes |
| DS3 Required standalone scenarios | First publication, drift, request crash, closure and wrong/unsuccessful outcome exercise one runner | scenarios are evidence data over one production assembly, not five implementations |
| API contract / Standalone dashboard execution | Commands inject only typed events/outcomes; state/topology/check inspect real Petrus evidence | local checker and exact replay remain evidence, not runtime authority |
| API contract / Shared step result | `PendingActivity` retains complete owner-local detail while host receives only `ActivityWait` | pending Activity is durable work state; posture is a detached hint |
| DS3 Known implementation blocker | Pinned Petrus cannot repair one selected unresolved occurrence without broad reconciliation | bounded one-occurrence reconstruction remains a Petrus prerequisite, not a Hamsterdan workaround |

## Later ownership and refinements

- DS4 executes the exact publication lookup-first, finalizes bounded
  refusal/uncertainty reason codes, and settles the original occurrence through
  claim, effect-observed and terminal-recorded cuts.
- DS5–DS8 add Activity families through the same manifest/build boundary
  without changing dashboard identity or adding a second topology.
- DS9 owns lifecycle successors, final-dashboard terminal-inability policy and
  the commit that closes a lifecycle generation after final dashboard landing.
- Fixture-calibrated numeric byte/row/history/artifact limits are implementation
  Plan values with −1 / limit / +1 evidence, not unresolved domain design.

## Subordinate vocabulary to evaluate

- `DashboardEvent`, `DashboardProjection`, `DashboardDocument`,
  `DashboardPublication`, outcome variants and local scenario command names are
  concrete API vocabulary under the dashboard concern.
- `ActivityRequested` is Petrus's record/API name for request durability.
- occurrence, operation, correlation and idempotency remain fields within
  Activity identity rather than separate glossary concepts.
- `MANIFEST`, `TOKEN_CLASSES`, `GATES`, execution lanes and checker/resource
  keys remain construction/evidence vocabulary subordinate to Activity and
  production-subnet execution.
- waiting posture and individual cut names describe bounded runtime reporting,
  not separate workflow concepts.

## Deliberately unresolved beyond DS3

- Petrus's released public name/result/error types for bounded repair of one
  selected unresolved occurrence;
- DS4's concrete provider refusal/uncertainty reason codes and effect
  correspondence; and
- DS9's bounded operator-recovery or explicit generation-close policy when the
  final dashboard publication cannot land.

Private Petrus `Instance` access, complete-History authority, broad advancement
and a fake shadow reducer are ruled out rather than unresolved alternatives.

## Construction-only exclusions

- The non-selectable tracer handoff and temporary replacement paths disappear
  at DS13.
- Petrus dependency qualification, simulation commands, checker fields and
  resource gauges prove behavior but are not finished-product concepts.

## Trace handoff

The DS4–DS13 trace is complete in the
[candidate register](candidate-register.md). Whether Activity, Activity request
and Activity identity are distinct concepts remains for later Navigator review.
