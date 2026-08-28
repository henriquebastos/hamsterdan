---
code: CV21.DS5
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV21.DS4 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv21-ds4-settle-github-activity.md
  - contract-inheritance.md
  - ../../decisions/records/2026-08-28T2037Z-cv21-activities-run-in-separately-supervised-motus-workers.md
---

# CV21.DS5 — Settle one reconstructible agent round

## Outcome

Execute one real retained-workflow review or conversation request through the
new credential-free agent protocol and a separate agent Motus Worker role. Host
composition binds the exact route and process-local Agenticus/Pi runtime; Motus
owns Attempt execution and operational reporting. The round remains recoverable
across submission, Attempt terminal, cancellation, receiver delivery, and
Impetus workflow-terminal cuts.

## Vertical path

```text
retained agent work -> bridge typed work -> readiness authority/request custody
  -> Motus Dispatch -> separate agent Worker claim/lease
  -> host route -> credential-free Agenticus/Pi workspace -> agent lifecycle terminal
  -> exact receiver delivery -> Dispatch operational terminal
  -> later Engine collection -> Impetus canonical terminal
  -> bridge strict terminal -> original occurrence
```

## Owns

- agent request/result/terminal protocol, Pi adaptation, and workspace safety;
- host agent-Worker composition, operation-to-route binding, process-local
  runtime/secret lifetime, cancellation, and erasure evidence;
- Motus Attempt claim/lease/execution/reporting and Agenticus/Pi runtime
  correspondence without GitHub credentials;
- readiness request and exact receiver-delivery custody, first complete
  protected-work authority claim, findings fence, and canonical terminal
  admission through its Engine; and
- review/conversation bridge families and deterministic correspondence.

## Excludes

No mutation publication, GitHub credentials in the agent process or territory,
authority-owned Worker pump, complete later lifecycle matrix, new
review/conversation workflow fold, or inferred result from logs.

## Acceptance

- submission, execution terminal, and receiver delivery are distinct durable
  identities and cuts;
- one shared agent Worker role can serve multiple Instance-scoped requests
  without one Worker process or thread per PR;
- phase/incarnation/head/base/policy agree across durable grant, fresh provider
  truth, and fresh host evidence at the first protected call;
- cancellation and stale authority fail closed without fabricating a workflow
  terminal;
- retained exact results are delivered after reconstruction before new work;
  and
- secrets never enter commands, artifacts, state, diagnostics, or agent input.
