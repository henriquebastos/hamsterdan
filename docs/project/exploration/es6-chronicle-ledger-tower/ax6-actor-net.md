# AX6 — The actor variant (V4): one long-lived net per concern per PR

**Status:** done, 2026-08-14. Tests: [test_ax6_actor_net.py](test_ax6_actor_net.py)
(10, all executed on the frozen engine).

## The question

The Navigator's generator hunch: instead of killing the work instance
on every new head (V2), give each concern (review, CI, conversation,
correction) **one durable net for the PR's whole life**. New heads are
*sent into* the living net; it loops — receive, review, judge,
publish-or-hold, fold, wait — accumulating memory; it ends only when
the PR closes or merges.

Does this reintroduce the staleness constructs the tower eliminated
(production: 94 read arcs, 48 guards), or is there a shape that stays
clean while living across heads?

## The answer: clean — because of two mechanisms

**1. Sequential rounds by token conservation.** One `memory` token is
the actor's cumulative state *and* its idle baton. `start` consumes
it; every fold returns it; `end` consumes it forever. While a round is
in flight the baton is absent, so no second round can start — queued
heads wait in the mailbox place. Mutual exclusion, graceful shutdown
(close waits for the in-flight round), and termination are all plain
arcs. Zero guards.

**2. Staleness absorbed at the CAS boundary, not tested per token.**
No transition asks "am I current?". Every round runs to its publish
gate and the world's own compare-and-swap answers. `moved` is an
outcome arc: the unpublished findings fold back into memory as
*provisional*, and the next round's agent receives them — the
Navigator's semantics verbatim: *"consider what they did that was
pending plus do more with the new head."*

The actor is a **durable generator**: `Engine.deliver` is `send()`,
the publication effect is `yield`, and the coroutine frame is the
marking + chronicle — replayable, restartable, never a Python frame
(the ES-003 constraint holds).

## The topology (shipped spec DSL, verbatim)

```python
net = NetSpec("review_actor")
p, t = net.p, net.t

p.heads(HeadArrived)      # mailbox: heads accumulate here
p.memory(ReviewMemory)    # the baton: ONE token, PR lifetime
p.closed(CloseArrived)
p.done(Ended)

t.on_head >> p.heads      # ingress doors: what Engine.deliver fires
t.on_close >> p.closed

(p.heads, p.memory) >> t.start(handler="start_round") >> p.round(RoundOpen)
p.round >> t.review(handler="review_agent") >> p.output(AgentReview)
p.output >> t.judge(handler="validate_review") >> (p.findings(Findings), p.rejected(Rejected))
p.findings >> t.publish(handler="comment_gate") >> (p.landed(Landed), p.moved(Moved), p.fault(Fault))
p.landed >> t.fold_landed(handler="fold_landed") >> p.memory
p.moved >> t.fold_moved(handler="fold_moved") >> p.memory
p.rejected >> t.fold_rejected(handler="fold_rejected") >> p.memory
(p.closed, p.memory) >> t.end(handler="end_review") >> p.done
```

```diagram
                      ┌─────────────────────────────────────────────┐
 on_head ─▶ heads ─┐  │                                             │
                   ▼  ▼                                             │
                  start ─▶ round ─▶ review ─▶ output ─▶ judge       │
                    ▲                                   │   │       │
                 memory ◀── fold_landed ◀── landed ◀─ publish       │
                  ▲ ▲ │  ◀── fold_moved  ◀── moved  ◀───┘   ▼       │
                  │ │ │  ◀── fold_rejected ◀── rejected ◀───┘       │
 on_close ─▶ closed─┼─┴──▶ end ─▶ done          fault (fail closed) │
                    └───────────────────────────────────────────────┘
```

## Measures (test-pinned)

| | P | T | A | ratio | reads | guards | filters |
|---|---|---|---|---|---|---|---|
| Review actor — whole concern, whole PR life | 11 | 10 | 23 | 1.095 | 0 | 0 | 0 |

