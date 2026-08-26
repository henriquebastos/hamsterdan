# Experiment 5 — Readiness execution tree

Session S5. Durable inputs: the ES-010 index and the accepted S4 record,
[`04-ports-adapters.md`](04-ports-adapters.md). Source inspected at commit
`6df25ea`: every module under `src/hamsterdan/host/v5`, plus
`host/git_publish.py`, `host/pi_workspace.py`, `host/binding.py`, and
`host/protocol.py`. Immediate consumers in `host/service.py`,
`host/agenticus.py`, `host/__main__.py`, `agents/pi.py`, and `host/pi_a2.py`
were inspected only where needed to establish ownership.

Method: reclassify each current responsibility under the accepted
workflow/readiness/host language, apply the deletion test to the proposed
`application`, `runtime`, `authority`, `custody`, and `effects` groups, and
trace construction, one-PR execution, effect recovery, and reconstruction. S4's
eight capability groups and operation semantics are inputs, not questions
reopened here.

## Verdict

Most of `host/v5` is one deep readiness execution package, but neither the
directory nor `application.py` is an honest module boundary today:

- `application.py` combines one-PR orchestration, concrete GitHub and agent
  construction, conversation interpretation, Petrus wiring, timer driving,
  host scheduling hooks, and inactive-route policy;
- `ingress.py` combines provider evidence projection, readiness manifest and
  grant custody, and direct queries against the host-owned webhook inbox;
- `review.py` combines review Activity orchestration with durable request
  custody; and
- `binding.py` combines one-instance subject binding with process-wide legacy
  topology preflight.

The target readiness package is:

```text
readiness/
  application.py
  runtime.py
  ports.py
  authority.py
  custody/
    instance.py
    ingress.py
    review.py
    timers.py
  effects/
    evidence.py
    agents.py
    publication.py
    rerun.py
    review.py
    mutation.py
    git.py
  simulation/                 # Exp 10 owner; no production content from S5
```

Package initializers are non-facades. This tree adds no interface per noun:
`ports.py` holds the accepted S4 capability seam together; the four custody
modules have different durable reconstruction rules; and the effect split
follows different operation identities, authority cuts, and recovery
semantics. The application receives the S4 capabilities through the concrete
injection form eventually ruled by the engineering style contract. S5 does not turn the capability
signatures into a recommendation for Python `Protocol` classes.

The target one-PR application can be constructed with readiness-owned inputs
and exercised without HTTP ingress, a provider SDK object, multi-instance host
supervision, or a process-wide scheduler. Production still uses concrete
effects constructed by the host; deterministic readiness simulation supplies
the same S4 capabilities directly.

## Current module reclassification

