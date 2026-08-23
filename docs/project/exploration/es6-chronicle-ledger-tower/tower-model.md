# AX0 — The tower model: chronicle, ledger, and layered nets

The conceptual capture behind ES-006, recorded in detail so the idea
survives context loss. Everything here is *candidate reasoning* — the
topology experiments (AX1–AX4) exist to test it.

## 1. Genealogy: three questions that led here

**Q1 — How does a combinator strategy carry global context
functionally?** Answer: context is part of the block's *interface*
(the coeffect row), aggregated structurally during composition,
satisfied once at the edge. Three carriers, by kind of "global":
immutable per-case facts → stamp the token at ingress and compare at
boundaries; read-mostly coordination state → fold settled exits into
a snapshot outside the net; true contention → a real place, consumed
and returned (`holding`). Read-places are Reader; stamps are a frozen
Reader per case; fold/decide is context-as-projection; holding is
State made visible.

**Q2 — What if the net only ever sees one epoch, and epoch management
moves to the code that instantiates nets?** The staleness ladder:

```text
Level 1  production      staleness CHECKED         read arcs + guards
                                                   (42 of 94 read arcs)
Level 2  ES-004 model    staleness UNEXPRESSIBLE   epoch stamps; stale
                         in data                   completions inert
Level 3  this story      staleness UNEXPRESSIBLE   one net instance per
                         in existence              epoch; the stale net
                                                   is simply gone
```

