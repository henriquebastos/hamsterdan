# AX22 — Structured composition: combinators are the only control flow

**Status:** complete — Promising; continue.
**Question:** The Navigator's constraint: *what if control statements
could only call functions?* Can a composition layer whose only
operands are function-like blocks (one typed entry, named typed exits
— the AX20/AX21 signature) and whose only control flow is combinators
produce sound-by-construction nets, propagate purity, and enforce the
AX20 disposable rule at composition time?

**Hypothesis:** Blocks compose by **port fusion** — routing a named
exit into the next block's entry by renaming places, adding no glue
transitions and no new state — and everything the layer promises
(soundness, purity, effect placement) is decidable before the frozen
engine ever sees the net.

## What was built

[ax22_blocks.py](ax22_blocks.py): `Block` (nodes + entry port + named
exit ports + declared purity), two leaves (`transform` — pure linear
step; `classify` — the AX21 typed-outcome shape, impure by default,
`pure=True` for AX5 value branching), three combinators (`then`,
`rename_exit`, `disposable`), a static `check_sound`, and
`compile_block` onto the AX19 kernel.
[test_ax22_blocks.py](test_ax22_blocks.py), seventeen tests; the
behavioral ones execute the frozen `Engine`.

The example composes four leaves into a fenced change pipeline:

    pipeline = rename_exit(then(
        rename_exit(then(
            then(disposable(validate), apply, on="out"),
            finish, on="applied"), "out", "done"),
        record, on="stale"), "out", "rejected")

    pipeline : Intent → done(Done) | rejected(Rejected)

## Findings

- **The keystone came from a runtime probe, not design:** the frozen
  engine hands every Petri handler its output arcs *in declared order,
  each carrying the target place's color*. So the one authoring rule —
  **handlers address outputs by color, never by place name** — makes
  port fusion by renaming safe: a block's output places are never
  renamed (the upstream name survives fusion; only entries are
  absorbed), and handlers survive composition untouched.
- **Fusion adds nothing.** `then(validate, apply)` has exactly
  `2 + 3 − 1` places — b's entry absorbed, zero glue transitions, zero
  extra events. The full four-leaf pipeline compiles to 6 places, 4
  transitions, 9 arcs; deterministic serialization; and the frozen
  engine runs both terminal paths with no interior marking left — the
  dynamic soundness AX20 tested, now on a machine-composed net.
- **Soundness became a static judgment.** `check_sound` decides the
  workflow-net property (every node on an entry→exit path) on the
  block value before lowering; a stranded node is named in the error.
  Blocks built only from these leaves and combinators pass by
  construction — the Böhm–Jacopini bargain: give up arbitrary arcs,
  get analyzability.
- **Purity is composition-checked, and the AX20 rule executes.**
  `pure ∘ pure = pure`; `disposable(effectful)` is refused at
  authoring time with the doctrine in the message ("the commit
  boundary is the only effect-emitting point"). A pure `classify`
  (value-only branching) may live inside a disposable interior; the
  world-touching one may not.
- **Names disambiguate; types validate — again.** Exit-name collisions
  demand an explicit `rename_exit` (never silent merging); color
  mismatches at fusion name both ports; two same-colored outcomes on
  one classifier are refused because color is how handlers address
  exits. Every refusal message names the blocks, ports, and colors
  involved — composition errors read like type errors.

## Boundaries stated honestly

- **Purity is a declaration, not a verification.** The layer trusts
  leaves and polices composition; a lying leaf is undetectable without
  effect typing, which is beyond a spike (and likely beyond Python).
- **No loops and no context ports yet.** Cycles stayed inside leaves
  (AX8/AX21 bound them there); ambient state places (AX20's
  `authority`/`state`) have no block-algebra home yet — a context
  port would be exempt from the entry→exit path rule, which is exactly
  why it must be a *declared* exemption. Both are the natural next
  extensions, and both AX14 (explicit port identity) and AX20 (claim
  discipline) already say how they should behave.
- **Exit merging is refused, not solved.** Two branches converging on
  one continuation (the AX5 later-merge) currently requires distinct
  exit names; a `merge` combinator (same color, explicit intent) is
  the missing fourth combinator.
- **Inhibitor arcs are outside the block algebra** — they gate on
  absence, which has no entry→exit path meaning; `check_sound` refuses
  them loudly rather than mis-judging them.

## Verdict

**Promising; continue.** The structured-net constraint holds: with
blocks as values and combinators as the only control flow, soundness,
purity, and effect placement are all decided *before* lowering, and
the compiled result is exactly as small as the hand-drawn net — no
glue, no extra events. The missing pieces are known and shaped
(merge, loop-at-composition, declared context ports), not open
questions. Together with AX18/AX19 (kernel), AX20 (fenced function
subnets), and AX21 (classified boundaries), the layer model for the
final synthesis is now complete end to end: **blocks → combinators →
kernel → frozen engine**.
