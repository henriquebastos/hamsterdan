---
code: CV20
level: Value
status: Dropped
status_reason: Superseded before implementation by CV21 outer-system reconstruction and CV22 workflow replacement; retained as integrated design history
updated: 2026-08-28
related:
  - ../../exploration/es10-composable-hamsterdan-architecture/index.md
  - ../../decisions/records/2026-08-27T1604Z-composable-hamsterdan-is-the-planned-replacement-architecture.md
  - ../../decisions/records/2026-08-28T1453Z-cv20-fragments-into-outer-system-and-workflow-replacement-values.md
  - ../../decisions/records/2026-08-27T1925Z-cv20-delivers-through-vertical-tracer-bullets.md
  - ../../decisions/records/2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md
  - ../../decisions/records/2026-08-28T0153Z-configured-repository-recovery-discovers-unknown-open-pull-requests.md
  - ../../decisions/records/2026-08-28T1113Z-dashboard-closure-converges-before-generation-close.md
  - ../../decisions/records/2026-08-28T1114Z-cv20-accepts-production-subnets-locally-inside-vertical-tracers.md
  - ../cv19-private-v0-1-production/index.md
  - ../cv21-composable-outer-hamsterdan/index.md
  - ../cv22-decomposable-readiness-workflow/index.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20 — Composable, reconstructible Hamsterdan

> **Superseded 2026-08-28:** CV20 was not implemented. Its integrated
> complete-replacement plan is preserved for comparison and provenance. Current
> delivery ownership is [CV21](../cv21-composable-outer-hamsterdan/index.md) for
> the new outer system over one temporary bridge and
> [CV22](../cv22-decomposable-readiness-workflow/index.md) for the recursive
> production-subnet workflow, bridge removal, and final cutover. The remainder
> of this record describes the superseded CV20 plan and is not pullable work.

## Intent

Deliver one understandable Hamsterdan architecture in which pure workflow,
one-PR readiness execution, GitHub and agent implementations, trusted host
supervision, and deterministic simulation have typed, bounded ownership seams
and compose without duplicating semantic rules.

`src/hamsterdan2` and `tests2` are construction namespaces only. They are not a
selectable runtime and never read current V5 state. The current Hamsterdan V5
runtime remains the sole operational runtime through DS1–DS12. DS13 performs
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

1. [Architecture](architecture.md) — fixed decisions, package ownership,
   reviewed initial source map, import graph, runtime shape, durable authority
   and vocabulary.
2. [API contracts](api-contracts.md) — values, capabilities, identities,
   failures, bounded cuts, fixed names, and explicit DS-review questions.
3. [Delivery sequence](delivery-sequence.md) — tracer definition, linear graph,
   focused API review, state after each story, cumulative DST/observability,
   crash cuts, bounds and stop conditions.
4. [Replacement ledger](replacement-ledger.md) — module deletion test, reviewed
   initial test map, quality gate, 61/61 source and 46/46 test dispositions,
   fresh stores, cleanup and cutover inventory.
5. The selected Delivery Story — its owned paths, local contract slice,
   vertical path, component Technical Stories, API-strengthening questions and
   acceptance evidence.

These CV20 documents are the normative replacement design. Each DS Plan
Checkpoint may strengthen a listed DS-review name or signature and must update
the affected CV20 owner. It may not recover an alternative from exploration or
change a fixed boundary without a new Navigator ruling.

Delivery proceeds as a tracer ladder. Each of DS1–DS12 deepens one real
production spine from an external/operator/simulation command to a bounded
visible posture, durable workflow request, or accepted effect. Component work
is reviewable inside that tracer, not a separately accepted horizontal layer.
An exact production subnet may have a Navigator-facing local User Story and
acceptance checkpoint, but only the composed vertical path accepts Delivery.
Deterministic simulation, observability, crash recovery, finite bounds and
applicable correspondence ship with every tracer.

## Concept analysis

