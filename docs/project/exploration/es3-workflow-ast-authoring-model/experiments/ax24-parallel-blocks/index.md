# AX24 — Parallel in the block algebra: split, total branches, join policies

**Status:** complete — Promising; continue.
**Question:** The Composable Functions comparison exposed the completed
algebra's one structural gap: no AND-parallelism. Can a parallel
combinator join branches soundly in the presence of failure, with the
join policy explicit in the net — and does the library's totality
insight (every branch always returns exactly one Result) transfer to
Petri nets?

**Hypothesis:** Totalized branches make the AND-join sound: if every
branch is forced to emit exactly one token (whatever it means), the
join never waits on a token that cannot come. Fail-fast is a *second*,
different policy whose abandonment semantics demand purity — the
composable-functions `first` removal, turned into an admission rule.

## What was built

[ax24_parallel.py](ax24_parallel.py), on top of AX23's algebra
unchanged (imported, not restated):

- `par(name, branches, returns=)` — the 'all' policy: an AND-split
  handler copies the input token to every branch, every branch runs to
  completion (effects allowed — nothing is abandoned), an AND-join
  consumes exactly one token per branch and aggregates
  `{branch_name: data}`. **Precondition, enforced with the remedy in
  the error: every branch is total (exactly one exit).**
- `par_fail_fast(name, branches, returns=, failure=)` — eager failure:
  branches expose exactly `ok`/`failed` exits (all `failed` sharing
  one color so one place can receive whichever branch loses); one
  `armed` token (the AX20 once-only claim) is consumed by the all-ok
  join or by exactly one abort; losing branches' late tokens drain
  into a visible `abandoned` exit. **Admissible only over pure,
  context-free branches.**

[test_ax24_parallel.py](test_ax24_parallel.py), twenty-three tests on
the frozen engine, including the ES-003 inquiry example — receive,
parallel(reserve, taxes), charge — end to end.

## Findings

- **Totality transfers, and it is the whole game.** The 'all' join is
  sound *because* the precondition forces every branch to emit exactly
  one token. A branch with meaningful ok/failed variants totalizes
  first — each variant routed into one common result color, merged —
  and a downstream `classify` splits the aggregate again. Tested end
  to end: one failed branch still joins; two failed branches
  accumulate both errors in the verdict (the validation-applicative
  semantics of their `all`, reproduced on a net).
- **Fail-fast without totality costs structure, and the cost is
  linear, not exponential.** The naive AND-join over multi-exit
  branches needs a transition per exit combination (2^n). The armed
  once-only + per-branch abort + per-branch drains construction is
  2 + 3n transitions (asserted in a test). The price of eagerness is
  visible: expects, drains, and an `abandoned` exit where late tokens
  land as inspectable debris — never silently vanished, never
  double-reported (two simultaneous failures produce exactly one
  `failed` token; the once-only was tested, not assumed).
- **The purity gate turns their removal into our admission rule.**
  composable-functions deleted `first` because losing branches'
  effects still happen. Here `par_fail_fast` refuses any branch that
  is impure *or context-touching* (a pure `holding` block is still
  refused: abandoned work may not have held a shared resource) — with
  the lesson cited in the error message. The 'all' policy tolerates
  effects precisely because it abandons nothing.
- **One authoring-rule extension was necessary and is honest.**
  Fan-out/fan-in handlers address arcs **positionally** (declared arc
  order, preserved by every algebra rename), because a split produces
  the same data into N places that may share a color — color
  addressing cannot express that. Color remains the rule for routing
  leaves; position is the rule for structural fan-out/fan-in.
- **Shared read contexts compose across branches.** Two branches
  reading the same declared context place fuse it once and read
  concurrently (contextual-nets semantics — read arcs do not
  conflict); the context survives, unconsumed, and the aggregate
  carries both reads. Context union follows the AX14/AX23 rules
  (shared name must agree on color).

## Boundaries stated honestly

- **Which failure wins fail-fast is Petri nondeterminism.** Two
  simultaneous failures race for the armed token; the event-sourced
  history fixes the winner for replay, but authorship cannot predict
  it. That is declared fail-fast semantics, not a bug — and a reason
  to prefer the 'all' policy when the loser matters.
- **Fail-fast does not cancel; it disclaims.** Losing branches run to
  completion and then drain. True cancellation (stopping work early)
  would need engine support (timers/interrupts) outside the frozen
  boundary — noted for the Petrus speculation ledger only if ever
  needed.
- **Aggregate tokens are dict-shaped, untyped inside.** The join
  produces `{branch: data}` under one `returns` color; nothing checks
  the aggregate's interior shape. A typed record color (or the AX26
  typing layer) could tighten this.
- **`par` requires a common entry color** rather than computing a
  common subtype the way `CanComposeInParallel` intersects parameter
  types — colors are nominal, so there is nothing to intersect.
  Recoloring belongs inside the branch, visibly.

## Verdict

**Promising; continue.** The last structural gap in the algebra is
closed with the join policy explicit in the net: `par` (all-and-
aggregate, effects welcome, totality enforced) and `par_fail_fast`
(purity-gated, once-only armed, visible debris). The
composable-functions insights survived the phase change to durable
nets — totality as a join precondition, error accumulation as
aggregate-then-classify, and the `first` removal as a purity admission
rule. Next: AX25 (the failure rail as sugar over these primitives) and
AX26 (phase-shifting composition errors into pyright/ty).
