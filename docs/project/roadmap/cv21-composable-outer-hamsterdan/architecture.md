# CV21 architecture

This document owns CV21's target architecture. CV20 records the superseded
integrated replacement; it does not govern CV21 implementation.

## Fixed construction strategy

CV21 builds a parallel, non-selectable outer system under `src/hamsterdan2` and
`tests2`. The current application remains the sole runtime. New construction
uses fresh state roots and never opens current runtime state.

CV21 retains one current component: the V5 Petri Net and its workflow-only
contracts. The retained component is mounted only by
`readiness/workflow_bridge.py`. Everything above that seam is new.

```text
host service/API
  -> readiness application and lifecycle capabilities
       -> workflow boundary values
       -> readiness runtime
            -> workflow_bridge
                 -> current Net/seed/gates/contracts
       -> injected GitHub and agent capabilities
  -> concrete github_app and agents construction
```

## Package ownership

| Package | Owns | Must not own |
|---|---|---|
| `workflow` | final outer-facing workflow observations, Activity work, terminals, operation identity, occurrence projection, and detached posture language required by CV21 call sites | Net topology, loop state, folds, Engine lifecycle, provider/agent calls, clocks, persistence, or a copy of current workflow decisions |
| `readiness` | one-PR application, Petrus Engine/History/Dispatch adaptation, the sole legacy bridge, authority, ingress/review/timer/instance custody, and typed effect adaptation | concrete provider or agent construction, process-wide scheduling, HTTP or CLI |
| `github_app` | provider models, App credentials, bounded transport/gateway, webhook and route mechanisms, and lookup-first provider operations | readiness or workflow decisions, agent execution, process supervision |
| `agents` | credential-free request/result/terminal protocol, Pi adaptation, and workspace safety | GitHub credentials, provider publication, host route selection, workflow interpretation |
| `host` | sole concrete construction root, process resources, durable webhook/route custody, agent runtime custody, catalog, discovery, runnable fairness, lifecycle evidence, inspection, API, and service | workflow tokens, Activity resolution, History decoding, Petrus execution |
| `operator` | bounded human command behavior and atomic qualification setup | long-running service policy or workflow interpretation |
| `simulation` | logical time, deterministic scheduling, generic occurrence faults, process generations, budgets, strict artifacts, and replay | owner commands, domain policy, authority, retry, or checker semantics |

The `workflow` package is a boundary-language owner in CV21, not a replacement
workflow implementation. CV22 adds production topology and pure behavior behind
the same outer-facing language after ruling its subnet composition contract.

## Reviewed initial source shape

Paths are admitted by the tracer that first needs them. DS1 does not create an
empty final skeleton.

```text
src/hamsterdan2/
  workflow/
    values.py
    observations.py
    activities.py
  readiness/
    application.py
    runtime.py
    workflow_bridge.py
    ports.py
    authority.py
    custody/
    effects/
    simulation/
  github_app/
    models.py
    config.py
    auth.py
    transport.py
    gateway.py
    effects.py
    routing.py
    webhooks.py
    simulation/
  agents/
    protocol.py
    pi.py
    pi_workspace.py
    simulation/
  host/
    composition.py
    service.py
    discovery.py
    instances.py
    inspection.py
    runnable.py
    qualification.py
    api.py
    clock.py
    agents/
    simulation/
  operator/
  simulation/
```

An owning tracer may merge or split a path when deletion would otherwise
duplicate or mix a coherent responsibility. It must update this map before
implementation. Package initializers export no child facade.

## Import contract

Arrows mean imports:

```text
host composition ─────────▶ readiness construction
        ├─────────────────▶ github_app implementations
        └─────────────────▶ agents implementations

readiness application ────▶ workflow boundary values
readiness effects ─────────▶ injected github_app/agents capabilities
readiness runtime ─────────▶ Petrus + readiness.workflow_bridge
workflow_bridge ───────────▶ allowlisted current workflow modules

owner.simulation ──────────▶ owner production + simulation mechanics
simulation.hamsterdan ─────▶ owner simulation packages
```

The architecture gate rejects:

1. cycles, child re-exports, package-object imports, and production imports of
   simulation;
2. workflow-boundary imports of readiness, host, GitHub, agents, simulation,
   Petrus runtime, clocks, storage, filesystem, HTTP, or provider SDKs;
3. readiness-core imports of concrete provider/agent constructors or host;
4. GitHub and agents importing each other, readiness, workflow, host, or
   simulation;
