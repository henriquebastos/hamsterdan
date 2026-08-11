---
status: Completed
pulled: 2026-08-11
navigator: Henrique
source: ../exploration/es1-petri-net-motus-boundary/index.md
---

# RS-006 — Remove the false application query API

## Existing field refined

`PrReadinessApplication` returned ad hoc presentation dictionaries from
`reconcile`, `activate`, `route_comment`, and `projection`. Production ignored
every result; only tests consumed the dictionaries. The surface made one
command-oriented reconciliation adapter look like a second application query
model and preserved alternate entry points after RS-005 unified host
activation.

## Refinement boundary

Make `activate(trigger, *, comment=None) -> None` the sole application command.
Keep provider reads, lifecycle repair, Activity composition, effect fencing,
comment admission, workflow deliveries, and their exact ordering unchanged.
Do not introduce a typed replacement projection merely to preserve tests.

```text
HostService._activate_instance
  -> PrReadinessApplication.activate(trigger, comment?) -> None
       -> _reconcile(trigger) exactly once
            -> provider evidence
            -> generation lifecycle and workflow deliveries
       -> optional ConversationObservation delivery
```

Tests now inspect canonical `ReadinessSnapshot` values, lifecycle places,
`workflow_wait(snapshot)`, and observable conversation behavior. Public
`reconcile`, `route_comment`, and `projection` no longer exist.

## Analysis conclusions

- Generation start, stop, and repair remain one staged
  command/scope/commit protocol. Extracting a collaborator would relocate
  crash-sensitive complexity and worsen the call trace.
- Activity/effect construction remains legitimate composition around the fresh
  `AuthorityLease`; a dependency bundle would conceal rather than remove it.
- Provider evidence aggregation remains staged deliberately after pull-request
  lifecycle checks. The unused `VerifiedSnapshot` is not expanded without a
  demonstrated shared consumer.
- Duplicate comment admission is a real follow-up candidate, but changing from
  host-plus-application validation to one provider-ingress trust boundary
  requires an explicit security decision and is not incidental cleanup.

## Validation and review

Focused application/service evidence passes 108 tests. All former projection
assertions now observe canonical workflow state or effects. Static and format
checks pass. Independent adversarial review returned `APPROVE`: activation
reconciles exactly once, comments cannot double-deliver, provider ordering and
lifecycle behavior are unchanged, and no repository consumer of the removed
surface remains.

## Consequences and next boundary

- The application exposes commands and runtime capabilities, not a lossy
  presentation model.
- Forty-four net production lines were removed with no replacement abstraction.
- The Net remains at 46 places, 69 transitions, 309 arcs, and 17 retirements.
- The next candidate is one authoritative provider-ingress comment admission
  policy. The Navigator must choose that boundary before duplicate validation
  can be removed.
