---
code: CV21.DS4
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV21.DS3 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv21-ds3-expose-retained-workflow-activity.md
  - architecture.md
  - workflow-bridge.md
---

# CV21.DS4 — Settle one GitHub Activity lookup-first

## Outcome

Execute the DS3 typed dashboard publication through new readiness and GitHub
owners. One bounded step claims exact work, performs at most one provider
mutation attempt, records the exact outcome separately, and returns the strict
terminal through the bridge to the original current-Net occurrence.

## Vertical path

```text
typed pending publication -> readiness claim -> GitHub lookup/execute
  -> provider outcome custody -> readiness terminal admission
  -> bridge terminal conversion -> original current-Net occurrence
```

## Owns

- bounded provider auth/transport/gateway and exact PR read;
- provider publication lookup, marker/content identity, rate/response metadata,
  and one-attempt effect mechanism;
- readiness publication adapter and split claim/execute/terminal cuts; and
- provider/bridge correspondence and physical resource metrics.

## Excludes

No additional Activity family, workflow publication decision, dashboard state,
complete authority matrix, or hidden drain.

## Acceptance

- known absence permits at most one mutation attempt in one step;
- ambiguous response performs complete bounded lookup before another attempt;
- durable claim, provider observation/attempt, outcome custody, and History
  terminal are independently crashable and reconstructible;
- refusal and uncertainty remain distinct strict outcomes; and
- exact replay and mutation-sensitive checks detect duplicate or mismatched
  publication.
