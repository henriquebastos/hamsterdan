---
code: CV20.DS11
level: Delivery Story
status: Planned
status_reason: Waits for CV20.DS8 and CV20.DS10 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds8-trusted-host-custody-fair-supervision.md
  - cv20-ds10-readiness-journey-portfolio.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS11 — Prove real provider and process correspondence

## Outcome

Qualify replacement seams against real GitHub transport/Git, authenticated Pi
where approved, filesystem/SQLite durability, OS process death, lease expiry,
and bounded concurrent multi-PR host execution. This is correspondence evidence,
not another model.

## CV20 contract

This story qualifies the real seams already fixed in
[the architecture](architecture.md) and [the API contract](api-contracts.md).
The DS10 portfolio names the claims; correspondence maps each claim to direct
SDK, Git, Pi, filesystem, SQLite, process or host evidence and records any
remaining limit. It does not add fallback behavior.

## Owned paths

```text
tests2/acceptance/test_correspondence.py
tests2/integration/test_github_provider.py      added real-seam scenarios
tests2/integration/test_agent_execution.py     added real-seam scenarios
tests2/integration/test_host_lifecycle.py      added real-seam scenarios
```

Bounded fixtures, subprocess helpers and evidence codecs stay with these tests
unless an already-owned DS8 qualification seam is the natural owner. Production
behavior is changed only through the owning earlier DS contract, never hidden in
the correspondence harness.

## Fixed design

- Every required simulation claim has an explicit correspondence row naming
  claim, real seam, fixture, expected observation, bound and known limit.
- GitHub correspondence uses the real SDK/HTTP transport against mock transport
  by default; a live provider mutation requires separate explicit approval and
  a uniquely bounded fixture.
- Git correspondence exercises real object/ref operations, compare-and-swap,
  operation markers and lookup of accepted-but-hidden outcomes.
- Pi correspondence exercises the authenticated protocol only when separately
  approved; otherwise the required provider-neutral codec/runtime seam remains
  testable and the missing live claim is reported, not silently skipped green.
- Durability uses fresh SQLite connections/filesystem handles and real process
  death at named CV20 readiness cuts. In-process exception/reconstruction is
  insufficient.
- Host correspondence runs multiple PR lifecycles concurrently under bounded
  leases and proves durable fairness, generation fencing and failure isolation.
- Secret scans include process arguments, environment projections, artifacts,
  logs, stores, workspaces and agent values without printing secret material.
- Physical provider/runtime attempt counts are asserted in addition to terminal
  singularity.
- Evidence is reproducible, machine-readable and bound to revision, dependency
  versions, scenario, fixture identity, limits and result.
- The replacement remains disabled and non-selectable. Correspondence never
  reads, migrates or mutates V5 state.

## Position and predecessors

Requires CV20.DS8 and DS10. The replacement service remains disabled; external
mutations require separate explicit authorization and bounded fixtures.

## Implementation sequence

1. Rule the correspondence matrix/evidence and fixture APIs below.
2. Map every DS10 claim to required mock/real correspondence and an explicit
   limit; fail if a required row has no evidence.
3. Implement real GitHub transport and local Git object/ref/CAS correspondence.
4. Implement real Pi protocol/workspace/cleanup correspondence within the
   separately approved credential boundary.
5. Implement SQLite/filesystem/process-kill recovery at every required cut.
6. Implement bounded concurrent multi-PR host, lease-expiry and shutdown/startup
   correspondence.
7. Run effect cardinality, retained-resource and secret scans; emit the
   revision-bound qualification report used by DS12.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- correspondence row, claim identifier and pass/fail/unavailable vocabulary;
- fixture identity, ownership, provisioning and guaranteed cleanup contract;
- external-approval token/evidence boundary without embedding credentials;
- subprocess launch/kill/reopen protocol and named cut synchronization;
- physical attempt/cardinality observation and provider-marker extraction;
- evidence document schema, revision/dependency binding and artifact storage;
  and
- how an unapproved or unavailable real seam blocks qualification without
  making ordinary local CI unusable.

Harness names may change. Direct real-seam evidence, explicit limits, separate
external approval, fresh-process recovery, physical cardinality and secret
custody are fixed.

## Done condition

Each simulation claim has a direct real-seam counterpart where required;
process and transaction interruption recover from fresh processes; concurrent
PRs preserve fairness; accepted effects are not duplicated; cleanup and secret
scans pass; and correspondence limits remain explicit.

## Rollback

Remove correspondence harnesses and temporary replacement state. Never enable
the target service or translate its state into current V5.

## Validation

Run mock and approved real-provider tests, real Git object/ref CAS and lookup,
Pi request/result/cleanup, process kills at every required CV20 readiness cut,
SQLite interruption, lease recovery, concurrent-PR fairness, effect
cardinality, secret scans, and retained resource bounds.

## Expansion boundary

Expand by real seam and risk. Every external mutation, credential use, process
operation, and cleanup receives its own approval and evidence route. Record the
accepted correspondence/evidence API in CV20 before DS12 consumes it.
