---
code: CV20.DS9
level: Delivery Story
status: Planned
status_reason: Waits for accepted CV20.DS8 and is not pulled
updated: 2026-08-28
related:
  - index.md
  - cv20-ds8-recover-timers-deferred-work.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
  - ../../decisions/records/2026-08-28T1113Z-dashboard-closure-converges-before-generation-close.md
---

# CV20.DS9 — Fence lifecycle and authority changes

## Outcome

Apply the complete authority model to every established observation and effect.
Draft/ready changes, head/base/policy movement, route/custody revocation,
closure/merge and true conflict are admitted through the real lifecycle;
protected work executes only under matching readiness grant, fresh provider
truth and fresh host evidence; stale work ends in workflow-declared outcomes.
Repeated bounded exact reads converge every registered nonterminal subject when
provider and route authority remain available.

## Vertical paths

```text
lifecycle delivery -> host custody -> readiness manifest -> real life fold
  -> detached draft/ready posture

closure/merge observation -> closing lifecycle plus terminal DashboardEvent
  -> reconcile one older publication -> final terminal DashboardPublication
  -> landed outcome -> generation close -> detached closed/merged posture

protected Activity -> durable grant + fresh provider read + fresh host evidence
  -> exact AuthorityClaim fence -> execute or workflow-declared blocked/moved

head/base/policy or route changes across the read/fence cut
  -> no stale effect -> original occurrence receives owned terminal
```

This tracer introduces the complete authority-policy dimension. It reuses the
existing provider, agent, Git and timer mechanisms.

## Component Technical Stories

1. Complete lifecycle observation/fold vocabulary for draft, ready, head/base,
   policy, closure, merge, dashboard convergence and conflict.
2. Extend the established readiness `AuthorityClaim` composition across the
   complete operation-specific policy matrix.
3. Implement host route/custody lifecycle generations and read-only evidence.
4. Add blocked/moved/conflict terminal mapping in readiness adapters.
5. Extend every local/root checker, authority counterexample, replay and
   provider/process correspondence.

## Initial owned paths

```text
src/hamsterdan2/workflow/net/{life,dashboard,readiness,mutation,review}.py
src/hamsterdan2/readiness/{authority,application,ports}.py
src/hamsterdan2/readiness/effects/** established adapters
src/hamsterdan2/host/{composition,instances,inspection}.py and route custody
src/hamsterdan2/github_app/{models,gateway,routing}.py
implemented owner-local/root simulation and tests
```

## Fixed design

- `AuthorityClaim` contains phase, incarnation, head, base and policy.
- DS9 alone owns lifecycle successor creation and increments local incarnation
  for complete close/reopen/merge movement. DS2's incarnation 1 remains a
  durable first-local-observation fact, never current-provider authority.
- `CurrentnessWitness` is DS9-owned and cut-specific: a confirming exact read
  plus unchanged pre/post `RouteGeneration` and `CustodyGeneration` around the
  admission/fence cut. It has no TTL and is never inferred from delivery ID,
  receipt time, provider update time or Git ancestry.
- Every registered nonterminal subject receives bounded exact-read
  reconciliation. The exact read uses DS4 mechanics and DS2's source-neutral
  snapshot/provenance → observation/key → manifest/admission seam.
- DS5 introduced this complete claim and its three-source composition for the
  first protected findings call site; DS6 and DS7 reuse it for mutation and
  rerun. This DS completes lifecycle movements and the safeguard matrix for
  every established operation instead of changing those earlier contracts.
- A protected effect is current only when the durable readiness grant agrees
  with a fresh provider read, host reports the same active route generation,
  same-subject custody has not moved across read/fence, and all semantic fields
  agree at the operation-specific authority point.
- Provider truth alone is insufficient; host cannot grant workflow authority;
  readiness owns composition and fail-closed classification.
- Mutation, findings and rerun retain strong current-authority cuts. Reply,
  reminder and dashboard retain their accepted weaker operation-specific
  safeguards; one generic fence does not silently change semantics.
