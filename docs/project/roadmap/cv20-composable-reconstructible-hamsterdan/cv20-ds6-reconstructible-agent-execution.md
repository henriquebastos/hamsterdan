---
code: CV20.DS6
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

# CV20.DS6 — Deliver reconstructible agent execution

## Outcome

Implement the credential-free typed request/result/terminal protocol, Pi
adapter and workspace, and submit→accept→result/cancel→delivery lifecycle with
retained lookup-first recovery and bounded cleanup.

## CV20 contract

This story owns the agent capability in [the architecture](architecture.md).
The canonical request/result/terminal values, deterministic execution identity,
durable lifecycle and coding runner port are specified in
[the API contract](api-contracts.md).

## Owned paths

```text
src/hamsterdan2/agents/protocol.py
src/hamsterdan2/agents/pi.py
src/hamsterdan2/agents/pi_workspace.py
tests2/behavioral/agents/**
tests2/integration/test_agent_execution.py
```

`agents/simulation` remains a placeholder until DS9. Readiness chooses and
invokes the coding capability in DS7; host owns process lifecycle in DS8.

## Fixed design

- Canonical `AgentRequest`/`AgentResult` families validate at construction and
  codec boundaries. No raw provider dictionary crosses the public port.
- Coding requests/results retain repository, operation, attempt, base/head and
  exact delivered-result evidence needed by readiness.
- Execution identity is a deterministic function of logical operation and
  attempt; retrying the same pair addresses the same durable execution.
- Lifecycle states are durable and reconstructible across submit, accepted,
  runtime-terminal and delivered positions.
- The runtime exposes accepted delivery as an exact typed value, not merely a
  status summary. Returned mutable collections are copied/revalidated.
- Pi is one adapter behind the provider-neutral runtime protocol. Pi naming or
  exceptions do not leak into sibling packages.
- Workspace/filesystem access is explicit, bounded and injected.
- Current-authority fencing occurs before provider execution and before result
  delivery where authority can move.
- Agent calls receive no GitHub App credential, installation token, webhook
  secret or transport object.
- Operations, terminals, retained bytes, runtime starts and deliveries are
  bounded and observable.

## Position and predecessors

Requires CV20.DS1 and may proceed in parallel with DS2–DS5.

## Implementation sequence

1. Rule canonical request/result/terminal and lifecycle APIs below.
2. Implement validated typed values and strict canonical codec round trips.
3. Implement deterministic execution identity and durable state transitions.
4. Implement the provider-neutral runtime protocol and exact delivered-result
   retrieval with copy isolation.
5. Implement bounded workspace/filesystem capability and Pi adapter.
6. Prove crash cuts at submission, provider terminal and accepted delivery;
   reconstruct from durable state without duplicate runtime start/delivery.
7. Prove cancellation, stale authority, malformed payload, resource overflow
   and credential-leak paths fail closed.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- canonical `AgentRequest`, `CodingRequest`, `AgentResult`, `CodingResult` and
  terminal field names/types;
- result status vocabulary and invariants for changed/unchanged results and
  canceled/fault terminal variants;
- operation/attempt-to-execution-ID function and serialized representation;
- runtime submit, lookup, step, cancel, timeout, deliver and delivered-result
  signatures;
- durable lifecycle state names and transition/error taxonomy;
- Pi adapter and workspace capability protocols, including cancellation/fence
  call shapes; and
- resource budget/inspection fields and copy-isolation guarantees.

Names may be improved as one vocabulary. Provider neutrality, stable identity,
exact delivered-result access, durability, bounds and secret exclusion are
fixed.

## Done condition

Logical operation plus attempt determines one stable Pi execution; response
loss at runtime or delivery recovers from retained typed state without a second
runtime start or accepted terminal; cancellation, timeout, and cleanup remain
closed typed outcomes; and no GitHub credential enters agent territory.

## Rollback

Remove `hamsterdan2.agents`; current host route selection and agent execution
remain unchanged.

## Validation

Run request/result/terminal codec, operation identity, credential-refusal,
workspace safety, real Pi protocol correspondence, runtime/delivery
response-loss, cancellation/timeout/cleanup, one-start, and one-delivery tests.

## Expansion boundary

Expand protocol, Pi/workspace, and durable lifecycle into independently green
Technical Stories before implementation. Record the accepted protocol in CV20
before DS7 and DS8 compose it.
