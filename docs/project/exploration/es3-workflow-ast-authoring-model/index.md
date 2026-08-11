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
