---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-004 — Separate publication concern ownership

## Existing field refined

RS-001 replaced the aggregate `Control` token with independently addressable
business concerns, but retained one 23-field `PublicationState`. Finding,
conversation, dashboard, and readiness publication therefore consumed and
replaced the same token even though they have independent operation ownership,
failure, recovery, and terminal acceptance.

The aggregate also represented absent operation identity with an empty string
and retained exact recovery requests as generic dictionaries. Pydantic validated
the outer state but could not statically express which request belonged to each
recovery path.

## Refinement boundary

Replace `PublicationState` with four concrete strict Pydantic values and four
Petri places. Do not introduce a base class, generic publication framework, or
dynamic field-name router. Each transition consumes only the publication token
it owns; full-cohort joins remain limited to relational projection, generation
boundaries, dashboard derivation, conversation context, reminders, and
readiness gates.

Keep internal recovery custody out of `ReadinessSnapshot`. The snapshot remains
a business projection rather than a serialized copy of every workflow field.
No old Hamsterdan History/token compatibility is required.

## Delivered structure

```text
FindingPublicationState
  published / requested / operation / capability blocker

ConversationPublicationState
  requested / operation / exact ConversationPublicationRequest recovery
  capability blocker / terminal fault

DashboardPublicationState
  current and requested projection / operation
  exact DashboardPublicationRequest recovery / format
  capability blocker / terminal fault

ReadinessPublicationState
  requested / announced / operation
  exact ReadinessCommand recovery
  capability blocker / terminal fault
```

Operation ownership is `str | None`; absence is no longer an empty string.
Recovery is an exact request value or `None`. `ReadinessSnapshot` explicitly
projects public business state and omits all three retained recovery requests.
Host replay reconstructs each nested token through Pydantic `TypeAdapter` rather
than relying on direct dataclass construction from untyped JSON.

The recovery transition is now three explicit paths:

```text
recover_publication.conversation
recover_publication.dashboard
recover_publication.readiness
```

Each path reads authority and the two nonselected recoverable owners, consumes
only its selected owner plus the exact intent, and emits only that owner plus
its exact work contract. Invalid or stale recovery still has one explicit
retirement path.

## Topology result

| Metric | After RS-003 | After RS-004 |
| --- | ---: | ---: |
| Places | 43 | 46 |
| Transitions | 67 | 69 |
| Arcs | 266 | 309 |
| Retirement transitions | 17 | 17 |

The three-place increase replaces one aggregate place with four independent
owners. The two-transition increase replaces one dynamic recovery router with
three visible typed transitions. Arc growth makes true relational reads
explicit; it does not add execution or lifecycle mechanics. Topology count was
an observation, not an optimization target.

## Validation

Structural tests lock exact owner-local read, consume, and output arcs for
reply, dashboard, readiness, result acceptance, and all recovery paths.
Parameterized integration evidence proves conversation, dashboard, and
readiness recovery across process restart: each reconstructs the exact typed
request, creates one fresh Activity occurrence with the same operation,
idempotency, and payload, changes only selected ownership, clears after success,
and cannot recreate the same logical operation from stale recovery.

Static, formatting, type, package, relay, and full Python validation passed.
Independent adversarial review returned `APPROVE` with no release blocker.

## Consequences and next boundary

- Publication channels may evolve independently without rewriting unrelated
  durable state.
- `ReadinessSnapshot` remains the only complete consumer-facing business view;
  it is never a place color.
- No Petrus enhancement, actor abstraction, storage migration, or HA mechanism
  was warranted.
- The next refinement should inspect `ActionsState` and `MutationState` from
  executable transition dependencies before deciding whether either contains
  false coupling.
- Host activation-path simplification follows business-model clarity; HA and
  PostgreSQL remain explicitly deferred.
