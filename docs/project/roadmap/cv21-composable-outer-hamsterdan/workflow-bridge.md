# CV21 workflow bridge

The workflow bridge is CV21's sole temporary legacy adapter. It exists to reuse
proven workflow behavior while every outer owner is rebuilt. It is not a second
application, a V5 facade, a migration layer, or a supported compatibility lane.

## Ownership

The bridge lives at `src/hamsterdan2/readiness/workflow_bridge.py` because
readiness owns the one-PR Petrus Engine integration and the
application-to-workflow boundary. It is constructed by readiness runtime and
receives no provider client, agent runner, host store, clock, credential, or
current application object. Readiness does not own Motus Worker execution:
separately supervised Worker roles claim and execute tasks through Dispatch,
and a later Engine turn collects operational terminals into canonical Impetus
History.

Only this production file may directly import:

```text
hamsterdan.readiness.net_v5.topology
hamsterdan.readiness.net_v5.gating
hamsterdan.contracts.readiness_v5
```

The retained transitive closure is:

```text
hamsterdan.readiness.net_v5/**
hamsterdan.contracts.readiness_v5
hamsterdan.contracts.readiness.WorkflowModel
```

No CV21 test imports that closure to manufacture old tokens. Tests drive the
bridge through new values and inspect new values. Exact old token inspection,
when required to implement a mapping, remains private bridge code covered by
end-to-end correspondence against the real mounted Net.

## New-facing contract

The bridge supplies readiness runtime with one workflow definition containing:

- construction of a fresh Net and seed for one immutable PR Identity;
- the complete Activity declaration and terminal-variant plan;
- conversion of one typed new observation into one exact retained-workflow
  delivery;
- projection of one pending retained request into its exact typed new Activity
  work, occurrence, operation, correlation, and idempotency;
- conversion of one exact typed new terminal back to the original retained
  occurrence; and
- conversion of bounded runtime inspection into detached new lifecycle and
  work state.

Concrete Python signatures are DS1–DS3 Plan decisions made with readiness
runtime and the first real call sites present. They must not expose a generic
`dict`, legacy model, topology path, or untyped terminal. DS2 supplies the first
input signature: exact `HeadObservation`, `ObservationKey`, and authorized
policy become one bridge-private delivery. Bounded History reconstruction
recovers that delivery and validates its exact terminal without exposing a
retained token to host callers.

## Translation laws

Every mapping obeys all of these laws:

1. **Total over the admitted family.** Every allowed retained variant maps to
   one closed new variant. An unknown retained variant fails closed with a new
   bridge-owned diagnostic.
2. **Exact identity.** PR Identity, semantic source identity, occurrence,
   operation, correlation, idempotency, head/base/policy/generation, and timer
   generation are retained or translated by a versioned bijection. They are
   never regenerated from ambient state.
3. **No decision.** Conversion may rename, validate, canonicalize, or render a
   representation. It may not decide that work should exist, select a terminal,
   retry, close, defer, cancel, authorize, or order workflow work.
4. **No legacy escape.** New owners receive only new immutable values. Stored
   Inbox and replay rows contain no legacy module path, class name, exception,
   or serialized wrapper.
5. **Original occurrence return.** A terminal can be admitted only for the
   exact retained request and occurrence from which its new request was
   projected. Work, operation, correlation, and idempotency all match before
   History records the terminal.
6. **Fresh reconstruction.** Restart rebuilds the bridge and current Net from
   the fresh CV21 root. Process-local conversion objects and returned values are
   never recovery authority.
7. **Bounded refusal.** Malformed, unknown, mismatched, or oversized values fail
   before mutation with finite, secret-free diagnostics.

A pure representation conversion may turn the retained dashboard request's
entries and digest into the accepted complete publication command expected by
the new provider adapter. It may not infer a dashboard request when the Net did
not emit one or alter the Net's single-flight/recovery ordering.

## Family census

The bridge grows only from a real tracer call site. The implementation and its
architecture test keep a closed census with these columns:

```text
new family
retained input/work/terminal variants
identity and operation mapping
owning tracer
correspondence scenarios
removal replacement in CV22
```

| Family | First CV21 tracer | Required direction |
|---|---:|---|
| PR Identity, seed, lifecycle stage | DS1 | retained runtime state → detached new state |
| Head observation | DS2 | `HeadObservation` → retained `HeadSeen` at `on_head`; open generation 1 only; exact SHAs; explicit-true mergeability; authorized policy; strict/current base true/false; versioned identified History acceptance and exact source completion |
| draft/ready/comment/human acquisition as first used | later owning tracer | focused new observation → exact retained ingress token; no family is implied by the Head mapping |
| dashboard publication | DS3 | retained request → typed new Activity; typed new terminal → retained variant |
| provider publication and recovery outcomes | DS4 | new effect outcome → exact retained terminal |
| review and conversation agent work | DS5 | retained work ↔ typed new request/result terminal |
| mutation work and publication | DS6 | retained work ↔ exact new causal operation and terminal |
| CI evidence, rerun, and repair | DS7 | focused observation/work/terminal in both directions |
| reminder and deferred timers | DS8 | retained timer command/due fact ↔ new timer state values |
| closure and remaining lifecycle/authority outcomes | DS9 | focused new evidence and exact retained result families |

