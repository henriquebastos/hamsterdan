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
The first tracer that uses a capability rules the smallest concrete Python API
with its real producer, consumer, deterministic seam and observation surface in
view. Later tracers may extend that API from new real call sites, but do not add
speculative compatibility aliases. The Plan Checkpoint chooses the simplest
composition style allowed by the project's Python contract.

## Tracer API ruling rule

Every Plan Checkpoint reviews behavior/call tree, values/signatures, identities/
authority, errors, durable cuts/recovery, observations/limits and unresolved
names as one packet. The fixed semantics below constrain that review. A
concrete API becomes canonical only when this document and the owning DS record
are updated before implementation.

First-use ownership is:

| Contract family | First real tracer | Later strengthening |
|---|---|---|
| one-PR subject, composition, detached step/posture, Timeline/artifact | DS1 | DS2–DS10 only from added call sites |
| provider observation, host delivery and readiness ingress | DS2 | DS7/DS9 add observation families |
| workflow Activity/manifest/occurrence identity | DS3 | DS5–DS8 add Activity families |
| provider transport and lookup-first publication | DS4 | DS6/DS7 add Git/rerun operations; DS9 completes policies |
| agent protocol, runtime, workspace and exact delivery | DS5 | DS6 adds coding values |
| complete `AuthorityClaim` and first strong findings fence | DS5 | DS6/DS7 reuse it; DS9 completes the policy/lifecycle matrix |
| conversation, `MutWork`, coding and Git causal chain | DS6 | DS7 reuses it for repair |
| CI evidence, rerun and escalation | DS7 | DS11 qualifies combinations |
| timer protocol/custody and deferred wakes | DS8 | DS11 qualifies combinations |
| complete lifecycle and authority matrix | DS9 | DS10 consumes fresh evidence |
| catalog, runnable leases, multi-PR service/operator | DS10 | DS11 qualifies process behavior |
| journey/correspondence/evidence report | DS11 | DS12 consumes the report |
| cutover commands and no-return evidence | DS12 | removed when construction ends where specified |

## Cross-cutting identity contract

### PR subject

One readiness lifecycle is bound to one provider route, repository and pull
request. That subject cannot change after root creation. Host catalog identity,
readiness binding and provider routing must agree before work runs.

- **Fixed behavior:** immutable one-PR binding and fail-closed mismatch.
- **DS review:** concrete `Subject` representation and serialized field names
  in DS1; DS10 may extend portfolio inspection without changing identity.

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
- **DS review:** concrete claim/factory/evidence names at the first protected
  findings call site in DS5. DS9 may add lifecycle-driven APIs and completes
  the operation-specific matrix without changing the claim's meaning.

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
- **DS review:** request identity/projection names in DS3 and terminal-admission
  function/error names in DS4.

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

Before implementation, the first tracer for each Activity family must define
its final operation grammar in this document: dashboard in DS3, review in DS5,
mutation in DS6, CI rerun/repair in DS7, timer/deferred work in DS8 and any
remaining lifecycle operation in DS9. Each grammar encodes the stable PR
subject, business source identity and operation-specific authority required for
provider lookup and user-visible idempotency, while omitting topology labels
such as `v5`. Current provider markers may supply correspondence evidence; an
implementer does not infer the grammar from exploration.

- **Fixed behavior/name:** the five identities above and no topology label.
- **DS review:** final operation grammar in the owning first-use DS3–DS9 tracer.

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
- **DS review:** DS1 rules the minimal `build_net`/`seed_marking` boundary from
  real Petrus use; DS3 rules manifest/gate wiring; owning DS5–DS9 tracers extend
  topology without changing these names.

### Value groups

| Module | Owns | Boundary rule |
|---|---|---|
| `workflow.values` | shared workflow value behavior and cross-loop aliases | no readiness/provider wrappers |
| `workflow.observations` | complete normalized admission language | source delivery/door custody stays outside the value |
| `workflow.facts` | typed mail exchanged between loops | loops do not import sibling implementations |
| `workflow.activities` | Activity work, typed terminals and manifest | adapters consume these values directly |
| `workflow.net.*` | loop-private state and pure folds | private loop state does not become a public port |