5. Petrus Engine/History/Dispatch/Worker outside readiness runtime and the
   narrow Petrus authoring types needed inside the bridge;
6. concrete application construction outside `host/composition.py`;
7. any `hamsterdan` import outside `readiness/workflow_bridge.py`;
8. any `host.v5`, old application/effect/custody/timer module, topology
   selector, migration reader, compatibility facade, or V5-named public value;
9. current types in public annotations, returned values, raised exceptions,
   serialized payloads, test fixtures, artifacts, or owner-local state; and
10. wall-clock or sleep calls outside `host/clock.py`.

Positive checks require the real edges only after their owning tracer admits
them. The bridge allowlist and type-leak census apply from DS1.

## Runtime ownership and bounded cuts

One host process supervises many independent one-PR readiness lifecycles. One
call crosses one named durable cut and returns a detached value:

```text
provider acquisition
  -> host delivery custody
  -> readiness manifest/admission
  -> bridge translation and identified History admission
  -> retained workflow fold
  -> bridge projection of pending typed Activity
  -> readiness claim / execute / terminal-record cuts
  -> retained workflow occurrence
  -> detached readiness posture
  -> host acknowledgement or tail requeue
```

Convenience drains are finite loops over those calls. They are never hidden
inside application methods. Host sees detached lifecycle and work posture, not
markings, current tokens, legacy classes, or workflow terminal variants.

## Observation and admission

Webhook is the first acquisition source, not a special workflow path:

```text
PullRequestSnapshot + ObservationProvenance
  -> focused observation + ObservationKey
  -> IngressManifest + AdmissionGrant + ordered IngressEntry
  -> bridge conversion
  -> identified Petrus History admission
  -> retained workflow fold
```

History remains the sole workflow-admission ledger. Host delivery, readiness
staging, History acceptance, workflow fold, and webhook acknowledgement are
distinct observable cuts. Later exact reads and discovery use the same common
admission seam. `AdmissionGrant` is manifest-scoped admission authority, never
fresh effect authority.

## Authority and effects

Readiness authorizes protected work by combining:

1. its durable workflow grant;
2. a fresh exact provider read; and
3. fresh host route/custody evidence.

The complete semantic claim includes phase, incarnation, head, base, and policy.
No source substitutes for another. Every external mutation uses a stable logical
operation, lookup-first ambiguity recovery, at most one mutation attempt per
step, exact terminal correlation, and current-authority fencing at the required
cut. GitHub credentials remain host-side and never enter agent values or state.

## Durable truth

| Truth | Owner |
|---|---|
| provider acceptance and lookup result | GitHub operation custody or provider truth |
| agent submission, terminal, and receiver delivery | agent lifecycle custody |
| workflow request, occurrence, and terminal projection | Petrus History/Dispatch under readiness custody |
| bridge mapping/version and retained workflow identity | fresh CV21 readiness root |
| ingress manifest and admission grant | readiness ingress custody |
| review request and attempt | readiness review custody |
| timer command, acknowledgement, maturity, and delivery | readiness timer custody |
| subject/root/route registration | host catalog |
| runnable fairness and leases | host runnable custody |

Process-local frames, clients, coroutines, exceptions, queues, and simulation
frames are never recovery authority.

## Deterministic simulation

Every outer owner supplies strict commands and observations, eligible actions,
faults, retained modeled state, resource gauges, and an independent local
checker. Root composition mounts those unchanged owner modules and checks only
cross-owner relationships.

The bridge is exercised against the real retained production Net, not a shadow
reducer. Bridge-local correspondence checks exact input conversion, request and
occurrence projection, terminal return, reconstruction, and replay. Existing V5
tests remain workflow-behavior evidence; CV21 adds translation and outer-system
evidence rather than copying those tests.

The shared Timeline understands only action identity, logical time,
deterministic choices, process generations, generic occurrence faults, one-leaf
execution, resource budgets, artifacts, and replay. Domain eligibility and
checker meaning remain with each owner.

## Quality and state isolation

The isolated replacement gate covers only `src/hamsterdan2` and `tests2` and is
introduced with DS1. It includes the accepted Ruff/format/ty, verified ast-grep,
architecture, feedback, pytest, deterministic replay, semantic-coverage,
checker-sensitivity, and resource evidence as their real call sites arrive.

CV21 state roots are fresh, disposable, and visibly separate from current
runtime state. No code path discovers, imports, reads, converts, or mutates a
current root. Packaging, service configuration, deployment, and operator
commands expose no CV21 selector.