All cyclicity passes through `memory` (delete it and the net is
acyclic) — the AX2 rule again: **the loop is the actor's mainloop and
the state cell is its only axle.**

## Executed timeline (one PR, three heads, one chronicle)

1. Head `h1` delivered; round runs; world still at `h1` → publication
   **lands**. Memory: `reviewed=[h1]`.
2. Author pushes twice; `h2` and `h3` delivered into the *same living
   instance*. The `h2` round completes but its gate observes the world
   at `h3` → **moved**; findings fold back as provisional.
3. The `h3` round's agent receives `[finding:h2]` + adds
   `finding:h3`; gate lands. Exactly `[h1, h3]` ever reached the
   world — whichever order the mailbox drains, CAS lets only the
   current head publish.
4. Close delivered → `end` consumes the baton → `done` summarizes the
   life: `reviewed=[h1,h3], provisional=[]`.
5. A head delivered *after* close is a **dead letter**: recorded in
   the mailbox, never advanced, no error, no graveyard machinery.
6. `Engine.load` on the one chronicle reproduces the final marking —
   including the dead letter — and re-fires nothing.

## V2 (kill/respawn) vs V4 (actor), honestly

| | V2 disposable epochs | V4 long-lived actors |
|---|---|---|
| Staleness | by existence (kill) | by CAS verdict at the round boundary |
| Guards/reads | 0 / 0 | 0 / 0 |
| Instances per PR | ~1 per head (+case) — a 50-push PR leaves ~50 dead chronicles | ~1 per concern (~5 total), all ending naturally at close |
| GC | real: archive many dead instances | degenerates to archive-at-done |
| Graveyard | needed for every kill | only for close-while-in-flight; a living actor absorbs late completions normally |
| Cross-head memory | spawn arguments (snapshots passed at birth) | native: the memory baton |
| Incremental review | possible via arguments | native: `moved` findings feed the next round |
| History | many short per-epoch chronicles + case chronicle | one cumulative story per concern per PR (grows with PR life; replay cost grows too) |
| Wasted work | mid-flight agent work discarded at kill | intermediate rounds complete before their gate says `moved` — but their findings are *reused* as provisional |
| Failure mode | kill machinery bugs | `fault` swallows the baton: the actor stalls fail-closed and needs meta-level attention |
| Latency | new head reviewed immediately (old killed) | new head waits for the in-flight round to fold |

## What V4 removes from the machinery bill

V2's runtime spike needed: spawn-per-epoch, abandon/kill delivery,
per-instance ingress routing, graveyard append, GC over many dead
instances, and seed synthesis. V4 needs: spawn-per-PR-per-concern,
the same ingress routing, and archive-at-done. Kills, graveyards, and
seeds disappear from the common path — they remain only at PR close.
The engine already provides the crucial primitive: `Engine.deliver`
lands identified external events in a living instance (idempotent by
delivery identity, replay-faithful).

## Open after AX6

1. **Family shape:** V4 implies a router (case net) that broadcasts
   heads/close to concern actors — unmeasured; the AX2 case net
   shrinks (no spawn/abandon rows per epoch) but gains delivery
   fan-out. Candidate AX7.
2. **Mailbox compaction:** rapid pushes cost one completed-but-moved
   round per intermediate head. Options: accept (simplicity-first;
   findings are reused), or supersede queued heads at the router
   before delivery. Policy, not topology.
3. **Fault policy:** the stalled-actor semantics (baton lost) is
   honest fail-closed but needs a meta-level noticing story.
4. **Chronicle growth:** very long PRs accumulate one long history
   per concern; replay stays linear in PR activity.

## Verdict

**Promising; continue.** The long-lived actor keeps every tower
property (zero staleness constructs, confined cyclicity, honest
histories) while deleting most of the instance-management machinery
V2 required and making cross-head memory and incremental review
native instead of seeded. The trap — production's guard regrowth —
is structurally prevented by the baton + CAS-boundary pair, not by
discipline.