DS10–DS12 add no workflow family unless a real discovery or qualification path
exposes an omission. An omission updates this census before implementation; it
does not authorize a generic fallback.

The complete first DS2 mapping is delivered fail-closed under
`workflow-bridge/head-seen-intake@4`. It replaces the earlier task-shaped
identities because fresh CV21 roots have no compatibility or migration lane.
The webhook-derived `HeadObservation` carries exact PR Identity, branch tips,
and lifecycle semantics. Retained `HeadSeen` consumes only exact head/base SHAs,
explicit-true mergeability, the policy authorized with the Inbox row,
`strict_base=True`, and `base_current=False`. Policy does not enter
`ObservationKey` semantic equality, but it does enter the History delivery
identity. Provider time, route, DeliveryId, and Inbox sequence enter neither.

Only generation 1, lifecycle `open`, `draft=False`, and `merged=False` is
admitted. Closed, merged, and draft snapshots are rejected before History. The
bridge does not fabricate `DraftSeen`, `ReadySeen`, or `CloseSeen`, and does not
infer currentness, ordering, retry, effect authority, or a workflow decision.

`history-delivery:v2:sha256:<digest>` binds bridge identity, observation key,
and authorized policy revision. The Webhook Inbox durably binds that prepared
Intake to one delivery before public `Engine.accept_delivery` runs. A first
offer appends `ExternalEventDelivered` and `FiringBegun`; exact unfinished
reoffer returns the same occurrence without append. The Inbox outcome
`recorded` means that History accepted the delivery. It is not a fold or
workflow-completion record.

A later PR authority turn reads one complete finite History page and selects
the oldest unfinished bridged occurrence. It exact-reoffers that History-owned
source/token/identity, accepts only the correlated carrier, and calls public
`Engine.complete_delivery` once. The result must consume nothing, produce only
the exact `HeadSeen` at `life.heads`, and contain the ordered `FiringBegun`,
`TokensProduced`, `FiringCompleted` batch for the same occurrence. If response
loss leaves the occurrence already complete, the same History page proves the
exact terminal and returns `already_completed`; no second completion call or
host completion record exists.

Process tests use actual `SIGKILL` after raw Inbox commit, after History
acceptance, and after History completion. Fresh composition converges through
exact Inbox reconstruction or History reoffer without a second acceptance or
completion. Correspondence caps shared History at 128 MiB, each workflow at one
4,096-record page, and a fresh History write at 1 MiB of reserved headroom.
Malformed Inbox or History evidence fails with fixed owner diagnostics.

## Prohibited reuse

The bridge cannot import or call:

- `hamsterdan.host.v5` or another current host module;
- the current V5 application/runtime, ingress, claim, gates, review, mutation,
  rerun, timers, provider, agent, or Git publication implementation;
- current stores, service configuration, deployment paths, or runtime roots;
- current deterministic World helpers as production behavior; or
- a test fake that reimplements a retained fold.

The bridge may use only the current workflow topology, seed, pure Net helpers,
Activity gate declarations, and token contracts necessary to mount that Net.

## Correspondence evidence

Each admitted family adds scenarios that:

1. create only new command values;
2. mount the real retained production Net through the bridge;
3. drive one action at a time through named acceptance, fold, request, Dispatch
   publication, Worker operational-terminal, Engine-collection, and Impetus
   canonical-terminal cuts;
4. from DS4 onward, prove that a Worker can claim, execute, and report without
   the bridge or authority role on its call stack;
5. compare exact new observations with independently derived expectations;
6. crash at every newly introduced durable cut, reconstruct from a fresh object
   graph, and reach the same result;
7. exactly replay the expanded action sequence; and
8. mutate one mapping field or identity comparison and prove that the checker
   fails.

Existing V5 workflow tests and accepted CV17 journeys prove retained behavior.
CV21 correspondence proves that the bridge neither loses nor invents meaning
at the new boundary. It does not copy all V5 assertions into `tests2`.

## Removal test

CV22 has removed the bridge only when:

- readiness runtime receives the new workflow production factory at the same
  capability seam;
- no outer import, value, persistence schema, command, simulation module, or checker
  changes merely because the provider changed;
- `src/hamsterdan2` and `tests2` contain no `hamsterdan` import;
- every family correspondence scenario passes against the new workflow with
  the bridge-specific side removed; and
- the bridge, its mapping census, its fresh retained-workflow state, and every
  V5-named construction artifact are deleted together.
