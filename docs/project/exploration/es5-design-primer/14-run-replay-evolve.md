# 14 — Run, replay, evolve

**Rely on this: one call to first motion, replay as a method, and nets
that grow under the same name — the durable contract taught by using
it.**

## What it is

Running an authored block needs exactly one infrastructure name.
Everything the harness needs is already *on* the block: the entry port
says where the seed token goes and what color it must be (a wrong
injection is unrepresentable); the exits say where to observe; the
compiler carries the handlers and the soundness check.

```python
motion = run(workflow(), {"sku": "sku-1", "amount": 10.0})

motion.definition   # canonical net bytes — the replay contract's subject
motion.records      # the real History records
motion.settled      # token data at every named exit
motion.replay()     # recompile + reload history → marking equality, place by place
```

The four artifacts are the whole durable story: *definition
determinism + History = recoverable instance*. Driving is bounded — a
net that doesn't quiesce hits a budget and fails with a directed
diagnostic, never a silent spin. The history store is a visible
choice: in-memory when omitted, and it *says so*.

## Evolution

The net's **name is its process identity**. Evolving a live process
means compiling a new net under the same name over the same History:

- **Superset evolution** (adding places, transitions, exits) is
  zero-migration — old histories replay onto the grown net.
- **Narrowing** (removing what a history might reference) requires a
  whole-trace preflight — shaped by experiment, not yet built; treat
  it as a gap, not a feature.

Migration of an existing hand-written net follows the same physics:
re-author one concern, prove token-for-token parity against the
production oracle on the same scenarios, compose, repeat. No step is
irreversible.

## What it does not do

- No hidden durability: `run` defaults are labeled, never faked.
- No dispatched-activity workers in the minimal harness — wiring real
  workers adds dispatch bindings the surface must accept explicitly
  (a known bounded gap).
- Below-block splices (concept 13) have no ports, so no `run` — engine
  assembly there is honestly manual.

## How it relates

- Concept 1 is the contract this surface teaches.
- Concept 13's motion rung *is* this bounded driving.
- Concept 15's method ends every design with "run it, read the four
  artifacts, replay it."

## Why trust it

ES-003 AX28: the same unchanged 127-line harness drove a
linear+parallel+branching net and a cyclic retry net; the burden it
absorbed was measured (33 hand-composed engine sites, ~8 infra names
each → 1). AX17 proved one durable History across two compositions
under the same name, superset-safe on the real engine.
