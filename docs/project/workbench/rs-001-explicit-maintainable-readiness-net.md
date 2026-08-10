---
status: Active
pulled: 2026-08-09
navigator: Henrique
---

# RS-001 — Make the PR-readiness Net explicit and maintainable

## Existing field being refined

Hamsterdan's durable PR-readiness workflow currently coordinates through one
large `Control` token, generic dictionary-backed `Work` and `EffectResult`
envelopes, and open string vocabularies. Petrus provides durable Petri-Net
execution, but much of the workflow is expressed as a reducer-style state
machine inside that aggregate token.

## Refinement boundary

Refactor the existing workflow so independently evolving facts are represented
by independently addressable Petri-Net tokens, Activities use validated
specialized contracts, and the topology communicates workflow continuity.
Preserve current product behavior except for one accepted conversational
change: an explicit, unambiguous mutation instruction from an authorized human
executes without a second confirmation comment; ambiguous instructions request
clarification without mutation.

Existing durable History is disposable during this pre-use design phase. No
compatibility decoder, migration, dual Net, or legacy token shape is required.
Current-authority fencing, operation identity, provider isolation, lookup-first
recovery, restart behavior under the new schema, and the rule that Hamsterdan
never merges remain required.

## Progress

### 2026-08-09 — Validated contracts and direct mutation authorization

- Net-bound values are strict, frozen Pydantic dataclasses with forbidden extra
  fields and JSON-faithful serialization. The host owns Petrus conversion so
  typed Activity binding and runtime validation remain one contract.
- Existing workflow state, result, and intent vocabularies are closed with
  literal alternatives. Generic `Work.kind` and `EffectResult.kind` remain only
  until CR-004 replaces those envelopes with specialized contracts.
- Explicit authorized mutation instructions execute in one conversation cycle;
  ambiguous requests clarify without coding. Pending-confirmation state and
  protocol fields were removed while current-authority fencing remains.
- CR-006 selected one centralized `Authority` token plus independent concern
  tokens as the implementation route. Mutable authority will not be duplicated
  across concern tokens; full-cohort movement is reserved for generation and
  lifecycle boundaries.

### 2026-08-09 — Specialized Activity contracts

- Every readiness Activity now has one exact strict request/result pair. The
  generic `Work.kind`/`payload` and `EffectResult.kind` envelopes were removed.
- The Net exposes distinct typed work and result places; host methods consume
  typed fields directly and nominal result classes determine effect folding.
- Operation hashes and coding publication identities retain their established
  payload projections, while same-generation superseded result tokens are
  explicitly retired.

### 2026-08-09 — Established the concern-state partition

- The six strict token contracts now assign every aggregate field to exactly
  one owner: authority, Actions, review, human, mutation, or publication.
- `ReadinessSnapshot` projects those independent values and derives `wait`;
  parity tests prove the split preserves representative aggregate behavior.
- `Control` remains temporarily in the running Net only until the topology and
  host migrate to the proven contracts; CR-007 remains active.

### 2026-08-10 — Replaced the aggregate control token

- The active marking now holds exactly one `Authority`, `ActionsState`,
  `ReviewState`, `HumanState`, `MutationState`, and `PublicationState` token.
  No `Control` class, token color, or `current` place remains.
- Routine transitions read centralized authority and consume only the concerns
  they mutate. Full-cohort movement is limited to generation and lifecycle
  boundaries; host observation joins a strict derived `ReadinessSnapshot`.
- Current-authority fencing reads only local authority and mutation state before
  provider checks. Partial or duplicate active cohorts fail loudly.
- Publication revision remains a deliberate temporary serialization point for
  dashboard invalidation; CR-008 now owns removing that coupling.

### 2026-08-10 — Made dashboard projection currency relational

- Global revision and imperative dashboard invalidation are gone. Dashboard
  currency is derived by comparing the current concern-facts digest with the
  exact projection acknowledged by publication.
