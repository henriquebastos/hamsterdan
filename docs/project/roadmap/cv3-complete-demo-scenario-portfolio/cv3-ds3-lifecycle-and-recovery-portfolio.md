---
code: CV3.DS3
level: Delivery Story
status: Completed
status_reason: Accepted live on human-created PR39-44 with lifecycle, redelivery, restart, timeout, malformed-result, and provider-ambiguity recovery proven
updated: 2026-08-03
---

# CV3.DS3 — Lifecycle and recovery portfolio

Prove head supersession, PR closure, host restart, duplicate delivery, agent
timeout/malformed result, provider failure before call, and ambiguous provider
outcome after call. Fault injection remains host-owned and operation-identified;
recovery must fence current authority and look up provider state before retry.

## Delivered local slice

The host now accepts a persisted terminal Activity failure only after reloading
canonical History and proving that its entire prior prefix is unchanged and its
new suffix is the exact `ActivityFailed`/`FiringFailed` pair for an Activity
that was unresolved before the failed advance. It atomically replaces both
Engine custodians and continues draining sibling work. Divergent, rewritten,
or unproven History propagates the failure without changing runtime custody.

Immutable comment publication remains lookup-first and current-authority
fenced immediately before every possible write. It recovers an ambiguous call
through exact marker-and-body lookup, retries once only when no definitive
provider response exists, and fails closed on marker collision or definitive
rejection. Agent process startup failure is normalized without leaking provider
or operating-system detail; existing timeout and malformed-result contracts
remain explicit terminal Activity outcomes.

A disabled-by-default, one-shot host qualification seam can target one exact
repository, PR, boundary, phase, kind, and operation. It can exercise agent
timeout/malformed outcomes and immutable-comment pre-call/post-call ambiguity
without adding state to the Net or exposing a runtime API. The read-only
`inspect-instance` command emits bounded identifiers and Activity counts from a
stable, regular-file snapshot without replaying or editing History.

Local verification passed 237 Python tests with one opt-in provider test
skipped, all nine relay tests, lint, formatting, typing, sdist, and wheel builds.
At that checkpoint, fresh live lifecycle and fault portfolios,
deployment/restart evidence, and the bounded PR20 debt observation remained
before acceptance.

## Initial qualification blocker, resolved

Commit `c67e7773da26d3596541b943bb6bed3d6abb9d0e` was deployed through the
existing supervised host with frozen dependencies. Registration validation,
supervised restart, and health passed for App `4452953`, installation
`150464548`, and the one admitted repository. Credentials and runtime state
remained in host custody.

The first live portfolio attempt was not accepted. The orb's nominal human
credential could read the fixture but every Git push, GraphQL PR creation, and
Git-object write was denied. PR34-38 were therefore created through App
installation authority, which is not an admitted substitute for trusted-human
fixture setup. PR34-37
were closed unmerged and excluded. PR38 autonomously recovered from initial
review and scenario failure, published one App-owned repair, advanced from head
`5389b6e4f91218b57885a1f709b2350f34bb882a` to
`7590e0576be089a427ba50d56ab194bc74f433c7`, and reached terminal readiness with
29 completed Activities and no failure or unresolved Activity. This is useful
host behavior evidence but does not prove human head supersession, controlled
redelivery, or the isolated qualification-fault portfolio.

PR20's deployed read-only projection contained 756 records, 33 requested, 32
completed, one ActivityFailed/FiringFailed pair, and no unresolved Activity;
its inbox entries were terminal. This does not retroactively prove how its
historical churn was repaired and did not close the debt at that checkpoint.
Acceptance was blocked on a proven trusted-human fixture write route and fresh
isolated lifecycle, agent-failure, and provider-ambiguity runs. Intermittent
real agent protocol unavailability was a second confidence limit and was not
treated as an operation-scoped injected outcome.

The blocker was credential locality, not repository authority: the two human
OAuth sessions remained in the archived CV3.DS2 orb while runtime qualification
ran elsewhere with Amp's injected read-only credential. The source orb was
restored, both sessions were transferred without exposing their values, and Amp
project secrets now provision explicit ignored operator identity roots in every
fresh project orb. Human commands select the real `/usr/bin/gh` and a scrubbed
environment, keeping `henriquebastos`, `hsbastos`, and `hamster-dan[bot]`
distinct.

## Accepted live evidence

Human-created PR39 proved ready admission at head
`7a265ff5bd418c75632f6388d230271292192942`, human head advance to
`9cec33e051f210ecfad6f352cd248c5b833418fc`, exact old-head supersession, and
App-owned recovery to terminal head
`e0e87ad954cdde0815afce302a922e7729f31378`. Exact opened delivery UUID
`4c6ee5f0-8ebf-11f1-8949-888f052547ec` was redelivered through GitHub's App
delivery API and received duplicate custody without a new inbox row, History
append, or visible effect. A supervised restart preserved the terminal
projection. Human closure then converged with no late effect.

Four isolated operation-scoped faults were accepted:

- PR40 injected `agent/timed_out/review`; the exact review returned `unable`,
  the workflow continued, repaired, and converged with no unresolved Activity.
- PR44 injected `agent/malformed/review`; the exact review returned `unable`,
  later review/repair cleared, and all 31 Activities completed. PR41 was closed
  and excluded because its target passed before the fault was armed.
- PR42 injected immutable-comment `before_call`; the first attempt made no
  provider mutation, the one fenced retry published exactly one finding, and
  no duplicate appeared.
- PR43 injected immutable-comment `after_call`; GitHub accepted the call,
  withheld proof triggered exact marker/body lookup, and recovery returned the
  one existing effect without a second mutation.

PR39-44 were closed unmerged by `henriquebastos`. Final History projections
contained 167 requested and completed Activities, zero failed,
`FiringFailed`, or unresolved Activities. The inbox drained to 1,220 terminal,
zero pending, and zero failed deliveries; the fault variable was absent and the
host remained healthy. Accepted PR14/15 and PR23-33 were untouched. PR20's
bounded projection was identical before and after deployment and restart: 756
records, one explicit terminal Activity failure pair, and no unresolved
Activity or renewed churn.
