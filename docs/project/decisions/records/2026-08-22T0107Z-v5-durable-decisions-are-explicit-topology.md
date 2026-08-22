---
status: Decided
raised: 2026-08-21
decided: 2026-08-22
deciders:
  - Henrique (Navigator)
related:
  - ES-008
  - CV17
---

# V5 durable decisions are explicit topology

## Decision

Within V5 actor loops, durable domain alternatives and ordering that changes
enabledness are expressed through specialized token colors, places,
transitions, and arcs rather than an open envelope dispatched by Python
`kind`/`body` branching. Local calculations remain inside typed pure folds.
Filters are appropriate for total routing among predicates over one honest
type; they do not replace modeled outcome types.

The promoted readiness slice applies the rule to state, checks, review,
findings, human review, mutation pending/settled, and fault raised/cleared.
Actor-loop ownership, the readiness snapshot, provider gates, and the open
dashboard projection remain unchanged.

Cross-version recovery is part of the topology contract. The former
`ready.facts` place remains input-only, and filtered migration transitions
convert retained pre-promotion envelopes to specialized colors. It may be
removed only when an explicit migration boundary can prove no resumable
history retains that place; current producers must never write to it.

## Consequences

- The net, not incidental shared-mailbox FIFO order, states authority-before-
  evidence, pending-before-settlement, and recovery-clear-before-re-fault.
- New durable alternatives require an honest type and topology review; this is
  not a mandate to turn every Python branch into a place.
- Dashboard-only events continue using `GateFact`; readiness does not acquire
  types merely to steer dashboard projection.
- Additional places, transitions, arcs, drains, inhibitors, and migration
  branches are accepted when they represent these durable contracts. ES-008
  owns the measured cost and validation evidence.
- Conversation classification and lifecycle admission remain separately
  measurable candidates; this decision does not silently redesign them.
