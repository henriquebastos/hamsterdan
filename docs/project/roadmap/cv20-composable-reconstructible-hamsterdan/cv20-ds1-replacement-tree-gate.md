---
code: CV20.DS1
level: Delivery Story
status: Planned
status_reason: Promoted with CV20; no replacement-tree work is pulled
updated: 2026-08-27
related:
  - index.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS1 — Establish the replacement-tree gate

## Outcome

Create the empty `src/hamsterdan2` and `tests2` skeletons with the isolated
strict Ruff configuration, seven verified ast-grep rules, semantic AST
architecture/enum audit, and `scripts/check` integration. Positive architecture
assertions target explicit construction placeholders from the first commit.

## CV20 contract

This story establishes the complete source/test shape in
[the architecture](architecture.md), the blocking gate in
[the replacement ledger](replacement-ledger.md), and the first state in
[the delivery sequence](delivery-sequence.md). It implements no domain API.

The current V5 source, tests, configuration and runtime remain unchanged. The
new package can be imported only by target tests; it is absent from package
entry points, configuration, deployment and service selection.

## Owned paths

```text
src/hamsterdan2/**                    empty admitted source skeleton
tests2/**                             empty admitted test skeleton and gate tests
quality/hamsterdan2/ruff.toml
quality/hamsterdan2/sgconfig.yml
quality/hamsterdan2/ast-grep/*.yml
quality/hamsterdan2/ast-grep-tests/**
scripts/check                         target gate and collection wiring
```

`pyproject.toml` or test configuration may change only as needed to collect the
new isolated tree; they must not install or expose a second runtime.

## Fixed design

- Every initializer has at most a policy docstring and explicit empty exports.
- No package re-exports a child or acts as a facade.
- Strict Ruff/format, ty, seven ast-grep rules and semantic AST audit block from
  this story onward.
- The AST audit enforces both forbidden and required edges. A disconnected
  empty tree cannot pass by satisfying only negative rules.
- Explicit construction placeholders satisfy required-edge checks until their
  owning story replaces them with real construction.
- Gate configuration is isolated to `src/hamsterdan2`/`tests2`; old V5 is not
  reformatted, broadly suppressed or brought under the new rule set.
- Rule fixtures prove accepted and rejected cases. A suppression is local,
  justified and mechanically checked.

## Position and predecessors

The CV20 architecture and the exact gate/tree contract in the local replacement
ledger are the fixed inputs. This is the first Delivery Story, but it is not
active merely because CV20 is Planned.

## Implementation sequence

1. Expand this DS into gate/skeleton and check-integration Technical Stories.
2. Rule the gate command/diagnostic API below.
3. Create the exact empty source and test paths from the CV20 ledgers.
4. Add isolated Ruff/format and all seven ast-grep rules with fixtures.
5. Add the semantic architecture/enum audit with explicit positive
   placeholders.
6. Wire the gate and target tests into `scripts/check quick`; prove full/release
   inherit it.
7. Verify distribution and current service selection remain unchanged.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- names and arguments of the replacement-specific check commands;
- the minimal fixture DSL/layout for each ast-grep rule;
- stable, path-specific diagnostics for architecture failures;
- how construction placeholders are represented and replaced without weakening
  positive checks; and
- exact per-site suppression syntax and the design reason required with it.

These choices may improve gate usability. They may not change the fixed rule
set, package graph, source/test tree or isolation boundary.

## Done condition

The complete replacement skeleton exists; its gate blocks every rule listed in
the local replacement ledger and every forbidden or missing architecture edge;
rule fixtures prove both acceptance and rejection; and the current runtime is
unchanged and remains the only selectable runtime.

## Rollback

Remove the replacement skeleton and isolated gate. No installed application or
state root refers to it.

## Validation

Run rule fixtures, target Ruff format/check, ty, architecture positive/negative
fixtures, feedback-command tests, and project quick/full gates.

## Expansion boundary

Before implementation, expand this Delivery Story into bounded Technical
Stories for skeleton/gate ownership and check-command integration, then obtain
a Plan Checkpoint. The expansion must update the local CV20 API contract with
the ruled gate/diagnostic names; exploration is not an implementation input.
