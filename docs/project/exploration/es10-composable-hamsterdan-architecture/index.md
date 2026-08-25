---
status: Thickening
opened: 2026-08-25
navigator: Henrique
related:
  - ../es9-human-codebase-ownership/index.md
  - ../../roadmap/cv18-deterministic-readiness-simulation/index.md
  - ../../decisions/records/2026-08-01T0203Z-hamsterdan-is-a-standalone-petrus-application.md
  - ../../decisions/records/2026-08-23T2152Z-v5-is-the-only-runtime-and-retired-topology-state-fails-closed.md
---

# ES-010: Composable Hamsterdan architecture

## Inquiry

How should Hamsterdan separate pure workflow definition, effectful readiness
execution, trusted host supervision, provider and agent adapters, and
deterministic simulation so each module is independently understandable,
testable, and composable into larger simulations?

The exploration should produce a maintainer-facing architecture that is easier
to explain than the current V5-shaped source tree. It should also make each
module's interface a deterministic test seam without relying on permissive
mocks, test-only execution paths, or one whole-application fake that duplicates
production rules.

The expected outcome is a candidate for a new Capability Value with several
Delivery Stories. Production reorganization does not begin merely because this
Exploratory Story exists.

## Why this inquiry exists

The current top-level package graph already follows a sound direction:

```text
host
  -> agents
  -> github_app
  -> readiness
  -> contracts

readiness -> contracts
github_app -> contracts
```

The maintainer experience becomes less clear below that level:

- `host/v5` contains per-PR composition, Petrus runtime custody, durable ingress,
  timers, authority claims, and provider or agent effect adapters;
- `contracts/readiness_v5.py` combines host-normalized observations, private loop
  memory, loop-to-loop facts, and typed Activity work and results;
- the former `contracts/readiness.py` retains a large retired workflow model
  beside a few values still imported by current code;
- package and class names present `v5` as a permanent concept even though it was
  only the label of the implementation selected from earlier alternatives;
- the host package contains both process-wide supervision and one workflow's
  effectful execution;
- the current deterministic World proves a substantial host vertical but does
  not provide independently composable workflow, readiness, GitHub, agent,
  host, and whole-Hamsterdan simulations.

ES-009 correctly found that file size and journey tracing alone did not justify
broad reorganization. ES-010 begins from new Navigator direction and a stronger
design requirement: module interfaces should support compositional deterministic
simulation at every meaningful seam.

## Scope

- Define the target module tree and dependency direction before defining import
  rules or moving production files.
- Apply the deletion test to current and proposed modules.
- Separate pure workflow meaning from effectful readiness execution.
- Narrow `host` to trusted process ownership and multi-instance supervision.
- Design readiness-owned typed ports and concrete effect adapters composed by
  the host.
- Remove historical V5 naming from current source, schemas, tests, artifacts,
  and current documentation without compatibility machinery.
- Design Hamsterdan-owned deterministic simulation that can exercise each module
  alone and compose those same modules at larger scopes.
- Treat bounded production stepping as part of module design rather than a
  test-only hook.
- Produce an ordered Delivery candidate with explicit validation and
  documentation work.

Production behavior changes, package moves, schema changes, and executable
spikes require their own checkpoints. This index records inquiry and accepted
direction; it does not authorize implementation.

## Working language

### Workflow

The **readiness workflow** is the complete pure definition of one PR-readiness
process:

- the Petri Net topology;
- normalized observations accepted by the Net;
- durable state carried by its concern loops;
- typed facts exchanged between loops;
- typed Motus Activity requests and results;
- initial marking and pure folds.

The workflow decides, for example, that one failed exact-head CI run may request
one rerun before escalating to repair. It does not know that GitHub performs the
rerun or that an agent performs the repair.

### Readiness

**Readiness execution** runs the workflow against controlled real-world effects.
It owns one PR's workflow application, Petrus adaptation, durable workflow
custody, authority reads, timers, and adapters that implement workflow
Activities through GitHub, agents, Git, and other effect seams.

Readiness does not construct concrete provider or agent implementations inside
its application. It receives readiness-owned typed ports. Concrete adapters are
isolated under `readiness/effects`, and the host constructs and injects them.

### Host

The **host** is the trusted long-running process that owns application-wide
authority and supervises many independent readiness instances. It owns startup,
configuration, credentials, durable webhook custody, installation and repository
routing, agent runtime custody, process-wide runnable work, multi-instance
activation, reconciliation, and shutdown.

