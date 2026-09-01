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

DS1 and the delivered DS2 tasks through unfinished identified History
acceptance admit this source shape:

```text
src/hamsterdan2/
  github_app/
    models.py
    webhooks.py
    simulation/
      webhooks.py
  workflow/
    values.py
    observations.py
  readiness/
    ingress.py
    ingress_values.py
    projection.py
    root.py
    runtime.py
    workflow_bridge.py
    simulation/
      ingress.py
      lifecycle.py
  host/
    api.py
    application.py
    catalog.py
    composition.py
    delivery.py
    values.py
  simulation/
    hamsterdan.py
    process.py
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

DS2 task 2 fixes this boundary more narrowly. `github_app` verifies the exact
raw bytes before parsing and projects a bounded pull-request snapshot plus
webhook provenance. Host then binds the envelope to one configured active route
and acquires `(ProviderRouteId, DeliveryId)` in SQLite. One canonical normalized
content value is retained per acquisition identity. Identical redelivery is an
exact duplicate; changed normalized content permanently quarantines that one
acquisition without overwriting its original evidence. The request receives
HTTP 202 only after the retained, duplicate, or quarantined disposition is
durable. Invalid transport, signature, envelope, or route evidence is refused
without persistence.

The normalized snapshot contains only its immutable PR subject, exact head and
base branch tips, lifecycle state, draft and merged flags, tri-state
mergeability, and bounded provider update time. Webhook event, action, and
delivery identity are provenance. Raw body, signature, secret, arbitrary
headers, SDK values, branch policy, base currentness, provider currency, and
workflow decisions are neither retained nor returned.

DS2 task 3 adds a separate host-composed authority turn over reconstructed
delivery custody. Readiness projects the retained snapshot into the first
source-neutral Head observation for local incarnation 1, canonicalizes its
complete focused semantics, derives `ObservationKey` v1, and atomically retains
an immutable manifest, exact manifest-scoped grant, ordered entry, and closed
classification. Provider time, route, delivery/custody identity, provenance,
and policy revision stay outside semantic equality. A quarantined acquisition
gets an empty manifest and grant with `acquisition_collision`; identical
semantics from another acquisition are `corroborating`; key/bytes disagreement
is fatal `semantic_collision`; changed Head tips are `incomparable`; and
same-tip contradictions are non-retryable `conflicting` failure data.

Readiness assigns each first-retained manifest an immutable transaction
sequence so restart reconstruction can replay prior staged evidence and
recompute every classification exactly. The sequence orders classification
context only. It does not make delivery order, custody generation, provider
time, or webhook receipt order into semantic Head ordering.

Host staging linearizes at a final bounded delivery-custody read after strict
reconstruction of the initially fetched row. A collision completed before that
final read, including one concurrent with reconstruction, stages quarantine; a
collision after that read is later and cannot rewrite the original acquisition
being staged. Readiness obtains its staging-turn lock before host selection, so
another staging turn cannot overtake the selected acquisition before manifest
retention. HTTP uses no readiness lock and neither invokes nor waits for
readiness staging.
Reconstruction also limits every manifest, entry, and decision query before
model or BLOB decoding and rejects an existing database above its effective
SQLite page ceiling. Host selection likewise rejects delivery custody above its
configured row or effective page ceiling before readiness can mutate, and host
composition forwards that configured row ceiling to both HTTP custody and
staging reconstruction. Singleton acquisition and grant reads detect duplicate
authority even when an existing SQLite schema lacks the declared uniqueness
constraints.

The task-3 turn returns only detached staging posture and finite resource
counts. It neither calls the bridge nor opens readiness runtime, Petrus History,
Dispatch, or the retained Net. The existing webhook HTTP path still constructs
only GitHub normalization and host delivery custody, so acknowledgement neither
invokes nor waits for staging. Fresh-process reconstruction after staging
commit reoffers the exact acquisition without creating another manifest,
grant, entry, or decision.

DS2 task 4 adds a later host authority operation selected only by the task-2
`(ProviderRouteId, DeliveryId)` identity. Host reconstructs the task-3 staging
authority, derives its subject, requires the existing subject/root registration,
requires the catalog row to equal the instance/root deterministically derived
from that subject, and requires exactly one matching catalog row. Readiness
likewise requires exactly one singleton root-binding row before Engine load.
Both reads project type-valid, byte-bounded identities before strict value
construction; exact-one malformed rows therefore produce fixed bounded
corruption diagnostics rather than raw validation failures or stored content.
Duplicate, conflicting, or out-of-domain rows in constraint-free malformed
schemas fail closed. Host holds the existing catalog authority transaction
while readiness owns the one canonical Engine writer.
Even a corrupted redirect to a different internally valid opened root therefore
fails before History. The operation never auto-registers a subject, never
accepts caller-supplied staging, subject, grant, entry, policy, token, source,
identity, or occurrence, and remains absent from the HTTP call tree.

Readiness reconstructs the complete manifest, grant, entry, canonical
observation, acquisition, decision, policy, subject, and local incarnation
before opening History. Only the original durable `novel` posture with one
exact entry can cross the bridge. Every other closed task-3 classification
returns bounded non-admission posture, while malformed custody or History fails
loud without manufacturing success. The host-configured manifest ceiling is
preserved across both the outer subject selection and the inner authoritative
read, so an intervening append cannot enter through a wider default. Neither
ingress nor host storage records an accepted pointer: Petrus History remains the
only workflow-admission ledger.

The sole bridge maps the first admitted family, `HeadObservation` to retained
`HeadSeen` at source `on_head`, under bridge identity
`workflow-bridge/head-seen-history-acceptance@2`. It accepts only local
incarnation 1, lifecycle `open`, `draft=False`, and `merged=False`. It carries
the exact head and base SHAs, maps mergeability true only when the observation
is explicitly true, takes policy only from the reconstructed manifest, and
sets `strict_base=True` and `base_current=False`. Closed, merged, or draft
snapshots fail before History; no `DraftSeen`, `ReadySeen`, or `CloseSeen` is
fabricated.

The versioned delivery identity hashes bridge identity plus exact manifest ID,
grant ID and digest, entry order, and observation key. Because those authority
identifiers are reconstructed from canonical source-neutral staging, the
identity is stable across process loss and binds the complete staged semantics
without using timestamps, receipt order, mutable configuration, or retained
token rendering alone. Readiness calls public `Engine.accept_delivery` once,
without scope. A first offer commits adjacent `ExternalEventDelivered` and
`FiringBegun`; an exact unfinished reoffer reconstructs the same occurrence
without another append. The detached `HistoryAcceptancePosture` exposes only
strict new values and is never persisted as another authority record.

History load is finite before Petrus materialization: the canonical SQLite
database plus WAL and shared-memory companions may occupy at most 2 MiB. A
public `Engine.history_page` inspection then caps the accepted frontier at
4,096 records. The bounded page reserves two records only when the offered
delivery identity has no durable acceptance fact; an exact unfinished or ended
reoffer at the ceiling reserves none because it appends nothing. The same
page translates an ended prior acknowledgement; no `Engine.records`
full-copy inspection remains. Malformed Engine load/replay is translated to a
fixed readiness-owned corruption error with no stored payload in its exception
chain, including recursive JSON decode failures; changed-content collision
after a valid load remains distinct. The
public acceptance call is independently pinned to one source/token/identity
offer with no scope, and prior/scoped result branches have explicit bounded
postures and correlation checks. Owner and root observations independently
count zero unfinished firings before acceptance and exactly one afterward, and
budget that neutral count as `retained.readiness.in_flight_occurrences`.

Task 4 deliberately leaves the occurrence unfinished. It creates no
`FiringCompleted`, `TokensProduced`, retained-Net fold, host completion,
Dispatch task, Worker turn, provider read or effect, agent work, currentness
witness, lifecycle successor, or second admission ledger. Task 5 must
reconstruct staging, load the Engine, exact-reoffer to recover the same
`AcceptedDelivery` carrier, and call `Engine.complete_delivery` for only that
occurrence before it may project the retained fold or complete host custody.

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

The delivered task-3 staging cut stops at the manifest-scoped grant. Task 4
now converts that staged focused observation through the sole bridge and offers
identified delivery to Petrus History. Its unfinished acceptance is a third
observable cut after HTTP custody and source-neutral staging. Task 5 still owns
the fourth cut, retained-Net fold, plus later host completion; task 4 does not
collapse those facts.

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
| exact observation delivery acceptance and unfinished occurrence | Impetus History through public `Engine.accept_delivery` |
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

Task 4 owner-local and cumulative root Worlds add a separate strict History-
acceptance command after staging. Their neutral observations distinguish the
source, token color and payload, delivery identity, occurrence, adjacent record
order, accepted status, and still-unfolded status. Independent checker
mutations cover bridge identity, manifest/grant/key/order authority, every
mapped token field, identity, occurrence, record order, and accepted-versus-
folded posture. A real child process is killed after the two acceptance facts
commit but before caller acknowledgement; a fresh host/readiness graph exact-
reoffers the immutable staging authority and observes the same occurrence with
no additional History record. The root observation mounts the unchanged owner-
local staging posture, and accepted correspondence requires that posture to be
the exact original `novel` authority. File/byte and host-catalog observations
stop at ceiling plus one rather than materializing an oversized state; History
is inspected through one bounded public page. Before any public Engine load,
readiness reserves 128 KiB for SQLite WAL/shared-memory establishment; before a
new identity reaches `accept_delivery`, it remeasures the aggregate database,
WAL, and shared-memory footprint and reserves 1 MiB for the finite two-record
transaction. An exact durable reoffer reserves no append bytes, but still
requires load headroom. Root/catalog SQL projections also reject malformed
singleton values and duplicate root authority with fixed diagnostics before
constructing detached values. Strict ingress and History reconstruction errors
discard decoder exception chains so malformed retained acquisition,
observation, or History content cannot enter diagnostics. The owner checker
identity also binds the independently decoded canonical `HeadObservation`, so
changing the bridge-consumed observation while retaining its key/bytes cannot
pass.

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
