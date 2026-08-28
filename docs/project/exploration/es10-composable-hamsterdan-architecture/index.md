---
status: Promoted
opened: 2026-08-25
promoted: 2026-08-27
navigator: Henrique
related:
  - ../es9-human-codebase-ownership/index.md
  - ../../roadmap/cv18-deterministic-readiness-simulation/index.md
  - ../../roadmap/cv20-composable-reconstructible-hamsterdan/index.md
  - ../../roadmap/cv21-composable-outer-hamsterdan/index.md
  - ../../roadmap/cv22-decomposable-readiness-workflow/index.md
  - ../../decisions/records/2026-08-01T0203Z-hamsterdan-is-a-standalone-petrus-application.md
  - ../../decisions/records/2026-08-23T2152Z-v5-is-the-only-runtime-and-retired-topology-state-fails-closed.md
  - ../../decisions/records/2026-08-27T1604Z-composable-hamsterdan-is-the-planned-replacement-architecture.md
  - ../../decisions/records/2026-08-28T1453Z-cv20-fragments-into-outer-system-and-workflow-replacement-values.md
---

# ES-010: Composable Hamsterdan architecture

## Promotion status

This exploration is complete and retained as provenance. The canonical,
self-contained implementation owners are now
[CV21](../../roadmap/cv21-composable-outer-hamsterdan/index.md) for the new outer
system over one temporary current-Net bridge and
[CV22](../../roadmap/cv22-decomposable-readiness-workflow/index.md) for the
recursive production-subnet workflow, bridge removal, and final cutover.
[CV20](../../roadmap/cv20-composable-reconstructible-hamsterdan/index.md)
preserves the superseded integrated design and its review evidence. The
alternatives, experiment-era names and possibilities below are not
implementation inputs; where wording differs, the owning CV21 or CV22 record
governs Delivery.

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

### Replacement tree and delivery sequencing

The Navigator ruled that the new architecture is built as a parallel
replacement tree rather than an in-place migration:

- New production code lives under `src/hamsterdan2` with its tests under
  `tests2`, using the final inner package names (`workflow`, `readiness`,
  `host`, `github_app`, `agents`, `contracts`, `simulation`).
- `src/hamsterdan` is frozen except for production fixes while the replacement
  is built.
- When `src/hamsterdan2` fully replaces the current behavior, one cutover
  excludes `src/hamsterdan` and renames `src/hamsterdan2` to `src/hamsterdan`
  and `tests2` to `tests`.
- CV19's supervised launch does not happen before ES-010. Should any launch
  precede the cutover, the private single-operator deployment's durable state
  may be reset at cutover; no migration, alias, or dual-reader work exists in
  any ES-010 candidate.

### Replacement-tree quality gate

The frozen tree keeps its current non-blocking audit posture until deletion.
The replacement tree is a strict blocking surface from its first slice:

- `scripts/check` treats `src/hamsterdan2` and `tests2` as blocking for the
  full Ruff rule surface, formatting, `ty`, ast-grep structural rules, and
  cyclomatic complexity with `max-complexity = 4`.
- A function above complexity 4 requires a per-function `noqa: C901` with a
  one-line justification, reviewed at slice review. Engineering convention 17
  continues to govern the frozen tree until deletion.
- Replacement-tree tests are behavioral: they assert public behavior and its
  reason, not helper decomposition. Collaborators arrive through owned typed
  ports as injected strict fakes; `unittest.mock` and monkeypatching remain
  available only at seams the module does not own.
- The test taxonomy names four layers — behavioral unit, integration at real
  seams, deterministic simulation per module and composed, and journey
  acceptance — with deterministic simulation as the first-class correctness
  owner and the others as correspondence evidence. Each delivery slice states
  which layers it adds.
- the engineering style contract (Hamsterdan Python style contract) owns extracting the Navigator's
  Python style preferences into checkable rules, review conventions, and free
  taste. Its ruled contract should exist before the first code-writing
  replacement slice so `src/hamsterdan2` is written in that style from line
  one. the engineering style contract runs in parallel with Phases A and B below.

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
durable or effect cuts. Production drains and simulation Timelines use the same
steps.
Convenience drain or settle operations may remain only as bounded loops over the
single-step interface.

