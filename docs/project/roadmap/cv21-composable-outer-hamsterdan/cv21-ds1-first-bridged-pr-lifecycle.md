---
code: CV21.DS1
level: Delivery Story
status: Completed
status_reason: the first PR workflow opens through shared application and History storage, the sole bridge, and a process-loss recovery check under the isolated gate
updated: 2026-09-01
related:
  - index.md
  - architecture.md
  - workflow-bridge.md
  - delivery-sequence.md
---

# CV21.DS1 — Establish the first bridged PR lifecycle

## Outcome

Deliver the smallest real pulse of the new outer system. A strict command opens
one immutable PR Identity, host composition creates or loads its workflow in
shared History, the sole bridge mounts and seeds the current Net, and the host
receives a detached `awaiting_observation` stage. The operation reconstructs
after process loss and is idempotent for the same action and PR Identity.

## Vertical path

```text
open_pull_request command -> host pr_workflows transaction
  -> readiness runtime -> shared History -> sole bridge -> current Net/seed
  -> detached PullRequestWorkflow at pr_workflow_opened
```

## Owns

- isolated `src/hamsterdan2`/`tests2` quality and architecture gate;
- strict PR Identity, action identity, workflow identity, generation, stage,
  and checkpoint values;
- readiness runtime and sole-bridge construction of the retained Net; and
- bounded shared application, History, and Dispatch storage at the first real
  production seams.

## Excludes

No provider observation, Motus Worker construction, Activity execution,
workflow replacement code, current outer application reuse, runtime selector,
current state access, or deployment.

## Delivered contract

Installation `44`, repository `31`, and pull request `7` map to PR Identity
`(44, 31, 7)` and workflow identity `github:44:31:pr:7`. The one application
row records generation 1, stage `awaiting_observation`, checkpoint
`pr_workflow_opened`, and bridge `workflow-bridge/head-seen-intake@4`.

The host holds `BEGIN IMMEDIATE` on shared `hamsterdan.sqlite3` while readiness
creates or loads that workflow's partition in shared `history.sqlite3`. If
History commits and the process dies before the `pr_workflows` row commits, the
application transaction rolls back. A fresh exact command loads the existing
History and writes the one application row without reseeding History. Dispatch
uses shared `dispatch.sqlite3` and has no Worker in this story.

The glossary-aligned DS2 replacement removed DS1's former catalog, per-PR root
path, host-record checkpoint, and simulation-specific values. No migration or
compatibility reader retains that implementation shape; the completed user
outcome remains one reconstructible bridged PR workflow.

## Acceptance and evidence

- only `readiness/workflow_bridge.py` imports the exact legacy allowlist;
- the bridge mounts the production current Net and seed without old outer code;
- host receives strict replacement values, never markings, old types, or
  Petrus runtime objects;
- application storage has exactly `pr_workflows` and `webhook_inbox`, while all
  workflow identities share bounded History and Dispatch files;
- actual child `SIGKILL` after History open but before PR-workflow registration
  leaves 21 History records and zero application rows; fresh composition
  converges on 21 History records and one row; and
- the isolated `scripts/check hamsterdan2` gate covers the source/import
  boundary and this recovery path.
