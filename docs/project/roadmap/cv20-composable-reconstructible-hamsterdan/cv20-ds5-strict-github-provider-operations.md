---
code: CV20.DS5
level: Delivery Story
status: Planned
status_reason: Waits for CV20.DS1 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds1-replacement-tree-gate.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS5 — Deliver strict GitHub provider operations

## Outcome

Implement provider-owned models, App authentication/configuration, bounded
transport and gateway calls, route/webhook verification and persistence
mechanisms, and lookup-first comment/rerun/Git operations. Durable route/inbox
custody stays with host, and readiness classification does not enter the
provider package.

## CV20 contract

This story owns the GitHub capability described in
[the architecture](architecture.md): provider protocol, typed transport,
lookups, effects, errors and retained provider facts. The complete gateway and
lookup-first operation contracts are in [the API contract](api-contracts.md).

## Owned paths

```text
src/hamsterdan2/github_app/models.py
src/hamsterdan2/github_app/auth.py
src/hamsterdan2/github_app/config.py
src/hamsterdan2/github_app/transport.py
src/hamsterdan2/github_app/gateway.py
src/hamsterdan2/github_app/routing.py
src/hamsterdan2/github_app/webhooks.py
src/hamsterdan2/github_app/effects.py
tests2/behavioral/github_app/**
tests2/integration/test_github_provider.py
```

`github_app/simulation` remains a placeholder until DS9. Host route/webhook
custody and readiness Activity binding remain outside this story.

## Fixed design

- Webhook signature verification operates on raw bytes before JSON parsing.
- Transport owns authentication, request/response typing, pagination and rate
  classification; domain callers do not exchange raw provider dictionaries.
- `GitHubGateway` is the public capability consumed by readiness/host
  composition. It exposes typed reads, lookups and effects.
- Every externally mutating operation has stable operation identity, performs
  lookup before retry, fences current authority and allows at most one provider
  mutation attempt per bounded step.
- Accepted-effect lookup is based on provider-observable identity/markers, not
  an in-memory “already called” flag.
- Errors are closed and classified as retryable, provider-refused/permanent,
  stale-authority or protocol/correlation failures.
- Retained installation, authority, read, pending and accepted-effect state is
  byte/record bounded and measurable.
- GitHub credentials/tokens never enter agent values, calls, stores, artifacts
  or logs.
- This package does not import readiness, agents or host implementations.

## Position and predecessors

Requires CV20.DS1 and may proceed in parallel with DS2–DS4 and DS6.

## Implementation sequence

1. Rule public model, transport, gateway, operation and error APIs below.
2. Implement immutable validated provider/webhook values and raw-byte signature
   verification.
3. Implement typed transport, auth, pagination and classified failure mapping.
4. Implement provider lookups and effect requests/results with stable operation
   markers.
5. Implement `GitHubGateway`, retained route/webhook mechanisms and bounds.
6. Prove lookup-first response-loss recovery and one-attempt-per-step across all
   mutating capabilities.
7. Prove stale authority, secret isolation and provider payload/schema drift
   fail closed.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- webhook envelope, delivery identity and normalized event names/fields;
- `GitHubGateway` constructor and each read/lookup/effect signature;
- transport request/result, pagination and rate-limit value shapes;
- stable marker representation for accepted-effect lookup by capability;
- installation/PR authority claim and fence values;
- the closed GitHub error taxonomy and retry metadata; and
- retained-state budget keys, eviction rules and inspection surface.

The checkpoint may improve names and split capabilities for clarity. Raw-byte
verification, lookup-first recovery, current-authority fencing, one-attempt
cardinality and credential isolation are fixed.

## Done condition

Every provider request has finite row/page/byte/call/time bounds; complete
lookup precedes mutation; one step makes no more than one mutation attempt;
accepted-hidden outcomes recover later through lookup; and provider credentials
remain outside workflow and agents.

## Rollback

Remove `hamsterdan2.github_app`; the current provider implementation remains
installed and authoritative.

## Validation

Run behavioral auth/config/transport/effect tests, SDK mock-transport
integration, bounded pagination/rate-limit classifications, authority/content
collision cases, accepted-hidden response loss, and no-second-POST checks.

## Expansion boundary

Expand into behavior-sized provider custody and operation stories. Any real
provider mutation requires a separate explicit approval and bounded fixture.
Record the accepted capability API in CV20 before DS7 and DS8 consume it.
