---
status: Decided
raised: 2026-08-27
decided: 2026-08-28
recorded: 2026-08-28T0153Z
deciders:
  - Henrique (Navigator)
supersedes_in_part:
  - 2026-08-01T0335Z-githubkit-and-a-durable-relay-own-provider-ingress.md
  - 2026-08-27T1604Z-composable-hamsterdan-is-the-planned-replacement-architecture.md
  - 2026-08-27T1925Z-cv20-delivers-through-vertical-tracer-bullets.md
related:
  - CV20.DS9
  - CV20.DS10
  - CV20.DS11
  - CV21.DS9
  - CV21.DS10
  - CV21.DS11
---

# Configured-repository recovery discovers unknown open pull requests

## Decision

CV20 recovery covers both known and unknown eligible open pull requests in the
operator-configured repository portfolio.

For every registered nonterminal PR, repeated bounded exact reads eventually
converge known-subject state when the provider and configured route remain
available. For an eligible PR with no durable subject binding, repeated bounded
repository discovery passes eventually exact-read, register and enqueue it when
it remains open through a completed pass and sufficient quiescence/rate capacity
exists.

Unknown-subject discovery is a separate CV20.DS10 tracer. The former DS10
multi-PR supervision, DS11 qualification and DS12 cutover become DS11, DS12 and
DS13. This changes the CV20 sequence from eleven tracers plus cutover to twelve
tracers plus cutover without changing the vertical-tracer contract.

## Consequences

- Discovery lists only configured repositories. Provider accessibility is not
  configuration authority.
- Host owns `RepositoryDiscoveryPass` custody and persists explicit
  `RepositoryDiscoveryPassBoundary` values. Pages are transient provider query
  windows, not durable batches or workflow evidence.
- A listed unknown PR receives an exact provider read before registration or
  enqueue. List summaries never enter Petrus History.
- Registration and enqueue are idempotent across repeated pages, page restart,
  webhook/discovery races and process loss.
- The guarantee is eventual under completed bounded passes, not an atomic
  repository-snapshot guarantee. List absence never closes, revokes, deletes or
  proves completeness of the durable catalog.
- DS11 fairly schedules known-subject and discovery turns. DS9 retains
  lifecycle/freshness/current-authority ownership; DS4 retains provider list/get
  mechanics; DS2 remains webhook-only.
- Pagination, rate reserve, page/candidate/call/byte bounds, pass leases,
  deferral, restart/continuation and DST correspondence remain DS10 Plan and
  acceptance refinements backed by fixtures and −1 / limit / +1 evidence.
- The 2026-08-01 manual-redelivery consequence is superseded for CV20's planned
  replacement only. It remains historical truth for the current V5 runtime.
- E1 was selected and this canonicalization was approved through the source
  coordinator thread. This record does not manufacture a direct Navigator quote
  or treat the absent pending queue as repository truth.
