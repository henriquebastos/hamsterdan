---
status: Decided
raised: 2026-08-11
decided: 2026-08-11
deciders:
  - Henrique (Navigator)
supersedes:
  - 2026-08-05T1254Z-agenticus-routing-is-explicit-host-owned-and-fail-closed
related:
  - CV16
  - CV16.DS11
  - RS-013
---

# Agenticus Pi is the only agent execution route

## Decision

Hamsterdan has one production agent execution architecture: the exact isolated
Pi native A2 Local composition. The legacy Amp subprocess runner, runtime mode,
isolation waiver, rollback profile, and cross-mode cutover protocol are removed.
Pi unavailability fails closed and cannot select another runner.

The host still durably binds each logical operation to the exact reconstructible
execution composition: provider/model profile metadata plus immutable Petrus
Catalog snapshot. That identity remains stable across Attempts and restart.
Terminal Petrus History settles operation custody, and startup repairs the
History-before-settlement crash window.

Existing Agenticus operation custody is migrated without reinterpretation.
Resolved legacy rows have no continuing product meaning and are discarded.
Unresolved legacy work is refused because its implementation no longer exists;
it is never resumed through Pi.

## Consequences

- Startup has no agent mode choice and no nullable runtime composition.
- `RoutedAgentRunner` remains the one claim-before-provider composition edge.
- A changed profile or Catalog snapshot remains fenced while prior-composition
  work is unresolved; this is replay safety, not a product rollback feature.
- Retired `HAMSTERDAN_AGENT_MODE` and
  `HAMSTERDAN_AGENT_ISOLATION_REQUIRED` settings fail explicitly so stale
  deployment configuration cannot silently select or describe false behavior.
- The Amp webhook relay and operator rollback procedures are separate GitHub
  ingress concerns and are not changed by this decision.
