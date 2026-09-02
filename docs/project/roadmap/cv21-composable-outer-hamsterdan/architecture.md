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
| `workflow` | final outer-facing workflow observations, Activity work, terminals, operation identity, occurrence projection, and detached state language required by CV21 call sites | Net topology, loop state, folds, Engine lifecycle, provider/agent calls, clocks, persistence, or a copy of current workflow decisions |
| `readiness` | one-PR Engine integration over shared Impetus History and engine-facing Motus Dispatch, source-neutral projection, the sole legacy bridge, and typed Activity adaptation | Webhook Inbox persistence/scheduling, Motus Worker construction or driving, concrete provider or agent construction, process-wide scheduling, HTTP or CLI |
| `github_app` | provider models, App credentials, bounded transport/gateway, webhook and route mechanisms, and lookup-first provider operations | readiness or workflow decisions, agent execution, process supervision |
| `agents` | credential-free request/result/terminal protocol, Pi adaptation, and workspace safety | GitHub credentials, provider publication, host route selection, workflow interpretation |
| `host` | sole concrete construction root for each process role, shared application database, PR workflow identities, Webhook Inbox and its worker, concrete Activity registry/resolution and queue binding, agent runtime state, discovery, runnable fairness, lifecycle evidence, inspection, API, and service | workflow tokens, History decoding, Activity attempt/lease/retry semantics, or workflow execution decisions |
| `operator` | bounded human command behavior and atomic qualification setup | long-running service policy or workflow interpretation |
| `simulation` | logical time, deterministic scheduling, generic occurrence faults, process generations, budgets, strict artifacts, and replay | owner commands, domain policy, authority, retry, or checker semantics |

The `workflow` package is a boundary-language owner in CV21, not a replacement
workflow implementation. CV22 adds production topology and pure behavior behind
the same outer-facing language after ruling its subnet composition contract.

## Reviewed initial source shape

Paths are admitted by the tracer that first needs them. DS1 does not create an
empty final skeleton.

DS1 and the glossary-aligned DS2 implementation admit this source shape:

```text
src/hamsterdan2/
  github_app/
    models.py
    webhooks.py
  workflow/
    values.py
    observations.py
  readiness/
    intake_values.py
    projection.py
    runtime.py
    workflow_bridge.py
  host/
    api.py
    application.py
    composition.py
    database.py
    pr_workflows.py
    values.py
    webhook_inbox.py
```

The following cumulative shape remains directional for later tracers. A later
story still admits each path only when a real vertical call site needs it.

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

## Runtime ownership and bounded checkpoints

One Hamsterdan authority role schedules many independent one-PR readiness
lifecycles. Each readiness call crosses one named durable checkpoint and returns a
detached value. Motus Workers are separately supervised process roles over
durable Dispatch; the authority role never creates, pumps, or waits inside an
Activity implementation:

```text
signed provider delivery
  -> raw Webhook Inbox retention and HTTP 200
  -> later host normalization and semantic Intake classification
  -> bridge translation and unfinished identified History acceptance
  -> later exact retained source completion owned by History
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
  -> detached readiness state
  -> application checkpoint or tail requeue
```

Convenience drains are finite loops over those calls. They are never hidden
inside application methods. Host sees detached lifecycle and work state, not
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

HTTP ingress, Webhook Inbox processing, and PR authority scheduling are
distinct logical roles even when a later Plan chooses to co-locate them. The
Webhook Inbox Worker is host-owned and is not a Motus Worker. Their OS-process
placement is not decided by this Worker ruling. Motus Worker roles are not
co-located with the authority role in the accepted production-shaped profile.

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

The provider request cycle ends at the raw Webhook Inbox:

```text
GitHub -> Amp durable webhook relay -> HTTP ingress role
  -> bound exact headers/body -> verify HMAC
  -> commit DeliveryId, event, exact raw body, and body digest
  -> return HTTP 200
HTTP request ends
```

The request neither parses JSON nor opens readiness, History, or Dispatch.
`DeliveryId` classifies transport redelivery. Same ID/event/body returns the
original Inbox sequence as a duplicate; changed evidence records a bounded
collision digest without overwriting the original body. Valid signed malformed
JSON and unsupported events are retained for later rejection. Invalid transport
or HMAC is refused before persistence.

A later host-owned `WebhookInboxWorker` selects one Inbox row. It parses and
normalizes through `github_app`, binds configured route evidence, projects a
source-neutral `HeadObservation`, and computes `ObservationKey`. This worker is
not a Motus Worker and no Activity is involved. Provider timestamp, provenance,
delivery identity, route, policy, and Inbox order remain outside semantic
equality. PR Identity is included, but is not itself a deduplication key: one PR
may produce many different observations.

One application transaction reconstructs the exact row and workflow binding,
then durably authorizes only the first owner of a novel key. Same key and bytes
becomes `duplicate`; key/bytes disagreement or unsupported evidence becomes
`rejected`; unknown PR Identity remains pending for later registration. Durable
authorization prevents another delivery from reaching History while the first
handoff is uncertain.

