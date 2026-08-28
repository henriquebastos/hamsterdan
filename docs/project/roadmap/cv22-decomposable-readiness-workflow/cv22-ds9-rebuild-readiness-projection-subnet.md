---
code: CV22.DS9
level: Delivery Story
status: Planned
status_reason: Known readiness projection concern is manifested; waits for CV21 and the CV22 hierarchy/conformance ruling before pull
updated: 2026-08-28
related:
  - index.md
  - architecture.md
---

# CV22.DS9 — Rebuild the readiness projection subnet

## Outcome

Deliver the all-gates readiness projection, ready-edge authorization,
announcement, and retained failure behavior as an independently executable
production subnet.

## Manifest boundary

The current workflow proves that readiness projection and announcement form a
distinct concern. Input facts, announce ports, nested children, and close
coordination are settled when the story is pulled rather than copied from V5.

## Completion direction

The exact production assembly must satisfy CV22's recursive subnet invariant
locally and mount unchanged in every required containing composition.
