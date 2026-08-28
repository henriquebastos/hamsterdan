---
code: CV20.DS10
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS9 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv20-ds9-fence-lifecycle-authority.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
  - ../../decisions/records/2026-08-28T0153Z-configured-repository-recovery-discovers-unknown-open-pull-requests.md
---

# CV20.DS10 — Discover unregistered open PRs boundedly

## Outcome

Recover eligible open pull requests whose first webhook never became durable.
For one operator-configured repository, host owns a bounded
`RepositoryDiscoveryPass`, uses one bounded GitHub list page at a time, compares
listed identities with the durable subject catalog, exact-reads each unknown
candidate before registration, and idempotently registers and enqueues eligible
subjects into the same known-subject reconciliation path.

## Vertical path

```text
configured repository discovery turn
  -> host opens one bounded RepositoryDiscoveryPass
  -> github_app returns one bounded open-PR identity page
  -> host compares candidates with the durable subject catalog
  -> github_app exact-reads one unknown candidate
  -> host classifies route/lifecycle/eligibility
  -> idempotent subject registration plus runnable enqueue
  -> persist RepositoryDiscoveryPassBoundary
  -> complete or visibly defer the pass
```

List summaries are discovery hints. They never enter Petrus History and never
become workflow observations. The exact read must pass the same source-neutral
snapshot/provenance → observation/key → manifest/admission contract introduced
by DS2 before workflow admission can occur.

## Component Technical Stories

1. Add one bounded GitHub open-pull-request list-page result through the DS4
   provider gateway.
2. Add host-owned configured-repository discovery-pass custody and the durable
   `RepositoryDiscoveryPassBoundary`.
3. Compare one bounded candidate set against the durable catalog and exact-read
   unknown candidates before registration.
4. Classify closed, missing, unauthorized, route-invalid and otherwise
   ineligible exact reads without blind registration.
5. Register and enqueue eligible subjects idempotently and extend local/root
   simulation, checkers, replay, bounds and GitHub correspondence.

## Initial owned paths

```text
src/hamsterdan2/github_app/{gateway,models,transport}.py
src/hamsterdan2/host/{discovery,instances,runnable,inspection}.py
src/hamsterdan2/host/composition.py
implemented GitHub/host/root simulation and tests
```

The DS API review may merge `host/discovery.py` into another coherent host owner
if the deletion test does not justify a distinct module. Repository traversal,
pass custody and unknown-subject registration must remain host-owned either way.

## Fixed design

- Discovery lists only operator-configured repositories. A repository that the
  App can access but configuration does not admit is ignored or refused.
- `RepositoryDiscoveryPass` is a bounded durable work unit. A provider page is
  only a transient query window. The persisted resume vocabulary is
  `RepositoryDiscoveryPassBoundary`, not a generic cursor or timestamp.
- `LastCompletedOpenPullRequestDiscoveryPass` records the last completed
  bounded pass for inspection and scheduling. It is not a provider completeness
  watermark and does not authorize lifecycle changes.
- `UnknownPullRequestDiscovery` identifies this recovery source without making
  discovery summaries provider truth or workflow input.
- Every unknown listed candidate receives an exact provider read before
  registration or enqueue. List summaries never enter History.
- Registration and enqueue are idempotent. Repeated pages, page-1 restart,
  overlap, crash and webhook/discovery races create at most one subject binding
  and one due known-subject reconciliation path.
- A completed pass proves only that the bounded traversal completed under its
  recorded correspondence. It does not claim an atomic repository snapshot.
- Absence from a list page or completed pass never closes, revokes, deletes or
  proves completeness of the durable catalog.
- Pagination, rate state, protected reserve, page/candidate/call/byte limits,
  pass leases and defer windows are finite. Their numeric values and the choice
  between page-1 restart and ETag-validated continuation require fixture
  calibration at the DS Plan Checkpoint.
- Wall-clock time and DST are scheduling/correspondence concerns only. Neither
  establishes provider ordering, webhook completeness or list completeness.

## API-strengthening checkpoint

Review one list-page→exact-read→register/enqueue call tree and settle:

- configured-repository and discovery-turn input values;
- `RepositoryDiscoveryPass`, `RepositoryDiscoveryPassBoundary`,
  `LastCompletedOpenPullRequestDiscoveryPass` and
  `UnknownPullRequestDiscovery` durable/inspection shapes;
- provider list-page and exact-read results plus pagination/rate metadata;
- pass open/page/candidate/classify/register/complete/defer operations and
  transactions;
- page-1 restart versus ETag-validated continuation from measured fixtures;
- missing/closed/unauthorized/route-invalid/rate-deferred classifications;
- registration/enqueue collision and webhook-race behavior;
- page/candidate/call/byte/time/lease/defer/rate-reserve/journal/artifact limits;
  and
- repository-list, exact-get, pagination, rate and process-restart
  correspondence fixtures.

Exact Python signatures, cut payloads, refusal payloads and numeric limits are
Plan refinements. Every selected limit remains finite and requires
−1 / limit / +1 evidence before acceptance.

## Tracer acceptance

Given an operator-configured repository containing an eligible open PR with no
durable webhook or subject binding, when repeated bounded discovery turns run
with sufficient rate capacity and the PR remains open through one completed
pass, then an exact read precedes one idempotent registration/enqueue and the PR
enters known-subject reconciliation.

Acceptance also proves:

- page restart, overlap, repeated candidates, webhook/discovery races and crash
  at every pass-boundary/registration/enqueue cut create no duplicate binding;
- closed, missing, unauthorized and route-invalid exact reads are classified
  without workflow admission;
- list absence causes no close, revoke, delete or catalog-completeness claim;
- one unstable/rate-deferred repository remains visible and cannot convert
  partial traversal into a completed pass;
- owner-local and cross checker sensitivities, exact fresh-object replay,
  finite generated schedules and resource peaks;
- every limit at −1 / limit / +1; and
- real GitHub list/get pagination and rate metadata, fresh SQLite/filesystem,
  OS process death and DST correspondence.

## Done condition

Unknown eligible open PRs in configured repositories enter the durable
known-subject recovery path through bounded passes and exact reads. No atomic
snapshot, historical closed-PR discovery or provider-global traversal is
claimed.

## Stop conditions

Stop if list summaries enter History, list absence changes lifecycle, an
accessible unconfigured repository is traversed, registration precedes exact
read, a pass hides unbounded pagination, a generic timestamp/cursor claims
completeness, or discovery is folded into DS2, DS4, DS9 or DS11 ownership.

## Rollback

Remove discovery-pass custody, list-page use and discovery scheduling. DS9's
registered-subject exact-read recovery remains; current production is unchanged.

## Validation

Run list/get normalization, configured-scope refusal, pagination/rate behavior,
exact-read-before-registration, idempotent registration/enqueue, webhook races,
pass crashes/restarts, list-absence safety, local/cross sensitivities, generated
schedules/shrinking, exact replay, all limits at −1 / limit / +1, GitHub/storage/
process/DST correspondence, secret scans and project gates.

## Expansion boundary

Provider list-page mechanics, pass custody and registration may land as separate
Technical Stories. Keep DS10 open until one unknown eligible PR traverses the
real configured-repository discovery vertical into known-subject reconciliation.
