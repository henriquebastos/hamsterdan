# CV20 delivery sequence

This document is the canonical build order for CV20. It explains what exists
after each Delivery Story, what the next story may rely on, and which evidence
must remain green. All twelve stories are `Planned`; this sequence does not pull
DS1 or authorize implementation, external effects, deployment or cutover.

## Sequence rules

1. A Delivery Story expands into bounded User or Technical Stories before code
   changes begin.
2. Its Plan Checkpoint resolves the DS-review items listed in
   [the API contract](api-contracts.md).
3. Every child story leaves the current V5 runtime and the replacement tree
   green. Partial ownership moves that violate the final import graph are not
   accepted as intermediate states.
4. A story may depend only on accepted predecessors listed below. Parallel
   stories do not invent temporary cross-imports.
5. The replacement remains non-selectable through DS11. Tests may import it;
   configuration, entry points, service launch and deployed state do not.
6. Rollback means remove/revert the replacement story while current V5 keeps
   operating. It never means convert replacement state into V5.
7. Shared/external actions retain separate approval: dependency publication,
   provider mutation, credential use, process launch/kill, deployment, release,
   state retention/deletion, commit and push are not inferred from a story.

## Dependency graph

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

DS2–DS6 may proceed independently after DS1. DS7 is the first replacement
story that joins workflow with provider and agent capabilities. DS8 constructs
the real process but leaves it disabled. DS9 mounts production owners under
simulation. DS10 qualifies complete behavior. DS11 proves real-seam
correspondence. DS12 alone changes the installed application.

## State after each story

| Story accepted | New durable project state | Still deliberately absent |
|---|---|---|
| DS1 | exact replacement/test skeleton; blocking target gate; construction placeholders | domain behavior, target runtime, selectable service |
| DS2 | public bounded Petrus replay/repair and Motus claim/effect/terminal seams; pinned qualified dependency | workflow and readiness application |
| DS3 | pure real workflow topology, vocabulary, manifest and behavioral tests | Engine lifecycle, external implementations |
| DS4 | semantic-free Timeline, generation/fault/budget/artifact/replay mechanics | owner-local modules and domain scenarios |
| DS5 | strict GitHub App/provider implementation, route/webhook mechanisms and lookup-first operations | durable host custody, readiness classification or enabled target route |
| DS6 | typed agent protocol, Pi/workspace adapter and reconstructible execution lifecycle | host route/secret composition and readiness use |
| DS7 | one-PR readiness application using injected workflow/provider/agent capabilities and fresh stores | multi-PR process supervision and selectable service |
| DS8 | complete disabled host/operator composition with catalog, fair scheduling, inspection and bounded lifecycle | deterministic whole-system proof and production activation |
| DS9 | five owner-local simulations and one causal whole-Hamsterdan composition | full journey portfolio and real-seam qualification |
| DS10 | twelve accepted journeys through replacement owners with generated/replayable recovery | approved real-provider/process correspondence and cutover |
| DS11 | direct provider, Git, Pi, durability, process-death and concurrency evidence | installed replacement or state switch |
| DS12 | one canonical Hamsterdan package/runtime on fresh state; old implementation removed | active V5/Hamsterdan2 names, readers, selectors or compatibility |

## Story handoffs

### DS1 to every implementation story

DS1 supplies:

- the exact `src/hamsterdan2` and `tests2` package markers;
- isolated strict Ruff and formatter configuration;
- seven verified ast-grep rules and fixtures;
- semantic AST architecture/enum auditing;
- positive construction assertions; and
- `scripts/check` integration.

Every later story extends this admitted tree. It may not weaken a gate to make
new code pass. A justified per-site exception stays visible at the exact site
and is covered by the appropriate rule/test.

### DS2 to DS7

DS2 supplies public dependency seams only:

```text
page-bounded History replay
one-occurrence repair
Activity attempt claim
effect observed
terminal recorded
```

DS7 wraps those defining/public APIs in `readiness.runtime`. If Hamsterdan must
inspect or patch private Petrus runtime state, DS2 has not met its exit and DS7
does not begin.

### DS3 to DS7 and DS9

DS3 supplies:

```text
build_net
seed_marking
TOKENS
MANIFEST
wire_gates
workflow observations/facts/work/terminals
```

DS7 binds capabilities to the manifest and executes the Net. DS9's workflow
simulation mounts that same production package. Neither duplicates transition
folds or creates a simulation-only workflow.

### DS4 to DS9 and DS10

DS4 supplies the exact public `Timeline`, structural module contract, strict
artifact and replay. It contains no GitHub, agent, readiness, workflow or host
meaning. DS9 supplies owner modules; DS10 supplies semantic journeys. Neither
adds a second scheduler or artifact family.

### DS5 and DS6 to DS7/DS8

DS5 supplies provider implementations and provider-owned values. DS6 supplies
credential-free agent implementations and typed terminal lookup. DS7 defines
readiness-owned capability boundaries over them. DS8 is the only owner that
constructs those concrete implementations with credentials and process
resources.

The concrete import route is:

