---
code: CV21.DS11
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV21.DS10 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv21-ds10-discover-unregistered-open-prs-boundedly.md
  - architecture.md
  - ../../decisions/records/2026-08-28T2037Z-cv21-activities-run-in-separately-supervised-motus-workers.md
---

# CV21.DS11 — Supervise multiple PRs fairly

## Outcome

Run the complete new Hamsterdan authority role over several independent bridged
PR roots and configured-repository discovery. Durable sequence and bounded
selection leases ensure known-subject and discovery turns both progress while
failures remain isolated to their owning subject. This fairness is independent
of Motus queue, Attempt, and Worker concurrency.

## Vertical path

```text
service/API/operator -> catalog + runnable/discovery custody -> bounded fair turn
  -> one readiness lifecycle call -> detached posture -> tail requeue/settle
  -> bounded inspection and authority-role shutdown

independent Motus terminal -> runnable wake -> later bounded PR turn
```

## Owns

- host catalog, durable runnable sequence/leases, fair turn selection, service,
  authority-role startup/shutdown, API, CLI, and detached inspection;
- role-specific composition and failure isolation without Worker fleet
  supervision or per-PR Worker ownership;
- root multi-owner deterministic scheduling and cross-subject isolation
  checkers; and
- portfolio resource and correspondence evidence.

## Excludes

No workflow decoding by host, Worker launch/restart/scale control, Motus queue
or Attempt fairness policy, global drain, unbounded startup reconciliation, new
workflow family, selectable runtime, or deployment.

## Acceptance

- one call advances at most one subject/discovery cut and returns;
- a repeatedly failing due PR cannot starve another due PR or discovery forever;
- shared Worker roles can serve many Instances without one Worker process or
  thread per PR, while the authority role retains one advancing owner per
  selected Instance;
- expired leases recover under durable sequence and exact ownership;
- one subject's malformed state/effect does not corrupt another root;
- startup and shutdown preserve custody without fabricated completion; and
- bounded inspection reports only detached owner-approved values.
