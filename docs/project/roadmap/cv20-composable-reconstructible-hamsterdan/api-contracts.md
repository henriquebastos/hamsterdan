# CV20 API contracts

This document is the canonical contract register for values and capabilities
that cross CV20 package boundaries. It states what each boundary must mean
before a Delivery Story chooses concrete Python syntax.

The labels are:

- **Fixed behavior**: owner, data, identity, ordering, failure and recovery
  semantics are accepted.
- **Fixed name**: the named concept is part of the CV20 vocabulary.
- **DS review**: the owning Delivery Story must rule the concrete API name or
  signature before implementation. The exploration is not a fallback answer.

Pseudocode describes required capability shape. It does not require Python
`Protocol` classes, inheritance, mixins, or one interface file per capability.
The DS Plan Checkpoint chooses the simplest composition style allowed by the
project's Python contract.

## Cross-cutting identity contract

### PR subject

One readiness lifecycle is bound to one provider route, repository and pull
request. That subject cannot change after root creation. Host catalog identity,
readiness binding and provider routing must agree before work runs.

- **Fixed behavior:** immutable one-PR binding and fail-closed mismatch.
- **DS review:** concrete `Subject` representation and serialized field names
  in DS7/DS8.

### Authority claim

Readiness authorizes protected work with the complete semantic claim:

```text
AuthorityClaim:
  phase
  incarnation
  head
  base
  policy
```

The claim is valid only when:

1. the durable readiness grant agrees with a fresh provider read;
2. host lifecycle evidence still reports the same active route generation;
3. same-subject custody has not moved across the read/fence cut; and
4. all five semantic fields agree at the operation-specific authority point.

The claim is readiness-owned. A provider snapshot alone is insufficient, and
host cannot grant workflow authority.

- **Fixed behavior:** fields, three-source composition and freshness rule.
- **DS review:** concrete type/factory/method names in DS7.

### Workflow Activity identity

Every Activity request has:

```text
activity name
Engine occurrence
workflow-owned work value
work operation identity
correlation
idempotency
```

For external work, correlation and idempotency equal the stable operation
identity carried by the workflow work value. Before readiness records a
terminal, it compares the requested Activity, occurrence, correlation,
idempotency and terminal operation with the exact invocation. A mismatch fails
before Dispatch or History accepts the terminal.

- **Fixed behavior:** complete comparison and original-occurrence return.
- **DS review:** terminal-admission function and error names in DS2/DS7.

### External operations

An operation is a stable logical identity, not an attempt number. Exact replay,
process restart or ambiguous response does not change it. A different payload
or authored authority under the same operation is an identity collision.

Fixed identities include:

| Work | Stable operation |
|---|---|
| Conversation classification | `conversation:{repository}:pr:{number}:delivery:{delivery_id}` |
| Mutation agent work | `mutation:{repository}:pr:{number}:{MutWork.op_key}` |
| Pi execution | `pi:sha256(logical_operation + "\0" + attempt)` |
| Git mutation/publication | exact workflow `MutWork.op_key` |
| Activity terminal | original workflow operation plus original occurrence |

Before implementation, DS3/DS5/DS7 must define every other Activity family's
final operation grammar in this document. Each grammar encodes the stable PR
subject, business source identity and operation-specific authority required for
provider lookup and user-visible idempotency, while omitting topology labels
such as `v5`. Current provider markers may supply correspondence evidence; an
implementer does not infer the grammar from exploration.

- **Fixed behavior/name:** the five identities above and no topology label.
- **DS review:** final operation grammar for each other Activity family in
  DS3/DS5/DS7.

## Workflow contracts

### Public build boundary

The workflow package exposes defining-module construction values used by
readiness runtime:

```text
workflow.net.topology.build_net(...)
workflow.net.topology.seed_marking(...)
workflow.net.topology.TOKENS
workflow.activities.MANIFEST
workflow.net.gating.wire_gates(...)
```

`build_net` composes all nine concern loops. `seed_marking` creates the initial
marking. `TOKENS` is explicit and collision-checked. `MANIFEST` declares every
Activity once. `wire_gates` binds supplied implementations without importing
them into workflow.

- **Fixed names:** `build_net`, `seed_marking`, `TOKENS`, `MANIFEST`,
  `wire_gates`.
- **DS review:** exact parameters and return values in DS3, constrained by
  real Petrus integration and defining-module imports.

### Value groups

