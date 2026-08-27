---
code: CV20.DS5
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS4 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds4-settle-github-activity.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS5 — Settle one reconstructible agent round

## Outcome

Deepen the same PR lifecycle through one workflow-declared review round. The
real workflow emits `RoundOpen`; readiness projects one credential-free review
request; host routes it to the configured agent runtime; the exact retained and
accepted typed result is delivered once; and `AgentReview` returns to the
original workflow occurrence after restart-safe lookup.

## Vertical path

```text
retained PR observation and settled dashboard
  -> real workflow review fold -> RoundOpen Activity
  -> readiness exact AgentRequest projection
  -> host operation route and agent runtime custody
  -> agents submit -> accept -> terminal -> deliver lifecycle
  -> exact delivered AgentResult lookup
  -> readiness AgentReview terminal admission
  -> original workflow occurrence and changed posture
```

This tracer introduces one agent execution family, not mutation publication.

## Component Technical Stories

1. Implement credential-free immutable review request/result/terminal codecs.
2. Implement deterministic execution identity and durable agent lifecycle.
3. Implement bounded workspace and Pi adapter behind the provider-neutral port.
4. Add host Pi installation/runtime/route/secret custody.
5. Implement the readiness-owned complete `AuthorityClaim` and the strong
   current-authority policy required before findings work starts.
6. Implement workflow review round plus readiness request/terminal adaptation.
7. Extend all affected local/root simulations, checkers and correspondence.

## Initial owned paths

```text
src/hamsterdan2/agents/{protocol,pi,pi_workspace}.py
src/hamsterdan2/host/agents/{routing,pi}.py
src/hamsterdan2/readiness/authority.py
src/hamsterdan2/readiness/custody/review.py
src/hamsterdan2/readiness/effects/{agents,review}.py
src/hamsterdan2/workflow/net/review.py
implemented owner-local/root simulation and tests
```

## Fixed design

- Agent values contain no GitHub credential, provider client, webhook payload
  or workflow/runtime object.
- Logical operation plus attempt deterministically identifies one execution:
  `pi:sha256(logical_operation + "\0" + attempt)`.
- Durable positions are submit, accepted, runtime result/cancellation available
  and receiver delivered. Runtime and delivery lookup precede retries.
- One logical operation/attempt has at most one runtime start and one accepted
  receiver terminal.
- Delivered lookup returns a freshly validated exact typed request/result, not
  a summary. Mutable collections are copy-isolated.
- Readiness derives the request and terminal classification; host owns concrete
  runtime/route/secret lifetime; agents own protocol and execution state.
- Findings work starts only under the complete readiness-owned claim over the
  durable grant, a fresh provider read and fresh host route/custody evidence.
  DS5 rules the claim's complete shape and the first strong policy from this
  real call site; DS9 later completes the operation-policy and lifecycle matrix
  rather than retrofitting baseline authority onto already accepted tracers.
- Cancellation, timeout and cleanup failure are closed typed terminal variants
  and remain reconstructible.
- Every workspace, prompt, result, runtime, retained-terminal and cleanup path
  has explicit byte/call/time/count bounds.

## API-strengthening checkpoint

Review the exact `RoundOpen`→delivery→`AgentReview` call tree and settle:

- review request/result fields, terminal envelope and codec API;
- logical operation/attempt grammar and execution-ID representation;
- submit/lookup/step/cancel/timeout/deliver/delivered signatures and states;
- workspace/Pi call and host route APIs;
- complete claim/factory/evidence signatures and the findings authority fence;
- readiness projection/classification and original-occurrence admission;
- cancellation/timeout/cleanup/schema/identity error taxonomy; and
- one-start/one-delivery, retained-byte, workspace and artifact evidence limits.

Write the complete ruled protocol into [the API contract](api-contracts.md).
Provider neutrality, stable execution identity, exact delivered value, secret
exclusion and original-occurrence return are fixed.

## Tracer acceptance

Given the admitted PR lifecycle, when review work becomes eligible, then the
real workflow emits one `RoundOpen`, one stable agent execution starts, one
exact typed result is delivered and one `AgentReview` folds at the original
occurrence. Response loss after runtime acceptance or receiver delivery
reconstructs through retained lookup without another start or delivery.

Acceptance includes cancellation/timeout/cleanup paths, result/request/route
substitution cross sensitivities, local checker counterexamples, exact replay,
lowered runtime/workspace/retention limits, physical start/delivery counts,
provider-neutral Pi codec/workspace correspondence and authenticated Pi only
when separately approved.

## Done condition

The agent round is causal and reconstructible across all production owners.
Standalone protocol/runtime tests do not close the DS without the original
workflow request and fold.

## Stop conditions

Stop if GitHub credentials enter agents, execution identity changes on retry,
delivery exposes only status, readiness invokes a second implementation, host
interprets workflow meaning, or restart relies on a live process/result object.

## Rollback

Remove agent/runtime/review-loop growth and fresh route/execution state. DS4's
GitHub-only tracer remains accepted; current production is unchanged.

## Validation

Run strict codecs, workspace safety, one-start/one-delivery cuts, cancellation/
timeout/cleanup, authority and identity failures, original-occurrence folding,
local/cross sensitivity, exact replay, bounds, Pi/workspace correspondence,
credential scans and project gates.

## Expansion boundary

Protocol, runtime, workspace, host custody and workflow adaptation are Technical
Stories. Keep the DS open until the exact retained agent result traverses the
real composed request/return path.
