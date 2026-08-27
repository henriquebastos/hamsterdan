# CV20 replacement ledger

This document is the canonical placement and deletion contract for CV20. It
answers four questions without requiring the ES-010 exploration:

1. Which target module owns each responsibility?
2. Where does replacement validation live?
3. What happens to every current Python source and test file?
4. What old schema, artifact, name, configuration and documentation is removed
   at cutover?

“Replace” means implement accepted behavior under the new owner; it does not
mean copy the current file. “Split” means a current mixed-owner file contributes
behavior to more than one target. “Delete” means no target code path retains
that responsibility.

The package boundaries and current-file dispositions are fixed. Target module
and test paths are reviewed initial maps. An owning tracer may merge or split a
path under the deletion test when doing so produces a clearer API/responsibility,
provided this ledger and [the architecture](architecture.md) are updated before
implementation. No such change may alter package ownership or preserve a
compatibility lane.

## Target module deletion test

A target module exists only when deleting it would either duplicate a coherent
responsibility or mix that responsibility into a different owner. Package
initializers are the one structural exception: they establish package presence
and the no-facade policy while exporting nothing.

| Target module(s) | Responsibility that survives deletion |
|---|---|
| every `__init__.py` | package marker, policy docstring and explicit empty exports; never a facade |
| `workflow/values.py` | shared workflow value behavior and cross-loop aliases |
| `workflow/observations.py` | complete host/readiness-to-workflow admission language |
| `workflow/facts.py` | typed cross-loop mail without sibling implementation imports |
| `workflow/activities.py` | Activity work/terminal vocabulary and one manifest |
| `workflow/net/folding.py` | pure fold authoring and typed hydration shared by loops |
| `workflow/net/gating.py` | manifest-driven variant conversion and gate binding |
| `workflow/net/topology.py` | loop/gate composition, seed, token registry and build validation |
| `workflow/net/life.py` | lifecycle admission and incarnation baton |
| `workflow/net/ci.py` | exact-head CI state and check facts |
| `workflow/net/escalation.py` | bounded rerun/repair escalation decisions |
| `workflow/net/review.py` | review rounds, findings and typed inability decisions |
| `workflow/net/mutation.py` | mutation request/settlement and provisional-head facts |
| `workflow/net/conversation.py` | human-intent folds and workflow requests |
| `workflow/net/dashboard.py` | open-dashboard projection and self-healing state |
| `workflow/net/reminders.py` | reminder cycle and workflow timer protocol |
| `workflow/net/readiness.py` | readiness projection, fault facts and announcement decision |
| each owner `simulation/module.py` | mounts the real owner and owns strict commands, faults, retained modeled state and gauges |
| each owner `simulation/checker.py` | independent derivation outside the implementation it judges |
| `readiness/ports.py` | complete typed one-PR capability seam without one file per call |
| `readiness/authority.py` | one composition of durable grant, fresh provider and fresh host evidence |
| `readiness/application.py` | sequencing among admission, workflow, Activity, timer, wake and route cuts |
| `readiness/runtime.py` | Petrus construction, History/occurrence recovery, Dispatch/Worker cuts and terminal correlation |
| `readiness/custody/instance.py` | immutable subject/root binding |
| `readiness/custody/ingress.py` | atomic manifest/grant identity, order and reconstruction |
| `readiness/custody/review.py` | exact request/attempt retention |
| `readiness/custody/timers.py` | ordered command, acknowledgement, maturity and History-rebuild protocol |
| `readiness/effects/evidence.py` | provider truth to workflow-observation normalization |
| `readiness/effects/agents.py` | credential-free conversation/review/coding calls |
| `readiness/effects/publication.py` | shared comment ledger with operation-specific outcomes |
| `readiness/effects/rerun.py` | final-evidence rerun cut and ambiguity policy |
| `readiness/effects/review.py` | request recovery, authority cancellation and review-terminal classification |
| `readiness/effects/mutation.py` | one Activity coordinating injected coding and Git publication |
| `readiness/effects/git.py` | patch admission, Git proof, lookup, trailers, objects and exact ref CAS |
| `github_app/models.py` | frozen provider meaning independent of SDK shapes |
| `github_app/config.py` | strict provider portfolio and credential input/redaction |
| `github_app/auth.py` | App/installation authentication and token/client lifetime |
| `github_app/transport.py` | bounded SDK/HTTP wire behavior and response metadata |
| `github_app/gateway.py` | normalized reads and raw Git object/ref operations |
| `github_app/effects.py` | reusable provider lookup-first publication/rerun mechanisms |
| `github_app/routing.py` | typed installation/repository route persistence and generation mechanism; host owns active binding custody and resource lifetime |
| `github_app/webhooks.py` | signature verification, normalization and typed durable inbox mechanism; host owns admission/acknowledgement custody and resource lifetime |
| `agents/protocol.py` | credential-free request/result/terminal contracts and validation |
| `agents/pi.py` | Pi prompts, operation identity, result validation and bounded calls |
| `agents/pi_workspace.py` | checkout/archive/patch safety without GitHub credentials |
| `host/clock.py` | sole production wall-clock/sleep owner |
| `host/composition.py` | only concrete readiness/GitHub/agent construction root |
| `host/service.py` | portfolio startup, bounded multi-instance turns, isolation and shutdown |
| `host/api.py` | FastAPI/lifespan adaptation |
| `host/__main__.py` | process CLI and construction edge |
| `host/instances.py` | process discovery independent of readiness internals |
| `host/inspection.py` | bounded detached process/readiness aggregation |
| `host/runnable.py` | reconstructible wake hints and durable fair sequence/lease |
| `host/qualification.py` | disabled one-shot production correspondence faults |
| `host/agents/routing.py` | immutable operation-to-composition binding and activation |
| `host/agents/pi.py` | Pi installation, connection, runtime, secret and erasure custody |
| `operator/__main__.py` | human JSON/terminal behavior |
| `operator/qualification.py` | atomic setup transaction and result vocabulary |
| `simulation/runtime.py` | Timeline, generations, generic commands/observations, budgets and internal stepper coordination |
| `simulation/clock.py` | deterministic integer logical time |
| `simulation/scheduling.py` | cross-module eligible-action ordering and choice streams |
| `simulation/faults.py` | generic occurrence matching |
| `simulation/artifacts.py` | strict canonical artifact schema, encoding and byte refusal |
| `simulation/replay.py` | expanded-operation replay and exact comparison |
| `simulation/hamsterdan.py` | five-module adapters and cross-module checkers |

