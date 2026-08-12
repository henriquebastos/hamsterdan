# AX7 — Hybrid routing: type constraint and predicate constraint on one arc

Completed 2026-08-11. **Verdict: Promising; continue.**

## Design question

Can one case carry *both* a type constraint and a predicate constraint —
"only `Approved` tokens whose `risk` is below 20" — without exposing
low-level arcs, with the guard validated against the case's narrowed
type, and with sound semantics on the frozen runtime?

## Authoring surface

```python
approved = on(Approved)

sequence(
    hybrid(
        evaluate,  # -> Approved | Rejected
        case(Approved, when=approved.risk < 20, then=step(auto_processing)),
        case(Approved, then=step(senior_approval)),
        case(Rejected, then=step(manual_processing)),
    ),
    step(archive),
)
```

`hybrid()` fuses AX5's `switch` (union exhaustiveness, durable
`$variant` discriminator) with AX6's guard machinery (typed predicate
AST, ordered-exclusive lowering, mandatory defaults). A `case` names a
variant and optionally narrows it with a predicate over *that variant's*
fields.

## The decisive runtime fact

`enabledness.admitted` checks the arc's nominal color **before**
evaluating its filter:

```python
if not arc.admits(token):   # color gate first
    return False
if arc.filter is None:
    return True
...                          # filter runs only on color-matched tokens
```

So a hybrid arc `arc(color="Approved", filter=Cel("(risk < 20)"))` never
evaluates its filter on a `Rejected` token — a guard over the narrowed
type's fields can never raise on the other variants. Proven end-to-end:
the `Rejected` route runs under `warnings.simplefilter("error",
FilterEvaluationWarning)` and stays silent while flowing past two
`Approved` arcs whose filters read `risk`, a field `Rejected` lacks.
**Narrowed guards are sound by construction, not by luck.** This is the
frozen-runtime foundation the whole hybrid design rests on.

## Answers to the experiment's stated questions

- **Can type checking reject invalid guard fields?** Yes, twice over:
  `on(Approved).risk_score` fails at proxy construction ("Approved has
  no field 'risk_score'; available: [risk, score]"), and
  `case(Approved, when=on(Rejected).reason == ...)` fails at case
  construction because the predicate's root type is not the case's
  variant.
- **Does the guard AST need explicit knowledge of the data type, or can
  it operate structurally?** It *can* operate structurally (CEL reads
  whatever fields the token data has), but the typed root is what buys
  every early rejection above — and the color-first gate is what makes
  the typed assumption valid at runtime. Decision: guards are always
  rooted in a declared type; structural guards would trade compile
  errors for runtime warnings and parked tokens for no gain.
- **How does the DSL express this without exposing arcs?** The case *is*
  the arc: `case(type, when=predicate, then=body)` lowers to exactly one
  inscription carrying both constraints. Nothing else to author.

## Lowered shape

The union result lands variant-colored in one **untyped pool place**;
each case is one hybrid input arc off the pool:

```text
w.entry(Application) ─▶ evaluate ─▶ w.0.pool (untyped)
    ├─[Approved, (risk < 20)]──▶ case_0 ─▶ on_0(Approved) ─▶ auto_processing ──┐
    ├─[Approved, !(risk < 20)]─▶ case_1 ─▶ on_1(Approved) ─▶ senior_approval ──┤
    └─[Rejected, —no filter—]──▶ case_2 ─▶ on_2(Rejected) ─▶ manual_processing ┤
                                       (XOR merge) ─▶ w.0.out(Decision) ─▶ archive
```

- Exclusion is *within* a variant only — colors already separate
  variants, so `Rejected`'s single case carries no filter at all, and
  `Approved`'s default carries only `!(risk < 20)`.
- `PoolVariantHandler` adapts AX5's routing handler to a single target:
  it projects the `$variant`-stamped result as a variant-colored token
  into the pool, refusing unknown variants loudly. The hybrid arcs then
  do all routing declaratively — visible in the serialized net, not in
  handler code.

## Totality, decided explicitly

Two levels, both construction-time errors:

- every union member needs at least one case (AX5 exhaustiveness);
- within a variant, exactly one **unguarded** case must come last (the
  variant's default). A variant with only guarded cases would park
  unmatched tokens silently; a case after the unguarded default could
  never match; duplicate guards within a variant are unreachable. All
  three are refused with remedies.

## Evidence (15 tests)

- Shape: guard-root mismatch, unknown field on the narrowed type,
  uncovered variant, guarded-only variant, unreachable case after
  default, duplicate guard, non-union source — all refused with
  remedies.
- Lowering: pool untyped; the three arcs carry exactly
  (`Approved`, `(risk < 20)`), (`Approved`, `!(risk < 20)`),
  (`Rejected`, `None`); source map names each case
  (`case Approved when (risk < 20)`).
- Runtime: risk 10 → `auto:10`; risk 150 → `senior:150`; rejected →
  `manual:low score`; exactly one route per token; no filter warnings on
  the color-mismatched path; replay over a recompiled net reaches the
  same terminal state.

## Comparison with nesting the existing combinators

`switch(evaluate, case(Approved, then=branch(when(...), otherwise=...)),
case(Rejected, then=...))` expresses the same routing with AX5+AX6
pieces composed — two lowering stages, one extra place and passthrough
per guarded variant, and the guard living one level away from the type
that scopes it. The fused `hybrid` is flatter in both the authoring text
and the net, and it is the form that makes the type-narrows-then-
predicate-selects semantics a single visible inscription. Both survive;
`hybrid` is the better authoring surface when the branching criterion is
"which variant, and what does it look like", while `switch`+`branch`
composition remains right when the guard logically belongs to the
downstream fragment rather than the routing decision.

## Open questions carried forward

- The pool place holds mixed-color tokens; per-case FIFO fairness under
  load was not exercised (single-token cases only).
- AX8: cycles — the loop-back arc will need this same hybrid admission
  (retryable vs terminal) plus retry-count state; where does that state
  live?
