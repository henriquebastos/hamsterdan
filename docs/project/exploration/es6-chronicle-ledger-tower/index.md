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
| AX5 | Residue probe: an orphaned worker's late effect absorbed at a gate across an instance kill | done → [ax5-residue.md](ax5-residue.md) |
| AX6 | V4 variant: one long-lived actor net per concern per PR (the Navigator's generator hunch), executed on the frozen engine | done → [ax6-actor-net.md](ax6-actor-net.md) |

## Conclusion

**Pursue V2; reject V3.** All numbers engine-measured, pinned by
tests:

| | P | T | nodes | A | ratio | reads | guards | biggest piece |
|---|---|---|---|---|---|---|---|---|
| Production | 46 | 69 | 115 | **309** | 2.69 | 94 | 48 | 115 (all of it) |
| V2 explicit | 72 | 30 | 102 | **99** | 0.85–1.41 | 0 | 0 | 22 |
| V2 collapsed | 35 | 17 | 52 | **56** | 0.83–1.41 | 0 | 0 | 22 |
| V3 split | 83+ | 44+ | 121+ | 150+ | — | 0 | 0 | rejected (AX3) |

Arcs drop 68–82%; read arcs and guards go to zero, not down; the
largest thing a reader ever holds shrinks from 115 nodes to 22; and
the kill-residue safety story executed on the frozen engine (AX5).
The complexity that left the topology moved to (a) pure functions
(fold/decide/step) and (b) instance-management runtime machinery
Petrus does not yet have — paid once, domain-free, instead of
braided into every authored net. Recommended next step, pending the
Navigator's rulings on the open decisions below: a runtime spike on
spawn/abandon/ingress-routing/GC, the tower's remaining unknown.

**Post-conclusion addendum (AX6):** the Navigator's generator hunch
was measured as V4 — one long-lived actor net per concern per PR —
and it keeps every tower property while deleting kills, graveyards,
seeds, and most GC from the common path. The tower's two-level idea
survives unchanged; what is now open is whether the work level is
*disposable per epoch* (V2) or *durable per concern* (V4).

## Findings at a glance (details in each experiment)

- **AX1 — promising.** Under one fixed authority the domain is eleven
  isolated, acyclic, linear pipelines built from three shapes: ratio
  0.85, zero read arcs, zero guards, zero filters, fan-in nowhere.
- **AX2 — promising.** Everything the tower removed fits a 22-node
  case net: a (state × observation) grid with zero guards; the whole
  V2 system needs exactly two idioms — pipelines that work (ratio
  < 1) and one state cell that routes (ratio > 1, confined).
- **AX3 — not useful enough.** Splitting lifecycle from epoch
  management builds a shadow state machine (+73% nodes, 4 cross-net
  colors, new routing machinery). General rule: split levels **by
  world, not by topic**.
- **AX4 — promising.** Production measured with the same instruments:
  309 arcs, ratio 2.687, 94 read arcs, 48 guards, one braid. V2
  total: 99 arcs, 0 reads, 0 guards, thirteen independent pieces.
  Five re-derived primitives: pipeline, state cell, gate, typed
  ingress + decide-seeded entries, tower.
- **AX5 — promising.** Executed on the frozen engine: the kill is
  bookkeeping, the gate absorbs the orphaned effect (`moved`, not an
  error), chronicles never mix, and a dead instance replays honestly.
- **AX6 — promising.** The long-lived actor (V4): the whole review
  concern for the PR's whole life in 21 nodes / 23 arcs, zero
  guards/reads/filters, executed on the frozen engine via
  `Engine.deliver`. Sequential rounds by a memory-baton token;
  staleness absorbed at the CAS gate (`moved` findings become the
  next round's provisional input — incremental review is native).
  Deletes kills, graveyards, seeds, and most GC from the common path.
  V2 vs V4 is now a measured, open Navigator ruling.

## Navigator decisions (rulings of 2026-08-14)

1. **Epoch definition — ruled: head only.** Base movement is not an
   epoch cut; a *conflict* is the signal that matters, observed at
   fold time. A "final checkpoint" subnet (when nothing is pending,
   let the human judge merging on a moved-but-conflict-free base) was
   recognized as a sensible **additive** feature and deliberately
   deferred — it is new scope, not a change to this design.
2. **Kind-as-topology — ruled: explicit topology per publication
   kind**, with a refinement: extract the *shared publication
   mechanics* (render → CAS-gate → effect → record) as one reusable
   component subnet that each named kind instantiates, so per-kind
   logic can change without touching the others while the common part
   stays single-sourced. Collapsed form remains acceptable for
   mutations.
3. **Late-append policy — ruled: graveyard.** A dead instance's
   chronicle may record late worker completions, because *advancing a
   net* (enabling/firing) and *recording what the real world reported
   back* are different acts; history must reflect the world.
   Mechanism to be designed in the runtime spike.
4. **Seed contents — reframed, not ruled.** The Navigator questioned
   whether the seed exists only because PR-scoped facts were placed
   in head-scoped instances (see "lifetime assignment" below). Open
   fork: one case net owning all PR-scoped concerns vs per-concern
   sibling nets.
5. **Timer ownership — subsumed by 4.** Timers are PR-scoped facts;
   under lifetime assignment they never live in a head-scoped
   instance, so no handover problem exists.

### The lifetime-assignment reframe (open)

The seed/timer problems are symptoms of scope misassignment: a fact
should live in the layer whose lifetime equals the fact's own.
Head-scoped facts (review of *this diff*, CI for *this sha*) belong
in the disposable work instance and need no seed. PR-scoped facts
(conversation, reminders, dismissal memory, budgets) belong in the
long-lived case layer. GitHub-owned facts (approvals, draft state,
mergeability) are re-observed, never stored. Under this rule the
"seed" degenerates into spawn *arguments* — read-only snapshots
passed like function parameters — not state that must be kept alive
across cuts. Making a *work* concern long-lived was first predicted
to reintroduce per-token epoch guards — then AX6 measured it and
found a clean shape: with sequential rounds enforced by a memory
baton and staleness absorbed at the CAS gate, the actor stays at
zero guards/reads. The prediction was wrong for that shape; V2 vs V4
is now a measured, open ruling (see AX6).

## Governing constraints

- Petrus stays frozen; production behavior untouched.
- General net primitives, not Hamsterdan-only abstractions — the meta
  net pattern must be statable for *any* epoch-shaped authority.
- Candidate findings only; the Navigator rules the product choices
  (epoch definition, seed contents, late-append policy).
