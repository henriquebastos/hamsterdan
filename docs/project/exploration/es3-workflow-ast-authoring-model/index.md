---
status: Thickening
opened: 2026-08-11
navigator: Henrique
---

# ES-003 — Workflow AST authoring model compiled to the Petri net

## Inquiry

Can the current low-level Petrus DSL become an internal representation,
with processes authored through a higher-level embedded Python DSL — and
what is the right layered architecture if so?

```text
Activities describe work.
Combinators describe process structure.
The Python DSL constructs a workflow AST.
A compiler lowers the AST into the existing Petri-net representation.
The existing event-sourced runtime, dispatcher, and workers execute it.
```

In this model activities are AST leaves, combinators are internal nodes
defining topology, types validate compatibility and support local
inference (never sufficient identity for topology), guards may be Python
expression objects compiled to the existing CEL representation, and
effect-oriented or generator-based activity syntax is a separate
hypothesis to test — not an assumed foundation.

## Relation to ES-002

ES-002 asked how the existing readiness workflow should be written down
and answered by regeneration: its combinator experiment closed with the
universal-combinator approach rejected — the 14 fragment families were
domain vocabulary, the economics negative for a single net, and the real
pain was binding plumbing (since fixed at the right layer by
RS-014–RS-017). ES-003 tests a different hypothesis: an authoring-forward
workflow AST as intermediate representation, evaluated by design
experiments rather than by regenerating the hand-written topology.
ES-002's evidence binds this story as prior art: the guard decomposition
audit (45/48 guards decidable over four atom kinds), the
smallest-existing-expression rule, and the prohibition on live
continuation state.

## Method — experiment series AX

The story runs as a sequence of small, isolated, reversible design
experiments, AX0–AX12, each answering one stated design question with the
smallest useful prototype and a recorded verdict before the next begins.
Program, rules, and status: [experiments/index.md](experiments/index.md).
All records and spike code live inside this directory; production
`topology.py` is never modified and remains the comparison oracle.

## Navigator rulings — 2026-08-11

- The entire investigation is exploration work with every artifact inside
  this exploration directory.
- Petrus is frozen at the pinned baseline
  `3b41f19aa68ed228e68324f7c6888371f805b560` for all experiments.
  Speculation about Petrus runtime changes — for example binding real
  types instead of nominal color strings — is welcome as a dependent
  analysis result and accumulates in the
  [Petrus speculation ledger](petrus-speculation.md), never inside an
  experiment's implementation.

## Progress

- [AX0 — Architecture map and baseline example](experiments/ax0-architecture-map/index.md)
  completed 2026-08-11. Verified the architecture map against the pinned
  checkout; corrected the working premise (nominal string colors with no
  class registry; CEL present but unused by the production net;
  activities dispatched by occurrence ID with frozen results; the Net
  absent from History, so any compiler must be deterministic for replay);
  selected the actions failure → rerun-or-repair fragment
  (`topology.py` L1461–1476 plus its two activity bridges) as the
  baseline example for AX1–AX11.
- [AX1 — Minimal workflow AST](experiments/ax1-minimal-ast/index.md)
  completed 2026-08-11 — Promising; continue. Three frozen nodes
  (`Activity`/`Sequence`/`Parallel`) with structural identity, origin as
  non-identity metadata, deterministic walk paths as `NetPath` seeds, and
  an origin-free canonical form + fingerprint for compile-determinism
  checks. Fourteen tests pass. Honest gap carried to AX2/AX3: the AST
  omits exactly the data semantics (colors, transforms, join meaning)
  the current DSL forces you to write.
- [AX2 — Lowering Activity and Sequence onto the frozen Net](experiments/ax2-lower-sequence/index.md)
  completed 2026-08-11 — Promising; continue. The lowering contract is a
  threaded fragment (entry place in, exit place out; `Sequence` owns
  nothing). The ~200-line compiler produces nets byte-identical to the
  hand-written DSL equivalent, executes unmodified through
  `Engine`/`InlineDispatch`, replays over a recompiled net, fails loudly
  against divergent compilation, and carries a two-way source map
  (AST address ↔ generated paths ↔ authoring line). Duplicate activity
  occurrences bind safely by exact handler `NetUri`. Ten tests pass.
  AX3 next: derive colors from typed signatures instead of explicit
  `request=`/`result=` declarations.
- [AX3 — Typed activities, ports, and basic inference](experiments/ax3-typed-ports/index.md)
  completed 2026-08-11 — Promising; continue. `@activity` definitions
  already carry resolved hints, so inference needs no new machinery;
  single in/out, multi-input with distinct colors, sinks (as a signal),
  and async infer safely, while unions, optionals, and generics are
  refused with reasons and remedies. The mandated same-type-two-places
  case is refused loudly by the frozen derivation and resolved by a
  ~60-line place-bound port handler above the runtime — named ports need
  no Petrus change. Sink probe recorded as ledger SP-2. Fourteen tests
  pass.
- [AX4 — Parallel split, execution, join](experiments/ax4-parallel-join/index.md)
  completed 2026-08-11 — Promising; continue. The lowering contract
  generalizes to place sets; the split is an explicit `passthrough`
  transition and the join is the downstream multi-input activity's own
  transition — no hidden aggregator. Key findings: concurrency is
  driving-policy territory (`choose_conservative` serializes,
  `choose_throughput` parallelizes) so the authoring layer needs no
  concurrency syntax; terminal branch failure halts loud, poisons the
  Engine, and resumes via `Engine.load` with the sibling's result
  durably parked; a `-> None` branch terminates but cannot feed a join;
  and the cross-case join mispairing hazard was *proven* by crossed
  completions (ledger SP-3) — instance-per-case discipline, not types,
  provides correlation. Twelve tests pass.
- [AX5 — Branching by output type](experiments/ax5-type-branching/index.md)
  completed 2026-08-11 — Promising; continue. The runtime routes tokens
  by color through typed arcs natively — but silently drops what no arc
  admits, and union variant identity is erased at the worker boundary
  today. Both gaps close above the frozen runtime: a
  `VariantPayloadConverter` stamps a durable `$variant` discriminator
  (refusing subclasses and unlisted types loudly), and a routing handler
  projects to exactly the matching variant place. Branching is explicit
  (`switch`/`case`), with the union return as trigger and exhaustiveness
  validator; same-color case exits get an explicit XOR merge. Ledger:
  SP-1 evidence extended, SP-4 (strict routing mode) added. Nineteen
  tests pass.
- [AX6 — Guard-based branching with a single data type](experiments/ax6-guard-branching/index.md)
  completed 2026-08-11 — Promising; continue. A typed root proxy
  (`on(Application)`) builds a frozen predicate AST via operator
  overloading, validated against the dataclass at construction (unknown
  fields, constant type mismatches, unguarded optional fields all fail
  with remedies) and compiled to the bare-variable CEL dialect Petrus
  filters evaluate. Overlap policy decided explicitly: cases lower
  ordered-exclusive (each conjoined with prior negations) so first match
  wins deterministically on the frozen runtime, and `otherwise` is
  mandatory because a token no input arc admits parks silently. Input
  arcs proved to be competition, not duplication — the mirror of AX5's
  output-side drop (SP-4 extended). Lambda *tracing* works as sugar over
  the same objects; source inspection rejected. Thirty-five tests pass.
