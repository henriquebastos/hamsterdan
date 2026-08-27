# Experiment 12 — Enforcement and Delivery synthesis

Session S12. Durable inputs are the ES-010 index; the accepted S1–S11
experiment records; ruled checkpoints R1–R4; the fully ruled the engineering style contract Python
style contract; the current 61-module `src/hamsterdan` tree and 46-file Python
test tree; and the current feedback, architecture, packaging, and deployment
surfaces. The repository baseline was local `main` at `2266af5`, one accepted
R4-ruling commit ahead of `origin/main` at `4e12312`. No production,
maintained-test, configuration, roadmap, decision, debt, or worklog file is
changed by this synthesis.

Method: treat R1–R4 as fixed architecture inputs; assign every current source
module exactly once; state the complete replacement tree and its import rules;
separate target-tree blocking gates from the old tree's audit posture; turn the
production-seam gaps and cleanup inventory into dependency-ordered green
Delivery Stories; and test the candidate against every ES-010 completion
condition. This record is a Delivery contract, not an implementation and not a
compatibility plan.

## Verdict

ES-010 has a coherent Delivery candidate. The accepted architecture can be
built as a parallel replacement tree, qualified through behavior-owned tests,
and switched in one final cut without importing or migrating V5 runtime state:

```text
src/hamsterdan2 + tests2
  ├─ strict gate from their first commit
  ├─ pure workflow and one-PR readiness execution
  ├─ owned GitHub and agent implementations
  ├─ trusted host composition and fair supervision
  └─ owner-local simulations mounted by one Hamsterdan runtime
                       │
                       ▼
             qualified replacement tree
                       │
              one final rename/cutover
                       │
                       ▼
        old V5 source, tests, schemas, identities,
        profiles, artifacts, and compatibility code removed
```

The build order is twelve independently green Delivery Stories. Every story
has one owner, named predecessors, an observable result, a rollback point, and
focused validation. The old `src/hamsterdan` runtime remains the installed
application until the final story. Before that cut, the replacement code can
be imported and tested but is not a second production runtime, does not read
old state, and is not selected by configuration. There is no dual writer,
dual reader, topology selector, state migrator, alias facade, or compatibility
artifact reader.

The candidate preserves the settled product behavior and correctness
obligations: explicit human intent, workflow-owned decisions, credential
isolation, stable operation identity, current-authority fencing, at-least-once
effects, lookup-first recovery, independent PR progress, explicit finite
bounds, and exact deterministic replay. It does not preserve V5 internal names,
state schemas, History identities, simulation profiles, or artifact formats.

## Fixed inputs and non-goals

### R1 — value ownership

- `workflow` owns workflow values, observations, internal facts, Activity work,
  typed terminals, gate declarations, and loop-private state.
- `readiness` owns authority, admission, progress, custody, and effect-port
  values. It consumes workflow values directly rather than wrapping them.
- `github_app` owns normalized GitHub values, including admitted conversation.
- `agents` owns credential-free request/result and execution-terminal values.
- `host` owns process lifecycle, route/custody evidence, instance discovery,
  scheduling, and detached inspection values.
- Crossing a seam does not make a value neutral. The target has no `contracts`
  package.

### R2 — package ownership and behavior

- The workflow package is pure. It can import Petrus Net, binding, schema, and
  Activity defining modules, but not runtime execution objects.
- One-PR Petrus execution, authority, custody, and typed effect adaptation live
  in `readiness`.
- `host` is the only concrete application composition root. It owns webhook
  custody, process resources, provider and agent route custody, multi-instance
  fairness, lifecycle evidence, and shutdown, but no workflow interpretation.
- GitHub and agents remain sibling implementation boundaries and never import
  one another, workflow, readiness, or host.
- Exhausted provider-evidence failure during review becomes a typed workflow
  terminal.
- Replies, reminders, and dashboard retain their accepted operation-specific
  weaker safeguards rather than silently receiving the full mutation/findings
  fence.
- When a route is revoked with publication work queued, readiness combines the
  workflow declaration with fresh host lifecycle evidence and creates the
  workflow-declared blocked outcome. Host never decodes the request or creates
  its terminal.

### R3 — bounded execution

Production and simulation expose the same effect-adjacent positions:

```text
start / attempt claimed
  -> execute / effect observed
  -> finish / terminal recorded
```

The synchronous `Timeline` is public simulation/debugging API; its
`CoroutineStepper` is internal. Frames, callables, results held between phases,
and exceptions are process-local conveniences, never recovery authority.

### R4 — simulation design

- The S9 semantic-free Timeline is the shared simulation interpreter.
- Workflow, readiness, GitHub, agents, and host each own a strict local module,
  retained modeled state, local fault vocabulary, resource gauges, and local
  checker.
- Whole-Hamsterdan composition mounts those unchanged local simulations,
  supplies concrete adapters, and owns only cross-module properties.
- The required causal path is real workflow `MutWork` → accepted agent
  delivery → exact delivered `CodingResult` → readiness publication → `Pushed`
  into the original workflow occurrence.

### Deliberate non-goals

- Preserve or migrate current V5 state, SQLite schemas, History identities,
  dispatch queues, runnable hints, agent-route schemas, or simulation artifacts.
- Run old and new production topologies concurrently or select between them.
- Preserve `hamsterdan.*` import compatibility during construction.
- Promote experimental spike file shapes or operation counts as production
  API.
- Claim real process, filesystem, SQLite, provider, Pi, or distributed
  correspondence from deterministic simulation alone.
- Rewrite dated decisions, roadmap records, exploration records, or worklogs
  whose historical statements remain true at their recorded dates.

## Exact replacement source tree

Every initializer below contains at most a policy docstring and an explicit
empty export declaration. It never re-exports a child module. `module.py`
implements one owner-local S9 module and its strict vocabulary; `checker.py`
derives that owner's invariants from detached observations. The split keeps
the implementation and its independent derivation separate without creating
one file per command, value, or fault.

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

The operator support is a package rather than a single `operator.py` because
the deletion test identifies two independent rims: the human command surface
and atomic qualification setup. `operator.__main__` owns parsing, output, and
safe command calls; `operator.qualification` owns the qualification record and
filesystem/Git setup transaction. Neither belongs to process supervision.

`host.clock` is the sole production owner of direct wall-clock and sleep APIs.
Host composition injects its values/functions into webhook retry, readiness,
runnable, provider, agent, and shutdown policy. `simulation.clock` is a logical
integer clock and imports no wall-clock API.

## Target-module deletion test

The current-source ledger below handles every moved, split, and removed module.
This table applies the same deletion test to every introduced target module.
A grouped row covers only modules with the same structural reason; it does not
authorize them to import one another.

