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
---

# CV21.DS11 — Supervise multiple PRs fairly

## Outcome

Run the complete new host process over several independent bridged PR roots and
configured-repository discovery. Durable sequence and bounded selection leases
ensure known-subject and discovery turns both progress while failures remain
isolated to their owning subject.

## Vertical path

```text
service/API/operator -> catalog + runnable/discovery custody -> bounded fair turn
  -> one readiness lifecycle call -> detached posture -> tail requeue/settle
  -> bounded inspection and shutdown
```

## Owns

- host catalog, durable runnable sequence/leases, fair turn selection, service,
  startup/shutdown, API, CLI, and detached inspection;
- process-wide provider/agent resource lifetime and failure aggregation;
- root multi-owner deterministic scheduling and cross-subject isolation
  checkers; and
- portfolio resource and correspondence evidence.

## Excludes

No workflow decoding by host, global drain, unbounded startup reconciliation,
new workflow family, selectable runtime, or deployment.

## Acceptance

- one call advances at most one subject/discovery cut and returns;
- a repeatedly failing due PR cannot starve another due PR or discovery forever;
- expired leases recover under durable sequence and exact ownership;
- one subject's malformed state/effect does not corrupt another root;
- startup and shutdown preserve custody without fabricated completion; and
- bounded inspection reports only detached owner-approved values.
