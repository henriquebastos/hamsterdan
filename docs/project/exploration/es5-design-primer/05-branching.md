# 5 — Branching

**Rely on this: branch on modeled outcomes when someone modeled them,
on declared value guards when routing is about the data — and declare
the overlap policy either way.**

## What it is

Three proven branching forms, by what drives the decision:

1. **Modeled outcomes** — the deciding step itself returns which exit
   applies, as a typed outcome. The primary form: decisions someone
   *modeled* deserve names and types.
2. **Value guards** — the same data type flows everywhere; routing
   depends on the value's structure. Guards are Python *expression
   objects* (never parsed text, never inspected lambdas) compiled to
   the engine's CEL filters.
3. **Hybrid** — an arc constrains both the token type and a predicate
   over its fields.

## The idea

```python
# 1 — modeled outcomes: the decision is domain vocabulary
outcomes("evaluate", evaluate_fn,
         accepts=Application,
         outcomes={"approved": Approved, "manual": ManualReview})

# 2 — value guards: expression objects with declared order
app = on(Application)
FAST = (app.score > 700) & (app.applicant.age >= 18)

branch("triage",
    case(FAST,            then=fast_track()),
    otherwise=slow_track(),          # total by construction
)
# FAST.cel() == "((score > 700) && (applicant.age >= 18))"

# 3 — hybrid: type narrows first, predicate refines
case(type=ApprovedApplication, when=app.risk_score < 20, then=auto())
```

Guard expressions are frozen values: serializable, diffable,
structurally equal when equal — and the guard's field references are
checked against the declared payload type, so `app.rsik_score` fails
at authoring time.

## What it does not do

- No branching implied by a union return type — `-> Approved |
  Rejected` is a type, not a topology. Fan-out is always an explicit
  combinator.
- No silent overlap: cases are ordered and `otherwise` makes the
  branch total. Raw Petri nondeterminism is available only by
  deliberate descent (concept 13).
- Micro-types exist only when modeled: guards exist precisely so a
  step never returns artificial types just to steer routing.

## What it compiles to

Each form has a distinct, countable lowering:

```diagram
1 modeled outcomes      one exit PLACE per outcome; handler picks one
   in ─▶ [evaluate] ─▶ approved (Approved)
                   └─▶ manual (ManualReview)

2 value guards          CEL filter strings on the arcs; one router per case
   in ─▶ [score > 700]  ─▶ [fast case] ─▶ fast subtree
     └─▶ [score <= 700] ─▶ [slow case] ─▶ slow subtree

3 hybrid                the SAME arc carries both constraints
   in ─▶ (color=ApprovedApplication, filter="risk_score < 20") ─▶ [auto]
```

Form 2 is exactly what `FAST.cel()` is for: in today's spec DSL the
lowered arc is written `p.branch_in >> arc(filter="score > 700") >>
t.fast_case`. Mechanics:
[chapter 16](16-how-the-authoring-compiles.md). Exact code:
[ax6_compiler.py](../es3-workflow-ast-authoring-model/experiments/ax6-guard-branching/ax6_compiler.py),
[ax7_compiler.py](../es3-workflow-ast-authoring-model/experiments/ax7-hybrid-routing/ax7_compiler.py).

## How it relates

- Concept 2's typed activity outcomes are form 1 at the effect
  boundary.
- Concept 8 handles what no branch modeled.
- Concept 13's descent allows raw per-arc filters when the algebra's
  forms genuinely cannot say it.

## Why trust it

ES-003 AX5 (typed routing on the real engine, unions rejected as
implicit topology), AX6 (the predicate AST → exact CEL, overlap policy
made explicit, lambda inspection rejected on evidence), AX7 (hybrid
arcs with field authority from the payload type). ES-002's audit
grounds it: 45 of 48 production guards decompose into four decidable
atom kinds.
