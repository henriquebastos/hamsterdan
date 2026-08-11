# Registration evidence given one provider owner

Hamsterdan moved GitHub App registration and selected-repository inventory
interpretation from `HostService` into `GitHubAppClients`. One frozen
`RegistrationInventory` now crosses the provider/host boundary; the host only
atomically reconciles its registry after complete evidence is available.

The provider contract is fail-closed over exact identities, permissions,
events, suspension, status, bounded Link continuation, stable totals, complete
repository rows, and unique IDs/names. Installation credentials are not minted
before installation authority is accepted, and authentication/parsing failures
cannot expose token values through exception chains. This also closes
pre-existing partial-inventory replacement hazards.

Focused evidence passed 174 tests. Quick and full static/type/format/package
and relay gates passed; the Python suite passed 590 tests with one external
route deselected. Final adversarial review approved the provider/host boundary
with no release blocker.