A step may admit one observation, commit one workflow transition, request or
settle one Activity, apply one timer command, mature one timer, custody one
webhook, activate one PR, or reconcile one subject. A step is not an arbitrary
line of Python.

This direction makes crash cuts explicit without test-only callbacks or patches.
It also prevents one readiness instance from hiding unbounded work inside one
scheduler call.

### Timeline stepping mechanism remains exploratory

An explicit `step() -> StepResult` is the baseline. A bounded spike should
compare it with an ephemeral trampoline, generator-based authoring style, and
ordinary async owner calls routed through a coroutine stepper.

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

## Session plan

Each experiment below runs as one independent session or thread. A session is
safe alone because its inputs are durable records, its output is one durable
record, and it ends at a green state or a Navigator ruling. No session needs
another session's transcript.

Session mechanics:

- Each session begins by reading this index and the prior experiment records it
  names as inputs, nothing else.
- Each experiment writes one record under `experiments/` in this directory,
  named `<NN>-<slug>.md`.
- Each session ends by updating the "Current state" section of this index so
  the next session starts from the index alone.
- Spike code lives under this exploration directory, never under `src/`.
  Every session is non-production and leaves the repository green wherever it
  stops.
- A Navigator ruling checkpoint (R1–R4) closes each phase. A later session must
  not silently bypass an unruled checkpoint.

```text
Phase A: Evidence (read-only)
  S1  Exp 1  ownership + deletion map      -> experiments/01-ownership-map.md
  S2  Exp 2  workflow value ownership      -> experiments/02-value-ownership.md
  R1: Navigator rules the ownership and value maps.

Phase B: Interface design
  S3  Exp 3  workflow package shape        -> experiments/03-workflow-shape.md
  S4  Exp 4  ports + adapter matrix        -> experiments/04-ports-adapters.md
  S5  Exp 5  readiness execution tree      -> experiments/05-readiness-tree.md
  S6  Exp 6  host narrowing                -> experiments/06-host-narrowing.md
  R2: Navigator rules the target trees.

Phase C: Stepping
  S7  Exp 7  bounded-step contract         -> experiments/07-step-contract.md
  S8  Exp 8  Timeline/stepper spike        -> experiments/08-driver-spike.md
  R3: Timeline stepping mechanism ruled; promote a decision record if warranted.

Phase D: Simulation
  S9   Exp 9  simulation runtime           -> experiments/09-simulation-runtime.md
  S10x Exp 10 local module simulations     -> experiments/10-<module>-simulation.md
  S11  Exp 11 whole-Hamsterdan composition -> experiments/11-composition.md
  R4: Navigator rules the simulation design.

Phase E: Candidate
  S12  Exp 12 rules, delivery graph, CV proposal -> candidate gate ruling
```

Inputs: S1 and S2 read only current source and this index. S3 and S4 both read
only the ruled Phase A records and may run as parallel threads. S5 needs S4;
S6 needs S5. S7 needs the ruled Phase B trees; S8 needs S7. S9 needs S7 and the
R3 ruling. Exp 10 fans out per module (workflow, readiness, GitHub, agents,
host) once S9 fixes the runtime interface; those threads are parallel. S11
needs every Exp 10 record. S12 needs everything ruled plus the engineering style contract style
contract.

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

### 8. Timeline and coroutine stepper spike

Question: does an explicit loop, trampoline, or generator provide the clearest
bounded stepping mechanism beneath a simulation Timeline?

Work:

- prototype the explicit loop, data trampoline, completed-result generator,
  and clarified Timeline/coroutine-stepper mechanism outside production;
- reconstruct after every durable cut using only retained state;
- compare stack behavior, cancellation, fairness, inspectability, replay
  vocabulary, and type checking;
- reject generator-frame authority and hidden schedulers.

Output: evidence table and recommendation. Promote a decision record only if the
selected mechanism is hard to reverse, surprising, and chosen through a real
trade-off.

Exit: one stepping mechanism is selected or the explicit step baseline remains
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

The Navigator accepted the initial direction in a read-only architecture session
and, in a second planning session, ruled the replacement-tree strategy
(`src/hamsterdan2` with one final cutover rename), the strict replacement-tree
quality gate including `max-complexity = 4`, the behavioral dependency-injection
test preference, the four-layer test taxonomy with deterministic simulation
first-class, and the ES-010/CV19 sequencing. The same session added the session
plan above and opened the engineering style contract for the Python style contract in a parallel
thread. No production, test, configuration, runtime-state, or historical-record
change was authorized.

