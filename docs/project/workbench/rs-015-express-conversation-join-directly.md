---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es2-imperative-expression-layer/index.md
---

# RS-015 — Express the conversation join directly

## Existing field refined

Starting conversation classification is a relational join: it reads the nine
current readiness concern states, consumes one authorized conversation
observation, and produces one immutable classification request. The arcs made
that join visible, but a Petri-aware adapter repeated all ten runtime types,
searched the binding for them, called the already typed domain function, and
manually serialized its sole output.

## Accepted boundary

`conversation_work(...) -> ConversationClassificationRequest` is now itself a
Petrus direct transformation using the readiness-owned strict Pydantic
converter. Its signature is the complete input contract; the transition arcs
remain the complete relational read/consume contract. The redundant
`_conversation_work(binding, outputs)` adapter was deleted.

No other residual binding helper was generalized. `_put` still owns ordered
heterogeneous outputs; `_route` owns optional and target-dependent outputs;
Petri-aware guards own enabledness and retirement decisions; `_hydrate` and
`_values` still support those advanced handlers with strict replay hydration.

## Validation and review

The exact Net remains 46 places, 69 transitions, and 309 arcs. Focused Net and
host integration passed 104 tests, including conversation authorization,
classification, fan-out, restart, publication, and stale-result behavior.
Quick and full project gates passed. Independent adversarial review returned
`APPROVE` with no required changes.

## Consequences

- The conversation join now reads as one typed domain function plus visible
  relational arcs.
- One duplicate type list and one one-output serialization adapter disappeared.
- Remaining Petri-aware plumbing has an evidenced semantic role; reducing it
  requires a new capability or fragment contract, not another local rewrite.
