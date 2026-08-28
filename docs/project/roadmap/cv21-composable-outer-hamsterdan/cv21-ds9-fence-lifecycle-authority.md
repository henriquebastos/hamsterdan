---
code: CV21.DS9
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV21.DS8 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv21-ds8-recover-timers-deferred-work.md
  - contract-inheritance.md
---

# CV21.DS9 — Fence lifecycle and authority changes

## Outcome

Complete new outer lifecycle, currentness, authority, route-generation, and
known-subject convergence behavior around the retained Net. Every protected
operation fails closed when phase, incarnation, head, base, policy, route, or
custody changes at its exact authority cut.

## Vertical path

```text
known subject -> bounded exact provider read -> common admission -> bridge
  -> retained lifecycle/work -> complete new authority claim and fence
  -> execute, block, move, close, or retain explicit failure
  -> detached host posture
```

## Owns

- successor lifecycle/currentness evidence and complete operation-specific
  authority matrix;
- known-subject exact-read convergence through common admission;
- active route/custody generation movement, blocked/moved/conflict outcomes,
  and lifecycle evidence exposed to host; and
- remaining closure/lifecycle bridge families and authority race schedules.

## Excludes

No unknown-subject discovery, workflow lifecycle redesign, host-decoded Activity
work, or automatic close after an unresolved ambiguous effect.

## Acceptance

- durable grant, fresh provider truth, and fresh host evidence agree at every
  required protected cut;
- route/custody movement between read and mutation prevents execution;
- known nonterminal subjects eventually exact-read under bounded availability;
- bridge maps only the current Net's selected lifecycle terminal/outcome;
- close preserves explicit unresolved work and committed History ordering; and
- exhaustive deterministic races and checker mutations cover the complete
  policy matrix.