The host does not decide whether a PR is ready. The workflow decides. The host
constructs and supervises readiness execution under current authority.

### Activity and effect adapter

An **Activity** is typed Motus work declared by the workflow. An **effect
adapter** is the readiness implementation that performs that work against an
external seam. For example, the workflow owns `RerunReq`; a readiness effect
adapter implements it through a GitHub capability supplied by the host.

### Simulation

A **simulation** runs a real module inside a controlled deterministic
environment. The term `simulator` is avoided because it suggests a replacement
that imitates the real module. The term `sim` is avoided because it weakens
import and search clarity.

## Accepted direction

### Current code has no compatibility obligation

Hamsterdan has not entered production. ES-010 may replace all V5 source names,
package paths, persisted schemas, operation identities, queues, tests, and
simulation artifacts without migrations, import aliases, dual readers, or
replay compatibility.

This freedom includes:

- `host/v5`, `readiness/net_v5`, and `contracts/readiness_v5.py`;
- V5-prefixed Python symbols;
- `"topology": "v5"` bindings;
- V5-prefixed SQLite objects, queues, History identities, and timer identities;
- the `ready.facts` compatibility lane if no current design reason retains it;
- `hamsterdan.readiness.v5-world` profiles and retained replay artifacts;
- current README, operator, roadmap, Workbench, and development terminology.

Dated Ariad records remain truthful project history. CV17, ES-007, dated
worklogs, superseded decisions, and historical qualification evidence may keep
V5 terminology because that was their actual subject. Those records impose no
runtime or source compatibility requirement. A new decision should supersede
current V5-only durable-state policy rather than silently rewriting the old
record.

### Target ownership hypothesis

```text
hamsterdan/
  workflow/       pure readiness definition
  readiness/      effectful execution of that workflow
  host/           trusted process and multi-instance supervision
  github_app/     GitHub provider implementation
  agents/         credential-free agent protocol and execution adapters
  contracts/      only genuinely neutral cross-module values
  simulation/     Hamsterdan-owned deterministic runtime and whole-app composition
```

A candidate inner tree is:

```text
workflow/
  observations.py
  facts.py
  activities.py
  net/
    topology.py
    folding.py
    gating.py
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

readiness/
  application.py
  runtime.py
  authority.py
  ports.py
  custody/
    instance.py
    ingress.py
    timers.py
  effects/
    publication.py
    rerun.py
    review.py
    mutation.py
    git.py
    agents.py
  simulation/

host/
  __main__.py
  api.py
  service.py
  runnable.py
  agents/
    routing.py
    pi.py
  simulation/

github_app/
  ...
  simulation/

agents/
  ...
  simulation/

simulation/
  runtime.py
  clock.py
  scheduling.py
  faults.py
  artifacts.py
  replay.py
  hamsterdan.py
```

Names and file splits remain hypotheses until the experiments apply the deletion
test and trace real interfaces. The exploration should prefer coherent deep
modules over one file per noun.

### Dependency direction

The current working hypothesis is:

```text
host
  -> readiness application
  -> readiness effect adapters
  -> github_app
  -> agents

readiness application and custody
  -> readiness-owned ports
  -> workflow
  -> Petrus runtime defining modules

readiness/effects/github or publication
  -> readiness ports
  -> github_app

readiness/effects/agents
  -> readiness ports
  -> agents

workflow
  -> Petrus Net, History-value, and Activity defining modules only

github_app and agents
  -/> workflow, readiness, or host
```

Crossing a seam does not make a value neutral. A value belongs to the module that
owns its meaning. Workflow observations, facts, loop memory, and Activity
contracts belong to `workflow`. Readiness owns the capability ports required to
execute those Activities. `contracts` retains only values whose meaning is
truly neutral across sibling modules.

### Typed dependency injection

Host composes readiness through readiness-owned typed ports. The readiness
application does not import or construct concrete GitHub and agent
implementations. Concrete bridge adapters may import the readiness port and the
provider module they adapt; the host selects and constructs them.

Concrete scenario: a Git ref update succeeds but its response is lost.

- workflow simulation supplies the typed ambiguous Activity terminal;
- readiness simulation supplies a deterministic Git adapter that accepts the
  ref and loses the response;