S1 is complete: [experiments/01-ownership-map.md](experiments/01-ownership-map.md)
records the ruled module ledger, the single facade cycle, the mixed-owner list
(nine modules), the `contracts/readiness.py` live-surface finding (four names,
~93% residue), and both required path traces by owner. The import-graph tool
lives at [experiments/tools/import_graph.py](experiments/tools/import_graph.py).

S2 is complete: [experiments/02-value-ownership.md](experiments/02-value-ownership.md)
maps all 116 vocabulary names plus the four live retired names to one defining
owner and target import path each. Headline findings: the neutral residue in
`contracts` is empty (`WorkflowModel` is workflow mechanism,
`AdmittedConversation` is a `github_app` provider value, the retired
`ChangeResult`/`RepairResult` pair dies); the proposed
`observations`/`facts`/`activities` decomposition is acyclic and deep with one
added `workflow/values.py`; batons, sentinels, and terminal records are
loop-owned; and the class-name/token-color namespace is a durable interface
with named string-coupled readers. The trace tool lives at
[experiments/tools/value_trace.py](experiments/tools/value_trace.py).

Phase A is complete and checkpoint R1 is ruled: the Navigator accepted the S1
ownership map and the S2 value map, including the empty `contracts` residue,
`AdmittedConversation` moving to `github_app` with the `WorkflowModel` base
dropped, loop-owned batons with an explicit token-class registry replacing
`vars(_colors)` discovery, and the added `workflow/values.py`. Phase B may
begin: S3 (workflow package shape) and S4 (ports and adapter matrix) read the
ruled Phase A records and may run as parallel threads. S3's open items from S2
are the explicit token-class registry, the `GateFact` rename with legacy-lane
deletion, and the `publication_qualification` record shape (deferred to S6).

