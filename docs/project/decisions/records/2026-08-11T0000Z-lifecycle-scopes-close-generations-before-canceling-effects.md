# Lifecycle scopes close generations before canceling effects

## Decision

Hamsterdan will adopt production Petrus lifecycle scopes identified by
`(name, generation)`. Closing or resetting a scope first commits canonical
History and only then releases recoverable Dispatch cancellation instructions.
History append order decides close/completion races.

Closing a generation discards exact queued occurrences and consumed firing
inputs. Inputs are not implicitly restored; a domain requiring compensation
must model it explicitly. Cancellation fences future accepted execution but
does not claim an ambiguous external effect never happened. Late terminals are
durably acknowledged or quarantined and cannot alter closed workflow state.

Ingress proven to target a closed generation is canonically acknowledged and
dropped. Ingress with uncertain generation is quarantined rather than silently
dropped or interpreted as current.

## Rationale

The independent scope experiment proved replay-stable close/reset, exact
occurrence cleanup, append-ordered races, and quarantine while refuting thin
Engine-policy cleanup, failure-as-cancellation, timestamp ordering, and
cancel-before-commit. Discarding a closed generation is the smallest coherent
meaning for PR lifecycle supersession; generic restoration would recreate work
outside current authority.

## Consequences

- Petrus needs first-class scope and occurrence provenance in real History,
  Engine, and Dispatch contracts.
- Dispatch cancellation is post-commit outbox/reconciliation work.
- Same-generation operation ownership remains in the Hamsterdan Net.
- Scope generation does not automatically equal every business epoch or
  publication operation.
- High availability, actor modules, and hard side-effect cancellation remain
  separate decisions.