| Target module(s) | Why the boundary survives deletion |
|---|---|
| Every `__init__.py` | Required package marker and explicit no-facade policy; owns no runtime name or re-export |
| `workflow/values.py` | Canonical value behavior and cross-group aliases would otherwise be repeated in three vocabulary seams |
| `workflow/observations.py` | Names the complete host/readiness→workflow admission language |
| `workflow/facts.py` | Prevents loops from importing sibling loop implementations merely to exchange typed mail |
| `workflow/activities.py` | Is the one adapter-facing request/result vocabulary and single gate manifest owner |
| `workflow/net/folding.py` | Centralizes the pure fold-authoring/hydration mechanism used by all loops without owning loop meaning |
| `workflow/net/gating.py` | Owns variant conversion and declared gate binding against the manifest; readiness runtime owns effect-terminal correlation/admission |
| `workflow/net/topology.py` | Owns composition, initial marking, loop/gate aggregation, token registry, and build-time validation as one unit |
| `workflow/net/life.py` | Owns the lifecycle admission hub and incarnation baton |
| `workflow/net/ci.py` | Owns exact-head CI state and checks facts |
| `workflow/net/escalation.py` | Owns bounded rerun/repair escalation decisions |
| `workflow/net/review.py` | Owns review-round custody, findings, and typed inability decisions |
| `workflow/net/mutation.py` | Owns mutation request/settlement workflow state and provisional-head facts |
| `workflow/net/conversation.py` | Owns human-intent folds and typed workflow requests |
| `workflow/net/dashboard.py` | Owns the open dashboard event projection and self-healing state |
| `workflow/net/reminders.py` | Owns reminder-cycle and workflow side of the timer protocol |
| `workflow/net/readiness.py` | Owns readiness projection, fault facts, and announcement decision |
| Each owner `simulation/module.py` | Mounts that real owner under S9 and owns strict commands, faults, retained modeled state, and gauges |
| Each owner `simulation/checker.py` | Keeps the independent derivation outside the implementation it judges |
| `readiness/ports.py` | Shows the complete typed one-PR capability seam without one-file-per-port fragmentation |
| `readiness/authority.py` | Composes durable grant, fresh provider evidence, and fresh host lifecycle evidence once for all fenced effects |
| `readiness/application.py` | Owns the ordering among admission, workflow, Activity, timer, wake, and route cuts; otherwise host/simulation would duplicate it |
| `readiness/runtime.py` | Contains Petrus records, occurrence recovery, Dispatch/Worker cuts, and terminal correlation inside one adaptation boundary |
| `readiness/custody/instance.py` | Prevents one root from being opened for another PR without retaining topology compatibility |
| `readiness/custody/ingress.py` | Owns atomic manifest/grant identity, order, and reconstruction |
| `readiness/custody/review.py` | Owns exact request/attempt retention, which differs from ingress and timer reconstruction |
| `readiness/custody/timers.py` | Owns ordered command, acknowledgement, maturity, and History-rebuild protocol |
| `readiness/effects/evidence.py` | Is the sole GitHub-truth→workflow-observation normalization boundary |
| `readiness/effects/agents.py` | Isolates credential-free conversation/review/coding calls from their distinct orchestrators |
| `readiness/effects/publication.py` | Shares one comment-ledger mechanism while preserving five operation-specific methods and outcomes |
| `readiness/effects/rerun.py` | Owns a different final evidence cut and ambiguity policy from comment publication |
| `readiness/effects/review.py` | Owns request recovery, authority cancellation, and review-terminal classification, but not storage |
| `readiness/effects/mutation.py` | Coordinates coding and Git publication as one workflow Activity without implementing either capability |
| `readiness/effects/git.py` | Owns patch admission, Git proof, complete lookup, trailers, object creation, and exact ref CAS |
| `github_app/models.py` | Keeps frozen provider meaning from leaking SDK response shapes |
| `github_app/config.py` | Owns strict provider registration/portfolio/credential input and redaction |
| `github_app/auth.py` | Owns App/installation authentication and token/client lifetime |
| `github_app/transport.py` | Bounds SDK/HTTP response and request metadata behind one provider wire seam |
| `github_app/gateway.py` | Owns normalized reads and raw Git object/ref operations above transport |
| `github_app/effects.py` | Owns reusable lookup-first provider publication/rerun mechanisms below readiness classification |
| `github_app/routing.py` | Owns installation/repository route persistence and generation |
| `github_app/webhooks.py` | Owns signature verification, normalization, and durable provider inbox implementation |
| `agents/protocol.py` | Owns all credential-free request/result/terminal contracts and correlation validation |
| `agents/pi.py` | Adapts those contracts to Pi prompts, operation identity, result validation, and bounded calls |
| `agents/pi_workspace.py` | Owns exact checkout/archive/patch safety without GitHub credentials or host policy |
| `host/clock.py` | Is the one production wall-clock/sleep owner required by the style contract and injected into all consumers |
| `host/composition.py` | Is the only place that joins readiness construction with concrete GitHub/agent implementations and process resources |
| `host/service.py` | Owns portfolio startup, bounded multi-instance turns, failure isolation, and shutdown ordering |
| `host/api.py` | Is the FastAPI/lifespan adapter; deleting it would mix HTTP with service policy |
| `host/__main__.py` | Is the process CLI and construction edge; it contains no operator workflow |
| `host/instances.py` | Makes process discovery independent of readiness History/filesystem layout |
| `host/inspection.py` | Aggregates bounded detached process/readiness facts without becoming another History decoder |
| `host/runnable.py` | Owns reconstructible wake hints plus durable fair sequence/lease instead of rescanning all instances |
| `host/qualification.py` | Isolates disabled one-shot production correspondence faults from normal supervision |
| `host/agents/routing.py` | Owns immutable process operation→composition binding and route activation without workflow result names |
| `host/agents/pi.py` | Owns Pi installation, direct-key, opaque connection, runtime, and erasure custody |
| `operator/__main__.py` | Owns human JSON/terminal behavior separately from the long-running service CLI |
| `operator/qualification.py` | Owns the atomic human-operated setup transaction and its result vocabulary |
| `simulation/runtime.py` | Owns Timeline, generation boundaries, generic commands/observations, budgets, and internal stepper coordination |
| `simulation/clock.py` | Owns deterministic integer logical time independent of semantic scheduling |
| `simulation/scheduling.py` | Owns cross-module eligible-action ordering and choice streams without module meaning |
| `simulation/faults.py` | Owns generic occurrence matching; modules still interpret semantic points/payloads |
| `simulation/artifacts.py` | Owns strict canonical artifact schema/encoding and byte refusal |
| `simulation/replay.py` | Owns expanded-operation replay and exact comparison without an artifact registry |
| `simulation/hamsterdan.py` | Is the only owner of five-module construction adapters and cross-module checkers |

## Exact replacement Python test tree

Python tests are grouped by behavior owner, not made to mirror every
implementation file. Scenario classes and helper DSLs stay in the file that
owns the tested contract until independent reuse earns another module.

```text
tests2/
  test_architecture.py
  test_distribution.py
  test_feedback.py
  behavioral/
    workflow/
      test_vocabulary.py
      test_lifecycle.py
      test_ci_and_escalation.py
      test_review.py
      test_mutation_and_conversation.py
      test_dashboard_and_reminders.py
      test_readiness.py
    readiness/
      test_application.py
      test_runtime.py
      test_authority.py
      test_ingress_custody.py
      test_review_custody.py
      test_timer_custody.py
      test_publication_effects.py
      test_rerun_effect.py
      test_review_effect.py
      test_mutation_effect.py
    github_app/
      test_auth_and_config.py
      test_transport_and_gateway.py
      test_effects.py
      test_routing_and_webhooks.py
    agents/
      test_protocol.py
      test_pi.py
      test_pi_workspace.py
    host/
      test_clock.py
      test_composition.py
      test_service.py
      test_instances_and_inspection.py
      test_runnable.py
      test_agent_custody.py
      test_qualification.py
    operator/
      test_operator.py
  integration/
    test_workflow_runtime.py
    test_readiness_execution.py
    test_github_provider.py
    test_agent_execution.py
    test_host_lifecycle.py
  simulation/
    test_runtime.py
    test_workflow.py
    test_readiness.py
    test_github_app.py
    test_agents.py
    test_host.py
    test_composition.py
  acceptance/
    test_journeys.py
    test_recovery.py
    test_correspondence.py
```

The exact tree is a placement contract, not a test-count target. A Delivery
Story may add scenarios to an existing listed file but does not add a new
directory or helper module without applying the deletion test and updating
this contract through normal Navigator review.

`tests/amp_webhook_relay.test.ts` remains the maintained non-Python relay gate
through construction and cutover. It is not part of `tests2` or the 46-file
Python disposition ledger, and DS12 retains it at its canonical path.

## Final import DAG

```text
host service/API ───────────────▶ readiness lifecycle values
host composition ───────────────▶ readiness construction
        │                       ▶ readiness effect adapters
        ├───────────────────────▶ github_app
        └───────────────────────▶ agents

readiness application/custody ──▶ readiness ports/authority/runtime ──▶ workflow
readiness GitHub effects ────────▶ github_app
readiness agent effect ─────────▶ agents
readiness runtime ──────────────▶ Petrus runtime defining modules

operator.__main__ ──────────────▶ operator.qualification

owner.simulation ───────────────▶ owner production code
owner.simulation ───────────────▶ simulation mechanics
simulation.hamsterdan ──────────▶ five owner.simulation packages
```

