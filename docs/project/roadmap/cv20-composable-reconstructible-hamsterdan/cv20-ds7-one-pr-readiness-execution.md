---
code: CV20.DS7
level: Delivery Story
status: Planned
status_reason: Waits for CV20.DS2–DS6 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds2-bounded-petrus-motus-execution-seams.md
  - cv20-ds3-pure-readiness-workflow.md
  - cv20-ds4-hamsterdan-simulation-runtime.md
  - cv20-ds5-strict-github-provider-operations.md
  - cv20-ds6-reconstructible-agent-execution.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS7 — Deliver one-PR readiness execution

## Outcome

Implement readiness ports, authority, ingress/review/timer/instance custody,
effect adapters, bounded Petrus runtime, and one-PR application. Preserve every
readiness/runtime cut listed in the local API contract, enforce terminal
correlation before History, and pass the exact delivered coding result into
publication through injected capabilities.

## CV20 contract

This story implements the one-PR owner and all workflow-effect adaptation in
[the architecture](architecture.md). Its capability protocols, detached
`StepResult`, custody cuts, authority claim and terminal-admission rules are in
[the API contract](api-contracts.md). DS2–DS6 are complete inputs; this story
does not reopen their semantics.

## Owned paths

```text
src/hamsterdan2/readiness/application.py
src/hamsterdan2/readiness/authority.py
src/hamsterdan2/readiness/ports.py
src/hamsterdan2/readiness/runtime.py
src/hamsterdan2/readiness/custody/**
src/hamsterdan2/readiness/effects/**
tests2/behavioral/readiness/**
tests2/integration/test_workflow_runtime.py
tests2/integration/test_readiness_execution.py
```

`readiness/simulation` remains a placeholder until DS9. Concrete GitHub/agent
construction and multi-PR scheduling remain host work in DS8.

## Fixed design

- One lifecycle owns exactly one repository/PR subject and fresh persistence
  roots. It neither multiplexes subjects nor discovers them by scanning files.
- Readiness core depends on typed capability protocols; effect adapters may
  import one provider family each. Only host constructs concrete providers.
- Every public call performs bounded work and returns one detached
  `StepResult`. Convenience drains are test/CLI helpers with explicit caps.
- Readiness owns ingress, review attempt, timer and instance custody; Petrus
  History/Dispatch remain the workflow request/terminal authority.
- Terminal admission verifies Activity, occurrence, correlation, idempotency,
  terminal variant and terminal operation before appending to History.
- Protected effects require the complete durable-grant + fresh-provider +
  fresh-host authority claim at the specified cuts.
- Route/custody revocation becomes a workflow-declared blocked terminal;
  readiness—not host—performs that semantic mapping.
- Every mutating GitHub capability is lookup-first and makes at most one
  provider attempt per step.
- Agent execution is addressed by stable operation/attempt. The exact accepted
  delivered `CodingResult` passes through the injected coding port to
  publication; readiness does not manufacture another result.
- Publication consumes that result observably before `Pushed` returns to the
  original workflow Activity occurrence.
- Fresh databases/filesystem roots are replacement-only and never inspect or
  migrate V5 state.

## Position and predecessors

Requires CV20.DS2–DS6. It is the first story that composes the replacement
workflow with provider and agent capabilities, but it remains non-selectable.

## Implementation sequence

1. Rule readiness capability, construction, result, custody and error APIs
   below.
2. Compose the real Net/seed/manifest through the qualified DS2 runtime and add
   strict terminal admission.
3. Implement instance and ingress custody, including exact duplicate recovery.
4. Implement review/agent attempt custody and the exact delivered-result path.
5. Implement timer command/acknowledgement/maturity/History/delivery custody.
6. Implement authority and one-family effect adapters, including lookup-first
   response-loss recovery.
7. Implement the one-PR application with one named cut per call and detached
   lifecycle evidence.
8. Prove every crash cut against fresh SQLite/filesystem reopen and no duplicate
   provider/agent acceptance.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- public one-PR constructor/factory and injected capability/store arguments;
- capability protocols for clock, GitHub reads/effects, coding, lifecycle
  authority and delivery acknowledgement;
- fields for the fixed `StepResult` variants and the boundary between waiting,
  quiescence, terminal and unavailable;
- ingress/review/timer/instance custody record schemas and stable identities;
- terminal-admission request/error API;
- authority claim/evidence fields and stale/revoked classifications;
- readiness error hierarchy and mapping to workflow terminal families; and
- close/reconstruct/inspect signatures and finite defaults.

Names and signatures may be strengthened coherently. One-PR ownership,
capability injection, complete authority, exact terminal correlation,
lookup-first one-attempt effects and the exact delivered-result causal edge are
fixed.

## Done condition

One lifecycle owns one PR and returns one bounded step; every durable cut
reconstructs from owned state; authority combines current readiness, provider,
and host evidence; route revocation produces typed workflow-declared outcomes;
and ambiguous Git/agent effects recover lookup-first without duplication.

## Rollback

Remove replacement readiness and its fresh roots. Current host composition
still points only to the current runtime.

## Validation

Run custody/effect behavior tests, real Petrus integration, fresh
SQLite/filesystem reopen, all CV20 readiness/runtime crash cuts,
authority/revocation fences, one-attempt provider checks,
terminal-correlation refusal, and lookup-first Git/agent recovery.

## Expansion boundary

Expand by readiness capability and crash/recovery boundary. Do not implement
the whole application as one Technical Story. Every accepted API decision is
written into CV20 before DS8/DS9 consume it.
