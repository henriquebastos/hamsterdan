# AX6 — Guard-based branching with a single data type

Completed 2026-08-11. **Verdict: Promising; continue.**

## Design question

Can explicit Python expression objects represent same-type value routing
robustly — compiling deterministically to Petrus `Cel` arc filters,
preserving type and source information, and making the overlap and
no-match policies explicit rather than silently chosen?

## Hypothesis

Both branches receive the same type (`Application`); routing depends on
the value's structure (`score > 700`). The activity should not return
artificial micro-types just to steer routing. A small predicate AST built
by operator overloading on a typed root proxy can compile to the CEL
dialect Petrus filters actually evaluate, and an ordered-exclusive
lowering can give deterministic first-match-wins routing on the frozen
runtime.

## Authoring surface

```python
app = on(Application)

sequence(
    branch(
        when((app.score > 700) & (app.applicant.age >= 18), then=step(fast_track)),
        when(app.score > 500, then=step(senior_review)),
        otherwise=step(manual_review),
    ),
    step(archive),
)
```

`on(Application)` is a typed root proxy: attribute access is validated
against the dataclass (unknown fields fail listing the available ones;
scalar fields refuse nesting), comparisons produce frozen predicate
nodes, `&`/`|`/`~` combine them, and `.is_null()`/`.is_not_null()`/
`.one_of(...)` cover the remaining ES-002 guard-audit atom kinds.
`__bool__` raises with a remedy, so Python's untraceable `and`/`or`/`not`
keywords fail loudly at authoring time instead of silently collapsing to
one operand.

## What the spike established

### The predicate AST and its CEL compilation

- Frozen dataclass nodes: `Compare`, `NullCheck`, `Membership`, `And`,
  `Or`, `Not` over `FieldRef` paths. Structural equality holds
  (annotations are non-identity metadata), so recompilation is
  deterministic and duplicate predicates are detectable.
- Petrus filters see token data fields as **bare variables** — the root
  is elided: `app.score > 700` compiles to `(score > 700)`, nested access
  to `(applicant.age >= 18)`. Every node renders parenthesized, so
  negation and conjunction compose without precedence surprises.
- Construction-time type validation caught: unknown fields, nesting into
  scalars, constant type mismatch (`score > "700"`), ordering over
  non-orderable fields, and field-to-field comparison (refused — a
  single-token filter has one data scope).