## Tracer ownership of the initial map

This table assigns first implementation responsibility. Later tracers may
extend an existing owner only from a new real call site.

| Tracer | First implementation responsibility |
|---|---|
| DS1 | strict gate; minimum workflow/readiness/host spine; one-PR binding; core Timeline/artifact/replay; first local/root modules |
| DS2 | provider webhook/model/route input; host inbox custody; readiness ingress/evidence; `HeadSeen` lifecycle fold |
| DS3 | workflow facts/Activity manifest/folding/gating/topology and dashboard request; pending-Activity runtime evidence |
| DS4 | provider auth/transport/gateway/effects; readiness publication adapter; split effect cuts and terminal admission |
| DS5 | agents protocol/Pi/workspace; host agent custody/evidence; complete readiness authority claim and findings fence; readiness review custody/effect; workflow review round |
| DS6 | conversation/mutation folds; coding protocol; readiness mutation/Git; provider raw Git operations |
| DS7 | CI/escalation folds; provider check evidence; readiness/provider rerun operation |
| DS8 | workflow reminders/deferred values; readiness timer custody; host clock/deadline wake |
| DS9 | complete lifecycle/readiness folds; remaining authority-policy matrix; host/provider route-generation movement; blocked/moved mappings |
| DS10 | host catalog/runnable/service/API/CLI/inspection/qualification and operator surfaces |
| DS11 | acceptance journeys/recovery/correspondence, generated schedules, qualification/distribution evidence |
| DS12 | canonical rename, old implementation deletion, gate/config/deployment/doc promotion and fresh-state cutover |

Every DS1–DS11 row includes its owner-local/root simulation, checker,
correspondence and resource evidence. Those are not deferred modules owned by a
later integration story.

