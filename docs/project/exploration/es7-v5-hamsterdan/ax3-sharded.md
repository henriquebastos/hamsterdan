# AX3 — The sharded assembly: the SAME loops, any placement

**Status:** done, oracle-approved (three rounds), 2026-08-15.
**Question:** can placement change without rewriting workflows? AX1
authored the complete V5 Hamsterdan as nine actor loops cohabiting one
Petrus instance. AX3 deploys **the same authored net — same folds,
same activities, same seed batons, zero edits** — across several
instances, with AX2's courier carrying every cross-shard seam.

**Answer, stated precisely:** for a net inside the *shardable-net
profile* (below), **placement among already-shardable loops is
deployment-only**: a ~150-line generic splitter turns one built net
plus a placement map into shard nets; the one/two/nine-shard
placements land the identical selected outcome on all six AX1 scenario
scripts, the exercised seam-crash and shard-resurrection paths
converge, and every shard replays. Shardability itself remains a
*design* property — output-only seams don't happen by accident — but
the profile makes it checkable, and the splitter refuses anything
outside it.

- [test_ax3_sharded.py](test_ax3_sharded.py) — the whole prototype:
  the splitter, three placements, 34 pinned timelines.

## 1. The primitive

```text
split(built_net, placement) -> {shard_name: ShardPlan}
```

- A **loop** is a section of the authored net (`life.*`, `review.*`,
  …). A **placement** maps each loop to a shard name. One shard =
  cohabited; nine = every loop alone; any grouping between is legal.
- Each shard net contains its loops' places and transitions **copied
  by object identity** from the one authored net — no loop logic is
  written, changed, or even inspected by the splitter.
- For every foreign mailbox a shard's transitions feed, the splitter
  adds: a **proxy** (the same `Place` object, so folds' declared
  routes still name their targets; a proxy is transport, never state —
  it is excluded from seeding), an export **pump** (proxy + outbox
  baton → outbox baton, wrapping the token verbatim into an AX2
  envelope), and an **ack door + ack fold** per outbox.
- For every mailbox foreign shards feed, the target shard gets one
  delivery **door** (`on_courier_<mailbox>`), shared by all senders.
- The host assembly wires one AX2 `Courier` per `(shard, foreign
  mailbox)` route. Ingress doors (transitions with no input places)
  follow the shard of their target places.

The pump and ack folds are **schema-blind protocol code**: they touch
only the `Outbox`/`CourierAck` colors and wrap/unwrap the domain token
verbatim, so the same two functions serve every route of every net.

## 2. The shardable-net profile (refused, not documented)

`split` is generic over nets satisfying a profile, and raises
`ValueError` on anything outside it instead of silently mis-splitting:

1. **Sections-as-loops naming** — every place, and every transition
   except ingress doors, has a dotted loop prefix; nameless nodes are
   refused.
