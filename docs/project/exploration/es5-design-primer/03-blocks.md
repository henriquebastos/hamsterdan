# 3 — Blocks

**Rely on this: work is function-shaped — one typed entry, named typed
exits — and control flow may only call functions.**

## What it is

The unit of design is not a place or a transition; it is a **block** —
a subnet that behaves like a function. A token enters through one
typed door, work happens inside, and the token leaves through exactly
one of several *named, typed* exits. What happens next is never the
block's business: the routing layer alone decides.

This one constraint restores the linearity the low-level net lacks.
Interiors stay private; only ports are public; and any ambient state a
block touches must be *declared* — an undeclared dependency is refused.

## The idea

```python
Block(
    name="review_findings",
    entry=Port("in", ReviewJob),
    exits={
        "findings":  Port("findings", Findings),
        "clean":     Port("clean", CleanReview),
        "discarded": Port("discarded", Discarded),   # authority moved → drop
    },
    pure=False,                    # metadata with teeth (see below)
    contexts={},                   # ambient reads/holds, declared or refused
)
```

Two brackets refine the shape:

```python
disposable(block)                  # refuses impure blocks: this work may be
                                   # freely re-run and thrown away
holding(block, resource="claim")   # structural mutex: consume the resource
                                   # token at entry, return it at every exit
```

## What it does not do

- A block does not know its neighbors, the workflow, or any provider.
- Purity is declared, not verified — the algebra refuses *using* an
  impure block where purity is required, but does not inspect bodies.
- A block does not expose its interior places; debugging goes through
  exits and the source map, not through reaching inside.

## What it compiles to

A block *is* net structure — its entry and exits are real places, its
work is one or more transitions between them. The two leaf shapes:

```diagram
step:      ┌────────┐   ┌───────┐   ┌────────┐
           │ in (A) │──▶│ work  │──▶│ out(B) │        2 places, 1 transition
           └────────┘   └───────┘   └────────┘

outcomes:  ┌────────┐   ┌───────┐──▶ findings (Findings)
           │ in (A) │──▶│ work  │──▶ clean (CleanReview)
           └────────┘   └───────┘──▶ discarded (Discarded)
                        one exit place PER named exit; the transition
                        emits exactly one token per firing
```

Mechanics and condensed-exact pseudocode:
[chapter 16](16-how-the-authoring-compiles.md). Exact code:
[ax23_blocks.py](../es3-workflow-ast-authoring-model/experiments/ax23-completed-algebra/ax23_blocks.py)
(`transform`, `classify`, `holding`).

## How it relates

- Concept 4 composes blocks by fusing ports.
- Concept 9's disposability doctrine says *which* blocks should be
  pure: everything before a gate.
- Concept 13's soundness check enforces the shape (every interior node
  on some entry→exit path).

## Why trust it

ES-003 AX22/AX23 built and ran the full algebra over this shape; AX20
proved the claim bracket and disposable interior on the real engine.
ES-004 AX1/AX2 re-derived the same shape independently from the
product boundary ("secure entry/exit contracts") — two explorations,
one convergent unit.
