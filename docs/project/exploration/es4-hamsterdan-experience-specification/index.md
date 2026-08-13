---
status: Thickening
opened: 2026-08-12
navigator: Henrique
---

# ES-004 — Hamsterdan experience specification and subnet decomposition

## Inquiry

What does Hamsterdan essentially do — specified from its boundary, ignoring
the current Petri-net topology — and does that essential specification
decompose into linear, composable subnets when expressed with the ES-003
block algebra?

The motivating hunch (Navigator): the production net feels too complex for
what the product does. Control places acting as global state, spread
domain logic, and missing linearity may be accidental complexity rather
than essential requirements. The way to test this is to re-derive the
specification independently and only then compare.

## Why this is a separate story from ES-003

ES-003 asked *how to author workflows* and treated the production net as
the parity oracle: a candidate design was good when it regenerated the
same behavior. ES-004 inverts the method:

```text
ES-003: authoring model → lower → compare against production topology (oracle)
ES-004: boundary evidence → independent behavioral model → compare at the END
```

Divergence from the production net is evidence here, not failure. ES-003's
findings (block algebra, typed named ports, control/work separation,
railway outcomes, holding patterns) are prior art and tools — available
for use, not assumptions this story must accept.

## Method: deliberate topology blackout

During AX0–AX4, `src/hamsterdan/readiness/net/topology.py` (1,684 lines)
is **not** a source of truth. The specification is derived only from what
crosses the system boundary:

1. **Inputs** — GitHub webhook events, human intents, timers, sweeps, CLI.
2. **Outputs/effects** — the 11 activities: comments, dashboard, commits,
   reruns, agent invocations.
3. **Invariants** — authority fencing on `(epoch, head, base_head,
   policy_digest)`, one engine per PR, idempotency and
   outcome-classification doctrine.
4. **Contract types** — `src/hamsterdan/contracts/readiness.py` as shared
   vocabulary.

Evidence hierarchy when sources conflict: product docs and briefing >
contracts > github_app/host boundary code > activity signatures > (only in
AX5) the topology itself.

## What counts as a subnet

A candidate subnet is a concern with a **secure entry/exit contract**:
work that, once entered with authority, runs linearly to a domain outcome
and returns to the routing layer, which alone decides what happens next.

```python
# Investigative pseudocode — not an accepted API.
subnet(
    name="...",
    entry=Port(...),                    # single typed door
    exits={                             # explicit domain outcomes
        "completed": Port(...),
        "discarded": Port(...),         # work done, authority moved → drop
        "retryable": Port(...),
    },
    authority=...,                      # checked at entry and/or commit fence
    purity=...,                         # pure/disposable vs effectful
    effects=...,                        # which activities it may dispatch
)
```

Patterns to look for while decomposing: linear work paths; control vs work
separation; pure/disposable computations (compute freely, discard if
authority moved — simplicity over saved work); authority at subnet entry
or at the commit/fence boundary; explicit domain outcomes; composition
through typed named ports.

## Experiments

Registry: [experiments/index.md](experiments/index.md). Planned start
(later experiments should emerge from findings, not be overplanned):

- **AX0** — Boundary inventory and topology-independent experience map.
- **AX1** — Candidate subnets and their secure entry/exit contracts.
- **AX2** — Manually linearize one mostly pure/disposable concern.
- **AX3** — Authority/fence and discard/restart semantics for one subnet.
- **AX4** — Compose two subnets through typed named ports.
- **AX5** — Compare against the production topology; classify every
  divergence as (a) accidental complexity in the current net, (b) a real
  requirement the independent spec missed, or (c) an unresolved design
  choice.

## Synthesis

The series' results are folded into [synthesis/](synthesis/index.md) —
five lens documents (experiment map, negative results, positive
results, an executed one-PR walkthrough, and the unified candidate
experience specification) written for a reader who has seen none of
the code. The specification is a candidate for Navigator review, not a
decision; the open product choices it surfaces are tabled in
[synthesis/05-unified-experience-spec.md](synthesis/05-unified-experience-spec.md).

## Working documents

- [source-boundaries.md](source-boundaries.md) — evidence inventory
  (inputs, effects, invariants, contract types), with code references.
- [experience-map.md](experience-map.md) — behavior scenarios workbench
  (`given S / when X / then Y`), for manual and driven work.
- [subnet-candidates.md](subnet-candidates.md) — candidate concerns and
  entry/exit contract drafts.

## Relation to prior stories

- **ES-002** established that fragment families are domain vocabulary and
  that binding plumbing was the real authoring pain (fixed by RS-014–017).
- **ES-003** produced the block algebra, port model, guard expression
  layer, and the synthesis/candidate spec — prior art here, not doctrine.
- This story makes **no commitment to a production redesign**. Its output
  is an essential specification, decomposition evidence, and a classified
  divergence map for a future decision.