| Current module | Current responsibilities | Target disposition |
|---|---|---|
| `host/v5/__init__.py` | Empty package marker | Delete with `host/v5`; target initializers remain empty and do not re-export implementation |
| `host/v5/application.py` | Constructs every provider/agent effect, opens all stores and runtime, admits observations, classifies conversation, drives settlement, exposes host Worker hooks and detached inspection | Split: one-PR sequencing stays in `readiness/application.py`; concrete construction moves to host composition; conversation execution moves to `effects/agents.py`; Petrus work stays in `runtime.py`; stores move under `custody`; host scheduling methods are replaced by S6's lifecycle seam |
| `host/v5/claim.py` | Complete fresh authority value plus callable alias | `AuthorityClaim` remains a readiness-owned value in `ports.py`; fresh claim composition moves to `authority.py`; the topology-named callable alias dies and concrete injection follows the engineering style contract |
| `host/v5/gates.py` | Five comment publication Activities, rendering, lookup-first classification, authority asymmetry | `readiness/effects/publication.py`; `UnstagedCustodyError` becomes a readiness authority/custody boundary outcome rather than a GitHub exception subclass |
| `host/v5/ingress.py` | GitHub evidence projection, immutable readiness ingress manifests, durable readiness grants, reconciliation manifests, and queries of the host webhook `inbox` | Split: provider projection moves to `effects/evidence.py`; readiness manifests/grants move to `custody/ingress.py`; fresh grant/provider composition moves to `authority.py`; direct webhook-table access is removed and S6 supplies custody progress through the lifecycle seam |
| `host/v5/mutation.py` | Mutation Activity orchestration over agent coding plus Git publication | `readiness/effects/mutation.py`; it coordinates independently injected agent coding and Git publication adapters without constructing either |
| `host/v5/rerun.py` | One rerun Activity with final pre-request Actions evidence cut | `readiness/effects/rerun.py`; remains separate from comment publication as ruled in S4 |
| `host/v5/review.py` | Review request composition, durable request store, authority-cancellable agent execution, typed terminal classification | Split: orchestration moves to `effects/review.py`; exact request storage moves to `custody/review.py`; the agent call crosses `effects/agents.py` |
| `host/v5/runtime.py` | Petrus Net/Engine/History adaptation, inline and durable Dispatch, per-instance Worker, ingress folds, terminal collection, timer/wake History validation | `readiness/runtime.py`; consume the workflow-owned Activity manifest rather than import topology gate registries or hard-code current Activity names |
| `host/v5/timers.py` | Durable timer command ledger, injected clock, reconstruction from History, acknowledgements, maturity claiming/delivery | `readiness/custody/timers.py`; expose integer-microsecond deadlines and retain S4 ordering/reconstruction semantics |
| `host/git_publish.py` | Deep Git publication adapter: patch admission, object creation, operation trailers, complete first-parent lookup, exact ref CAS | `readiness/effects/git.py`; no longer host-owned merely because credentials are used at execution |
| `host/pi_workspace.py` | Credential-free Pi workspace capture, archive validation, canonical patch reconstruction, private temporary workspace cleanup | Not readiness. Move to `agents/pi_workspace.py`, beside the agent execution adapter it implements; host still constructs it and owns the Pi runtime and secrets |
| `host/binding.py` | Durable PR-root subject binding, retired-topology compatibility, whole-state preflight | Split: current subject/root binding becomes `readiness/custody/instance.py`; all `production`/`v5` compatibility and migration paths die; process-wide discovery/preflight belongs to S6 and must not decode workflow internals |
| `host/protocol.py` | Supposedly topology-neutral interface that imports GitHub observation, provider conversation, Petrus Activity types, and publication-specific Worker controls | Delete. It is a union of current host calls, not a stable abstraction. S6 defines the narrow host-to-readiness lifecycle seam over readiness-owned values; Petrus resolver types remain inside readiness runtime |

### `pi_workspace.py` is outside readiness

The workspace receiver has no workflow, authority-grant, or Activity terminal
meaning. It implements the credential-free workspace boundary already declared
by `agents/pi.py`, and `host/__main__.py` only constructs it beside the Pi
runtime. Moving it into readiness would make readiness know Pi runtime policy
and workspace archives. Keeping it in `host` would keep an agent implementation
under process supervision. `agents/pi_workspace.py` is the honest owner; host
retains runtime construction, direct-key custody, route selection, and resource
shutdown.

Its current private import of `_safe_path` from `host/git_publish.py` does not
justify a neutral utility. Agent workspace paths have the stricter denied-root
policy; the agent module should own that validation. Git publication keeps its
own patch-admission path rule.

## Target ownership and dependency graph

```text
host composition
  -> readiness.application construction seam
  -> readiness.effects constructors
  -> github_app production implementations
  -> agents production implementations

readiness.application
  -> readiness.ports
  -> readiness.authority
  -> readiness.custody
  -> readiness.runtime
  -> workflow values and public build seam

readiness.authority
  -> readiness.ports
  -> readiness.custody.ingress
  -> injected fresh provider/custody evidence

readiness.runtime
  -> workflow public build and Activity manifest
  -> Petrus defining modules

readiness.effects.*
  -> readiness.ports
  -> workflow Activity work and terminal values
  -> github_app or agents only where adapted

readiness.custody.*
  -> readiness-owned values
  -> workflow boundary values where reconstructed
  -/> github_app, agents, host, HTTP, or provider SDK types
```

`application.py` does not import concrete provider or agent packages.
`effects` does not import the application or runtime. `runtime.py` does not
import concrete effects; it receives Activity implementations and consumes the
workflow-owned manifest. Custody does not discover host tables. The host may
import effect constructors because it is the composition root, but the effect
objects it supplies satisfy readiness-owned capabilities.

