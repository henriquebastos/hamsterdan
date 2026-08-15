# AX4 — The verdict: production vs V5 cohabited vs V5 sharded

**Status:** done, oracle-approved (five review rounds), 2026-08-15.
Conclusions remain candidate recommendations — the Navigator decides.
**Question:** with all three artifacts real and measured — the
untouched production braided topology, AX1's complete cohabited V5,
and AX3's derived sharded V5 — what do the numbers and behaviors say,
and which constructs are generic Petrus-layer primitives?

Every structural count below is asserted in
[test_ax4_verdict.py](test_ax4_verdict.py), which imports production
**read-only** — production code is not touched anywhere in ES-007.
(Test-suite sizes and approximate line counts are cited, not
asserted.)

**Comparison limitation, stated up front.** Structural counts compare
implemented artifacts with overlapping but non-identical integration
scope: production carries real webhook custody, dispatch, and
observability; V5 runs on fake worlds, single-threaded, with in-memory
history. The counts establish profile shape and prototype behavior —
**not** production parity, migration safety, maintainability, latency,
or operational cost. AX1 was never run against production, and no
canonical scenario establishes production↔V5 behavioral equivalence.

**Recommendations are candidates.** The Navigator decides.

## 1. The shape, side by side

Two lenses, three metrics, defined by direction: **strict** (AX3's
`seams()`: arcs between two *named* prefixes — cross-**section** in
production, whose dotted prefixes are operational sections rather
than owners; cross-**loop** custody only in V5, where every prefix is
a declared loop owner); **broad input** (endpoint prefixes differ,
*including* an empty prefix — shardable-profile violations, not by
itself proof of cross-concern coupling); and **broad output**
(topology anatomy under the same prefix lens — in V5 it includes the
8 root ingress-door feeds alongside the 74 custody seams, so it is
not a custody count either).

| metric | production | V5 cohabited | V5 nine-shard |
| --- | --- | --- | --- |
| places | 46 | 85 | 199 |
| transitions | 69 | 77 | 217 |
| arcs | 309 | 312 | 604 |
| **arc/node ratio** | **2.69** | **1.93** | 1.45 |
| read arcs | 94 | 0 | 0 |
| guards | 48 | **0** (asserted `{}`) | 0 authored |
| CEL filters / inhibitors | 0 / 0 | 0 / 0 | 0 / 0 |
| cross-prefix input arcs, strict (named→named) | 11 | **0** | 0 authored; 38 generated (mailbox proxy → courier pump, asserted) |
| profile-violating inputs, broad (incl. unowned endpoints) | **92** (11 named + 79 from unowned places + 2 into unowned transitions) | **0** | 0 authored; 38 generated |
| cross-prefix output seams, strict (named→named) | 12 | 74 | 74 logical, lowered to 38 courier routes; ordinary cross-instance arcs 0 |
| cross-prefix output arcs, broad (incl. unowned endpoints) | 72 | 82 (74 seams + 8 ingress-door feeds) | — |
| unowned (rootless) non-ingress nodes | **58** (33 places + 25 transitions) | 0 | 0 |
| fold handlers | 33 | 61 | 61 + 76 protocol registrations (2 shared functions) |
| activity bindings | 11 | 8 | 8 |
| bound callables total | 44 | 69 | 69 + 76 |
| authored external ingress doors | 7 | 8 | 8, routed |
| generated protocol doors (ack + delivery) | — | — | 64 (38 + 26); 72 source transitions total |
| shardable (AX3 profile)? | **refused** | **yes, mechanically** | derived |

Three readings of that table:

1. **Same arc budget, opposite topology.** Production and V5 cohabited
   have nearly identical arc counts (309 vs 312) but production packs
   them into half the places (46 vs 85). The difference is *where
   coupling lives*: production couples transitions to shared state via
   94 read arcs and 48 guards; V5 gives every fact its own mailbox
   place, has zero read arcs and zero guards, and expresses all
   cross-loop influence as 74 explicit, declared output seams —
   coupling is not eliminated, it is moved to visible one-way mail.
   The arc/node ratio drops from 2.69 to 1.93 — the Navigator's "state
   spread" hunch, now measured.