Cancellation-as-net-structure is known-bad in the literature (reset
arcs break locality and decidability; YAWL added cancellation regions
as a special construct because plain nets cannot say "kill this
region" cleanly). The clean move is meta-level cancellation: kill the
*instance*, not the tokens. In an event-sourced engine the kill is
almost free — stop feeding events, mark dead, never resume. No stop
places, no poison tokens: **abandonment, not termination**.

**Q3 — But doesn't that split history and complicate the machinery?**
Yes — and that split has a name and a long pedigree.

## 2. The speculation/commitment boundary

Every system that reconciles a pure, replayable model with a stateful
concurrent world ends up with two layers:

```text
CHRONICLE   what physically happened: attempts, cancels, waste, races
            — imperative, at-least-once, messy, operational
LEDGER      what counts: settled facts, total, replayable
            — pure, ordered, the thing you reason over
```

The impurity is a **conserved quantity**: it cannot be removed, only
relocated and concentrated. The design question is never "how do I
eliminate the tension" but "is every fact clearly on one side, and is
the impure side written once."

Precedents (each is the same two-layer split):

| System | Chronicle | Ledger | Retirement point |
|---|---|---|---|
| OCC databases (Kung & Robinson 1981) | transaction attempts | committed state | commit-time validation |
| STM (Harris/Marlow/Peyton Jones) | aborted speculative runs | committed transactions | validate-and-commit |
| MVCC (Postgres) | dead row versions | visible snapshot | commit |
| CPU speculation | reorder buffer | architectural state | retirement, in order |
| Git | reflog | history | ref advance |
| WAL databases | write-ahead log | checkpointed state | fsync + apply |
| Temporal | activity attempt logs | workflow event history | completion recorded |
| **Petrus (this model)** | dispatcher attempts, killed instances | each net's History | **the gates** |

The gates (comment gate, git gate) are the retirement point: the only
place speculation becomes fact. This is why the ES-004 finding
"authority pre-checks are economy, never correctness" holds — nothing
upstream of retirement can be load-bearing.

## 3. The Navigator's cell insight

> The chronicle and the ledger are like a cell — indivisible. But
> cells can exist inside another one.

Formalized: a **cell** is one (chronicle, ledger) pair — one engine
instance with its History and the operational machinery that feeds
it. Cells do not share their interior. A cell's *world* — the thing
its gates act on and its ingress observes — can itself contain other
cells. That containment is the **tower**:

```diagram
┌─ META CELL (world = the set of epoch instances) ──────────────────┐
│  ledger: which instances existed, why spawned, why abandoned      │
│  chronicle: advisory cancels sent, seeds built, GC                │
│                                                                   │
│  transitions: observe authority change → [abandon old][seed new]  │
│  "abandon" is an ordinary ACTIVITY: idempotent, at-least-once,    │
│  classified — to the meta net, killing an instance is exactly     │
│  what posting a comment is to the domain net                      │
└───────────────┬───────────────────────────────────────────────────┘
                ▼ holds handles, never reaches inside
┌─ EPOCH CELL (world = GitHub) ─────────────────────────────────────┐
│  ledger: domain History under ONE fixed authority                 │
│  chronicle: worker attempts, retries, spends                      │
│  gates: comment (lookup-first), git (CAS)                         │
│  contains NO epoch, NO staleness, NO drain, NO dormancy           │
└───────────────────────────────────────────────────────────────────┘
```

Properties that make the tower composable:

- **Each level is internally pure.** No level expresses its own
  cancellation — the meta-circularity limit (a program cannot express
  its own SIGKILL; a formalism needs an interpreter outside itself —
  Smith's reflective towers). Kill is foreign to the epoch net and
  native-as-an-effect to the meta net. The "conflict of natures"
  dissolves because no conflict exists *within* a level.
- **Reasoning is restored level by level.** Replay the meta ledger to
  know which nets existed and why; replay any epoch ledger to know
  what happened inside it. Reading order, not archaeology.
- **Replay never "passes the drop."** Abandonment is the absence of
  further events plus a terminal meta-event explaining why. Nothing
  is truncated or deleted; a dead epoch replays as safely as a
  finished one.
- **Complexity moves from O(every net) to O(one runtime).** The
  braided staleness layer today would recur in every authored net.
  As a meta net it is written once, domain-free — a general primitive
  for any epoch-shaped authority.

## 4. The residues — what the kill cannot do

Honest limits, so the experiments don't cheat:

1. **Effects in flight.** You can kill bookkeeping, not the world. An
   agent run or HTTP POST launched under epoch N may land after the
   kill (at-least-once guarantees it eventually will). The gates
   remain unchanged and load-bearing: orphaned workers hit CAS /
   lookup-first and classify harmlessly (`moved`, absorbed,
   "outdated"). AX5 probes exactly this.
2. **Cancellation is advisory.** Send the cancel to the dispatcher
   for economy (stop burning money); never wait for confirmation —
   waiting rebuilds distributed consensus. Delivery-at-checkpoints,
   safety-at-brackets (async exceptions, structured concurrency); the
   bracket here is the gate.
3. **Cross-epoch continuity becomes a visible seed.** Repair lineage,
   dispositions, reminder notes, the human mirror — whatever must
   survive the kill is synthesized by the meta cell into the new
   instance's **birth payload**. Discipline: the seed is exactly the
   union of the concerns' `resume()` outputs, nothing more, or it
   degenerates into a God token. What survives is a *product
   decision*, now forced into one typed value.
4. **Between instances, someone must still answer.** Read-only
   replies and durable notes are head-indifferent (ES-004 AX7 effect
   grades) and live beside the tower, not inside any epoch cell.

## 5. The layer variants to test

**V2 — two nets per PR.**

```text
case net   (one per PR, long-lived)     the meta cell:
           PR lifecycle (active / dormant / terminal) + epoch
           management (spawn, abandon, seed) + cross-epoch folds
work net   (one per epoch, disposable)  the epoch cell:
           review · actions observe/rerun/repair · head-bound
           conversation execution · publications · readiness
           — under ONE fixed authority, no staleness constructs
```

**V3 — three nets per PR.**

```text
pr net        lifecycle only: active / dormant / terminal
epoch net     authority management: spawn / abandon / seed
work net      as in V2
```

The open question V2-vs-V3 decides: does separating "is the PR alive"
from "which authority is current" pay its coordination cost, or is
lifecycle just three more rows in the case net's transition table?

**Open product/definition choices** (Navigator rules these, the
experiments must surface them):

- What advances the epoch — head only (base moves stay a stamped
  comparison inside the work net), or the full authority tuple
  (head, base_head, policy_digest → any change kills)? Maximal
  simplicity vs instance churn.
- Late-append policy: refuse appends to dead instances vs a
  graveyard log.
- Seed contents per concern (the `resume()` census).
- Timer ownership across instances (a reminder armed in epoch N
  maturing in epoch N+2).

## 6. What "simple" means here — the measures

Per net: `P`, `T`, `A`, `arcs/(P+T)` (target ≈ 1 for work nets),
read-arc count (target 0 staleness reads), guard count and what each
guard is *about* (domain vs bookkeeping), and the construct census —
which spec-DSL features each net actually needed (`arc.read`,
filters, multi-input transitions, scopes, timers). The census feeds
the reframe hypothesis: if work nets need only linear chains, typed
outcome fan-out, and gates, the primitive set for the authoring layer
shrinks accordingly, and blocks/combinators get re-derived from
evidence instead of assumed.

Comparison baseline: former production
`src/hamsterdan/readiness/net/topology.py` in pre-consolidation Git history
(~30+ places, 94 read arcs measured in ES-004 AX5) and the ES-005
[chapter 17](../es5-design-primer/17-hamsterdan-rebuild-brief.md)
contract, which the layered nets must still honor clause by clause.

## 7. Literature index

For future digging — the names behind each piece:

- **Optimistic concurrency control:** H.T. Kung, J.T. Robinson, "On
  Optimistic Methods for Concurrency Control" (1981) — commit-time
  validation; the git gate is OCC.
- **STM:** T. Harris, S. Marlow, S. Peyton Jones, M. Herlihy,
  "Composable Memory Transactions" (2005) — speculation, abort,
  retry; aborted runs absent from logical history.
- **MVCC:** snapshot isolation; instance-per-epoch is MVCC for nets.
- **Asynchronous exceptions:** S. Marlow, S. Peyton Jones, A. Moran,
  J. Reppy, "Asynchronous Exceptions in Haskell" (2001) — masking,
  brackets, interruptible points; cancellation delivered, not
  enforced.
- **Structured concurrency:** M. Sústrik (libdill essays), N. Smith
  (Trio nurseries, "Notes on structured concurrency"), R. Elizarov
  (Kotlin coroutines) — cancellation scopes as trees.
- **Sagas / compensation:** H. Garcia-Molina, K. Salem, "Sagas"
  (1987) — should in-flight work finish, at business scale.
- **Reset nets / cancellation:** C. Dufourd, A. Finkel, Ph.
  Schnoebelen, "Reset nets between decidability and undecidability"
  (1998); van der Aalst & ter Hofstede, YAWL cancellation regions —
  why kill does not belong inside the net.
- **Reflective towers:** B.C. Smith, "Reflection and Semantics in
  LISP" (1984) — a formalism needs an interpreter outside itself.
- **Coeffects:** T. Petricek, D. Orchard, A. Mycroft, "Coeffects: a
  calculus of context-dependent computation" (2014) — typed context
  requirements that compose (the Q1 answer).
- **Workflow nets:** W. van der Aalst, "The Application of Petri Nets
  to Workflow Management" (1998); dynamic change: C. Ellis, K.
  Keddara, G. Rozenberg, "Dynamic change within workflow systems"
  (1995) — the seed-token problem under the name "process instance
  migration".
- **Speculative execution / retirement:** reorder buffers; architectural
  state advances only at retirement — the hardware isomorph of gates.