## Reviewed initial replacement Python test map

Tests are grouped by behavior owner, not mirrored one-to-one from production
files. Scenario classes and local DSL helpers stay in the behavior file until
independent reuse earns another module.

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

The map is grouped by behavior owner, not a test-count target or immutable file
inventory. A tracer may add scenarios, merge files whose separation adds no
responsibility, or split a file when independently reusable test vocabulary
earns a new owner. The deletion test and Navigator review update this ledger
before implementation; package/behavior ownership does not move silently.

`tests/amp_webhook_relay.test.ts` remains the maintained relay gate during
construction and after cutover. It is not part of `tests2` or the Python
disposition census.

## Replacement quality gate

DS1 creates and runs the isolated gate over the real modules it admits:

```text
quality/hamsterdan2/ruff.toml
quality/hamsterdan2/sgconfig.yml
quality/hamsterdan2/ast-grep/*.yml
quality/hamsterdan2/ast-grep-tests/
tests2/test_architecture.py
scripts/check integration
```

The isolated Ruff configuration selects `ALL`, uses line length 120 and Ruff
formatting, and has only this justified veto list:

```text
E731 E501 D ARG RUF012 COM812 EM TRY003
PLR0904 PLR0911 PLR0912 PLR0913 PLR0915
```

Production keeps `ANN`, `N`, `ERA`, `PT`, `S`, `RUF100`, `PLR2004`, `T20`,
`FIX`, `TD` and `FBT`. `tests2` alone ignores `ANN`, `SLF`, `S101`, `S105`,
`S106` and `PLR2004`. The command rim receives the path-scoped `T20` exception.
Isort is case-sensitive, sorts within sections, leaves two lines after imports,
uses no import banners, and puts test machinery in the final ruled `testing`
section.

Ruff `C901` uses maximum complexity 4. One cohesive parser, state machine,
workflow fold or lifecycle operation may have a justified per-function
suppression. Global/file-wide complexity suppression is forbidden.

The seven blocking ast-grep rules are:

1. no banner comments in source/tests;
2. no underscore methods in source except dunders and justified true internals;
3. no underscore dataclass fields in source;
4. direct clock/sleep use only in `host/clock.py`;
5. no ad hoc mixins;
6. patch paths are constants in tests; and
7. no function-local imports in source.

`tests2/test_architecture.py` owns cycle/relative-import resolution, forbidden
and positive edges, empty initializers, defining-module imports, external
library custody, unique readiness runtime custody, manifest/loop/gate/token
census, forbidden generation/compatibility names and registry-driven enum
privacy.

Positive checks apply when their owning tracer admits the corresponding real
composition. DS1 does not create an empty final skeleton or construction
placeholder merely to satisfy a future edge. Every later tracer updates the
positive census in the same change that introduces the real edge.

The replacement gate runs from `scripts/check quick`; `full` and `release`
inherit it. At DS12 the isolated config becomes the repository default and the
temporary path qualifier disappears.

## Current source disposition (61/61)