- Route/custody revocation is host evidence. Readiness creates the
  workflow-declared blocked terminal; host never decodes Activity work.
- Head/base/policy movement under one operation cannot be accepted as an exact
  duplicate. It is stale authority or identity collision.
- Provider closure/merge observation and committed lifecycle-generation close
  are separate cuts. Observation makes the desired dashboard absorbingly
  terminal while the generation remains open only for reconciliation and its
  one final dashboard publication. No new unrelated work is claimed.
- Already accepted operations are reconciled by stable identity. After the
  final terminal dashboard publication lands, lifecycle commits generation
  close; then no new effects are claimed and late facts cannot reopen the
  dashboard.
- A terminal inability to land the final dashboard remains explicit retained
  failure. This DS rules the bounded operator-recovery or close policy rather
  than silently treating failure as alignment.
- Authority evidence and error output are bounded, typed and secret-free.

## API-strengthening checkpoint

Review the lifecycle and each operation-specific fence call tree and settle:

- lifecycle observation/closing/state/terminal and detached posture fields;
- final-dashboard convergence acknowledgement and terminal-inability policy;
- incarnation successor and cut-specific `CurrentnessWitness` values;
- any claim/current-authority capability extensions forced by new lifecycle
  call sites; the complete claim shape and three-source rule remain unchanged;
- host route/custody evidence, generation and read APIs;
- provider fresh-read values and read/fence transaction boundaries;
- per-operation authority matrix and blocked/moved/conflict terminal mapping;
- unavailable/stale/revoked/collision/closed error taxonomy;
- read, grant, route-change, effect-claim and terminal cuts; and
- evidence age/call/row/byte, generation, retained blocker and artifact limits.

Numeric limits, exact call signatures, payload fields and refusal shapes remain
fixture-calibrated Plan refinements with −1 / limit / +1 evidence.

Write the ruled matrix and signatures into [the API contract](api-contracts.md).
Three-source authority, operation-specific safeguards, readiness-owned mapping
and fail-closed movement are fixed.

## Tracer acceptance

Run complete vertical schedules for draft→ready, stale base update, policy/head
movement, route revocation, true conflict, collaboration approval and PR close/
merge. Close/merge proves closure observation, older-operation reconciliation,
one final terminal dashboard publication and generation close as distinct
ordered cuts. Each begins with provider/host input and ends in workflow-owned
posture or typed terminal, with no stale physical effect.

Inject movement at every read/fence cut and assert the exact owning local or
cross checker, stable operation behavior and physical effect count. Crash after
grant/read/claim/accepted effect/terminal; reconcile accepted work without
duplication. Require exact replay, lowered authority/retention budgets and real
provider fresh-read, route-generation and process-restart correspondence.

## Done condition

Every established effect is fenced by its explicit policy and every lifecycle
movement reaches a real typed outcome. A standalone `AuthorityClaim` test or
generic fence cannot close this DS.

## Stop conditions

Stop if any effect uses provider truth alone, host fabricates workflow outcomes,
one generic policy changes weaker operations, route generation is not fresh,
generation close can overtake final dashboard convergence, closed subjects
claim new work, or stale identity is treated as retryable.

## Rollback

Remove the complete-policy/lifecycle growth and fresh generation state. DS8's
timer and earlier current-authority happy paths remain; current production is
unchanged.

## Validation

Run all lifecycle schedules, operation-specific authority matrix, every
read/fence movement and crash cut, no-stale-effect physical counts, local/cross
sensitivities, known-subject exact-read convergence, exact replay, every limit at
−1 / limit / +1, provider/route/process/DST correspondence, secret scans and
project gates.

## Expansion boundary

Expand by one lifecycle behavior or operation-specific policy at a time. Keep
the DS open until the portfolio proves the same three-source authority model at
the real composed effects, not merely in an isolated policy component.
