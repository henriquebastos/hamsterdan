---
code: CV20.DS7
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS6 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds6-publish-causal-mutation.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS7 — Recover CI and repair escalation

## Outcome

Deepen the causal lifecycle with exact-head CI evidence and bounded escalation.
A check-suite delivery is normalized, admitted and folded; a first failure may
declare one lookup-first rerun; persistent regression escalates through the
existing agent and mutation seams; clean recovery updates the same workflow
incarnation and visible readiness posture.

## Vertical paths

```text
check delivery -> CheckSeen -> real CI fold -> clean posture

first failure -> real escalation fold -> RerunReq
  -> lookup-first provider rerun -> RerunLanded -> same CI workflow

persistent failure -> workflow repair request
  -> established agent coding lifecycle -> established Git publication
  -> Pushed -> new exact-head CI evidence -> recovered or bounded escalation
```

This tracer introduces the CI/rerun causal chain. It reuses agent and Git
effect families rather than creating alternate repair paths.

## Component Technical Stories

1. Add provider-owned bounded check-suite/run evidence normalization.
2. Implement exact-head CI and escalation workflow loops/facts.
3. Implement `RerunReq` lookup-first provider/readiness effect adaptation.
4. Connect persistent regression to existing review/coding/mutation operations.
5. Extend local/root simulation, generated schedules, checkers and provider
   correspondence for clean/flake/regression outcomes.

## Initial owned paths

```text
src/hamsterdan2/workflow/net/{ci,escalation}.py
src/hamsterdan2/readiness/effects/rerun.py
src/hamsterdan2/readiness/application.py
src/hamsterdan2/github_app/{models,gateway,effects}.py
implemented owner-local/root simulation and tests
```

## Fixed design

- CI evidence is bound to exact head/run identity and finite check rows/pages.
  Stale evidence cannot authorize or settle current-head work.
- Workflow alone classifies clean, first-attempt flake, persistent regression,
  repair escalation and inability. Readiness/provider report typed evidence.
- Rerun is stable, lookup-first and at most one provider mutation attempt per
  step. Ambiguous acceptance is reconciled later.
- Persistent regression reuses stable agent/Git identities from DS5/DS6; it
  does not invoke a direct repair shortcut.
- Every repair head returns through `Pushed`; subsequent CI evidence is for that
  exact provisional/current head.
- Escalation counters and retry eligibility are durable workflow meaning, not
  host wake counts or simulation state.
- Each branch has a finite terminal/posture and observable physical attempt
  counts; no loop drains until green.

## API-strengthening checkpoint

Review clean, flake and persistent-regression call trees together and settle:

- provider check-suite/run/evidence models and pagination result API;
- workflow CI state/facts, rerun/repair request fields and operation grammars;
- readiness evidence projection and rerun lookup/effect/result signatures;
- exact-head/stale-run/ambiguous/rate-limit/failure classifications;
- escalation counters, terminal/posture vocabulary and finite retry policy;
- named ingress, Activity, response-loss, repair and new-head cuts; and
- check-row/page/body, rerun, agent, Git, workflow and artifact limits/metrics.

Write the ruled contracts into [the API contract](api-contracts.md). Exact-head
authority, workflow-owned classification, lookup-first rerun and reuse of the
established repair chain are fixed.

## Tracer acceptance

Acceptance covers three deterministic schedules: clean green without mutation;
first-attempt flake with exactly one accepted rerun and clean fold; and
persistent regression with bounded escalation through one causally aligned
repair, exact new-head evidence and a declared final posture.

For each schedule, crash at delivery, fold, Activity claim/effect/terminal,
agent delivery, Git acceptance and new-head evidence; rebuild from durable
owners; assert physical counts, local/cross checker ownership, exact replay and
lowered finite bounds. Substitute stale head or rerun operation in composition
and require exactly the responsible cross violation. Provider check/rerun
transport correspondence is required; live mutation retains separate approval.

## Done condition

All three full vertical schedules pass. Isolated CI folds, rerun clients or
repair tests do not close the DS without the end-to-end escalation and recovery
postures.

## Stop conditions

Stop if host/simulation classifies CI, stale evidence affects current head, a
rerun retries in one step, persistent failure bypasses the established causal
mutation chain, or any schedule requires unbounded convergence.

## Rollback

Remove CI/escalation/rerun growth and its fresh retained state. DS6 mutation
remains independently accepted; current production is unchanged.

## Validation

Run exact-head/stale evidence, clean/flake/regression behavior, rerun ambiguity,
repair causal checks, all named crash cuts, physical counts, local/cross
sensitivities, generated finite schedules/shrinking, exact replay, bounds,
provider correspondence, secret scans and project gates.

## Expansion boundary

CI vocabulary, rerun effect and escalation schedules may be separate Technical
or User Stories. Preserve one reviewable trace per outcome and keep the DS open
until each enters at provider input and ends in workflow-owned posture.