| Module | Owns | Boundary rule |
|---|---|---|
| `workflow.values` | shared workflow value behavior and cross-loop aliases | no readiness/provider wrappers |
| `workflow.observations` | complete normalized admission language | source delivery/door custody stays outside the value |
| `workflow.facts` | typed mail exchanged between loops | loops do not import sibling implementations |
| `workflow.activities` | Activity work, typed terminals and manifest | adapters consume these values directly |
| `workflow.net.*` | loop-private state and pure folds | private loop state does not become a public port |

The fixed observation families are head/base authority, draft/ready, closure,
human conversation and CI/run evidence. DS3's API checkpoint must record the
final concrete type census and fields in this document before implementation.
After that ruling, additions require a CV20 contract update rather than an ad
hoc ingress payload.

### Activity manifest

Every manifest entry declares:

```text
gate name
request type
closed terminal variants
execution lane
stable operation derivation
blocked-terminal mapping, when route revocation can block it
```

Required Activity capabilities are:

| Capability | Workflow request | Allowed workflow terminals |
|---|---|---|
| Reply publication | `ReplyReq` | `Replied | ReplyBlocked | ReplyFault` |
| Findings publication | `Publishable` | `ReviewLanded | ReviewMoved | ReviewBlocked | ReviewFault` |
| Dashboard publication | `DashReq` | `DashLanded | DashDeferred | DashBlocked | DashFault` |
| Reminder publication | `RemReq` | `RemLanded | RemBlocked | RemFault` |
| Readiness announcement | `AnnounceReq` | `ALanded | ADeferred | AMoved | ABlocked | AFault` |
| CI rerun | `RerunReq` | `RerunLanded | RerunMoved | RerunFault` |
| Agent review | `RoundOpen` | `AgentReview | RoundDeferred | RoundMoved | RoundUnable` |
| Mutation | `MutWork` | `Pushed | MovedM | FaultM | DeclinedM` |

The terminal union is closed. Provider, agent, Git or infrastructure values do
not cross it. A returned terminal is a classified workflow outcome. A raised
exception is an unclassified implementation/infrastructure failure and cannot
be silently converted to a business terminal.

- **Fixed behavior:** capability groups, workflow ownership and closed result
  families.
- **DS review:** final method names and whether capabilities are functions,
  callable objects or collaborator methods in DS3/DS7.
- **DS review:** terminal type names may improve during DS3 only if every loop,
  manifest entry, adapter and CV20 document changes together.

### Mutation causal contract

`MutWork` carries workflow meaning, not an agent result. Its semantic fields
are:

```text
op
op_key
head
base
policy
incarnation
lineage
kind
instruction
run_id
attempt
```

The workflow derives `MutWork`; composition/readiness must not reconstruct or
alter it. Readiness projects it into one concrete `CodingRequest`. The exact
delivered `CodingResult` is then passed to Git publication. Publication outcome
must be sensitive to that exact result. The resulting `Pushed.op_key` closes
the same workflow occurrence.

- **Fixed behavior/name:** `MutWork`, `CodingRequest`, `CodingResult`, `Pushed`
  and the causal flow.
- **DS review:** exact immutable Python data shapes in DS3/DS6 and mutation
  capability signature in DS7.

### Timer values

Workflow owns `TimerCommand`, `TimerCommandApplied` and `TimerDue`. Readiness
custody applies commands, retains acknowledgements, claims mature timers and
marks exact deliveries. The clock uses signed integer microseconds; no float
conversion is allowed.

- **Fixed behavior:** owner, value roles, ordering and time unit.
- **DS review:** exact value fields and custody method names in DS3/DS7.

## Readiness contracts

### Evidence projection

One provider-to-workflow normalization capability projects a bounded provider
event/action into zero or more workflow observations. Delivery identity and
door identity remain in readiness custody and are attached to the immutable
manifest rather than embedded in workflow observations.

```text
project(event, action) -> tuple[workflow observation, ...]
```

- **Fixed behavior:** normalized values only; no provider exceptions or SDK
  objects cross the boundary.
- **DS review:** capability and method names in DS7.

### Conversation classification

The classification task contains delivery, comment text/identity, actor and
association plus the complete authority claim. It uses the stable conversation
operation, checks provider currency while the agent attempt is live, and
returns one authorized or unauthorized workflow `CommentSeen`. Readiness
freezes that result in the ingress manifest before workflow admission.

- **Fixed behavior:** task fields, identity, current-authority check and frozen
  result.
- **DS review:** task/capability names and exact actor field types in DS7.

### Authority capability

```text
current_authority() -> AuthorityClaim
```

