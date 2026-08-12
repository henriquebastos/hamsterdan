# AX23 — The completed algebra: merge, loop, and context ports

**Status:** complete — Promising; continue.
**Question:** AX22 closed with three shaped gaps — explicit merge,
loops at composition level, and declared context ports for ambient
state. Do all three fit the block algebra *as combinators*, without
touching the leaves, the fusion rule, or the frozen engine — and can
the full AX20 + AX21 story then be told from the algebra alone?

**Hypothesis:** Each gap is a port operation, not a new kind of node:
`merge` fuses two same-colored exits into one place, `loop` fuses a
named exit back into the block's own entry (the AX8 tree-to-cycle
hypothesis at composition level), and context ports are *declared*
exemptions from the entry→exit path rule — `reads=` for the AX20
fence, `holding` for the AX20 claim bracket.

## What was built

[ax23_blocks.py](ax23_blocks.py) restates AX22's algebra (the
AX19-restates-AX18 precedent) plus exactly the missing pieces:

- `merge(block, *exits, into=)` — explicit convergence of same-colored
  named exits; refuses fewer than two names, differing colors,
  unknown exits, colliding result names, and any transition that would
  end up producing twice into one place.
- `loop(block, on=)` — the named exit's place renamed onto the block's
  own entry place; refuses color mismatches and swallowing the only
  exit. The authoring expression stays a tree; the net becomes cyclic.
- `classify(..., reads=((place, color), ...))` — read arcs onto
  declared context places; the classifier sees `fn(data, contexts)`
  and routes on shared state read atomically in the firing. A reading
  step can never be `pure` (the fence-once rule).
- `holding(block, context=, color=)` — the AX20 claim bracket from
  handler-less passthrough transitions: a claim consumes the outer
  entry token *and* the context token, parks the claim in a held
  place, and one release per exit returns the context token.
- `check_sound` exempts declared context places only; `disposable`
  now refuses context-touching blocks *before* judging purity (a pure
  block wrapped in `holding` is still not discardable — it held a
  shared resource).

[test_ax23_blocks.py](test_ax23_blocks.py), thirty-six tests; the
behavioral ones execute the frozen `Engine`. The capstone composes
the whole AX20 + AX21 story from the algebra alone:

    capstone = holding(                       # AX20 structural claim
        prepare(disposable) >> fence(reads=authority)   # fence once
        >> loop(apply : Fresh → Applied|Already|Fresh|Failed,
                on="transient")               # AX21 bounded retry
        >> finish / note >> merge(into="done")          # convergence
        >> record(stale → rejected),
        context="state")

    capstone : Intent → done(Settled) | rejected(Rejected) | failed(Failed)
    contexts : authority (read), state (held)

16 places, 10 transitions, 33 arcs; deterministic serialization; the
state token is returned on every terminal path including failure.

## Findings

- **All three gaps closed as port operations.** No new node kinds, no
  glue transitions, no leaf changes, no engine probes beyond what
  AX20/AX22 already established (passthrough routes by color; output
  arcs carry colors). `merge` removes one place; `loop` removes one
  place and adds one cycle; `holding` adds exactly the AX20 shape
  (gate, context, held, one claim, one release per exit).
- **Merge is convergence, not synchronization — tested, not asserted.**
  Two tokens seeded through two branches arrive as two tokens in the
  merged place; nothing pairs, waits, or combines. The AND-join
  (synchronization) remains AX4's separate construct; conflating the
  two is the classic workflow-patterns confusion (Simple Merge WCP-5
  vs Synchronization WCP-3) and the algebra keeps them apart by name.
- **The tree-to-cycle hypothesis holds at composition level.** The
  authoring expression for the bounded retry is a nested function
  call; the compiled net has a visible cycle (exactly one transition
  produces into the entry place). `check_sound`'s reachability
  argument needs no special-casing for cycles. Boundedness stays
  data-driven in the classifier — attempts ride in the token, the cap
  is visible in `fn`, and the persistent-outage path exits through
  `failed` still releasing the held state.
- **Declared exemption is what makes ambient state a contract.** The
  same net with the `contexts` declaration dropped fails `check_sound`
  with the context place named as stranded. The declaration is not
  paperwork; it is the difference between AX20's diagnosis ("control
  places as global state smear") and a visible, lintable capability:
  contexts union by explicit name across composition (the AX14 rule),
  and a shared name must agree on color.
- **The resource discipline is enforced twice, structurally and
  statically.** Structurally: without the context token nothing
  enters (the intent waits at the gate); two entrants serialize
  through one resource; the token count is exactly one after every
  run, failure included. Statically: `holding` refuses a context color
  colliding with any boundary color (passthrough routes by color and
  could not tell claim from payload) and `disposable(holding(pure))`
  is refused — held resources are not discardable work.
- **One check-ordering lesson.** `disposable` originally judged purity
  first, so a reads-block (never pure) got the generic purity message.
  The context check must come first: it is the more specific refusal
  and the only one that can catch the pure-`holding` case.

## Boundaries stated honestly

- **Read contexts reintroduce coupling deliberately.** A `reads=`
  declaration is exactly the shared-state smear AX20 diagnosed — the
  algebra makes it *visible and declared*, not absent. Fence-once
  discipline stays authorial: nothing yet stops an author declaring
  reads at every step. A lint (at most one reading step per block, at
  the boundary) is possible on the block value but was not built.
- **Loop boundedness is not proven, only shaped.** `check_sound`
  accepts any cycle; termination lives in the classifier's data logic
  (attempts in the token). A declared-bound variant
  (`loop(..., at_most=n)` compiling to a counter or weight) would make
  the bound structural; deferred, since AX21 already showed data-driven
  bounds testable.
- **`holding` serializes the whole bracket.** One context token means
  one entrant at a time from claim to release — correct for the AX20
  concern-state use, too coarse for read-mostly resources. Weighted
  claims (counting semaphores) are expressible with AX19 arc weights
  but untested.
- **Merge requires prior color agreement.** Two branches converging
  must already have transformed into one color; `merge` will not adapt
  types. That is deliberate (types validate, names identify) but means
  convergence usually costs one `transform` per branch.

## Verdict

**Promising; continue.** The algebra is now closed over everything
the earlier experiments needed: sequence, branch, merge, loop,
disposable interiors, read fences, and held resources — leaves +
seven combinators, all decided before lowering, all running unchanged
on the frozen engine. Together with AX18/AX19 (kernel) this completes
the candidate layer model end to end with no shaped gaps left:
**blocks → combinators → kernel → frozen engine**. What remains for
synthesis is judgment, not machinery: which disciplines (fence-once,
declared bounds, weighted claims) become lints, and how the AX10
authoring-style findings sit on top of this semantic core.
