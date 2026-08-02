---
code: CV3.DS3
level: Delivery Story
status: In Progress
status_reason: Recovery boundaries and reproducible qualification controls are qualified locally; fresh live portfolio remains
updated: 2026-08-02
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
Fresh live lifecycle and fault portfolios, deployment/restart evidence, and the
bounded PR20 debt observation remain before acceptance.
