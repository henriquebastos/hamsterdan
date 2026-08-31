---
code: CV20.DS2
level: Delivery Story
status: Dropped
status_reason: Parent CV20 was superseded before implementation by CV21 and CV22; this reviewed story is retained as design evidence
updated: 2026-08-28
related:
  - index.md
  - cv20-ds1-first-bounded-pr-lifecycle.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
  - ../../decisions/records/2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md
---

# CV20.DS2 — Admit and fold one PR observation

## Outcome

Deepen the DS1 lifecycle with one real inbound observation. A bounded raw
GitHub pull-request webhook is verified and normalized by `github_app` into an
immutable `PullRequestSnapshot` plus webhook `ObservationProvenance`, retained
under host delivery custody, projected by readiness into focused observations,
staged as one immutable `IngressManifest` and manifest-scoped `AdmissionGrant`,
classified against Petrus History, folded by the real workflow when novel,
reflected in detached posture and acknowledged by host only after readiness
reports accepted or already-accepted posture.

## Vertical path

```text
bounded raw webhook bytes
  -> github_app signature verification and typed normalization
  -> PullRequestSnapshot plus webhook ObservationProvenance
  -> host delivery_retained under active route binding/custody
  -> readiness observation/key projection and manifest plus grant
  -> History classification and identified admission
  -> real workflow HeadSeen fold when novel
  -> changed detached StepResult/WorkPosture
  -> host exact-delivery acknowledgement and posture record
```

After acceptance, one real PR head/base observation changes workflow state and
is recoverable at every custody cut. No Activity or external mutation occurs.

## Component Technical Stories

1. Add provider-owned webhook/config/snapshot/provenance values and raw-byte
   verification.
2. Add host active-route binding and three-layer receipt/delivery custody for
   one subject/delivery.
3. Add readiness canonical observations/keys, manifest/grant storage, durable
   classification, corroboration and bounded admission cuts.
4. Add workflow `HeadSeen` vocabulary with local incarnation 1 and the lifecycle
   fold that consumes it.
5. Extend local/root simulations, checkers, artifacts and correspondence for
   the new provider→host→readiness→workflow edge.

Each component may be reviewed independently; accepted Delivery requires the
whole path and host acknowledgement ordering.

## Initial owned paths

```text
src/hamsterdan2/github_app/{models,config,webhooks,routing}.py
src/hamsterdan2/host/composition.py and host custody/inspection owners
src/hamsterdan2/readiness/{application,ports}.py
src/hamsterdan2/readiness/custody/ingress.py
src/hamsterdan2/readiness/effects/evidence.py
src/hamsterdan2/workflow/observations.py and workflow/net/life.py
implemented owner-local/root simulation and tests
```

## Fixed design

- Signature verification receives exact raw bytes before JSON parsing.
- Provider SDK objects, credentials, headers and raw dictionaries do not cross
  `github_app`.
- `PullRequestSnapshot` is immutable provider truth: stable `PRSubject`, exact
  head/base `BranchTip(repository_id, ref, sha)`, lifecycle, draft, tri-state
  mergeability and diagnostic provider update time. Webhook event/action belongs
  only to `ObservationProvenance`; readiness-owned policy is `PolicySeen`, not a
  provider snapshot field.
- Host owns delivery/route custody; readiness owns manifest/grant and workflow
  admission; workflow owns the observation and fold meaning.
- Webhook acquisition identity is `(ProviderRouteId, DeliveryId)` and preserves
  exact `X-GitHub-Delivery`. `ActiveRouteBinding`, `RouteGeneration` and host
  `CustodyGeneration` replace undefined door identity. Generations are
  provenance/fences, not semantic equality.
- `HeadSeen` contains `PRSubject`, local incarnation and exact head/base
  `BranchTip` values. Draft, lifecycle, mergeability and policy are separate
  focused observation families. The first locally admissible `HeadSeen` binds
  incarnation 1 as an observation, not provider-current authority. DS2 never
  increments it and does not implement `CurrentnessWitness`; DS9 owns both.
- `ObservationKey` is `obs:v1:sha256:<digest>` over persisted canonical bytes of
  version, subject, local incarnation, observation family and focused semantics.
  Version 1 freezes key encoding, not snapshot schema. Equality compares bytes
  as well as digest.
