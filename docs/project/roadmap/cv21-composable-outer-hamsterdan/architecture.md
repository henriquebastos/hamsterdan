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
host authority composition
  -> readiness application and lifecycle capabilities
       -> workflow boundary values
       -> one-PR Petrus Engine
            -> Impetus Instance/History
            -> engine-facing Motus Dispatch
            -> workflow_bridge
                 -> current Net/seed/gates/contracts

host Worker composition
  -> Motus Worker + WorkerDispatch
       -> readiness typed Activity adapter
            -> concrete github_app or agents capability
```

## Package ownership

| Package | Owns | Must not own |
|---|---|---|
| `workflow` | final outer-facing workflow observations, Activity work, terminals, operation identity, occurrence projection, and detached posture language required by CV21 call sites | Net topology, loop state, folds, Engine lifecycle, provider/agent calls, clocks, persistence, or a copy of current workflow decisions |
| `readiness` | one-PR application, Engine integration over Impetus History and engine-facing Motus Dispatch, the sole legacy bridge, authority, ingress/review/timer/instance custody, and typed Activity adaptation | Motus Worker construction or driving, Activity claim/retry/execution policy, concrete provider or agent construction, process-wide scheduling, HTTP or CLI |
| `github_app` | provider models, App credentials, bounded transport/gateway, webhook and route mechanisms, and lookup-first provider operations | readiness or workflow decisions, agent execution, process supervision |
| `agents` | credential-free request/result/terminal protocol, Pi adaptation, and workspace safety | GitHub credentials, provider publication, host route selection, workflow interpretation |
| `host` | sole concrete construction root for each process role, process-local resources, durable webhook/route custody, concrete Activity registry/resolution and queue binding, agent runtime custody, catalog, discovery, runnable fairness, lifecycle evidence, inspection, API, and service | workflow tokens, History decoding, Activity attempt/lease/retry semantics, or workflow execution decisions |
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
host authority composition ─▶ readiness construction
host Worker composition ────▶ Motus Worker/WorkerDispatch
        ├────────────────────▶ readiness Activity adapters
        ├────────────────────▶ github_app implementations
        └────────────────────▶ agents implementations

readiness application ────▶ workflow boundary values
readiness effects ─────────▶ injected github_app/agents capabilities
readiness runtime ─────────▶ Petrus Engine/Impetus History/
                             engine-facing Motus Dispatch
readiness runtime ─────────▶ readiness.workflow_bridge
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
5. Petrus Engine, Impetus History, or engine-facing Motus Dispatch outside
   readiness runtime; Motus Worker or WorkerDispatch outside host Worker
   composition; and Petrus authoring types outside the narrow readiness and
   bridge call sites that need them;
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

One Hamsterdan authority role schedules many independent one-PR readiness
lifecycles. Each readiness call crosses one named durable cut and returns a
detached value. Motus Workers are separately supervised process roles over
durable Dispatch; the authority role never creates, pumps, or waits inside an
Activity implementation:

```text
provider acquisition
  -> host delivery custody
  -> readiness manifest/admission
  -> bridge translation and identified History admission
  -> retained workflow fold
  -> bridge projection of pending typed Activity
  -> Impetus Activity request/occurrence
  -> Motus Dispatch publication
  -> detached ActivityWait

separately supervised Motus Worker
  -> Dispatch claim/lease
  -> host-composed typed Activity implementation
  -> provider or Agenticus/Pi operation
  -> Dispatch operational terminal

later authority turn
  -> Engine collects Dispatch terminal
  -> Impetus records canonical Activity terminal
  -> bridge converts the exact terminal
  -> retained workflow occurrence
  -> detached readiness posture
  -> host custody completion or tail requeue
```

Convenience drains are finite loops over those calls. They are never hidden
inside application methods. Host sees detached lifecycle and work posture, not
markings, current tokens, legacy classes, or workflow terminal variants.

`host/composition.py` is the sole concrete composition location, not a
single-process mandate. Each executable role invokes the constructor for its
own in-process graph. An external deployment supervisor owns Worker launch,
restart, scaling, placement, and termination; no workflow, readiness lifecycle,
or authority turn spawns a Worker. CV21 qualifies these role boundaries but
does not deploy them.

The first real execution profile uses a separately supervised same-host Motus
Worker over durable Local Dispatch. It does not make SQLite, one host, or one
Worker process part of workflow semantics. Later Absurd/PostgreSQL or ZeroMQ
placement may replace the Dispatch/Worker infrastructure without changing the
Net, Activity declarations, readiness boundary, or terminal path. GitHub and
agent Activities use separate Worker roles so GitHub credentials never enter
agent process territory.

Ingress and authority scheduling are distinct logical roles even when a later
Plan chooses to co-locate them. Their OS-process placement is not decided by
this Worker ruling. Motus Worker roles are not co-located with the authority
role in the accepted production-shaped profile.

After DS5, the smallest long-lived Hamsterdan topology therefore has three OS
processes when ingress and authority are co-located, or four when they are
split:

```text
ingress + authority (or one process for each logical role)
one or more GitHub Worker processes
one or more agent Worker processes
```

The external Amp relay is another service, not a Hamsterdan process. SQLite
Local Dispatch is durable storage, not a daemon. Worker process counts are pool
capacity and never derive from the number of PR Instances. A hundred PRs can
share the same bounded Worker pools.

Inside one agent Attempt, Agenticus/Pi may launch a bounded operation-local Pi
child process. Agenticus owns that child protocol and lifetime; it is not
another long-lived Worker role, does not receive GitHub credentials, and is not
recovery authority. The agent Worker may reconstruct or retry from durable
Motus and agent-lifecycle custody after that child exits or crashes.

## Request and asynchronous process cycles

The provider request cycle ends at durable host custody:

```text
GitHub -> Amp durable webhook relay -> HTTP ingress role
  -> bound and verify request
  -> durably commit delivery identity and normalized observation
  -> return custody acknowledgement
HTTP request ends
```

No readiness fold, Engine advancement, Dispatch claim, provider mutation,
agent execution, or terminal admission is required to return that
acknowledgement. Relay uncertainty may redeliver the same provider identity;
durable custody classifies it without starting another workflow admission.

Outside the request, an authority turn claims one host delivery, advances one
PR through readiness, and either returns detached posture or publishes a Motus
Activity. A Worker turn may continue while ingress or the authority role is
down. After the Worker durably reports an operational terminal, a later
authority turn collects it, lets Impetus author the canonical terminal, and
continues the retained occurrence through the bridge.

Logs are role-local observations correlated by subject/Instance, occurrence,
operation, Attempt, and Worker incarnation. They are not delivery, workflow,
Dispatch, provider-effect, or agent-result authority.

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

History remains the sole workflow-admission ledger. Host delivery, HTTP custody
acknowledgement, readiness staging, History acceptance, and workflow fold are
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
Worker turn, exact terminal correlation, and current-authority fencing at the
required cut. GitHub credentials exist only in the GitHub Worker role and never
enter agent values, state, processes, or diagnostics.

## Durable truth

| Truth | Owner |
|---|---|
| provider acceptance and lookup result | GitHub operation custody or provider truth |
| agent submission, terminal, and receiver delivery | agent lifecycle custody |
| workflow request, occurrence, and canonical terminal | Impetus History through the one-PR Engine composed by readiness |
| Activity task, Attempt, claim, lease, retry, heartbeat, and operational terminal | Motus Dispatch |
| Activity execution and operational report | Motus Worker using the host-composed Activity registry |
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
