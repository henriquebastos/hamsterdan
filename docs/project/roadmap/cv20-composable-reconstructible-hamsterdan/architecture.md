# CV20 architecture

This document is the canonical architecture contract for CV20 implementation.
The ES-010 records explain how the design was reached; they are provenance, not
an additional specification. A Delivery Story does not consult exploration to
choose between alternatives. If this document and a historical exploration
statement differ, this document governs CV20.

## Design status

CV20 uses two design states:

- **Fixed** means the ownership, behavior, or boundary is accepted. A Delivery
  Story cannot change it without a new Navigator ruling and a corresponding CV20
  update.
- **DS review** means the behavior and owner are fixed, but a concrete class,
  function, parameter, field, or exception name is intentionally left for that
  tracer Delivery Story's API-strengthening Plan Checkpoint.

There is no implicit third state in the exploration. If implementation exposes
a missing choice, the Driver records it as a DS-review question instead of
recovering an old experimental possibility.

## Resulting system

CV20 builds a replacement in non-selectable `src/hamsterdan2` and `tests2`
namespaces. The current V5 application remains the sole runtime through
CV20.DS1–DS12. Replacement code uses fresh state roots and never reads,
converts, or writes current runtime state.

CV20.DS13 is a separately approved cutover. It stops the current service,
preserves old state only as bounded rollback custody, removes the current
implementation, renames the replacement to canonical `src/hamsterdan` and
canonical Python test paths, and switches packaging and deployment. The
finished system is simply Hamsterdan. `hamsterdan2` and V5 remain only in dated
historical records; neither remains an active identifier, package, schema,
selector, compatibility path, or operator concept.

```text
construction                                      cutover

current src/hamsterdan ── sole runtime ───────────────┐
                                                     ├─▶ canonical src/hamsterdan
src/hamsterdan2 ───── non-selectable replacement ─────┘

old state ─────────── current runtime only ──▶ bounded rollback custody
new state ─────────── replacement only ──────▶ canonical fresh state
```

## Fixed architecture decisions

| Concern | Fixed decision | Consequence |
|---|---|---|
| Delivery strategy | Build a parallel, non-selectable replacement and perform one final cutover | No story before DS13 changes the installed runtime |
| Delivery increment | DS1–DS12 are progressively deepened vertical tracer bullets | Component implementation is Technical Story work and cannot close Delivery without a bounded end-to-end outcome |
| API design | Semantics and ownership are contract-first; concrete signatures are call-site-proven in the first tracer that uses them | Producer, consumer, deterministic seam and observation surface are reviewed together; no speculative compatibility API |
| Compatibility | Do not migrate state, read old schemas, preserve old imports, or add artifact readers | A compatibility adapter is an architecture violation, not deferred work |
| Value ownership | Values stay with the package that defines their meaning | The target has no neutral `contracts` package |
| Workflow | `workflow` owns pure workflow meaning, including observations, facts, Activity work and terminals, and loop state | Workflow imports no runtime, provider, agent, host, clock, filesystem, HTTP, or database effect |
| Readiness | One readiness lifecycle owns one PR, Petrus execution, authority, custody, and typed effect adaptation | Readiness consumes workflow values directly and exposes bounded lifecycle results to host |
| Host | `host` is the only concrete application composition root | Host owns process resources and supervision but no workflow names, terminals, or Petrus runtime objects |
| GitHub | `github_app` owns normalized provider values, authentication, transport, route/webhook verification and persistence mechanisms, and provider-level lookup-first operations | Host owns durable inbox/route custody and resource lifetime; readiness classifies provider outcomes; provider code does not import readiness |
| Agents | `agents` owns credential-free requests, results, terminals, Pi adaptation, and workspace safety | Host owns route and secret/runtime custody; GitHub credentials never enter agent values or state |
| Authority | Readiness combines durable grant, fresh provider truth, and fresh host route/custody evidence at required effect cuts | No package substitutes one source for the complete authority claim |
| At-least-once effects | Stable operation identity plus lookup-first recovery controls ambiguity | One step makes at most one external mutation attempt; a later step reconciles before retry |
| Route revocation | Host reports fresh lifecycle evidence; readiness creates the workflow-declared blocked result | Host never decodes Activity work or fabricates a workflow terminal |
| Timers | Workflow owns timer commands and due facts; readiness owns durable timer custody | Command, acknowledgement, maturity claim, History acceptance, and delivered marks remain distinct cuts |
| Fairness | Host owns durable enqueue sequence, bounded selection leases, and tail requeue | One already-due PR cannot be starved by a repeatedly failing PR |
| Configured-repository recovery | DS9 exact-reads every known nonterminal subject; DS10 boundedly discovers unknown eligible open PRs; DS11 fairly schedules both turn classes | List summaries are hints, exact read precedes registration, and no pass claims an atomic repository snapshot |
| Bounded execution | Production and simulation expose claim/start, effect-observed/execute, and terminal-recorded/finish cuts | Process-local frames and returned values are never recovery authority |
| Simulation runtime | Hamsterdan owns one semantic-free synchronous `Timeline`; `CoroutineStepper` is internal | The runtime schedules one owner action and at most one leaf without understanding domain meaning |
| Simulation ownership | Workflow, readiness, GitHub, agents, and host each own their local simulation and checker | Root composition mounts those unchanged modules and owns only cross-module properties |
| Workflow subnet review | Each concern is independently constructible and inspectable from its exact production assembly before composition | Local Navigator acceptance stabilizes the subnet but cannot close its vertical tracer |
| Tracer evidence | Every tracer ships deterministic composition, local/cross checker evidence, named crash cuts, resource gauges and applicable real-seam correspondence | DST, observability and correspondence cannot be deferred to a later integration phase |
| Causal mutation | Real workflow `MutWork` creates the agent request; the exact delivered `CodingResult` reaches Git publication; `Pushed` returns to the original occurrence | Equality-by-reconstruction or co-mounting is insufficient evidence |
| Quality gate | The CV20 replacement gate defined in the ledger blocks the replacement tree from DS1 onward | The old tree keeps its current checks until deletion; the target receives no broad suppressions |
| Naming | `hamsterdan2` is construction-only; V5 names do not enter replacement APIs | DS13 removes both temporary generation labels from active truth |
| Initializers | Every package initializer is empty except for a policy docstring and explicit empty exports | There are no package facades or child re-exports |