- host simulation adds durable custody and reconstruction;
- production supplies the real Git and GitHub adapter;
- the workflow and readiness application remain unchanged across those scopes.

### Bounded production stepping

Each stateful module should expose bounded single-step progress at meaningful
durable or effect cuts. Production drivers and simulations use the same steps.
Convenience drain or settle operations may remain only as bounded loops over the
single-step interface.

A step may admit one observation, commit one workflow transition, request or
settle one Activity, apply one timer command, mature one timer, custody one
webhook, activate one PR, or reconcile one subject. A step is not an arbitrary
line of Python.

This direction makes crash cuts explicit without test-only callbacks or patches.
It also prevents one readiness instance from hiding unbounded work inside one
scheduler call.

### Driver mechanism remains exploratory

An explicit `step() -> StepResult` is the baseline. A bounded spike should
compare it with an ephemeral trampoline or generator-based authoring style.

Any candidate must reject a design that:

- stores workflow truth in a generator frame;
- requires generator continuation for crash recovery;
- creates a second scheduler that duplicates Petrus workflow execution;
- creates a test-only execution path;
- makes every module asynchronous merely to obtain interleaving;
- obscures the durable cut represented by one yielded operation; or
- permits one call to drain unbounded work.

### Hamsterdan owns deterministic simulation

Hamsterdan simulation is not executed or owned by Petrus. `workflow.simulation`
uses Petrus because the real workflow uses Petrus. GitHub, agents, readiness,
host, and whole-Hamsterdan simulation remain independent of Petrus testing
ownership.

A Hamsterdan-owned deterministic simulation runtime coordinates:

- logical time;
- timer registration and maturity;
- ordering among eligible module steps;
- deterministic choices;
- modeled I/O completion;
- fault activation;
- crash generations;
- budgets and resource accounting;
- journaling, artifacts, and replay.

Every module receives the same deterministic environment so independently owned
state remains synchronized. Parallel behavior is explored as recorded
interleavings of bounded module steps. Actual process and thread parallelism
remains separate correspondence evidence.

Useful implementation from `petrus.testing.dst` may be copied into Hamsterdan.
Copied code becomes Hamsterdan-owned, carries explicit provenance, and may be
renamed or changed without compatibility or synchronization. Hamsterdan does
not design one package to serve both Petrus and Hamsterdan now.

After Petrus and Hamsterdan have independently proven their simulation designs,
a separate future exploration may compare them. A neutral package should exist
only if two mature implementations reveal a genuinely shared module. That
future extraction is outside ES-010.

### Local simulation ownership and composed checkers

Each production owner also owns its deterministic simulation under a local
`simulation` package:

```text
workflow/simulation
readiness/simulation
github_app/simulation
agents/simulation
host/simulation
```

Local simulation packages own their command vocabulary, observations, faults,
deterministic adapters, resource measures, and checkers. The top-level
`hamsterdan.simulation` package owns only shared deterministic execution and
whole-application composition.

Local checkers compose upward:

```text
workflow simulation
  workflow checkers

readiness simulation
  workflow + readiness checkers

host simulation
  workflow + readiness + host checkers

whole Hamsterdan
  every local checker + cross-module checkers
```

Independent expected models are added only where a genuinely different
derivation can catch correlated implementation mistakes. The current independent
readiness model is evidence for that pattern; a bounded queue or codec may need
direct invariants rather than a second implementation.

## Current evidence to preserve during exploration

### Import graph

Static inspection of the current source found a clean top-level DAG and one
source cycle:

```text
hamsterdan.readiness.net_v5
  <-> hamsterdan.readiness.net_v5.topology
```

The cycle comes from the package initializer importing topology while topology
imports concern modules through the package object. Other dense clusters are
acyclic composition cones. In particular, `host.v5.application` and
`host.service` import several lower defining modules directly. Density alone is
not evidence for moving those modules.

`tests/test_architecture.py` is the current relative-import-aware owner of source
import rules. Python AST should remain the primary import-graph mechanism.
ast-grep may enforce local structural conventions after the target ownership map
is ruled. Rules must follow architecture; they must not invent it.

### Current test layers

The repository currently has useful but uneven locality:

- concern-loop tests use a real Petrus Engine through one shared Net harness;
- host integration tests cover custody, persistence, restart, and local Git or
  process seams;
