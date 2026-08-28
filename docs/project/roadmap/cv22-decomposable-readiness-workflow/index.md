---
code: CV22
level: Value
status: Planned
status_reason: Known workflow concerns are manifested as low-detail Delivery Stories; every story remains unpulled pending CV21 and the typed hierarchy/conformance ruling
updated: 2026-08-28
related:
  - ../../decisions/records/2026-08-28T1453Z-cv20-fragments-into-outer-system-and-workflow-replacement-values.md
  - ../../decisions/records/2026-08-28T1113Z-dashboard-closure-converges-before-generation-close.md
  - ../../decisions/records/2026-08-28T1114Z-cv20-accepts-production-subnets-locally-inside-vertical-tracers.md
  - ../cv21-composable-outer-hamsterdan/index.md
  - ../cv20-composable-reconstructible-hamsterdan/index.md
  - architecture.md
  - cv22-ds1-rebuild-dashboard-subnet.md
  - cv22-ds2-rebuild-lifecycle-subnet.md
  - cv22-ds3-rebuild-ci-subnet.md
  - cv22-ds4-rebuild-escalation-subnet.md
  - cv22-ds5-rebuild-review-subnet.md
  - cv22-ds6-rebuild-mutation-subnet.md
  - cv22-ds7-rebuild-conversation-subnet.md
  - cv22-ds8-rebuild-reminders-subnet.md
  - cv22-ds9-rebuild-readiness-projection-subnet.md
  - cv22-ds10-compose-root-readiness-workflow.md
  - cv22-ds11-qualify-workflow-and-remove-bridge.md
  - cv22-ds12-cut-over-canonical-hamsterdan.md
---

# CV22 — Decomposable PR-readiness workflow

## Intent

Replace the temporary CV21 bridge and retained V5 Petri Net with a simpler
workflow assembled from production subnets that can each be understood, run,
inspected, reconstructed, replayed, and deterministically checked in isolation
and at every containing scale.

## Value

A maintainer can focus on one workflow concern—or one nested child of that
concern—without loading the entire project into working memory. Accepted local
behavior remains the exact production assembly used by its parent workflow and
the complete Hamsterdan tracer. The finished workflow preserves intended user
behavior while removing V5 concepts and the temporary bridge.

## Input from CV21

CV22 starts only after CV21 supplies:

- a qualified typed workflow boundary for observations, Activity work,
  terminals, occurrences, operation identity, and detached posture;
- new readiness runtime, custody, effects, authority, host, provider, agent, and
  deterministic owners;
- exact bridge-family correspondence and complete outer journey evidence; and
- a proven factory seam at which the workflow provider can be replaced without
  changing outer imports or contracts.

CV22 does not redesign the outer system while replacing the workflow. A missing
outer capability returns to its CV21 owner rather than being hidden in a subnet.

## Fixed direction

Every production workflow concern must be:

1. independently constructible from its exact production assembly;
2. executable one action at a time through strict typed boundary values;
3. inspectable through marking, arcs, pending Activity/History evidence, and a
   generated view from that mounted production subnet;
4. crashable and reconstructible at every owned durable cut;
5. exactly replayable with local checker and finite resource evidence; and
6. mounted unchanged in its parent subnet, workflow-owner simulation, and root
   CV21 composition.

These rules apply recursively when one subnet contains other subnets. Local
Navigator acceptance stabilizes a subnet's behavior and language. Isolated
green evidence alone does not close its Delivery Story; the story's Plan
Checkpoint identifies the containing composition edge required for acceptance.

## Delivery Story manifest

The current working workflow already establishes nine concern boundaries worth
preserving as independently reviewable production-subnet stories. Their story
numbers identify the initial inventory; they do not yet fix implementation
order, parent/child hierarchy, typed ports, or internal topology.

1. [Dashboard](cv22-ds1-rebuild-dashboard-subnet.md)
2. [Lifecycle admission](cv22-ds2-rebuild-lifecycle-subnet.md)
3. [CI observation](cv22-ds3-rebuild-ci-subnet.md)
4. [Escalation and repair](cv22-ds4-rebuild-escalation-subnet.md)
5. [Review](cv22-ds5-rebuild-review-subnet.md)
6. [Mutation](cv22-ds6-rebuild-mutation-subnet.md)
7. [Conversation](cv22-ds7-rebuild-conversation-subnet.md)
8. [Reminders](cv22-ds8-rebuild-reminders-subnet.md)
9. [Readiness projection and announcement](cv22-ds9-rebuild-readiness-projection-subnet.md)
10. [Root workflow composition](cv22-ds10-compose-root-readiness-workflow.md)
11. [Replacement qualification and bridge removal](cv22-ds11-qualify-workflow-and-remove-bridge.md)
12. [Final cutover](cv22-ds12-cut-over-canonical-hamsterdan.md)

This is deliberately a low-detail manifest. Before a subnet story is pulled,
its Plan Checkpoint must establish its actual boundary and acceptance. If that
work reveals independently meaningful nested production subnets, each child is
manifested before its containing story is pulled rather than hidden as a
Technical Story.

## Design prerequisite before pulling a Delivery Story

CV22 must first rule:

- what a typed subnet boundary contains and which intermediate states are
  externally observable;
- how parent and child assemblies connect and who owns boundary places/values;
- when parent-first development may substitute an abstract child and what
  deterministic evidence proves that the concrete child conforms;
- whether composition is flattened `NetSpec` construction, retained hierarchy,
  or another production representation; and
- which behavioral equivalence is required when an abstract boundary hides
  concurrency, multiple ports, Activities, cancellation, or failure.

Until this is ruled, “one magical transition” is a useful sketch, not a
production contract. The manifest records known work without pretending that
its hierarchy, order, or implementation contract is settled.

## First concrete subnet

The accepted dashboard design remains the first concrete workflow target. It
has four distinct meanings—event, projection, immutable publication command,
and exact publication outcome—plus single-flight publication and final closed-
document convergence before lifecycle generation close. CV22 does not reopen
that behavior while settling the general recursive composition mechanism.

## Expected completion

CV22 completes when:

1. every workflow concern and nested subnet satisfies local and composed
   deterministic acceptance through its exact production assembly;
2. complete workflow/root journeys preserve intended behavior and CV21 outer
   contracts without the bridge;
3. no new package imports current `hamsterdan`, no V5 type/schema/name escapes,
   and all bridge-specific state and artifacts are removed;
4. a separately approved final cutover removes the current implementation,
   renames the construction tree and tests to canonical Hamsterdan paths, and
   updates packaging, deployment, configuration, and active documentation; and
5. neither “Hamsterdan2” nor “V5” remains an active runtime, path, schema,
   selector, compatibility, or operator concept.

## Boundaries

- Current V5 remains the sole runtime until the final cutover.
- Pre-cutover CV22 uses fresh disposable construction state and remains
  non-selectable.
- CV22 does not migrate or convert current state and does not maintain the
  bridge after cutover.
- Exploration records may inform the hierarchy ruling but do not decide it.
- Deployment, current-state retention/deletion, cutover, rollback, commit,
  push, and release retain explicit approval boundaries.
