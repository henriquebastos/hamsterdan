---
code: CV16.DS11
level: Delivery Story
status: Qualified Locally
status_reason: Exact Pi native A2 Local composition, probe-gated adapter, and durable same-route lifecycle gates pass without provider authority
updated: 2026-08-05
---

# CV16.DS11 — Host composition and operation-route custody

## Scope

- Pin Petrus exactly to `ceb36d5db5b3bc9ed13ebc02a9971708d9461b20`.
- Register and explicitly enable the exact Pi native A2 Local topology in a
  host-owned Catalog, retain its provider-neutral immutable snapshot, and bind
  Anthropic `claude-sonnet-4-5` as separately validated profile metadata.
- Expose only `agenticus` and `legacy-amp`; reject implicit selection, reject Amp
  A1 as isolation, and keep legacy as explicit rollback.
- Claim each operation's complete route before dispatch, reconstruct only that
  route on retry, settle after durable terminal History, repair the terminal
  crash window on startup, and refuse cutover with unresolved prior-route work.
- Derive a distinct deterministic Pi runtime-operation identity for each coding
  attempt while keeping every attempt fenced to that one durable Activity route.
- Preserve the existing request/result protocol and all readiness business and
  effect policy.
- Adapt the unchanged protocol to an injected public Pi A2 operation lifecycle,
  selecting it only after an exact READY installation probe. A missing or
  non-ready probe remains fail-closed and never selects legacy Amp.
- Keep `PI_NATIVE_A2_LOCAL` distinct from `AGENT_AS_NET_A5_LOCAL` and its
  AgentNetRunner Program, Hands, and Continuation topology.

## Local evidence

Focused adapter, host composition, Activity, runtime, architecture, application,
and service suites pass 105 tests. The full project gate passes formatting,
Ruff, ty, nine Bun relay tests, source and wheel builds, and 285 Python tests
with the one opt-in provider test skipped. No provider authority or paid/live
operation was run.

## Limits

The selected Catalog snapshot and READY probe prove deterministic compatibility
and installation only. Production startup deliberately remains fail-closed
because no Petrus-owned A2 host factory is injected. This slice does not read an
Anthropic key, start a real provider operation, materialize connection custody,
create territory, run Hands, manage Attachment or Continuation lifecycle, or
claim live support. Route custody and Petrus History are separate stores joined
by ordering and startup repair rather than a cross-store transaction. A live
runtime also requires Petrus-owned lookup-first recovery when a process restarts
after a completed Pi operation was closed but before terminal Activity History.

## Next slice

Petrus should first expose one supported A2 host factory that owns connection
custody, Motus binding, EpisodeAttachment, Hands gateway, continuation/turn
stores, and verified teardown behind a credential-free start request. Its probe
must not consult authority and its start must materialize authority at most once.
After Hamsterdan consumes and deterministically qualifies that factory, request
a separate explicitly bounded live-authority gate.