2. **Output-only seams** (AX7's anti-braid rule, load-bearing) — every
   cross-loop arc is *transition → foreign mailbox*. A foreign
   **input of any mode** (consume, read, or inhibit) braids custody
   and is refused **as a net property, before placement is even
   consulted**: a co-located braid is still a braid
   (`test_a_braided_net_is_refused` pins both the separated and the
   co-located placement).
3. **Exact placement coverage** — the placement maps exactly the loops
   present (no missing loop, no phantom loop), and every shard name is
   a non-empty string.
4. **Ingress doors target one shard each.**
5. **Reserved namespace** — no authored node in the `courier.` /
   `on_courier_` / `on_ack_` namespaces; no authored place using the
   protocol colors `Outbox`/`CourierAck`.
6. **No net-level completion** — a global completion predicate has no
   per-shard meaning; splitting such a net is refused.
7. **Globally injective route naming** — mailbox paths that collide
   under mangling (`c.foo_bar` vs `c.foo.bar`) are refused across
   **all** seam targets on any placement, since two source shards
   feeding the colliding pair would silently share one inbound door
   (`test_colliding_seam_targets_are_refused_globally`).

Each clause is pinned by a refusal test
(`test_the_profile_is_enforced_not_documented` and the two named
above). This is the payoff of
the V5 authoring discipline: because AX1's loops communicate only by
mailing facts, the seam census is fully mechanical — `seams(net)`
derived from arcs alone **exactly equals** AX1's hand-declared
`DECLARED_SEAMS` (74 arcs).

## 3. The machinery bill is a formula

Per route (one `(shard, foreign mailbox)` channel): 3 places (proxy
duplicate + outbox + ack place), 3 transitions (pump + ack fold + ack
door), 7 arcs. Per inbound door: 1 transition + 1 arc. **Nothing else
changes** — pinned as an exact arithmetic identity over the shard sums
(`test_the_machinery_bill_is_a_formula`).

| placement | shards | routes | doors | P | T | A |
| --- | --- | --- | --- | --- | --- | --- |
| authored (AX1) | — | — | — | 85 | 77 | 312 |
| solo | 1 | 0 | 0 | 85 | 77 | 312 |
| two (edge/core) | 2 | 17 | 17 | 136 | 145 | 448 |
| nine | 9 | 38 | 26 | 199 | 217 | 604 |

- The degenerate split adds **nothing**: solo contains the very same
  `Place`/`Transition`/`Arc` objects as the authored net, not merely
  equal counts (`test_solo_placement_reproduces_the_cohabited_net`).
- 74 seam arcs collapse into 38 routes at nine shards because a route
  is a channel, not an arc: all of a shard's transitions feeding the
  same foreign mailbox share one outbox.
- Nine-way machinery is ~+114 P/T (~+134%) and +292 arcs (~+94%) — all
  of it *generated transport*, none of it authored. Per-shard nets are
  small (`dash` P10 T11 A29; `life` P48 T55 A144).

## 4. The equivalence claim, scoped honestly

**Selected-outcome equivalence plus per-seam FIFO** on the solo, two-,
and nine-shard placements (18 parametrized cases):

- All six AX1 scenarios (`full_life`, `announce_once`, `ladder`,
  `snooze_reminders`, `draft_resume`, `supersede`) run against
  cohabited AX1 and against each derived assembly; compared are the
  externally visible world effects (readiness keys, comment kind/key,
  pushes, reruns, dashboard, authority) plus **14 selected
  baton/terminal places, token-for-token** — not every internal
  marking (the per-shard whole-marking replay test covers those).
- **Loop-definition sameness is mechanical**: shard nets hold the
  authored `Place`/`Transition` objects, and every authored handler
  registered on a shard engine `is` the cohabited wiring's callable
  (`test_loop_definitions_are_shared_by_object_identity`).
- **The lowering preserves order**: two heads admitted before any
  drain sit in one outbox as parcels `n=1,2` in emission order, and
  the target folds them in exactly that order
  (`test_two_queued_parcels_cross_one_seam_in_emission_order`) — this
  tests AX3's proxy→pump→outbox derivation, not (again) AX2's courier.
- **Not claimed:** identical global interleaving across seams. The
  dashboard's arrival-ordered entry list is compared as a sorted
  multiset — the one deliberate order-insensitive comparison, declared
  where it happens.
- Anti-vacuity: absolute facts are pinned on the sharded runs alone
  (readiness key `ready:h1:i1`, terminal phase, `announced == [1]`,
  ladder burn, dormancy incarnation `i2`) so "equal" can never mean
  "equally empty."
- Engine access stays serialized (one thread), as in AX1/AX2. True
  concurrent shards are future work; the claim here is placement
  transparency, not parallelism.

## 5. Crash and replay evidence — exactly what was exercised

Crash-safety is **AX2's theorem**; AX3 exercises it inside the real
assembly. The evidence covers exactly:

- **Two AX2 crash boundaries on one route** (life→`review.heads`,
  nine-way placement): courier death between target delivery and
  source ack (fresh drain redelivers; engine dedup absorbs; finished
  world and compared batons match the clean run; `agent_calls == 1`),
  and target-shard death after durable landing but before its folds
  ran (resurrect via `Engine.load` from the shard's chronicle;
  converges identically).
- **Per-shard replay**: after a full scenario, each of the nine
  shards' chronicles rebuilds the exact live marking — whole tokens,
  color and data.

Not exercised: the after-ack boundary (AX2 covers it in isolation),
source-shard resurrection, racing drains, crashes on other routes,
concurrency, or a durable history store. The claim is inheritance plus
these exercised paths, not an exhaustive proof.

## 6. What is generic, what is not

Generic (candidate Petrus-layer primitives):

1. `split(built, placement)` — generic over the **shardable-net
   profile** (§2), not over arbitrary Petrus nets. The profile's
   assumptions are explicit and each violation is refused. The braid
   refusal and profile tests use toy nets, not Hamsterdan.
2. The pump/ack protocol folds — schema-blind, reused verbatim across
   all 38 routes and both token schemas.
3. The shardability invariant as a *checkable* property — a lint any
   net can run to learn whether (and where) it can shard.

Hamsterdan-specific (assembly only): the placement maps, the scenario
scripts, and `door_engine`'s knowledge that `on_timer` enters `rem`.

## 7. Limits

- Proxies duplicate the `Place` object across shards; the mailbox
  place exists in both source (as pump input, never seeded) and target
  (as real mailbox). Marking state never collides — the source copy is
  drained by the pump — but tooling that assumes a place lives in one
  net would need the route table.
- Route identity here is `{prefix}-{shard}:{mailbox}` — sufficient for
  these tests; production routes must satisfy AX2's identity-namespace
  invariant (source incarnation included).
- The splitter operates on the built schema, not the spec DSL; a
  DSL-level `placement=` would be sugar over exactly this. Before any
  Petrus promotion, dotted-name inference should become explicit loop
  ownership and ingress metadata, and `ShardPlan` should carry owned
  places and partitioned registries so assembly is harder to misuse.