```text
host.composition
  -> github_app concrete constructors
  -> agents/host agent-runtime constructors
  -> readiness effect adapters
  -> readiness lifecycle construction
```

Readiness core never imports concrete construction, and GitHub/agents never
import one another.

### DS7 to DS8

DS7 supplies a one-PR lifecycle with bounded admit/progress/settle/inspect/close
semantics and detached `StepResult`. DS8 supplies host lifecycle evidence and
calls that lifecycle once per selected subject turn.

The acknowledgement rule is fixed:

```text
host retains delivery
  -> readiness returns accepted/already accepted for exact delivery
  -> host acknowledges delivery
  -> host persists posture and route settlements
```

### DS3–DS8 to DS9

Each owner is production-complete enough to mount directly. DS9 adds exactly:

- one local simulation module and checker per owner;
- strict owner-local commands, observations, faults and gauges;
- root adapters that join local modules; and
- cross checkers that compare edge-local evidence.

DS9 does not implement a second domain model. A local module used in root
composition is the same module used in standalone local tests.

### DS9 to DS10

DS9 supplies deterministic causal composition, failures, shrinking inputs,
resource accounting and exact replay. DS10 uses them to express product
journeys. A journey names the visible outcome, authority, operation identity,
physical effect cardinality, crash/recovery cuts and finite limits.

### DS10 to DS11

DS10 states what behavior must hold. DS11 pairs selected simulation claims with
real provider/process evidence. DS11 does not change the model to match a
convenient harness. A mismatch returns to the production owner or simulation
contract that is wrong.

### DS10 and DS11 to DS12

DS12 begins only after behavior and correspondence are accepted. It requires a
new cutover decision and explicit approval for shared deployment/state actions.
The current V5-only decision remains active before that point.

## Story sequence

### DS1 — Establish the replacement-tree gate

Create the complete empty source/test skeleton and blocking quality gate. Use
explicit construction placeholders so positive architecture checks are active
before real modules exist. The old tree receives no blanket formatting or
suppression work.

Exit: every required positive/negative rule has a fixture, `quick` runs the
target gate, and the empty replacement is distributively invisible.

### DS2 — Own bounded Petrus and Motus execution seams

Implement and qualify public dependency APIs for bounded History replay,
one-occurrence repair and split Activity execution positions. Pin the qualified
dependency and expose a thin readiness-runtime contract test.

Exit: one step can attempt at most one provider mutation, response-loss cuts
are observable, and Hamsterdan imports no private dependency state.

### DS3 — Deliver the pure readiness workflow

Implement workflow values, observations, facts, Activity manifest, nine loops,
token registry, topology and declaration-only real-Engine tests. Remove the
`ready.facts` compatibility lane from the replacement design rather than
porting it.

Exit: observations derive exact typed Activity work, exact terminals fold by
original occurrence/correlation, and static purity/registry checks pass.

### DS4 — Deliver the Hamsterdan simulation runtime

Implement logical clock, deterministic scheduling, occurrence faults,
generation loss, one-leaf stepper coordination, global/module budgets, strict
journal, one artifact version and exact replay.

Exit: independent generic modules interleave and recover exactly; every budget
failure terminates, discards process-local frames and remains replayable.

### DS5 — Deliver strict GitHub provider operations

Implement provider models, App auth/config, bounded transport/gateway,
route/webhook verification and persistence mechanisms, and lookup-first
comment/rerun/Git operations. Host retains durable route/inbox custody. Provider
operations report observations; they do not return workflow decisions.

Exit: complete bounded lookup precedes every mutation, a step makes at most one
mutation attempt, and accepted-hidden effects recover without duplication.

### DS6 — Deliver reconstructible agent execution

Implement request/result/terminal codecs, Pi/workspace adaptation and durable
submit→accept→result/cancel→delivery lifecycle with bounded lookup and cleanup.

Exit: response loss cannot create a second runtime start or accepted delivery,
and no persisted or transmitted agent value contains GitHub credentials.

### DS7 — Deliver one-PR readiness execution

Implement readiness ports, authority, custody, effect adapters, bounded Petrus
runtime and one-PR application. Enforce terminal correlation before History.
Pass the exact delivered coding result through mutation publication.

Exit: every readiness cut reconstructs from fresh state, route revocation
produces workflow-declared outcomes in readiness, and ambiguous effects recover
lookup-first.

### DS8 — Deliver trusted host custody and fair supervision

Implement concrete composition, provider/agent resource lifetime, catalog,
lifecycle evidence, fair runnable sequence/lease, detached inspection, bounded
startup/shutdown, qualification controls, API, process CLI and operator package.

Exit: two already-due PRs progress fairly, credentials remain in trusted
custody, host uses no workflow/Petrus knowledge, and the service remains
disabled/non-selectable.

### DS9 — Compose whole Hamsterdan deterministically

Implement five owner-local simulation/checker packages and root composition.
Prove local counterexamples and cross-only authority/work substitutions. Prove
the causal mutation vertical with result and work sensitivity.

Exit: resources are a bounded union, exact replay rebuilds fresh object graphs,
and only the responsible checker reports each injected violation.

