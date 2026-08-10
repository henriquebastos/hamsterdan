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

## Change Requests

| Change Request | Outcome |
| --- | --- |
| CR-001 Characterize behavior and map state ownership | Complete |
| CR-002 Establish Pydantic workflow contracts | Complete |
| CR-003 Close domain vocabularies | Complete |
| CR-004 Specialize Activity requests and results | Complete |
| CR-005 Simplify explicit conversational mutations | Complete |
| CR-006 Compare active-token decomposition strategies | Complete |
| CR-007 Replace `Control` with independent state tokens | Active |
| CR-008 Make dashboard and readiness projection relational | Candidate |
| CR-009 Reduce retirement to proven invariants | Candidate |
| CR-010 Restructure the Net around workflow continuity | Candidate |
| CR-011 Review, coherence, and documentation | Candidate |

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