Arrows mean “imports.” The diagram folds one special case: an owner-local
simulation imports both its production owner and neutral simulation mechanics;
production modules never import simulation. Whole composition imports all five
local simulations, never their private stores.

### Forbidden edges and names

The blocking architecture audit enforces all of these:

1. The `hamsterdan2` graph is acyclic.
2. Initializers do not re-export child names, and code never imports a module
   through a package object (`from hamsterdan2.workflow.net import life`).
3. `workflow` never imports readiness, host, GitHub, agents, simulation, or
   Petrus `Engine`, Dispatch, Worker, History-store implementations, provider
   SDKs, HTTP libraries, clocks, SQLite, or filesystem effects.
4. Readiness core (`application`, `runtime`, `ports`, `authority`, `custody`)
   never imports concrete providers, agents, host, or simulation.
5. Each `readiness.effects` module may bridge at most one provider family.
   `mutation.py` coordinates readiness-owned coding and Git capabilities; it
   does not import their concrete `agents` or `github_app` implementations.
6. `github_app` and `agents` never import one another, workflow, readiness,
   host, or simulation.
7. Only `github_app` imports GitHubKit or `httpx`; only `host` imports FastAPI.
8. Only `readiness.runtime` imports Petrus `Engine`, Dispatch, and Worker.
   This supersedes the current V5 architecture assertion that host owns those
   objects. Host remains the sole concrete *application composition root*.
9. Only `host/composition.py` imports readiness construction and concrete
   GitHub/agent implementations together.
10. Production code does not import owner-local simulation or root simulation.
11. There is no `contracts` package, `net_v5`, `host.v5`, `V5*` identifier,
    topology selector, compatibility facade, `ready.facts` place/migration,
    or Petrus DST profile/artifact import.
12. Imports name defining modules. Root and package-object convenience imports
    fail even when they would not create a cycle.
13. Among Hamsterdan modules, `operator.__main__` imports only
    `operator.qualification`; `operator.qualification` imports no Hamsterdan
    module.

### Required positive edges

Negative rules alone can produce a disconnected but green tree. The audit also
requires:

- `host/composition.py` to import the readiness construction seam plus GitHub
  and agents concrete constructors;
- `readiness/runtime.py` to import `workflow.net.topology.build_net`,
  `seed_marking`, the explicit token registry, the workflow Activity manifest,
  gate wiring, and Petrus runtime defining modules;
- `workflow.net.topology` to import every loop by full module path, aggregate
  all explicit `TOKENS`, and fail on name collisions or undeclared colors;
- `workflow.activities.MANIFEST` to declare every gate exactly once, with
  request, result variants, lane, operation identity, and blocked mapping;
- readiness application to receive effect capabilities rather than import
  implementations;
- `operator.__main__` to import `operator.qualification` directly;
- every owner-local simulation to import and mount its real owner surface;
- `simulation.hamsterdan` to mount the same five local modules used by their
  standalone tests and to own composition adapters and cross checkers; and
- the causal composition test to prove unchanged `MutWork`, exact delivered
  `CodingResult`, result-sensitive publication, and `Pushed` correlation back
  to the original workflow occurrence.

## Complete current-source disposition ledger

“Replace” means reimplement the accepted responsibility in the named target;
it does not mean copy the current module wholesale. “Split” means the current
file has more than one target owner. “Delete” means no target code path retains
that responsibility.

<!-- source-disposition:start -->
| Current source | Disposition in the replacement |
|---|---|
| `src/hamsterdan/__init__.py` | Replace with empty-policy `src/hamsterdan2/__init__.py`; no facade |
| `src/hamsterdan/agents/__init__.py` | Delete re-exports; replace with empty `agents/__init__.py` |
| `src/hamsterdan/agents/pi.py` | Replace in `agents/pi.py`; retain credential-free Pi adaptation and prompt validation |
| `src/hamsterdan/agents/protocol.py` | Replace in `agents/protocol.py`; remove `ChangeResult`/`RepairResult` aliases and add one public typed durable result/cancellation/timeout/cleanup encoding |
| `src/hamsterdan/contracts/__init__.py` | Delete; target has no neutral contracts package |
| `src/hamsterdan/contracts/readiness.py` | Split `WorkflowModel` to `workflow/values.py` and `AdmittedConversation` to `github_app/models.py`; delete retired workflow and qualification values |
| `src/hamsterdan/contracts/readiness_v5.py` | Split by R1 into `workflow/{values,observations,facts,activities}.py` and loop-private values; no compatibility module |
| `src/hamsterdan/github_app/__init__.py` | Replace with empty `github_app/__init__.py` |
| `src/hamsterdan/github_app/auth.py` | Replace in `github_app/auth.py` |
| `src/hamsterdan/github_app/config.py` | Replace in `github_app/config.py` |
| `src/hamsterdan/github_app/effects.py` | Replace provider comment/rerun mechanisms in `github_app/effects.py`; readiness classifications stay in readiness effects |
| `src/hamsterdan/github_app/gateway.py` | Replace in `github_app/gateway.py` |
| `src/hamsterdan/github_app/models.py` | Replace in `github_app/models.py`, adding provider-owned admitted conversation |
| `src/hamsterdan/github_app/routing.py` | Replace in `github_app/routing.py`; use a fresh schema, not a migration |
| `src/hamsterdan/github_app/transport.py` | Replace in `github_app/transport.py`; expose bounded request metadata needed by classified provider policy |
| `src/hamsterdan/github_app/webhooks.py` | Replace in `github_app/webhooks.py`; retain provider ingress and durable inbox implementation while host owns its lifetime and disposition |
| `src/hamsterdan/host/__init__.py` | Delete re-exports; replace with empty `host/__init__.py` |
| `src/hamsterdan/host/__main__.py` | Split process CLI/composition to `host/__main__.py` and human operator commands to `operator/__main__.py` |
| `src/hamsterdan/host/agenticus.py` | Split route custody to `host/agents/routing.py` and credential-free routed calls to `readiness/effects/agents.py`; delete History/result-name interpretation and legacy schema migration |
| `src/hamsterdan/host/api.py` | Replace in `host/api.py` |
| `src/hamsterdan/host/binding.py` | Replace subject binding in `readiness/custody/instance.py` and process discovery in `host/instances.py`; delete topology identity, legacy reads, and preflight |
| `src/hamsterdan/host/git_publish.py` | Replace in `readiness/effects/git.py` |
| `src/hamsterdan/host/pi_a2.py` | Replace trusted Pi runtime/secret custody in `host/agents/pi.py` |
| `src/hamsterdan/host/pi_workspace.py` | Replace credential-free workspace execution in `agents/pi_workspace.py` |
| `src/hamsterdan/host/protocol.py` | Delete; replace with readiness-owned construction/lifecycle values consumed by host |
| `src/hamsterdan/host/publication_qualification.py` | Move atomic setup to `operator/qualification.py`; delete historical `PublicationQualification` |
| `src/hamsterdan/host/runnable.py` | Replace in `host/runnable.py` with durable fair sequence, leases, and tail requeue |
| `src/hamsterdan/host/service.py` | Split concrete construction to `host/composition.py`, discovery to `host/instances.py`, aggregation to `host/inspection.py`, one-shot correspondence faults to `host/qualification.py`, and retain bounded supervision in `host/service.py` |
| `src/hamsterdan/host/testing/__init__.py` | Delete; local simulations and root simulation have empty owned initializers |
| `src/hamsterdan/host/testing/_readiness_contract.py` | Replace its useful closed vocabularies and bounds in owner-local simulation modules; delete Petrus profile identity |
| `src/hamsterdan/host/testing/_readiness_provider.py` | Split deterministic truth into GitHub, agents, and readiness local simulations |
| `src/hamsterdan/host/testing/readiness_coverage.py` | Replace required semantic coverage as acceptance assertions over Hamsterdan artifacts; delete V5/Petrus profile accounting |
| `src/hamsterdan/host/testing/readiness_world.py` | Split runtime mechanics to `simulation/*`, owner behavior to five local simulations, and cross composition to `simulation/hamsterdan.py` |
| `src/hamsterdan/host/v5/__init__.py` | Delete; no topology package or facade |
| `src/hamsterdan/host/v5/application.py` | Split one-PR sequencing to `readiness/application.py`, concrete construction to `host/composition.py`, conversations to `readiness/effects/agents.py`, and runtime/custody to their owners |
| `src/hamsterdan/host/v5/claim.py` | Replace authority value/capability in `readiness/ports.py` and composition in `readiness/authority.py` |
| `src/hamsterdan/host/v5/gates.py` | Replace operation-specific publication classifications in `readiness/effects/publication.py` |
| `src/hamsterdan/host/v5/ingress.py` | Split provider projection to `readiness/effects/evidence.py`, manifest/grant custody to `readiness/custody/ingress.py`, and authority composition to `readiness/authority.py`; delete inbox-table access and schema migration |
| `src/hamsterdan/host/v5/mutation.py` | Replace orchestration in `readiness/effects/mutation.py`; injected coding and Git capabilities remain separate |
| `src/hamsterdan/host/v5/rerun.py` | Replace in `readiness/effects/rerun.py` |
| `src/hamsterdan/host/v5/review.py` | Split request custody to `readiness/custody/review.py` and typed review execution to `readiness/effects/review.py`; use a fresh schema |
| `src/hamsterdan/host/v5/runtime.py` | Replace in `readiness/runtime.py` with bounded replay/repair and split Motus cuts; remove V5 names and hard-coded gate sets |
| `src/hamsterdan/host/v5/timers.py` | Replace in `readiness/custody/timers.py` with fresh names/schema and bounded reconstruction; delete V5 schema compatibility |
| `src/hamsterdan/operator.py` | Split command rim to `operator/__main__.py` and qualification transaction to `operator/qualification.py` |
| `src/hamsterdan/readiness/__init__.py` | Replace with empty `readiness/__init__.py` |
| `src/hamsterdan/readiness/net_v5/__init__.py` | Delete re-export facade; target `workflow/net/__init__.py` is empty |
| `src/hamsterdan/readiness/net_v5/ci.py` | Replace in `workflow/net/ci.py` |
| `src/hamsterdan/readiness/net_v5/conversation.py` | Replace in `workflow/net/conversation.py` |
| `src/hamsterdan/readiness/net_v5/dashboard.py` | Replace in `workflow/net/dashboard.py` |
| `src/hamsterdan/readiness/net_v5/esc.py` | Replace in `workflow/net/escalation.py` |
| `src/hamsterdan/readiness/net_v5/folding.py` | Replace in `workflow/net/folding.py`; hydrate requested types, not reflective module globals |
| `src/hamsterdan/readiness/net_v5/gating.py` | Replace in `workflow/net/gating.py` with manifest-driven declared handlers and variant conversion; readiness runtime owns terminal correlation/admission |
| `src/hamsterdan/readiness/net_v5/life.py` | Replace in `workflow/net/life.py` |
| `src/hamsterdan/readiness/net_v5/mutation.py` | Replace in `workflow/net/mutation.py` |
| `src/hamsterdan/readiness/net_v5/readiness.py` | Replace in `workflow/net/readiness.py`; delete `ready.facts` and all migration folds/CEL arcs |
| `src/hamsterdan/readiness/net_v5/reminders.py` | Replace in `workflow/net/reminders.py` |
| `src/hamsterdan/readiness/net_v5/review.py` | Replace in `workflow/net/review.py`, including typed provider-evidence inability |
| `src/hamsterdan/readiness/net_v5/topology.py` | Replace in `workflow/net/topology.py` as `build_net`, seed, gate aggregation, explicit token registry, and build validation |
| `src/hamsterdan/readiness/payloads.py` | Replace its useful converter in `workflow/net/gating.py`; delete the simulation-only module |
| `src/hamsterdan/testing/__init__.py` | Delete |
| `src/hamsterdan/testing/readiness.py` | Replace independent expectations in owner-local checkers and journey acceptance; do not retain a second whole-readiness model |
<!-- source-disposition:end -->

