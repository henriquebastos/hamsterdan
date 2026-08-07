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
Anthropic API-key catalog entry for `claude-sonnet-4-5`. Production accepts
authority only through an explicit absolute path to an owned, bounded `0600`
regular file and exact absolute Pi CLI, Node, and package-root paths. Parsing,
composition, probe, and replay do not read key material. Live support still
requires accepted provider evidence.

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
  authority; a one-shot supplier reads into an erasable buffer only when Petrus
  begins a fresh operation.
- Legacy rollback requires explicit mode selection and an explicit isolation
  waiver; no failure can select it automatically.
- Route custody and Petrus History remain separate durable stores with strict
  claim-before-dispatch, History-before-settlement ordering and startup repair.
- No connection custody, runtime supervision, Hands gateway, Attachment,
  territory lifecycle, or effect-fencing implementation is copied from Petrus.
- A settled Pi workspace archive is continuation custody, not host-tree mutation
  authority. Schema-2 binds exact input archive, route correlation, and effective
  attachment policy to replay identity. Hamsterdan privately validates and
  canonicalizes the settled archive, derives and reproduces its patch against
  the exact requested head, and only then enters the existing publication fence.
- Model-authored diff and path claims are never mutation authority. Reserved
  publication trailers are also refused before idempotency recovery or mutation.
- Startup and FastAPI lifespan failures close every already-owned runtime
  resource so Petrus can revoke connection custody and erase persistent key
  operations. Cleanup uncertainty remains fail-closed.
- The first direct-key live attempt exercised authority once but was rejected by
  the host Git publication boundary before ref mutation. That result does not
  change the selected profile or authorize fallback. Deterministic diagnosis
  and the separately bounded second attempt below still did not establish live
  support.
- Publication qualification retains only a closed, coordinate-free stage
  category in canonical Activity results. Publication-dependent assertions run
  once only after one successful original publication; replay and cleanup
  categories remain separate and cannot overwrite the first cause. This
  evidence contract does not change the AgentRunner protocol or weaken current
  authority, object identity, exact CAS, or idempotency fences.
- The separately authorized second attempt completed one production runtime
  operation but admitted no changed `CodingResult`. The safe boundary is
  `agent_result_unaccepted`; the host must not retroactively infer whether output
  was unchanged or failed schema, correlation, or workspace admission.
- Future coding outcomes retain only a closed adapter/Activity category for
  runtime lifecycle, output schema, correlation, unchanged, unable, or workspace
  reconciliation. Operation/workspace cleanup uncertainty remains a separate
  closed field and cannot replace the first cause. Categorized outcomes are
  terminal without retry or publication; generic unclassified failures retain
  same-route retry fencing. This evidence contains no model output, provider
  diagnostics, coordinates, patches, or exception prose and does not weaken the
  canonical workspace or publication fences.
