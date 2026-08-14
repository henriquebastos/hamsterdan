# 11 — Fold and decide

**Rely on this: project settled outcomes into one immutable snapshot,
decide from the snapshot — and in-flight flags simply vanish.**

## What it is

Cross-concern coordination ("publish the dashboard when review and
actions have both settled") does not need concerns reading each
other's places. Instead: every concern's typed exits fold into one
immutable snapshot value, and one pure function decides what work
follows from the snapshot alone.

```python
snapshot = fold(snapshot, exit_value)   # typed exit → new snapshot (pure)
work     = decide(snapshot)             # snapshot → identity-carrying work (pure)
```

Three problems dissolve at once:

- **In-flight flags vanish.** The fold sees only *settled* exits;
  while a repair runs, its exit hasn't folded yet, so there is nothing
  to suppress and no `repair_in_flight` guard to maintain.
- **Dedup flags become operation identity.** The same folded state can
  only emit the same operation (`dashboard:{epoch}:{head}:{digest}`);
  the gate absorbs replays lookup-first. "Announce once per
  generation" is the snapshot's lifetime, not a reset rule.
- **Replay is a refold.** The snapshot is an event-sourced projection;
  losing it costs a refold from the log, never correctness.

## The idea

```text
concern exits:   review:clean ─┐
                 actions:green ─┼─▶ fold ─▶ Snapshot ─▶ decide ─▶ [publish dashboard
                 human:approved┘     (pure)  (immutable)   (pure)    id=dash:{e}:{h}:{d}]
```

Folding is commutative across *independent* concerns (any arrival
order, same snapshot) and ordered *within* a concern by that concern's
own subnet — last-write-wins mirrors depend on exactly that.

## What it does not do

- The snapshot is not authority — it is derived. The gate (concept 9)
  and the epoch (concept 10) still guard the world.
- `decide` performs no effects and reads no clock; it returns work
  descriptions with identities. Dispatch happens elsewhere.
- No concern reads another concern's interior — the snapshot is the
  only cross-concern surface.

## How it relates

- Concept 10's epochs make old-generation exits fold inert.
- Concept 12 feeds time into the fold as ordinary events.
- Concern shapes differ freely underneath (a phase ladder, a
  last-write-wins mirror, pure rewrites) — the fold hosts all of them
  without forcing one mold.

## Why trust it

ES-004 AX8 built the pattern and asserted commutativity over all 24
arrival permutations; AX9/AX10/AX12 reused it unchanged for timers,
the escalation ladder, and the human mirror; the in-flight guards it
retired are counted in the AX5 sweep against the real `build_net()`.
