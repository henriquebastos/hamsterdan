---
code: CV3
level: Value
status: In Progress
status_reason: CV2.DS2 proved guarded coding; deterministic scenario portfolio execution is active
updated: 2026-08-01
---

# CV3 — Complete demo scenario portfolio

## Intent

Make Hamsterdan fully operational on `HBNetwork/demo-pr-readiness` across every
archetypical PR state the product claims to coordinate. Each scenario is
reproducible, isolated on a fresh PR, inspectable, and accepted from durable
provider and History evidence rather than inferred from unit tests.

## Scope and sequence

1. [CV3.DS1 — Deterministic scenario laboratory](cv3-ds1-deterministic-scenario-laboratory.md)
   owns clean, flake, persistent-failure, review-finding, and repair fixtures.
2. [CV3.DS2 — Authority and collaboration gates](cv3-ds2-authority-and-collaboration-gates.md)
   owns stale base, conflicts, reviews, threads, and draft transitions.
3. [CV3.DS3 — Lifecycle and recovery portfolio](cv3-ds3-lifecycle-and-recovery-portfolio.md)
   owns supersession, closure, restart, redelivery, and agent/provider failures.

## Done condition

Given any admitted archetypical scenario in the portfolio
When its exact scripted provider transitions occur
Then Hamsterdan reaches the expected durable control state and visible App
effects
And every stale, duplicate, uncertain, or failed operation resolves under the
same authority, credential, fencing, and recovery contracts used in production.

## Boundaries

- Scenario JSON controls deterministic CI behavior only; it does not fake real
  GitHub lifecycle, review, base, conflict, or thread state.
- Agents inspect and edit credential-free checkouts only.
- The host owns every GitHub effect.
- PRs remain isolated and unmerged unless a base-advance fixture explicitly
  requires one separately approved human merge.
