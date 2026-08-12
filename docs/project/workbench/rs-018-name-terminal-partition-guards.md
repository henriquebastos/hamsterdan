---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es2-imperative-expression-layer/index.md
---

# RS-018 — Name terminal partition guards

## Existing field refined

Three acceptance/retirement boundaries still expressed exact terminal
partition rules through generic binding adapters or inline negated lambdas:
conversation publication acceptance, invalid change-intent retirement, and
unrecoverable publication-intent retirement.

## Accepted boundary

Each transition now uses a named strict typed predicate with one parameter for
every selected typed arc:

- current conversation publication results accept through exact authority and
  operation ownership;
- a change intent retires exactly when it cannot authorize mutation;
- a publication recovery intent retires exactly when no owned blocked
  publication can replay its retained request.

The latter two predicates remain explicit complements of their corresponding
authorization rules. Petrus validates their typed-arc plans, and Hamsterdan's
Pydantic converter owns strict replay hydration.

Dynamic per-target recovery authorization, heterogeneous result-retirement
loops, subset-selection guards, and snapshot joins remain Petri-aware. No
partition DSL, correlation expression, or generic retirement family was added.

## Validation and review

The exact Net remains 46 places, 69 transitions, and 309 arcs. Focused Net and
host integration passed 104 tests, including stale publication, explicit
recovery, invalid intent, and current operation acceptance. Quick and full
gates passed with 584 Python tests and 9 Amp webhook relay tests. Independent
adversarial review returned `APPROVE` with no required changes.

## Consequences

- Three acceptance/retirement decisions now have explicit typed call stacks.
- Complementary authorization and retirement rules are visible as domain
  predicates, making a future mechanical partition check possible without
  committing to an expression language.
- Remaining generic binding code continues to represent heterogeneous or
  relational topology rather than accidental fixed-shape plumbing.
