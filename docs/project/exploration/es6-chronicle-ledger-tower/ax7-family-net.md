# AX7 — The cohabitation variant (V5): all concern actors in ONE instance

**Status:** done, 2026-08-14. Tests: [test_ax7_family_net.py](test_ax7_family_net.py)
(11, all executed on the frozen engine).

## The question

The Navigator's asyncio hunch: AX6's actor nets look like generators —
and asyncio runs many generators in one thread. Can the V4 actors
(review, CI, dashboard, …) cohabit **one engine instance** that lives
with the PR from open to close, instead of one instance per concern?

## The answer: yes — and it dissolves the router

A Petri net is natively concurrent: the net is the event loop, each
concern's baton loop is a coroutine, and several loops in one net is
the *normal* reading of a net, not a trick. Production itself is one
instance with many concurrent concerns; its sin was the braid, never
the cohabitation. Three things get *simpler* than V4-as-instances:

1. **Broadcast is topology.** `on_head` is one source transition
   whose output arcs fan the delivered token into every interested
   mailbox. The V4 router instance disappears into two arcs.

   ```python
   net.t.on_head >> (review.p.heads, ci.p.heads)
   net.t.on_close >> (review.p.closed, ci.p.closed, dash.p.closed)
   ```

2. **Cross-concern dataflow is an arc.** A fold is a pure
   `petri_handler` returning its own baton AND a fact into a
   sibling's mailbox — multi-color output, host-side, no dispatch,
   no cross-instance messaging machinery:

   ```python
   r.p.landed >> r.t.fold_landed(handler=petri_handler(_fold_review_landed)) \
       >> (r.p.memory, d.p.facts)
   ```

3. **One chronicle tells the PR's whole story** — all concerns
   interleaved, one replay, one archive at close.

## The discipline that prevents the braid (asserted structurally)

Concern loops share **nothing** except the ingress broadcast and
declared mailbox-to-mailbox fact arcs. Batons are private. The test
removes the two ingress doors and the two declared fact arcs and
asserts the net falls apart into exactly three independent concern
subgraphs; a second test walks every arc and refuses any undeclared
cross-concern touch. This rule — *concerns connect only
event-to-mailbox, never state-to-state* — is the anti-braid invariant
and a candidate validation for any future authoring layer.

## Measures (test-pinned)

| | P | T | A | ratio | reads | guards | filters |
|---|---|---|---|---|---|---|---|
| V5 family (review + CI + dashboard), whole PR life, ONE instance | 23 | 17 | 47 | 1.175 | 0 | 0 | 0 |

All cycles pass through the three private batons (`review.memory`,
`ci.memory`, `dash.memory`); removing them makes the net acyclic.

**Honest scope note:** these three loops cover three of production's
~six concern families (no mutations, reruns, reminders, conversation,
or extra publication kinds here). Extrapolating the measured loop
sizes, a full V5 would sit near 80–90 nodes and ~110 arcs — still
roughly a third of production's 309 arcs, with zero staleness
constructs, in the *same* architectural footprint production already
uses: one instance per PR.

## Executed timeline (one PR, three heads, a mid-life fault, one chronicle)

1. `h1` delivered → **both** mailboxes receive it (broadcast). Review
   lands `finding:h1`; CI assesses `ok`; each fold emits a fact; the
   dashboard upserts twice.
2. `h2`, `h3` delivered in quick succession. Review: `h2` round
   completes, gate says `moved`, findings fold back; `h3` round
   carries them (`[finding:h2, finding:h3]`) and lands. CI: `h2`
   assessment **faults** — the CI baton is swallowed; `h3` rests in
   CI's mailbox forever, visibly.
3. Fault isolation is behavioral, not architectural: review and
   dashboard kept running in the same instance, because enabledness
   is local to each transition.
4. Close delivered → review and dashboard end gracefully (their
   batons return first — token conservation is also graceful
   shutdown); CI **cannot** end: `ci.closed` rests unconsumed. The
   stall is honest, visible in the marking, and replayable — never an
   exception.
5. `Engine.load` reproduces the entire final marking — done tokens,
   the fault residue, the dead-letter head — and re-fires nothing.

## The four designs, one line each

| | instances per PR | staleness | router | cross-concern | guards/reads | chronicle |
|---|---|---|---|---|---|---|
| Production | 1 (+scopes) | 94 reads, 48 guards in-net | — | braided places | 48/94 | 1, braided |
| V2 tower | ~1 per head + case | by kill | case net | spawn args + case | 0/0 | many short |
| V4 actors | ~1 per concern (~5) | CAS at round boundary | needed | messaging | 0/0 | 1 per concern |
| V5 cohabitation | **1** | CAS at round boundary | **arcs** | **arcs** | 0/0 | **1, whole story** |

## What remains open after AX7

1. **Meta level shrinks to the host.** With V5 there is no case-net
   instance left: the host spawns the PR instance at the first
   webhook and archives it when the marking is terminal. Dormancy
   (draft PRs) and lifecycle could be a fourth tiny actor loop inside
   the same instance — unmeasured.
2. **Blast radius.** One poison event or corrupted chronicle now
   affects the PR's whole instance, not one concern. Mitigated by
   delivery identity + quarantine already in the engine; unmeasured.
3. **Chronicle growth.** One history accumulates everything a PR ever
   did; replay stays linear but long. V4 sharding by concern remains
   the fallback if this ever hurts.
4. **Serialized advancement.** One instance advances one occurrence
   at a time; concerns interleave rather than truly parallelize. At
   PR event rates this is irrelevant, but it is a real difference
   from V4.
5. **Mailbox compaction and fault recovery** carry over from AX6
   unchanged (router-less compaction would happen at the host's
   delivery decision; a stalled loop needs a meta-level noticing
   story).

## Verdict

**Promising; continue.** V5 keeps every tower and actor property —
zero staleness constructs, confined cyclicity, honest fail-closed
residue, native incremental memory — while deleting the router, the
cross-instance messaging, per-concern spawning, and multi-chronicle
correlation. One PR = one durable, replayable, self-contained net
whose loops are the concerns. The V2-vs-V4 ruling collapses into a
simpler one: **V5 unless a measured reason forces sharding.**
