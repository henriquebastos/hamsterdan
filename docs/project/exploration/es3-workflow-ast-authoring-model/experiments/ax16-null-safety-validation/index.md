# AX16 — Null-safety as validation, grounded in CEL's absorption semantics

- State: Completed, 2026-08-12.
- Question: AX15 shipped its recovery guards under an *author
  obligation* — conjoin `.present()` before any nested optional read —
  because `validate_null_safety` (v1) cannot see two of the three risk
  classes and enforces the one it sees by left-to-right ordering. Can
  the obligation become a validator? And is ordering even the right
  soundness criterion?
- Verdict: **Promising; continue** — ordering is the *wrong* criterion.
  celpy implements the CEL spec's commutative, error-absorbing logic
  operators (`error && false == false` **in both orders**;
  `error && true` raises), so soundness is a **sibling-set property**:
  a risky read is safe iff some conjunct anywhere in the same all-of is
  false whenever the path is absent (`.present()`), dually for any-of
  (`.is_null()`, since `true || error == true` but `false || error`
  raises). `validate_guard` encodes exactly that criterion in ~100
  lines, closes all three v1 holes, validates AX15's real recovery
  guards clean, and catches the guard with its presence conjunct
  deliberately removed. AX15's "ordering obligation" is hereby revised:
  membership, not position.
- Spike: [`ax16_validation.py`](ax16_validation.py) (`validate_guard`,
  `_risk_points`, the two absorption-polarity guarantee functions),
  [`test_ax16_validation.py`](test_ax16_validation.py) — 21 tests,
  [`conftest.py`](conftest.py) (sys.path bridge). No shared-module or
  production changes.

## The ground truth, proven on Petrus's `compile_guard` path

| expression shape | celpy result |
| --- | --- |
| `error && false` (either order) | `false` — absorbed |
| `error && true` | **raises** — binding parks silently |
| `true \|\| error` (either order) | `true` — absorbed |
| `false \|\| error` | **raises** |

AX15's forbidden order — risky read first, `.present()` last —
evaluates correctly today: when the path is absent the read errors, the
presence conjunct is false, and commutative `&&` absorbs. The silent
parking mode needs *every* other conjunct true, which is precisely the
world an unsecured guard cannot rule out.

## The validator

`validate_guard(predicate, *root_types)` — the root dataclasses are
knowledge the compiler already holds per transition:

- **Risk points** are recomputed from the root types: every prefix of a
  reference that is declared optional or crosses an open map —
  including inherited parent optionality (v1 hole 1) — and, for
  comparisons and membership, the leaf itself. Both sides of a
  cross-token comparison are checked (v1 hole 2).
- **Securers** are computed per connective with the right polarity:
  inside an `And`, each conjunct is validated against the union of its
  siblings' *false-when-absent* guarantees (`.present()`,
  `~x.is_null()`, unions through nested `And`s); inside an `Or`, the
  duals (`.is_null()`, `~x.present()`). Position is irrelevant (v1
  hole 3 — its ordering rule also only ever fired on leaf-optional
  refs). `.present()` inside an `Or` has the wrong polarity and
  deliberately secures nothing.
- A `NullCheck` decides its leaf but still *selects* through its
  prefixes — `present(recovery.intent)` is itself refused unless
  `recovery` is secured.
- Error messages name the risk point, the reason, and both remediation
  spellings.

## Second finding: the two evaluators disagree

`==` on a present-but-null leaf is **total** in celpy
(`null == "op" → false`, no error) — the conservative refusal of
unguarded optional-leaf equality is unnecessary for CEL guards. But
`holds()` — the Python evaluator the compiler uses for scatter-lane
routing — **crashes** on the identical predicate and data, and not even
with its own domain error: it distinguishes missing map keys
(`_MISSING`) from present-but-`None` fields, and its comparison table
evaluates all six operators eagerly, so `None > str` raises a raw
`TypeError` before `==` is looked up. Relaxing the validator today
would make a predicate's legality depend on where the compiler happens
to place it (guard vs lane). Recorded refinements for the shared
module's next iteration: lazy operator dispatch in `holds()`, a
`None`-aware equality semantics aligned with CEL, then the equality
relaxation.

## Consequences for the design

- The predicate DSL needs **no ordering discipline** — authors conjoin
  `.present()` anywhere; the validator enforces membership. The AX12
  recommendation's guard-model section should absorb this: validation
  is per-transition (`validate_guard` with the transition's bound
  roots) and belongs in the compiler right before rendering.
- The silent-parking failure mode (`error && true`) is real and
  reachable; static validation is the primary defense. Guard-error
  *surfacing* remains runtime speculation territory (existing ledger
  scope), unchanged by this experiment.
- `holds()`/CEL divergence is now demonstrated, not suspected — any
  future combinator that moves a predicate between lane routing and
  guard rendering must not change its semantics.
