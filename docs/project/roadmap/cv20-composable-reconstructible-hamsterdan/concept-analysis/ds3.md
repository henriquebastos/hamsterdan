# DS3 concept extraction

## Source

- Delivery Story: [`../cv20-ds3-expose-workflow-activity.md`](../cv20-ds3-expose-workflow-activity.md)
- Cross-boundary contracts: [`../api-contracts.md`](../api-contracts.md),
  "Workflow Activity identity", "Activity manifest", "Workflow-runtime cuts"
  and "Readiness cuts"
- Cumulative sequence: [`../delivery-sequence.md`](../delivery-sequence.md),
  "DS3 — One durable Activity"

Reviewed source revision: 2026-08-28 working tree.

## Extracted behavior

DS3 lets workflow alone declare one external-work request. The request has a
stable operation identity and an Engine occurrence; correlation and idempotency
equal the operation identity. Readiness preserves the exact requested work and
identity from History/Dispatch, exposes bounded waiting posture, and does not
execute the effect inline. Reconstruction leaves the request pending.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| Outcome, lines 18–23 | Workflow declares `DashReq`; readiness records its occurrence and reports waiting while Dispatch holds it | workflow Activity, Activity request, Activity occurrence, pending Activity |
| Vertical path, lines 25–39 | The request crosses workflow, Petrus History/Dispatch and detached host inspection without mutation | durable Activity request and waiting posture |
| Fixed design, lines 62–77 | Workflow owns request creation; complete identity is retained; one advancement records at most one request and never executes inline | workflow-owned work, operation identity, correlation, idempotency |
| Acceptance, lines 96–107 | History and Dispatch retain identical occurrence/work/identity and reconstruction preserves it | reconstructible pending Activity |
| API contracts / Workflow Activity identity, lines 109–130 | Every request carries six identity elements and a terminal must match the exact invocation | Activity identity; operation/correlation/idempotency are subordinate identity fields |
| API contracts / Activity manifest, lines 252–288 | One manifest entry declares capability, request, closed terminals, lane, operation derivation and blocked mapping | Activity manifest; gate and terminal variants are API vocabulary |
| API contracts / Workflow-runtime cuts, lines 495–510 | An impure workflow action may record one request but cannot execute an effect inline | durable request boundary; named cuts are mechanics |
| Delivery sequence / DS3, lines 167–174 | DS3 hands off exact request and identity in History/Dispatch with waiting posture | candidates survive into effect execution |

## Later ownership and refinements

- DS4 settles the pending request through distinct claim, effect-observed and
  terminal-recorded positions and returns a typed terminal to its original
  occurrence (DS4 Vertical path, lines 26–37; Fixed design, lines 84–87).
- DS5–DS8 add Activity families without changing the common identity or manifest
  contract (API contracts / First-use ownership, lines 50–63).
- DS8 reuses original Activity/operation correlation for deferred work (DS8
  Fixed design, lines 80–81).
- DS9 maps stale or revoked work to workflow-declared outcomes and keeps host
  from decoding Activity work (DS9 Fixed design, lines 90–93).

## Subordinate vocabulary to evaluate

- `DashReq` is the first request type, not the general concept.
- `ActivityRequested` is a Petrus record/API name for request durability.
- occurrence, operation, correlation and idempotency may be fields within
  Activity identity rather than separate glossary concepts.
- `MANIFEST`, `TOKENS`, gate names, execution lanes and closed terminal variants
  may remain API vocabulary subordinate to Activity declaration.
- waiting posture and individual cut names describe bounded runtime reporting,
  not separate workflow concepts.

## Unresolved DS-review items

- final `DashReq` fields and operation grammar;
- manifest, token, build, seed and gate-wiring signatures;
- public Petrus request/replay/occurrence structures and errors;
- readiness advancement and pending-Activity projection names;
- History/Dispatch diagnostics and request-byte limits; and
- compact workflow names, checker evidence and resource gauges.

## Construction-only exclusions

- The non-selectable tracer handoff and temporary replacement paths disappear
  at DS13.
- Petrus dependency qualification and simulation/checker mechanics prove the
  behavior but are not finished-product concepts.

## Trace handoff

The DS4–DS13 trace is complete in the
[candidate register](candidate-register.md). Whether Activity, Activity request
and Activity identity are distinct concepts remains for later Navigator review.
