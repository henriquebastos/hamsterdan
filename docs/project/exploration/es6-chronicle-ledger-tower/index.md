# ES-006 — The chronicle/ledger tower: layered net decomposition

**Status:** Thickening, 2026-08-14.
**Navigator seed:** the three-step conversation that produced the tower
model (context carrying → staleness by existence → the
speculation/commitment boundary), captured in
[tower-model.md](tower-model.md).

## The question

If staleness, cancellation, and epoch management move out of the
domain net into a meta layer — and the meta layer is *itself* a net
whose world is the set of engine instances — **what shape do the
resulting nets actually have?**

The hypothesis is radical simplification: each layer's net becomes
small, linear, and readable, because today's single net is two braided
layers (domain work + staleness bookkeeping) forced into one topology.

## The reframe hypothesis (why this precedes more DSL work)

ES-003/ES-005 explored authoring constructs (blocks, combinators,
rails) against the *current* single-layer topology. If the layered
decomposition simplifies topology as much as suspected, the census of
constructs a net actually needs changes. So this exploration
deliberately **forgets the block algebra**: every net here is written
in the shipped spec DSL (`petrus.impetus.dsl.NetSpec`) with TDD, and
only *after* seeing the simplified shapes do we re-derive which
authoring primitives are genuinely primitive ("the primitive census").
The blocks-and-combinators reframe, if it survives, comes after.

## Method rules

1. Shipped spec DSL only — no imports from ES-003 spike code.
2. TDD on shape: every net is built (`NetSpec(...).build()`) and its
   inventory asserted (places, transitions, arcs, filters, read arcs).
3. Shape first, machinery later: instance management, abandon
   delivery, and GC are *modeled as activities* of the meta net, not
   implemented as infrastructure.
4. **Greenfield, not refactoring.** This is a fresh expression of the
   same goal, not a decomposition of the existing net. Behavior comes
   from ES-005
   [chapter 17](../es5-design-primer/17-hamsterdan-rebuild-brief.md)
   (the boundary-confirmed contract) and from first principles.
   Production `topology.py` is **quarantined until AX4**: it is never
   opened while designing AX1–AX3, so its structural choices — control
   places, drain machinery, staleness plumbing — cannot leak into the
   new design. It re-enters only at AX4, as the measured baseline.
5. Measures per net and per variant: `P`, `T`, `A`, `arcs/(P+T)`,
   read-arc count, guard count, count of staleness-only constructs
   (target: 0 inside work nets), and the construct census.
6. Each experiment stops for Navigator review before the next.

## Experiments

| # | Question | Status |
| --- | --- | --- |
| AX0 | Capture the tower model, variants, and measures | done → [tower-model.md](tower-model.md) |
| AX1 | V2 work net: the domain net under one fixed authority — how simple? | done → [ax1-work-net.md](ax1-work-net.md) |
| AX2 | V2 meta net: PR lifecycle + epoch spawn/abandon as ordinary activities | done → [ax2-case-net.md](ax2-case-net.md) |
| AX3 | V3 variant: split PR lifecycle from epoch management (three nets) | done → [ax3-v3-split.md](ax3-v3-split.md) — not useful enough |
| AX4 | Comparison: shape metrics, construct census, primitive re-derivation | done → [ax4-comparison.md](ax4-comparison.md) |
| AX5 | Residue probe: an orphaned worker's late effect absorbed at a gate across an instance kill | optional |

## Governing constraints

- Petrus stays frozen; production behavior untouched.
- General net primitives, not Hamsterdan-only abstractions — the meta
  net pattern must be statable for *any* epoch-shaped authority.
- Candidate findings only; the Navigator rules the product choices
  (epoch definition, seed contents, late-append policy).