The fixed observation families are head/base authority, draft/ready, closure,
human conversation and CI/run evidence. Their first real tracers record the
concrete types/fields here before implementation: head/base in DS2,
conversation in DS6, CI/run in DS7 and remaining lifecycle/authority in DS9.
Additions require a CV20 contract update rather than an ad hoc ingress payload.

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
  callable objects or collaborator methods in the owning DS3–DS9 tracer.
- **DS review:** terminal type names may improve before their first tracer use
  only if loop, manifest entry, adapter and CV20 documents change together.

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
- **DS review:** exact immutable Python data shapes and mutation capability
  signatures in DS6.

### Timer values

Workflow owns `TimerCommand`, `TimerCommandApplied` and `TimerDue`. Readiness
custody applies commands, retains acknowledgements, claims mature timers and
marks exact deliveries. The clock uses signed integer microseconds; no float
conversion is allowed.

- **Fixed behavior:** owner, value roles, ordering and time unit.
- **DS review:** exact value fields and custody method names in DS8.

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
- **DS review:** capability and head-observation method names in DS2; DS7/DS9
  extend the same boundary for CI and lifecycle evidence.

### Conversation classification

The classification task contains delivery, comment text/identity, actor and
association plus the complete authority claim. It uses the stable conversation
operation, checks provider currency while the agent attempt is live, and
returns one authorized or unauthorized workflow `CommentSeen`. Readiness
freezes that result in the ingress manifest before workflow admission.

- **Fixed behavior:** task fields, identity, current-authority check and frozen
  result.
- **DS review:** task/capability names and exact actor field types in DS6.

### Authority capability

```text
current_authority() -> AuthorityClaim
```

Evidence unavailability produces a readiness-owned, bounded, secret-free
failure before a new observation or effect is accepted.

- **Fixed behavior:** fresh three-source composition.
- **DS review:** sync/async shape and failure taxonomy in DS9.

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
- **DS review:** concrete names and transaction API in DS8.

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
  DS1 for the first lifecycle; later owning tracers add only fields proven by
  their new calls, with terminal lifecycle fields completed in DS9.

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
- **DS review:** DS1 rules page cursor/result and initial runtime layout, DS2
  rules observation cuts and DS3 rules occurrence repair/action request use.

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
  the first tracer that exercises each cut: DS1–DS4, DS8 and DS10 respectively.

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
- **DS review:** initial factory/lifecycle names and signatures in DS1, delivery
  admission in DS2, effect settlement in DS4 and close/service use in DS9/DS10.

## GitHub provider contracts

### Values and credentials

`github_app.models` freezes provider meaning before it reaches readiness.
GitHubKit response objects, installation tokens, request headers and raw HTTP
errors remain inside `github_app`. Configuration validates strict App,
installation, repository and route inputs and redacts secret-bearing values.

- **Fixed behavior:** provider-owned frozen models and secret custody.
- **DS review:** webhook/observation models in DS2; transport/effect errors in
  DS4; CI and lifecycle model additions in DS7/DS9.

### Bounded transport and gateway

Every request declares applicable page, row, byte, call and elapsed-time
bounds. Pagination cannot expose an unbounded iterator. Transport returns
enough bounded metadata to classify rate limits and stale reads without
exposing credentials.

The gateway owns normalized reads plus raw Git object/ref operations. It does
not classify readiness outcomes.

- **Fixed behavior:** complete bounded reads, metadata and ownership.
- **DS review:** whether the transport keeps `request`/`pages` or uses more
  specific calls; response and pagination value names in DS4.

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
  method grouping in DS4 for comment publication, DS6 for Git and DS7 for rerun.

### Operation-specific authority

Mutation, findings and rerun use their accepted strong current-authority cuts.
Reply, reminder and dashboard keep their accepted weaker operation-specific
safeguards. CV20 does not silently strengthen every publication to one generic
fence.

- **Fixed behavior:** safeguards remain operation-specific.
- **DS review:** initial dashboard safeguard in DS4 and complete explicit matrix
  plus capability parameters in DS9.

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
  codec API in DS5; coding variants are ruled in DS6.

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
  in DS5.

### Pi and workspace

Pi adaptation creates the fixed execution identity, validates prompts and
typed results, and performs bounded calls. Workspace code owns exact checkout,
archive and patch safety without GitHub credentials. Host owns Pi installation,
connection, process runtime, secret lifetime and route composition.

- **Fixed behavior:** identity and custody split.
- **DS review:** adapter, workspace and host custody API names in DS5.

