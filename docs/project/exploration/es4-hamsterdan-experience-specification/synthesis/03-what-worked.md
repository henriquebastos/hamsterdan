# Lens 3 — What worked, and why

Each entry: the pattern, the code that proves it, and why it holds.
Everything here is executed — by the spike tests (547 passing across
the exploration) or by the captured walkthrough
([04-one-pr-walkthrough.md](04-one-pr-walkthrough.md)).

---

## 1. The topology blackout as a method (AX0)

Deriving the specification with the production net deliberately unread
produced something the project never had: an *independent* statement
of what Hamsterdan does, against which the topology could then be
*judged*. The sharpest yield was structural: the boundary owns safety
(fencing, CAS, lookup-first, operation identity — fully specified);
the net owns decisions (when review fires, when readiness publishes,
rerun vs repair — specified **nowhere else**, 29 documentation gaps).
Divergence became evidence instead of failure: AX5 could classify 94
read arcs precisely because the model was derived, not transcribed.

## 2. Two gates, and disposability before them (AX1, AX2)

Classifying all 11 activities by disposability collapsed the effect
surface to exactly two world-mutation gate types:

```text
COMMENT GATE  conversation/finding/dashboard/reminder/readiness publish
              — operation identity + lookup-first + supersession
GIT GATE      CAS ref advance inside repair/change
              — exact compare-and-swap; the operation is the fence
```

Everything before a gate — pure computation, read-only discovery,
agent invocations that only *spend* — can be thrown away. "Secure
exit" gets a precise meaning: the only way work becomes world-visible
is through a gate. AX2 made the doctrine observable on the real
engine: on stale authority the agent ran, the fence caught it, and
`world.comments == []` — money spent, world untouched.

## 3. Attempt-first: classify outcomes instead of preventing them (AX3)

```python
# the gate's own outcome classification IS the staleness signal:
outcomes={"committed": "ProvisionalHead",
          "moved":     "BranchMoved",       # preconditions changed — not an error
          "fault":     "NonrecoverableFault"}
```

Why it holds: it matches what the providers actually guarantee (CAS
rejects atomically; comments never reject), and it converts the
Navigator's two idempotency kinds into mechanics — lookup-first for
"did it before → skip" (comment markers, git head-commit trailers),
outcome classification for "doing it again fails → preconditions
changed → discard, wait for the webhook, never force".

## 4. Three control states, one resume move (AX6)

```python
Running(epoch, head)
Quiescent(last_epoch, last_head, expected=None)   # expected: the head we pushed
Terminal(status, last_epoch, last_head)
```