<!-- source-disposition:start -->
| Current source | Replacement disposition |
|---|---|
| `src/hamsterdan/__init__.py` | Replace with empty-policy `src/hamsterdan2/__init__.py`; no facade |
| `src/hamsterdan/agents/__init__.py` | Delete re-exports; replace with empty `agents/__init__.py` |
| `src/hamsterdan/agents/pi.py` | Replace in `agents/pi.py`; retain credential-free Pi adaptation and prompt validation |
| `src/hamsterdan/agents/protocol.py` | Replace in `agents/protocol.py`; remove `ChangeResult`/`RepairResult` aliases and add public typed result/cancellation/timeout/cleanup terminal encoding |
| `src/hamsterdan/contracts/__init__.py` | Delete; target has no neutral contracts package |
| `src/hamsterdan/contracts/readiness.py` | Split `WorkflowModel` to `workflow/values.py` and `AdmittedConversation` to `github_app/models.py`; delete retired workflow/qualification values |
| `src/hamsterdan/contracts/readiness_v5.py` | Split by value owner into workflow values/observations/facts/activities and loop-private values; no compatibility module |
| `src/hamsterdan/github_app/__init__.py` | Replace with empty `github_app/__init__.py` |
| `src/hamsterdan/github_app/auth.py` | Replace in `github_app/auth.py` |
| `src/hamsterdan/github_app/config.py` | Replace in `github_app/config.py` |
| `src/hamsterdan/github_app/effects.py` | Replace provider comment/rerun mechanisms in `github_app/effects.py`; readiness classifications stay in readiness effects |
| `src/hamsterdan/github_app/gateway.py` | Replace in `github_app/gateway.py` |
| `src/hamsterdan/github_app/models.py` | Replace in `github_app/models.py`, adding provider-owned admitted conversation |
| `src/hamsterdan/github_app/routing.py` | Replace in `github_app/routing.py` with a fresh schema |
| `src/hamsterdan/github_app/transport.py` | Replace in `github_app/transport.py`; expose bounded metadata required by provider policy |
| `src/hamsterdan/github_app/webhooks.py` | Replace provider ingress/inbox implementation; host owns lifetime and disposition |
| `src/hamsterdan/host/__init__.py` | Delete re-exports; replace with empty `host/__init__.py` |
| `src/hamsterdan/host/__main__.py` | Split process CLI/composition to `host/__main__.py` and human commands to `operator/__main__.py` |
| `src/hamsterdan/host/agenticus.py` | Split route custody to `host/agents/routing.py` and routed calls to `readiness/effects/agents.py`; delete History/result-name interpretation and legacy migration |
| `src/hamsterdan/host/api.py` | Replace in `host/api.py` |
| `src/hamsterdan/host/binding.py` | Split subject binding to readiness instance custody and discovery to host instances; delete topology identity/legacy reads/preflight |
| `src/hamsterdan/host/git_publish.py` | Replace in `readiness/effects/git.py` |
| `src/hamsterdan/host/pi_a2.py` | Replace trusted Pi runtime/secret custody in `host/agents/pi.py` |
| `src/hamsterdan/host/pi_workspace.py` | Replace credential-free workspace execution in `agents/pi_workspace.py` |
| `src/hamsterdan/host/protocol.py` | Delete; replace with readiness-owned construction/lifecycle values consumed by host |
| `src/hamsterdan/host/publication_qualification.py` | Move atomic setup to `operator/qualification.py`; delete historical qualification value |
| `src/hamsterdan/host/runnable.py` | Replace in `host/runnable.py` with durable fair sequence, leases and tail requeue |
| `src/hamsterdan/host/service.py` | Split concrete construction, discovery, inspection and qualification; retain bounded supervision in `host/service.py` |
| `src/hamsterdan/host/testing/__init__.py` | Delete; target simulations have empty owned initializers |
| `src/hamsterdan/host/testing/_readiness_contract.py` | Replace useful vocabularies/bounds in owner-local simulations; delete Petrus profile identity |
| `src/hamsterdan/host/testing/_readiness_provider.py` | Split deterministic truth into GitHub, agents and readiness local simulations |
| `src/hamsterdan/host/testing/readiness_coverage.py` | Replace semantic coverage as acceptance assertions; delete V5/Petrus profile accounting |
| `src/hamsterdan/host/testing/readiness_world.py` | Split mechanics to root simulation, behavior to five local modules and cross composition to `simulation/hamsterdan.py` |
| `src/hamsterdan/host/v5/__init__.py` | Delete; no topology package/facade |
| `src/hamsterdan/host/v5/application.py` | Split one-PR sequencing, concrete construction, conversations and runtime/custody to their owners |
| `src/hamsterdan/host/v5/claim.py` | Replace authority value/capability in readiness ports/authority |
| `src/hamsterdan/host/v5/gates.py` | Replace operation-specific publication classifications in `readiness/effects/publication.py` |
| `src/hamsterdan/host/v5/ingress.py` | Split projection, ingress custody and authority; delete provider inbox-table access and migrations |
| `src/hamsterdan/host/v5/mutation.py` | Replace orchestration in `readiness/effects/mutation.py`; coding/Git capabilities stay separate |
| `src/hamsterdan/host/v5/rerun.py` | Replace in `readiness/effects/rerun.py` |
| `src/hamsterdan/host/v5/review.py` | Split request custody and typed review execution; use a fresh schema |
| `src/hamsterdan/host/v5/runtime.py` | Replace in `readiness/runtime.py` with bounded replay/repair and split cuts; remove V5 names/hard-coded gates |
| `src/hamsterdan/host/v5/timers.py` | Replace in readiness timer custody with fresh schema and bounded reconstruction |
| `src/hamsterdan/operator.py` | Split command rim to `operator/__main__.py` and setup transaction to `operator/qualification.py` |
| `src/hamsterdan/readiness/__init__.py` | Replace with empty `readiness/__init__.py` |
| `src/hamsterdan/readiness/net_v5/__init__.py` | Delete facade; target `workflow/net/__init__.py` is empty |
| `src/hamsterdan/readiness/net_v5/ci.py` | Replace in `workflow/net/ci.py` |
| `src/hamsterdan/readiness/net_v5/conversation.py` | Replace in `workflow/net/conversation.py` |
| `src/hamsterdan/readiness/net_v5/dashboard.py` | Replace in `workflow/net/dashboard.py` |
| `src/hamsterdan/readiness/net_v5/esc.py` | Replace in `workflow/net/escalation.py` |
| `src/hamsterdan/readiness/net_v5/folding.py` | Replace in `workflow/net/folding.py`; hydrate requested types rather than module globals |
| `src/hamsterdan/readiness/net_v5/gating.py` | Replace manifest-driven binding/conversion; readiness runtime owns terminal admission |
| `src/hamsterdan/readiness/net_v5/life.py` | Replace in `workflow/net/life.py` |
| `src/hamsterdan/readiness/net_v5/mutation.py` | Replace in `workflow/net/mutation.py` |
| `src/hamsterdan/readiness/net_v5/readiness.py` | Replace in `workflow/net/readiness.py`; delete `ready.facts` and migration folds/arcs |
| `src/hamsterdan/readiness/net_v5/reminders.py` | Replace in `workflow/net/reminders.py` |
| `src/hamsterdan/readiness/net_v5/review.py` | Replace in `workflow/net/review.py`, including typed provider-evidence inability |
| `src/hamsterdan/readiness/net_v5/topology.py` | Replace as `build_net`, seed, gate aggregation, explicit token registry and build validation |
| `src/hamsterdan/readiness/payloads.py` | Move useful converter behavior to workflow gating; delete simulation-only module |
| `src/hamsterdan/testing/__init__.py` | Delete |
| `src/hamsterdan/testing/readiness.py` | Replace independent expectations in local checkers/journeys; no second whole-readiness model |
<!-- source-disposition:end -->

