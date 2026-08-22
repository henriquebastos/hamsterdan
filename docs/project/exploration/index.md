# Exploration

Exploratory Stories preserve meaningful uncertainty before it becomes Delivery.
Each story owns an `index.md` under `es<N>-<slug>/` and uses one of: Thickening,
Paused, Candidate, Promoted, or Archived.

## Active

- [ES-001 — Simplify the Petri Net at the Motus boundary](es1-petri-net-motus-boundary/index.md)
- [ES-003 — Workflow AST authoring model compiled to the Petri net](es3-workflow-ast-authoring-model/index.md)
- [ES-004 — Hamsterdan experience specification and subnet decomposition](es4-hamsterdan-experience-specification/index.md)
- [ES-005 — The design primer: consolidated learning for the design phase](es5-design-primer/index.md):
  the cross-story distillation of everything that earned trust in
  ES-001–ES-004, taught as isolated concepts in one normalized
  pseudocode vocabulary, with per-concept lowerings, the
  from-spec-to-net method, and the Hamsterdan rebuild brief. Candidate
  input to the design phase; positives only — negative results stay in
  the source syntheses.
- [ES-006 — The chronicle/ledger tower: layered net decomposition](es6-chronicle-ledger-tower/index.md):
  what shape do the nets take when staleness, cancellation, and epoch
  management move to a meta net whose world is the set of engine
  instances — one disposable work net per epoch, written in the
  shipped spec DSL with TDD, measured against the ES-005 contract.
- [ES-007 — The complete V5 Hamsterdan: cohabited, then sharded](es7-v5-hamsterdan/index.md):
  the decision-grade three-way comparison — production untouched, a
  complete actor-loop V5 net in one instance, and the same authored
  loops sharded across instances via a generic courier. Tests whether
  sharding is a deployment decision rather than a design decision.
  Oracle-checkpointed at each experiment. Complete: for nets inside
  the enforced shardable profile, placement is deployment-only;
  conclusions remain candidate recommendations.
- [ES-008 — Typed readiness decisions as production V5 topology](es8-typed-readiness-topology/index.md):
  a promoted production experiment replacing readiness's open `GateFact`
  dispatcher with specialized colors, places, and folds while retaining an
  input-only filtered migration lane for interrupted histories. Behavioral and
  cross-version recovery evidence is green; formerly implicit FIFO authority
  and producer-causality rules are explicit topology.

## Archived

- [ES-002 — Imperative expression layer compiled to the readiness Net](es2-imperative-expression-layer/index.md)