- Same acquisition identity and content is `exact_duplicate`; changed bytes
  under that identity is `acquisition_collision` and quarantines before History.
  Same key/bytes from another acquisition is `corroborating`: append one bounded
  deterministically deduplicated provenance reference without another History
  admission or fold. Same key/different bytes is a fatal `semantic_collision`.
- Readiness persists one `IngressManifest` and one immutable manifest-scoped
  `AdmissionGrant` per acquisition, including an empty projection. A grant
  authorizes classification/admission under its frozen lifecycle binding; it is
  not fresh provider truth, effect authority or a mutable latest-subject grant.
  Each manifest has `0..N` ordered unique-key `IngressEntry` values. Empty
  manifests stage but create no History event.
- `HistoryAdmissionId = admission:v1:sha256:<ObservationKey digest>` identifies
  Petrus delivery. Petrus History is the sole workflow-admission ledger;
  `ObservationAdmission` is only a rebuildable projection/index. No separate
  observation/admission ledger is allowed.
- Persist the closed `AdmissionDecision` family: `exact_duplicate`,
  `acquisition_collision`, `novel`, `corroborating`, `stale`,
  `semantic_collision`, `conflicting`, `incomparable`. Contradictions are
  durable non-retryable failure-as-data. Delivery ID, receipt time,
  provider `updated_at` and Git ancestry establish no total order; changed
  unconfirmed evidence is `incomparable` and refresh-required.
- One call performs one named bounded cut: `delivery_retained`,
  `delivery_quarantined`, `ingress_staged`, `ingress_entry_classified`,
  `observation_accepted`, `observation_folded`, `readiness_step_returned`,
  `delivery_acknowledged` or `custody_item_disposed`. Corroboration stops at the
  no-fold `ingress_entry_classified` cut.
- Receipt has three layers: Amp's GitHub-facing HTTP receipt, host
  `InboxReceipt` proving retention or permanent refusal/quarantine, and terminal
  `delivery_acknowledged`. Host performs guarded idempotent
  `retained → acknowledged` CAS only after accepted/already-accepted posture;
  pending posture cannot acknowledge.
- Raw body, signature and non-allowlisted headers are transient. Normalized
  delivery/snapshot evidence remains through active and accepted-but-
  unacknowledged custody, then atomically compacts to a bounded redacted
  tombstone. No TTL, eviction or truncation may erase required evidence.
- Every resource limit is finite and refusal occurs before partial durable
  writes. Numeric limits and exact refusal/cut payloads are fixture-calibrated
  Plan refinements with −1 / limit / +1 evidence, not accepted constants.
- Host acknowledges only after readiness returns accepted/already accepted for
  that exact delivery.
- Reconstruction uses durable inbox, manifest/grant and History state, never a
  parsed request object or returned fold value.
- The observation and posture have strict codecs and byte/record limits.
- DS2 is strictly webhook-only. Provider reads in DS4/DS9/DS10 converge through
  the same snapshot/provenance → observation/key → manifest/admission contract.
- DS2 crash recovery is blocked until Petrus, beyond pinned
  `44cac5ff48ac371ebae56323941983f30db13c0d`, supplies a public bounded
  accept/resume-one-accepted-unfinished-occurrence seam that Hamsterdan pins and
  qualifies. Internal `Instance` access and collapsing accepted/folded cuts are
  forbidden.
- Python uses validating native scalar subtypes, strict Pydantic at durable/
  external boundaries, frozen dataclasses only when they remove real
  boilerplate, private state with predicates/domain operations and direct
  callable composition. Exact classes/methods/signatures and Pydantic/dataclass
  placement remain call-site Plan decisions. `dict[str, Any]`, generic handler/
  context/result names, exported status enums, one-file-per-noun,
  Protocol-per-call and fake-pure reducers are rejected.

## API-strengthening checkpoint

Review the exact raw-webhook→fold call tree and settle:

- webhook envelope, provider route, delivery and subject value shapes;
- snapshot/provenance, `BranchTip`, focused observation and canonical-key codecs;
- host retain/route/acknowledge and readiness stage/admit calls;
- manifest/grant/entry schema, `AdmissionDecision`, corroboration, collision and
  acknowledgement results;
