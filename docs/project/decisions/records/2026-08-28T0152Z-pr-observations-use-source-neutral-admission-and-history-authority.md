---
status: Superseded
raised: 2026-08-27
decided: 2026-08-28
recorded: 2026-08-28T0152Z
superseded: 2026-09-01
superseded_by: 2026-09-01T1159Z-webhook-inbox-hands-novel-observations-to-history.md
deciders:
  - Henrique (Navigator)
related:
  - CV20.DS2
  - CV21.DS2
  - 2026-08-27T1925Z-cv20-delivers-through-vertical-tracer-bullets.md
---

# PR observations use source-neutral admission and History authority

Superseded by
[Webhook Inbox hands novel observations to History](2026-09-01T1159Z-webhook-inbox-hands-novel-observations-to-history.md).
The source-neutral observation and History-authority principles remain; the
manifest, grant, staging database, classification family, and host completion
consequences do not.

## Decision

Provider acquisition and workflow observation are different facts. A webhook or
provider exact read produces one immutable provider-owned
`PullRequestSnapshot` plus bounded source-specific `ObservationProvenance`.
Readiness projects focused workflow observations, persists their canonical bytes
and `ObservationKey`, stages one immutable `IngressManifest` and one
manifest-scoped `AdmissionGrant`, and uses identified Petrus delivery for each
novel observation. Petrus History is the sole workflow-admission ledger.

`ObservationKey` version 1 freezes semantic-key encoding, not the snapshot
schema. The key includes subject, local incarnation, observation family and
focused semantics. Acquisition identity, route/custody generations, provider
timestamps, policy and provenance are excluded from semantic equality. Same key
with different canonical bytes is a fatal semantic collision. Same key and
bytes from a different acquisition is bounded corroboration without another
History admission or fold.

The first locally admissible `HeadSeen` binds local incarnation 1. It records
the first lifecycle segment known to this Hamsterdan root; it does not prove
provider-current authority. DS2 never increments incarnation and does not
implement `CurrentnessWitness`. DS9 owns lifecycle successors, currentness and
authority.

DS2 implements webhook acquisition only. Later exact reads must use the same
snapshot/provenance → observation/key → manifest/admission seam rather than a
second workflow input path.

## Consequences

- `ObservationAdmission` may be a reconstructible projection/index, but it is
  never an admission ledger or authority source. No `ObservationLedger` or
  `AdmissionLedger` is introduced.
- One acquisition always has one manifest and grant, including an empty
  projection. An empty manifest enters readiness custody but creates no History
  delivery.
- Admission classification is durable and closed: `exact_duplicate`,
  `acquisition_collision`, `novel`, `corroborating`, `stale`,
  `semantic_collision`, `conflicting`, and `incomparable`.
- Contradictions are non-retryable failure-as-data. A changed observation that
  cannot be ordered from accepted evidence is `incomparable` and requires
  refresh; delivery ID, receipt time, provider update time and Git ancestry do
  not create a total order.
- DS2 crash recovery requires Petrus to expose and Hamsterdan to qualify a
  public bounded accept/resume-one-accepted-unfinished-occurrence seam. Internal
  `Instance` access and collapsing accepted/folded cuts are forbidden.
- This ruling was approved through the source coordinator thread after the
  Navigator approved Bundles A-D. It does not claim that an absent uncommitted
  queue or patch was applied.
