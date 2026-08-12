# AX26 — Build-time type checking: how far pyright and ty push composition errors to edit time

**Status:** complete — Promising; continue (pyright as the edit-time
authority today; ty tracked as it matures; the deterministic compiler
stays the final judge).
**Question:** Composable Functions' `FailToCompose<A, B>` proves that
composition errors can surface as red squiggles before anything runs.
How far can Python typing — checked by pyright 1.1.411 and ty 0.0.63,
both pinned — move the block algebra's CompositionErrors from runtime
to edit time, and how do the two checkers actually compare?

**Hypothesis:** A thin generic façade — colors as Python types, blocks
as `TBlock[I, O]` values — lets both checkers reject bad
`then`/`route`/`par`/`disposable` compositions statically, while
lowering to the exact same AX23/AX24 runtime structure.

## What was built

[ax26_typed.py](ax26_typed.py) — the typed façade (~190 lines), four
deliberate encodings:

- **Types are colors.** Domain types are TypedDicts; `_color(tp)` is
  the AX23 color string (canonical for subscripted generics too:
  `Join2[Reservation, Taxes]` is a *different* color from any other
  parameterization). TypedDicts are plain dicts at runtime, so token
  data flows through the frozen engine with zero bridging — the
  petrus-speculation "bind types instead of strings" idea realized at
  the authoring layer, runtime untouched.
- **Totality by construction.** `TBlock[I, O]` always has one exit;
  the two-outcome `TChoice[I, A, B]` is deliberately NOT a TBlock and
  cannot enter `t_then`/`t_par2` until routed — AX24's totality
  precondition becomes a static structural fact.
- **Purity as a subtype.** `TPure <: TBlock`; `t_disposable` accepts
  only TPure; `t_then` overloads propagate pure ∘ pure = pure.
- **Explicit convergence.** `t_route` requires both handlers and an
  explicit `returns=`, so a bad merge is a constraint violation, not
  an inferred union.

Fixtures fed to both checkers: [cases_good.py](cases_good.py) (must be
diagnostic-free), [cases_bad.py](cases_bad.py) (nine marked mistakes,
each the static twin of a runtime CompositionError),
[cases_infer.py](cases_infer.py) (seven `reveal_type` probes).
[test_ax26_static.py](test_ax26_static.py) runs both pinned checkers
as subprocesses and asserts the catch matrix line by line — a version
bump that changes the story fails a test.

## The catch matrix (pinned by tests)

| # | Mistake | Static twin of | pyright | ty |
|---|---|---|---|---|
| 1 | `then` middle mismatch | color-mismatch fusion | caught | missed |
| 2 | route handler off its outcome type | color-mismatch fusion | caught | missed |
| 3 | route handlers don't converge on `returns=` | merge color mismatch | caught | missed |
| 4 | route missing an outcome | exhaustiveness | caught | caught |
| 5 | par branches disagree on entry | common-entry rule | caught | missed |
| 6 | choice used where total block required | AX24 totality | caught | caught |
| 7 | `disposable(effectful)` | AX20/AX23 purity gate | caught | caught |
| 8 | `disposable(pure ∘ effectful)` | purity propagation | caught | caught |
| 9 | leaf whose fn contradicts declared ports | leaf honesty | **missed** | **missed** |

## Findings

- **pyright: 8/9, with zero false positives and zero annotation
  burden.** Every generic constraint fires; the good-cases file needs
  no casts, no explicit type arguments, nothing beyond ordinary
  function signatures. Error locality is exact (the offending argument)
  and messages name the conflict
  (`"Review" is not the same as "Receipt"`).
- **ty 0.0.63: precise inference, incomplete enforcement.** Its
  `reveal_type` output is *identical* to pyright's on all seven probes
  — `TPure[Order, Order]`, `TBlock[Order, Join2[Reservation, Taxes]]`,
  the works — but it does not yet fail calls whose generic constraints
  are unsatisfiable (unsolved bounds surface as `Unknown`, e.g.
  `Expected TPure[Unknown, Unknown]`). Every miss is a
  generic-parameter mismatch; every catch is structural: missing
  argument, overload arity, nominal subclass at the top level. This is
  ty's pre-1.0 no-false-positives posture, and it means the four most
  valuable checks — bad `then`, bad route, bad merge, bad par — do
  not fire in this project's CI checker today.
- **The shared hole is instructive: redundancy creates it, inference
  closes it.** Case 9 declares a leaf with *two* sources for `O`
  (`fn`'s return and `returns=`); pyright widens `O` to `Raw | Order`
  instead of conflicting (classic TypeVar union-widening), ty solves
  to Unknown. The `t_fn` variation — ports inferred from the function
  signature alone, `get_type_hints` feeding the runtime colors —
  removes the second source, so the leaf *cannot* lie: single source
  of truth for checker and colors both. This vindicates AX3's
  signature-inference direction with a sharper argument: inference is
  not merely convenient, it is *safer* than declaration.
- **The shadow was caught lying — by a runtime test, which is the
  point.** `t_step` initially lowered through AX23's `transform`,
  which is always pure; the static "effectful" story contradicted the
  runtime `pure` flag until the purity test failed. Static types
  assert; only the deterministic layer verifies. Same lesson from the
  fixtures: ty caught a genuine bug pyright's bidirectional TypedDict
  inference silently accepted structurally-shaped, and AX23's
  unique-leaf-name rule rejected a fixture both checkers were happy
  with. Three layers, three different catches.
- **Runtime unchanged, end to end.** The typed inquiry example — parse,
  par(reserve, taxes), charge, judge-and-route — runs on the frozen
  engine through both routes; the par aggregate is byte-identical to
  the `Join2` TypedDict shape; lowering stays deterministic.

## Limits

- Named exits beyond fixed arity are not statically expressible:
  `TChoice` hard-codes two outcomes; Python has no mapped/conditional
  types to generalize over exit-name→type maps (the `FailToCompose`
  machinery does not translate). Fixed-arity combinators
  (`t_par2`/`t_par3`, two-way choice) are the practical ceiling —
  acceptable, since AX23's runtime algebra handles the general case.
- Context ports, `holding`, and guard-field validation (AX7) were not
  encoded; purity/context constraints beyond the TPure subtype remain
  compiler judgments.
- The harness depends on pinned tool versions (`pyright@1.1.411` via
  uvx, ty 0.0.63 from the lockfile); the catch matrix is expected to
  change as ty matures, and the tests will say so loudly.

## Verdict

Promising; continue. The layered verdict the evidence supports: the
type checker is an *advisory* layer of real value — with pyright,
authors get edit-time rejection of almost every composition mistake
for free, and `t_fn`-style signature inference is both cheaper and
safer than explicit declaration — but the deterministic
`CompositionError` layer remains the authority, because every checker
missed something a runtime check caught. ty, the project's CI checker,
currently enforces only the structural subset; adopt the façade
pattern now, track ty's generic solver, and never delete a compiler
check because a checker duplicates it.
