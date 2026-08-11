---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es2-imperative-expression-layer/index.md
---

# RS-014 — Express typed acceptance directly

## Existing field refined

Six acceptance transitions with one unambiguous output hid their domain rule
behind generic Petri binding plumbing. The reader had to follow token hydration,
runtime type lookup, a reflected folder implementation, output position, and
token serialization to discover a simple typed transformation.

The strict Pydantic payload converter was also owned by `host` even though both
the readiness Net and host-composed Activities need the same readiness contract
boundary.

## Accepted boundary

Human observation, change completion, repair completion, and conversation,
dashboard, and readiness publication acceptance are now explicit Petrus direct
transformations. Their signatures state every selected typed input and their
single typed output. For example:

```python
def _accept_dashboard(
    authority: Authority,
    state: DashboardPublicationState,
    result: DashboardPublicationResult,
) -> DashboardPublicationState:
    ...
```

`Authority` remains explicit because the transition reads it to authorize the
firing even though folding does not mutate it. Dynamic fan-out, optional
outputs, multiple owners, and target-aware routing remain Petri-aware handlers;
forcing them through direct syntax would hide rather than clarify topology.

`PydanticPayloadConverter` moved from `host` to `readiness`, beside the strict
workflow values whose replay and result conversion it enforces. Host Activities
consume that boundary rather than owning it.

## Production boundary

An Activity-bridge or universal `owned_effect` combinator was not introduced
into production. The smallest repeated bridge was already clearer as
`work >> transition >> result`; forcing every variant through one broad helper
would encode its exceptions as configuration. The independent ES-002 branch
continues to test a small grammar of named semantic fragment families against
exact regenerated topology. RS-014 deliberately supplies concrete production
evidence to that experiment rather than promoting its vocabulary early.

## Validation and review

The exact Net remains 46 places, 69 transitions, and 309 arcs. Existing unit
and host integration portfolios prove strict replay hydration, current-authority
guards, accepted folding, stale-result retirement, restart, and durable
publication behavior. Quick and full project gates passed. Adversarial review
approved the expression boundary without finding a behavior or ownership
regression.

## Consequences

- Simple acceptance rules read as domain function signatures rather than
  generic token plumbing.
- Petri-aware mechanics remain visible exactly where topology is genuinely
  dynamic.
- The change improves expression clarity but does not claim to simplify the
  workflow graph or establish an imperative DSL.
- ES-002 remains open: future syntax must remove a demonstrated concept, not
  conceal arcs behind a configurable helper.
