---
code: CV20.DS4
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS3 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv20-ds3-expose-workflow-activity.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
  - ../../decisions/records/2026-08-28T1113Z-dashboard-closure-converges-before-generation-close.md
---

# CV20.DS4 — Settle one GitHub Activity lookup-first

## Outcome

Execute the DS3 `DashboardPublication` through a real readiness adapter and
bounded GitHub provider implementation. Complete lookup precedes at most one
publication attempt; an accepted-but-hidden response is recovered in a later
step; the exact landed `DashboardPublicationOutcome` returns to the original
Activity occurrence and the real workflow fold updates posture.

## Vertical path

```text
DS3 ActivityRequested(DashboardPublication, occurrence, operation)
  -> readiness claims one exact attempt
  -> github_app complete marker lookup plus current fence
  -> at most one dashboard/comment publication attempt
  -> durable provider observation
  -> readiness records exact landed DashboardPublicationOutcome
  -> Petrus completes original occurrence and workflow folds
  -> host records settled detached posture
```

This is the first accepted external-effect family. It remains exercised by
deterministic provider simulation by default; any live GitHub mutation requires
separate explicit approval.

## Component Technical Stories

1. Implement bounded provider transport/gateway values and App authentication
   lifetime without leaking credentials, including one exact PR read and one
   bounded configured-repository open-PR list page for later consumers.
2. Implement operation-marker lookup and one-attempt dashboard publication.
3. Qualify Motus attempt-claim, effect-observed and terminal-recorded seams.
4. Implement the readiness publication adapter and strict terminal admission.
5. Extend host concrete construction plus provider/readiness/workflow/root
   simulation, checker and correspondence evidence.

## Initial owned paths

```text
src/hamsterdan2/github_app/{auth,transport,gateway,effects}.py
src/hamsterdan2/readiness/effects/publication.py
src/hamsterdan2/readiness/{application,runtime,ports}.py
src/hamsterdan2/host/composition.py
implemented owner-local/root simulation and tests
Petrus/Motus split effect-position seam and dependency pin, if needed
```

## Fixed design

- The workflow request/terminal remain workflow-owned. Provider observations
  and refusal/ambiguity values remain `github_app`-owned. Readiness alone maps
  between them.
- Provider read acquisition identity is `(ProviderRouteId, ProviderReadId)`.
  Retrying a read that can observe changed state creates a new read ID. Exact
  reads normalize to the same `PullRequestSnapshot` plus read provenance used by
  DS2's source-neutral admission seam; they do not create a second observation
  path.
- The gateway exposes exact current-PR read mechanics and one bounded open-PR
  list page. It owns transport, pagination and rate metadata, not discovery-pass
  custody, eligibility, registration, lifecycle or readiness classification.
  DS10 is the first consumer of repository listing.
- Every effect uses stable operation identity and provider-observable marker:
  `<!-- hamsterdan:readiness operation=<operation> head=<head> -->`.
- A bounded complete lookup runs before each possible mutation. One call makes
  at most one provider mutation attempt and never retries immediately after an
  ambiguous response.
- Activity claim, effect observation and terminal recording are distinct cuts.
  Lost process-local result forces lookup-first recovery.
- Terminal admission compares activity, occurrence, exact work, correlation,
  idempotency, terminal variant and terminal operation before History.
- Credentials/tokens stay in host/provider construction and never enter
  workflow, artifacts, simulation commands or detached results.
- Physical lookup/mutation counts, retained provider bytes and terminal count
  are observed independently of final workflow state.

## API-strengthening checkpoint

Review the exact request→provider→terminal call tree and settle:

- bounded transport page/call/result metadata and provider error taxonomy;
- exact PR read and one-page open-PR list inputs/results, including stable
  candidate identity, pagination correspondence and rate metadata;
- gateway lookup/publication inputs, marker extraction and accepted/refused/
  ambiguous result values;
- Activity attempt claim/effect observation/terminal record signatures;
- readiness adapter, authority fence and terminal-admission signatures;
- operation collision, stale authority, malformed provider response and
  correlation errors;
- per-call/time/page/body/retained-byte limits and physical-attempt metrics; and
- mock/live correspondence fixture and evidence names.

Write the ruled API into [the API contract](api-contracts.md). Lookup-first
order, one-attempt cardinality, exact terminal return and credential custody are
fixed.

## Tracer acceptance

Given the exact pending DS3 request, when bounded host/readiness work runs, then
one provider publication is accepted and one landed
`DashboardPublicationOutcome` closes the original occurrence. If the response
is lost after provider acceptance, generation 2's first effect action is lookup,
no second mutation occurs, and the same terminal and workflow posture result.

Acceptance also requires exact-read/list-page normalization and bounds without
making DS4 perform discovery, plus refused/stale/collision paths,
provider-result and terminal-substitution cross sensitivities, exact replay,
lowered call/page/byte/attempt budgets, physical one-effect evidence, real
SDK/HTTP mock-transport and GitHub marker correspondence, and secret scans.
Unapproved live correspondence is explicitly unavailable rather than silently
green.

## Done condition

The full request-to-effect-to-original-fold loop is accepted. A green provider
client, effect adapter or workflow terminal test alone cannot close the DS.

## Stop conditions

Stop if effect lookup is incomplete/unbounded, one step can attempt twice,
readiness trusts a local “already called” flag, host maps a workflow terminal,
correlation is checked after History, or credentials cross into another owner.

## Rollback

Remove provider execution/adapter growth and fresh provider state. DS3 retains
the pending `DashboardPublication`; no current-runtime path changes.

## Validation

Run provider exact-read/list-page and adapter/workflow behavior, each split
effect cut, accepted-hidden recovery, one-attempt/cardinality checks,
authority/collision/terminal failures, local/cross sensitivities, exact replay,
every limit at −1 / limit / +1, SDK list/get/pagination/rate correspondence,
secret scans and project gates.

## Expansion boundary

Provider, runtime-seam and adapter work may land as Technical Stories. The DS
stays open until one workflow-declared request completes one real composed
lookup-first effect and returns to its original workflow occurrence.
