---
code: CV20.DS6
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS5 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds5-settle-agent-round.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS6 — Publish one causally aligned mutation

## Outcome

Complete the first mutation vertical. One authorized human change comment is
normalized and admitted; the real workflow classifies it and declares exact
`MutWork`; readiness projects one `CodingRequest`; the exact accepted delivered
`CodingResult` from agents reaches Git publication; and one typed `Pushed`
returns to the original workflow occurrence after lookup-first crash recovery.

## Vertical path

```text
signed authorized change comment
  -> provider normalization, host custody, readiness frozen classification
  -> real conversation/mutation folds -> exact MutWork and occurrence
  -> canonical CodingRequest and stable agent operation
  -> exact retained/delivered CodingResult
  -> readiness patch admission and Git object/ref-CAS publication
  -> provider-observable operation trail plus Pushed
  -> original MutWork occurrence -> workflow provisional head/posture
```

DS4 established GitHub publication mechanics and DS5 established agent
execution. This tracer introduces one cross-owner causal chain; it does not
introduce a second coding implementation or carry agent results in `MutWork`.

## Component Technical Stories

1. Add authorized conversation normalization/classification and immutable
   manifest evidence.
2. Implement conversation/mutation workflow folds and exact `MutWork` identity.
3. Add coding request/result protocol variants to the existing agent lifecycle.
4. Implement readiness mutation coordination and patch admission.
5. Implement bounded Git object/trailer/lookup/ref-CAS publication.
6. Extend local/root simulation, causal checkers, A/B sensitivity and Git
   correspondence.

## Initial owned paths

```text
src/hamsterdan2/workflow/net/{conversation,mutation}.py
src/hamsterdan2/readiness/effects/{agents,mutation,git}.py
src/hamsterdan2/agents/protocol.py
src/hamsterdan2/github_app/{gateway,effects,models}.py
src/hamsterdan2/host/composition.py
implemented owner-local/root simulation and tests
```

## Fixed design

- `MutWork` is workflow-owned and contains operation, operation key, head,
  base, policy, incarnation, lineage, kind, instruction, run ID and attempt. It
  contains no `CodingResult`.
- Conversation identity is
  `conversation:{repository}:pr:{number}:delivery:{delivery_id}`. Mutation agent
  identity is `mutation:{repository}:pr:{number}:{MutWork.op_key}`. Git uses the
  exact `MutWork.op_key`.
- Readiness projects the exact workflow work once and validates repository,
  operation, attempt and full request when retrieving the delivered result.
- The delivered value—not a reconstructed equal value—enters publication.
  Canonical result digest affects accepted publication evidence/head.
- Patch admission, complete first-parent lookup, operation trailers, object
  creation and exact expected-head ref CAS are bounded and lookup-first.
- Current-authority fence runs before agent acceptance and Git mutation.
- Response loss after ref acceptance records no local success authority. The
  next generation looks up before agent or publication work.
- `Pushed.op_key` and expected head must match publication and the original
  Activity occurrence before History accepts it.

## API-strengthening checkpoint

Review the complete comment→mutation→fold call tree and settle:

- conversation task/comment/actor/association and authorized/unauthorized
  observation values;
- immutable `MutWork`, `CodingRequest`, `CodingResult` and `Pushed` fields;
- request projection, delivered-result lookup and coding capability signatures;
- patch admission, result-digest schema, Git proof/object/ref-CAS APIs;
- operation grammars, authority claim/fence and collision semantics;
- declined/blocked/moved/fault terminal names and owner-specific errors;
- response-loss cuts and physical agent/Git observations; and
- request/result/patch/repository/history/artifact resource limits.

Record the ruled API in [the API contract](api-contracts.md). Exact causal value
flow, ownership, lookup-first CAS, result sensitivity and original-occurrence
closure are fixed.

## Tracer acceptance

Given one authorized change comment on the current head, when bounded work runs,
then the exact History-declared `MutWork` produces the agents request, the exact
accepted delivered `CodingResult` produces one Git publication, and the
resulting `Pushed` closes the original occurrence.

Acceptance requires:

- A/B changes only one valid `CodingResult` field while work/request/payload
  stay equal and publication result digest/head change;
- composition-only `MutWork.instruction` substitution leaves all local checkers
  green and reports exactly the workflow→composition violation;
- unchanged delivered result yields `DeclinedM` and no Git publication;
- response loss after ref acceptance, generation-2 lookup first, no second
  agent/runtime/publication and one final workflow fold;
- exact replay, physical counts and lowered bytes/rows/calls/attempts; and
- real local-Git object/ref-CAS/trailer/lookup correspondence plus separately
  approved provider/Pi evidence when available.

## Done condition

The causal vertical and both sensitivities pass through production owners. Equal
fixtures, co-mounting, terminal singularity without physical effect count, or
separately green agent/Git tests cannot close the DS.

## Stop conditions

Stop if composition/readiness authors workflow work, readiness creates a second
agent result, publication is insensitive to the exact delivered result, Git
retries without complete lookup, or `Pushed` can close another occurrence.

## Rollback

Remove conversation/mutation/coding/Git growth and fresh state. DS5 review
rounds and DS4 dashboard publication remain accepted; current production stays
unchanged.

## Validation

Run conversation/authority/workflow tests, coding exact-result and copy-isolation
tests, Git patch/object/ref-CAS behavior, both cross sensitivities, unchanged/no-
effect behavior, every response-loss cut, one-start/one-delivery/one-publication
counts, exact replay, bounds, Git correspondence, secret scans and project gates.

## Expansion boundary

Conversation, workflow mutation, coding protocol and Git publication are
Technical Stories around one accepted causal chain. Do not close the DS at an
intermediate “agent result delivered” or “commit published” milestone.
