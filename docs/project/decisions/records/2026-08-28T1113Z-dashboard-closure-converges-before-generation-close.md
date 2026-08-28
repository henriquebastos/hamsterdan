---
status: Decided
raised: 2026-08-28
decided: 2026-08-28
recorded: 2026-08-28T1113Z
deciders:
  - Henrique (Navigator)
related:
  - CV20
  - CV20.DS3
  - CV20.DS4
  - CV20.DS9
  - 2026-08-11T0000Z-lifecycle-scopes-close-generations-before-canceling-effects.md
---

# Dashboard closure converges before lifecycle generation close

## Decision

CV20 distinguishes a durable provider-closure observation from the later
commit that closes the workflow lifecycle generation. The lifecycle fold maps
the observation into the same typed dashboard-event family used by other
dashboard-relevant workflow facts. That event carries the evidence-owned close
instant and makes the desired dashboard document absorbingly closed; a pure
fold never reads the wall clock to invent it.

Dashboard publication remains single-flight. If closure is observed while one
exact publication is unresolved, the closed desired document supersedes every
newer desired document that has not yet become an Activity. The already-issued
publication is reconciled under its original immutable work and operation
identity. Only after that exact operation settles may workflow declare one new
immutable publication carrying the final closed document. One operation never
identifies different publication bytes.

On the successful path, the lifecycle generation commits close only after the
final closed publication lands. Once that commit exists, later facts cannot
reopen the dashboard and no new dashboard effect may be claimed. A terminal
inability to land the final publication remains explicit retained failure; DS9
must rule its bounded operator-recovery or explicit close policy rather than
treating failure as alignment.

This ordering does not change the accepted rule that generation close commits
canonical History before cancellation. It inserts final dashboard convergence
before that close command. Ambiguous accepted work is still reconciled
lookup-first and is never canceled as though it could not have happened.

## Consequences

- The provider-closure observation remains provider/workflow evidence, while
  the dashboard consumes an internal `DashboardEvent`; provider values do not
  enter dashboard state.
- The dashboard needs one durable desired/landed/pending projection and one
  publication/outcome boundary. Closure does not require a parallel publication
  lane or permission to overtake unresolved work.
- A dedicated dashboard-closing token or healing race is not presumed. Any
  additional color must prove a durable ownership, waiting, recovery, or
  enabledness distinction that the event, projection, Activity and terminal do
  not already express.
- An older dashboard rendering may be visible briefly before the final closed
  rendering. This is accepted; final convergence is required, intermediate
  display precision is not.
- DS3 owns the isolated workflow vocabulary and close-during-publication
  scenario, DS4 proves lookup-first provider settlement, and DS9 composes real
  closure observation through final convergence and lifecycle close.
- Current V5 close behavior remains runtime evidence, not CV20 authority.
