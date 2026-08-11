---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es2-imperative-expression-layer/index.md
---

# RS-017 — Name lifecycle guards

## Existing field refined

Six generation transitions embedded lifecycle authority in untyped lambdas at
their wiring sites. Initial and resumed birth additionally captured an expected
relation from a loop. Understanding why a generation could start or stop
required reading closure parameters, a duplicated type tuple, and several
inline comparisons together.

## Accepted boundary

Initial, resumed, and superseding generation birth and active, dormant, and
seed generation stop now use named predicates with exact Pydantic input and
`bool` return annotations. Shared commit/start and commit/stop matching are
named once as domain atoms. Each transition uses Petrus's strict typed-guard
carrier, so its complete selected-arc contract is checked while building the
Net.

The topology remains explicit. Generation birth still creates the complete
concern cohort, and each stop route still has its distinct output places and
handler. No lifecycle fragment, relation DSL, correlation expression, or
generic transition descriptor was introduced.

## Validation and review

The exact Net remains 46 places, 69 transitions, and 309 arcs. Focused Net and
host integration passed 104 tests, including generation create, resume,
supersession, stop, restart, and lifecycle-scope recovery. Quick and full gates
passed with 584 Python tests and 9 Amp webhook relay tests. Independent
adversarial review returned `APPROVE` with no required changes.

## Consequences

- Lifecycle enabledness now appears in named domain call stacks rather than
  captured authoring lambdas.
- Commit-boundary equality is visible as a reusable semantic atom without
  introducing an expression language.
- This is production clarity evidence only; it does not revive the rejected
  experimental `GenerationBirth` or `GenerationStopRoute` families.
