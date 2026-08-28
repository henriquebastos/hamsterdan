# DS6 concept extraction

## Source

- Delivery Story: [`../cv20-ds6-publish-causal-mutation.md`](../cv20-ds6-publish-causal-mutation.md)
- Cross-boundary contracts: [`../api-contracts.md`](../api-contracts.md),
  "Mutation causal contract", "Conversation classification", "Exact delivered
  result" and "Lookup-first provider effect"
- Cumulative sequence: [`../delivery-sequence.md`](../delivery-sequence.md),
  "DS6 — One causal mutation"

Reviewed source revision: 2026-08-28 working tree.

## Extracted behavior

DS6 turns an authorized human change comment into one workflow-owned mutation
work value. Readiness projects that exact work into a coding request; the exact
accepted agent-delivered coding result enters bounded lookup-first Git
publication; and a typed publication result closes the original occurrence.
Operation identity, authority and the delivered-result digest preserve the
causal relationship across restart and provider ambiguity.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| Outcome, lines 18–24 | Authorized conversation produces exact workflow work, exact coding result and one typed publication return | authorized conversation, mutation work, causal mutation |
| Vertical path, lines 26–37 | Provider/host/readiness/workflow/agent/Git values form one explicit causal chain | coding request, delivered coding result, Git publication, provisional head |
| Fixed design, lines 65–84 | Workflow owns `MutWork`; readiness preserves exact projection/result; Git is bounded, fenced and lookup-first; terminal must match original work | mutation causal chain, result sensitivity, exact-head ref CAS |
| Acceptance, lines 104–122 | A/B result and work substitutions must change only their causal outputs; unchanged result has no publication | causal dependency rather than co-mounted mechanics |
| API contracts / Mutation causal contract, lines 290–318 | `MutWork` semantics and workflow→coding→Git→workflow flow are fixed | mutation work and causal mutation are enduring candidates; concrete value names are fixed APIs |
| API contracts / Conversation classification, lines 389–399 | Authorized/unauthorized comment classification is frozen before workflow admission under current authority | conversation classification; authorized conversation observation |
| API contracts / Exact delivered result, lines 711–720 | Readiness cannot substitute another coding implementation or equal result | exact delivered result refined from DS5 |
| API contracts / Lookup-first provider effect, lines 636–644 | Git owns patch admission, lookup, trailers, objects and expected-head CAS; result digest affects evidence | Git publication as specialized lookup-first effect |
| Delivery sequence / DS6, lines 199–206 | DS6 hands off the accepted workflow→agents→Git→workflow causal vertical | causal mutation survives into repair reuse |

## Later ownership and refinements

- DS7 reuses the same agent/mutation/Git chain for persistent CI regression and
  requires every repair head to return through `Pushed` before exact-head CI
  evidence (DS7 Vertical paths, lines 34–36; Fixed design, lines 69–72).
- DS9 completes lifecycle and operation-specific authority for mutation while
  preserving the full claim introduced in DS5 (DS9 Fixed design, lines 79–93).
- DS12 qualifies conversational change, agent repair, persistent regression and
  accepted-hidden Git recovery as portfolio journeys/overlays (DS12 named
  journeys, lines 71–83).
- DS13 removes generation labels but preserves externally accepted operation
  meanings used for provider lookup and idempotency (replacement ledger /
  Removed names, schemas and artifacts, lines 438–457).

## Subordinate vocabulary to evaluate

- `MutWork`, `CodingRequest`, `CodingResult` and `Pushed` are fixed cross-boundary
  API names; the analysis should not equate each class name with a concept.
- operation key, lineage, run ID and attempt are fields of mutation identity.
- declined, blocked, moved and fault are terminal variants within mutation
  settlement.
- patch admission, operation trailers, object creation, result digest and ref
  CAS are subordinate Git-publication vocabulary.
- provisional head may be a workflow fact within the causal chain rather than a
  standalone concept.

## Unresolved DS-review items

- conversation task, actor, association and authorization observation shapes;
- immutable mutation/coding/publication value fields;
- request projection, delivered-result lookup and coding capability APIs;
- patch admission, result digest, Git proof/object/ref-CAS APIs;
- mutation operation grammar, claim/fence and collision semantics;
- terminal/error names and response-loss evidence; and
- calibrated request, result, patch, repository, History and artifact limits.

## Construction-only exclusions

- A/B substitutions, checker violations, physical counts and local-Git/provider
  correspondence are evidence mechanics, not finished-system concepts.
- `hamsterdan2` paths and the replacement-versus-current framing end at DS13.

## Trace handoff

The DS7–DS13 trace is complete in the
[candidate register](candidate-register.md). Whether authorized conversation
and provisional head merit standalone terms remains for Navigator review.
