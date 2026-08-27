---
code: CV20.DS10
level: Delivery Story
status: Planned
status_reason: Waits for CV20.DS7–DS9 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds7-one-pr-readiness-execution.md
  - cv20-ds8-trusted-host-custody-fair-supervision.md
  - cv20-ds9-whole-hamsterdan-deterministic-composition.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS10 — Requalify the readiness journey portfolio

## Outcome

Express the eleven accepted semantic journeys plus the causal mutation journey
through replacement production owners and composed simulation. Each journey
names user-visible behavior, authority, stable operation, effect cardinality,
crash/recovery cuts, and finite bounds.

## CV20 contract

This story is the executable behavior portfolio for the contracts in
[the architecture](architecture.md) and [the API contract](api-contracts.md).
It adds no alternative model or production abstraction. It drives the DS7/DS8
public surfaces and DS9 composed simulation, and emits one uniform journey
report for DS11/DS12 qualification.

## Owned paths

```text
tests2/acceptance/test_journeys.py
tests2/acceptance/test_recovery.py
```

Journey DSL/helpers remain local to these files until independent reuse is
demonstrated. New production modules and a second acceptance framework are out
of scope.

## Fixed design

- The twelve top-level journeys are: clean green; first-attempt flake;
  persistent CI regression; seeded review finding; conversational change;
  agent repair; hero review; draft-to-ready; stale base update; true conflict
  resolution; collaboration approval; and causal exact delivered-result
  mutation publication.
- Reminder/timer progression, route revocation, ambiguous Git recovery and PR
  closure are required recovery/authority overlays across the applicable
  journeys. They do not create extra top-level journey identities.
- Every journey declares initial state, user/provider input, expected posture,
  authority evidence, stable operations, accepted external-effect cardinality,
  named crash cuts and finite resource bounds.
- Journeys use production owner APIs and DS9 composition; they do not call
  private stores, patch hidden runtime state or fabricate workflow terminals.
- Recovery scenarios restart from fresh object graphs and persistent roots.
  Process-local continuation is not evidence.
- Mutation publication checks the real workflow work, canonical coding request,
  exact accepted agent result, publication dependency and original Activity
  occurrence closure.
- Schedule generation has finite operation/interleaving/fault domains. Shrunk
  failures retain the same semantic violation and exactly replay.
- Reports distinguish local-owner failure, cross-module failure, bound failure
  and correspondence-unavailable. A green aggregate never hides a skipped
  required scenario.
- The replacement remains non-selectable; these journeys do not exercise a
  deployment selector or current V5 state.

## Position and predecessors

Requires CV20.DS7–DS9. It qualifies behavior but does not enable the replacement
runtime.

## Implementation sequence

1. Rule the journey DSL, scenario identity and report contract below.
2. Encode the non-mutating lifecycle/CI/review/posture journeys.
3. Encode timer, route-revocation, closure and conflict/stale-authority
   journeys.
4. Encode mutation and ambiguous Git response-loss journeys with exact
   operations and effect cardinality.
5. Encode the causal exact delivered-result journey and sensitivity controls.
6. Add finite schedule generation, semantics-preserving shrinking and exact
   replay.
7. Run the complete portfolio through production owners and composed
   simulation; lower declared bounds to prove they are real.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- scenario/journey identifier and declaration vocabulary;
- DSL names for state setup, input, named cut, restart, effect/cardinality,
  posture and bound expectations;
- whether synchronous and generated schedules share one scenario value or two
  explicit types;
- shrink input/output and “same semantic violation” contract;
- per-journey and portfolio report schemas, skip/unavailable policy and stable
  diagnostic fields; and
- evidence artifact linkage consumed by DS11 and DS12.

These are acceptance APIs, not production extension points. The named behavior
families, real-owner execution, causal path, finite generation and exact replay
are fixed.

## Done condition

All twelve named journeys pass with their applicable timer, revocation,
Git-ambiguity and closure overlays; every required physical effect count and
crash cut passes; and generated schedules shrink and exactly replay.

## Rollback

Remove incomplete replacement acceptance scenarios. Prior production-owner and
simulation stories remain green; current production remains V5.

## Validation

Run the complete journey portfolio with exact authority/effect assertions,
crash cuts, lowered resource bounds, generated schedule shrinking, and replay.

## Expansion boundary

Expand into behavior-coherent journey groups with Navigator-visible outcomes;
do not organize stories around internal modules alone. Record accepted journey
and report vocabulary in CV20 so DS11 does not infer it from tests.
