# AX20 — Function-like subnets: claim, run linearly, fence once

**Status:** complete — Promising; continue.
**Question:** The Navigator diagnosed the real net's broad coupling:
control places (authority, concern state) act as global state read by
many transitions, so no concern reads as a sequence. Can a subnet
behave like a *function call* — enter through a claiming boundary, run
a linear disposable interior, and judge validity exactly once at the
exit — restoring linearity without an in-flight flag?

**Hypothesis:** Entry routes by per-token arc filter and *consumes* the
concern's state token (a structural mutex); the interior is a pure
linear pipe with no shared-state reads; two complementary exit guards
fence the moving authority once — commit emits the effect and releases
the state updated, discard throws the whole run away and releases the
state unchanged. Work is cheap; a stale run restarts with fresh inputs.

## What was built

[ax20_subnet.py](ax20_subnet.py) authors the pattern in AX19 kernel
notions only — no Python model types, plain-dict tokens, nominal
colors. [test_ax20_subnet.py](test_ax20_subnet.py), fifteen tests,
every behavioral one executing the frozen `Engine`.

The shape: `submit → intents → [claim] → accepted → [prepare] → draft
→ [commit | discard]`, with `state` consumed at claim and re-produced
at both exits, and `authority` read at the exits only.

Three of five transitions are handler-less: `submit` is a source,
`claim` and `discard` route purely by color through frozen passthrough
(Intent→accepted, State→claimed; Draft→rejected, State→state). Only
`prepare` (the domain transform) and `commit` (the effect construction)
are code.

## Findings

- **The mutex is structural.** Claim holds the state token, so the
  empty `state` place blocks every rival entry; the serialized net
  contains no `in_flight` or `provisional` string anywhere. What AX13
  encoded as three guard conjuncts and a flag round-trip
  (`change_in_flight=True` … back to `False`) is here a token's
  *location*.
- **Entry blindness collapses two cases into one.** Entry never reads
  authority, so "stale when it arrived" and "authority moved while we
  worked" are indistinguishable to the net — both judged once, at the
  fence. The precondition, stated as contract: **the input carries the
  authority coordinates it was issued under** (the intent's
  epoch/head), and `prepare` snapshots them into the draft. The fence
  compares snapshot to current authority; no entry authority read was
  silently reintroduced.
- **Exclusivity is constructive, not policed.** The two exit guards are
  rendered complements (`FENCE` and `!(FENCE)`), so exactly one exit is
  enabled once a draft exists — the same complement discipline AX13
  found in production's `_mutation`/retire pair, but applied once at
  the boundary instead of smeared across authorize-time conjuncts.
- **Soundness is testable, not rhetorical.** After either terminal
  path: every interior place (`intents`, `accepted`, `claimed`,
  `draft`) is empty, and exactly one State-colored token exists in the
  whole net. Replay over a recompiled net reaches the same marking,
  including runs that held the claim mid-history.
- **Routing by arc filter keeps the queue live.** A non-matching intent
  (`kind == "noise"`) never binds, never errs, and never blocks a later
  matching token — the AX19 filter contract doing entry routing.
- **Restart is re-entry, not recovery.** After a discard, a fresh
  `submit` with current coordinates commits normally; the stale husk
  stays inert in `rejected`. *Who* re-submits is deliberately outside
  the subnet — the rejected place is an observation surface, not a
  retry policy. That gap is stated, not hidden.

## Comparison with the AX13 change concern

| | AX13 (pessimistic, flag-guarded) | AX20 (optimistic, claim-fenced) |
| --- | --- | --- |
| Authority reads | authorize **and** retire (before any work) | exits only (after the work) |
| Concern-state reads | 3 guard conjuncts + flag write + flag clear elsewhere | consume at entry, produce at exits |
| Entry guard | 7-conjunct `MUTATION` smear | none (arc filter routes; token claims) |
| In-flight encoding | `change_in_flight` boolean in state data | the state token's *location* |
| Stale valid intent | retired before work begins | worked, then discarded wholesale |
| Concurrency | flag rejects rivals | empty place disables rivals |

Cost of the whole pattern: 8 places, 5 transitions, 17 arcs, 2 guards,
2 authority read arcs, 2 code bodies. The trade is explicit: AX13
refuses doomed work before starting; AX20 performs it and throws it
away. The Navigator's ruling makes that trade acceptable — "we don't
have to save work; simplicity first."

## Boundaries stated honestly

- **The fence is atomic with effect *emission*, not application.** The
  guard evaluation, state release, and `work` token production happen
  in one firing — but a token in `work` is a request. Authority can
  move after commit; the external effect still needs the project's
  current-authority fencing at execution. This pattern narrows the
  race, it does not repeal the at-least-once doctrine.
- **Optimistic discard is safe only while the interior is pure.** The
  commit transition must remain the sole effect-emitting point; an
  interior with irreversible side effects would need compensation
  machinery this pattern deliberately excludes.
- **The claim serializes the concern.** Throughput is bounded by one
  run at a time per state token; if the interior were a long Motus
  activity rather than a passthrough transform, the claim window would
  span the activity's latency. Fine for a mutation concern (that
  serialization is the *point*); wrong for fan-out work.

## Verdict

**Promising; continue.** The function-subnet shape is real: entry =
filter + structural claim, interior = guardless linear pipe, exit =
one fence with complementary commit/discard. It eliminates the
in-flight flag and confines authority coupling to the boundary, on the
frozen runtime, with fewer moving parts than the flag-guarded
equivalent — and its preconditions (inputs carry their issuing
coordinates; interior purity; external restart policy) are contracts a
composition layer can check, not folklore.