## Package ownership

| Package | Owns | Must not own |
|---|---|---|
| `workflow` | workflow values, normalized observations, internal facts, Activity requests and terminals, nine concern loops, topology, manifest, token registry, pure folding and gate declarations | Engine lifecycle, History/Dispatch stores, external calls, clocks, credentials, persistence |
| `readiness` | one-PR application, Petrus runtime adaptation, authority, ingress/review/timer/instance custody, effect capabilities and classifications | concrete provider or agent construction, process scheduling, HTTP or CLI |
| `github_app` | provider models, App credentials, bounded transport/gateway, route/webhook mechanisms, provider-level lookup-first effects | durable process custody, readiness decisions, workflow values, agent execution, process supervision |
| `agents` | typed request/result/terminal protocol, Pi request adaptation, credential-free workspace operations | GitHub credentials, host route selection, workflow or readiness interpretation |
| `host` | concrete construction, provider/agent resource lifetime, instance catalog, runnable fairness, lifecycle evidence, inspection, API and service process | workflow names, Activity resolution, History decoding, Petrus execution |
| `operator` | human command behavior and atomic qualification setup | long-running service policy or workflow interpretation |
| `simulation` | logical time, deterministic scheduling, generic occurrence faults, process generations, budgets, artifacts and replay | owner commands, domain eligibility, retries, timers, authority or checker semantics |

## Observation and recovery language

Provider acquisition, workflow observation and readiness authority are separate
layers:

```text
acquisition
  PullRequestSnapshot + ObservationProvenance
    -> focused observation + ObservationKey
    -> IngressManifest + AdmissionGrant + ordered IngressEntry values
    -> HistoryAdmissionId in Petrus History
    -> workflow fold

recovery
  known subject -> bounded exact read -> common admission seam
  unknown subject -> bounded configured-repository pass -> exact read
                  -> idempotent registration/enqueue -> common admission seam
```

The minimal aggregates are:

- provider-owned immutable `PullRequestSnapshot` and bounded
  `ObservationProvenance`;
- readiness-owned immutable `IngressManifest`, one manifest-scoped
  `AdmissionGrant`, and ordered unique-key `IngressEntry` values;
- host-owned delivery custody, active route binding/generations and
  `RepositoryDiscoveryPass` custody; and
- Petrus History as the sole workflow-admission ledger.

`HeadSeen` is one focused workflow observation: subject, local incarnation and
exact head/base branch tips. Draft, lifecycle, mergeability and readiness policy
remain separate facts. The first local `HeadSeen` binds incarnation 1 without
claiming current authority. DS9 owns later lifecycle incarnations and
cut-specific `CurrentnessWitness`; DS2 never implements either behavior.