This ledger intentionally maps source responsibility, not line movement. The
replacement implementation is written under the new ownership boundaries and
tested there; copying a mixed-owner file and later splitting it would make the
parallel tree red or architecture-invalid between stories.

## Enforcement contract (the engineering style contract gate)

The strict gate starts in Delivery Story 1 and blocks every later story. It
applies only to `src/hamsterdan2` and `tests2` while the replacement is being
built. The current `src/hamsterdan` and `tests` remain under the existing quick,
full, and non-blocking audit contracts until they are deleted at cutover.

### Gate ownership and files

- `quality/hamsterdan2/ruff.toml` owns the isolated strict Ruff configuration.
- `quality/hamsterdan2/sgconfig.yml` and
  `quality/hamsterdan2/ast-grep/*.yml` own seven structural rules.
- `quality/hamsterdan2/ast-grep-tests/` owns positive/negative rule fixtures.
- `tests2/test_architecture.py` owns semantic import-DAG, defining-module,
  positive-composition, external-library, forbidden-name, and enum-privacy
  audits. A small explicit enum registry lives in that test, not in production.
- `scripts/check` invokes the replacement gate from `quick`; therefore `full`
  and `release` inherit it. It also runs `tests2` once the tree exists.

The isolated config avoids weakening the target to accommodate old V5 and
avoids mechanically reformatting or suppressing the old tree before cutover.
At cutover it becomes the repository default and the temporary path qualifier
is removed.

### Ruff and formatter

`src/hamsterdan2` selects `ALL`, uses line length 120 and the Ruff formatter,
and keeps only this justified veto list:

```text
E731 E501 D ARG RUF012 COM812 EM TRY003
PLR0904 PLR0911 PLR0912 PLR0913 PLR0915
```

Production keeps `ANN`, `N`, `ERA`, `PT`, `S`, `RUF100`, `PLR2004`, `T20`,
`FIX`, `TD`, and `FBT` selected. `tests2` alone ignores `ANN`, `SLF`, `S101`,
`S105`, `S106`, and `PLR2004`. The command rim receives the one path-scoped
`T20` exception because printing is its job. Isort is case-sensitive, forces
sorting within sections, leaves two lines after imports, uses no import banner
comments, and puts test machinery in the ruled final `testing` section.

Ruff `C901` uses maximum complexity 4. A cohesive parser, state machine,
workflow fold, or lifecycle operation may carry one per-function justified
suppression; global or file-wide complexity suppression is forbidden.

### ast-grep

The seven verified rules are blocking:

1. `no-banner-comments` in source and tests;
2. `no-underscore-methods` in source, with dunders exempt and per-site
   justified suppression for a true internal;
3. `no-underscore-dataclass-fields` in source;
4. `clock-has-one-owner` in source, allowing direct clock/sleep reads only in
   `src/hamsterdan2/host/clock.py`; the simulation logical clock does not use
   wall-clock APIs;
5. `no-adhoc-mixins` in source;
6. `patch-paths-are-constants` in tests; and
7. `no-function-local-imports` in source.

Every rule has passing and failing fixtures. A suppression must name the design
reason at the exact site and remains subject to `RUF100` or fixture coverage.

### Python AST audit

The AST audit, rather than regex, owns:

- cycle detection and relative-import resolution;
- every forbidden and required edge above;
- empty initializers and rejection of re-export/import facades;
- defining-module imports for Petrus and Hamsterdan concepts;
- provider-library and FastAPI custody;
- unique readiness-runtime custody of Engine/Dispatch/Worker;
- `MANIFEST`, loop, gate, and token-registry census;
- forbidden V5/compatibility names and paths; and
- enum privacy: registered enum definitions may not be imported or compared
  outside their owner, except in `tests2`.

Tier (b) the engineering style contract rules remain review guidance. S12 does not convert judgment
about naming, composition, comments, call-site narrative, typed data, errors,
or test structure into additional brittle mechanical checks.

## Production seam resolutions

The experiments identified real seams that cannot remain experimental. They
are assigned to Delivery Stories rather than hidden as future debt.

