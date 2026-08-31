# DS7 concept extraction

## Source

- Delivery Story: [`../cv20-ds7-recover-ci-repair-escalation.md`](../cv20-ds7-recover-ci-repair-escalation.md)
- Cross-boundary contracts: [`../api-contracts.md`](../api-contracts.md),
  "Value groups", "Activity manifest", "Lookup-first provider effect" and "DS
  API-strengthening register"
- Cumulative sequence: [`../delivery-sequence.md`](../delivery-sequence.md),
  "DS7 — CI and repair escalation"

Reviewed source revision: 2026-08-28 working tree.

## Extracted behavior

DS7 admits finite provider check evidence bound to an exact head and run.
Workflow—not host, provider or simulation—classifies clean recovery, first
failure, persistent regression, repair escalation and inability. A first
failure may request one lookup-first rerun; persistent regression reuses the
existing agent and causal mutation chain. Durable escalation/retry meaning and
finite final postures replace any drain-until-green loop.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| Outcome, lines 18–24 | Exact-head check evidence drives bounded rerun or established repair, ending in the same incarnation/posture | CI evidence, CI recovery, repair escalation |
| Vertical paths, lines 26–37 | Clean, flake and persistent-failure paths share one CI workflow and reuse established mutation | CI fold, rerun, persistent regression, repair |
| Fixed design, lines 61–76 | Evidence is exact-head/run and bounded; workflow owns classification/counters; rerun is lookup-first; every branch is finite | exact-head CI evidence, workflow escalation, rerun effect, escalation state |
| Acceptance, lines 94–106 | Three deterministic schedules prove clean, one-rerun flake and bounded causal repair | outcome variants are scenarios under common concepts |
| API contracts / Value groups, lines 236–250 | CI/run evidence is a fixed normalized observation family owned by workflow admission language | CI evidence as an enduring observation family |
| API contracts / Activity manifest, lines 274–280 | Rerun and mutation have closed workflow request/terminal families | request/terminal names are API variants |
| API contracts / Lookup-first provider effect, lines 613–644 | Rerun inherits complete lookup, collision, fence and at-most-one mutation order | rerun effect is a specialization of lookup-first effect |
| API contracts / DS API-strengthening register, lines 987–996 | DS7 owns exact-head CI, rerun/repair operations, limits and schedule reporting | concrete state/operation vocabulary remains DS review |
| Delivery sequence / DS7, lines 208–214 | DS7 hands off bounded CI recovery without a second repair path or convergence drain | CI recovery and repair escalation survive later qualification |

## Later ownership and refinements

- DS8 adds time/deferred work over established provider and agent seams; DS7's
  immediate CI/repair behavior remains intact (DS8 Fixed design, lines 80–81;
  Rollback, lines 126–127).
- DS9 applies the complete AuthorityClaim and operation-specific matrix to rerun
  and mutation and gives stale work workflow-declared outcomes (DS9 Fixed design,
  lines 79–93).
- DS12 qualifies first-attempt flake, persistent regression/bounded repair and
  agent repair among the named journeys, plus accepted-hidden provider/Git
  recovery overlays (DS12 named journeys, lines 71–83).
- DS13 removes V5/Hamsterdan2 labels while the canonical workflow still owns CI
  and escalation responsibilities (replacement ledger / Target module deletion
  test, lines 41–45; Removed names, lines 438–457).

## Subordinate vocabulary to evaluate

- clean, first-attempt flake, persistent regression, repair and inability are
  classified outcomes/paths, not automatically standalone concepts.
- `CheckSeen`, `RerunReq`, `RerunLanded` and `Pushed` are observation/request/
  terminal API names.
- escalation counters, retry eligibility and exact run identity are internal
  vocabulary of workflow escalation and CI evidence.
- exact-head, stale-run, ambiguous, rate-limit and failure labels are
  classifications within evidence/effect handling.
- named ingress, Activity, response-loss, repair and new-head cuts are recovery
  mechanics; generated schedules and physical counts are test evidence.

## Unresolved DS-review items

- provider check-suite/run/evidence models and pagination API;
- workflow CI facts/state and rerun/repair operation grammars;
- readiness evidence projection and rerun effect APIs;
- exact-head, stale, ambiguous, rate-limit and failure classifications;
- escalation counters, finite retry policy and terminal/posture vocabulary;
- named recovery cuts and schedule reports; and
- calibrated check, rerun, agent, Git, workflow and artifact limits.

## Construction-only exclusions

- The three deterministic schedules, shrinking, checker substitutions and
  provider correspondence are qualification mechanics rather than concepts.
- Temporary replacement paths and current-production rollback language end at
  DS13.

## Trace handoff

The DS8–DS13 trace is complete in the
[candidate register](candidate-register.md). Whether rerun and repair are
subordinate escalation strategies remains for later Navigator review.
