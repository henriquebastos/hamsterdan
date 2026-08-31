# CV22 workflow architecture direction

This document separates fixed workflow direction from the unresolved mechanism
that must be ruled before a manifested CV22 Delivery Story is pulled.

## Fixed workflow ownership

The replacement workflow owns only pure process meaning:

- normalized typed observations accepted at the CV21 boundary;
- concern-local state, folds, topology, gates, and lifecycle decisions;
- typed facts passed between workflow concerns;
- immutable Activity work and closed terminal families;
- initial marking, completion, and explicit failure state; and
- local deterministic scenario/checker language derived from production
  assemblies.

It imports no readiness runtime, Engine lifecycle, Dispatch/Worker execution,
provider or agent implementation, host, clock, credential, storage, filesystem,
HTTP, or simulation effect. CV21 readiness supplies execution and external
effects through the unchanged boundary.

## Recursive production-subnet invariant

A **production subnet assembly** is the one construction used in every context.
It is never a review-only diagram, copied reducer, permissive mock, or alternate
test topology.

For every concern and nested concern:

```text
exact production assembly
  ├─ mounted alone in subnet-local deterministic execution
  ├─ mounted unchanged in its containing production subnet
  ├─ mounted unchanged in workflow-owner deterministic execution
  └─ mounted unchanged behind CV21 readiness in root composition
```

Each local runner exposes typed boundary injection, one-action stepping, current
marking and arcs, pending Activity and History evidence, strict terminal
delivery, named crash/reconstruction cuts, exact replay, local checker failures,
resource gauges, and a generated view. Parent and root checkers judge only
relationships not already owned locally.

## Construction hierarchy is not yet behavioral abstraction

Current Petrus `NetSpec` can stamp nested specifications and flatten their paths
into one built Net. That establishes reusable construction, but does not by
itself prove that a child can be replaced by one abstract transition while a
parent is developed.

A child may expose behavior that one transition cannot represent:

- several input or output moments rather than one atomic firing;
- intermediate state visible to sibling concerns;
- internal concurrency or choice affecting boundary order;
- pending Activities and exact terminal occurrences;
- cancellation, retry, deferred time, or retained failure; and
- resource/liveness obligations observable before final output.

CV22 therefore distinguishes:

1. **structural composition** — how exact production specs are assembled; and
2. **contract substitution** — when a smaller executable abstraction may stand
   in for a child while proving a parent independently.

Only the first is currently evidenced. The second requires a Navigator ruling
backed by executable examples and counterexamples.

## Required hierarchy ruling

The pre-delivery design checkpoint must answer, in order:

1. What are the child's typed input/output ports, and can state cross the child
   boundary at any other place?
2. Does a parent own those ports, does the child own them, or does a separate
   interface assembly own the connection?
3. Which child observations are visible while it is in progress: outputs only,
   pending Activities, lifecycle state, failure, cancellation, or all marking?
4. What executable abstract child may parent tests use before concrete child
   internals exist?
5. What trace, invariant, enabledness, completion, liveness, and resource
   evidence must agree between abstract and concrete children?
6. How does exact operation/occurrence identity survive substitution and later
   expansion?
7. Can the chosen rule apply recursively to a child containing two children
   plus local transitions without changing production assembly?

The ruling must include at least one case where contraction is sound and one
where a single-transition contraction is rejected. It must use public Petrus
construction/runtime doors or record a focused Petrus dependency instead of
accessing private internals.

## Development order after the ruling

The architecture permits both directions when the conformance contract makes
them honest:

- **child-first:** implement and accept a production subnet locally, then mount
  it in its parent and vertical tracer; or
- **parent-first:** implement the parent against an accepted executable child
  contract, then replace that abstraction with the conforming production child
  without changing parent behavior.

The order is chosen per tracer. Neither direction licenses a shadow workflow
model. A parent-first abstraction tests the boundary contract; the concrete
child's local runner tests its internals; composition proves that the real child
satisfies the same parent-visible traces and invariants.

## Dashboard anchor

The dashboard provides the first accepted concrete boundary evidence:

```text
typed DashboardEvent
  -> DashboardProjection
  -> immutable DashboardPublication Activity
  -> exact DashboardPublicationOutcome
  -> updated projection or retained explicit failure
```

Its production assembly is independently stepped, inspected, crashed,
reconstructed, replayed, and checked. The same assembly mounts into the workflow
and root tracer. Closure first makes the desired document absorbingly closed,
then reconciles any exact in-flight publication, lands one final closed
publication, and only then permits lifecycle generation close. Terminal
inability remains explicit retained failure until its later policy is ruled.

This anchor proves the local-production-subnet method. It does not decide the
general nested substitution contract by analogy.

## Composition and cutover evidence

After subnet-local acceptance, workflow-owner composition proves mail, lifecycle,
gate, occurrence, completion, and resource relationships among exact subnets.
Root composition replaces the CV21 bridge factory and reuses unchanged outer
simulation modules and checks. Full journey correspondence compares user-visible
outcomes and exact outer operations, not private V5 markings.

Final cutover additionally requires:

- complete bridge-family replacement and zero old imports;
- deletion of the bridge, current workflow and current outer implementation;
- no compatibility reader, dual writer, topology selector, or state migration;
- fresh-state and bounded rollback-custody instructions;
- canonical package/test rename and gate/config/deployment promotion; and
- explicit Navigator approval immediately before shared service or state action.

## Delivery pull gate

CV22 manifests the workflow concerns already evident in the current system so
their replacement can be reviewed one subnet at a time. Numbering those stories
does not settle their implementation order or permit work to start. Before any
subnet story is pulled, the hierarchy ruling must define:

- the exact production construction API;
- local runner and generated-view contract;
- abstract child fixture, if admitted;
- conformance checker and counterexample expectations;
- parent/root mounting and identity rules; and
- first tracer order beginning with the accepted dashboard anchor or a smaller
  prerequisite proven necessary by that design.

If a story's design reveals independently meaningful child subnets, CV22
manifests those children before pulling the parent. This keeps the initial
inventory lightweight without recreating CV20's whole-workflow review burden
inside one story.
