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
  - ../../decisions/records/2026-08-28T2037Z-cv21-activities-run-in-separately-supervised-motus-workers.md
---

# CV21.DS4 — Settle one GitHub Activity lookup-first

## Outcome

Execute the DS3 typed dashboard publication in the first separately supervised
Motus Worker process. A same-host Local Dispatch carries the exact task from the
one-PR Engine to a host-composed GitHub Activity. One bounded Worker turn claims
exact work, performs at most one provider mutation attempt, and reports the
operational outcome. A later authority turn collects it, lets Impetus record
the canonical terminal, and returns the strict terminal through the bridge to
the original current-Net occurrence.

## Vertical path

```text
typed pending publication -> Motus Local Dispatch
  -> separate GitHub Worker claim/lease -> GitHub lookup/execute
  -> provider outcome custody -> Dispatch operational terminal
  -> later Engine collection -> Impetus canonical terminal
  -> bridge terminal conversion -> original current-Net occurrence
```

## Owns

- bounded provider auth/transport/gateway and exact PR read;
- provider publication lookup, marker/content identity, rate/response metadata,
  and one-attempt effect mechanism;
- host GitHub-Worker composition, Activity registry/queue binding, separate
  process lifetime, and Local Worker/Dispatch correspondence;
- readiness typed publication/terminal adaptation with Motus-owned
  claim/lease/execute/report and Impetus-owned canonical terminal cuts; and
- provider/bridge correspondence and physical resource metrics.

## Excludes

No additional Activity family, workflow publication decision, dashboard state,
complete authority matrix, remote Worker provider requirement, authority-owned
Worker pump, or hidden drain.

## Acceptance

- known absence permits at most one mutation attempt in one step;
- ambiguous response performs complete bounded lookup before another attempt;
- real process evidence proves that the authority role does not construct or
  drive the Worker and can restart independently of one live or completed
  Attempt;
- durable Dispatch claim, provider observation/attempt, provider outcome,
  operational terminal, Engine collection, and Impetus canonical terminal are
  independently crashable and reconstructible;
- refusal and uncertainty remain distinct strict outcomes; and
- exact replay and mutation-sensitive checks detect duplicate or mismatched
  publication.