This table assigns source responsibility, not lines. A mixed-owner current file
must be reimplemented under final owners; copying it first would make an
architecture-invalid intermediate tree. Target paths named here refer to the
reviewed initial map and follow any pre-implementation merge/split ruling in
this ledger.

## Current Python test disposition (46/46)

<!-- test-disposition:start -->
| Current test | Delivery disposition |
|---|---|
| `tests/fixtures/skip_probe.py` | Delete; target feedback tests create the policy probe in a temporary admitted tree |
| `tests/integration/host/test_git_publish.py` | Re-express Git lookup/object/ref behavior in provider and readiness mutation integration |
| `tests/integration/host/test_pi_a2_factory.py` | Re-express trusted Pi construction in agent execution integration |
| `tests/integration/host/test_pi_workspace.py` | Re-express workspace safety in agent behavioral/integration tests |
| `tests/integration/host/test_qualification_setup_local.py` | Re-express atomic setup in operator behavior tests |
| `tests/integration/host/test_readiness_scenarios.py` | Re-express user behavior in `tests2/acceptance/test_journeys.py` |
| `tests/integration/host/test_service.py` | Re-express startup, custody, fairness, restart and shutdown in host lifecycle integration |
| `tests/integration/testing/test_readiness_campaign.py` | Replace with generated schedules in simulation/acceptance recovery; no profile compatibility |
| `tests/integration/testing/test_readiness_coverage.py` | Replace semantic coverage with journey assertions over Hamsterdan artifacts |
| `tests/integration/testing/test_readiness_world.py` | Split into local simulations, composition, recovery acceptance and correspondence |
| `tests/test_architecture.py` | Replace with strict target DAG, positive composition, defining-module, custody, forbidden-name and enum audits |
| `tests/test_check_command.py` | Replace target gate invocation/path policy in `tests2/test_feedback.py` |
| `tests/test_distribution.py` | Replace source/wheel/entry-point contracts in `tests2/test_distribution.py` |
| `tests/test_pytest_policy.py` | Replace target collection/skip policy in `tests2/test_feedback.py` |
| `tests/unit/agents/test_pi.py` | Re-express Pi prompt, identity, result and bounded execution behavior |
| `tests/unit/agents/test_protocol.py` | Re-express strict request/result and durable terminal codec |
| `tests/unit/github_app/test_app_foundation.py` | Re-express provider config/auth/routing/webhook foundation |
| `tests/unit/github_app/test_github.py` | Re-express transport, gateway, lookup-first effects and bounds |
| `tests/unit/host/test_agenticus.py` | Split process route custody and routed readiness calls; delete History/result-name parsing |
| `tests/unit/host/test_binding.py` | Re-express subject binding/catalog; delete topology/legacy compatibility |
| `tests/unit/host/test_host_architecture.py` | Replace with target host boundaries and positive composition audit |
| `tests/unit/host/test_pi_a2.py` | Re-express Pi secret/runtime custody in host agent tests |
| `tests/unit/host/test_publication_qualification.py` | Re-express atomic operator setup; delete historical qualification type tests |
| `tests/unit/host/test_runnable.py` | Re-express wake coalescing and durable fair sequence/lease/tail behavior |
| `tests/unit/host/test_v5_gates.py` | Re-express five operation-specific publication effects without V5 names |
| `tests/unit/host/test_v5_ingress.py` | Split admission/custody/application/runtime/host-ack crash behavior; delete old schema/drain cases |
| `tests/unit/host/test_v5_mutation.py` | Re-express injected coding-to-Git mutation, authority, result sensitivity and terminals |
| `tests/unit/host/test_v5_rerun.py` | Re-express final-evidence rerun behavior |
| `tests/unit/host/test_v5_review.py` | Split exact request custody and typed review execution; delete schema migration cases |
| `tests/unit/host/test_v5_timers.py` | Re-express fresh timer protocol, ordering, bounded rebuild and crash cuts |
| `tests/unit/readiness/net_v5/harness.py` | Delete shared implementation-shaped harness; behavior files keep local DSLs |
| `tests/unit/readiness/net_v5/test_ci_loop.py` | Re-express CI behavior under workflow tests |
| `tests/unit/readiness/net_v5/test_conversation_loop.py` | Re-express conversation under workflow mutation/conversation tests |
| `tests/unit/readiness/net_v5/test_dashboard_loop.py` | Re-express dashboard behavior and event value |
| `tests/unit/readiness/net_v5/test_escalation_loop.py` | Re-express escalation under CI/escalation tests |
| `tests/unit/readiness/net_v5/test_gating.py` | Re-express manifest binding, variant routing and terminal correlation |
| `tests/unit/readiness/net_v5/test_inline_recovery.py` | Split real workflow recovery into workflow-runtime/readiness integration |
| `tests/unit/readiness/net_v5/test_lifecycle_loop.py` | Re-express lifecycle; delete ready-facts migration/facade/V5 census assertions |
| `tests/unit/readiness/net_v5/test_mutation_loop.py` | Re-express mutation behavior and instruction propagation |
| `tests/unit/readiness/net_v5/test_readiness_loop.py` | Re-express readiness projection/announcement; delete legacy migration behavior |
| `tests/unit/readiness/net_v5/test_reminders_loop.py` | Re-express timer/reminder behavior under dashboard/reminders tests |
| `tests/unit/readiness/net_v5/test_review_loop.py` | Re-express review rounds, findings and typed evidence inability |
| `tests/unit/readiness/test_payloads.py` | Fold converter contracts into vocabulary/gating behavior |
| `tests/unit/test_operator.py` | Re-express human command and qualification behavior under operator tests |
| `tests/unit/test_orb_setup.py` | Preserve deployment/setup behavior against target command/package; activation stays separately approved |
| `tests/unit/testing/test_readiness_model.py` | Replace independent properties in local checkers/journeys; delete second whole-readiness model |
<!-- test-disposition:end -->