The [CV20 concept analysis](concept-analysis/index.md) records a reproducible,
non-authoritative extraction of final-system vocabulary across DS1–DS13. It
preserves source evidence, later refinements, exclusions and pending Navigator
questions while terms are reviewed one at a time. Accepted language belongs in
the project glossary; the analysis does not replace this Value's canonical
architecture, API contracts or Delivery Stories.

## Pending audit rulings

The [DS1–DS13 pending-rulings register](pending-rulings.md) preserves
reconciled audit evidence and recommendations for later Navigator review. It is
not canonical acceptance and changes no Delivery Story or decision.

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
DS1 bounded PR lifecycle -> DS2 observation -> DS3 Activity
  -> DS4 GitHub effect -> DS5 agent round -> DS6 causal mutation
  -> DS7 CI/repair -> DS8 timers -> DS9 authority/lifecycle
  -> DS10 unknown discovery -> DS11 multi-PR/discovery fairness
  -> DS12 qualification -> DS13 cutover
```

## Delivery

1. [CV20.DS1 — Establish the first bounded PR lifecycle](cv20-ds1-first-bounded-pr-lifecycle.md)
2. [CV20.DS2 — Admit and fold one PR observation](cv20-ds2-admit-fold-pr-observation.md)
3. [CV20.DS3 — Exercise the dashboard subnet and expose one Activity](cv20-ds3-expose-workflow-activity.md)
4. [CV20.DS4 — Settle one GitHub Activity lookup-first](cv20-ds4-settle-github-activity.md)
5. [CV20.DS5 — Settle one reconstructible agent round](cv20-ds5-settle-agent-round.md)
6. [CV20.DS6 — Publish one causally aligned mutation](cv20-ds6-publish-causal-mutation.md)
7. [CV20.DS7 — Recover CI and repair escalation](cv20-ds7-recover-ci-repair-escalation.md)
8. [CV20.DS8 — Recover timers and deferred work](cv20-ds8-recover-timers-deferred-work.md)
9. [CV20.DS9 — Fence lifecycle and authority changes](cv20-ds9-fence-lifecycle-authority.md)
10. [CV20.DS10 — Discover unregistered open PRs boundedly](cv20-ds10-discover-unregistered-open-prs-boundedly.md)
11. [CV20.DS11 — Supervise multiple PRs fairly](cv20-ds11-supervise-multiple-prs-fairly.md)
12. [CV20.DS12 — Qualify journeys and real-seam correspondence](cv20-ds12-qualify-journeys-correspondence.md)
13. [CV20.DS13 — Cut over and remove V5](cv20-ds13-cutover-remove-v5.md)

Every Delivery Story is `Planned`. Before implementation, the selected tracer
must expand into one or more User/Technical Stories and pass its own Plan
Checkpoint. Component Technical Stories cannot close the tracer without its
real vertical acceptance. Promotion does not pull DS1, authorize a deployment,
or change CV19's active priority.

## Done condition

CV20 is complete when:

1. the thirteen Delivery Stories satisfy their accepted outcomes and validation;
2. the final implementation preserves the stated user behavior, authority,
   credential, recovery, fairness, bounds, and replay contracts;
3. DS13 receives explicit approval for service, deployment, and state actions;
4. the replacement is the only canonical `hamsterdan` package and runtime;
5. no active runtime concept, path, identifier, schema, selector, compatibility
   reader, or operator instruction retains “Hamsterdan2” or “V5”; and
6. active product, project, process, decision, distribution, and deployment
   truth agrees with the cutover.

## Boundaries

- V5 remains the only runtime until DS13; `hamsterdan2` is never selectable.
- No replacement code opens, migrates, or converts current runtime state.
- No Delivery Story begins merely because CV20 is Planned.
- Provider mutations, production launch, cutover, state retention/deletion,
  release, commit, and push retain their existing explicit approval boundaries.
- Historical exploration, decisions, roadmap evidence, and worklogs keep their
  recorded V5 terminology; active runtime and operator surfaces do not.