### Petrus and Motus

1. **Bounded History load and repair.** Petrus must expose page-bounded History
   replay and one-occurrence reconciliation so the first load cannot perform an
   unbounded scan or redispatch set. `readiness.runtime` returns
   `history_page_replayed` and `occurrence_repaired` cuts directly.
2. **Split Activity execution.** Motus must expose claim, effect-observed, and
   terminal-recorded positions separately. There is at most one provider
   mutation attempt in an effect step; retries are later steps.
3. **Terminal correlation.** `readiness.runtime` owns the terminal-admission
   boundary. Before recording a terminal, it compares occurrence, Activity,
   correlation/idempotency, and the terminal's operation identity with the
   exact requested invocation. A mismatch fails closed before History folding.
   This resolves the S10 workflow counterexample without putting provider
   meaning in the pure Net.

These are bounded Petrus changes with their own tests and pinned dependency
updates. Delivery stops if the public seams require Hamsterdan to inspect or
patch private Petrus runtime state.

### GitHub

- Every provider request has finite page, row, byte, call, and elapsed-time
  bounds.
- Publication lookup reads complete bounded first-parent history for the exact
  operation and digest before agent work or mutation.
- One publication step makes at most one provider mutation attempt. Immediate
  “retry after ambiguous response” inside the same call is removed; a returned
  ambiguous observation becomes durable eligibility for a later lookup-first
  step.
- Fresh full authority is fenced immediately before effects where R2 requires
  it. Reply/reminder/dashboard retain their ruled weaker operation-specific
  safeguards.
- Transport returns enough bounded response metadata for typed rate-limit and
  stale-read classification. No reset timestamp is added to workflow or
  readiness unless a Delivery test proves the scheduler needs one; until then,
  the bounded provider policy supplies a classified retry deadline.

### Agents

- `agents.protocol` owns a public typed, serializable terminal envelope for
  result, cancellation, timeout, and cleanup failure. The terminal is keyed by
  logical operation and attempt and validates the concrete request/result pair.
- Agent execution exposes submit, acceptance, result availability, delivery,
  lookup, cancellation, and cleanup cuts. Runtime response loss and delivery
  response loss recover from retained stores without a second runtime start or
  second accepted receiver terminal.
- Pi execution identity remains `pi:sha256(operation + "\0" + attempt)`.
- Host owns operation-to-route composition and Pi secret/runtime custody;
  agent requests, workspaces, terminals, logs, and artifacts remain
  credential-free.

### Readiness

- One lifecycle owns one PR and returns one S7 `StepResult` per call.
- Admission, workflow, Activity, timer, deferred wake, route settlement, and
  reconstruction cuts are independently schedulable and finitely bounded.
- Authority combines the durable readiness grant, fresh provider evidence,
  and fresh host route/same-subject custody generations at each required cut.
- Route revocation creates operation-specific typed blocked outcomes in
  readiness from workflow declarations plus host evidence.
- Mutation preserves the S11 causal dependency: exact workflow work produces
  the agent request; the exact delivered result enters Git publication; the
  resulting typed terminal closes the original occurrence.

### Host

- Webhook terminal custody and readiness terminal custody remain separate. A
  host delivery is acknowledged only after readiness returns exact accepted or
  already-accepted posture and host records the returned scheduling posture.
- A durable instance catalog replaces History-path discovery.
- A monotonic enqueue sequence, bounded selection lease, and tail requeue make
  scheduler fairness durable. One selected subject receives at most one
  readiness call before another already-due subject can be selected.
- Service construction is one cut: validate the portfolio, inspect bounded
  catalog pages, repair route posture, activate the process agent route, then
  admit ingress and scheduler work.
- Shutdown stops new claims, spends a finite fair terminal-settlement budget,
  and closes each loaded instance/process resource independently. Abrupt abort
  performs no semantic settlement.

### Simulation

- Module semantics, semantic fault admission, checker rules, and resource
  gauges stay owner-local.
- Timeline owns only clock, deterministic interleaving, generic occurrence
  faults, generations, one-leaf phase execution, global budgets, artifacts,
  and replay.
- One artifact format exists: `hamsterdan-simulation`, version 1. It has no old
  Petrus profile identity, compatibility reader, migration field, or import
  registry.
- Exact replay reconstructs fresh module graphs and compares operations,
  choices, journal, clock, generation, resources, and digest exactly.

## V5 and compatibility cleanup inventory

The final story is deletion, not migration. It cannot begin until the
replacement passes every preceding validation row.

### Source, names, and workflow schema

- Delete all `src/hamsterdan/host/v5`, `src/hamsterdan/readiness/net_v5`, and
  `src/hamsterdan/contracts` code.
- Delete the old host readiness protocol, Activity resolver, History decoder,
  topology binding/preflight, topology selector assumptions, and all
  `production`/`v5` compatibility reads.
- Delete `ready.facts`, its nine migration transitions/folds, ordering arcs,
  and CEL-only compatibility mechanism.
- Delete `ChangeResult`/`RepairResult` aliases and retired qualification values.
- Rename the workflow identity from `pr_v5` to `pr_readiness`; rename
  `build_net_v5` to `build_net`; remove all `V5*` type/class names and
  `v5-`/`v5:` operation prefixes that are not externally accepted product
  identities.
- Preserve current external operation meanings where required for GitHub
  lookup and user-visible idempotency, but do not preserve topology labels in
  those identities.

### Durable stores

Fresh replacement roots use new schemas and names. No replacement reader opens
or mutates old roots. The cleanup deletes deployed old state only through a
separately approved operator action after rollback is no longer needed.

- Replace `v5_ingress_manifests`, `v5_authority_grants`, and
  `v5_reconciliation_manifests` with fresh readiness ingress custody.
- Replace `v5_timer_meta`, `v5_timer_operations`, `v5_timers`, and their
  indexes with fresh timer custody.
- Replace `v5_review_requests` and its in-place migration with fresh review
  request custody.
- Replace topology-labeled subject binding with one subject/root binding.
- Replace legacy-migrating agent route tables, runnable rows without durable
  fairness sequence/lease, and filesystem History discovery with fresh host
  route, runnable, and instance-catalog stores.
- Replace the current webhook/routing stores only where their bounded target
  contracts differ; do not add old-schema readers to the new package.
- Replace old Dispatch/History file names and queue identities with target
  readiness-owned names. There is no queue copy or terminal conversion.

### Artifacts, profiles, and tests

- Delete Petrus DST profile/checker identities, V1–V4 artifact compatibility,
  V5 resource keys, semantic-coverage profile names, and current World
  operations from maintained source.
- Delete every old-tree Python unit/integration test after its required
  behavior is proven in `tests2`; do not mechanically port
  implementation-coupled schema, private method, facade import, or
  topology-selection assertions.
- Retain `tests/amp_webhook_relay.test.ts` as the independently maintained Amp
  relay gate; it is not old-tree Python runtime coverage.
- Replace the current architecture test with the R1–R4/the engineering style contract audit. In
  particular, change “host owns Engine/Dispatch/Worker” to “readiness runtime
  owns them; host composition owns concrete construction.”
- Replace the current mutation-only mutmut target and V5-specific check output
  with target-tree semantic targets chosen during Delivery review.
- Replace distribution tests and build package paths from `hamsterdan` to the
  cut-over `hamsterdan` tree after the final rename.

The test disposition is behavior-based and complete for the current 46 Python
test files:

<!-- test-disposition:start -->
| Current test | Delivery disposition |
|---|---|
| `tests/fixtures/skip_probe.py` | Delete; `tests2/test_feedback.py` creates its policy probe in an admitted temporary tree |
| `tests/integration/host/test_git_publish.py` | Re-express Git lookup/object/ref behavior in `tests2/integration/test_github_provider.py` and readiness mutation integration |
| `tests/integration/host/test_pi_a2_factory.py` | Re-express trusted Pi construction in `tests2/integration/test_agent_execution.py` |
| `tests/integration/host/test_pi_workspace.py` | Re-express workspace safety in agent behavioral/integration tests |
| `tests/integration/host/test_qualification_setup_local.py` | Re-express atomic setup in `tests2/behavioral/operator/test_operator.py` |
| `tests/integration/host/test_readiness_scenarios.py` | Re-express user behavior in `tests2/acceptance/test_journeys.py` |
| `tests/integration/host/test_service.py` | Re-express startup, custody, fairness, restart, and shutdown in `tests2/integration/test_host_lifecycle.py` |
| `tests/integration/testing/test_readiness_campaign.py` | Replace with generated schedules in simulation and acceptance recovery tests; no Petrus profile compatibility |
| `tests/integration/testing/test_readiness_coverage.py` | Replace required semantic coverage with journey assertions over Hamsterdan artifacts |
| `tests/integration/testing/test_readiness_world.py` | Split into owner-local simulations, composed simulation, recovery acceptance, and direct correspondence |
| `tests/test_architecture.py` | Replace with strict target DAG, positive composition, defining-module, provider-custody, forbidden-name, and enum audits |
| `tests/test_check_command.py` | Replace with target gate invocation and path-policy contracts in `tests2/test_feedback.py` |
| `tests/test_distribution.py` | Replace with source/wheel/entry-point contracts in `tests2/test_distribution.py` |
| `tests/test_pytest_policy.py` | Replace with target collection/skip policy in `tests2/test_feedback.py` |
| `tests/unit/agents/test_pi.py` | Re-express Pi prompt, identity, result, and bounded execution behavior in agents tests |
| `tests/unit/agents/test_protocol.py` | Re-express strict request/result plus new durable terminal codec in `tests2/behavioral/agents/test_protocol.py` |
| `tests/unit/github_app/test_app_foundation.py` | Re-express provider config/auth/routing/webhook foundation in GitHub behavioral tests |
| `tests/unit/github_app/test_github.py` | Re-express transport, gateway, lookup-first effects, and bounds in GitHub behavioral/integration tests |
| `tests/unit/host/test_agenticus.py` | Split process route custody to host agent tests and routed calls to readiness effect tests; delete History/result-name parsing |
| `tests/unit/host/test_binding.py` | Re-express subject binding and instance catalog; delete topology/legacy compatibility cases |
| `tests/unit/host/test_host_architecture.py` | Replace with target host boundaries and positive composition audit |
| `tests/unit/host/test_pi_a2.py` | Re-express Pi secret/runtime custody in host agent tests |
| `tests/unit/host/test_publication_qualification.py` | Re-express atomic setup in `tests2/behavioral/operator/test_operator.py` and delete historical `PublicationQualification` tests |
| `tests/unit/host/test_runnable.py` | Re-express wake coalescing plus durable fair sequence/lease/tail behavior |
| `tests/unit/host/test_v5_gates.py` | Re-express five operation-specific publication effects without V5 names |
| `tests/unit/host/test_v5_ingress.py` | Split admission/custody/application/runtime/host-ack crash behavior; delete old schemas/migrations and drains |
| `tests/unit/host/test_v5_mutation.py` | Re-express injected coding→Git mutation, authority, result sensitivity, and typed terminals |
| `tests/unit/host/test_v5_rerun.py` | Re-express final-evidence-cut rerun behavior in readiness rerun tests |
| `tests/unit/host/test_v5_review.py` | Split exact request custody and typed review execution; delete schema migration cases |
| `tests/unit/host/test_v5_timers.py` | Re-express fresh timer protocol, ordering, bounded rebuild, and crash cuts; delete V5 schema cases |
| `tests/unit/readiness/net_v5/harness.py` | Delete shared implementation-shaped harness; behavior-owned workflow files keep their smallest local DSL |
| `tests/unit/readiness/net_v5/test_ci_loop.py` | Re-express CI behavior under workflow behavioral tests |
| `tests/unit/readiness/net_v5/test_conversation_loop.py` | Re-express conversation behavior under workflow mutation/conversation tests |
| `tests/unit/readiness/net_v5/test_dashboard_loop.py` | Re-express dashboard behavior and `DashboardEvent` under workflow tests |
| `tests/unit/readiness/net_v5/test_escalation_loop.py` | Re-express escalation behavior under CI/escalation tests |
| `tests/unit/readiness/net_v5/test_gating.py` | Re-express manifest binding, variant routing, and exact terminal correlation under workflow/runtime tests |
| `tests/unit/readiness/net_v5/test_inline_recovery.py` | Split real workflow recovery into workflow-runtime and readiness execution integration tests |
| `tests/unit/readiness/net_v5/test_lifecycle_loop.py` | Re-express lifecycle behavior; delete `ready.facts`, migration, facade, and V5 census assertions |
| `tests/unit/readiness/net_v5/test_mutation_loop.py` | Re-express mutation workflow behavior and instruction propagation |
| `tests/unit/readiness/net_v5/test_readiness_loop.py` | Re-express readiness projection/announcement; delete legacy-lane migration behavior |
| `tests/unit/readiness/net_v5/test_reminders_loop.py` | Re-express workflow timer/reminder behavior under dashboard/reminders tests |
| `tests/unit/readiness/net_v5/test_review_loop.py` | Re-express review rounds, findings, and typed provider-evidence inability |
| `tests/unit/readiness/test_payloads.py` | Fold converter contracts into vocabulary/gating behavior; delete simulation-only module assumption |
| `tests/unit/test_operator.py` | Re-express human command and qualification behavior in `tests2/behavioral/operator/test_operator.py` |
| `tests/unit/test_orb_setup.py` | Preserve deployment/setup behavior against the target command/package; activation remains separately approved |
| `tests/unit/testing/test_readiness_model.py` | Replace independent properties in owner-local checkers and journey tests; delete the second whole-readiness model |
<!-- test-disposition:end -->

### Active documentation and decision supersession

At Delivery/cutover, update active truth in:

- `README.md`;
- `AGENTS.md` architecture contract;
- `docs/project/briefing.md`;
- `docs/process/development-guide.md` and engineering convention 2/gate status;
- active CV19 deployment/operator instructions and package/service entry points;
- `pyproject.toml`, `scripts/check`, ast-grep configuration, and architecture
  tests; and
- current operator/deployment docs that name V5 topology, old paths, old state,
  or old inspection commands.

Dated CV17/CV18/ES7/ES8/ES9 records and worklogs remain unchanged as historical
evidence. At candidate promotion, create one architecture decision that
supersedes
`2026-08-23T2152Z-v5-is-the-only-runtime-and-retired-topology-state-fails-closed.md`
and states that the composable replacement is the only runtime with no old
state compatibility. Preserve or restate the still-valid principle from
`2026-08-22T0107Z-v5-durable-decisions-are-explicit-topology.md`: durable
workflow decisions stay explicit in the topology. The R3 Timeline/coroutine
decision remains active.

## Ordered green Delivery graph

```text
DS1 replacement gate
 ├─ DS2 Petrus/Motus seams
 ├─ DS3 workflow
 ├─ DS4 simulation runtime
 ├─ DS5 GitHub provider
 └─ DS6 agents

DS2 + DS3 + DS4 + DS5 + DS6 ──▶ DS7 readiness
DS6 + DS7                    ──▶ DS8 host
DS3 + DS4 + DS5 + DS6 + DS7 + DS8 ──▶ DS9 composition
DS7 + DS8 + DS9              ──▶ DS10 journeys
DS8 + DS10                   ──▶ DS11 correspondence
DS10 + DS11                  ──▶ DS12 cutover
```

“Rollback” means restore the repository to the predecessor story while the old
installed runtime continues unchanged. It never means translating new state
back into V5.

### DS1 — Establish the replacement-tree gate

**Outcome.** Add the empty replacement skeleton, exact test skeleton, isolated
strict Ruff/ast-grep configuration, architecture audit, and `scripts/check`
integration. Positive architecture assertions initially target explicit
construction placeholders rather than becoming optional.

**Predecessor.** R1–R4 and the engineering style contract only.

**Rollback.** Remove the new tree and isolated gate files; old runtime and
checks were never changed semantically.

**Validation.** Rule fixtures; target Ruff format/check; ty; architecture
positive/negative fixtures; feedback-command tests; quick/full gates.