Evidence unavailability produces a readiness-owned, bounded, secret-free
failure before a new observation or effect is accepted.

- **Fixed behavior:** fresh three-source composition.
- **DS review:** sync/async shape and failure taxonomy in DS7.

### Timer custody capability

The capability must support these semantic operations without combining their
durable cuts:

```text
apply one command
read oldest pending acknowledgement
mark exact acknowledgement delivered
claim earliest mature timer
read oldest pending maturity
mark exact maturity delivered
read next due instant
```

Construction receives the exact retained workflow acknowledgements/due facts
needed to rebuild or fail closed. A live method does not hide that recovery in
an unbounded constructor.

- **Fixed behavior:** operation set and ordering.
- **DS review:** concrete names and transaction API in DS7.

### Shared step result

Readiness and host communicate one detached bounded result family:

```text
CutRef:
  owner
  kind
  subject | none
  identity | none
  generation | none

StepResult = Progressed | Waiting | Quiescent | Terminal | Unavailable

Progressed:
  cut
  posture
  admission | none
  settled_agent_routes       # zero or one

Waiting:
  wait
  posture

Quiescent:
  posture

Terminal:
  lifecycle_generation
  reason                     # closed | merged
  posture

Unavailable:
  error_class                # closed and secret-free
  retryable
  eligible_at_us | none
  posture
```

`WorkPosture` reports only whether work is eligible now, one primary wait,
next deadline, whether host delivery remains, and bounded counts of retained
workflow/Activity/timer/route items. It is a reconstructible hint, not
canonical state.

`DeliveryPosture` is pending, accepted or already accepted for one exact
delivery. Host acknowledges its inbox row only after accepted/already accepted
is returned.

- **Fixed names:** `StepResult`, `Progressed`, `Waiting`, `Quiescent`,
  `Terminal`, `Unavailable`, `CutRef`, `WorkPosture`, `DeliveryPosture`.
- **Fixed behavior:** detached shape and host acknowledgement rule.
- **DS review:** concrete dataclass fields and enum/private-value treatment in
  DS7/DS8.

### Workflow-runtime cuts

| Cut | Maximum work before return |
|---|---|
| `history_page_replayed` | decode one bounded History page; no Dispatch or effect call |
| `occurrence_repaired` | repair one retained occurrence by one redispatch, projection, pure completion or cancellation action |
| `observation_accepted` | accept one identified workflow observation delivery |
| `observation_folded` | commit one lifecycle fold for that accepted observation |
| `workflow_action_committed` | execute one normal Petrus coordinator action after reconstruction |

Petrus `Wait` and `Stop` map to non-progress results. An impure workflow action
may record one `ActivityRequested`; it never executes the effect inline.

- **Fixed names/behavior:** the five cuts and bounds.
- **DS review:** page cursor/result structures in DS2 and runtime method layout
  in DS7.

### Readiness cuts

One readiness call returns after one cut:

| Cut | Maximum work before return |
|---|---|
| `ingress_staged` | recover/project one delivery and atomically store one bounded manifest plus grant |
| `ingress_entry_accepted` | accept one frozen manifest entry into History |
| `ingress_entry_folded` | fold one accepted entry; the final fold may complete delivery posture |
| `runtime_reconstructed` | replay one History page or repair one occurrence |
| `workflow_advanced` | commit one workflow action |
| `activity_attempt_claimed` | claim one exact Activity attempt |
| `activity_effect_observed` | run fixed lookup/fence work and at most one external mutation or agent call |
| `activity_terminal_recorded` | record one already observed typed terminal in Dispatch |
| `timer_command_applied` | transactionally apply one workflow timer command |
| `timer_ack_accepted` | accept one oldest command acknowledgement into History |
| `timer_ack_marked` | mark that exact acknowledgement delivered |
| `timer_maturity_claimed` | claim one earliest due timer |
| `timer_maturity_accepted` | accept one oldest persisted maturity into History |
| `timer_maturity_marked` | mark that exact maturity delivered |
| `deferred_wake_accepted` | accept one exact review or announcement wake |
| `agent_route_settled` | report one workflow-settled agent operation to host |

An observed effect result may live in a process-local continuation until the
adjacent terminal-recording step. If lost, a fresh process reconciles through
the durable effect owner. It never trusts or serializes the lost result.

- **Fixed names/behavior:** all cuts, one-call boundary and lookup-first
  recovery.
- **DS review:** application method names and lane selection representation in
  DS7.

### Readiness lifecycle

The host needs these semantic capabilities:

```text
inspect bound root -> detached readiness inspection
open one bound lifecycle from injected capabilities
admit one delivery and fresh lifecycle evidence -> StepResult
progress one reason and fresh lifecycle evidence -> StepResult
settle one already-started terminal cut -> StepResult
stop claiming new effects
close local resources under explicit mode
```

`settle` cannot claim a new external effect. `inspect` is bounded and read-only.
It may decode readiness-owned state but returns no History records, Engine,
Dispatch, workflow names or typed terminals.

- **Fixed behavior:** operation set, one-PR binding and detached results.
- **DS review:** factory/lifecycle names and signatures in DS7/DS8.

## GitHub provider contracts

### Values and credentials

`github_app.models` freezes provider meaning before it reaches readiness.
GitHubKit response objects, installation tokens, request headers and raw HTTP
errors remain inside `github_app`. Configuration validates strict App,
installation, repository and route inputs and redacts secret-bearing values.

- **Fixed behavior:** provider-owned frozen models and secret custody.
- **DS review:** model names and error taxonomy in DS5.

### Bounded transport and gateway

Every request declares applicable page, row, byte, call and elapsed-time
bounds. Pagination cannot expose an unbounded iterator. Transport returns
enough bounded metadata to classify rate limits and stale reads without
exposing credentials.

The gateway owns normalized reads plus raw Git object/ref operations. It does
not classify readiness outcomes.

- **Fixed behavior:** complete bounded reads, metadata and ownership.
- **DS review:** whether the transport keeps `request`/`pages` or uses more
  specific calls; response and pagination value names in DS5.

### Lookup-first provider effect

Each mutation follows:

```text
complete bounded lookup for exact operation and payload/authority
if compatible accepted effect exists: return it
if same operation conflicts: return identity collision
read/fence the operation-specific current authority
attempt at most one provider mutation
return accepted, refused, or ambiguous observation
```

An ambiguous observation becomes durable eligibility for a later step. The
same call does not hide an immediate second POST/ref mutation. Later recovery
does the complete lookup again.

Comment operations retain the externally discoverable marker:

```text
<!-- hamsterdan:readiness operation=<operation> head=<head> -->
```

Git mutation owns patch admission, complete first-parent lookup, operation
trailers, Git object creation and exact expected-head ref CAS. The exact
delivered `CodingResult` is part of publication input and its canonical digest
must affect accepted publication evidence.

- **Fixed behavior/name:** lookup-first order, one attempt, marker, exact ref
  CAS and result sensitivity.
- **DS review:** provider result types, canonical result-digest schema and
  method grouping in DS5/DS7.

### Operation-specific authority

Mutation, findings and rerun use their accepted strong current-authority cuts.
Reply, reminder and dashboard keep their accepted weaker operation-specific
safeguards. CV20 does not silently strengthen every publication to one generic
fence.

- **Fixed behavior:** safeguards remain operation-specific.
- **DS review:** explicit matrix and capability parameters in DS5/DS7.

## Agent contracts

### Protocol values

`agents.protocol` owns credential-free immutable request/result pairs for:

| Kind | Request/result role |
|---|---|
| conversation | classify one admitted human comment |
| review | inspect a PR and return typed review evidence/findings |
| coding | propose a patch, changed files, evidence and commit message |

It also owns one public serializable terminal envelope with result,
cancellation, timeout and cleanup-failure variants. The envelope identifies
logical operation and attempt and validates that the concrete result matches
the concrete request kind.

`ChangeResult` and `RepairResult` compatibility aliases do not enter the
replacement.

- **Fixed behavior:** kinds, credential-free values, terminal variants and
  pair validation.
- **Fixed names:** `CodingRequest`, `CodingResult`.
- **DS review:** other concrete value/terminal names, field types and public
  codec API in DS6.

### Durable execution lifecycle

The lifecycle exposes distinct durable positions:

```text
submit -> accepted -> runtime result/cancellation available -> delivered
```

It supports lookup, cancellation, timeout and bounded cleanup. Runtime response
loss uses retained terminal lookup before another start. Delivery response loss
uses retained receiver acceptance before another delivery. One logical
operation/attempt has at most one runtime start and one accepted receiver
terminal.

- **Fixed behavior:** positions, lookup precedence and cardinality.
- **DS review:** store schemas, lifecycle API and terminal-delivery method names
  in DS6.

### Pi and workspace

Pi adaptation creates the fixed execution identity, validates prompts and
typed results, and performs bounded calls. Workspace code owns exact checkout,
archive and patch safety without GitHub credentials. Host owns Pi installation,
connection, process runtime, secret lifetime and route composition.

