# 4 — Composition

**Rely on this: names give topology, types give compatibility — and
connectivity is never inferred from type matching.**

## What it is

Blocks compose by **port fusion**: an exit port of one block becomes
the entry port of the next. No glue places, no adapters between
compatible ports, no ambient wiring. The composed thing is itself a
block, so composition nests indefinitely.

The doctrine that keeps this safe has two halves:

- **Names define topology.** You always say *which* exit continues
  (`on="committed"`). Two places merge only when their declared port
  names are fused — never because their types happen to match.
- **Types validate compatibility.** Fusion refuses when colors
  disagree, eagerly, at the call site, with both colors named in the
  message.

## The idea

```python
flow  = then(mutate(), announce(), on="committed")   # fuse one named exit
flow  = then(flow, publish(), on="out")

merge(triage, "express", "priority", into="fast")    # same-colored exits → one
rename_exit(block, "out", "priced")                  # names are yours to shape

# when payload shapes differ, the adapter is explicit and pure:
then(a, adapt(quote_to_charge), b, on="quoted")
```

A wrong composition fails *now*, not at runtime:

```text
CompositionError: block 'announce' has no exit 'commited';
its exits are ['committed', 'moved']
```

## What it does not do

- No global "find a place with this type" — the moment two places
  share a color, type-directed wiring is ambiguous, and the engine
  itself refuses two same-color candidate arcs.
- No implicit joins: same-colored exits stay separate until you
  `merge` them by name.
- No hidden data flow: if a downstream step needs a different shape,
  the adapter is a visible pure function, inferred from its signature.

## What it compiles to

Nothing. That is the finding worth holding: `then`, `merge`, and
`rename_exit` add **zero places, zero transitions, zero arcs**. Fusion
is a rename — the downstream block's entry place *becomes* the
upstream block's exit place, and the absorbed place is dropped:

```diagram
before:  a_in ─▶ [a] ─▶ a_out      b_in ─▶ [b] ─▶ b_out
after:   a_in ─▶ [a] ─▶ a_out ─▶ [b] ─▶ b_out
                        └── b's arcs now name a_out; b_in is gone
```

```python
# condensed exact — the entire mechanic
mapping = {b.entry.place: a.exits[on].place}
nodes   = a.nodes + rename(b.nodes, mapping)
```

This is why composed nets stay countable: sequence contributes no
connective tissue, so `arcs/(P+T)` stays near 1 (concept 10) unless a
real decision or join adds it. Full mechanics:
[chapter 16](16-how-the-authoring-compiles.md).

## How it relates

- Concept 3 defines what is being fused.
- Concept 5/6/7 are the only sources of fan-out, fan-in, and cycles.
- Concept 13's editor rung catches most fusion mistakes before the
  eager refusal does.

## Why trust it

ES-003 AX14 made port-name fusion the structural rule; AX22 proved
no-glue composition; error messages carrying the fix verbatim were
measured (5/10) in AX27. ES-004 AX4 fused two independently authored
subnets through one line and one pure adapter on the real engine, with
zero ambient places — and the eager refusal caught a real protocol
anachronism statically.
