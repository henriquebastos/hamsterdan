# AX28 — One file to first motion: the smallest honest general harness

**Status:** complete — Promising; continue (with the store-default
decision explicitly tabled for the Navigator, not absorbed here).
**Question:** the governing product target asks for one file to first
motion, and the generality ruling demands the mechanism be a general
primitive, not project vocabulary. Can a single call take *any*
authored Block — not a Hamsterdan shape — to a quiescent instance on
the frozen engine, while keeping every durable artifact (canonical
definition, History, marking, replay) inspectable and every validation
intact? Or does "radically simple" inevitably start hiding the
semantics the target forbids hiding?

**Hypothesis:** the composition burden the spikes carry —
hand-assembling `Engine.create` with store, dispatch, marking,
handlers, guards on every run — is harness work, not authoring
meaning. A ~120-line general `first_motion(block, datum)` can absorb
all of it because everything it needs is already *on* the Block:
the entry port names the seed place and color, the exits name the
observation points, and `compile_block` already carries handlers,
guards, and `check_sound`.

## What was built

[ax28_motion.py](ax28_motion.py) — the harness, 127 lines, zero
workflow knowledge:

- `first_motion(block, data, *, net_name=, instance=, history=,
  limit=)` compiles the block through the AX19 kernel (running
  `check_sound` — validation is not weakened), seeds exactly one entry
  token whose color comes from the block's own entry port (a
  wrongly-colored injection is unrepresentable through this surface),
  and drives the frozen `Engine` to quiescence under a bounded advance
  budget.
- The returned `Motion` hides nothing: `.definition` (the canonical
  serialized net — the replay contract's subject), `.records` (the
  real History records), `.place(name)` and `.settled` (token data at
  any place / at every named exit), and `.replay()` — which recompiles
  the same block, `Engine.load`s the same History over the fresh
  compile, and proves the rebuilt marking matches place by place.
- The store is a visible choice: `history=` accepts any History Store;
  when omitted, motion runs in-memory and `Motion.store_defaulted`
  says so. Nothing fakes durability.

[ax28_one_file.py](ax28_one_file.py) — the authoring side: the ES-003
inquiry example (receive → parallel reserve/taxes → charge → judge
into settled/review) as one 102-line file (docstring and domain
lambdas included). Its imports are workflow vocabulary (`transform`,
`classify`, `then`, `par`) plus exactly **one** infrastructure name:
`first_motion`. Run directly it prints the honest artifacts:

```text
net definition: 5732 canonical bytes
history records: 39
exits: {'settled': [{'sku': 'sku-1', 'total': 12.0}], 'review': []}
replay: rebuilt marking matches, place by place
```

[test_ax28_motion.py](test_ax28_motion.py), nine tests on the frozen
engine: the one-file example reaches motion with both branch outcomes
live; the definition is deterministic across motions; replay rebuilds
the identical marking; a *structurally different* net — a data-driven
cycle built from AX23's `loop` — runs and replays through the very
same harness with zero per-shape composition; an unsound block is
refused by `CompositionError` before anything moves; a non-quiescing
net hits the diagnostic budget instead of spinning silently; and a
supplied store is used as given and labeled `store_defaulted=False`.

## Findings

- **The composition burden was real, and it was harness work.** The
  prior spikes hand-compose `Engine.create` at 33 call sites across 22
  files, each touching ~8 infrastructure names (`Engine`, `Marking`,
  `NetPath`, `Token`, `InMemoryHistoryStore`, `InlineDispatch`, plus
  handler/guard threading). The one-file example touches **one**. None
  of that repetition ever carried workflow meaning — which is exactly
  why a general primitive could absorb it.
- **Generality held — the ruling's criterion is met.** The same
  `first_motion`, unchanged, drove a linear+parallel+branching net and
  a cyclic retry net. Everything shape-specific lives on the Block
  (entry port, exits); the harness reads it instead of knowing it. A
  hosted app's vocabulary (ES-004's shapes) would sit *above* this,
  composing blocks — not beside it, re-composing engines.
- **Radical simplicity and honesty did not conflict here.** `Motion`
  resolves the tension by *exposing* rather than wrapping: the
  canonical bytes, the record count, the exits, and replay-as-a-method
  mean the first-motion experience *teaches* the durable contract
  (definition determinism + History = recoverable instance) rather
  than hiding it. The demo's four print lines are precisely the four
  honest artifacts.
- **The tabled store decision is now concrete.** The pull between "no
  hiding durable semantics" and "radically simple" lands on one
  parameter: `history=` defaulted to in-memory *with a label*. Whether
  first motion should instead demand an explicit store, or default to
  a durable one, is Navigator territory — the harness surfaces the
  choice; it does not make it.
- **The advance budget is the honest answer to data-driven cycles.**
  AX23's `loop` admits nets whose termination depends on token data;
  `first_motion` cannot prove termination, so it bounds driving
  (default 200 advances) and fails with a directed diagnostic naming
  the likely cause and the remedy. Silent spinning is unrepresentable.

## Limits — what "one file" honestly means here

- The file imports the spike-sibling libraries (`ax23_blocks`,
  `ax24_parallel`, `ax28_motion`) via path arrangement; it is one
  *authoring* file over pre-existing spike machinery, not a
  distributable package. The measurement that matters — infrastructure
  names an author must touch: one — survives packaging; the path
  arrangement does not.
- The AX23 algebra is PetriWork-only, so the harness passes
  `activities=()` honestly. A net with dispatched Activity leaves
  (worker-side effects, AX21's territory) needs dispatch bindings a
  first-motion surface must accept and surface — a bounded follow-up,
  not covered here.
- `first_motion` solves the *run harness*, not AX27's
  generated-authoring feedback loop; the two are complementary probes
  under the same target.

## Verdict

**Promising; continue.** One general call closes the
composition-surface gap the governing target moved into scope, on more
than one net shape, with validation intact and every durable artifact
inspectable. Carry forward: the store-default product decision
(tabled), the Activity-leaf extension (bounded follow-up), and AX27's
generated authoring as the next candidate probe — now measured against
these general primitives rather than any project vocabulary.
