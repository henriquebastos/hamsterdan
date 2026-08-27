---
code: CV20.DS3
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS2 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds2-admit-fold-pr-observation.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS3 — Expose one workflow-declared Activity

## Outcome

Deepen the admitted PR path until the real workflow declares its first external
request: a dashboard publication `DashReq`. Readiness records the exact Petrus
Activity occurrence and exposes bounded waiting posture while Dispatch holds
the request. No provider adapter executes it in this tracer.

## Vertical path

```text
real retained PR observation
  -> host one-subject step
  -> readiness bounded workflow advancement
  -> real lifecycle/dashboard folds
  -> workflow MANIFEST-declared DashReq
  -> Petrus ActivityRequested plus Dispatch occurrence
  -> detached waiting posture and host inspection
```

After acceptance, the production system can explain exactly what external work
the workflow wants, with stable identity and durable occurrence, while doing no
external mutation.

## Component Technical Stories

1. Complete the workflow value/fact/Activity manifest substrate needed by the
   lifecycle and dashboard loops.
2. Add manifest-driven gate wiring and explicit token/topology validation.
3. Qualify public Petrus/Motus request and one-occurrence reconstruction seams.
4. Extend readiness runtime to advance once and surface a pending Activity in
   detached posture without executing it.
5. Extend owner-local/root simulation and checkers with durable History/Dispatch
   request evidence.

## Initial owned paths

```text
src/hamsterdan2/workflow/{values,facts,activities}.py
src/hamsterdan2/workflow/net/{folding,gating,topology,dashboard}.py
src/hamsterdan2/readiness/{application,runtime,ports}.py
implemented workflow/readiness/host simulations and tests
Petrus/Motus public request/reconstruction seam and dependency pin, if needed
```

## Fixed design

- `workflow` alone decides that a dashboard publication is needed and creates
  `DashReq`; readiness and simulation cannot construct an equal substitute.
- `MANIFEST` declares gate, request type, closed terminal variants, execution
  lane, operation derivation and blocked mapping exactly once.
- The request carries stable business operation identity; correlation and
  idempotency equal it. Engine assigns the occurrence.
- Readiness retains and exposes occurrence, activity, operation, correlation,
  idempotency and exact decoded work from History/Dispatch evidence.
- One advancement may record one `ActivityRequested`; it cannot execute an
  effect inline.
- Pending work produces a bounded waiting posture and remains pending across
  fresh reconstruction.
- Wrong gate, duplicate manifest/token, malformed work or identity collision
  fails before an Activity is considered executable.

## API-strengthening checkpoint

Review the real observation→Activity call tree and settle:

- final `DashReq` fields and stable operation grammar;
- `MANIFEST` entry, token registry, `build_net`, `seed_marking` and `wire_gates`
  signatures needed by the implemented loops;
- public Petrus request/replay/one-occurrence structures and errors;
- readiness advancement and pending-Activity/posture projections;
- History/Dispatch identities, correlation diagnostics and request-byte limits;
- local/cross checker evidence and resource gauges; and
- any compact workflow names that should be strengthened before first use.

Record all ruled values/signatures in [the API contract](api-contracts.md).
Workflow ownership, manifest completeness, exact identity and no-inline-effect
behavior are fixed.

## Tracer acceptance

Given the accepted DS2 observation, when bounded host/readiness advancement
runs, then the production workflow emits exactly one manifest-declared
`DashReq`; History and Dispatch retain the same occurrence, work, operation,
correlation and idempotency; and inspection reports bounded waiting.

Acceptance also proves request-time crash/reconstruction, wrong
occurrence/operation/variant refusal before completion, a work-substitution
cross-checker counterexample, exact replay, lowered pending/History/byte limits,
and direct correspondence through the real Petrus Net/Engine/History/Dispatch
path. No provider call is permitted in the canonical artifact.

## Done condition

The real DS2 input reaches one durable production workflow request through the
actual composed path. Pure workflow tests or a simulation-created request are
necessary but insufficient.

## Stop conditions

Stop if the request requires copied folds, simulation-only workflow semantics,
private Petrus inspection, a readiness-authored `DashReq`, inline provider
execution, or unbounded advancement past unrelated eligible actions.

## Rollback

Remove dashboard Activity behavior and its runtime/simulation growth. DS2 still
admits and folds one observation without requesting external work.

## Validation

Run workflow vocabulary/topology/manifest tests, real Engine request paths,
request reconstruction, identity/variant failures, no-provider-call assertions,
local/cross sensitivity, replay, resource bounds and project gates.

## Expansion boundary

Expand pure workflow, runtime seam and evidence work as Technical Stories, but
keep the DS open until the admitted observation produces the real durable
Activity and bounded host-visible wait.