- semantic journey tests cover recognizable end-to-end behavior;
- CV18 simulation runs a real single-PR host against deterministic provider and
  agent models;
- architecture and distribution tests own repository-level rules.

Some tests sit under a narrower owner than the behavior they exercise. For
example, inline recovery tests under the readiness Net tree compose concrete
host, GitHub, agent, and Git publication modules. Test relocation should follow
the accepted module seam rather than file size.

### Current deterministic World

The current `ReadinessWorld` is valid host-level deterministic simulation
evidence. It runs real webhook ingress, host custody, readiness application,
Petrus Engine, Net, History, Dispatch and Worker, timers, route custody, and
reconciliation. It models GitHub transport and truth, agent terminals, and Git
publication.

Its current limits are evidence for ES-010, not defects in CV18's accepted
scope:

- one fixed PR;
- same-process reconstruction rather than process death;
- coarse host operations that may drain several internal workflow steps;
- no standalone workflow, readiness, GitHub, agent, or whole-app simulation;
- no real Pi runtime or subprocess Git in the World;
- some checkers know production History and SQLite shapes; and
- several named fault dimensions remain explicitly blocked.

CV18 remains historical accepted evidence. ES-010 may replace its architecture
without preserving profile or artifact compatibility.

## Exploration experiments

The experiments are dependency ordered. A later experiment may refine an
earlier hypothesis, but it should not silently bypass an unresolved decision.

### 1. Current ownership and deletion map

Question: what does each maintained source module own today, and which modules
are pass-throughs or mixed owners?

Work:

- produce the complete current import DAG, strongly connected modules, fan-in,
  and fan-out;
- classify every source and test-support module by interface and implementation;
- apply the deletion test to package initializers, `contracts`, current host
  modules, readiness topology modules, and shipped test support;
- distinguish current production, current operator support, current simulation,
  and historical executable residue.

Output: a ruled module ledger and a list of observed mixed owners. File size is
recorded only as a navigation signal.

Exit: the Navigator can explain the current clean-green and mutation-recovery
paths by owner without relying on V5 package names.

### 2. Workflow language decomposition

Question: what values form the workflow's honest interface and internal
language?

Work:

- classify every current readiness value as normalized observation, loop-owned
  memory, loop-to-loop fact, Activity work/result, neutral cross-module value,
  or retired residue;
- trace every producer and consumer;
- test whether the proposed `observations`, `facts`, and `activities` modules are
  deep and acyclic;
- determine whether some groups should remain together for locality;
- identify the minimal neutral residue, if any, that still belongs in
  `contracts`.

Output: an exact value ownership map and target import paths.

Exit: every current value has one defining owner and no type exists merely
because several callers need it.

### 3. Pure workflow package shape

Question: what is the smallest clear interface around the pure readiness
workflow?

Work:

- map topology, loop, fold, gate declaration, initial marking, and Activity
  manifest ownership;
- remove the package-initializer cycle in a throwaway structural prototype;
- prove the workflow can build and run without host, GitHub, agent, or Hamsterdan
  simulation imports;
- decide the public import seam for building, seeding, stepping, and observing
  the workflow;
- assess whether the current concern-loop file boundaries still earn their
  depth after value ownership changes.

Output: target `workflow` tree, import graph, and interface candidates.

Exit: a workflow-only reader can trace one decision from observation to Activity
request and typed terminal without entering readiness execution.

### 4. Readiness ports and effect adapters

Question: what exact capabilities must effectful readiness receive from the
host?

Work:

- trace comment publication, rerun, agent review, conversation, coding, Git
  publication, authority evidence, clocks, and timer custody;
- define ports from readiness needs rather than provider SDK methods;
- test each port against production and deterministic adapters;
- keep GitHubKit, HTTP, credentials, Pi runtime objects, Engine, Dispatch, Worker,
  and simulation truth out of port values;
- decide which adapters belong together and which earn separate modules.

Output: a port and adapter matrix with operation identity, error modes, ordering,
recovery, and authority invariants.

Exit: production and deterministic adapters can satisfy each port without
patching readiness implementation.

### 5. Readiness execution tree

Question: which current host modules form one deep readiness execution module?

Work:

- reclassify current `host/v5`, `host/git_publish.py`,
  `host/pi_workspace.py`, `host/binding.py`, and `host/protocol.py` under the
  accepted workflow/readiness/host language;