### Exact delivered result

Readiness coding capability receives repository URL, exact `CodingRequest`,
logical operation, attempt and a current-authority fence. It returns the exact
validated `CodingResult` accepted by agent delivery. Readiness cannot invoke a
second coding implementation or manufacture an equal result for publication.

- **Fixed behavior:** exact value dependency and current fence.
- **DS review:** coding capability signature and whether result lookup is a
  separate collaborator operation in DS6.

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
- **DS review:** one-subject evidence begins in DS1/DS2; complete generation and
  revocation names are ruled in DS9.

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
  DS1, extended when provider/agent resources first appear in DS2/DS4/DS5.

### Instance catalog and inspection

The catalog maps one subject to relative readiness root and provider route. It
does not copy head, base, policy, workflow phase, History identity or Activity
state. Startup reads bounded pages and asks readiness to inspect each root.

Inspection combines bounded provider/host counts with readiness's detached
projection. It never parses History or constructs a running host solely to
read state.

- **Fixed behavior:** mapping and detached inspection boundary.
- **DS review:** one-subject binding/inspection in DS1 and catalog page/portfolio
  JSON in DS10.

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
- **DS review:** lease/store API and batch configuration in DS10.

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
- **DS review:** DS1/DS2 rule the one-subject open/posture/acknowledgement cuts;
  DS5 adds route settlement; DS10 rules selection/requeue/close organization.

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
- **DS review:** concrete mechanics/type names in DS1; each tracer rules only
  its new owner-local command/observation/action vocabulary.

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
- **DS review:** DS1 rules core result/error/artifact fields at first use; DS4
  rules split effect leaves, DS8 time advance, and later tracers extend evidence
  without creating another artifact family.

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
- **DS review:** local command/fault vocabularies in every tracer alongside the
  production behavior they drive; root cross evidence grows at the same time.

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
| DS1 | one-PR ownership, sole composition, bounded step/posture, strict gate and core Timeline/artifact | subject/root/factory/result signatures, minimal Petrus replay cursor, gate diagnostics and first local/root evidence |
| DS2 | raw-byte provider input, host delivery custody, readiness manifest/grant and real `HeadSeen` fold | webhook/route/delivery/observation values, stage/admit/ack calls, duplicate/collision errors and bounds |
| DS3 | workflow ownership, manifest identity and first durable `DashReq` | request/terminal fields, manifest/token/build/wiring APIs, occurrence projection and pending posture |
| DS4 | lookup-first one-attempt provider effect and split Activity positions | transport/gateway/result APIs, marker lookup, claim/effect/terminal calls, terminal admission and physical metrics |
| DS5 | credential-free agent protocol, stable execution identity, exact delivery and first protected findings call | review values/codecs, lifecycle/store calls, Pi/workspace/route custody, complete claim/evidence APIs, findings fence, cancellation errors and bounds |
| DS6 | exact workflow→coding→Git→workflow causal contract | conversation/`MutWork`/coding/`Pushed` shapes, result digest, patch/Git/ref-CAS APIs and sensitivity evidence |
| DS7 | exact-head CI, workflow escalation and lookup-first rerun | CI evidence/state, rerun/repair operations, retry limits, stale/ambiguous errors and schedule reports |
| DS8 | integer-time workflow protocol and readiness timer custody | timer/custody/clock/wake APIs, reminder/deferred operations, cut transactions and resource keys |
| DS9 | complete lifecycle outcomes and operation-specific authority matrix over the established claim | lifecycle-driven claim/evidence/generation extensions, remaining policy matrix, blocked/moved/conflict mappings and fence diagnostics |
| DS10 | catalog discovery, durable runnable fairness and one-call host turns | catalog/page/lease/service/inspection/operator APIs, startup/shutdown aggregation and portfolio bounds |
| DS11 | twelve journey meanings, complete correspondence and explicit approvals | journey/shrink/report DSL, claim/fixture/process-kill protocols, evidence binding and unavailable policy |
| DS12 | one cutover, no migration and canonical Hamsterdan naming | operator command sequence, no-return marker, rollback record and cleanup evidence |

## Provenance

The detailed experiments that established these contracts remain under
[ES-010](../../exploration/es10-composable-hamsterdan-architecture/index.md).
They are useful for auditing rationale or experimental correspondence. They do
not supply missing API decisions during Delivery.