### DS10 — Requalify the readiness journey portfolio

Implement twelve acceptance journeys: the eleven accepted semantic journeys
named in the DS10 record plus exact delivered-result mutation. Apply the
required timer, revocation, Git-ambiguity and closure overlays. Use replacement
owners and composed simulation, not V5 fixtures or a second model.

Exit: every journey has visible outcome, authority, stable operation, physical
effect count, crash/recovery evidence, finite bounds, shrinking and exact replay.

### DS11 — Prove real provider and process correspondence

Run direct evidence against GitHub transport/Git, authenticated Pi where
approved, fresh filesystem/SQLite state, OS process death, lease expiry and
bounded multi-PR concurrency.

Exit: each required simulation claim has a named real-seam counterpart and its
limits are explicit. The replacement service remains disabled.

### DS12 — Cut over and remove V5

After a separate approval, stop the old service, retain old state only for
bounded rollback, rename replacement source/tests to canonical paths, switch
package/entry points/deployment, qualify fresh state, and delete current code,
schemas, configuration and active documentation.

Exit: there is one Hamsterdan runtime and no active V5/Hamsterdan2 concept.
Old-state deletion remains a later separately approved action.

## Validation matrix

Each DS selects the rows it owns. DS10–DS12 cover the matrix completely.

| Layer | Required evidence | Decisive boundary |
|---|---|---|
| Mechanical gate | strict Ruff/format, ty, seven ast-grep rules/fixtures, AST architecture/enum audit | target blocks from DS1; no blanket suppressions |
| Behavioral unit | every workflow loop, readiness custody/effect group, GitHub operation family, agent lifecycle, host lifecycle/fairness | full transitions and exact typed failures, not private helper calls |
| Petrus seam | bounded replay, one-occurrence repair, one coordinator action, split Motus phases | no private import or hidden multi-occurrence drain |
| Storage | fresh History, Dispatch, ingress, review, timer, catalog, route, runnable and webhook stores | transaction interruption/reopen, exact bounds, no old reader |
| Provider | bounded GitHubKit/httpx, Git object/ref and Pi/workspace operations | one mutation attempt per step, complete lookup, credentials isolated |
| Local simulation | five owners independently | strict vocabularies, meaningful local counterexample, bounds, replay |
| Composed simulation | unchanged local modules under one Timeline | cross failures belong only to cross checkers |
| Journey acceptance | twelve target journeys | outcome, authority, operation, effect count, crash/recovery and bound |
| Correspondence | provider, Git, Pi, filesystem/SQLite, OS death, lease/concurrency | direct real-seam evidence for required simulation claims |
| Distribution/operation | source/wheel, entry points, config, inspection and image | fresh install, secret scan, disabled through DS11 |

## Required crash cuts

The complete portfolio includes:

- ingress manifest/grant stage, entry History acceptance, fold, returned host
  posture and inbox acknowledgement;
- bounded History page and one-occurrence repair;
- Activity request, attempt claim, effect observed, terminal record and
  workflow projection;
- timer command, command acknowledgement, maturity claim, maturity History
  acceptance and exact delivered marks;
- deferred wake and agent-route settlement;
- subject selection lease, instance open, readiness return, posture/route
  recording, requeue and close;
- agent submit, acceptance, runtime terminal, cancellation, delivery and lookup;
  and
- accepted Git/ref or comment mutation with response loss before local terminal.

Each test discards process-local state and reconstructs from durable owners.
Injecting a callback inside an otherwise unbounded operation does not prove an
exposed production cut.

## Required finite bounds

Every public command, step, observation, startup page, shutdown turn and
artifact declares and tests relevant limits for:

```text
input and output bytes
rows and History records examined
pages
external calls
provider mutation attempts
attempts and retries
elapsed time and deadlines
eligible actions
owner steps and leaf calls
choice draws and active faults
generations
journal entries and artifact bytes
pending Activities
loaded instances
catalog, route and runnable rows
retained terminals
workspace and archive bytes
```

A logical-operation limit does not excuse unbounded internal reads. Lowering a
meaningful limit must produce a typed refusal or replayable budget failure.

## Stop conditions

Delivery stops for Navigator review when:

- a story requires a compatibility reader, state migration, dual writer,
  selector or active second runtime;
- package ownership or an import edge must differ from
  [the architecture](architecture.md);
- a DS-review API choice changes fixed behavior rather than naming/composition;
- bounded execution requires private Petrus inspection or hides more than one
  effect attempt in a step;
- provider or agent credentials would cross their fixed custody boundary;
- a process restart depends on a saved coroutine, local return or exception;
- a local simulation cannot mount the real production owner;
- a cross property can pass without a real data dependency;
- real correspondence contradicts deterministic semantics; or
- DS12 cannot remove active V5/Hamsterdan2 concepts without compatibility code.

## Completion

CV20 completes only when all twelve stories are accepted, current project truth
describes the resulting single runtime, and DS12's separately approved cutover
has produced canonical Hamsterdan on fresh state. Historical records remain
unchanged as dated evidence; active code, configuration, schemas, deployment
and operator language contain no generation label.