## Grouping and deletion test

### `application.py` earns the one-PR sequencing boundary

The application owns the order between readiness-owned custody and the
workflow runtime:

1. recover or project one exact ingress batch;
2. preview the durable grant;
3. classify an admitted conversation against that preview when present;
4. atomically retain the manifest and grant before workflow delivery;
5. deliver and fold each frozen observation in canonical order;
6. collect workflow terminals;
7. apply timer commands, acknowledgements, maturities, and deferred wakes; and
8. report bounded progress or the next external wait.

Deleting this module would force host or simulation to reproduce that ordering,
including the host-before-workflow authority cut. It therefore earns a deep
module. It does not earn the right to construct GitHub clients, agent runners,
effect adapters, Dispatch storage, or a process scheduler.

The current `settle()` hides two nested 500-step drains. S5 preserves the
responsibility, not that interface. S7 defines the bounded application step and
expresses drains as bounded loops over it.

### `runtime.py` earns the Petrus adaptation boundary

The runtime is the only readiness module that needs `Engine`, `History`, Net
paths, Dispatch, Worker, and Petrus selection policy. It owns:

- building or loading one workflow instance;
- translating workflow Activity declarations and implementations to Petrus;
- one identified external delivery and one lifecycle fold;
- collecting Activity terminals and reopening canonical History after an
  uncertain append;
- projecting accepted timer and deferred-wake facts from History; and
- bounded execution of an eligible Activity attempt.

Deleting it would spread Petrus records, tokens, occurrences, and reopening
rules into application, custody, effects, and simulation. It stays whole. The
current hard-coded `_INGRESS_FOLDS`, Activity-name sets, and imports from
`net_v5.topology` are V5 coupling, not reasons to split the module. The
replacement runtime derives declarations and durability from the ruled
workflow manifest and its public seam.

### `ports.py` earns one readable readiness capability contract

S4 ruled eight capability groups with distinct method sets and value ownership.
Keeping them together lets a reader see the complete construction boundary and
prevents one-file-per-port fragmentation. Deleting `ports.py` would either make
the application import provider/agent implementations or make each effect
invent a local request vocabulary. It retains only readiness-owned values and
workflow Activity values; it is not a neutral `contracts` package.

### `authority.py` earns the composition of three independent facts

A current authority claim is valid only when:

```text
durable readiness grant
  + fresh provider phase/head/base/policy evidence
  + no host-custodied same-PR authority movement awaiting readiness admission
  = executable AuthorityClaim
```

No one input can replace the composition. Deleting `authority.py` would repeat
the full comparison in findings, rerun, review, mutation, and announcement, or
push readiness grant interpretation into the host/provider adapter. It stays a
root readiness module. It returns readiness-owned outcomes and does not subclass
`GitHubBoundaryError`.

### The four custody modules do not merge

- `custody/instance.py` prevents a state root from being opened for a different
  PR subject. It has no retired-topology reader.
- `custody/ingress.py` atomically binds immutable source manifests to the
  readiness grant and reconstructs their lineage.
- `custody/review.py` freezes one exact credential-free review request by
  operation and attempt.
- `custody/timers.py` is an ordered command and maturity ledger reconstructed
  against accepted workflow History.

They share SQLite as a mechanism but not identity, reconstruction, ordering, or
failure invariants. One generic store would expose tables and codecs rather
than hide them. Merging them into `application.py` would make construction and
recovery unreadable. Each therefore survives the deletion test.

The current ingress store's direct `inbox` queries fail the ownership test.
Webhook acceptance, retry, terminal disposal, and row ordering remain host
custody. Readiness retains only manifests/grants and the custody progress
accepted through the host-to-readiness lifecycle seam. S6 must define that
seam; S5 does not add host webhook methods to the S4 effect-port matrix.

### Effect modules follow recovery semantics, not external products

- `evidence.py` projects provider truth into workflow observations. It is the
  only effect that knows provider snapshot shapes during normalization.
- `agents.py` isolates the credential-free agent protocol and route adapter for
  conversation, review, and coding. Review and mutation retain their distinct
  readiness orchestration.
- `publication.py` keeps the five comment-ledger Activities together behind
  five typed operations, preserving S4's deliberate authority asymmetry.
