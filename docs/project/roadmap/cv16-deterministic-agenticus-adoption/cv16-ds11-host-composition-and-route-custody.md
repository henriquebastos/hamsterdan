---
code: CV16.DS11
level: Delivery Story
status: Qualified Locally
status_reason: Exact Pi native A2 Local composition and durable same-route lifecycle gates pass the full project check without provider authority
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
- Preserve the existing request/result protocol and all readiness business and
  effect policy.

## Local evidence

Focused host composition, Activity, runtime, architecture, application, and
service suites pass 89 tests. The full project gate passes formatting, Ruff, ty,
nine Bun relay tests, source and wheel builds, and 269 Python tests with the one
opt-in provider test skipped. No provider authority or paid/live operation was
run.

## Limits

The selected Catalog snapshot proves static compatibility and explicit
enablement only. The `agenticus` runner deliberately fails closed. This slice
does not probe a Pi installation, read an Anthropic key, instantiate the Pi
adapter, materialize connection custody, create territory, run Hands, manage
Attachment or Continuation lifecycle, or claim live support. Route custody and
Petrus History are separate stores joined by ordering and startup repair rather
than a cross-store transaction.

## Next slice

Add the smallest host adapter that maps the unchanged Hamsterdan `AgentRunner`
protocol onto the qualified Pi runtime lifecycle, including installation probe,
Petrus-owned custody/Hands/Attachment/Motus composition, candidate admission,
and deterministic recovery tests. Only after those gates pass should a separate,
explicitly bounded live-authority qualification be requested.
