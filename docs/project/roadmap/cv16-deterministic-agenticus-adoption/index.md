---
code: CV16
level: Value
status: Active
status_reason: Schema-2 A2 workspaces and host-derived canonical patches are deterministically qualified; authority and live gates remain
updated: 2026-08-05
---

# CV16 — Deterministic Agenticus adoption

## Intent

Move Hamsterdan from a hard-coded shared-orb Amp default to an explicit,
host-owned Agenticus composition without weakening workflow policy, credential
custody, operation identity, or recovery guarantees.

## Delivery

[CV16.DS11 — Host composition and operation-route custody](cv16-ds11-host-composition-and-route-custody.md)
owns the deterministic A2 profile, explicit rollback mode, immutable Catalog
snapshot, restart/cutover fence, credential-free Pi lifecycle adapter, and the
Petrus-owned A2 host boundary, and private archive-to-canonical-patch proof.

## Done condition

CV16 is complete only after separately bounded installation, adapter, authority,
runtime lifecycle, and live qualification slices preserve the existing
`AgentRunner` product protocol and demonstrate recoverable isolated execution.

## Boundaries

- The host remains the sole runtime composition and credential root.
- No GitHub credential enters agent territory.
- Legacy Amp is rollback only and never an automatic fallback.
- Static Catalog compatibility is not installation or live-provider evidence.