### DS2 — Own bounded Petrus and Motus execution seams

**Outcome.** Deliver public Petrus page-bounded replay/one-occurrence repair and
split Motus claim/effect-observed/terminal-recorded seams, pin the qualified
dependency, and expose them only through an initially thin
`readiness.runtime` contract test.

**Predecessor.** DS1.

**Rollback.** Revert the Petrus pin and target runtime adapter; old runtime
still uses its prior dependency.

**Validation.** Petrus unit/property tests, bounded History/occurrence tests,
accepted-effect response-loss cuts, one provider mutation attempt per step,
Hamsterdan integration against public defining modules, and dependency build.

### DS3 — Deliver the pure readiness workflow

**Outcome.** Implement the R1 vocabulary, nine concern loops, explicit gate
manifest, token registry, topology, correlation contract, typed review
evidence failure, blocked outcomes, and no `ready.facts` lane under
`workflow`. It runs on a real Petrus Engine with declaration-only Activities.

**Predecessor.** DS1; may proceed in parallel with DS2 because it imports only
defining modules.

**Rollback.** Remove `workflow` and its tests; no installed runtime references
it.

**Validation.** Behavioral loop portfolio; registry collision/missing-color
tests; AST purity/cycle/facade checks; real Engine observation→Activity→typed
terminal paths; wrong occurrence/operation/variant refusal; S3 and S10
correspondence scenarios.

### DS4 — Deliver the Hamsterdan simulation runtime

**Outcome.** Implement S9's runtime split across clock, scheduling, faults,
artifacts, replay, and runtime modules with the public Timeline/internal
stepper boundary, exact budgets, terminal budget failures, generation loss,
one artifact version, and exact replay.

**Predecessor.** DS1.

**Rollback.** Remove root simulation mechanics; no production path imports
them.

**Validation.** Generic independent-pair proof; offered/executed/idle crashes;
equal-time ordering; one-leaf rule; every budget boundary; strict artifact
decoder; byte refusal; exact failure replay; static semantic-independence
audit.

### DS5 — Deliver strict GitHub provider operations

**Outcome.** Implement provider-owned values, auth/config, bounded transport,
gateway, route/webhook custody, and lookup-first comment/rerun/Git operations.
No readiness classification enters the provider package.

**Predecessor.** DS1.

**Rollback.** Remove `hamsterdan2.github_app`; the old GitHub implementation
remains installed.

**Validation.** Behavioral auth/config/transport/effect tests; SDK client with
mock HTTP transport; bounded pagination/time/rate-limit classifications;
full-authority and content collision; accepted-hidden response loss; no second
POST in one step.

### DS6 — Deliver reconstructible agent execution

**Outcome.** Implement credential-free typed protocol and public terminal
codec, Pi adapter/workspace, and submit→accept→result/cancel→delivery lifecycle
with retained lookup-first recovery and bounded cleanup.

**Predecessor.** DS1.

**Rollback.** Remove `hamsterdan2.agents`; host route selection has not
switched.

**Validation.** Request/result/terminal codec tests; operation identity;
credential-key refusal; workspace safety; real Pi protocol correspondence;
runtime and delivery response-loss cuts; cancellation/timeout/cleanup; one
runtime start and one accepted delivery.

### DS7 — Deliver one-PR readiness execution

**Outcome.** Implement readiness ports, authority, four custody modules, eight
effect groups, bounded runtime, and one-PR application. Mutation receives the
delivered coding result as an injected capability; terminal correlation is
enforced before History; every S7 cut is public and reconstructible.

**Predecessor.** DS2–DS6.

**Rollback.** Remove readiness package and fresh readiness roots. No host or
production selector points at it.

**Validation.** Behavioral custody/effect tests; real Petrus runtime
integration; fresh SQLite/filesystem reopen tests; all S7 readiness crash cuts;
authority and route-revocation fences; one-attempt provider boundary; and
lookup-first Git/agent recovery.

### DS8 — Deliver trusted host custody and fair supervision

**Outcome.** Implement explicit composition, provider/agent resource custody,
instance catalog, lifecycle evidence, fair runnable sequence/lease, one-PR
turns, detached inspection, bounded startup/shutdown, qualification faults,
API, and operator package. Host contains no workflow names or Petrus runtime
objects.

**Predecessor.** DS6 and DS7; DS5 is reached through DS7 concrete effects.

**Rollback.** Remove target host/operator and their fresh stores; old service
entry point remains installed.

**Validation.** Two-PR fair scheduling; route revoke/reactivate generations;
delivery ack ordering; catalog and hint loss; lifecycle response loss;
selection lease repair; startup/close failure containment; credential and
inspection bounds; FastAPI lifespan; and CLI integration.

### DS9 — Compose whole Hamsterdan deterministically

**Outcome.** Implement the five owner-local simulation packages, then mount
those unchanged modules through `simulation.hamsterdan`. Prove each local
checker before adding only cross properties, including the S11 causal mutation
vertical and authority/work substitution sensitivities.

**Predecessor.** DS3–DS8.

**Rollback.** Remove simulation composition and local simulation packages;
production owners remain independently green.

**Validation.** Every local checker independently red/green; composition-only
cross counterexamples; response-lost generation-2 recovery; exact result A/B;
real workflow-work substitution; resource-union/budget failure; canonical
artifact encode/decode/exact replay.

### DS10 — Requalify the readiness journey portfolio

**Outcome.** Express the eleven accepted semantic journeys plus the causal
mutation journey through target production owners and composed simulation.
Every journey names user-visible behavior, authority, operation identity,
effect cardinality, crash cuts, and finite bounds.

**Predecessor.** DS7–DS9.

**Rollback.** Remove incomplete target acceptance scenarios; production is
still the old runtime and prior stories remain green.

**Validation.** Clean green; transient CI rerun; review findings; human
approval; draft→ready; stale base; conflict; reminder/timer; route revocation;
conversation mutation; Git ambiguity/recovery; closure; and the exact causal
delivered-result publication path. Generated schedules shrink and exactly
replay.

### DS11 — Prove real provider and process correspondence

**Outcome.** Qualify target seams against real GitHub transport/Git,
authenticated Pi where approved, filesystem/SQLite durability, OS process
death, lease expiry, and bounded concurrent multi-PR host execution. This is
correspondence evidence, not a second model.

**Predecessor.** DS8 and DS10.

**Rollback.** Remove correspondence harnesses and temporary target state;
never enable the target service. External mutations require separate explicit
approval and use dedicated bounded fixtures.

**Validation.** Mock-transport plus approved real-provider tests; real Git
object/ref CAS and first-parent lookup; Pi request/result/cleanup; kill at S7
cuts and restart from fresh process; SQLite transaction interruption;
selection-lease recovery; concurrent PR fairness; no duplicate physical
effect; secret scanning and retained-resource bounds.

### DS12 — Cut over and remove V5

**Outcome.** Stop the old service, preserve its state as rollback-only data,
rename `hamsterdan2` to the canonical package path and move `tests2` into the
canonical Python test paths in one change, retaining
`tests/amp_webhook_relay.test.ts`. Switch packaging/entry points/deployment to
the new runtime, update active docs and architecture decision, delete old
source/Python tests/configuration, and qualify fresh state. No new runtime
opens old state.

**Predecessor.** DS10 and DS11 accepted; explicit Navigator approval for the
shared deployment/state actions.

**Rollback.** Before the no-return checkpoint, restore the old package/image
and old state read-only snapshot; discard all fresh target roots. After a new
external effect is accepted by the target, rollback is an operator decision
that reconciles stable external operations, never a schema downgrade. Old
state deletion is a later separately approved action.

**Validation.** Forbidden-name/schema/path census; no old package import;
source/wheel install and CLI smoke; full gate; all target journeys;
fresh-state startup; bounded supervised launch; one approved real operation;
restart/reconciliation; active-doc and decision coherence; deployment image
identity and secret scan.

## Validation matrix

Every Delivery Story selects rows from this matrix. DS10–DS12 must cover the
matrix completely.

