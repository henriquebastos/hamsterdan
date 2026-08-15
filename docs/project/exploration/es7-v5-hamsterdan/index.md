# ES-007 — The complete V5 Hamsterdan: cohabited, then sharded

**Status:** complete, 2026-08-15 (all AX0–AX4 done and
oracle-approved; conclusions remain candidate recommendations for the
Navigator).
**Navigator seed:** after ES-006 AX6/AX7 (actor loops, cohabitation),
build the decision-grade three-way comparison: production untouched ·
a complete V5 net · the same loops sharded across instances. The deep
question: **is sharding a deployment decision or a design decision?**
If identical authored loops run cohabited or sharded with only the
assembly changing, location transparency holds and "V5 vs V4" stops
being an architecture fork.

## Navigator rulings for this exploration

1. V5-complete and V5-sharded **share the same concern loop
   definitions** — the sameness *is* the finding. Both are fully
   independent of production.
2. Dormancy-as-a-loop is explored in AX0/AX1, not pre-decided.
3. Same commit-and-push-at-≥90%-confidence rule as ES-006.
4. **Oracle checkpoint:** at each AX completion the result is checked
   with the oracle before moving forward.

## Method rules (inherited from ES-006, plus)

1. Shipped spec DSL only; production `topology.py` stays quarantined
   until the AX4 comparison (greenfield, not refactoring).
2. Behavior comes from the ES-005 chapter 17 boundary contract, not
   from production structure.
3. TDD on shape AND on behavior: every net is built and measured;
   every timeline executes on the frozen engine with fake worlds
   (fake GitHub, fake agents) and replays.
4. Scope honesty: this is decision-grade evidence, not a host
   replacement — webhook custody, real dispatch, and observability
   stay out.
5. General primitives, never Hamsterdan-only abstractions, in
   anything reusable (especially AX2's courier).

## Experiments

| # | Question | Status |
| --- | --- | --- |
| AX0 | Contract census: every chapter-17 clause mapped to a concern loop; boundary obligations separated from tower-era mechanisms; instruments pinned | done, oracle-checked (amendments A1–A4 folded in) → [ax0-contract-census.md](ax0-contract-census.md) |
| AX1 | The complete cohabited V5 net: all loops, one instance, executed timelines | done, oracle-approved after six rounds (blockers pinned as tests; census amendment A5) → [ax1-complete-v5.md](ax1-complete-v5.md) |
| AX2 | The courier primitive: outbox place + identified delivery across instances, crash-and-redeliver proof, generic | done — [ax2-courier.md](ax2-courier.md), oracle-approved (4 rounds) |
| AX3 | The sharded assembly: the SAME loops across several instances; trace-equivalence against AX1 | done, oracle-approved after three rounds (shardable-net profile enforced, not documented) → [ax3-sharded.md](ax3-sharded.md) |
| AX4 | Verdict: production vs V5 vs V5-sharded — shape, behavior coverage, machinery bill, engine-state isolation, replay; final primitive census | done, oracle-approved after five rounds (strict/broad metrics kept apart, decompositions pinned as tests) → [ax4-verdict.md](ax4-verdict.md) |