One `step(state, event)` function is the whole head machine. Three
production mechanisms (Dormant place, provisional flag + scattered
fence checks, inline supersession drain) and two special cases (seed
place, born-draft refusal) become rows in one transition table.
**`epoch+1` on every resume is the load-bearing move:** a stale
completion of drained work carries an old epoch and is inert without
any bookkeeping — staleness becomes *unexpressible* rather than
*checked-for* (the fate of 42 of production's 94 read arcs).

## 5. Effect grades detach conversations entirely (AX7)

```python
read_only     reply, status                     → Answer, in ANY state (Terminal too)
durable_note  acknowledge dismiss defer
              snooze resume reassign            → Apply, head-indifferent
head_bound    change update_base
              resolve_conflict recover_publication → Execute(epoch, head) | Decline(reason)
```

One pure `service` function; only `Execute` ever carries an
epoch/head stamp (production stamps all twelve kinds). Declines are
attempt-first: an immediate explanatory comment, not a queue. 21 read
arcs → one typed port.

## 6. Typed named ports as the only seam (AX4, AX11)

Two subnets authored in different experiments fused through one line
and one pure adapter, on the real engine, with zero ambient places:

```python
announced = then(mutation_subnet(world), announce_commit(), on="committed")
composed  = then(announced, publish_comment(world), on="out")
# asserted: composed.contexts == {} ; no authority/state/control place in the net
```

Composition errors read like type errors and caught a real protocol
anachronism (AX2's fence-era publisher) statically. AX11 completed the
contract — `Port(name, payload_type)`: **names give topology, nominal
types give identity, shape gives diagnostics, signatures give
adapters, and the payload type gives guards their field authority.**
The settled doctrine, now with fields: types validate compatibility;
named ports define topology; connectivity is never inferred globally
by type.

## 7. Fold + decide: the projection pattern (AX8, reused by AX9/AX10/AX12)

```python
snapshot = fold(snapshot, exit_value)     # typed concern exits → one immutable value
work     = decide(snapshot)               # pure decisions → identity-carrying work
```

Why it holds, three ways at once:

- **In-flight flags vanish** — the fold sees only settled exits; while
  a repair runs, its exit simply hasn't folded, so there is nothing to
  suppress (`provisional`/`change_in_flight`/`repair_in_flight` guards
  had nothing left to guard).
- **Dedup flags become operation identity** —
  `dashboard:{epoch}:{head}:{digest}`: the same folded state can only
  emit the same operation; the AX3 gate absorbs replays lookup-first.
  "Announce once per generation" is the snapshot's *lifetime*, not a
  reset rule.
- **Replay is a refold** — the snapshot is an event-sourced
  projection, rebuildable from the log; losing it costs a refold, not
  correctness. No live object is ever durable state.

Commutative across independent concerns (tested over all 24
permutations); ordered *within* a concern by that concern's own subnet
— which AX12 showed is load-bearing by design for last-write-wins
mirrors.

## 8. Time as typed ingress (AX9)

The scheduler is a provider like GitHub: `ArmTimer` out,
`TimerDue(epoch, head, sequence, at)` in, maturity a durable folded
fact. The instant lives in the event, so `fold`/`decide` never read a
clock — replay has zero wall-clock nondeterminism, the same discipline
Petrus's own `Delay` watermark provides (deliberately preserved, not
displaced). The durable-maturity trick keeps production's subtlest
semantic for free: a matured-but-suppressed reminder fires the moment
conditions return; snooze cancels the *decision*, never the *fact*.
Nine read arcs → one `reminder_wanted(snapshot)` predicate, verbatim.

## 9. The escalation ladder with provider-owned loop state (AX10)

The one real cycle in production is genuine domain structure — and its
loop variable was GitHub's all along:

```text
failure@attempt=1 → rerun once → failure@attempt>1 (reproduced)
→ repair (once per fingerprint, once per PR lineage) → new head
→ confirmed resume carries {repair_used, repair_fingerprint}
→ same fingerprint again → the human rung
```

Boundedness is structural, not emergent: each rung emits at most one
identity-deduped operation; the worst case emits exactly two
operations; the authoring stays tree-shaped because the "iteration" is
the next generation. The monotonic fence over
`(run_id, attempt, conclusion)` replaces a place, a transition, a
predicate, and three read arcs.

## 10. The static layer pays today (AX11)

Both pyright 1.1.411 and ty 0.0.63 catch every tested structural
mistake — phantom field access, wrong adapter return, wrong payload
type — on unmodified production pydantic models, with zero annotation
burden beyond ordinary signatures. The project's CI (`scripts/check`
runs `ty check src`) already enforces the adapter layer. The division
of labor that emerged:

```text
edit time (ty, in CI today)    adapter bodies, arguments, returns — structural
compose time (deterministic)   fusion rule, shape diffs, guard paths — semantic
run time (frozen engine)       unchanged
```

## 11. Concern shapes are allowed to differ (AX10 vs AX12)

Actions is a phase ladder with budget fences; human is a
last-write-wins mirror plus notes; review dispositions are pure
rewrites. The fold/decide pattern hosts all three without forcing one
mold — and *because* AX12 mirrored production verbatim instead of
imposing the ladder, it surfaced the reassign/observation ownership
collision as a real product question rather than papering over it.

## 12. The Navigator's heuristics, quantified (AX5)

> "If I have a lot more arcs, then I probably have state spread."

```text
                    arcs/(P+T)   reads
production net        2.69        94 (30%)
AX2 review chain      1.07         1 (the fence AX3 then retired)
AX4 composed subnet   ~1.1         0
```

The excess above ~1 arcs/node is almost exactly the read-arc
population. 73% of the reads are displaced by executed experiments;
the rest served the readiness projection until AX8 folded it. Every
number is asserted against the real `build_net()` — the sweep cannot
drift from the code it measures.
