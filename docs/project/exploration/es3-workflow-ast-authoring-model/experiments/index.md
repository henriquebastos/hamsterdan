# ES-003 — Authoring-model experiment series (AX)

A sequence of small, isolated, reversible design experiments testing whether
the current low-level Petrus DSL can become an internal representation while
processes are authored through a higher-level embedded Python DSL:

```text
Activities describe work.
Combinators describe process structure.
The Python DSL constructs a workflow AST.
A compiler lowers the AST into the existing Petri-net representation.
The existing event-sourced runtime, dispatcher, and workers execute it.
```

The series is numbered AX0–AX12 to stay distinct from ES-002's earlier
"Experiment 1" (the combinator-regeneration experiment, closed 2026-08-11
with the universal-combinator approach rejected), whose evidence binds
this series as prior art.

## Series rules

1. Each experiment answers one stated design question with the smallest
   useful prototype, evaluated before the next begins.
2. Everything — records, spike code, tests — lives inside this experiment
   directory tree. Production code and `topology.py` are never modified;
   the production net remains the comparison oracle.
3. Petrus is frozen at the pinned baseline
   `3b41f19aa68ed228e68324f7c6888371f805b560`. Experiments lower only onto
   the existing public surface. Evidence that suggests a Petrus runtime
   change goes into the [Petrus speculation ledger](petrus-speculation.md)
   as analysis, never into an experiment's implementation.
4. Prior ES-002 evidence binds the series: first use the smallest existing
   Petrus expression that says the truth directly; a new surface must
   eliminate a demonstrated burden, not merely rename fluent wiring.
   The closed combinator experiment showed the pain is binding plumbing and
   per-concern fragment repetition, not `>>` arcs — the AX series tests the
   different hypothesis that an authoring-forward AST (not regeneration of
   the hand-written topology) changes those economics.
5. No text parsers. Embedded Python object construction only.
6. No live generator or coroutine frame may become durable workflow state.
7. Spike tests run with
   `uv run --frozen pytest -q docs/project/exploration/es3-workflow-ast-authoring-model/experiments/`.
8. Each experiment record ends with one verdict: Promising; continue —
   Promising with changes — Not useful enough — Incompatible with the
   current architecture.
9. Spike module and test filenames carry their experiment prefix
   (`ax2_compiler.py`, `test_ax2_compiler.py`): all spike directories
   share one pytest run, so bare module names collide across experiments
   (learned in AX2).

## Experiments

| # | Question | State | Verdict |
| --- | --- | --- | --- |
| [AX0](ax0-architecture-map/index.md) | Architecture map and baseline example | Completed | Baseline selected |
| [AX1](ax1-minimal-ast/index.md) | Minimal workflow AST (Activity/Sequence/Parallel) | Completed | Promising; continue |
| [AX2](ax2-lower-sequence/index.md) | Lowering Activity and Sequence to `Net` | Completed | Promising; continue |
| [AX3](ax3-typed-ports/index.md) | Typed activities, ports, basic inference | Completed | Promising; continue |
| [AX4](ax4-parallel-join/index.md) | Parallel split, execution, join | Completed | Promising; continue |
| [AX5](ax5-type-branching/index.md) | Branching by output type | Completed | Promising; continue |
| [AX6](ax6-guard-branching/index.md) | Guard-based branching, predicate AST → CEL | Completed | Promising; continue |
| [AX7](ax7-hybrid-routing/index.md) | Hybrid type + guard routing | Completed | Promising; continue |
| [AX8](ax8-loops-retries/index.md) | Loops, cycles, retries | Completed | Promising; continue |
| [AX9](ax9-effect-authoring/index.md) | Effect-oriented activity authoring | Completed | Promising with changes |
| [AX10](ax10-authoring-styles/index.md) | Python authoring-style comparison | Completed | Promising; continue |
| [AX11](ax11-real-fragment/index.md) | Leading design on the real baseline fragment | Completed | Promising; continue |
| [AX12](ax12-recommendation/index.md) | Architecture recommendation (synthesis snapshot) | Completed | Promising with changes |
| [AX13](ax13-sibling-amortization/index.md) | Sibling amortization: marginal cost of the second concern | Completed | Promising; continue |
| [AX14](ax14-fragment-composition/index.md) | Fragment composition by explicit named-port identity | Completed | Promising; continue |
| [AX15](ax15-recovery-concern/index.md) | Production's hardest guard as a composed recovery concern | Completed | Promising; continue |
| [AX16](ax16-null-safety-validation/index.md) | Null-safety as validation over CEL absorption semantics | Completed | Promising; continue |
| [AX17](ax17-net-evolution/index.md) | Net evolution: one durable history across two compositions | Completed | Promising; continue |
| [AX18](ax18-generic-kernel/index.md) | Generic kernel: net-agnostic IR beneath the domain sugar | Completed | Promising; continue |

## Standing inputs from prior ES-002 evidence

- Guard decomposition audit: 45 of 48 guarded transitions decompose into
  four decidable atom kinds; only two genuinely opaque atoms exist. Direct
  input to AX6/AX7 — a predicate AST needs exactly those atoms, and CEL
  (currently unused by the production net: 0 filter declarations) is the
  candidate execution backend to test.
- RS-014/RS-015/RS-016/RS-017: typed direct transformations and public
  `typed_guard` already removed the accidental binding plumbing. The AX
  series measures against this improved baseline, not the older one.
- `stateless` and the durable-execution literature: syntax reference only;
  the Net stays the single durable workflow representation.