- **Null safety is a compile concern**: a raising filter reads as
  *not admitted*, so `note == "vip"` over the optional `note` would park
  the token silently. `when()` runs a null-safety walk: comparisons over
  optional fields are refused unless a left-conjunct `is_not_null()`
  secures them (mirroring CEL's `&&` short-circuit).

### Expression objects vs lambda inspection

Lambda **tracing** (not source inspection) came nearly free:
`trace(Application, lambda a: (a.score > 700) & (...))` calls the lambda
with the typed root proxy and gets the identical predicate tree. Its
sharp edge is inherent: `and`/`or`/`not` cannot be traced — `__bool__`
turns that into a loud authoring error. Source/AST inspection was
rejected without a full prototype: it would exist only to rescue those
three keywords, at the cost of source availability, closure capture,
serialization, and stable source mapping. Explicit expression objects are
the foundation; tracing is a compatible sugar.

### Overlap policy — decided explicitly, both semantics demonstrated

The frozen runtime's input-arc semantics differ from AX5's output-arc
semantics in exactly the right way:

- Overlapping *input* filters are **competition, not duplication**: two
  transitions racing for one token, one wins nondeterministically
  (proven with a mini-net: token admitted by both filters lands in
  exactly one output place).
- A token admitted by *no* input arc **parks** in its place — silently
  when filters evaluate cleanly to false, with a
  `FilterEvaluationWarning` when a filter raises. Never dropped, but
  silently stuck.

Chosen policy, encoded in the lowering rather than left to the scheduler:

- **Ordered-exclusive cases**: case *n* compiles to its predicate
  conjoined with the negations of every earlier case —
  `(score > 500) && !((score > 700) && (applicant.age >= 18))` — so at
  most one router is ever enabled. First match wins by declaration
  order, deterministically, with no runtime priority feature. Cost:
  filter expressions grow linearly in case position.
- **Mandatory `otherwise`**: carries the conjunction of all negations,
  so every evaluable token has exactly one route. Totality is
  unrepresentable to break at the AST layer.
- Structurally identical duplicate predicates are refused (the later
  case is provably unreachable); arbitrary semantic overlap is
  statically undecidable and is made *harmless* by the exclusive
  lowering instead of pretended away.

The raw-overlap alternative (legal Petri nondeterminism) remains
available to a future author as plain Petrus, but the `branch()`
combinator deliberately does not expose it.

### Generated net (baseline example)

```text
w.entry(Application)
  ├─[(p0)]──────────────▶ w.0.case_0 ──▶ w.0.when_0 ──▶ fast_track ──┐
  ├─[p1 && !p0]─────────▶ w.0.case_1 ──▶ w.0.when_1 ──▶ senior_review ─┤
  └─[!p0 && !p1]────────▶ w.0.otherwise ▶ w.0.when_otherwise ▶ manual_review ─┤
                                              (XOR merge, 3 passthroughs) ────▶ w.0.out(Decision) ──▶ archive
```

Routers are pure `passthrough` transitions (no dispatch, no workers);
the XOR merge reuses the AX5 pattern. The source map carries
`when <cel>` entries pointing at the authoring line of each `when()`,
and `CompiledWorkflow.filters` exposes the exact CEL string per router
for debugging.

### Runtime evidence (35 tests)

- High-score adult → `fast_track`; overlapping guards resolve by
  declaration order (score=800, age=16 falsifies case 0, routes to case
  1 — never nondeterministic); mid → senior; low → `otherwise`.
  Exactly one review activity is requested per token.
- Replay over a recompiled net reaches the same terminal state
  (deterministic predicates → deterministic filters → same `Net`).
- A forged token with `score=null` raises in every filter: the token
  parks in `w.entry` with `FilterEvaluationWarning`, no activity fires —
  exactly the failure the null-safety validation makes unrepresentable
  from typed authoring.
- Mini-net honesty tests: overlap = competition; clean no-match = quiet
  parking (the strongest argument for the mandatory `otherwise`).

## Comparison with the current DSL

Production Hamsterdan uses **zero** CEL filters today; value routing is
done by transition-level `typed_guard` predicates plus hand-wired XOR
places. The ES-002 guard audit showed 45/48 production guards decompose
into the same atom kinds this predicate AST covers (comparison,
null-check, membership, boolean composition). AX6 is the first proof in
this stack that CEL arc filters execute those atoms on the frozen
runtime — with the predicate durable in the net definition
(`NetDefinitionV3` serializes the `Cel` string) instead of living in
Python callables that history cannot see.

## Failure modes and error quality

| Failure | Where caught | Quality |
| --- | --- | --- |
| Unknown/misspelled field | proxy attribute access | lists available fields |
| Constant type mismatch | comparison construction | names field, types, value |
| Optional field unguarded | `when()` null-safety walk | names field, shows remedy |
| `and`/`or`/`not` keywords | `__bool__` | names `&`/`|`/`~` |
| Mixed subject types | `branch()` construction | lists offending roots |
| Duplicate predicate | `branch()` construction | prints the CEL, "never match" |
| Missing default | keyword-only `otherwise` | unrepresentable |
| Forged null at runtime | enabledness | warning + visible parked token |

## Ledger updates

- SP-4 extended: input-arc parking evidence (quiet park on clean
  no-match) recorded as the input-side counterpart of silent output
  drops.

## Open questions carried forward

- AX7: the hybrid — a case keyed by *both* a variant type and a
  predicate over that variant's fields; whether the guard AST can
  validate against each case's narrowed type.
- Ordered-exclusive filter growth is linear in case count; fine at
  workflow scale, worth watching if branches ever get wide.
- Guard placement: AX6 used arc filters; transition guards
  (`GuardEvaluationWarning` path) remain unexplored — potentially
  relevant when a guard must read *multiple* input places at once.