DS2 is webhook-only. Source-neutral means webhook and later exact-read
acquisitions use the same snapshot/provenance and admission contract, not that
DS2 performs provider reads. DS4 owns exact-read/list transport mechanics, DS9
owns known-subject convergence and currentness, DS10 owns unknown discovery, and
DS11 owns fair scheduling across known/discovery turns.

## Factories and reducers

Pure reducers perform deterministic state transitions over explicit values.
They never hide clocks, randomness, storage, processes, credentials or provider
calls. Intention-named factories compose explicit capabilities and may assemble
an owner around an injected reducer. A factory does not make an effectful owner
pure, and a reducer does not become a generic service layer.

For example, a readiness factory may bind durable ingress custody, History and
an injected observation reducer. The reducer can classify/fold an explicit
observation, but cannot fetch GitHub state or open storage behind the call.

Crossing a package boundary does not make a value neutral. For example,
`MutWork` remains workflow-owned when readiness executes it, and
`CodingResult` remains agent-owned when readiness publishes it.

## Tracer verticality contract

A Delivery Story is a tracer only when all of these are true:

1. it begins at an external, operator, or deterministic-simulation command;
2. it enters through the real `host` composition and every production owner
   relevant to the behavior;
3. it ends in a bounded visible posture, durable workflow request, or accepted
   external effect;
4. downstream code owned by Hamsterdan is not replaced by a permissive mock;
5. the same change adds owner-local behavioral evidence, root deterministic
   composition, checker sensitivity, named cuts, exact replay and resource
   bounds; and
6. a newly introduced external seam gains direct correspondence in that tracer
   or records an explicitly approved/unavailable qualification blocker.

For example, defining a provider observation value is component work. Taking
bounded raw webhook input through provider normalization, host custody,
readiness admission, the real workflow fold and detached posture is a tracer.
The provider value, custody store and fold may land as small green Technical
Stories, but the Delivery Story remains open until the vertical result exists.

The same rule applies to workflow subnets. A tracer may first expose one exact
production subnet through a Navigator-visible owner-local scenario runner that
steps it, renders its arcs and marking, injects typed boundary values, crashes
and reconstructs it, and replays its local checker evidence. This is an explicit
User Story and acceptance boundary inside the tracer, not a separate CV or a
substitute for the real producer/consumer path.

Each tracer introduces at most one major new effect family, custody state
machine, authority policy, concurrency dimension, or causal chain. If one
review would have to reason about several new chains simultaneously, split the
tracer rather than broadening its acceptance surface.

The first real call site also carries every fixed cross-cutting obligation it
needs: complete applicable authority, stable identity, recovery, bounds and
observation. Those obligations cannot be deferred as “integration,” but they
also cannot be used to hide a second new policy or causal chain in the tracer.

## Reviewed initial replacement source map

The package set and ownership boundaries are fixed. The module paths below are
the reviewed initial placement map, not an immutable 89-file prescription. The
owning tracer may merge or split modules during its API-strengthening Plan
Checkpoint when the deletion test demonstrates a clearer responsibility. It
must update this map and the replacement ledger before implementation.

New or split modules require the deletion test: the module must own a coherent
responsibility that would otherwise be duplicated or mixed into a different
owner. One command, value, fault, or class is not by itself a reason to create
a module. Merging files may not merge package ownership or create forbidden
imports.

```text
src/hamsterdan2/
  __init__.py
  workflow/
    __init__.py
    values.py
    observations.py
    facts.py
    activities.py
    net/
      __init__.py
      folding.py
      gating.py
      topology.py
      life.py
      ci.py
      escalation.py
      review.py
      mutation.py
      conversation.py
      dashboard.py
      reminders.py
      readiness.py
    simulation/
      __init__.py
      module.py
      checker.py
  readiness/
    __init__.py
    application.py
    runtime.py
    ports.py
    authority.py
    custody/
      __init__.py
      instance.py
      ingress.py
      review.py
      timers.py
    effects/
      __init__.py
      evidence.py
      agents.py
      publication.py
      rerun.py
      review.py
      mutation.py
      git.py
    simulation/
      __init__.py
      module.py
      checker.py
  github_app/
    __init__.py
    auth.py
    config.py
    effects.py
    gateway.py
    models.py
    routing.py
    transport.py
    webhooks.py
    simulation/
      __init__.py
      module.py
      checker.py
  agents/
    __init__.py
    protocol.py
    pi.py
    pi_workspace.py
    simulation/
      __init__.py
      module.py
      checker.py
  host/
    __init__.py
    __main__.py
    api.py
    clock.py
    composition.py
    service.py
    discovery.py
    instances.py
    inspection.py
    runnable.py
    qualification.py
    agents/
      __init__.py
      routing.py
      pi.py
    simulation/
      __init__.py
      module.py
      checker.py
  operator/
    __init__.py
    __main__.py
    qualification.py
  simulation/
    __init__.py
    runtime.py
    clock.py
    scheduling.py
    faults.py
    artifacts.py
    replay.py
    hamsterdan.py
```

