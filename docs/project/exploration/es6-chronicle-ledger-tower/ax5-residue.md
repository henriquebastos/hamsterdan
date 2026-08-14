# AX5 — The residue probe: what the kill cannot do, executed

**Question.** An orphaned worker dispatched under a killed epoch
eventually lands its effect. Does the tower stay safe without the
kill doing anything to the world — and does the dead instance replay
without lying?

**Method.** Not a shape experiment: this one runs the **frozen
engine**. Two real `Engine` instances of the AX1 gate step share one
world (a fake git server with *server-side* CAS, like GitHub's), each
with its own `InMemoryHistoryStore`. The case net's role is played by
the test timeline; ES-003 AX5's variant-routing helpers reused
unchanged. All claims asserted by
[test_ax5_residue.py](test_ax5_residue.py) — 5 tests, all passing.

## The timeline

```text
t1  epoch-1 spawned: push op-e1, expected h1 → h1b   (worker in flight)
t2  the author pushes: authority moves, h1 → h2
t3  the KILL: epoch-1 is simply never advanced again — no poison
    tokens, no drain, nothing enters the dead net
t4  epoch-2 spawned under h2: push op-e2, h2 → h3 → committed ✓
t5  the orphaned epoch-1 worker finally lands (at-least-once
    guarantees it eventually will)
```

## What the engine proved

1. **The gate absorbs the orphan; the kill never had to.** The
   world's CAS rejects op-e1 (`expected h1, observed h3`): branch
   stays at `h3`, commits list is exactly `["op-e2"]`. Safety is the
   gate's property, not the kill's — the ES-004 doctrine "authority
   pre-checks are economy, never correctness" holds across an
   instance boundary.
2. **The orphan lands as a classified outcome, not an error.** The
   dead cell's token rests in `moved` with the observed head in its
   data — kind-2 idempotency ("preconditions changed") as data, no
   exception, no fault, no retry.
3. **The chronicles never mix.** `op-e1` appears only in epoch-1's
   records, `op-e2` only in epoch-2's — asserted in both directions.
   Two cells, two ledgers, zero shared bookkeeping.
4. **Replay never passes the drop.** `Engine.load` on the dead cell's
   history reproduces its final marking — *including* the late
   `moved` token (graveyard policy: the dead chronicle may still
   record) — quiesces immediately, and re-fires nothing: the world's
   commit list is untouched by resurrection.

## Policy surfaced, not ruled

The probe *models* the graveyard option (late completions append to
the dead chronicle, inert because nobody folds a dead ledger). The
alternative — refuse appends after the terminal meta-event — trades
a complete chronicle for a smaller one. Navigator's product choice
(tower-model §5).

## Honest limits

- `InlineDispatch` compresses "worker in flight" into "advance
  later"; a real dispatcher interleaves mid-pipeline. The gate
  argument is unaffected (CAS is server-side), but delivery-order
  edge cases are untested here.
- The kill-as-never-advance is the semantic essence; production
  needs the operational wrapper (mark dead, stop routing ingress,
  advisory cancel to the dispatcher for economy).

## Verdict

**Promising; continue.** The tower's central bet — that instance
death plus unchanged gates is *sufficient* safety for in-flight
effects — executed on the frozen engine exactly as the model
predicted, including honest replay of a killed instance.
