# ES-005 — The design primer: consolidated learning for the design phase

**Status:** Candidate — the consolidation of ES-001–ES-004 learning
that matters for the future, 2026-08-14.
**Sources:** everything that *earned trust* across
[ES-001](../es1-petri-net-motus-boundary/index.md) (boundary
ownership), [ES-002](../es2-imperative-expression-layer/index.md)
(expression economics), [ES-003](../es3-workflow-ast-authoring-model/index.md)
(the authoring algebra, AX0–AX29), and
[ES-004](../es4-hamsterdan-experience-specification/index.md) (the
boundary-derived experience, AX0–AX12). Negative results, dead ends,
and exploration narrative are deliberately absent — they live in the
source syntheses. This is only what to rely on.

## What this is for

The explorations answered "what works?" by trying things. The design
phase asks a different question: "what should *I* build, and how do
the pieces relate?" This primer teaches each keepable finding as an
isolated concept — technically and conceptually — so a net can be
designed from a spec (Given/When/Then user stories) by a person, step
by step, without reading any spike code.

Every concept file has the same shape:

```text
What it is            two or three sentences
The idea              pseudocode — teaching shape, NOT an API
What it does not do   the concept's deliberate limits
How it relates        links to the sibling concepts
Why trust it          one-line evidence with a pointer to the record
```

Structural concepts (3–8) additionally carry a **"What it compiles
to"** section: the exact places/transitions/arcs the construct
becomes, with the shared mechanics in
[chapter 16](16-how-the-authoring-compiles.md).

**All pseudocode here is one normalized vocabulary**, chosen for
teaching. The spikes use several evolving APIs; this primer uses one.
Snippets are labeled by fidelity — *teaching shape* (normalized),
*condensed exact* (shortened spike code, same names and refusals),
*exact current Petrus syntax* (build-verified by
[test_refund_netspec.py](test_refund_netspec.py)), or *derived*
(lowering rules applied by hand). The vocabulary mapping, once:

| Primer word | Meaning | Proven as |
|---|---|---|
| `Port(name, Type)` | a typed, named door | ES-003 AX22, ES-004 AX11 |
| `Block` | function-shaped subnet: one entry, named exits | ES-003 AX22/AX23 |
| `step(name, fn)` | pure 1→1 leaf | `transform`, ES-003 AX22 |
| `outcomes(name, fn, ...)` | 1→n typed routing leaf | `classify`, ES-003 AX22 |
| `then(a, b, on=)` | fuse exit port to entry port | ES-003 AX22 |
| `par(name, branches)` | AND-split + explicit join | ES-003 AX24 |
| `loop(block, on=)` | fuse an exit back to the entry | ES-003 AX23 |
| `holding(block, resource=)` | claim bracket / structural mutex | ES-003 AX20/AX23 |
| `attempt` / `recover` | failure rail sugar | ES-003 AX25 |
| `fold` / `decide` | event projection + pure decisions | ES-004 AX8 |
| `run(block, data)` | one call to first motion | `first_motion`, ES-003 AX28 |

## Reading order

Foundations — the ground truths everything sits on:

1. [The engine contract](01-engine-contract.md) — history is the
   truth; determinism is a duty; replay is recompile-and-reload.
2. [Work and routing](02-work-and-routing.md) — the net routes,
   workers work; attempt-first; the two idempotency kinds.

Structure — how a good net is shaped:

3. [Blocks](03-blocks.md) — work is function-shaped; control may only
   call functions.
4. [Composition](04-composition.md) — names give topology; types give
   compatibility; nothing is wired by type-matching.
5. [Branching](05-branching.md) — modeled outcomes, value guards, and
   the hybrid.
6. [Parallel](06-parallel.md) — split, explicit join policy, and
   correlation.
7. [Cycles](07-cycles.md) — loops from trees; where loop state lives.
8. [The failure rail](08-failure-rail.md) — the unmodeled failure
   lane.
9. [Gates and disposability](09-gates-and-disposability.md) — the
   only two ways work becomes world-visible; everything before a gate
   is discardable.
10. [Control and epochs](10-control-and-epochs.md) — a small control
    machine; staleness made unexpressible; the arcs-per-node signal.
11. [Fold and decide](11-fold-and-decide.md) — the projection pattern
    that dissolves in-flight flags.
12. [Time](12-time.md) — timers as just another provider.

Surfaces — what surrounds an authored net:

13. [Validation](13-validation.md) — the four-rung ladder, and
    governed descent below the algebra.
14. [Run, replay, evolve](14-run-replay-evolve.md) — one call to
    motion; nets that grow under the same name.

Method — the payoff:

15. [From spec to net](15-from-spec-to-net.md) — mapping
    Given/When/Then to entries, steps, exits, and gates; a worked
    example carried all the way down to today's spec DSL; the design
    checklist.
16. [How the authoring compiles](16-how-the-authoring-compiles.md) —
    the lowering rules behind every "What it compiles to" section:
    leaves add nodes, composition only renames, the node economy, and
    the staged pipeline from expression to replayed marking.
17. [The Hamsterdan rebuild brief](17-hamsterdan-rebuild-brief.md) —
    how the Hamsterdan net behaves (the boundary-confirmed contract as
    Given/When/Then), the NET-DECIDED design space, the proven
    control-place simplifications, and the target shape — everything
    needed to design your own version with chapter 15's method.

## How the concepts relate

```diagram
                        ┌───────────────────────────┐
                        │ 15 FROM SPEC TO NET       │  method
                        │ 16 HOW IT COMPILES        │
                        │ 17 HAMSTERDAN BRIEF       │
                        └─────────────┬─────────────┘
              ┌───────────────────────┼──────────────────────┐
              ▼                       ▼                      ▼
   ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
   │ STRUCTURE          │  │ STATE PATTERNS     │  │ SURFACES           │
   │ 3 blocks           │  │ 9 gates            │  │ 13 validation      │
   │ 4 composition      │  │ 10 control/epochs  │  │ 14 run/replay/     │
   │ 5 branching        │  │ 11 fold+decide     │  │    evolve          │
   │ 6 parallel         │  │ 12 time            │  │                    │
   │ 7 cycles           │  │                    │  │                    │
   │ 8 failure rail     │  │                    │  │                    │
   └─────────┬──────────┘  └─────────┬──────────┘  └─────────┬──────────┘
             └────────────────┬──────┴───────────────────────┘
                              ▼
                 ┌───────────────────────────┐
                 │ FOUNDATIONS               │
                 │ 1 engine contract         │
                 │ 2 work and routing        │
                 └───────────────────────────┘
```

## Where the depth lives

When a concept here is not enough, the owning syntheses carry the full
evidence, captures, and the rejected alternatives:

- ES-003 [synthesis](../es3-workflow-ast-authoring-model/synthesis/index.md)
  — the algebra, walkthrough, spec, recommendations (D1–D9 open
  decisions).
- ES-004 [synthesis](../es4-hamsterdan-experience-specification/synthesis/index.md)
  — the boundary-derived experience spec and the one-PR walkthrough.
- ES-001 [record](../es1-petri-net-motus-boundary/index.md) — which
  layer owns which execution mechanics.
- ES-002 [record](../es2-imperative-expression-layer/index.md) — why
  fewer authoring lines is never the goal.
