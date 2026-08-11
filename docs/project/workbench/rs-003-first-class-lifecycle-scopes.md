---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-003 — Introduce first-class lifecycle scopes

## Existing field being refined

Hamsterdan now delegates operational publication execution to Motus, but its
readiness Net still carries repeated retirement transitions for queued work,
Activity results, and observations that belong to a superseded, dormant, or
terminal PR generation. The independent Lane 3 experiment proved that a
canonical lifecycle scope can remove much of that framework pressure, but it
did not integrate with production Engine, History, Dispatch, or ingress.

## Accepted direction

Implement production lifecycle scopes from fresh accepted Petrus and
Hamsterdan `main` branches. Experimental branches are evidence only and are not
merged or rebased into production.

A scope has durable identity `(name, generation)`. History append order, not
timestamps, resolves close/completion races. Closing a generation discards its
consumed firing inputs and exact queued occurrences; restoration is not
implicit. Domain compensation remains explicit workflow behavior.

Scope close/reset commits canonical History before Dispatch cancellation is
requested. Cancellation prevents future accepted execution where fencing is
still possible, but never promises that an ambiguous external effect did not
happen. Exact late completions are durably acknowledged or quarantined and
cannot alter a closed generation.

Ingress proven to target a closed generation is canonically acknowledged and
dropped. Ingress whose generation cannot be proved is quarantined rather than
silently dropped or reinterpreted as current. Terminal publication blockers may
be superseded only by a new authority basis/generation or an explicit authorized
recovery command; automatic cooldown does not mint new logical executions.

The host remains the multi-Instance scheduler. This story does not introduce
high availability, PostgreSQL as a prerequisite, a framework scheduler, actor
modules, durable capability containers, or exactly-once side-effect claims.

## Autonomous decision policy

- At 90% or greater confidence, the Driver selects the smallest
  provider-neutral design consistent with the accepted contracts, records the
  decision, implements it, and validates it.
- Below 90%, the Driver stops only at the exact unresolved semantic decision and
  presents evidence, alternatives, and a recommendation.
- Petrus production changes land and validate first. Hamsterdan then pins the
  exact accepted Petrus revision and integrates it. Both projects push directly
  to `main`; no pull request is created.

## Change Requests

| Change Request | Outcome |
| --- | --- |
| CR-001 Petrus canonical scope records, replay, and race semantics | Completed in Petrus `b0bb336a077b70b6d702aef26acbf8ad1381f9b3` |
| CR-002 Petrus occurrence provenance and Engine close/reset | Completed in the accepted Petrus revision |
| CR-003 Petrus commit-first Dispatch cancellation and quarantine | Completed in the accepted Petrus revision |
| CR-004 Petrus scoped delivery and closed-scope ingress disposition | Completed in the accepted Petrus revision |
| CR-005 Pin accepted Petrus and integrate Hamsterdan scope lifecycle | Completed |
| CR-006 Remove only behaviorally replaced retirement topology | Completed |
| CR-007 Add explicit authorized recovery for terminal blockers | Completed |
| CR-008 Cross-project review, validation, coherence, and closure | Completed |

## Validation contract

- Duplicate-valued queued tokens are cleaned by durable occurrence identity,
  never value equality.
- Close/reset replay reconstructs active generation, exact queue, Activity
  phase, cancellation instructions, and quarantine.
- Completion-before-close and close-before-completion are deterministic by
  append order even at equal instants.
- Close/reset append failure emits no Dispatch cancellation instruction.
- Restart repairs cancellation work only after canonical close/reset exists.
- Pending, claimed, and running Activity disposition is explicit and fenced.
- Exact duplicate late terminal redelivery is acknowledged; conflicting
  redelivery fails loudly.
- Closed-generation ingress is durably acknowledged/dropped; uncertain ingress
  is quarantined.
- Hamsterdan preserves same-generation operation ownership, current authority,
  business retry budgets, provider lookup-first recovery, and never-merge
  behavior.
- The final Net reduction is measured against current production 40 places,
  138 transitions, and 412 arcs; the old Lane 3 count is not an acceptance
  target.
- Focused, full, release, restart, and adversarial checks pass in Petrus before
  Hamsterdan changes its pin.

## Out of scope

- Distributed Instance scheduling or PostgreSQL migration.
- Hard cancellation or exactly-once external effects.
- Generic actor/module runtime or durable service locator.
- Implicit restoration of consumed inputs.
- Automatic retry of terminally blocked logical operations.
- Merging the disposable Lane 3 implementation.

## Current Hamsterdan preparation

The current 40-place, 138-transition, 412-arc Net contains 91 retirement
transitions. Fresh classification against production `main` identifies:

| Retirement responsibility | Count | Scope disposition |
| --- | ---: | --- |
| Dormant/terminal transient absorption | 56 | Replace after exact scoped queue/result proof |
| Stale-generation queued work, basis, and timer | 15 | Replace after scoped occurrence proof |
| Stale external ingress | 1 | Replace only after scoped ingress provenance proof |
| Same-generation operation ownership | 8 | Retain |
| Invalid/completed basis routing | 4 | Retain |
| Admission and lifecycle ingress | 7 | Retain or route through explicit ingress disposition |

