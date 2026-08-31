---
code: CV22.DS1
level: Delivery Story
status: Planned
status_reason: Known dashboard concern is manifested; waits for CV21 and the CV22 hierarchy/conformance ruling before pull
updated: 2026-08-28
related:
  - index.md
  - architecture.md
  - ../../decisions/records/2026-08-28T1113Z-dashboard-closure-converges-before-generation-close.md
---

# CV22.DS1 — Rebuild the dashboard subnet

## Outcome

Deliver the dashboard as an independently executable production subnet that
preserves the accepted projection, single-flight publication, exact outcome,
recovery, and final closed-document behavior.

## Manifest boundary

The accepted dashboard decision establishes this concern and makes it the first
concrete subnet anchor. Typed ports, nested children, internal topology, and the
composition edge that closes this story are settled only when the story is
pulled.

## Completion direction

The exact production assembly must satisfy CV22's recursive subnet invariant
locally and mount unchanged in every required containing composition.