- test the proposed `application`, `runtime`, `custody`, `authority`, and
  `effects` grouping through the deletion test;
- identify false topology-neutral abstractions that no longer earn an interface;
- preserve authority, at-least-once effects, lookup-first recovery, and
  credential isolation.

Output: target `readiness` tree and one-PR execution reading route.

Exit: readiness can be constructed through typed ports and exercised without
HTTP ingress or multi-instance host supervision.

### 6. Host narrowing

Question: what remains when host owns only the trusted process and
multi-instance supervision?

Work:

- classify startup, HTTP ingress, webhook custody, configuration, secrets,
  provider registry, agent runtime custody, runnable work, instance activation,
  reconciliation, inspection, and shutdown;
- identify readiness-specific policy still hidden in `HostService`;
- define the host-to-readiness factory and lifecycle seam;
- preserve independent PR progress and bounded scheduler behavior;
- apply the deletion test to retained qualification and operator modules.

Output: target `host` tree, lifecycle interface, and multi-instance invariants.

Exit: host simulation can replace readiness with a strict deterministic adapter,
and readiness simulation can run without host.

### 7. Bounded-step contract

Question: which durable and effect cuts must production expose as one bounded
step?

Work:

- inventory current drains and hidden loops in workflow runtime, readiness
  settlement, timer handling, Activity execution, and host scheduling;
- define step result values and quiescence or wait dispositions;
- map every current crash/recovery test to a step cut;
- prove production drains can be expressed as bounded loops over the same steps;
- define fairness and resource bounds for one instance and multiple instances.

Output: step contracts and cut matrix for workflow, readiness, and host.

Exit: simulations reach required crash cuts without callbacks, monkeypatches, or
private mutable runtime access.

### 8. Driver mechanism spike

Question: does an explicit loop, trampoline, or generator provide the clearest
bounded driver over durable steps?

Work:

- prototype the three mechanisms outside production;
- reconstruct after every durable cut using only retained state;
- compare stack behavior, cancellation, fairness, inspectability, replay
  vocabulary, and type checking;
- reject generator-frame authority and hidden schedulers.

Output: evidence table and recommendation. Promote a decision record only if the
selected mechanism is hard to reverse, surprising, and chosen through a real
trade-off.

Exit: one driver mechanism is selected or the explicit step baseline remains
because alternatives add no leverage.

### 9. Hamsterdan simulation runtime

Question: what deterministic execution machinery does Hamsterdan itself need?

Work:

- inventory generic behavior currently consumed from `petrus.testing.dst`;
- copy only useful pieces into an isolated experiment with provenance;
- remove Petrus profile, artifact, and compatibility assumptions that Hamsterdan
  does not need;
- define one logical clock, eligible-action scheduler, deterministic choices,
  fault controller, crash generation, budgets, journal, artifact, and replay
  interface;
- prove that the runtime knows no workflow, readiness, GitHub, agent, or host
  semantics.

Output: Hamsterdan-owned runtime candidate and copy-and-own ledger.

Exit: a trivial pair of independent simulation modules share time, ordering,
crash, and exact replay without importing Petrus testing code.

### 10. Local module simulations and checkers

Question: can each major module run alone under its real interface?

Work:

- build minimal experimental simulations for workflow, readiness, GitHub,
  agents, and host;
- reuse production step and port interfaces;
- give each simulation strict commands, observations, faults, bounds, and local
  checkers;
- use independent models only where they supply a different semantic derivation;
- fail loudly on undeclared operations and unknown inputs.

Minimum scenarios:

- workflow: observation to Activity request, terminal fold, crash, and reload;
- readiness: accepted-but-response-lost effect and lookup-first settlement;
- GitHub: authority movement, stale read, rate limit, accepted hidden effect,
  and identity collision;
- agents: submit, accept, run, terminal availability, terminal delivery,
  cancellation, and runtime loss;
- host: two PR instances, route revocation, fair scheduling, crash, and resource
  cleanup.

Output: local simulation interfaces, checker catalog, and gaps requiring
production seam changes.

Exit: each module can generate and replay one meaningful failure without
constructing whole Hamsterdan.

### 11. Whole-Hamsterdan composition

Question: do the same local simulations compose under one Hamsterdan runtime?

Work:

- mount workflow, readiness, GitHub, agent, and host simulations under one clock
  and scheduler;