| Layer | Required evidence | Decisive boundary |
|---|---|---|
| Mechanical gate | strict Ruff/format, ty, seven ast-grep rules/fixtures, AST architecture/enum audit | only `src/hamsterdan2`/`tests2` block before cutover; no blanket suppressions |
| Behavioral unit | every workflow loop, readiness custody/effect group, GitHub operation family, agent lifecycle, host lifecycle/fairness | tests pin full state transitions and exact typed failure payloads, not private helpers |
| Petrus seam integration | bounded replay, one-occurrence repair, one coordinator action, split Motus phases | no private Petrus import or hidden multi-occurrence drain |
| Storage integration | fresh History, Dispatch, ingress, review, timer, catalog, route, runnable, webhook stores | transaction interruption/reopen; exact row/byte/page bounds; no old-schema reader |
| Provider integration | GitHubKit/httpx transport, Git object/ref publication, Pi protocol/workspace | one mutation attempt per step; complete lookup; credential isolation; cleanup |
| Local simulation | workflow, readiness, GitHub, agents, host independently | strict unknown-value refusal; meaningful local counterexample; bounds; exact replay |
| Composed simulation | unchanged five local modules under one Timeline | local reports unchanged; only cross checker owns cross-edge failures |
| Journey acceptance | eleven accepted semantic journeys plus causal mutation | user-visible outcome, authority, operation, effect count, crash/recovery, bound |
| Real correspondence | GitHub, Git, Pi, filesystem/SQLite, OS death, lease/concurrency | simulation claim is paired with one direct real-seam observation |
| Distribution/operation | source/wheel, entry points, config, inspection, deployment image | fresh install; secret scan; disabled-by-default target until separately approved launch |

### Required crash cuts

The matrix carries all S7 cuts, including:

- manifest/grant stage, entry History acceptance, fold, host posture, and inbox
  acknowledgement;
- bounded History page and one occurrence repair;
- Activity request, claim, effect observed, terminal record, and workflow
  projection;
- timer command, acknowledgement acceptance/mark, maturity claim,
  acceptance/mark, and runnable-hint repair;
- deferred wake and agent-route settlement;
- subject selection lease, instance open, readiness return, posture/route
  recording, requeue, and close;
- agent submit, acceptance, runtime terminal, cancellation, delivery, and
  lookup; and
- accepted Git/ref or comment effect with response loss before local terminal.

Every cut is tested by killing/discarding process-local state and reconstructing
from owned durable state. Callback injection inside an unbounded operation is
not accepted as evidence that the target exposes the cut.

### Required finite bounds

Every public command, step, observation, startup page, shutdown turn, and
artifact declares and tests relevant bounds for:

```text
input/output bytes; rows and History records examined; pages; external calls;
provider mutation attempts; attempts/retries; elapsed time/deadline; eligible
actions; owner steps; leaf calls; choice draws; active faults; generations;
journal entries; artifact bytes; pending Activities; loaded instances;
catalog/route/runnable rows; retained terminals; workspace/archive bytes.
```

Tests lower each meaningful limit and prove a typed refusal or replayable
terminal budget failure. “One logical operation” without bounded internal
reads is not sufficient.

## Capability Value and Delivery Stories proposal

Candidate Capability Value title:

> **Composable, reconstructible Hamsterdan**

Candidate value statement:

> Workflow, one-PR readiness execution, GitHub and agent implementations,
> trusted host supervision, and deterministic simulation run through typed,
> bounded ownership seams and compose while preserving current user behavior,
> independent PR progress, authority fencing, credential isolation,
> at-least-once effects, lookup-first recovery, explicit resource bounds, and
> exact deterministic replay.

Proposed Delivery Story titles, in dependency order:

1. Establish the replacement-tree gate.
2. Own bounded Petrus and Motus execution seams.
3. Deliver the pure readiness workflow.
4. Deliver the Hamsterdan simulation runtime.
5. Deliver strict GitHub provider operations.
6. Deliver reconstructible agent execution.
7. Deliver one-PR readiness execution.
8. Deliver trusted host custody and fair supervision.
9. Compose whole Hamsterdan deterministically.
10. Requalify the readiness journey portfolio.
11. Prove real provider and process correspondence.
12. Cut over and remove V5.

This is a roadmap proposal, not roadmap state. Promotion belongs to a separate
Navigator ruling after this candidate is accepted.

## Decision, debt, and documentation assessment

### Decisions

No unruled architecture or product decision blocks Delivery. The three S4/S6
questions are already ruled by R2, terminal-correlation ownership is fixed at
the readiness runtime admission boundary, and the public agent terminal codec
is owned by `agents.protocol`. Rate-limit reset metadata is omitted unless a
bounded scheduler test proves it necessary.

At promotion/cutover, one new architecture decision must supersede the current
V5-only/retired-state decision. The durable-explicit-topology principle and R3
Timeline/coroutine decision stay active. No decision record is created by S12
because the candidate has not yet been promoted.

### Debt

No debt is proposed. Bounded Petrus/Motus execution, strict provider calls,
agent result custody, host fairness, and real correspondence are required
Delivery inputs, not optional follow-ups. A debt record is warranted only if a
later accepted Delivery candidate deliberately defers one of these obligations
with an explicit consequence and recovery plan.

### Documentation

S12 updates only this experiment and the ES-010 index. Active project truth is
updated story-by-story when the corresponding implementation becomes true;
cutover performs the final README/briefing/AGENTS/development/deployment and
decision coherence pass. Dated evidence remains historical.

## Candidate-gate assessment

The Navigator accepted this candidate's Experience Report on 2026-08-27. The
candidate meets the first twelve ES-010 completion conditions and is ready for
the separate thirteenth gate, roadmap placement:

1. **Exact package ownership:** the source tree and 61-entry disposition ledger
   assign every current responsibility once.
2. **Pure workflow:** explicit allowed imports, defining-module seam, manifest,
   and token registry are fixed.
3. **One-PR readiness:** application, runtime, authority, custody, effects, and
   bounded cuts have one owner.
4. **Narrow host:** concrete composition, lifecycle evidence, fair scheduling,
   discovery, inspection, and shutdown are fixed without workflow knowledge.
5. **Provider/agent isolation:** implementation packages and credential custody
   have explicit forbidden edges and positive composition checks.
6. **Bounded execution:** R3 cuts, finite measures, and production dependency
   seams are Delivery obligations.
7. **Composable simulation:** one semantic-free runtime, five unchanged local
   modules, local checkers, and one cross owner are fixed by R4.
8. **Causal mutation evidence:** DS7/DS9/DS10 retain the exact S11 dependency and
   both result/work sensitivities.
9. **Blocking quality contract:** the engineering style contract tier (a) has exact owners and command
   integration; tier (b) remains review guidance.
10. **No compatibility architecture:** parallel build and one cutover contain
    no state/artifact reader, migration, selector, alias, or dual runtime.
11. **Green reversible delivery:** all twelve stories have predecessors,
    rollback boundaries, and focused checks while old production remains
    unchanged until DS12.
12. **Complete validation:** behavior, real seams, local/composed simulation,
    journeys, process/provider correspondence, distribution, crash cuts, and
    bounds are explicit.
13. **Pending promotion gate:** the Capability Value, Delivery Stories,
    decision supersession, debt result, and active-doc cleanup are ready.
    Candidate acceptance is recorded; roadmap placement is not inferred by
    S12.

No stop condition triggered: the candidate does not contradict R1–R4; no
current source module is unassigned or multiply assigned; no compatibility or
dual-runtime mechanism is required; each slice can remain green and reversible;
and no unruled architecture or product choice is needed.

## Exit assessment

S12 supplies one self-contained candidate from ruled architecture to Delivery.
An implementation session can choose the next story, read its outcome,
predecessors, owned files, production seams, rollback point, and validation
without rediscovering ownership or reopening R1–R4. The current production
tree remains authoritative until a separately accepted final cutover.

ES-010 remains `Thickening` after Navigator acceptance of this candidate and
pending a separate promotion ruling. No Delivery Story, roadmap item,
decision, debt, commit, push, deployment, or external effect is authorized by
this record.
