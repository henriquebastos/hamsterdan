---
code: CV21.DS3
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV21.DS2 and the required public Petrus selected-occurrence seam; no work is pulled
updated: 2026-08-28
related:
  - index.md
  - cv21-ds2-admit-pr-observation-through-bridge.md
  - workflow-bridge.md
  - ../../decisions/records/2026-08-28T2037Z-cv21-activities-run-in-separately-supervised-motus-workers.md
  - ../cv22-decomposable-readiness-workflow/index.md
---

# CV21.DS3 — Expose one retained-workflow Activity

## Outcome

Drive accepted DS2 input through the current Net until its real dashboard loop
declares one durable request. The bridge projects it as exact typed new Activity
work, Impetus History proves the request/occurrence, and Motus Dispatch durably
retains the pending task. Readiness reports a visible detached wait. A scripted
operational terminal can return through Engine collection only to that original
occurrence. No Worker or provider implementation runs.

## Vertical path

```text
accepted new observation -> bridge -> current dashboard behavior
  -> retained request/History occurrence -> bridge typed Activity projection
  -> Motus Dispatch publication -> detached ActivityWait
  -> scripted Dispatch terminal -> Engine collection -> Impetus canonical terminal
  -> bridge strict terminal conversion -> original occurrence
```

## Owns

- first closed workflow Activity work/terminal boundary used by new outer code;
- pending request/occurrence projection, durable Dispatch publication, complete
  identity comparison, and strict terminal-admission failure surface;
- bridge translation for the retained dashboard request/outcomes; and
- bridge-local and root crash/replay/correspondence evidence.

## Excludes

No Motus Worker construction or execution, provider Activity implementation,
new dashboard event, projection, fold, subnet, closure policy, provider
publication, or copy of retained workflow tests. CV22 owns the accepted new
dashboard subnet.

## Acceptance

- Impetus History proves the canonical request/occurrence and Motus Dispatch
  proves durable pending operational custody;
- host receives only opaque detached waiting posture;
- request, occurrence, work, operation, correlation, idempotency, and terminal
  operation all match before terminal recording;
- terminal-return evidence enters as a scripted Dispatch operational outcome,
  then only the one-PR Engine lets Impetus record the canonical terminal;
- unknown/mismatched variants fail before mutation;
- reconstruction repairs or resumes only one selected occurrence through a
  public bounded Petrus seam; and
- mapping and occurrence-check mutations fail independent checkers.
