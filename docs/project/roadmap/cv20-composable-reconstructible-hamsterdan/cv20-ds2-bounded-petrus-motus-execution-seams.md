---
code: CV20.DS2
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

# CV20.DS2 — Own bounded Petrus and Motus execution seams

## Outcome

Deliver public Petrus page-bounded History replay and one-occurrence repair,
plus Motus claim, effect-observed, and terminal-recorded cuts. Pin the qualified
dependency and expose it through a thin `readiness.runtime` contract without
private Petrus inspection or patching.

## CV20 contract

This story supplies the dependency seam consumed later by one-PR readiness. It
does not implement workflow meaning or the readiness application. The fixed
cut names and bounds are in [the API contract](api-contracts.md); the cross-story
handoff is in [the delivery sequence](delivery-sequence.md).

## Owned paths

```text
Petrus repository                  public bounded History replay/repair
Petrus Motus runtime               claim/effect-observed/terminal-recorded seams
pyproject.toml and uv.lock         qualified dependency pin
src/hamsterdan2/readiness/runtime.py
tests2/behavioral/readiness/test_runtime.py
tests2/integration/test_workflow_runtime.py
```

Only a thin replacement-side adapter/contract enters `readiness.runtime` in
this story. DS7 later owns full runtime composition.

## Fixed design

- History reconstruction is page-bounded by records and bytes.
- Repair handles at most one retained occurrence per returned step.
- Activity execution exposes separate durable claim, effect-observed and
  terminal-recorded positions.
- One effect step makes at most one provider mutation attempt.
- A response-lost accepted effect is observable after execution and before
  terminal record.
- Terminal admission can compare Activity, occurrence, correlation,
  idempotency and terminal operation before History folding.
- Hamsterdan imports public defining/runtime modules. It does not inspect,
  monkey-patch or reach into private Petrus state.
- Dependency changes have their own tests, history and publication approval.

## Position and predecessors

Requires CV20.DS1. It may proceed in parallel with DS3–DS6 after the gate is
accepted.

## Implementation sequence

1. Expand into independently reviewable Petrus History, Motus execution and
   Hamsterdan integration stories.
2. Rule exact public signatures and error/cursor values.
3. Implement page-bounded replay and one-occurrence repair with boundary tests.
4. Split Motus claim, effect-observed and terminal-recorded positions.
5. Prove accepted-effect response loss and one-attempt cardinality.
6. Pin the qualified dependency and exercise only public APIs through the thin
   replacement runtime contract.
7. Build/test both repositories before accepting the handoff to DS7.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- History page request/cursor/result shapes and terminal page semantics;
- one-occurrence repair request/result and closed repair kinds;
- Motus attempt claim, observed effect and terminal record signatures;
- correlation-mismatch and boundedness error taxonomies;
- sync/async boundaries and transaction ownership; and
- dependency pin and cross-repository landing order.

The names may change during this review, but the five public cut meanings and
one-attempt bound may not.

## Done condition

Petrus and Motus expose the required bounded public seams; one effect step makes
at most one provider mutation attempt; response-loss recovery is observable at
each cut; and Hamsterdan imports only defining/public modules under the pinned
dependency.

## Rollback

Revert the dependency pin and replacement runtime adapter. The current runtime
continues using its existing dependency and state.

## Validation

Run Petrus unit/property tests, bounded History/occurrence tests, accepted-effect
response-loss cuts, one-attempt checks, Hamsterdan integration, and dependency
builds.

## Expansion boundary

Expand into independently reviewable Petrus/Motus and Hamsterdan integration
Technical Stories before implementation. Changes in another repository retain
their own plan, history, and push checkpoints. Accepted API names/signatures
must be written into the CV20 API contract before DS7 relies on them.