`host.clock` is the only production module allowed to call wall-clock or sleep
APIs directly. It supplies clock behavior to all production consumers.
`simulation.clock` owns integer logical time and imports no wall-clock API.

## Import graph

```text
host service/API ───────────────▶ readiness lifecycle values
host composition ───────────────▶ readiness construction and effect adapters
        ├───────────────────────▶ github_app concrete implementations
        └───────────────────────▶ agents concrete implementations

readiness application/custody ──▶ readiness ports/authority/runtime ──▶ workflow
readiness GitHub effects ────────▶ github_app
readiness agent effects ─────────▶ agents
readiness runtime ───────────────▶ Petrus defining/runtime modules

operator.__main__ ───────────────▶ operator.qualification

owner.simulation ────────────────▶ owner production code
owner.simulation ────────────────▶ simulation mechanics
simulation.hamsterdan ───────────▶ five owner.simulation packages
```

Arrows mean imports. Production modules never import simulation. Owner-local
simulations import their production owner and shared mechanics; they do not
import sibling simulations. Root composition imports all five local simulation
packages but not their private stores.

### Forbidden edges and names

The architecture gate rejects:

1. any cycle in `hamsterdan2`;
2. child re-exports or imports through package objects;
3. workflow imports of readiness, host, GitHub, agents, simulation, runtime
   Engine/Dispatch/Worker, provider SDKs, HTTP, clocks, SQLite, or filesystem
   effects;
4. readiness core imports of concrete providers, concrete agents, host, or
   simulation;
5. a readiness effect module bridging more than one provider family, except
   `effects/mutation.py`, which coordinates injected coding and Git
   capabilities without importing their implementations;
6. GitHub or agents importing one another, workflow, readiness, host, or
   simulation;
7. GitHubKit or `httpx` outside `github_app`, FastAPI outside `host`, or Petrus
   Engine/Dispatch/Worker outside `readiness.runtime`;
8. construction of readiness plus concrete GitHub/agent implementations
   outside `host/composition.py`;
9. production imports of owner-local or root simulation;
10. `contracts`, `net_v5`, `host.v5`, `V5*`, topology selectors, compatibility
    facades, `ready.facts`, migration folds, or Petrus DST profile/artifact
    identities; and
11. `operator.qualification` importing another Hamsterdan package.

### Required edges

The gate also requires positive construction:

- `host/composition.py` imports readiness construction and concrete GitHub and
  agent constructors;
- `readiness/runtime.py` imports workflow `build_net`, `seed_marking`, explicit
  tokens, Activity manifest and gate wiring plus Petrus defining/runtime
  modules;
- `workflow.net.topology` imports every loop by defining module, aggregates all
  explicit tokens, and rejects missing or duplicate color names;
- every workflow loop introduced as a subnet can be mounted independently from
  the same production construction used by `workflow.net.topology`;
- the Activity manifest declares every gate once with request, terminal
  variants, lane, operation identity and blocked mapping;
- readiness application receives capabilities instead of importing their
  implementations;
- every local simulation mounts its real production owner; and
- `simulation.hamsterdan` mounts those same five modules and owns the causal
  cross-module checkers.

## Runtime shape

One host process supervises many independent one-PR readiness lifecycles:

```text
GitHub webhook
  -> GitHub durable inbox
  -> host subject custody and fair runnable claim
  -> readiness admission for exactly one PR
  -> pure workflow observation/fold/action
  -> typed Activity request
  -> readiness effect capability
  -> GitHub or agent implementation
  -> typed Activity terminal
  -> original workflow occurrence
  -> detached readiness posture
  -> host acknowledgement/requeue
```

The host can observe only lifecycle evidence, detached readiness posture,
settled agent-operation identities, and bounded inspection. It cannot inspect
the workflow marking or decide which terminal an Activity receives.

One readiness call returns after one named cut. Convenience drains are finite
loops over the same calls; there is no production-only hidden drain.

## Durable authority and recovery

Durable truth stays with the component that can prove it:

