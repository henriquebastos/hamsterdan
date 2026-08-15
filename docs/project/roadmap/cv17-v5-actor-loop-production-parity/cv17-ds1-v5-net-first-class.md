---
code: CV17.DS1
level: Delivery Story
status: Active
status_reason: Starting with loop-by-loop TDD rewrite from the ES-007 AX1 record
updated: 2026-08-15
---

# CV17.DS1 — The V5 net as first-class code

## Scope

- Create `src/hamsterdan/readiness/net_v5/` as a parallel sibling of
  `readiness/net`, honoring the same architecture contract: it owns
  workflow decisions and imports nothing from `github_app`, `agents`, or
  `host`.
- Rewrite the nine ES-007 concern loops with TDD against the real
  `contracts/` types, using the AX1 record as guidance and the exploration
  code as reference only — no copy-paste of exploration fakes.
- Express dormancy as a loop inside the net, per the parity decision.
- Pin the structural census as tests: zero guards, zero read arcs, zero
  unowned places, every place owned by exactly one loop, cross-loop
  influence only through mailed-fact output seams, ingress doors as the
  only no-input transitions.
- Expose a `build_net_v5()` composition entry mirroring `build_net()`'s
  contract shape (net, handlers, activity bindings) so DS2 can compose it
  without special cases.
- Execute the ES-005 chapter-17 boundary timelines on the frozen engine
  with fake worlds at this stage; real host composition, durable history,
  and dispatch arrive in DS2/DS3.

## Out of scope

- Any change under `readiness/net`, `host`, `github_app`, or `agents`.
- Sharding, the courier, host wiring, durable recovery.

## Done condition

All nine loops implemented with their folds and activity declarations
against real contract types; structural census tests and boundary timeline
tests pass; `scripts/check full` is green; the Navigator accepts an
Experience Report.
