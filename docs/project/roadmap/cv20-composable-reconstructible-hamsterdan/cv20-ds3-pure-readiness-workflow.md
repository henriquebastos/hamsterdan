---
code: CV20.DS3
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

# CV20.DS3 — Deliver the pure readiness workflow

## Outcome

Implement the CV20 workflow vocabulary, nine concern loops, explicit Activity
manifest, token registry, topology, typed blocked/review-evidence outcomes, and
correlation contract under `workflow`, with no runtime execution or
`ready.facts` compatibility lane.

## CV20 contract

This story implements the pure owner defined in
[the architecture](architecture.md). Its public build boundary, value groups,
Activity families, terminal unions, timer values and mutation causal fields are
fixed in [the API contract](api-contracts.md).

## Owned paths

```text
src/hamsterdan2/workflow/values.py
src/hamsterdan2/workflow/observations.py
src/hamsterdan2/workflow/facts.py
src/hamsterdan2/workflow/activities.py
src/hamsterdan2/workflow/net/**
tests2/behavioral/workflow/**
tests2/integration/test_workflow_runtime.py
```

`workflow/simulation` remains a placeholder until DS9. Readiness runtime and
effect implementations are outside this story.

## Fixed design

- Nine loops own lifecycle, CI, escalation, review, mutation, conversation,
  dashboard, reminders and readiness projection.
- Values remain with workflow; there is no target `contracts` package.
- `build_net`, `seed_marking`, `TOKENS`, `MANIFEST` and `wire_gates` are the
  public construction vocabulary.
- Every gate appears exactly once in the manifest with request type, closed
  terminal variants, lane, operation derivation and blocked mapping.
- Topology imports every loop by defining module and rejects duplicate/missing
  token colors or gates.
- Workflow imports Petrus defining modules but no Engine lifecycle, store,
  provider, agent, host, clock, filesystem or database effect.
- Exact terminal occurrence/correlation is part of the request/return contract;
  readiness runtime enforces admission in DS7.
- `MutWork` is derived by real workflow folds and carries no agent result.
- Timer commands and due facts are workflow-owned; custody is not.
- `ready.facts`, V5 names and compatibility folds/arcs are absent.

## Position and predecessors

Requires CV20.DS1. It may proceed beside DS2 because it imports Petrus defining
modules but not runtime execution objects.

## Implementation sequence

1. Rule the final workflow value, manifest and build signatures below.
2. Implement shared values, observations, facts and Activity work/terminal
   families with strict round-trip validation.
3. Implement pure fold/hydration and manifest-driven gate binding.
4. Implement the nine loops in behavior-coherent groups.
5. Compose topology, initial marking, explicit token registry and build-time
   validation.
6. Run real Engine paths with declaration-only Activities: observation to work,
   exact typed terminal to final fold.
7. Prove wrong occurrence, operation and terminal variant fail closed and that
   no compatibility lane or forbidden import exists.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- final names/fields for workflow observations, shared facts and loop-private
  state;
- final Activity request and terminal names, including whether current compact
  names such as `ALanded` and `FaultM` should become capability-stating names;
- `MANIFEST` entry data shape and operation-derivation API;
- `build_net`, `seed_marking` and `wire_gates` signatures;
- token registry representation and collision diagnostics;
- fold/hydration call-site shape without reflection over module globals; and
- timer value fields in integer microseconds.

Renaming is allowed only as one coherent vocabulary update across loops,
manifest, CV20 contracts and tests. Ownership and terminal meanings are fixed.

## Done condition

The real Petrus Net derives exact typed Activity work from normalized
observations and folds exact correlated terminals; workflow imports no effectful
owner; every loop, token, and gate is declared and validated; and no copied
compatibility transition remains.

## Rollback

Remove the replacement workflow and its tests. No installed runtime imports it.

## Validation

Run the behavioral loop portfolio, registry collision/missing-color tests, AST
purity/cycle/facade checks, real Engine observation→Activity→terminal paths,
wrong occurrence/operation/variant refusal, and the production-Net
observation-to-work and terminal-to-fold correspondence scenarios.

## Expansion boundary

Expand by coherent workflow behavior groups rather than one file per loop; each
User or Technical Story must preserve a real Net validation route. The final
workflow vocabulary is written into the CV20 API contract before DS7/DS9 use it.
