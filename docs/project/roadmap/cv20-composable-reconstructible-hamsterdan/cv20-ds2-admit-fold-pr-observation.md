---
code: CV20.DS2
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS1 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds1-first-bounded-pr-lifecycle.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS2 — Admit and fold one PR observation

## Outcome

Deepen the DS1 lifecycle with one real inbound observation. A bounded raw
GitHub pull-request webhook is verified and normalized by `github_app`, retained
under host delivery custody, staged by readiness as an immutable manifest/grant,
accepted into History, folded by the real workflow, reflected in detached
posture and acknowledged by host only after readiness reports acceptance.

## Vertical path

```text
bounded raw webhook bytes
  -> github_app signature verification and typed normalization
  -> host durable inbox and subject route
  -> readiness ingress manifest plus grant
  -> real workflow HeadSeen admission and lifecycle fold
  -> changed detached StepResult/WorkPosture
  -> host exact-delivery acknowledgement and posture record
```

After acceptance, one real PR head/base observation changes workflow state and
is recoverable at every custody cut. No Activity or external mutation occurs.

## Component Technical Stories

1. Add provider-owned webhook/config/model values and raw-byte verification.
2. Add host route and durable inbox custody for one subject/delivery.
3. Add readiness ingress manifest/grant storage and bounded admission cuts.
4. Add workflow `HeadSeen` vocabulary and the lifecycle fold that consumes it.
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
- Host owns delivery/route custody; readiness owns manifest/grant and workflow
  admission; workflow owns the observation and fold meaning.
- Delivery identity and door/route identity stay outside `HeadSeen` and are
  retained in the ingress manifest.
- One ingress call performs one named bounded cut: stage, accept one entry, fold
  one entry, acknowledge one delivery or record posture.
- Exact duplicate delivery returns accepted/already accepted for the original
  delivery. Conflicting content under one identity fails closed.
- Host acknowledges only after readiness returns accepted/already accepted for
  that exact delivery.
- Reconstruction uses durable inbox, manifest/grant and History state, never a
  parsed request object or returned fold value.
- The observation and posture have strict codecs and byte/record limits.

## API-strengthening checkpoint

Review the exact raw-webhook→fold call tree and settle:

- webhook envelope, provider route, delivery and subject value shapes;
- normalized head/base/policy/mergeability fields and `HeadSeen` name/fields;
- host retain/route/acknowledge and readiness stage/admit calls;
- manifest/grant schema, duplicate/collision errors and acknowledgement result;
- `ingress_staged`, `ingress_entry_accepted`, `ingress_entry_folded` and
  `delivery_acknowledged` cut payloads;
- provider/host/readiness/workflow observations, local/cross report fields and
  row/page/body/journal/artifact limits; and
- unresolved API/error names visible at the real call sites.

Record the ruled signatures in [the API contract](api-contracts.md). Ownership,
raw-byte verification, immutable staging, exact duplicate behavior and
acknowledgement order are fixed.

## Tracer acceptance

Given one valid signed pull-request delivery for the DS1 subject, when host
processes bounded work, then the exact normalized `HeadSeen` reaches the real
workflow fold, readiness returns accepted posture and host acknowledges the
same delivery. Invalid signatures, wrong subjects and content collisions fail
before workflow admission.

Acceptance also proves:

- crash/reopen after inbox retention, manifest/grant commit, History acceptance,
  fold and returned posture, with one final acknowledgement;
- a composition-only observation or delivery substitution leaves every local
  checker green and fails exactly the responsible cross edge;
- exact replay from fresh modules and lowered input/row/page/history budgets;
- provider, host, readiness and workflow resource peaks; and
- real raw-byte signature, typed normalization and fresh SQLite/filesystem
  correspondence.

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
every named crash cut, duplicate/collision checks, local/cross sensitivities,
exact replay, lowered bounds, mock-transport/fresh-storage correspondence,
secret scans and project gates.

## Expansion boundary

Expand by custody owner, but retain one vertical acceptance artifact. Do not
accept “provider observation implemented” or “workflow fold implemented” as
Delivery until the same real value traverses all owners and host acknowledges it.