- `rerun.py` remains separate because its final Actions inventory read is the
  pre-effect evidence cut and every unproven issue is a fault.
- `review.py` owns request recovery, authority cancellation, and review terminal
  classification, but not durable request storage.
- `mutation.py` owns one workflow Activity over coding and publication, but not
  either adapter's implementation.
- `git.py` owns patch admission, Git object proof, operation trailers,
  complete-history reconciliation, and exact ref CAS.

Deleting `agents.py` would leak sibling `agents` request/result and routing
objects into three readiness orchestrators. Deleting `git.py` would prevent the
accepted response-lost scenario from replacing Git independently of coding.
Merging rerun into publication would again expose the shared comment transport
as the domain interface. The S4 grouping therefore survives source placement.

## False topology-neutral abstractions

### `host.protocol.ReadinessApplication`

The current protocol is not topology-neutral. Its method set exposes the
current implementation's plumbing:

- provider-owned `Observation` and `AdmittedConversation` inputs;
- direct Petrus `ActivityDefinition` lookup;
- durable-publication Worker pumping;
- unresolved-publication inspection; and
- an untyped detached-state dictionary.

It should be deleted, not renamed. The replacement application's public seam
belongs to readiness and uses readiness-owned admission, progress, inspection,
and closure values. S6 fixes the exact lifecycle method set; S7 fixes progress
stepping.

### `DurableActivityResolver` and host Activity lookup

The current host knows `DURABLE_PUBLICATION_GATES`, resolves an Activity name
back through the application, wraps it in an instance lock, synthesizes
inactive terminals, and wakes the runnable index. This is a second composition
path around the application's original Activity definitions.

The target readiness runtime owns its Activity implementations, Dispatch, and
per-instance Worker. Host supervision requests one bounded readiness progress
step and records the returned disposition; it does not resolve workflow
Activity names. Route revocation enters through host/readiness lifecycle and
authority composition, not a static call to
`PrReadinessV5Application.inactive_activity_result()`.

The resolver alias, `activity(name)`, `inactive_activity_result()`,
`run_durable_activities()`, `stop_durable_activities()`, and
`has_unresolved_publication()` therefore do not survive as public host
interfaces. S7 may retain equivalent internal runtime queries where one bounded
step needs them.

### V5 binding and schema compatibility

`TopologyIdentity`, legacy binding reads, migration columns, V5 table names,
topology fields, and preflight rejection of former state exist only because the
current tree once supported alternatives. ES-010 explicitly has no
compatibility obligation. The replacement retains a single subject binding and
fresh schemas, not a generalized topology abstraction.

## Construction route

Production construction becomes explicit without letting readiness construct
providers:

```text
host selects installation + repository + PR
  -> host obtains operation-scoped GitHub authority and agent route
  -> host constructs readiness effect adapters for the S4 capabilities
  -> host supplies subject identity, state roots, clock, workflow settings,
     effect adapters, and provider-side authority/custody evidence
  -> readiness application opens instance, ingress, review, timer, and History custody
  -> readiness authority binds durable grant to fresh supplied evidence
  -> readiness runtime wires supplied Activity implementations to workflow MANIFEST
  -> host retains only the resulting readiness lifecycle object
```

The application constructor receives no GitHubKit client, HTTP object,
installation token, Pi runtime, process-wide route registry, host webhook store,
or simulation truth. Concrete adapters may hold GitHub and agent collaborators;
the application sees only the accepted readiness capabilities.

## One-PR execution reading route

The shortest target route for one custodied provider observation is:

```text
host webhook custody selects one PR and mechanically projects source metadata
  -> readiness.application admits one readiness-owned ingress command
  -> effects.evidence projects fresh provider truth to workflow observations
  -> custody.ingress recovers an existing manifest or previews the next grant
  -> effects.agents classifies an optional conversation against that preview
  -> custody.ingress atomically stores exact manifest + resulting grant
  -> runtime delivers and folds each observation through workflow
  -> runtime reaches a typed Activity request from workflow MANIFEST
  -> the injected readiness effect returns its declared typed terminal
  -> runtime records and folds the terminal
  -> application advances timer/deferred custody and reports bounded progress
```

Reconstruction follows the same modules:

```text
application opens bound PR root
  -> runtime reloads canonical History
  -> ingress custody validates manifest/grant lineage
  -> review custody reopens exact outstanding requests
  -> timer custody rebuilds or validates against accepted History facts
  -> effect adapters reconcile stable operations lookup-first
  -> bounded progress resumes from retained state, never Python object continuity
```

No step requires HTTP ingress or another PR instance. A deterministic readiness
simulation can provide source commands, S4 capability implementations, logical
time, and storage faults directly around these same modules.

## Preserved correctness obligations

### Authority and credential isolation

- Every fenced effect compares the durable readiness grant, fresh provider
  evidence, and host custody barrier immediately before execution.
- Replies, reminders, and dashboard retain the S4 authority asymmetry; S5 does
  not silently add the full fence.
- Provider credentials remain inside host-constructed GitHub adapters. Agent
  request values and workspaces remain credential-free.
- The application, workflow, custody records, and port values contain no token,
  SDK client, HTTP response, or Pi runtime object.

### At-least-once effects and recovery

- Stable operation identity is spent at the external effect.
- Lookup precedes mutable authority reads where the S4 operation matrix requires
  it.
- Accepted-but-response-lost Git publication remains `FaultM` until complete
  first-parent lookup proves the one matching commit.
- Comment identity collision and Git operation/digest collision fail closed.
- Review request and timer command custody return the exact prior value for an
  existing identity.

### Independent progress and reconstruction

- One readiness application owns one PR History and one set of reconstructible
  custody stores.
- Process scheduling stays host-owned; one application's Worker and Petrus
  runtime stay readiness-owned.
- Host invokes bounded progress and cannot drain one instance indefinitely.
  The exact step and fairness contracts remain S7 scope.
- All recovery derives from History, manifests, operation ledgers, request
  custody, and timer custody rather than object or generator continuity.

## R2 tensions and handoff to S6

1. **The two accepted S4 tensions remain open.** Review provider-evidence
   failure still lacks a typed workflow terminal, and reply/reminder/dashboard
   intentionally remain less fenced than findings and readiness announcement.
   S5 preserves both rather than choosing new behavior.
2. **Webhook custody needs a lifecycle seam, not shared tables.** Current
   readiness code queries the host `inbox` for unstaged and terminal rows.
   The target removes that database coupling. S6 must define how host reports
   same-PR pending/terminal custody and route revocation to one readiness
   application. This is process lifecycle input, not a ninth external-effect
   capability.
3. **Inactive publication policy currently bypasses readiness.** Host knows
   three workflow Activity names and fabricates blocked terminals after route
   revocation. S6 must place revocation in the lifecycle/authority seam so host
   no longer decodes or manufactures workflow terminals. The exact retained
   behavior should be ruled at R2.
4. **Agent route repair currently parses workflow History from host.**
   `host/agenticus.py` knows transition names and mutation terminal variants,
   while `runtime.py` separately scans the same History to settle routes. The
   target binding remains readiness-owned; S6 must keep process-wide agent
   route custody without making host decode workflow internals. S7 can define
   the bounded terminal-settlement cut.
5. **Process-wide state discovery and `publication_qualification` remain S6.**
   The replacement needs no old-topology preflight. S6 decides the retained
   host discovery/inspection owner and the already-deferred qualification-fault
   placement without moving either into readiness.

## Exit assessment

Every source module named by experiment 5 has one target owner or an explicit
outside-readiness disposition. The proposed application, runtime, ports,
authority, custody, and effects groups each survive the deletion test. Provider
construction, HTTP/webhook custody, Pi runtime custody, multi-instance
scheduling, and shutdown remain outside readiness; Petrus adaptation,
one-PR durable execution, authority composition, timers, and typed effect
orchestration remain inside.

The construction and reading routes show that one readiness application can run
through S4's typed capabilities without HTTP ingress or multi-instance host
supervision while preserving authority fencing, credential isolation,
at-least-once effects, stable identity, and lookup-first recovery. No executable
spike was needed: S5 classifies existing executed production and deterministic
routes; bounded stepping and standalone simulation proof belong to S7 and S10.

Experiment 5 therefore meets its exit criterion. S6 can narrow host from this
tree. Checkpoint R2 remains unruled and owns the five tensions above.