Only an authorized novel observation reaches public `Engine.accept_delivery`.
Fresh acceptance commits `ExternalEventDelivered` and `FiringBegun`; exact
reoffer recovers the same occurrence without append. The application
transaction then marks the Inbox row `recorded`. If the process dies after the
History commit, the application transaction rolls back while History survives;
fresh processing exact-reoffers and records the handoff.

The Inbox owns no later completion mark. A PR authority turn derives the oldest
unfinished bridged occurrence from one bounded History page, exact-reoffers its
source/token/identity, and calls public `Engine.complete_delivery` only for that
carrier. A prior successful terminal returns `already_completed` from History
alone. Completion does not run a broad drain, advance `life.admit_head`, create
Dispatch, run a Worker, read the provider, or start an agent.

Fresh state uses shared `hamsterdan.sqlite3`, `history.sqlite3`, and
`dispatch.sqlite3`. The application file contains exactly `pr_workflows` and
`webhook_inbox`; no per-PR database, catalog, ingress/staging database,
manifest, grant, accepted pointer, fold table, or host completion receipt
exists. Separate application and History files permit the application writer to
hold its transaction while Petrus writes through an independent connection.

Outside the request, an authority turn claims one host delivery, advances one
PR through readiness, and either returns detached state or publishes a Motus
Activity. A Worker turn may continue while ingress or the authority role is
down. After the Worker durably reports an operational terminal, a later
authority turn collects it, lets Impetus author the canonical terminal, and
continues the retained occurrence through the bridge.

Logs are role-local observations correlated by PR Identity/workflow identity,
occurrence, operation, Attempt, and Worker generation. They are not delivery,
workflow, Dispatch, provider-effect, or agent-result authority.

## Observation and admission

Webhook is the first acquisition source, not a special workflow path:

```text
verified DeliveryId + exact raw body in Webhook Inbox
  -> later normalized provider snapshot
  -> focused HeadObservation + ObservationKey
  -> durable novel authorization in the same Inbox row
  -> bridge conversion + identified Petrus History acceptance
  -> later History-owned completion
```

History remains the sole workflow ledger. The Inbox owns raw transport
evidence, semantic authorization, and its Intake outcome. `recorded` means the
exact identified delivery reached History; it is not a completion marker.
Later exact reads and discovery use the same focused observation boundary.
No manifest, grant, admission-decision table, accepted pointer, or host
completion record exists.

## Authority and effects

Readiness authorizes protected work by combining:

1. its durable workflow intent in History;
2. a fresh exact provider read; and
3. fresh host route and generation evidence.

The complete semantic claim includes stage, generation, head, base, and policy.
No source substitutes for another. Every external mutation uses a stable logical
operation, lookup-first ambiguity recovery, at most one mutation attempt per
Worker turn, exact terminal correlation, and current-authority fencing at the
required checkpoint. GitHub credentials exist only in the GitHub Worker role and never
enter agent values, state, processes, or diagnostics.

## Durable truth

| Truth | Owner |
|---|---|
| signed raw delivery, transport duplicate/collision, semantic authorization, and Intake outcome | host Webhook Inbox in `hamsterdan.sqlite3` |
| PR Identity to workflow identity and generation | host `pr_workflows` in `hamsterdan.sqlite3` |
| provider acceptance and lookup result | GitHub operation state or provider truth |
| agent submission, terminal, and receiver delivery | agent lifecycle state |
| workflow request, occurrence, and canonical terminal | Impetus History through the one-PR Engine composed by readiness |
| Activity task, Attempt, claim, lease, retry, heartbeat, and operational terminal | Motus Dispatch |
| Activity execution and operational report | Motus Worker using the host-composed Activity registry |
| bridge mapping/version | readiness workflow bridge |
| exact observation acceptance, unfinished occurrence, and successful terminal | Impetus History through public `Engine.accept_delivery` and `Engine.complete_delivery` |
| review request and attempt | readiness review state |
| timer command, acknowledgement, maturity, and delivery | readiness timer state |
| route registration | host application state |
| runnable fairness and leases | host runnable state |

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

DS2 deterministic evidence drives the production HTTP, application SQLite,
bridge, shared History, and retained Net seams directly. It distinguishes raw
Inbox retention, transport duplicate/collision, semantic
pending/recorded/duplicate/rejected, identified unfinished acceptance, and
History-owned completion. Concurrency covers two deliveries competing for one
semantic observation and multiple distinct observations for one PR.

Real child processes are killed after raw Inbox commit, after History
acceptance but before Inbox acknowledgement, and after History completion but
before caller acknowledgement. Fresh composition converges without another
Inbox row, History acceptance, or terminal. Corruption mutations cover raw
body digest, normalized evidence, canonical observation/key, PR binding,
bridge identity, acceptance pair, and terminal pair.

Bounded inspection limits the application to two tables, 10,000 workflows and
10,000 Inbox rows by default, 131,072 SQLite pages, 1 MiB raw bodies, 16 KiB
normalized values, and 8 KiB observations. Shared History is capped at 128 MiB
and one 4,096-record page per workflow, with 1 MiB reserved before a fresh
acceptance or completion write. The source completion does not advance the
newly enabled retained dashboard transition, so Dispatch pending count remains
zero.

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
