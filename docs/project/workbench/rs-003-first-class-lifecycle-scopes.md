---
status: Active
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
| CR-001 Petrus canonical scope records, replay, and race semantics | Planned |
| CR-002 Petrus occurrence provenance and Engine close/reset | Planned |
| CR-003 Petrus commit-first Dispatch cancellation and quarantine | Planned |
| CR-004 Petrus scoped delivery and closed-scope ingress disposition | Planned |
| CR-005 Pin accepted Petrus and integrate Hamsterdan scope lifecycle | Planned |
| CR-006 Remove only behaviorally replaced retirement topology | Planned |
| CR-007 Add explicit authorized recovery for terminal blockers | Planned |
| CR-008 Cross-project review, validation, coherence, and closure | Planned |

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