- every fixed named cut, receipt layer, tombstone and repair payload;
- provider/host/readiness/workflow observations, local/cross report fields and
  row/page/body/journal/artifact limits; and
- unresolved API/error names visible at the real call sites.

Record the ruled signatures in [the API contract](api-contracts.md). Ownership,
raw-byte verification, immutable staging, exact duplicate behavior and
acknowledgement order are fixed.

## Tracer acceptance

Given one valid signed pull-request delivery for the DS1 subject, when host
processes bounded work, then the exact normalized incarnation-1 `HeadSeen`
reaches one identified History admission and real workflow fold, readiness
returns accepted posture and host acknowledges the same delivery. Invalid
signatures, wrong subjects and content collisions fail before workflow
admission.

Acceptance also proves:

- crash/reopen after inbox retention, manifest/grant commit, History acceptance,
  fold and returned posture, with one final acknowledgement;
- empty manifests, exact retries, acquisition/semantic collisions,
  corroboration, conflicting/incomparable classifications and accepted-History/
  missing-local-projection repair with no duplicate root/admission/fold;
- a composition-only observation or delivery substitution leaves every local
  checker green and fails exactly the responsible cross edge;
- exact replay from fresh modules and lowered input/row/page/history budgets;
- provider, host, readiness and workflow resource peaks; and
- real raw-byte signature, typed normalization and fresh SQLite/filesystem
  correspondence.

## Evidence contract

- **TDD behavior:** HMAC-before-parse, incarnation 1, empty manifest, exact
  retry, both collision classes, corroboration, atomic manifest/grant, History
  repair, no early acknowledgement, accepted/already-accepted acknowledgement
  and tombstone compaction.
- **Property/stateful:** deterministic/NFC codec round trips; each semantic field
  changes the key while provenance, policy and timestamps do not; webhook/read
  source permutations converge; bytes are checked with the digest; retries and
  crashes preserve one manifest/acquisition and one History admission/fold/key.
- **Mutation:** removing semantic key components, adding forbidden key inputs,
  treating tri-state mergeability as boolean, omitting route from acquisition
  identity, digest-only equality, early acknowledgement, missing CAS, second
  fold, trusting local projection, silent truncation and secret leakage must be
  detected.
- **Deterministic simulation:** crash/redelivery/collision at every named cut,
  accepted-History/missing-local repair, accepted-begun-unfinished occurrence,
  reduced budgets and fresh route/custody generations exactly replay.
- **Real seams:** raw GitHub HMAC/GUID redelivery, tri-state mergeability, real
  codecs/SQLite/filesystem/process death and the qualified Petrus resume seam.
  Fake only external Amp/GitHub transport and injected clock behavior.

Every finite limit is exercised at −1 / limit / +1. DST does not establish
GitHub ordering, webhook completeness or provider currency.

## Done condition

The full inbound edge and acknowledgement loop are accepted with exact typed
values, crash recovery, checker sensitivity, replay, bounds and correspondence.
A provider value or workflow unit test alone cannot satisfy this DS.

## Stop conditions

Stop if provider parsing leaks into host/readiness, workflow receives delivery
custody, host acknowledges before readiness acceptance, one call drains several
entries/folds, or recovery needs an in-memory request/fold result.

## Rollback

Remove this tracer's fresh provider/inbox/ingress state and added code. DS1's
provider-free one-PR lifecycle remains intact and current production is unchanged.

## Validation

Run signature/schema/subject failures, ingress and workflow behavior tests,
every named crash cut, duplicate/collision/corroboration/classification checks,
canonical codec properties and mutation sensitivity, accepted-History repair,
local/cross sensitivities, exact replay, every limit at −1 / limit / +1,
raw-HMAC/GUID redelivery, tri-state mergeability, real Petrus resume seam,
fresh-storage/process-death correspondence, secret scans and project gates.

## Expansion boundary

Expand by custody owner, but retain one vertical acceptance artifact. Do not
accept “provider observation implemented” or “workflow fold implemented” as
Delivery until the same real value traverses all owners and host acknowledges it.
