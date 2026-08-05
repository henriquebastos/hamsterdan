---
status: Decided
raised: 2026-08-05
decided: 2026-08-05
deciders:
  - Henrique (Navigator, standing authorization)
related:
  - CV16
  - CV16.DS11
---

# Agenticus routing is explicit, host-owned, and fail-closed

## Decision

Hamsterdan's first Agenticus profile is Pi native A2 Local using the direct
Anthropic API-key catalog entry for `claude-sonnet-4-5`. This is static
composition evidence only: it neither reads authority nor claims installation,
provider availability, runtime qualification, or live support.

The selected route is exactly `PI_NATIVE_A2_LOCAL`. `AgentNetRunner` is not an
implementation of that route: it belongs to `AGENT_AS_NET_A5_LOCAL` with a
different Program, Hands, and Continuation topology and must be rejected rather
than substituted.

The host owns two explicit modes: `agenticus` and `legacy-amp`. Agenticus is the
configured adoption route. Legacy Amp exists only for deliberate rollback,
never implicit fallback, and cannot be selected while isolation is required.
Amp A1 provider-managed territory is not accepted as agent isolation.

Before each agent runner call, the host durably claims the operation's complete
mode, profile, and immutable Petrus Catalog snapshot. Restart redispatch must
reconstruct that exact route. Petrus terminal History settles the claim; startup
repairs the narrow crash window where terminal History committed before route
settlement. A complete-route change is refused while prior-route work remains
unresolved, and every claim rechecks the currently active route.

## Rationale

Hamsterdan's host is already the sole composition and credential boundary, and
the product requires credentials to stop there. Pi native A2 Local matches that
ownership and the qualified Petrus profile while preserving the existing
credential-free `AgentRunner` request/result contract. Petrus intentionally does
not own durable Pi/Amp operation routing, so that fence belongs in the host.

## Consequences

- The hard-coded Amp runner default is removed from `HostService`.
- Agenticus execution is selected only after an exact READY Pi installation
  probe on the Petrus-owned A2 host. Composition and probe do not consult
  authority; production's supplier remains unavailable until a bounded live gate.
- Legacy rollback requires explicit mode selection and an explicit isolation
  waiver; no failure can select it automatically.
- Route custody and Petrus History remain separate durable stores with strict
  claim-before-dispatch, History-before-settlement ordering and startup repair.
- No connection custody, runtime supervision, Hands gateway, Attachment,
  territory lifecycle, or effect-fencing implementation is copied from Petrus.
- A settled Pi workspace archive is continuation custody, not host-tree mutation
  authority. Unchanged coding requires the archive to exist; changed coding is
  non-retryably refused until Hamsterdan can reconcile a private staged archive
  with the exact current PR tree and existing publication fence.