## Fresh durable stores

Replacement roots use new names and schemas. No replacement reader opens,
modifies or migrates an old root.

| Current state family | Replacement disposition |
|---|---|
| V5 ingress manifests, grants and reconciliation manifests | fresh readiness ingress custody |
| V5 timer metadata, operations, timers and indexes | fresh timer custody |
| V5 review requests and in-place migration | fresh review custody |
| topology-labelled subject binding | one immutable subject/root binding |
| legacy-migrating agent routes | fresh host operation-route store |
| runnable rows without durable fairness sequence/lease | fresh fair runnable store |
| filesystem History discovery | host instance catalog |
| old Dispatch/History file and queue identities | fresh readiness-owned names |
| current webhook/routing stores | replace only where target bounded contracts differ; never add old-schema readers |

Old state is retained only as bounded rollback custody after DS12 approval. It
is never an available runtime or compatibility contract. Deletion is a later,
separately approved operator action.

## Removed names, schemas and artifacts

DS12 removes from active code and state:

- `host/v5`, `readiness/net_v5` and `contracts`;
- topology descriptors/selectors and old binding/preflight/Activity resolver;
- `ready.facts`, nine migration transitions/folds, ordering arcs and CEL-only
  compatibility;
- `ChangeResult`/`RepairResult` aliases and retired qualification values;
- `pr_v5`, `build_net_v5`, every `V5*` type and topology-only `v5-`/`v5:`
  operation prefix;
