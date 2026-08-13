# AX27 — Generated authoring against the composition authority

**Status:** complete — Promising; continue (with the trust contract and
the residue boundary stated below treated as load-bearing findings).
**Question:** the Deer Workflow comparison raised the generated-
authoring route: an agent emits authoring source and iterates against
deterministic feedback instead of a human learning the vocabulary
first. Does *our* composition authority — the algebra's eager
`CompositionError`s, `compile_block`'s `check_sound`, and the AX26
typed façade under pyright — actually behave as a machine feedback
loop? Concretely: is review total (every candidate, however broken,
becomes structured feedback), are the messages repair-grade, and can
the loop guarantee the net is never executed as a side effect of
review?

**Hypothesis:** no new authority is needed. The refusals the algebra
already carries, staged behind a ~120-line total `review` function,
give a generator everything a compiler gives Deer's loop — with the
distinctive property that most refusals carry the concrete
alternatives verbatim, so some repairs are mechanical from the message
alone.

## What was built

[ax27_review.py](ax27_review.py) — the reviewer, general by
construction (it knows the authoring contract `workflow() -> Block`,
never any workflow). `review(name, source)` is **total**: every
outcome is a structured `Feedback` — verdict, stage, error type, the
authority's message verbatim, the offending candidate line when known,
and net statistics (places, transitions, exits, canonical definition
bytes) on success. Stages in candidate order:

- `source` — the text does not parse.
- `author` — executing the authoring source or `workflow()` is
  refused; the algebra's eager `CompositionError`s land here, as does
  anything else generated code can raise.
- `sound` — the composed Block fails `check_sound` at compile.

[ax27_corpus.py](ax27_corpus.py) — one correct candidate, **ten
characteristic generator mistakes** (misremembered exit name, wrong
color chained, leaf name reuse, cross-color merge, loop on a missing
exit, loop with no way out, duplicate outcome colors, single-branch
par, truncated output, dataclass surgery producing an orphan), and
**two honest residue cases** no pre-motion review can catch.

[cases_generated_static.py](cases_generated_static.py) +
[pyrightconfig.json](pyrightconfig.json) — the no-execution stage: a
generated typed-façade candidate whose color mistake pinned pyright
1.1.411 must reject from source text alone.

[test_ax27_review.py](test_ax27_review.py), thirty tests.

## Findings

- **Review is total and staged correctly.** All ten mistakes are
  refused at their expected stage with the expected message fragments;
  the good candidate passes with net statistics; review is
  deterministic (identical `Feedback` across runs).
- **The messages are repair-grade, measured not asserted.** All ten
  refusals name the offending element. **Five of ten carry the
  concrete alternatives verbatim** (`its exits are ['out']`, both
  colors, the branch list) — pinned as a count so a message regression
  fails a test. The repair-loop test closes the circle mechanically:
  the wrong-exit candidate's message alone dictates the one-token fix,
  and the repaired source passes.
- **Review never executes the net — proven behaviorally.** With
  `Engine.create`/`Engine.load` monkeypatch-poisoned, review of the
  good candidate still succeeds. Motion is a separate stage the loop's
  operator opts into explicitly (AX28's `first_motion`); nothing in
  the reviewer can reach it.
- **The trust contract is explicit.** Reviewing authoring source *is*
  executing Python — composition is ordinary code by design. A
  generation loop therefore runs `review` with exactly the trust it
  extends to the generated source itself. The static stage is the
  no-execution alternative: pinned pyright rejected the generated
  typed-façade mistake on exactly the marked line (two diagnostics,
  both on it, none elsewhere) without importing the candidate.
- **The eager algebra makes the `sound` stage nearly unreachable.**
  Combinator-only source cannot compose an unsound block — the
  refusals fire at call time. Reaching `check_sound` required the
  corpus to descend to dataclass surgery on Block internals. This is
  the layered validation story working: the deepest net-level check is
  a safety net for descent-level authoring, not the daily authority.
- **Stage-honest source positions.** `source`- and `author`-stage
  refusals point into the candidate's own text (the deepest candidate
  frame); a `sound`-stage refusal happens after `workflow()` has
  returned, so it names the offending *node*, never a line — a limit
  the loop's operator must know.
- **The residue boundary is real and demonstrated.** Two mistakes pass
  every pre-motion stage: a classifier that returns an undeclared
  outcome at runtime, and a data-driven non-termination. Both are
  caught only by the explicitly separate motion stage — the first by
  the handler's own `CompositionError` at firing time, the second by
  `first_motion`'s advance budget. A generation loop that stops at
  review is therefore incomplete by construction; the full loop is
  static → review → opt-in motion, each stage catching what the
  earlier ones cannot.

## Limits

- The corpus is characteristic, not empirical: ten mistakes chosen
  from the algebra's refusal surfaces, not mined from real generator
  transcripts. A live agent loop would sample differently.
- No actual LLM sits in the loop; the repair demonstration is scripted
  (deliberately — determinism is what makes it a test).
- The static stage covers one mistake here; the full catch matrix
  (8/9 pyright, 4/9 ty) is AX26's record, not re-measured.

## Verdict

**Promising; continue.** The composition authority behaves as a
machine feedback loop today, with no new machinery: total review,
staged deterministic refusals, five of ten messages carrying the
remedy verbatim, a behavioral never-executes guarantee, and an honest
three-stage story (static without execution, review with authoring
execution, motion by explicit choice). Carry forward: message quality
is now a measurable property worth holding at this bar if the algebra
is ever productized, and the residue boundary defines what a
generation loop must include motion for.
