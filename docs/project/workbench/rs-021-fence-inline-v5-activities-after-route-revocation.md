---
status: Candidate
captured: 2026-08-24
navigator: Henrique
source: ../exploration/es9-human-codebase-ownership/candidate-review.md
---

# RS-021 — Fence inline V5 Activities after route revocation

## Existing field to refine

`HostService` may open a strictly bound V5 PR with an inactive installation or
repository route so it can settle canonical History after restart. Durable
`reply_gate`, `dash_gate`, and `announce_gate` Activities execute through
`HostService._guard_durable_activity`, which checks the current registry route.

The five identified inline Activities execute through `InlineDispatch` and do
not pass through that host guard:

- `review_agent`;
- `publish_gate`;
- `rerun_gate`;
- `git_gate`; and
- `reminder_gate`.

Their host adapters correctly reconcile stable operation identity before reading
current authority. If lookup proves absence, their claim readers compare the
host grant and fresh provider truth but do not check whether the registry still
admits the installation and repository.

Concrete failure shape: an unresolved `git_gate` survives a restart, the route is
revoked, startup opens the intact V5 History, and lookup proves that the old
operation did not land. Current code can continue toward agent execution and Git
publication without a current route check.

## Evidence

- `src/hamsterdan/host/service.py`: `_application`, `sweep`,
  `_activate_instance`, and `_guard_durable_activity`;
- `src/hamsterdan/host/v5/runtime.py`: `_CompositeDispatch` and
  `V5Runtime.open`;
- `src/hamsterdan/readiness/net_v5/gating.py`:
  `DURABLE_PUBLICATION_GATES` and `_IDENTIFIED_INLINE_GATES`;
- `src/hamsterdan/host/v5/application.py`: Activity composition and
  `current_claim`;
- `src/hamsterdan/host/v5/mutation.py`: `V5MutationGate.git_gate`; and
- `tests/integration/host/test_service.py`:
  `test_v5_revoked_route_settles_instance_queue_as_typed_blocked_without_provider_calls`,
  which covers only the durable publication gates.

ES-009 observed an unresolved inline `git_gate` reach read-only publisher
reconciliation after route suspension. The absent-lookup branch to later agent
and provider work follows directly from the gate code. No provider mutation was
executed during exploration.

## Candidate boundary

Preserve lookup-first recovery for every stable operation. After lookup proves
absence, require current registry admission before any new:

- agent review or coding call;
- findings, reply, dashboard, reminder, or readiness publication;
- Actions rerun request;
- Git object write; or
- ref compare-and-swap.

Keep registry custody in `host`. Do not give `readiness`, `github_app`, `agents`,
or neutral contracts concrete registry knowledge.

The refinement must cover all inline Activities rather than patching only
`git_gate`. It must not prevent a revoked route from settling an already-landed
operation into canonical History without issuing a duplicate effect.

## Correctness obligations for the future plan

- **Authoritative state and authority.** Canonical History owns unresolved
  Activity occurrences. The host registry owns current installation and
  repository admission. The host grant and fresh provider truth continue to own
  PR, lifecycle, head, base, and policy authority.
- **Safety.** A revoked route may perform read-only lookup for a retained stable
  operation. Lookup absence must lead to no new agent or provider effect.
  Lookup presence may settle the original operation but must not create another
  effect.
- **Fair-environment liveness.** An intact retained operation can settle after
  route restoration or can settle as already landed while the route remains
  inactive. The plan must state the typed disposition for proven absence under
  revocation and how later restoration reopens work, if it does.
- **Bounds.** Retain current bounded lookup, retry, Activity, payload, and History
  behavior. Do not introduce polling or an unbounded startup loop.
- **Nondeterminism.** Route revocation or restoration may race startup,
  reconciliation lookup, provider visibility, Activity redispatch, and terminal
  projection.
- **Crash and ambiguity cuts.** Test before lookup, after lookup proves existing,
  after lookup proves absent, before an agent call, before an external effect,
  after provider acceptance, and before the Activity terminal enters History.
- **Independent evidence.** Assert provider and agent call ledgers directly in
  addition to History terminals. History alone cannot prove that no external
  effect occurred.

## Change Request

### CR-001 — Apply current route admission to every inline V5 effect

Status: Parked

A future plan must select one host-owned seam that all inline adapters can use
after lookup-first reconciliation. It must define typed outcomes for inactive
routes without changing operation identity or moving workflow policy into the
host.

Likely files:

- `src/hamsterdan/host/service.py`
- `src/hamsterdan/host/v5/application.py`
- host V5 gate composition or claim ports
- `tests/integration/host/test_service.py`
- focused gate and restart tests

Validation seeds:

- for each inline Activity, a persisted unresolved occurrence under a revoked
  route performs no new effect when lookup proves absence;
- an existing provider marker or Git commit settles without a duplicate effect;
- route restoration follows one explicit recovery posture;
- durable publication revocation tests remain green;
- semantic journeys and generated Git recovery still converge;
- `scripts/check quick` and `scripts/check full` pass before acceptance.

## Pull state

This candidate is captured but not pulled. No runtime change, route policy,
provider operation, migration, launch prerequisite, commit, or release action is
authorized by this record. ES-009 remains a learning session.
