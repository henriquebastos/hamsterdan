# AX10 — Python authoring-style comparison

- State: Completed, 2026-08-12.
- Question: which embedded-Python spelling should author the workflow
  AST — nested combinators, a fluent chain, a context-manager builder,
  or a generator — judged on a nested example, not a five-line demo?
- Verdict: **Promising; continue** — nested combinators are the core
  and the default surface; an immutable fluent chain is acceptable
  optional sugar for linear flows; context-manager and generator
  builders are rejected for structure.
- Spike: [`ax10_ast.py`](ax10_ast.py) (minimal structural core),
  [`ax10_styles.py`](ax10_styles.py) (the three challengers),
  [`test_ax10_styles.py`](test_ax10_styles.py) — 16 tests.

## Method

One structural skeleton (`Activity`/`Sequence`/`Parallel`/`Retry`,
names only — colors, ports, and guards are AX3–AX8 territory) and one
comparison workflow deep enough to expose nesting behavior: a parallel
whose first branch is itself a two-step sequence, a bounded retry, and
a tail step. Every style must produce the **same canonical AST**
(proven by a parametrized equality test) or it is not an authoring
layer but a different model.

## What the probes showed

**Nested combinators** (the AX1–AX8 incumbent). The source *is* the
tree: nesting is indentation, refactoring is expression extraction
(pure values — proven safe by construction), and a bad argument fails
at the constructor naming its position (`sequence step 1: expected an
activity name or workflow node, got int`). Static typing is real:
constructors take and return node types. Its known cost stands:
deeply nested trees read inside-out, and Python's indentation
discipline is doing the readability work.

**Fluent chain** (`Flow.start(...).parallel(...).retry(...).then(...)`).
Made immutable, it is safe — prefix reuse cannot cross-contaminate
(tested). It reads best for *linear* pipelines, but the probe shows it
degenerates exactly where workflows get interesting: a multi-step
parallel branch cannot stay in the chain and becomes a nested
`Flow.start(...)` expression — combinators wearing a method chain. As
optional sugar over the same nodes it costs ~30 lines and forbids
nothing, so it may exist; it must not be the semantic surface.

**Context-manager builder.** The style's essence is a mutable scope
stack, and everything wrong with it follows: structure comes from
statement order rather than values, `flow.do(...)` returns nothing
reusable (the assignment idiom `order = flow.do(...)` would fake a
dataflow the AX3–AX7 model wires by types and ports, not variables),
builders are single-use, misuse is only caught at runtime
(`branch()` outside `parallel()`, one-branch parallels, use after
`build()` — all tested), and a static type checker sees only
`None`-returning calls. It also cannot be serialized or diffed until
fully executed. Rejected.

**Generator builder.** The driver collects yields into a sequence and
sends back a symbolic handle. The probes reproduce the AX9-B lesson at
the workflow layer: branching on a handle raises (`if approved:` →
"symbolic at authoring time; branch with workflow combinators"), and a
Python `for` over a static range is compile-time **unrolling**, not a
durable loop — `retry`/cycles still require the AX8 combinator. Since
every useful yield is already a combinator expression, the generator
adds ceremony without power. Rejected for structure — while remaining
exactly right *inside* activities (AX9-A), where the yielded values are
effects and the interpreter is transient. One syntax, two layers, no
conflict.

## Rubric

| Dimension | Combinators | Fluent | Context manager | Generator |
| --- | --- | --- | --- | --- |
| Small workflows | good | best (linear) | verbose | good |
| Large/nested workflows | good (indentation) | degenerates | statement soup | good until control flow |
| Type checking | full | full | `None` calls | partial (yields untyped) |
| IDE autocomplete | full | best | weak | weak |
| Refactoring | extract expression | split chain | manual re-order | extract function |
| Error locality | constructor, positional | named call | runtime scope errors | named yield |
| Hidden mutable state | none | none (immutable) | scope stack | driver + handles |
| Loops/cycles | `retry` node | `.retry(...)` | `with retry():` | unrolls; must yield `retry` |
| Prior-output references | types/ports (honest) | types/ports | fakes via variables | fakes via handles |
| AST construction | direct | thin wrapper | deferred, stateful | replayed collection |
| Serialization | canonical (AX1) | same AST | same AST after build | same AST after build |
| Net debugging | source map (AX2) | same | statement→node mapping unclear | yield→node mapping ok |

## Decision shape carried forward

The semantic core is pure combinator values. The default authoring
surface is the combinators themselves. A fluent façade is permitted
sugar for linear flows because it is immutable and lowers to identical
nodes. Builders that derive structure from mutable statement order are
excluded. Generators author activity internals (effects, AX9-A), never
workflow structure.
