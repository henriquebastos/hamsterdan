# AX1 — Minimal workflow AST

- State: Completed, 2026-08-11.
- Question: is a small workflow AST — `Activity`, `Sequence`, `Parallel`
  only — a useful intermediate representation: traversable, printable,
  deterministic enough to feed a compiler, and easier to read than the
  low-level net definition?
- Prototype: [workflow_ast.py](workflow_ast.py) (~170 lines), tests in
  [test_workflow_ast.py](test_workflow_ast.py) (14 passing). No net
  generation, no execution, no production change.

## Authoring syntax

Real Hamsterdan activity names (from `ACTIVITY_TRANSITIONS`):

```python
sequence(
    activity(review),
    parallel(
        activity(actions_discovery),
        activity(conversation),
    ),
    activity(dashboard_publish),
)
```

Bare callables and strings coerce to leaves, so
`sequence(review, "repair")` also works.

## AST produced

`render()` output — every node carries a structural address:

```text
sequence [/]
  activity review [/0]  # Run the PR readiness review agent.
  parallel [/1]
    activity actions_discovery [/1/0]  # Observe the current GitHub Actions state for the PR head.
    activity conversation [/1/1]  # Classify unresolved PR conversation into intents.
  activity dashboard_publish [/2]  # Publish the readiness dashboard comment.
```

## Design decisions

1. **Identity is structural; origin is metadata.** `origin`
   (filename/line, captured at construction) is excluded from equality
   (`compare=False`). Two builds of the same source yield equal ASTs and
   equal fingerprints — the precondition for AX0's determinism
   requirement (the `Net` is not in History; resume re-supplies it).
2. **Activities are symbolic.** The leaf stores only the activity name as
   the `Worker` resolves it, plus the first docstring line. A callable is
   a convenience source for name/doc, never retained — the AST carries no
   Python code, mirroring the `NetDefinitionV3` stance.
3. **Structural paths as `NetPath` candidates.** `walk()` yields
   deterministic child-index paths (`/1/0`); these are the natural seed
   for generated `NetPath`s and `NetUri` source mapping in AX2.
4. **No construction-time normalization.** `sequence(a, sequence(b, c))`
   stays nested; the authoring shape is preserved for source mapping.
   Whether the compiler flattens during lowering is an AX2 question.
5. **Serialization stance: reproducible, not durable.** The AST does not
   need to be persisted — like `NetSpec` today, it is rebuilt from source
   on every run. What matters is a stable canonical form: `canonical()`
   is JSON-faithful and origin-free; `fingerprint()` digests it for
   compile-determinism and versioning checks.

## Comparison with the current DSL

The same shape written directly in the Petrus DSL needs, per activity, a
work place, an `execute.*` transition, and a result place (the bridge
pattern), plus a fan-out transition after `review`, a join transition
before `dashboard_publish`, and pure handlers for both:

| Measure | Current DSL | AX1 AST |
| --- | --- | --- |
| Places declared | 8 | 0 |
| Transitions declared | 6 (4 execute + fork + join) | 0 |
| Arcs declared | ~12 | 0 |
| Pure handlers to write | 2 (fork/join transforms) | 0 (not yet expressible) |
| Nodes | — | 6 |
| Concurrency visible at a glance | no (implied by arc fan-out) | yes (`parallel`) |

The AST is unambiguously easier to *read* — order and concurrency are the
whole text. But the table's last row of honesty: the current DSL's extra
elements are not all ceremony. The fork/join handlers carry **data
semantics** (what each branch receives, how results combine) that the AX1
AST simply does not express yet.

## Explicit, inferred, ambiguous

- Explicit: step order, concurrency structure, activity names.
- Inferred: leaf name and doc from the callable; origin from the frame.
- Ambiguous / absent (deliberately deferred): data flow between steps
  (what does `dashboard_publish` consume?), token colors, join semantics,
  failure paths, and any validation that an activity name is actually
  registered — symbolic leaves defer that to compile/bind time, which is
  where the current DSL also discovers it (host binding in
  `PrReadinessHost.open()`).

## Failure modes

- `sequence()` → `WorkflowShapeError: sequence() needs at least one step;
  an empty sequence has no behavior`.
- `parallel(review)` → `WorkflowShapeError: parallel() needs at least two
  branches, got 1; a single branch is just the step itself`.
- Unknown activity name: **not** caught at AST time. Acceptable for AX1;
  AX2 must decide where name resolution is validated.

Nodes are frozen dataclasses; mutation raises `AttributeError`.

## Evaluation against the series criteria

- Serialization: canonical form exists and is code-free; durability not
  required (History + re-supplied Net remain the durable pair).
- Replay: unaffected — nothing executes; determinism property tested
  (`test_identical_construction_yields_equal_ast`,
  `test_fingerprint_is_stable_across_builds`).
- Debugging: `render()` with structural addresses plus `origin` gives
  both directions — AST → source line, and (future) AST → generated
  element via path-derived `NetUri`.
- Type checking: none yet; leaves are untyped names. AX3's whole subject.

## Verdict

**Promising; continue.** The tree is trivially traversable, printable,
deterministic, and vastly more readable than the equivalent wiring. The
open risk is real, though: everything interesting the current DSL forces
you to write (colors, data transforms, join semantics) is exactly what
this AST omits. AX2 (lowering `Activity`/`Sequence` onto `Net`) will show
whether the compiler can supply that honestly or whether the leaves must
grow type information first.
