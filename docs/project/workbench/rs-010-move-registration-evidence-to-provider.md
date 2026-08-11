---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-010 — Move registration evidence to the provider

## Existing field refined

`HostService.reconcile_registration()` contained the complete GitHub protocol
for App identity, permissions, events, installation selection, suspension,
installation permissions, and selected-repository pagination. The host then
mutated its registry. Provider parsing and host composition were one 99-line
operation.

## Accepted boundary

`GitHubAppClients.registration_inventory(config)` now returns one immutable
provider value:

```python
@dataclass(frozen=True)
class RegistrationInventory:
    installation_id: int
    repositories: tuple[tuple[int, str], ...]
```

The provider boundary validates exact App/account identities, permissions,
events, explicit active suspension evidence, HTTP success, same-origin Link
continuation, a 20-response bound, stable exact repository totals, every
repository shape, and unique repository IDs and case-normalized names. App and
installation reads remain ordered so no installation token is minted before
installation authority is accepted. Transport/authentication failures are
projected to secret-safe `GitHubBoundaryError` values without unsafe chaining.

Only after complete evidence exists does the host atomically replace registry
routes and publish the selected installation identity. Provider failure leaves
both unchanged. `HostService.reconcile_registration()` is now a small
composition operation rather than a GitHub parser.

## Validation and review

Focused provider and host evidence passed 174 tests. `scripts/check quick`
passed static, format, and production type checks. `scripts/check full` passed
package and relay gates, then 590 Python tests with one explicitly external
route deselected. Iterative adversarial review found and closed partial
inventory, test-boundary, pagination, suspension/type, secret-chain, HTTP
status, continuation/cardinality, Link syntax, and duplicate-identity gaps; the
final decision was `APPROVE` with no release blocker.

## Consequences

- GitHub registration protocol has one provider owner and one typed output.
- Host registry mutation remains host-owned, atomic, and downstream of complete
  provider validation.
- The extraction closes pre-existing cases that could destructively reconcile a
  partial portfolio.
- No application, Net, lifecycle, Activity execution, scheduler, storage
  schema, or Petrus behavior changed.
