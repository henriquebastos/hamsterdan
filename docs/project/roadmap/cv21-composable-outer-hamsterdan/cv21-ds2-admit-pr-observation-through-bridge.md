---
code: CV21.DS2
level: Delivery Story
status: Active
status_reason: Tasks 1 and 2 are delivered; source-neutral readiness staging is the next planned task and tasks 3 through 5 remain
updated: 2026-08-30
related:
  - index.md
  - cv21-ds1-first-bridged-pr-lifecycle.md
  - contract-inheritance.md
  - ../../decisions/records/2026-08-28T0152Z-pr-observations-use-source-neutral-admission-and-history-authority.md
---

# CV21.DS2 — Admit one PR observation through the bridge

## Outcome

Accept one signed GitHub webhook through new provider normalization and durable
host delivery custody, then acknowledge the HTTP request without waiting for
readiness. A later authority turn performs source-neutral readiness admission,
bridge conversion, and identified Petrus History delivery until the current
Net folds the exact observation. Custodied, acknowledged, admitted, and folded
remain distinct reconstructible cuts.

## Vertical path

```text
HTTP request: raw webhook -> new GitHub verification/normalization
  -> host delivery custody -> HTTP acknowledgement -> request ends

later authority turn: PullRequestSnapshot + provenance -> focused observation/key
  -> manifest/grant -> bridge conversion -> identified History -> current fold
  -> detached posture -> host delivery completion
```

## Owns

- first provider models, webhook acquisition, route evidence, and durable host
  delivery custody;
- snapshot/provenance, focused observation/key, ingress manifest/grant/entries,
  exact classification, and acknowledgement cuts; and
- first observation-family bridge census and correspondence scenarios.

## Excludes

No provider exact read, discovery, successor incarnation/currentness, effect,
new workflow fold, or second admission ledger.

## Confirmed expansion

DS2 proceeds serially. Completion of one task does not imply completion of the
Delivery Story:

1. **Petrus phased-delivery prerequisite — delivered.** Petrus `origin/main`
   contains exact commit `4e5c2500af4eb439e8e8f5ec108982c81bfc7427`
   (`feat(engine): split identified delivery into durable phases`). Hamsterdan
   does not consume that revision until task 4 first needs History acceptance.
2. **Signed webhook to durable HTTP custody — delivered.** One real ASGI
   request ends after new GitHub normalization and host-owned durable
   acquisition.
3. **Source-neutral readiness staging and classification — next planned.** Add
   the common snapshot/provenance projection, manifest, grant, and closed
   admission classifications outside the request.
4. **Bridge and identified History acceptance — planned.** Pin the delivered
   Petrus revision, map the accepted observation through the sole bridge, and
   qualify the distinct accepted and folded cuts.
5. **Retained fold, host completion, and process/DST qualification — planned.**
   Complete the cumulative tracer and its correspondence, crash, replay,
   checker-sensitivity, and resource evidence.

## Delivered task 2 contract

The task begins with exact raw ASGI headers and bytes and ends with one bounded
HTTP response. It does not open readiness, touch Petrus History, claim Dispatch,
run a Worker, call a provider API, invoke the bridge, or fold workflow state.

`github_app` owns strict provider identifiers and webhook models,
HMAC-before-parse verification through the installed GitHubKit boundary,
immutable `PullRequestSnapshot`, bounded `ObservationProvenance`, and exact
envelope normalization. `host` owns configured active-route binding, durable
inbox custody, acquisition identity `(ProviderRouteId, DeliveryId)`, monotonic
custody generation, receipt, collision quarantine, and FastAPI composition.

The snapshot retains only:

- immutable installation/repository/pull-request subject;
- exact head and base tips, each with repository ID, branch ref, and SHA;
- provider lifecycle state, draft, merged, and tri-state mergeability; and
- bounded diagnostic provider update time.

Event, action, and delivery ID belong to provenance. Branch policy, base
currentness, provider currency, arbitrary provider fields, and workflow
decisions are not inferred.

The durable acquisition outcomes are closed:

- first valid identity and canonical normalized content: `retained`;
- same route, delivery ID, and content: `exact_duplicate`, with no second row;
- same route and delivery ID with changed content: `quarantined`, with the
  original normalized evidence never overwritten and no readiness eligibility.

All three return HTTP 202 with the exact bounded receipt fields `custody`,
`provider_route_id`, `delivery_id`, `custody_generation`, and `disposition`.
The generation assigned by the first acquisition remains stable for every
redelivery. A collision and every later redelivery of a quarantined acquisition
return `quarantined`; HTTP receipt never claims workflow completion.

Transport and persistence are bounded: the raw body is at most 1 MiB; the raw
header block is at most 100 entries and 32 KiB; protected header values are
unique and at most 256 bytes; provider integer identifiers are in the positive
signed-64-bit range; branch evidence has explicit byte limits; normalized
provider timestamps are canonical UTC instants; normalized canonical content
is at most 16 KiB; and one custody store retains at most 10,000 acquisition
rows. Invalid HMAC, malformed or oversized request, duplicate protected header,
unsupported envelope, and unconfigured or mismatched route return HTTP 400 as
`{"refusal":"<closed_reason>"}`. Exhausted custody capacity returns the same
bounded shape with HTTP 503. Invalid raw input is never persisted.

The concrete route is `POST /github/webhooks`. A retained, duplicate, or
quarantined acquisition returns only the five documented receipt fields with
HTTP 202; a refusal returns only its closed reason. Neither response claims
later readiness or workflow completion.

SQLite retains only configured route identity, delivery identity, custody
generation, canonical normalized content and digest, disposition, and at most
one collision digest. It never retains raw body, signatures, secrets, arbitrary
headers, provider dictionaries, SDK objects, or unbounded diagnostics. A fresh
process can reconstruct the original normalized delivery and quarantine state.

## Acceptance

- exact duplicate, corroboration, collision, incomparable evidence, and refusal
  have closed finite outcomes;
- the HTTP response requires only durable host custody and never waits for a
  readiness fold, Dispatch claim, provider effect, or Worker;
- History is the sole workflow-admission ledger;
- same accepted input reaches the current Net exactly once across every named
  crash cut without old value leakage;
- bridge conversion does not add policy or provider provenance to semantic
  equality; and
- owner-local/root replay and mutation-sensitive checks prove the full path.

Task 2 alone does not satisfy this Delivery Story acceptance. Tasks 3–5 remain
required before DS2 can become `Completed` or receive a completion worklog.