- Dashboard requests bind that projection into their operation identity. A
  late success acknowledges only its original projection, so concern changes
  during publication leave the dashboard stale and eligible for a fresh update.
- Routine Actions, human, review-intent, and mutation transitions no longer
  consume publication state solely to invalidate a dashboard. Publication
  remains an owner only where publication facts or leases actually change.
- Human reconciliation now owns an observation sequence for durable delivery
  identity. Repeated reversible authority edges survive replay without
  restoring the removed global revision; that lineage is excluded from the
  rendered projection digest.
- Capability-denied dashboard and readiness leases remain fenced but do not yet
  have an automatic recovery trigger. CR-010 will resolve that inherited
  workflow-continuity gap without introducing an immediate retry loop.

### 2026-08-10 — Reduced retirement to distinct invariants

- Retirement now distinguishes inactive-cohort absorption, generic authority
  staleness, and concern-owned operation supersession instead of applying all
  three mechanically to every transient place.
- Specialized result and intent/basis guards own stale and same-generation
  superseded cleanup where their predicates already partition acceptance from
  retirement. Generic authority cleanup remains only for unowned observations,
  staged Actions basis, timers, and Activity work.
- Twelve redundant stale transitions were removed. Remaining generated
  retirement transitions are named after their place rather than numeric tuple
  position, so topology inspection identifies the residue being absorbed.
- Behavioral regressions cover stale Actions results and conversation bases;
  dormant and terminal absorption remains complete for every transient place.

### 2026-08-10 — Made publication continuity explicit in the Net

- Dashboard and readiness publication now carry separate exact lease tokens.
  A failed Activity moves its lease through a durable five-minute Delay and
  reissues the byte-identical request under the same operation identity.
- Delay maturity depends only on the retry token. Reissue then rejoins current
  authority and publication ownership, so unrelated publication changes cannot
  reset the retry clock and stale basis/lifecycle leases cannot execute.
- Lease authority includes epoch, head, base, policy, operation, and requested
  state. Same-head basis replacement and operation supersession retire active,
  waiting, and matured continuity tokens before they can reactivate.
- Typed ingress, Activity boundaries, concern folding, conversation fan-out,
  projection publication, timers, lifecycle, and retirement are now called out
  directly in topology order. No additional subnet wrapper layer was added:
  the existing contiguous Petri DSL is simpler to trace than one-use builders.
- Topology hydration now uses one strict Pydantic JSON-validation path for all
  token colors; malformed new-schema History fails rather than degrading into
  partially hydrated compatibility values.

## Change Requests

| Change Request | Outcome |
| --- | --- |
| CR-001 Characterize behavior and map state ownership | Complete |
| CR-002 Establish Pydantic workflow contracts | Complete |
| CR-003 Close domain vocabularies | Complete |
| CR-004 Specialize Activity requests and results | Complete |
| CR-005 Simplify explicit conversational mutations | Complete |
| CR-006 Compare active-token decomposition strategies | Complete |
| CR-007 Replace `Control` with independent state tokens | Complete |
| CR-008 Make dashboard and readiness projection relational | Complete |
| CR-009 Reduce retirement to proven invariants | Complete |
| CR-010 Restructure the Net around workflow continuity | Complete |
| CR-011 Review, coherence, and documentation | Active |

## Standing execution authorization

The Navigator approved this Refinement Story and authorized autonomous execution
through its Change Requests. The Driver stops only for a consequential unresolved
product or architecture decision, a safety-boundary conflict, materially changed
scope, an external authority action, or a validation blocker that changes the
route. Final Experience Report, refinement review/coherence, and history action
remain explicit checkpoints.

## Validation contract

- Focused behavioral checks close each Change Request.
- `scripts/check quick` follows each coherent implementation stage.
- `scripts/check full` is required before the Experience Report.
- Fresh-Engine restart/replay, token cardinality, late-result retirement,
  conversation mutation, current-authority fencing, and lookup-first recovery
  remain explicit regression boundaries.
