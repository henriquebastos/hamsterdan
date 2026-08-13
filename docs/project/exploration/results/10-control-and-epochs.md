# 10 — Control and epochs

**Rely on this: one small control machine per case, an epoch that
increments on every resume — staleness becomes unexpressible instead
of checked-for.**

## What it is

A long-lived case (a PR, an order, an account) has a tiny control
machine deciding *whether work runs at all*, separate from the
subnets that do the work:

```python
Running(epoch, head)                       # work flows
Quiescent(last_epoch, last_head, expected) # stopped; expected = the state
                                           # we ourselves caused, if any
Terminal(status, last_epoch, last_head)    # closed
```

One pure `step(state, event) -> (state, commands)` function is the
whole machine. The load-bearing move: **`epoch+1` on every resume.**
Every piece of work is stamped with the epoch that authorized it; a
completion arriving from a drained generation carries an old epoch and
is *inert on arrival* — no drain transitions, no suppression flags, no
ambient staleness checks. You don't detect stale work; stale work
simply cannot land.

The diagnostic that finds spread state: **arcs per node.** A net
whose `arcs/(places+transitions)` is well above 1 is reading ambient
state everywhere; the excess is almost exactly the read-arc
population.

## The idea

```text
event: new head arrives        → Quiescent? resume with epoch+1 → Running
event: PR goes draft/stale     → Running → Quiescent (in-flight work
                                 completes but folds inert — old epoch)
completion{epoch=3} arrives    → current epoch is 4 → inert, by comparison
                                 of two integers, nowhere special
```

Requests that must work even while quiescent are graded, not fenced:

```text
read_only     answer questions      → allowed in ANY state, even Terminal
durable_note  acknowledge, snooze   → apply, head-indifferent
head_bound    change, rebase        → Execute(epoch, head) | Decline(reason)
```

Only `head_bound` work ever carries the epoch/head stamp.

## What it does not do

- It does not own domain logic — the machine routes life-cycle, the
  subnets do work. Keep the table small enough to read aloud.
- It does not queue declined work: a decline is an immediate
  explanatory answer (attempt-first for humans).
- It does not reach into running work to cancel it; draining is
  letting completions arrive inert.

## How it relates

- Concept 9's gates catch what epochs don't: world-level races.
- Concept 11 is where completions fold — the fold ignores old epochs
  for free.
- Concept 15's checklist asks "what is your epoch?" for any resumable
  case.

## Why trust it

ES-004 AX6 replaced three production mechanisms and two special cases
with this one machine; the epoch move retired the purpose of 42 of
production's 94 read arcs. AX7 proved the three effect grades detach
conversations entirely. AX5 quantified the heuristic: production at
2.69 arcs/node with 94 reads vs ~1.07 for the derived subnets — the
excess *was* the spread state.
