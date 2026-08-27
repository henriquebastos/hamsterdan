---
code: CV20
level: Value
status: Planned
status_reason: ES-010 is promoted with twelve planned Delivery Stories; none is pulled while CV19 remains active
updated: 2026-08-27
related:
  - ../../exploration/es10-composable-hamsterdan-architecture/index.md
  - ../../decisions/records/2026-08-27T1604Z-composable-hamsterdan-is-the-planned-replacement-architecture.md
  - ../cv19-private-v0-1-production/index.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20 — Composable, reconstructible Hamsterdan

## Intent

Deliver one understandable Hamsterdan architecture in which pure workflow,
one-PR readiness execution, GitHub and agent implementations, trusted host
supervision, and deterministic simulation have typed, bounded ownership seams
and compose without duplicating semantic rules.

`src/hamsterdan2` and `tests2` are construction namespaces only. They are not a
selectable runtime and never read current V5 state. The current Hamsterdan V5
runtime remains the sole operational runtime through DS1–DS11. DS12 performs
one separately approved cutover: the replacement becomes canonical
`src/hamsterdan` and `tests`, the current implementation is removed, and the
temporary “Hamsterdan2” and “V5” concepts disappear from active runtime,
configuration, schema, and operator language.

## Value

Workflow, readiness execution, provider and agent implementations, host
supervision, and simulation compose through explicit capabilities while
preserving current user behavior, independent PR progress, authority fencing,
credential isolation, at-least-once effects, lookup-first recovery, finite
bounds, and exact deterministic replay.

## Canonical implementation contract

CV20 is self-contained for implementation and review. Read these local owners
in order:

1. [Architecture](architecture.md) — fixed decisions, package ownership, exact
   source tree, import graph, runtime shape, durable authority and vocabulary.
2. [API contracts](api-contracts.md) — values, capabilities, identities,
   failures, bounded cuts, fixed names, and explicit DS-review questions.
3. [Delivery sequence](delivery-sequence.md) — dependency graph, state after
   each story, cross-story handoffs, validation matrix, crash cuts, bounds and
   stop conditions.
4. [Replacement ledger](replacement-ledger.md) — module deletion test, exact
   test tree, quality gate, 61/61 source and 46/46 test dispositions, fresh
   stores, cleanup and cutover inventory.
5. The selected Delivery Story — its owned paths, local contract slice,
   implementation order, API-strengthening questions and acceptance evidence.

These CV20 documents are the normative replacement design. Each DS Plan
Checkpoint may strengthen a listed DS-review name or signature and must update
the affected CV20 owner. It may not recover an alternative from exploration or
change a fixed boundary without a new Navigator ruling.

## Exploration provenance

[ES-010](../../exploration/es10-composable-hamsterdan-architecture/index.md)
and its
[S12 synthesis](../../exploration/es10-composable-hamsterdan-architecture/experiments/12-enforcement-delivery.md)
record how the design was derived, the experiments, rejected alternatives and
correspondence limits. They are audit references, not required reading for a
CV20 implementation or API review. If historical wording differs from the
canonical CV20 contract, CV20 governs Delivery.

## Delivery graph

```text
DS1 replacement gate
 ├─ DS2 Petrus/Motus seams
 ├─ DS3 workflow
 ├─ DS4 simulation runtime
 ├─ DS5 GitHub provider
 └─ DS6 agents

DS2 + DS3 + DS4 + DS5 + DS6 ──▶ DS7 readiness
DS6 + DS7                    ──▶ DS8 host
DS3 + DS4 + DS5 + DS6 + DS7 + DS8 ──▶ DS9 composition
DS7 + DS8 + DS9              ──▶ DS10 journeys
DS8 + DS10                   ──▶ DS11 correspondence
DS10 + DS11                  ──▶ DS12 cutover
```

## Delivery

1. [CV20.DS1 — Establish the replacement-tree gate](cv20-ds1-replacement-tree-gate.md)
2. [CV20.DS2 — Own bounded Petrus and Motus execution seams](cv20-ds2-bounded-petrus-motus-execution-seams.md)
3. [CV20.DS3 — Deliver the pure readiness workflow](cv20-ds3-pure-readiness-workflow.md)
4. [CV20.DS4 — Deliver the Hamsterdan simulation runtime](cv20-ds4-hamsterdan-simulation-runtime.md)
5. [CV20.DS5 — Deliver strict GitHub provider operations](cv20-ds5-strict-github-provider-operations.md)
6. [CV20.DS6 — Deliver reconstructible agent execution](cv20-ds6-reconstructible-agent-execution.md)
7. [CV20.DS7 — Deliver one-PR readiness execution](cv20-ds7-one-pr-readiness-execution.md)
8. [CV20.DS8 — Deliver trusted host custody and fair supervision](cv20-ds8-trusted-host-custody-fair-supervision.md)
9. [CV20.DS9 — Compose whole Hamsterdan deterministically](cv20-ds9-whole-hamsterdan-deterministic-composition.md)
10. [CV20.DS10 — Requalify the readiness journey portfolio](cv20-ds10-readiness-journey-portfolio.md)
11. [CV20.DS11 — Prove real provider and process correspondence](cv20-ds11-real-provider-process-correspondence.md)
12. [CV20.DS12 — Cut over and remove V5](cv20-ds12-cutover-remove-v5.md)

Every Delivery Story is `Planned`. Before implementation, the selected story
must expand into one or more User or Technical Stories and pass its own Plan
Checkpoint. Promotion does not pull DS1, authorize a deployment, or change
CV19's active priority.

## Done condition

CV20 is complete when:

1. the twelve Delivery Stories satisfy their accepted outcomes and validation;
2. the final implementation preserves the stated user behavior, authority,
   credential, recovery, fairness, bounds, and replay contracts;
3. DS12 receives explicit approval for service, deployment, and state actions;
4. the replacement is the only canonical `hamsterdan` package and runtime;
5. no active runtime concept, path, identifier, schema, selector, compatibility
   reader, or operator instruction retains “Hamsterdan2” or “V5”; and
6. active product, project, process, decision, distribution, and deployment
   truth agrees with the cutover.

## Boundaries

- V5 remains the only runtime until DS12; `hamsterdan2` is never selectable.
- No replacement code opens, migrates, or converts current runtime state.
- No Delivery Story begins merely because CV20 is Planned.
- Provider mutations, production launch, cutover, state retention/deletion,
  release, commit, and push retain their existing explicit approval boundaries.
- Historical exploration, decisions, roadmap evidence, and worklogs keep their
  recorded V5 terminology; active runtime and operator surfaces do not.
