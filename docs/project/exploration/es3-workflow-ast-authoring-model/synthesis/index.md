# ES-003 Synthesis — what 30 experiments taught us

**Status:** candidate synthesis for Navigator review. First issued
2026-08-12 over AX0–AX26; extended 2026-08-13 to fold in the final
probe arc (AX27–AX29) and the closing
[recommendations](06-recommendations.md).
**Supersedes:** [AX12](../experiments/ax12-recommendation/index.md), which
was an early recommendation *snapshot* taken at the series midpoint
(after AX0–AX11, before composition, the kernel, blocks, parallel
policies, the failure rail, and static typing existed). AX12 stands
unedited as a historical record; this synthesis is the current story.

## Who this is for

A Python-fluent reader who knows only basic Petri-net vocabulary —
place, transition, token, arc — and has read **zero** code from this
repository and **neither** the ES-002 nor ES-003 records. Everything
needed is quoted or explained inline; source links are for digging
deeper, not prerequisites.

Two sentences of grounding so nothing later surprises you:

- **Petrus** is this project's event-sourced Petri-net engine. A net is
  places (typed token containers), transitions (things that fire when
  their input places hold suitable tokens), and arcs (the wiring, which
  can carry filters). Every firing appends records to an immutable
  History; replaying the History over the same net reconstructs the
  exact state. Side-effecting work ("activities") is dispatched to
  workers outside the net.
- **The inquiry:** the current way to author a net is low-level — you
  write every place, transition, arc, guard, and callback by hand. ES-003
  asked whether that representation can become an internal one, with
  processes authored through a higher-level embedded Python DSL that
  *compiles* to it. Thirty experiments (AX0–AX29) tested that
  hypothesis in small, reversible spikes. Petrus itself stayed frozen at
  one pinned commit throughout; not one runtime change was needed.

## Reading order

| Doc | Lens | Read it to learn |
|---|---|---|
| [01-experiment-map.md](01-experiment-map.md) | What we did | Every experiment's question, verdict, and takeaway — and exactly what to read if you want to dig into one. |
| [02-what-did-not-work.md](02-what-did-not-work.md) | Negative results | The designs we tried and rejected, each with the code and the evidence that killed it. |
| [03-what-worked.md](03-what-worked.md) | Positive results | The patterns that survived contact with the frozen engine, each with the code that proves it. |
| [04-end-to-end-walkthrough.md](04-end-to-end-walkthrough.md) | How it works | One canonical workflow traced through every intermediate representation: authoring expression → typed value → block → kernel nodes → serialized net → execution trace → history → replay. Real captured output, not idealized. |
| [05-unified-candidate-spec.md](05-unified-candidate-spec.md) | The proposal | The cherry-picked unified design — layer model, primitives, combinators, sugar, types, guards, validation — every feature annotated with the experiment that proved it. **A candidate for discussion, not a decision.** |
| [06-recommendations.md](06-recommendations.md) | The recommendations | Every recommendation the series supports, argued from quoted code as facts — for, against, cost — plus the consolidated list of decisions only the Navigator can make. |

Read 01 first for the map. If you want to *understand the design*,
read 04 (the walkthrough) before 05 (the spec). 02 and 03 are
reference lenses you can read in either order. 06 is the closing
argument — read it last, after the spec.

## The four arcs

The 30 experiments read best as four narrative arcs:

```diagram
┌───────────────────────────┐  ┌────────────────────────────┐  ┌─────────────────────────────┐
│ Arc 1: FOUNDATIONS        │  │ Arc 2: COMPOSITION         │  │ Arc 3: COMPOSABLE FUNCTIONS │
│ AX0–AX12                  │  │ AX13–AX23                  │  │ AX24–AX26                   │
│                           │  │                            │  │                             │
│ Can an AST lower onto     │  │ What is the right unit of  │  │ What does a proven TS       │
│ the frozen engine at all? │  │ composition? Blocks with   │  │ library teach us? Parallel  │
│ Types, parallel, guards,  │  │ ports; a generic kernel;   │  │ policies, the failure rail, │
│ loops, effects, styles,   │  │ claim/fence; typed         │  │ and static typing with      │
│ one real fragment.        │  │ outcomes; a full algebra.  │  │ pyright and ty.             │
└───────────────────────────┘  └────────────────────────────┘  └─────────────────────────────┘
                                        │
                                        ▼
                    ┌────────────────────────────────────────────┐
                    │ Arc 4: PROGRESSIVE DISCLOSURE               │
                    │ AX27–AX29                                   │
                    │                                             │
                    │ Does the algebra meet the governing DX      │
                    │ target? Generated authoring against the     │
                    │ composition authority; one file to first    │
                    │ motion; the governed descent seam down      │
                    │ to kernel authoring.                        │
                    └────────────────────────────────────────────┘
        every AX verdict: "Promising; continue" except AX9 ("Promising with changes")
                        and AX12 ("Promising with changes", superseded)
```

- **Arc 1 (AX0–AX12)** proved the mechanism: a workflow AST can lower
  deterministically onto the frozen engine, byte-identical on
  recompilation, with typed ports, guards compiled to CEL, cycles from
  a tree-shaped AST, and full source mapping — and it measured honestly
  that the win is *safety and explicitness*, not fewer lines.
- **Arc 2 (AX13–AX23)** found the right unit: not a workflow-shaped
  AST but **blocks** — function-like subnet values with one typed
  entry, named typed exits, declared contexts, and purity metadata —
  composed by port fusion under a small combinator algebra
  (`then`, `merge`, `loop`, `holding`, `disposable`), lowered through a
  net-agnostic kernel IR. This realized the Navigator's structural
  intuition: *control statements may only call functions*.
- **Arc 3 (AX24–AX26)** stress-tested the algebra against
  [Composable Functions](../composable-functions.md) (seasonedcc,
  TypeScript): parallel with explicit join policies (`par` /
  `par_fail_fast`), railway-oriented failure as pure sugar, and a
  typed façade that moves most composition errors into the editor
  (pyright catches 8/9; ty currently 4/9; the deterministic compiler
  stays the authority).
- **Arc 4 (AX27–AX29)** tested the algebra against the Navigator's
  governing DX product target (recorded in the
  [exploration index](../index.md)): the composition authority behaves
  as a machine feedback loop for *generated* authoring (total staged
  review; five of ten refusals carry the remedy verbatim; review
  provably never executes the net); one general `first_motion` call
  takes any Block to a quiescent, replayable instance (33
  hand-composed `Engine.create` sites collapse to one imported
  infrastructure name); and descent to kernel authoring composes under
  a two-depth law without weakening a single check.

## Ground rules that held for all 30 experiments

- Petrus frozen at `3b41f19aa68ed228e68324f7c6888371f805b560`; zero
  runtime changes made or needed. Speculation lives only in the
  [Petrus speculation ledger](../petrus-speculation.md).
- Production `topology.py` never modified; it served as the parity
  oracle (AX11/AX13/AX15 reproduce real fragments token-for-token).
- Every experiment: one question, smallest prototype, focused tests,
  recorded verdict before the next began. 427 exploration tests passed
  at the AX26 mark; 599 pass at the AX29 close.
- Literature trail in [theory-references.md](../theory-references.md);
  external-design comparison in
  [composable-functions.md](../composable-functions.md).
