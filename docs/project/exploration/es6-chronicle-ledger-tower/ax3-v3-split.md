# AX3 — The V3 variant: splitting lifecycle from epoch management

**Question.** Does separating "is the PR alive" (pr net) from "which
authority is current" (epoch net) pay its coordination cost, or is
lifecycle just three more rows in the case net's table?

**Method.** Same rules as AX1/AX2. All claims asserted by
[test_ax3_v3_split.py](test_ax3_v3_split.py) — 6 tests, all passing.

## The split, as built

```diagram
┌─ pr net (lifecycle) ─────────┐      ┌─ epoch net (instances) ──────┐
│ active/dormant/terminal      │      │ running/idle/finished        │
│ × observed_open/draft/closed │─────▶│ × head_seen/went_active/     │
│ emits lifecycle FACTS ───────┼──────│   went_dormant/went_terminal │
│                              │      │ owns spawn + abandon         │
└──────────────────────────────┘      └──────────────────────────────┘
```

The pr net keeps AX2's grid but, instead of commanding spawn/abandon,
emits four cross-net facts. The epoch net consumes them with its own
state cell and owns the instance pipelines.

## Measured price of the split

| | P | T | A | nodes | ratio |
|---|---|---|---|---|---|
| **V2** case net (AX2 grid) | 13 | 9 | 31 | **22** | 1.409 |
| V3 pr net | 10 | 6 | 23 | 16 | 1.438 |
| V3 epoch net | 14 | 8 | 28 | 22 | 1.273 |
| **V3 total** | 24 | 14 | 51 | **38** | — |

Same behavior, +73% nodes, +65% arcs. And two costs the table
understates, both asserted:

1. **Four cross-net fact colors exist as places in BOTH nets** —
   `head_seen`, `went_active`, `went_dormant`, `went_terminal` — plus
   the token-routing machinery between engine instances, which the
   shipped runtime does not provide. V2 needs none of this: its
   "boundary" is ordinary places inside one net.
2. **The epoch net's states are a shadow.** Asserted exactly: every
   epoch-net state change is triggered by a pr-net lifecycle fact and
   never by a domain fact — `running/idle/finished` is
   `active/dormant/terminal` mirrored across the boundary with a
   one-webhook lag. A mirrored state machine is dual-write
   bookkeeping, the very disease the tower cures.

The split also opens ordering races V2 cannot have (a `head_seen`
arriving while the epoch net is still `idle` is a dead token; in V2
the single state token makes that interleaving unrepresentable).

## What the split would buy — and why it doesn't pay here

A genuine level in the tower owns a *world* the level below cannot
see: the case net's world is engine instances; the work net's world
is GitHub. The pr/epoch split creates two nets that share the *same*
world and the same driving facts — that's why the shadow appears.
Levels earn their existence by owning different worlds, not by
grouping related concerns. (This is the general primitive: **split by
world, not by topic.**)

## Verdict

**Not useful enough.** Lifecycle is three rows in the case net's
table; V3 rebuilds ES-004's dual-write bookkeeping as topology and
adds cross-net machinery for the privilege. V2 stands: one case net,
one work net per epoch. AX4 carries the numbers.