- **Fixed behavior:** identity and custody split.
- **DS review:** adapter and workspace API names in DS6/DS8.

### Exact delivered result

Readiness coding capability receives repository URL, exact `CodingRequest`,
logical operation, attempt and a current-authority fence. It returns the exact
validated `CodingResult` accepted by agent delivery. Readiness cannot invoke a
second coding implementation or manufacture an equal result for publication.

- **Fixed behavior:** exact value dependency and current fence.
- **DS review:** coding capability signature and whether result lookup is a
  separate collaborator operation in DS6/DS7.

## Host contracts

### Lifecycle evidence

Host provides fresh evidence with this meaning:

```text
route_generation
route_status              # active | revoked
custody_generation
earliest_pending_delivery | none
tracked_delivery_status   # unknown | pending | failed | terminal | none
```

Both generations advance whenever their owned state changes. Readiness can ask
about one retained blocker without querying host tables.

- **Fixed behavior:** fields, generation semantics and read-only boundary.
- **DS review:** type/method names in DS8.

### Construction

Only `host.composition` joins:

```text
validated configuration and secret paths
GitHub App clients/routes/webhook custody
Pi installation/runtime and operation route custody
readiness effect implementations
readiness lifecycle construction
host catalog/runnable/inspection/service resources
```

Construction values contain no HTTP request, installation token, webhook row,
runnable row, Engine, Dispatch, Worker or simulation state.

- **Fixed behavior:** sole composition location and credential lifetime.
- **DS review:** named factories and ownership-friendly constructor grouping in
  DS8.

### Instance catalog and inspection

The catalog maps one subject to relative readiness root and provider route. It
does not copy head, base, policy, workflow phase, History identity or Activity
state. Startup reads bounded pages and asks readiness to inspect each root.

Inspection combines bounded provider/host counts with readiness's detached
projection. It never parses History or constructs a running host solely to
read state.

- **Fixed behavior:** mapping and detached inspection boundary.
- **DS review:** catalog schema, page token and JSON output names in DS8.

### Fair runnable contract

The runnable store owns durable enqueue sequence, eligibility instant,
selection lease, coalesced reasons and tail requeue. A service turn:

```text
select one due subject
open/reconstruct that subject
call readiness at most once
persist returned delivery/route/posture consequences
requeue or close the subject
```

A failed or immediately re-woken subject is ordered behind already-due
unclaimed subjects. Lost/corrupt wake hints reconstruct from catalog plus
readiness inspection.

- **Fixed behavior:** fairness and one-readiness-call turn.
- **DS review:** lease/store API and batch configuration in DS8.

### Host cuts

| Cut | Maximum work before return |
|---|---|
| `catalog_page_inspected` | inspect one bounded catalog/readiness page |
| `custody_item_disposed` | terminally dispose one host-owned non-workflow delivery |
| `subject_selected` | durably lease one due subject |
| `instance_opened` | open/reconstruct one readiness lifecycle |
| `readiness_step_returned` | call readiness once and preserve its nested cut unchanged |
| `delivery_acknowledged` | acknowledge one exact host delivery from accepted posture |
| `posture_recorded` | persist one subject's bounded wake/deadline hint |
| `agent_route_recorded` | settle one readiness-reported agent operation |
| `subject_requeued` | release one subject at tail sequence |
| `instance_closed` | close one instance/resource independently |

- **Fixed names/behavior:** all cuts and recovery boundaries.
- **DS review:** public service method organization in DS8.

## Simulation contracts

### Structural module boundary

The structural shape is fixed without requiring an interface class:

```text
SimulationModule:
  name
  open(context) -> generation
  drop(generation)
  close(generation)
  resource_usage(generation | none) -> named integer gauges

generation:
  command(name, strict_payload, context) -> strict value
  observe(name, strict_payload, context) -> strict value
  eligible_actions(context) -> bounded tuple[ActionRef, ...]
  step(action, context) -> one owner coroutine result
```

Retained module stores live outside the generation. `drop` destroys all
process-local state. Eligibility after restart derives only from retained
owner state.

- **Fixed behavior/signature shape:** all operations above.
- **DS review:** concrete type names and sync/async annotations in DS4.

### Timeline

The public synchronous API is fixed:

```text
Timeline.open(modules, budget, *, seed=0) -> Timeline

timeline.command(module, name, payload)
timeline.observe(module, name, payload=none)
timeline.advance(to_us)
timeline.fault(module, point, *, occurrence=1, payload=none)

timeline.start() -> LeafOffered | StepCompleted | Waiting
timeline.execute() -> LeafExecuted
timeline.finish() -> StepCompleted
timeline.step() -> StepCompleted | Waiting
timeline.run(step_budget) -> RunResult

timeline.crash(cut)
timeline.restart() -> Timeline
timeline.artifact(scenario_id) -> Artifact

Artifact.encode() -> bytes
Artifact.decode(payload) -> Artifact
replay(artifact, build_modules) -> ReplayResult
```

`start`, `execute` and `finish` expose one owner step with zero or one leaf.
`run` is a finite loop, not convergence. A stale generation rejects every call.
Budget termination discards frames and remains artifactable and replayable.

- **Fixed names/behavior:** `Timeline`, `Artifact`, the API and
  `hamsterdan-simulation` version 1.
- **DS review:** exact result/error field shapes in DS4.

### Runtime and module ownership

Runtime owns logical clock, cross-module tie selection, deterministic choices,
generic occurrence matching, process generations, one-leaf mechanics, global
budgets, strict journal, artifact and replay. Modules own command/observation
vocabulary, semantic faults, state, eligibility, retries, timers, fairness,
resources and local checking.

Local checkers consume detached observations/artifacts rather than module
stores. Root cross checkers compare edge-local facts from more than one owner.
Checker output does not become runtime disposition.

- **Fixed behavior:** ownership and checker independence.
- **DS review:** local command/fault vocabularies in DS9 after production owners
  exist.

## Error contract

1. Expected business outcomes use the closed typed workflow terminal declared
   for that Activity.
2. Boundary unavailability uses an owner-defined, bounded, secret-free
   classification with retry eligibility when applicable.
3. Identity, authority, correlation, schema and replay contradictions fail
   closed; they are not retries.
4. Durable operations may store failures as data when reconstruction must
   preserve them. Process-local programming and infrastructure failures remain
   exceptions until classified by the owning boundary.
5. Unknown commands, observations, faults, payload fields, enum values and
   artifact fields are rejected. No boundary invents defaults for unknown
   values.
6. No error payload includes credentials, provider clients, raw secret-bearing
   responses, unbounded body text or arbitrary exception representations.

Concrete exception/data taxonomies are **DS review** items owned by the package
that detects the failure. Cross-package generic error hierarchies are not
allowed.

## DS API-strengthening register

Each story must resolve its listed questions before implementation. Resolving
means updating this document and the DS record, not preserving the answer only
in a chat or plan.

| Story | Fixed before review | Questions the DS must settle |
|---|---|---|
| DS1 | exact tree, gate rules, positive/negative architecture edges | gate command names, fixture DSL and diagnostic payloads |
| DS2 | bounded replay/repair and split claim/effect/terminal positions | Petrus/Motus public signatures, cursor/result/error types, pin/update sequence |
| DS3 | workflow ownership, nine loops, values, manifest and topology names | final value fields/names, manifest entry shape, build signatures, loop-local APIs |
| DS4 | Timeline API, module structure, one-leaf semantics and artifact family | concrete result/error dataclasses, strict JSON aliases, budget construction |
| DS5 | provider custody, bounds and lookup-first one-attempt algorithm | transport/gateway methods, provider model names, operation results/errors, limit types |
| DS6 | credential-free protocol, stable execution identity and lifecycle cuts | request/result/terminal fields, codec, stores, Pi/workspace call signatures |
| DS7 | one-PR ownership, cuts, authority, causal mutation and typed terminals | readiness capabilities, application/lifecycle signatures, custody schemas, failure taxonomy |
| DS8 | sole composition root, lifecycle evidence, catalog, fairness and shutdown | constructors, store/lease APIs, inspection JSON, service/CLI commands |
| DS9 | five local modules, one root composition and checker ownership | exact local command/observation/fault vocabularies and report types |
| DS10 | twelve journey meanings and required evidence | acceptance DSL and artifact/coverage report schema |
| DS11 | direct real-seam correspondence and explicit external approvals | harness boundaries, process-kill controls and evidence report format |
| DS12 | one cutover, no migration and canonical Hamsterdan naming | operator command sequence, no-return marker, rollback record and cleanup evidence |

## Provenance

The detailed experiments that established these contracts remain under
[ES-010](../../exploration/es10-composable-hamsterdan-architecture/index.md).
They are useful for auditing rationale or experimental correspondence. They do
not supply missing API decisions during Delivery.