2. **Production's input violations are dominated by unowned root
   state — the cohort is the largest single contributor, not the
   whole story.** The 92 profile-violating inputs decompose (pinned in
   `test_the_unowned_input_anatomy`) as: 11 named→named section arcs,
   79 arcs from *unowned root places* into named-section transitions,
   and 2 arcs from named places into unowned root transitions. Of the
   79, **40** originate at the nine root cohort places (`authority`,
   `actions_state`, `review_state`, `human_state`, `mutation_state`,
   four publication states; 37 read + 3 consume) and **39** at other
   root places — generation control (`generation_start/stop/commit`),
   `admission`, `seed`/`dormant`/`terminal`, `recovery_basis`, and
   the basis/result buffers (the exact source set is asserted, so the
   attribution cannot drift). So the "control places as global state"
   pattern the Navigator suspected is real and measurable, but it is
   root state *generally* (cohort + generation/admission plumbing),
   not the cohort alone. V5 has no root state at all — every place has
   an owner.
3. **The splitter's refusal is itself a measurement.** Running AX3's
   `split` on the production net raises `ValueError` on the
   unowned-node clause first (58 nodes without a section owner); the
   braid clause (92 foreign inputs) would refuse it next — pinned as
   `test_production_is_outside_the_shardable_profile`. No AX3
   placement is accepted for the current topology — production cannot
   be sharded *as designed* by this splitter.

## 2. What the same decision looks like in each style

Production gates readiness by reading global state. The announce
transition consumes its own ninth cohort place
(`readiness_publication_state`) while **reading the other eight**
(authority, actions/review/human/mutation state, three publication
states) under a guard that projects them into a snapshot:

```python
# production topology.py, VERBATIM (read-only quote)
announce = t.authorize_readiness(
    handler=petri_handler(_announce),
    guards=_guard(lambda *values: ready(_snapshot_values(*values))),
)
for place in cohort[:8]:
    place >> arc.read() >> announce
```

Whether readiness fires depends on eight concerns' current markings;
the guard recomputes a global snapshot at enablement time.

V5 mails facts to a fold that owns the whole decision (zero guards,
zero read arcs — the readiness loop's memory is one baton). Labeled
**simplified**; the real wiring is AX1 line ~2493, same structure:

```python
# AX1, SIMPLIFIED — other loops SEND facts; ready folds them
ready.p.facts(GateFact)                         # mailbox: anyone may write
(ready.p.facts, ready.p.snap) >> ready.t.fold(handler=...) >> ready.p.snap
# the decision fires when the BATON says all gates are green,
# not when a guard over eight foreign places says so
```

The production style is shorter on nodes and heavier on coupling; the
V5 style spends places to keep every decision locally explainable —
each loop's decisions read from its own baton history.

## 3. Behavior and replay evidence, honestly scoped

Test counts below are **not comparable coverage quantities** — the
suites test different things at different fidelities:

- **Production**: the repository's `tests/` suite (584 tests) covers
  production broadly — the topology *and* the real host (webhook
  custody, dispatch, observability, recovery). ES-007 claims none of
  that scope for V5.
- **V5 cohabited**: AX1's 47 tests (timelines plus structural and
  replay checks) execute the ES-005 chapter-17 boundary contract on
  the frozen engine with fake worlds — admission, supersession,
  dormancy/resume, escalation ladder, publication effects,
  conversation, reminders, readiness, terminal folds.
- **V5 sharded**: AX3's 34 tests (profile refusals, formula, identity,
  equivalence timelines, crash, replay) prove selected-outcome
  equivalence across solo/two/nine placements plus the exercised
  crash paths.

Replay and chronicle, per artifact:

- **Production**: one durable history per PR; restart, custody, and
  dispatch-recovery behavior covered by its own suite.
- **V5 cohabited**: one shared in-memory chronicle for all nine loops;
  one whole-marking replay test. Events are *loop-attributable* (every
  place has an owner) but the chronicle itself is shared — per-loop
  chronicles arrive only with sharding.
- **V5 sharded**: one in-memory chronicle per shard; exact per-shard
  whole-marking replay; one exercised review-shard resurrection.
- **Not measured anywhere in ES-007**: durable-store crash injection,
  true concurrency, throughput, latency, backpressure, history growth,
  process isolation, operational observability.

## 4. The costs, stated plainly

**Cohabited V5 vs production:** +39 places, +8 transitions, +3 arcs;
more fold handlers (61 vs 33) because every decision is a fold. In
exchange: zero guards, zero read arcs, loop-attributable events, and
the *option* of sharding. Scheduling: V5 relies on
`choose_throughput`, which **production already configures**
(`host/runtime.py`); this is a shared dependency, not a new V5 cost —
but AX1 did show `choose_conservative` would block independent loops,
and ES-007's serialized orchestrators prove nothing about concurrent
scheduling.