- old ingress, timer, review, binding, route, runnable, catalog, Dispatch and
  History schemas/identities;
- Petrus DST profile/checker identities, V1–V4 compatibility, V5 resource keys,
  simulation profile names and current World operations; and
- old Python tests after their required behavior passes in `tests2`.

Externally accepted operation meanings required for provider lookup and
user-visible idempotency remain, but topology labels are removed from those
identities.

The replacement artifact is only:

```text
family: hamsterdan-simulation
version: 1
```

It has no old profile identity, version registry, migration field or
compatibility reader.

## Cutover file and documentation cleanup

DS12 renames:

```text
src/hamsterdan2 -> src/hamsterdan
tests2 behavioral/integration/simulation/acceptance -> canonical Python tests
```

It retains `tests/amp_webhook_relay.test.ts` at its existing path and changes
the isolated target quality configuration into the repository default.

The cutover updates current truth in:

- `README.md`;
- `AGENTS.md` architecture contract;
- `docs/project/briefing.md`;
- `docs/process/development-guide.md` and active engineering gate status;
- current deployment/operator instructions and package/service entry points;
- `pyproject.toml`, `scripts/check`, ast-grep configuration and architecture
  tests;
- active project/product/process/decision owners; and
- any current command or inspection documentation that names old paths, state,
  schemas or topology.

Dated CV17/CV18/ES7/ES8/ES9/ES10 records, decisions and worklogs remain
historical evidence. The DS12 cutover decision supersedes the current V5-only
operational decision. Active documents do not preserve V5 or Hamsterdan2 as a
runtime concept merely because history still contains those words.

## Ledger verification

Mechanical coherence checks must prove:

1. every current `src/hamsterdan/**/*.py` path appears exactly once between the
   source markers;
2. every current `tests/**/*.py` path appears exactly once between the test
   markers;
3. the reviewed initial and accepted actual source/test maps contain no
   duplicate path;
4. every accepted actual target module passes the deletion test and has one
   responsibility owner;
5. every admitted path is owned by its tracer or explicitly listed
   quality/dependency/cutover scope, with no future-only placeholder;
6. every DS1–DS11 tracer has local/root simulation, checker, bounds and
   correspondence disposition alongside production responsibility; and
7. DS12's forbidden-name/schema/path census reaches zero in active owners.
