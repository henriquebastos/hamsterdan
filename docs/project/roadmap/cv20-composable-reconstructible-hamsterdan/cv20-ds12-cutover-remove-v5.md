---
code: CV20.DS12
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS10 and CV20.DS11 plus explicit cutover approval
updated: 2026-08-27
related:
  - index.md
  - cv20-ds10-readiness-journey-portfolio.md
  - cv20-ds11-real-provider-process-correspondence.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
  - ../../decisions/records/2026-08-27T1604Z-composable-hamsterdan-is-the-planned-replacement-architecture.md
---

# CV20.DS12 — Cut over and remove V5

## Outcome

After separate explicit approval, stop the current service, preserve its state
only as bounded rollback data, rename `src/hamsterdan2` to canonical
`src/hamsterdan`, move `tests2` into canonical Python test paths, retain the Amp
relay gate, switch packaging/entry points/deployment, and remove the current
source, tests, schemas, configuration, and active documentation.

The finished system is simply Hamsterdan. “Hamsterdan2” was only a construction
namespace and “V5” described the removed implementation; neither survives as an
active runtime, identity, path, schema, selector, compatibility, or operator
concept.

## CV20 contract

This story performs the only runtime transition allowed by
[the architecture](architecture.md). The exact source/test/schema/name
disposition and quality-gate promotion are in
[the replacement ledger](replacement-ledger.md); the preconditions, no-return
point and final state are in [the delivery sequence](delivery-sequence.md).

Before this story, operators run only current Hamsterdan (V5); the replacement
tree is non-selectable construction work. After this story, the qualified
replacement has the canonical `hamsterdan` package, service, state and operator
names. There is no V5, Hamsterdan2, generation selector or dual-runtime concept.

## Owned paths

DS12 owns the coordinated repository-wide transition, limited by the exact
disposition ledger:

```text
src/hamsterdan/**              remove old implementation; move replacement here
tests/**                       remove old Python tests; move tests2 here
src/hamsterdan2/**             construction path must disappear
tests2/**                      construction path must disappear
quality/hamsterdan2/**         promote rules to canonical configuration/remove
pyproject.toml and uv.lock     package, entry points, dependencies, test config
scripts/check                  canonical gate names/paths
deployment/** and .github/**   one canonical service/runtime where applicable
README.md and active docs      describe only resulting Hamsterdan
old runtime schemas/roots      remove from active access; snapshot is opaque
```

The 61-source and 46-Python-test ledgers are exhaustive. The maintained Amp
relay test remains canonical and is not part of that Python census.

## Fixed design

- DS12 starts only after accepted DS10/DS11 evidence, a fresh full qualification
  run and explicit Navigator/operator approval of shared actions.
- The existing V5-only operational decision remains in force until the cutover
  decision supersedes it. There is no pre-DS12 selector or shadow runtime.
- The current service is stopped and fenced before state snapshot or package
  replacement. In-flight external operations are reconciled by stable identity.
- Old state is captured as bounded, read-only, access-controlled rollback data.
  The replacement neither reads nor migrates it.
- The old source/tests are removed and the replacement moves to canonical names
  as one reviewable cutover change. No adapters, aliases or compatibility
  schemas bridge the implementations.
- New canonical Hamsterdan starts from fresh roots and is qualified before
  accepting external mutation.
- The no-return point is the first externally accepted mutation by the new
  canonical runtime. Before it, rollback restores old image/package and opaque
  snapshot. After it, rollback requires explicit external reconciliation and
  never a schema downgrade.
- Packaging, entry points, deployment, service identity, configuration, gates,
  operator commands and active documentation all use only `hamsterdan`.
- Active code/config/schema/docs have a zero-match census for `hamsterdan2`, V5,
  topology selectors and compatibility-lane names. Dated historical records may
  retain those terms as provenance.
- Old-state deletion is not implied by cutover; it is a later separately
  approved destructive action.

## Position and predecessors

Requires accepted CV20.DS10 and DS11, explicit Navigator approval for shared
deployment/state actions, and a cutover decision that supersedes the current
V5-only operational decision.

## Implementation sequence

1. Rule the cutover command/evidence API below and expand DS12 into preparation,
   shared action, fresh-runtime qualification and no-return cleanup stories.
2. Re-run DS10/DS11/full gates on the exact candidate revision; record artifacts,
   dependency versions, resource bounds and correspondence limits.
3. Inventory active service/routes/operations; drain or reconcile them by stable
   identity, then stop and fence the current service.
4. Create and verify the bounded read-only old-state snapshot; record restore and
   disposal custody without exposing it to replacement code.
5. Apply the disposition ledger: remove old implementation/tests, move
   replacement to canonical paths, promote its gate, switch packaging/service/
   deployment/configuration, and update active documentation.
6. Run path/name/schema/import/distribution/deployment censuses and the complete
   qualification portfolio from fresh canonical state.
7. Start canonical Hamsterdan under bounded supervision; verify read-only
   startup, health, inspection and restart/reconstruction before mutation.
8. Obtain explicit no-return approval, execute one separately approved bounded
   external operation, reconcile it, restart, and prove one accepted effect.
9. Remove temporary cutover machinery and any active fallback/selector; retain
   only the opaque rollback snapshot under its separate custody policy.
10. Record final coherence: there is one Hamsterdan, no V5/Hamsterdan2 concept,
    and no active old-state reader.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- preparation/inspect/stop/snapshot/verify/start/reconcile command names and
  arguments;
- mandatory dry-run and confirmation behavior for destructive/shared commands;
- cutover plan, preflight, action journal and final evidence schemas;
- snapshot identity, integrity, access, retention and restore contracts;
- no-return approval/evidence representation and exact external-operation
  fixture;
- active-name/path/schema census scope and machine-readable failure format;
- rollback command/decision surface on each side of no-return; and
- removal of temporary construction-only command names after completion.

These APIs exist only to perform and audit the cutover; they do not become a
permanent version-selection surface. The no-dual-runtime, fresh-state,
canonical-name and no-compatibility decisions are fixed.

## Done condition

Only canonical `hamsterdan` source/tests/package/entry points exist; fresh state
runs the qualified replacement; no new runtime opens old state; no active code,
configuration, schema, deployment, or operator documentation names
`hamsterdan2`, V5, or a topology selector; and active project/product/process
truth describes the single resulting Hamsterdan runtime.

Historical records may retain their dated terminology. Any retained old-state
snapshot is opaque rollback custody, not an available runtime or compatibility
contract.

## Rollback

Before the no-return checkpoint, restore the old package/image and read-only
state snapshot and discard fresh replacement roots. After a new external effect
is accepted by canonical Hamsterdan, rollback requires explicit operator
reconciliation under stable external operations, never a schema downgrade.
Old-state deletion remains a later separately approved action.

## Validation

Run forbidden active-name/schema/path census, no-old-package imports,
source/wheel install and CLI smoke, full gates and journeys, fresh-state startup,
bounded supervised launch, one approved real operation, restart/reconciliation,
active-doc/decision coherence, deployment identity, and secret scan.

## Expansion boundary

Expand into separately reviewable cutover preparation, shared operator action,
fresh-runtime qualification, and no-return cleanup stories. No expansion may
weaken the explicit approval boundary or add compatibility architecture. All
final operational steps must be understandable from CV20 alone before shared
action is requested.