**Sharding on top:** the machinery bill is a formula (3 places + 3
transitions + 7 arcs per route; 1 transition + 1 arc per inbound
door). Nine-way: **+114 places, +140 transitions (254 nodes), +292
arcs** — all generated, none authored, matching the formula exactly
(`test_the_growth_is_entirely_generated`). Operationally: nine
engines, 38 couriers, route-identity discipline (AX2's namespace
invariant), and at-least-once transport everywhere a seam used to be
an ordinary arc.

**Engine-state isolation demonstrated** (not blast radius — host,
process, transport, and shared-storage failure were never isolated):
the largest shard (`life`, 103 nodes) is smaller than production's
whole net (115); `dash` is 21. What AX3 exercised, exactly: after a
parcel landed, the review Engine alone was discarded and reloaded
from its own chronicle, and the assembly then converged to the
canonical outcome. Life was *not advanced during* the simulated
outage, so no claim is made about other shards making progress while
one is down.

## 5. The primitive census — what ES-007 actually found

**Authoring conventions** (patterns over the shipped DSL, enforceable
as lints, requiring nothing from the engine):

1. **The actor-loop discipline** (AX1): one concern = one loop = one
   memory baton + mailbox places; cross-loop communication is mailed
   facts only. The braid census is its lint.
2. **The seed baton** (AX1): loops start with their memory token in
   place; no initialization transitions.
3. **The ingress door** (AX1/AX2): a transition with no inputs, fired
   by identified delivery; the engine's identity dedup is the only
   dedup anywhere.

**Runtime/assembly candidates** (small generic code, engine
unchanged):

4. **The courier** (AX2): outbox baton + stateless schema-blind
   transport + door-identity dedup = **exactly-once door landing**
   (not general exactly-once processing) under immutable global route
   identity, serialized Engine access, and `Engine.deliver`'s
   commit-before-return atomicity. ~80 lines, crash-tested at each
   pinned boundary.
5. **The splitter + shardable-net profile** (AX3): ~150 lines deriving
   any placement from one authored net, refusing nets outside the
   profile. The profile doubles as a *shardability lint* even if
   sharding is never used. Generic ingress-door placement derivation
   belongs here too.

**Verification tooling** (not a runtime primitive):

6. **The canonical timeline** (AX1/AX3): scenario scripts + selected
   outcomes as the equivalence instrument across assemblies.

**Hamsterdan-specific composition** (not primitives): the nine
concrete concern loops, their domain facts/colors and folds, activity
gates, placement maps, scenario worlds, and the host's door dispatch.

Pre-promotion requirements already identified: explicit loop-ownership
metadata instead of dotted-name inference; `ShardPlan` carrying owned
places and partitioned registries; route identity including source
incarnation; serialized-access guarantees; durable-backend
qualification.

## 6. Candidate recommendations (Navigator decides)

1. **Prefer the V5 loop discipline as the authoring model for a
   production-parity replacement *experiment*** — not immediate
   adoption. Evidence for preference: strict cross-section input arcs
   11 → 0, unowned-endpoint input violations 81 → 0 (unowned root
   places eliminated entirely, 33 → 0), guards 48 → 0, read arcs
   94 → 0, ratio 2.69 → 1.93 at essentially the same arc budget, plus
   mechanical seam census and the option of sharding. Promotion to actual adoption should require
   running the boundary scenarios through real host composition and
   durable recovery.
2. **Treat sharding as a deployment decision, deferred.** Location
   transparency is established for selected outcomes, the tested
   placements, serialized access, and nets inside the profile — scale
   benefit was not measured. Nothing about the authoring model needs
   deciding now; the bill is a known formula, not a rewrite.
3. **Prefer parallel replacement over incremental refactor — because
   it protects production, not because incremental is impossible.**
   The splitter refusal proves production is not *directly* consumable
   by AX3; it does not prove ownership metadata and mailbox seams
   couldn't be introduced incrementally. But a parallel V5 behind the
   same boundary contract (ES-005 ch. 17, already encoded as AX1
   timelines) permits parity testing while production keeps running.
4. **Promote the courier and the profile lint first** if any Petrus
   promotion happens — conditional on the pre-promotion requirements
   above. Both are small, generic, and useful independent of any
   sharding decision. Precisely scoped: until explicit ownership
   metadata exists, the lint identifies **profile violations** —
   unowned nodes and cross-prefix inputs — not custody boundaries;
   with dotted-name inference it cannot know which prefix *owns*
   what, only which arcs and nodes would block sharding.
