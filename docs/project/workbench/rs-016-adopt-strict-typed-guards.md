---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es2-imperative-expression-layer/index.md
---

# RS-016 — Adopt strict typed guards

## Existing field refined

Petrus could derive typed guards internally, but its public authoring shorthand
fixed their converter to the permissive dataclass default. Hamsterdan therefore
wrapped guards in `_typed_guard(types, predicate)`, hydrated every selected
token itself, and searched values by runtime type to preserve strict Pydantic
replay validation.

Petrus `3b41f19aa68ed228e68324f7c6888371f805b560` adds the provider-neutral
`typed_guard(..., converter=...)` carrier without changing ordinary callable
guards or any canonical Net/runtime contract.

## Accepted boundary

Hamsterdan pins that exact Petrus revision. Eight transitions whose guards have
one honest parameter for every selected typed arc now use the public carrier:

- admission refresh and review retry;
- Actions acceptance;
- change, rerun, repair, and reply authorization;
- Actions-basis retirement.

Existing domain predicates gained exact Pydantic input and `bool` return
annotations. Admission refresh gained one named predicate because its
competition with review retry is a real workflow rule, not adapter mechanics.
Petrus now checks typed-arc/signature correspondence when building the Net and
Hamsterdan's converter strictly validates every selected replayed value.

`_guard`, `_typed_guard`, `_hydrate`, and `_values` remain for guards that
intentionally select only part of a larger relational binding, dynamic
loop-generated transition families, broad snapshot joins, and advanced
Petri-aware handlers. Adding ignored parameters or one-off wrappers merely to
increase a conversion count was rejected.

## Validation and review

The exact Net remains 46 places, 69 transitions, and 309 arcs. Focused Net and
host integration passed 104 tests. Quick and full project gates passed,
including 584 Python tests and 9 Amp webhook relay tests. Independent
adversarial review returned `APPROVE` with no required changes.

## Consequences

- Strict typed guard binding is now a Petrus contract rather than Hamsterdan
  adapter code for the converted transitions.
- The eight guards form an executable carrier baseline for ES-002's broader
  guard-decomposition audit.
- This does not validate or introduce declared correlation/filter expressions;
  the audit's 45/48 classification still requires mechanical evidence before a
  correlation language is designed.
