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

- Petrus supplies first-class scope and occurrence provenance in real History,
  Engine, and Dispatch contracts as of
  `b0bb336a077b70b6d702aef26acbf8ad1381f9b3`.
- Dispatch cancellation is post-commit outbox/reconciliation work.
- Same-generation operation ownership remains in the Hamsterdan Net.
- Scope generation does not automatically equal every business epoch or
  publication operation.
- High availability, actor modules, and hard side-effect cancellation remain
  separate decisions.

Hamsterdan stages each generation start or stop as an unscoped command, performs
the exact scope reset or close, and then delivers a matching
`GenerationCommit`. The Net requires both command and commit. Reconciliation
repairs any interrupted boundary before ordinary provider reconciliation, so no
cross-component transaction is implied.

Terminal publication exhaustion does not reopen work automatically. Capability
failure retains an immutable recovery request, and only an explicit authorized
intent naming the exact target and blocked operation may create one fresh
Activity occurrence. The stable provider-effect operation is reused for
lookup-first reconciliation. Unknown terminal failures instead become typed
nonrecoverable publication faults.
