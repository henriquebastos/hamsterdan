---
status: Candidate
captured: 2026-08-24
navigator: Henrique
source: ../exploration/es9-human-codebase-ownership/history-loss-finding.md
---

# RS-020 — Fail closed on missing canonical History

## Existing field to refine

Hamsterdan reconstructs runtime state from an intact canonical Petrus History
after process loss. It does not reconstruct a deleted `history.jsonl` from
runnable hints, ingress manifests, Dispatch rows, timers, agent routes, or
provider-operation records.

A binding-only PR root currently represents two indistinguishable states:

1. a valid crash cut after `binding.json` is written but before a new Engine
   writes its first History record; or
2. an established PR whose canonical History was later deleted.

`ensure_instance_binding` accepts both shapes. `V5Runtime.open` creates a fresh
Engine whenever `history.jsonl` is absent, while startup and periodic sweeps
discover persisted PRs by enumerating History files. The damaged established PR
may therefore remain dormant or open as a fresh workflow depending on which
later trigger reaches it.

The evidence and safety consequence are recorded in
`../exploration/es9-human-codebase-ownership/history-loss-finding.md`.

## Candidate boundary

Make missing established canonical History one consistently detected,
fail-closed operator state while preserving the valid first-initialization crash
cut.

The refinement must:

- distinguish a never-started binding-only root from an established workflow
  whose canonical History is missing;
- refuse to create a fresh Engine for the damaged established workflow;
- prevent startup, periodic reconciliation, pending custody, retained runnable
  wakes, or direct active-route lookup from bypassing the fence;
- preserve safe restart when a crash occurs after binding creation but before the
  first canonical History record;
- keep GitHub and agent effects disabled for the fenced PR;
- expose a bounded sanitized operator diagnosis and recovery posture; and
- add focused destructive-file-loss tests without using live provider state.

The refinement must not:

- reconstruct Petri marking or Activity lineage from noncanonical projections;
- treat runnable, ingress, Dispatch, timer, agent-route, or provider-operation
  stores as replacement workflow truth;
- delete, rewrite, or silently reseed surviving state;
- launch authenticated provider operations during qualification;
- weaken the V5-only topology identity or retired-state fail-closed contract; or
- enter active work merely because this candidate is recorded.

## Change Request

### CR-001 — Detect and fence an established PR whose History is absent

Status: Parked

Requested change:

Introduce one durable, crash-safe distinction which proves that canonical History
has previously been established for a bound PR. Use it to make every host opening
and discovery route reject the established-but-missing-History shape before
`Engine.create` or any external effect.

The implementation route is deliberately unselected. A future confirmation and
plan must resolve:

- which host-owned durable record carries the establishment fact;
- the write ordering between binding creation, first History creation, and that
  record;
- behavior for a torn or corrupt History file rather than a fully absent file;
- discovery of binding roots which startup currently misses when it globs only
  `history.jsonl`;
- interaction with pending webhook custody, runnable hints, Dispatch terminals,
  timers, and agent-route rows; and
- the operator action required after the PR is fenced.

Likely production areas:

- `src/hamsterdan/host/binding.py`
- `src/hamsterdan/host/v5/runtime.py`
- `src/hamsterdan/host/service.py`
- host persistence and startup tests

Validation seeds:

- a new PR may resume after the valid binding-before-first-History crash cut;
- an established PR with deleted `history.jsonl` fails closed on startup;
- the same damage fails closed when reached by pending custody, runnable wake,
  periodic reconciliation, or direct application lookup;
- surviving projections do not cause an external effect;
- an intact established History still reconstructs normally;
- focused tests, `scripts/check quick`, and `scripts/check full` pass before any
  Experience Report.

## Pull state

This candidate is captured but not pulled. Its Change Request is parked. No
repair design, implementation, production migration, operator action, commit, or
release scope is authorized by this record.

A future Navigator may pull this Refinement Story, request a design experiment
first, promote it to Delivery if it becomes a broader operational contract, or
reject the candidate.
