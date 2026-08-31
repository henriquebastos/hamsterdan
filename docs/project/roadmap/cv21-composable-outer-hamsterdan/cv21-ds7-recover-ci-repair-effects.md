---
code: CV21.DS7
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV21.DS6 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv21-ds6-publish-causal-mutation.md
  - workflow-bridge.md
  - ../../decisions/records/2026-08-28T2037Z-cv21-activities-run-in-separately-supervised-motus-workers.md
---

# CV21.DS7 — Recover CI and repair effects

## Outcome

Admit exact-head CI evidence through the common new observation seam and route
the rerun or repair work selected by the current Net to the already separated
GitHub or agent Motus Worker role. Provider rerun ambiguity and agent repair
recovery remain bounded and lookup-first while the retained workflow continues
owning escalation policy.

## Vertical path

```text
exact-head checks -> common admission -> bridge -> current escalation decision
  -> typed rerun/repair work -> Motus Dispatch
  -> GitHub Worker rerun or agent Worker repair/recovery
  -> Dispatch operational terminal -> later Engine collection
  -> Impetus canonical terminal -> strict bridge terminal
  -> original current-Net occurrence
```

## Owns

- exact-head check acquisition/normalization and CI observation mapping;
- provider rerun operation, lookup, ambiguity classification, and custody;
- reuse of accepted GitHub/agent Worker roles and agent/mutation capabilities
  for exact rerun or repair work; and
- CI/rerun/repair bridge families, schedules, resources, and correspondence.

## Excludes

No new CI or escalation fold, retry count, repair-selection policy, broad test
matrix, or unrelated provider effect.

## Acceptance

- stale-head or incomparable CI evidence cannot authorize work;
- each rerun operation has stable identity and at most one attempt between
  complete bounded lookups;
- retained workflow chooses rerun versus repair and receives the exact terminal;
- crashes at admission, Dispatch claim, provider/agent outcome, operational
  terminal, Engine collection, and canonical terminal cuts recover without
  duplicate mutation; and
- deterministic schedules distinguish transient failure, persistent failure,
  stale evidence, refusal, and ambiguity.