The conservative current candidate is therefore 71 retirement transitions,
rising to 72 only if closed/uncertain ingress semantics are proven in production.
This is a hypothesis to validate, not a target to force. Same-generation
operation retirement remains mandatory because lifecycle generation is not
business operation identity.

Explicit recovery will authorize a new Engine occurrence while retaining the
same provider-side operation/idempotency identity. Petrus Local Dispatch keys
custody by `(instance, occurrence)`, so a new occurrence may intentionally reuse
that identity; the Activity then performs lookup-first reconciliation. The
remaining Hamsterdan design must preserve or reconstruct the original desired
payload—especially conversation reply text—without treating History scanning as
hidden Net state or restoring automatic retries.

## Delivered result

Hamsterdan pins Petrus
`b0bb336a077b70b6d702aef26acbf8ad1381f9b3` and uses one exact lifecycle scope
named `readiness-generation`. PR-lifetime lifecycle commands remain unscoped;
generation-owned ingress, queued occurrences, firings, and Activity requests
carry the exact `LifecycleScope(name, generation)` returned by Petrus.

The production Net changed as follows:

| Metric | Before RS-003 | After RS-003 |
| --- | ---: | ---: |
| Places | 40 | 43 |
| Transitions | 138 | 67 |
| Arcs | 412 | 266 |
| Retirement transitions | 91 | 17 |

The three additional places and remaining transitions are not lifecycle cleanup
recreated under new names. They make generation start/stop commits and explicit
publication recovery visible workflow facts. The 17 retained retirements decide
same-generation operation ownership, stale or invalid basis, invalid admission,
and invalid recovery—business questions that a lifecycle scope cannot answer.

### Crash-safe lifecycle boundary

Scope reset/close and Net state cannot be one cross-component transaction.
Hamsterdan therefore uses a durable staged boundary protocol rather than
assuming an in-memory call sequence is atomic:

```text
start
  stage unscoped GenerationStart(generation=N)
  -> reset/open exact scope N
  -> deliver scoped GenerationCommit(N, "start")
  -> Net admits generation N

stop
  stage unscoped GenerationStop(generation=N)
  -> close exact scope N
  -> deliver unscoped GenerationCommit(N, "stop")
  -> Net makes the PR dormant or terminal
```

The matching commit is required by the Net, so a staged command cannot mutate
business state before Petrus has established the lifecycle boundary. On every
reconciliation, the host repairs an incomplete boundary before processing new
provider state. Repair also opens a missing initial scope after a crash between
Engine creation and `open_scope`, and permits a seed-only Instance to stop if
the PR becomes draft or terminal before admission. Repetition is harmless
because the exact generation and boundary are durable.

### Cancellation and late outcomes

Host Activity indexes treat occurrences named by `ScopeClosed.cancelled` and
`ScopeReset.cancelled` as terminal, alongside completed, failed, and quarantined
occurrences. A cancelled publication therefore cannot remain an artificial
publisher fence after its generation is closed. Exact late terminal delivery is
still governed by Petrus: it is acknowledged or quarantined and cannot mutate
the closed generation.

### Publication exhaustion and recovery

Retryable operational failures stay inside one Motus logical execution.
Terminal capability failures latch an explicit blocker and retain the immutable
request needed for recovery. A trusted agent intent
`recover_publication(target, operation)` may authorize exactly one fresh
Activity occurrence only when its authority, target, exact blocked operation,
and retained request all match current state. The fresh occurrence deliberately
reuses the stable provider-effect operation so lookup-first reconciliation can
discover an ambiguous prior effect. Invalid, stale, mismatched, and unauthorized
recovery is consumed without effect; no timer or transition can self-authorize
another logical execution.

Unknown terminal publication failures project a typed nonrecoverable fault
rather than remaining projection-pending or masquerading as a recoverable
capability problem. This keeps scope close/replay deterministic while preventing
readiness until a new basis supersedes the fault. A same-head basis refresh
clears stale operation identities, recovery payloads, blockers, and faults.

## Verification and limitations

The final implementation was exercised through 524 Python tests (one explicit
external-provider route skipped), including restart at every lifecycle seam,
wrong-generation commits, old queued and in-flight cancellation, late-terminal
quarantine, cancellation-aware host indexes, explicit one-shot recovery, and
terminal failure projection. Static, format, type, JavaScript, source, and wheel
gates and nine relay tests passed. An adversarial review returned `APPROVE` after the fresh-Instance
create/open gap and seed-only termination gap were repaired.

Scopes do not provide hard interruption, exactly-once side effects,
same-generation business supersession, or a distributed scheduler. Provider
effects remain operation-identified, freshly fenced, and lookup-first. The host
still owns one advancing owner per Instance and reconstructible runnable hints.
