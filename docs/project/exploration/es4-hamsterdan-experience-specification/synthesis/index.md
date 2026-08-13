# ES-004 Synthesis — what 13 experiments taught us about Hamsterdan itself

**Status:** candidate synthesis for Navigator review, 2026-08-13.
This synthesis folds AX0–AX12 into one story and one candidate
specification. Nothing here is a decision; no production code changed
anywhere in the series.

## Who this is for

A Python-fluent reader who knows only basic Petri-net vocabulary —
place, transition, token, arc — and has read **zero** code from this
repository and **neither** the ES-002, ES-003, nor ES-004 records.
Everything needed is quoted or explained inline; source links are for
digging deeper, not prerequisites.

Three sentences of grounding so nothing later surprises you:

- **Hamsterdan** watches GitHub pull requests and drives them to
  "ready": it reviews code with agents, publishes findings and a
  dashboard as PR comments, reruns or repairs failed CI, answers
  `@app` conversations, reminds idle reviewers, and announces
  readiness. All side effects go through **11 activities** (comment
  posts, git pushes, agent invocations) executed by workers.
- **Petrus** is the event-sourced Petri-net engine underneath: the
  production workflow is one 1,684-line net definition
  (`src/hamsterdan/readiness/net/topology.py`) whose places hold
  typed tokens and whose transitions fire activities. Petrus stayed
  **frozen** throughout this series.
- **The inquiry:** the Navigator's hunch was that this net is too
  complex for what the product does — "places acting as global
  state", "missing linearity and composition". ES-004 tested that by
  *deriving an independent specification of Hamsterdan from its
  boundary alone* (webhooks in, activities out, invariants), with the
  production topology deliberately blacked out — then comparing at
  the end and classifying every divergence.

The verdict in one sentence: **the hunch was right and is now a
number** — production spends 94 of its 309 arcs (30%) letting distant
transitions peek at shared state, 73% of those reads are displaced by
mechanisms the experiments executed, and every production *rule*
survives intact in a model built from three control states, per-concern
folds, pure decisions, and two effect gates.

## Reading order

| Doc | Lens | Read it to learn |
|---|---|---|
| [01-experiment-map.md](01-experiment-map.md) | What we did | Every experiment's question, verdict, and takeaway — and exactly what to read if you want to dig into one. |
| [02-what-did-not-work.md](02-what-did-not-work.md) | Negative results | The designs we tried (or inherited) and rejected, each with the code and the evidence that killed it. |
| [03-what-worked.md](03-what-worked.md) | Positive results | The patterns that survived contact with production semantics and the frozen engine, each with the code that proves it. |
| [04-one-pr-walkthrough.md](04-one-pr-walkthrough.md) | How it works | One pull request's whole life traced through the unified model — admission, CI failure, the escalation ladder, a real CAS-gated repair on the Petrus engine, quiescence, confirmed resume, readiness, a reminder, the human concern, terminal, replay. Real captured output, not idealized. |
| [05-unified-experience-spec.md](05-unified-experience-spec.md) | The proposal | The cherry-picked unified specification — control machine, concern folds, subnet shapes, gates, ports, time, effect grades — every clause annotated with the experiment that proved it, plus the open product choices. **A candidate for discussion, not a decision.** |

Read 01 first for the map. If you want to *understand the model*, read
04 (the walkthrough) before 05 (the spec). 02 and 03 are reference
lenses you can read in either order.

## The three arcs

```diagram
┌───────────────────────────────┐  ┌───────────────────────────────┐  ┌───────────────────────────────┐
│ Arc 1: BLACKOUT DERIVATION    │  │ Arc 2: CONTROL AS A FUNCTION  │  │ Arc 3: THE SWEEP AND THE DEBT │
│ AX0–AX3                       │  │ AX6, AX7, AX4                 │  │ AX5, AX8–AX12                 │
│                               │  │                               │  │                               │
│ Specify Hamsterdan from its   │  │ One quiescent state replaces  │  │ Measure the divergence: 94    │
│ boundary alone. Find the two  │  │ dormant/provisional/seed;     │  │ read arcs, five categories,   │
│ gates and two fractal subnet  │  │ conversations detach from the │  │ 73% accidental. Then EARN the │
│ shapes. Linearize one concern.│  │ head machine; two subnets     │  │ rest: projection fold, timers,│
│ Kill the pre-check fence: the │  │ compose through one typed     │  │ the repair ladder, payload    │
│ operation IS the fence.       │  │ port, zero shared places.     │  │ shape, the human mirror.      │
└───────────────────────────────┘  └───────────────────────────────┘  └───────────────────────────────┘
     every verdict: "promising; continue" — AX5 concluded "question answered"
     (AX6/AX7 ran before AX4/AX5 because AX3's conclusion forced their questions)
```

- **Arc 1 (AX0–AX3)** derived the specification production never had:
  the boundary fully specifies *how* effects happen safely but almost
  never *when* work is chosen — the decision layer existed only as
  topology. The decomposition found exactly **two world-mutation
  gates** (comment posts, git CAS) and two fractal shapes covering 9
  of the 11 activities. AX2 proved one concern linearizes at 1.07
  arcs/node on the real engine; AX3 proved authority pre-checks are
  never correctness — the git CAS closes the race completely, and a
  stale comment *cannot* be prevented by any check.
- **Arc 2 (AX6, AX7, AX4)** built the control layer as a pure
  function: three states (`Running`/`Quiescent`/`Terminal`), one
  resume move at `epoch+1`, provisional authority reduced to an
  optional `expected` field, conversations graded by effect
  (read-only / durable note / head-bound) so nothing is ever parked,
  and two independently authored subnets fused through one typed
  named port with **zero** ambient places on the real engine.
- **Arc 3 (AX5, AX8–AX12)** ran the executable divergence sweep —
  every number derived from `build_net()` and asserted — then worked
  every item the independent model had not yet earned: the readiness
  projection as a fold (AX8), time as typed ingress (AX9), the
  rerun→repair loop as a bounded escalation ladder (AX10), port
  contracts that carry payload shape (AX11), and the human concern as
  a snapshot mirror plus notes (AX12).

## What is deliberately NOT here

- **No production redesign, no migration plan.** ES-004's charter made
  no commitment to rebuilding Hamsterdan; the output is a
  specification, decomposition evidence, and a classified divergence
  map for a future decision.
- **No decided product policies.** Two genuine product choices
  surfaced and remain open for the Navigator: whether finding
  dispositions survive quiescence (AX5 #6 / AX7), and who owns
  `reminder_recipient` when a GitHub observation collides with a
  local reassign note (AX12). The spec lists every open choice in one
  table.
- **No Petrus changes.** Where the model wants something the engine's
  authoring layer lacks (payload-typed ports), AX11 showed the engine
  needs no change — the color string becomes a derived projection of
  the payload type.

## Relation to the ES-003 synthesis

ES-003 asked *how to author* nets and produced the block algebra,
typed ports, and guard layer — treating production behavior as the
oracle. ES-004 asked *what Hamsterdan essentially is* and used ES-003's
results as tools, not doctrine. The two syntheses meet in
[05-unified-experience-spec.md](05-unified-experience-spec.md): the
experience spec is expressed *in* the block/port vocabulary, and two
ES-004 findings (payload-shape ports from AX4/AX11, the `spendable`
effect grade from AX2) feed back into the ES-003 candidate design.
Neither synthesis requires reading the other; each quotes what it
needs.