| Truth | Durable owner | Recovery rule |
|---|---|---|
| Provider request/effect acceptance | GitHub provider operation store or external provider truth | complete bounded lookup before another mutation attempt |
| Agent submission, execution terminal and receiver delivery | agent lifecycle stores | lookup retained execution/result before start or delivery retry |
| Workflow request, occurrence and terminal projection | Petrus History/Dispatch under readiness custody | page-bounded replay and one-occurrence repair |
| Ingress manifest and readiness grant | readiness ingress custody | exact duplicate returns retained/already accepted posture |
| Review request/attempt | readiness review custody | rebuild exact request and attempt; never infer from agent logs |
| Timer command, acknowledgement, maturity and delivery marks | readiness timer custody | replay the oldest exact pending cut before new timer work |
| Subject/root/provider-route registration | host instance catalog | inspect the registered root; never discover by scanning History files |
| Runnable fairness and selection | host runnable store | expired leases requeue under durable sequence |
| Agent route composition | host route store | readiness inspection reports live/settled operation identities |

Coroutines, open files, client objects, exception instances, returned values,
in-memory queues, and simulation frames are process-local. Losing them may
force lookup-first work, but may not change the resulting operation identity or
authorize a duplicate effect.

## Simulation shape

The shared runtime understands only strict commands and observations,
`ActionRef(module, name, identity, eligible_at_us)`, logical time, deterministic
choice streams, generic occurrence faults, process generations, one-leaf
execution, resource budgets, artifacts, and replay.

Each owner-local module supplies strict semantic commands, observations,
eligibility, faults, retained state, resource gauges and its local checker.
Root composition supplies concrete adapters and checks only relationships
between owners.

Workflow evidence has three nested scales:

1. a subnet-local runner mounts one exact production concern and checks its
   internal typed ports, marking, Activities, reconstruction and bounds;
2. the workflow-owner simulation composes accepted concern modules and checks
   workflow-owned relationships; and
3. root composition mounts the unchanged owner modules and checks only the
   producer, consumer, custody and effect edges between owners.

No scale carries a shadow reducer or copied workflow rule. A typed outcome may
be supplied at the subnet boundary for local execution, while provider
correspondence remains owned by the provider tracer and root composition.

This shape exists from the first tracer and thickens with production behavior.
There is no late simulation-composition phase. Each tracer adds the local
vocabulary and checker evidence for its new owner behavior, mounts those same
production owners in root composition, records exact operations/cuts/resource
peaks, and replays from a fresh object graph.

The required cross-module mutation proof is:

```text
workflow History declares exact MutWork and occurrence
  -> composition hands off that exact work
  -> agents retain and deliver exact CodingResult
  -> readiness publication consumes that result
  -> publication digest/head changes when only that result changes
  -> Pushed closes the original workflow occurrence and operation
```

Changing only the composition handoff or delivered result must leave all local
checkers green and make the relevant cross checker fail. A composed scenario
that merely creates equal values independently does not satisfy this contract.

## Naming and vocabulary

| Term | Meaning in CV20 |
|---|---|
| Hamsterdan | The product and, after DS13, the only canonical implementation |
| `hamsterdan2` | Temporary source namespace used only during DS1–DS12 construction |
| V5 | The current implementation that remains operational until DS13 and is then removed |
| workflow | Pure Petri Net definition and workflow-owned typed values |
| readiness | One-PR execution, authority, custody and effect adaptation |
| host | Trusted process composition and multi-PR supervision |
| operation | Stable logical identity used to reconcile at-least-once external work |
| occurrence | Engine-assigned identity of one workflow Activity request |
| correlation/idempotency | Identity carried between Activity request, effect operation and terminal admission |
| posture | Detached bounded hint returned to host; never canonical workflow state |
| cut | One externally visible bounded progress boundary |
| local checker | Independent owner-specific derivation from detached evidence |
| cross checker | Composition-owned derivation that compares facts from more than one owner |

Names and signatures whose status is **DS review** are listed in
[the API contract](api-contracts.md). A DS may improve those names while keeping
the fixed vocabulary and ownership above. Any proposed rename of a fixed term
must update this document before implementation.

## Provenance

The accepted evidence is retained in
[ES-010](../../exploration/es10-composable-hamsterdan-architecture/index.md),
especially its
[S12 synthesis](../../exploration/es10-composable-hamsterdan-architecture/experiments/12-enforcement-delivery.md).
Those records contain experiments, rejected alternatives and correspondence
limits. They are useful when auditing why the contract exists, but are not
required to implement or review a CV20 Delivery Story.
