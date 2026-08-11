---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-013 — Remove legacy Amp agent execution

## Existing field refined

The host still represented agent execution as a runtime choice between the
accepted Agenticus/Pi architecture and a rollback-only Amp subprocess adapter.
That choice made the composition snapshot nullable, branched runtime ownership,
persisted mode/profile/snapshot triples, and required cross-mode cutover tests
and configuration despite Pi being the only intended architecture.

## Accepted boundary

`compose_agent() -> AgentComposition` now resolves the sole exact isolated Pi
A2 profile and non-null Catalog snapshot. `compose_agent_runner(...)` performs
the exact READY probe and returns either `PiNativeRunner` or the existing
fail-closed `UnavailablePiRunner`; it does not select among providers.

`AgentRouteStore` persists only logical operation, exact profile, non-null
snapshot, and settlement. The profile remains because the Catalog snapshot does
not identify the selected provider/model. Composition-change fencing, terminal
History repair, and claim-before-provider ordering remain replay guarantees.
The prior schema migrates unresolved Agenticus custody exactly, discards only
settled legacy rows, and refuses unresolved legacy work rather than
reinterpreting it.

The legacy Amp adapter, export, tests, mode enum, mode/isolation configuration,
nullable composition, runtime branch, and rollback cutover behavior were
deleted. Provider-neutral protocol tests previously colocated with the Amp
adapter moved to their actual contract owner. The Amp webhook relay was not
touched.

## Validation and review

Focused Agenticus, Pi, protocol, Activity, service, and migration evidence passed
140 tests. Quick and full project gates passed, including all 9 unrelated Amp
webhook relay tests and 584 Python tests. Adversarial review first found the
History-before-route-settlement migration gap and provider-neutral tests still
owned by the deleted adapter. Both were corrected; final review returned
`APPROVE`.

## Consequences

- Host startup describes one execution architecture instead of one choice plus
  a dormant implementation.
- Pi absence is unambiguously unavailability, never fallback.
- Deployment configuration must remove the retired mode and isolation keys;
  stale settings fail with an explicit migration message.
- Existing unresolved Pi operations remain restartable under the same exact
  composition.
- No Net, lifecycle, Motus, scheduler, GitHub ingress, or Petrus behavior
  changed.
