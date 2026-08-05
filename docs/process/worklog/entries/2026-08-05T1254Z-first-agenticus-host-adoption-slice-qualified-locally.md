# First Agenticus host-adoption slice qualified locally

Hamsterdan now consumes exact Petrus revision
`ceb36d5db5b3bc9ed13ebc02a9971708d9461b20` directly from Git and resolves the
qualified Pi native A2 Local topology and separately validated direct Anthropic
API-key profile metadata at the host composition boundary. The former
`HostService` Amp default is gone. Explicit
`agenticus` and rollback-only `legacy-amp` modes replace fallback behavior, and
required isolation refuses both legacy execution and Amp A1 semantics.

Every agent Activity now commits its mode, profile, and immutable Catalog
snapshot before entering the unchanged `AgentRunner` protocol. Repeated attempts
reconstruct the same route, every claim rechecks the active complete route,
durable terminal Petrus History settles the claim, and startup repairs the
terminal-history crash window before allowing cutover. Unresolved work blocks a
mode, profile, or snapshot change.

Focused host suites passed 89 tests. `scripts/check full` passed formatting,
Ruff, ty, nine Bun relay tests, source and wheel builds, and 269 Python tests;
the one explicitly opt-in real-provider test remained skipped. No credentials,
provider authority, paid operation, or live agent execution were used.

This is deterministic composition and lifecycle evidence, not complete
migration or live support. Agenticus execution intentionally fails closed until
the next bounded adapter slice, and a later live gate requires an explicit
request after deterministic migration evidence passes.
