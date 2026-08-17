---
code: CV18.DS2
level: Delivery Story
status: Planned
status_reason: The real host composition does not yet run against one replayable logical GitHub/agent/provider event-and-fault world
updated: 2026-08-17
related:
  - index.md
  - cv18-ds1-readiness-correctness-model-and-simulation-contract.md
  - https://github.com/henriquebastos/petrus
---

# CV18.DS2 — Deterministic host and provider fault world

## Intent

Run the real supported Hamsterdan host composition under deterministic logical
time and event order while external systems remain explicit, bounded models of
truth and failure rather than ad hoc mocks.

## Scope

- Consume the accepted Petrus CV19 event, logical-time, Activity, fault,
  crash/reload, and replay contracts through an approved test surface.
- Drive real Hamsterdan composition doors with normalized events for:
  - PR open/head/base/policy, draft/resume/close, and reconciliation;
  - Actions workflow/run/job attempts and delayed or reordered observations;
  - review requests, approvals, changes requested, requested reviewers, thread
    resolution, findings, and conversation;
  - timer acknowledgement/maturity and runnable scheduling;
  - agent review, coding, inability, classified failure, and retained terminal;
  - publication, rerun, dashboard, readiness, comment, and Git mutation effects;
  - webhook duplicate/redelivery, missed-observation repair, host crash, and
    restart.
- Model provider outcomes at the effect boundary: rejected before acceptance,
  accepted and visible, accepted but response/terminal lost, delayed visibility,
  stale read, retryable unavailability/rate limit, non-retryable refusal, and
  operation-identity collision.
- Keep provider truth independent of Hamsterdan's desired state. Stable markers,
  operation IDs, refs, comments, reruns, and agent-operation ledgers record what
  the modeled provider accepted; lookup-first recovery queries that truth.
- Crash by discarding all host/process objects and reopening through production
  custody, History, timer, runnable, operation, and reconciliation paths. The
  scenario cannot retain hidden volatile state.
- Make every external call fail on an undeclared operation; silent permissive
  mocks are prohibited.
- Serialize and replay the expanded schedule without using the PRNG.

## Acceptance / Done condition

1. One vertical scenario crosses signed delivery custody → readiness work →
   external effect accepted → terminal/acknowledgement crash → full host rebuild
   → lookup-first settlement without duplicate effect.
2. Replaying an expanded scenario produces the same normalized provider truth,
   accepted Histories/custody, oracle observations, and terminal disposition at
   the same commits.
3. The host is genuinely reconstructed; no runtime, provider client, mutable
   fake-world alias, timer object, or Engine survives a simulated process crash.
4. Accepted-but-response-lost differs from definite rejection and drives the
   production recovery path rather than an invented exactly-once shortcut.
5. Every scenario is bounded by events, logical time, provider calls, retained
   state, pending work, and wall-clock test budget, and reports the ending bound.
6. No credential, private payload, real provider authority, wall sleep, or
   private Petrus runtime import is needed.
7. Existing focused host, V5, CV17 parity, and full gates remain green.

## Driver QA and evidence plan

- Begin with publication ambiguity/restart because it crosses current authority,
  provider truth, stable identity, Petrus terminal freezing, host custody, and
  lookup-first recovery in one slice.
- Add timer and lifecycle races only after replay and true reconstruction pass.
- Perturb logging/observation and verify replay does not depend on extra random
  draws or dictionary aliasing.
- Run focused host/provider/recovery suites and `scripts/check full`.

## Out of scope

- Stateful random workload generation and shrinking; DS3 owns it.
- Real GitHub API, Git object, model-provider, or network fidelity claims.
- Reimplementing readiness, authority, retry, settlement, or Petrus logic in
  the fault world.
- Reopening or replacing completed CV17, or selecting the default topology.