S3 is complete: [experiments/03-workflow-shape.md](experiments/03-workflow-shape.md)
records the target `workflow` tree, import graph, and public seam. Headline
findings: gate declaration — today triplicated across loop `GATES` tuples,
activity return unions, and `gating.py` handler chains — unifies into one
workflow-owned `MANIFEST` of `GateDeclaration`s in `workflow/activities.py`;
`gating.py` stays whole as a workflow module (revised S1 verdict — its imports
are all allowed Petrus defining modules, and effectful execution already lives
in `runtime.py`); the public seam is defining-module imports with no facade,
and stepping is deliberately absent (Petrus `Engine.advance()` composed by
readiness or simulation; the contract is S7's scope); the cycle dies under two
AST-checkable rules (no initializer re-exports, no `from package import
module`); all nine loops keep their depth. S3's open items are closed:
hydration needs no registry (by requested type against arc-stamped color)
while the composer owns an explicit `TOKEN_CLASSES` registry aggregated from
per-module `TOKENS` exports with build-time validation; `GateFact` renames to
`DashboardEvent` with `dash.facts` → `dash.events`, and deleting the legacy
`ready.facts` lane makes the replacement workflow CEL-free. The executable
structural prototype lives at
[experiments/spikes/03-workflow-shape/](experiments/spikes/03-workflow-shape/)
(three proofs pass: structure, workflow-only decision run on a real Engine,
loud registry failure). `publication_qualification` remains deferred to S6.
S4 is complete and accepted by the Navigator:
[experiments/04-ports-adapters.md](experiments/04-ports-adapters.md) records the
eight readiness capability groups and the operation-level adapter matrix.
Headline findings: readiness receives typed workflow Activity implementations,
not broad GitHub or agent ports; the five comment publications stay together
behind distinct typed methods, rerun stays separate because it owns the final
pre-request evidence cut, review request storage moves to readiness custody,
and mutation remains one Activity while coding and Git publication stay
independently replaceable adapters. Authority combines the durable readiness
grant with fresh provider evidence; timer command ordering, persistence,
reconstruction, acknowledgements, and maturity belong to readiness custody,
with only the clock and construction inputs supplied by host. Port values carry
no GitHubKit, HTTP, credentials, Pi runtime, Petrus runtime, or simulation truth.
Two questions remain visible for R2: review provider-evidence failure currently
has no typed workflow terminal, and reply/reminder/dashboard intentionally do
not share the full authority fence used by findings and readiness announcement.
The candidate method sets are capability-signature pseudocode, not a direction
to implement Python `Protocol` interfaces; concrete injection form remains owned
by the ruled the engineering style contract style contract. the engineering style contract is required before the first
replacement code-writing slice and S12, not before S4 acceptance or S5. At S4
acceptance, checkpoint R2 remained unruled and S5 could proceed from the
accepted S4 record.

S5 is complete and accepted by the Navigator:
[experiments/05-readiness-tree.md](experiments/05-readiness-tree.md) records the
target `readiness` tree and one-PR execution route. Headline findings: most of
`host/v5` becomes the deep readiness execution package, split into one-PR
application sequencing, Petrus runtime adaptation, authority, reconstructible
custody, and operation-specific effects; `host/git_publish.py` moves to the Git
effect, while `host/pi_workspace.py` belongs with the agent adapter rather than
readiness. The current host application protocol, durable-Activity resolver,
host Activity-name lookup, inactive-result synthesis, and V5 compatibility
bindings are false topology-neutral abstractions and do not survive. The current
ingress store's direct queries against the host webhook `inbox` reveal a missing
host-to-readiness lifecycle seam, not a ninth S4 effect capability. S6 must
define that custody/revocation seam, stop host agent-route repair from decoding
workflow History, place process-wide discovery and the deferred
`publication_qualification` concern, and preserve bounded independent PR
progress. S4's review-failure and deliberately unfenced-publication tensions
remained open beside these S5 handoffs for checkpoint R2. At S5 acceptance, R2
remained unruled and S6 could proceed from the accepted S5 record.

S6 is complete and accepted by the Navigator:
[experiments/06-host-narrowing.md](experiments/06-host-narrowing.md) records the
target `host` tree, host-to-readiness factory and lifecycle seam, and
multi-instance invariants. Headline findings: a host-owned durable instance
catalog replaces discovery through readiness History paths; a monotonic
route/custody lifecycle view replaces shared webhook-table access; readiness
reports bounded agent-operation posture so process-wide route repair no longer
decodes workflow History; and host inspection aggregates readiness-owned
detached projections instead of parsing History itself. `HostService` loses
Activity-name lookup, inactive-terminal synthesis, readiness drains, and
concrete one-PR construction; the retained runnable index must provide bounded
fair turns so one degraded PR cannot monopolize progress. Production
qualification faults remain a separate optional host composition concern, live
atomic setup qualification moves beside operator support, and the unconsumed
historical `PublicationQualification` record dies in the replacement tree.
S4's review-evidence and deliberately weaker publication-fencing questions,
plus the exact readiness-owned outcome for queued publication after route
revocation, were carried into checkpoint R2 below.

Phase B is complete and checkpoint R2 is ruled: the Navigator accepted the S3
workflow tree, S4 ports and adapter matrix, S5 readiness tree, S6 host tree,
their dependency direction, and the host-to-readiness lifecycle seam. Exhausted
review provider-evidence failure becomes a typed workflow terminal rather than
remaining an opaque Motus execution failure. Reply, reminder, and dashboard
publication retain their operation-specific safeguards without silently
inheriting the full exact-head/base/policy fence used by findings and readiness
announcement. A queued publication encountering route revocation retains its
typed blocked outcome, but readiness creates that outcome from workflow
declaration and host lifecycle evidence; host never decodes Activity work or
manufactures a workflow terminal. These are architecture rulings, not
production-change authorization. S7 may now define the bounded-step contract
from the ruled Phase B trees; S8 still requires S7.

S7 is complete and accepted by the Navigator:
[experiments/07-step-contract.md](experiments/07-step-contract.md) records the
workflow-runtime, readiness, and host step contracts and the current
crash/recovery cut matrix. Headline findings: one bounded step crosses exactly
one named cut for one subject and separately bounds rows, bytes, calls, and
time; `Progressed`, `Waiting`, `Quiescent`, `Terminal`, and `Unavailable` are
distinct results; effect observation is exposed before Activity terminal
recording; timer acceptance and local markers remain separate; and host inbox
acknowledgement, posture, route settlement, and fair requeue follow readiness
as their own cuts. Production drains are finite budgeted loops over the same
steps used by simulation. One-instance weak fairness uses a readiness-lane
cursor; multi-instance fairness uses a durable enqueue sequence or equivalent
cursor, one readiness call per selected subject, and tail requeue. The record
identifies two mechanism gaps for S8 rather than hiding them: current Petrus
first-load reconciliation can repair multiple retained occurrences before one
normal action, and current Worker execution combines claim, effect, and
terminal report. At S7 acceptance R3 remained unruled, so S8 could begin its
Timeline/stepper spike from the accepted S7 contract.

S8's first record was accepted as executed evidence, then reopened after the
Navigator clarified that “trampoline” meant ordinary deep Python calls yielding
their actual leaf callable, not recursion elimination or a data bounce around a
monolithic `step()`. The amended
[experiments/08-driver-spike.md](experiments/08-driver-spike.md) retains the
original 31-cut/618-crash comparison and adds a callable-coroutine spike across
host, readiness, workflow, and Activity layers. Its public `Timeline` can stop
before the leaf, after the leaf while its value remains outside the owners, or
after normal returns produce the host result through one internal
`CoroutineStepper`. All 32 returned progress
positions and the three focused effect positions reconstruct without a saved
frame; lookup-first recovery leaves one provider mutation per operation. The
amended recommendation is Timeline over the callable coroutine stepper, with
production using that same stepper inside an explicit finite drain. Durable
owner state retains all scheduling authority, and the stepper enforces one leaf
per owner step. The Petrus bounded-load and split Activity-execution gaps
remain. The Navigator accepted the amended S8 and ruled R3 in
[`Timeline and coroutine stepper share bounded execution`](../../decisions/records/2026-08-26T2012Z-timeline-and-coroutine-stepper-share-bounded-execution.md):
`Timeline` is the public simulation/debugging API, `CoroutineStepper` is the
shared internal mechanism, and production uses bounded `step()`/`drain()` over
that mechanism. Coroutine frames and callables remain process-local; durable
owner state remains recovery and scheduling authority. The ruling authorizes
no production implementation and leaves S9 to settle the exact Timeline API.

S9 is complete and accepted by the Navigator:
[experiments/09-simulation-runtime.md](experiments/09-simulation-runtime.md)
defines the exact Hamsterdan-owned `Timeline`, structural module boundary,
logical clock, eligible-action scheduler, namespaced deterministic choices,
occurrence faults, crash generations, budgets and resource gauges, strict
journal, single-version artifact, and exact replay contract. The copy-and-own
ledger pins every adapted mechanism to Petrus
`44cac5ff48ac371ebae56323941983f30db13c0d` while omitting profiles,
identities, checker cadence, fair/converged policy, process framing, and V1–V4
compatibility. Its independent `alpha`/`beta` proof shares time and equal-time
ordering, crosses the offered/executed/idle crash positions, recovers a landed
effect lookup-first, and exactly replays without importing Petrus testing code
or naming workflow, readiness, GitHub, agent, or host semantics. Coroutine
frames, callables, held leaf values, exceptions, and owner-return values remain
process-local and absent from artifacts; durable modules retain eligibility and
recovery authority. The confirmed post-acceptance review correction makes every
execution-budget failure terminal, discards any suspended frame, reserves
post-operation journal capacity, and preserves an exact final artifact even
when leaf, journal, or restart-generation capacity is exhausted. The isolated
spike and ten focused contracts live under
[experiments/spikes/09-simulation-runtime/](experiments/spikes/09-simulation-runtime/).
No production, maintained test, or configuration surface changed.

Experiment 10's five local simulations are complete and accepted by the
Navigator: [workflow](experiments/10-workflow-simulation.md),
[readiness](experiments/10-readiness-simulation.md),
[GitHub](experiments/10-github-simulation.md),
[agents](experiments/10-agents-simulation.md), and
[host](experiments/10-host-simulation.md). Each mounts through S9's unchanged
`Timeline`, declares strict module-owned commands, observations, faults,
resources, and local checker rules, generates one meaningful failure, and
exactly replays without constructing whole Hamsterdan. The workflow proof
reconstructs a pending Activity request from retained History and detects a
typed terminal with the wrong operation. Readiness recovers one accepted
response-lost Git effect lookup-first with one agent call. GitHub crosses an
executed-phase crash after exactly one accepted POST and refuses content or
full-authority identity collisions. Agents recover retained runtime and
delivery terminals across two crashes without a duplicate runtime start. Host
gives two PRs bounded fair progress, preserves a stable operation across
response-loss requeue or crash, observes route revocation freshly, and cleans
up resources after a local close failure.

Pre-acceptance review corrected physical-effect counting in the readiness
checker, GitHub's retained proof to respect one mutation attempt per bounded
step, idempotent agent resubmission in its checker, and host response-loss
terminalization before requeue. Thirty-three focused contracts and every
session's quick and full gates pass. Production still needs the bounded
Engine-load, Activity/effect, GitHub publication, agent lifecycle/terminal, and
host lifecycle/catalog/scheduler/shutdown seams recorded by the five reports;
those are S11/S12 correspondence inputs rather than new debt or authorization
for production changes. No production, maintained test, or configuration
surface changed.

S11 is complete and accepted by the Navigator:
[experiments/11-composition.md](experiments/11-composition.md) first retained an
accepted partial negative result when the unchanged S10 workflow and readiness
simulations lacked a causal typed edge. The accepted bounded follow-up extends
only the S10 workflow, agents, and readiness experiments and composes all five
local simulations under S9's unchanged `Timeline`. The corrected vertical is:

```text
real build_net_v5 MutWork
  -> accepted agents delivery
  -> exact delivered CodingResult
  -> readiness publication
  -> Pushed into the original workflow occurrence
```

The workflow request projection comes from the production `git_gate`
`ActivityRequested` History record, not composition handoff state. The
composition-owned adapter returns the exact retained typed agents result to
readiness without making the local simulations import one another. Readiness
records that result's canonical digest in the one accepted Git publication;
after the accepted response is lost, generation two reconciles lookup-first
without a second agent call or publication and returns exact `Pushed` to the
original Activity occurrence. The real production mutation fold then settles.

All five local checkers and the one cross-module checker pass, resource use is
bounded, and the canonical crash/recovery artifact replays exactly. A full-flow
counterexample that changes only the composition handoff's `MutWork.instruction`
leaves every local checker passing while the cross checker reports exactly that
composition altered the real workflow-declared work; this establishes checker
ownership rather than mere co-mounting. The S10 standalone defaults and current
production correspondence tests remain green. No production, maintained test,
configuration, or runtime-state surface changed, and no debt record is needed.

Phase D evidence S9 through S11 is complete and checkpoint R4 is ruled. The
Navigator accepted S9's Hamsterdan-owned semantic-free `Timeline`, the five
owner-local simulations and checkers from S10, and S11's composition-owned
adapters and cross-module checkers as the target simulation design inputs. The
ruling preserves bounded production-aligned steps, explicit resource limits,
lookup-first crash recovery, and exact replay while retaining the reports'
correspondence limits: it does not approve production implementation, spike
file structure, artifact compatibility, or claims about real process or
distributed concurrency.

S12 has synthesized those fixed inputs into the Delivery candidate at
[experiments/12-enforcement-delivery.md](experiments/12-enforcement-delivery.md).
It fixes the exact `src/hamsterdan2` and `tests2` trees, final import DAG and
blocking the engineering style contract gate, a 61/61 current-source disposition ledger, production
seam and V5 cleanup inventories, twelve dependency-ordered green Delivery
Stories, the complete validation matrix, and promoted Capability Value. The
Navigator accepted its Experience Report and promoted the candidate on
2026-08-27 as CV20. The
[later fragmentation decision](../../decisions/records/2026-08-28T1453Z-cv20-fragments-into-outer-system-and-workflow-replacement-values.md)
dropped [that integrated plan](../../roadmap/cv20-composable-reconstructible-hamsterdan/index.md)
before implementation. CV21 now owns outer reconstruction through one retained-
Net bridge and CV22 owns recursive production-subnet workflow replacement and
final cutover. Neither successor is pulled. Current V5 remains the only runtime
until a separately approved CV22 cutover; no replacement implementation or
deployment change has begun.