- route namespaced commands without modules importing one another's simulation
  implementations;
- exercise parallel eligible work through recorded interleavings;
- compose local checkers and add only cross-module properties;
- compare one retained current CV18 scenario against the new composition without
  requiring artifact compatibility.

Minimum vertical: signed webhook, workflow decision, agent operation, accepted
GitHub or Git effect with lost response, host crash, reconstruction, lookup-first
settlement, and exact replay with one accepted effect.

Output: whole-application simulation candidate, semantic coverage report, and
correspondence limits.

Exit: one scenario can be reduced to a lower simulation scope when the failing
property belongs to that module, while cross-module failures remain replayable
at whole-app scope.

### 12. Enforcement and Delivery expansion

Question: what should other sessions implement, in what order, and how will the
repository prevent architectural drift?

Work:

- finalize the target package and test trees;
- write the allowed dependency graph and reviewed exceptions;
- assign every maintained production module to one architecture rule owner;
- keep Python AST as import-direction authority and add ast-grep only for local
  syntax structure it expresses better;
- define positive composition assertions beside forbidden edges;
- design small green delivery slices with focused tests, current behavior
  characterization, documentation, and rollback points;
- identify current decisions that need superseding and active docs that need
  rewriting;
- propose the new Capability Value and expand it into Delivery Stories before
  implementation.

Output: candidate package map, architecture rules, delivery graph, validation
matrix, decision list, debt assessment, and CV proposal.

Exit: the Navigator can accept or reject the complete candidate without asking a
Delivery session to rediscover its architecture.

## Correctness obligations during exploration

Every candidate must preserve or deliberately improve:

- the workflow owns coordination and provider-independent readiness decisions;
- host authority fences every external effect immediately before execution;
- credentials and installation tokens remain host-owned and never enter agent or
  workflow values;
- effects remain at-least-once with stable operation identity and lookup-first
  recovery;
- each PR has independent progress and durable workflow authority;
- crash reconstruction uses retained state rather than Python object continuity;
- every retry, queue, timer, scheduler loop, generated scenario, and artifact has
  an explicit bound;
- simulations distinguish modeled claims from real provider, process, storage,
  and concurrency evidence;
- local checkers cannot borrow desired state from the implementation they judge;
- whole-app composition does not weaken local module testability.

## Explicit non-goals

- Preserve or migrate V5 runtime state, schemas, identities, imports, or replay
  artifacts.
- Design current support for two simultaneous workflow versions.
- Implement future ingress routing between draining and new workflow versions.
- Extract a generic deterministic simulation package shared by Petrus and
  Hamsterdan.
- Replace real GitHub, agent, Git, process-kill, filesystem, database, security,
  or concurrency correspondence tests with simulation claims.
- Split large files merely because they are large.
- Collapse concern loops whose separate durable decisions still earn their
  depth.
- Add architecture rules before the target ownership graph is accepted.

Future workflow replacement may use upper-level routing so new instances enter a
new implementation while an old deployment drains. ES-010 should avoid blocking
that future shape, but it does not design or implement it now.

## Candidate gate

ES-010 may become a Delivery candidate only when it has:

1. an exact target source and test tree;
2. one ruled import DAG with every maintained module assigned or explicitly
   exempted;
3. a deletion-test assessment for every moved, split, merged, introduced, or
   removed module;
4. accepted workflow, readiness, host, port, adapter, and step interfaces;
5. a Hamsterdan-owned simulation runtime design with explicit Petrus provenance
   and no synchronization contract;
6. standalone workflow, readiness, GitHub, agent, and host simulation evidence;
7. one whole-Hamsterdan composition using the same local simulation modules;
8. local and cross-module checker ownership with independence limits;
9. correctness, liveness, resource-bound, crash, and replay obligations;
10. a source cleanup inventory covering V5 names, retired contracts, tests,
    artifacts, schemas, docs, and decisions;
11. an ordered delivery plan that keeps the repository reviewable and green;
12. a proposed Capability Value with Delivery Stories and concrete validation
    routes; and
13. explicit Navigator acceptance of the candidate and roadmap placement.

## Current state

The Navigator accepted the initial direction in a read-only architecture session.
No production, test, configuration, runtime-state, or historical-record change
was authorized. This index is the first durable exploration artifact. The next
session should begin with experiment 1 rather than turning the target tree above
into an unreviewed rename plan.
