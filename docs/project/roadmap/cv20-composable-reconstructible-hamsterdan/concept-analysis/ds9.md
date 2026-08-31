# DS9 concept extraction

## Source

- Delivery Story: [`../cv20-ds9-fence-lifecycle-authority.md`](../cv20-ds9-fence-lifecycle-authority.md)
- Authority contracts: [`../api-contracts.md`](../api-contracts.md), "Authority
  claim", "Authority capability", "Operation-specific authority" and
  "Lifecycle evidence"
- Observation model: [`../architecture.md`](../architecture.md), "Observation
  and recovery language"

Reviewed source revision: 2026-08-28 working tree.

## Extracted behavior

DS9 completes pull-request lifecycle movement and current-authority fencing.
Readiness combines its durable grant, a fresh exact provider read and fresh host
route/custody evidence for the operation-specific authority point. A
cut-specific currentness witness proves that route and custody did not move
around that read and cut. Lifecycle successors receive a new local incarnation.
Stale protected work ends through a workflow-declared blocked, moved or conflict
outcome, while repeated bounded exact reads converge registered nonterminal
subjects.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| Outcome, lines 18–26 | Lifecycle movements and protected effects share a complete three-source authority model | lifecycle, authority claim, current authority |
| Vertical paths, lines 28–39 | Lifecycle admission, authority fencing and movement during a fence have distinct outcomes | authority fence, stale work |
| Fixed design, lines 66–98 | Incarnations, cut-specific currentness, known-subject reconciliation and operation-specific policies are fixed | incarnation, currentness witness, lifecycle authority, reconciliation |
| Tracer acceptance, lines 122–133 | Every lifecycle schedule must end in workflow posture or terminal with no stale physical effect | final behavior survives; schedules and effect counts are qualification evidence |
| API contracts / Authority capability, lines 401–416 | Current authority uses fresh three-source composition; a witness is cut-specific and has no TTL | authority claim is refined; currentness witness is a likely subordinate proof value |
| API contracts / Shared step result, lines 467–493 | Terminal posture gains lifecycle generation and closed/merged reason in DS9 | lifecycle completes the earlier detached-result concept |
| API contracts / Lifecycle evidence, lines 752–769 | Host reports route and custody generations plus retained-delivery status without granting workflow authority | lifecycle evidence and generations support, but do not replace, authority |
| Architecture / Observation and recovery language, lines 120–130 | DS9 owns successor incarnations, currentness and known-subject convergence | DS2's incarnation and observation candidates are completed here |

## Earlier concepts completed or refined

- **Authority claim:** DS5 established the complete claim and three-source rule;
  DS9 applies its operation-specific policy matrix to every established effect.
- **Local incarnation:** DS2's first local observation binds incarnation 1. DS9
  defines successor creation for close, reopen and merge movement.
- **Observation admission:** exact-read acquisitions reuse DS2's source-neutral
  snapshot, provenance, observation key, manifest and History admission path.
- **Lifecycle:** DS9 adds draft/ready, head/base/policy movement, closure, merge
  and true conflict, and completes terminal detached posture.
- **Operation:** authority remains operation-specific. DS9 rejects one generic
  fence that would change safeguards for replies, reminders or dashboards.
- **Reconstruction:** bounded exact reads converge known nonterminal subjects;
  delivery age, receipt time and process state never prove currentness.

## Subordinate vocabulary to evaluate

- `CurrentnessWitness`, `RouteGeneration` and `CustodyGeneration` are likely
  proof values inside lifecycle authority rather than peer product concepts.
- Phase, incarnation, head, base and policy are fields of `AuthorityClaim`.
- Draft, ready, closed, merged, blocked, moved and conflict are lifecycle or
  terminal variants, not automatically standalone glossary entries.
- Authority fence and current-authority point may name one relationship: the
  operation-specific cut at which all authority evidence must agree.
- Known-subject exact-read reconciliation may belong under reconstruction or
  configured-repository recovery rather than stand alone.

## Unresolved DS-review items

- lifecycle observation, state, terminal and posture fields;
- successor-incarnation and `CurrentnessWitness` representations;
- claim/current-authority capability extensions required by concrete call sites;
- host route/custody evidence, generation and read APIs;
- provider fresh-read values and read/fence transaction boundaries;
- the per-operation policy matrix and blocked/moved/conflict mappings;
- unavailable, stale, revoked, collision and closed failures; and
- calibrated authority evidence, call, row, byte, generation and artifact
  limits.

## DS13 final-language exclusions

- V5 lifecycle names, topology selectors, compatibility folds and old route or
  binding schemas do not survive cutover.
- “Complete-policy growth” and “fresh generation state” describe delivery and
  rollback scope, not final concepts.
- Named read/grant/route-change/effect-claim cuts are bounded mechanics unless
  needed inside the authority definition.
- Lifecycle schedules, injected races, physical counts and correspondence are
  acceptance evidence, not final-system vocabulary.
