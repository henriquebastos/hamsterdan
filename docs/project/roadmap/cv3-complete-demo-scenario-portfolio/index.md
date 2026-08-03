---
code: CV3
level: Value
status: Completed
status_reason: All deterministic, authority, collaboration, lifecycle, restart, redelivery, agent-failure, and provider-ambiguity scenarios are accepted live
updated: 2026-08-03
---

# CV3 — Complete demo scenario portfolio

## Intent

Make Hamsterdan fully operational on `HBNetwork/demo-pr-readiness` across every
archetypical PR state the product claims to coordinate. Each scenario is
reproducible, isolated on a fresh PR, inspectable, and accepted from durable
provider and History evidence rather than inferred from unit tests.

## Scope and sequence

1. [CV3.DS1 — Deterministic scenario laboratory](cv3-ds1-deterministic-scenario-laboratory.md)
   completed clean, flake, persistent-failure, review-finding, conversational,
   and repair qualification.
2. [CV3.DS2 — Authority and collaboration gates](cv3-ds2-authority-and-collaboration-gates.md)
   completed stale base, true conflict, reviews, threads, and draft transitions
   through real provider authority on isolated PR29-33.
3. [CV3.DS3 — Lifecycle and recovery portfolio](cv3-ds3-lifecycle-and-recovery-portfolio.md)
   completed supersession, closure, restart, redelivery, and operation-scoped
   agent/provider failure recovery on human-created PR39-44.

## Accepted value evidence

CV3's three Delivery Stories are accepted from fresh provider and durable
History evidence. PR23-28 proved the deterministic scenario laboratory;
PR29-33 proved real GitHub authority and collaboration gates; PR39-44 proved
lifecycle and recovery boundaries. Every accepted Instance ended with no
unresolved Activity, provider effects retained exact current-authority fencing
and lookup-first recovery, and human, App, and credential-free agent identities
remained separate. The final lifecycle inbox contained 1,220 terminal entries,
zero pending, and zero failed entries.

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
