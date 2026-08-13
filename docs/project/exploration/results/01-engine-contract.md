# 1 — The engine contract

**Rely on this: the History is the only durable truth, and everything
you author must be deterministically reproducible from source.**

## What it is

A net is places (token containers named by a *color* — a nominal type
name), transitions (they fire when their input places hold suitable
tokens), and arcs (the wiring; an arc can carry a value filter). Every
firing appends immutable records to a History. The engine never stores
the net itself in the History — only what happened.

That absence is the load-bearing fact. To recover an instance, the net
is rebuilt *from source* and the History is replayed over it. So the
authoring layer carries a duty: **same source must produce a
byte-identical net, every time.** Frozen values, stable ordering, no
randomness, no wall-clock reads during construction.

## The idea

```text
author source ──compile──▶ net definition (canonical bytes)
                              │
                     run: fire transitions, append records
                              ▼
                          History (immutable, the truth)

recover = compile(source again) + replay(History)  ⇒  identical marking
```

External input enters through one door, with a deduplicating identity:

```python
engine.deliver(transition, data, identity="webhook:{delivery_id}")
# same identity delivered twice → second one is inert
```

## What it does not do

- The History does not describe the net; it cannot detect an authoring
  layer that compiles differently on Tuesday. Determinism is *your*
  duty, enforced by asserting byte-equality of recompiled definitions.
- Replay does not re-execute side effects; it re-derives the marking.
  Effects live outside (concept 2).
- Colors are names, not structures. Two different meanings sharing a
  color are indistinguishable to the engine — name them apart.

## How it relates

- Concept 2 puts side-effecting work outside this contract.
- Concept 14 turns replay and determinism into a one-call surface.
- Concept 15's checklist starts here: name your colors first.

## Why trust it

Proven by asserting `compile(source) == compile(source)` at the byte
level in every ES-003 arc, and replay-to-identical-marking on the real
engine throughout (ES-003 AX2/AX17/AX28; the whole pipeline captured in
the [ES-003 walkthrough](../es3-workflow-ast-authoring-model/synthesis/04-end-to-end-walkthrough.md)).
