# AX4 — Production vs the tower: numbers, census, primitives

**Question.** Measured with the same instruments, what does the
layered decomposition actually buy — and which authoring primitives
does a net genuinely need once the braid is gone?

**Method.** The quarantine lifted: production `topology.py` opened
for the first time in ES-006 and measured read-only with AX1's
helpers. Every number is pinned by
[test_ax4_comparison.py](test_ax4_comparison.py) — 5 tests, all
passing. Production behavior untouched.

## The numbers

| net | P | T | A | ratio | read | guards | filters | fragments | cyclic |
|---|---|---|---|---|---|---|---|---|---|
| **production** (one braided net) | 46 | 69 | 309 | **2.687** | **94** | **48** | 0 | 1 | yes |
| **V2 case net** (AX2 grid) | 13 | 9 | 31 | 1.409 | 0 | 0 | 0 | 1 | state-confined |
| **V2 work net** (AX1 explicit) | 59 | 21 | 68 | 0.850 | 0 | 0 | 0 | 12 | no |
| **V2 total** | 72 | 30 | **99** | — | **0** | **0** | 0 | 13 | — |
| V3 total (AX3, rejected) | 83+ | 44+ | 150+ | — | 0 | 0 | 0 | — | — |

Same product contract (ES-005 ch. 17, boundary-derived). The tower
needs **a third of the arcs, zero of the 94 read arcs, zero of the
48 guards**. V2 has *more places* than production (72 vs 46) — and
that is the point: places are cheap named facts; production's cost
lives in its 309 arcs and 94 reads, the connectivity that makes every
concern depend on everything. Production is one fragment — nothing
can be read, tested, or replayed alone; V2 is a 22-node case net plus
twelve isolated pipelines, each ≤ 10 nodes.

Fan-in tells the same story: production joins 2 tokens at 19
transitions, 3 at 7, and 8 at one; its `admission` place feeds 7
competing transitions. V2's work net has fan-in nowhere; its case net
joins exactly (state, fact) pairs.

## Where production's 94 reads and 48 guards went

| production construct | where it lives in the tower |
|---|---|
| staleness read arcs + `_current` guards (42 reads — ES-004 AX5) | **nonexistence** — the stale instance is gone (case net kills; work net never knows) |
| lifecycle flags (dormant, provisional, drain, seed places) | 3 state places + 6 grid transitions in the case net |
| `*_in_flight` / dedup snapshot reads | fold over settled exits (pure control layer, no places) |
| routing guards on shared places | typed entry colors per pipeline (`decide` emits the right color) |
| fences as topology | data comparison in `head_check`'s pure handler + the gates |
| the repair loop cycle | acyclic pipeline; iteration = the next generation arriving |

## Arc density as diagnosis

```text
ratio < 1     work        (pipelines: 0.83-0.85)
ratio ~ 1.3-1.4  coordination (one state cell, confined)
ratio ~ 2.7   braid       (work and coordination in one topology)
```

The Navigator's original proportion hunch, made precise: high
arcs/(P+T) is not "too many arcs", it is *coordination leaking into
work*. Health = confining ratio > 1 to one small net.

## The primitive census — what authoring actually needs

Everything AX1-AX3 built used exactly this subset of the spec DSL:

```text
NEEDED                                  NOT NEEDED ANYWHERE
typed places        p.name(Color)       arc.read()
handler transitions t.name(handler=)    arc.inhibit()
consume arcs        >>                  CEL arc filters
colored fan-out     t >> (a, b, c)      guards
multi-input (state, fact) pairs         weights
scopes for naming   s.concern           timers (deferred: open Q)
initial marking as birth
```

Re-derived primitives for a future authoring layer — from evidence,
not assumption:

1. **The pipeline** — `entry ─▶ steps ─▶ typed exits`. Sequence +
   typed outcome fan-out. Covers every effect concern (ES-003's
   `then`/rail survive; most other combinators were braid-serving).
2. **The state cell** — state places held (consumed-and-returned) by
   (state, fact) transitions. One per net, small. Subsumes ES-003's
   `holding`; the grid form needs no guards when ingress is typed.
3. **The gate** — a transition whose handler is attempt-first and
   whose exits classify (`committed | moved | blocked | fault`).
   A pipeline step, distinguished by contract, not topology.
4. **Typed ingress and `decide`-seeded entries** — classification
   happens before the net; tokens arrive already typed. This is what
   eliminated filters and guards.
5. **The tower** — nets managing nets, split **by world, not by
   topic** (AX3's negative result): a level earns its existence by
   owning a world the level below cannot see.

Parallel split/join, exclusive choice in-net, loops, retries-as-
topology: none appeared. Join = fold; choice = typed exits; loop =
provider-owned state or next generation; retry = dispatcher.

## Honest limits

- Shape evidence only: handlers are symbolic; dispatch, replay, and
  the instance-spawning machinery (the case net's activities) are
  unproven here. AX5 probes the kill residue; the spawn/route/GC
  runtime is real work the tower requires from Petrus.
- More instances = more Histories: per-epoch storage and the meta
  ledger's growth are unmeasured operational costs.
- The 99-arc V2 counts symbolic handlers; production's guards encode
  real logic that moves into pure handlers and `decide` — code that
  still exists, just testable as functions instead of topology.

## Verdict

**Promising; continue.** The braid was coordination, not domain: same
contract, one third of the arcs, zero reads, zero guards, and a
five-primitive census for the authoring layer. V2 (case + work) is
the recommended shape; V3 rejected.
