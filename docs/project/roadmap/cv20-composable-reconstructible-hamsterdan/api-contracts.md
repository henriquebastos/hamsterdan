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

## Python shape policy

Concrete Python follows the project engineering contract:

- one-value identities and semantic scalars use validating native-type
  subtypes;
- external input and durable/serialized output use strict Pydantic boundary
  models;
- frozen dataclasses appear only when they remove real record boilerplate;
- private state is exposed through predicates and domain operations rather than
  exported status enums; and
- narrow collaborators use direct callables/composition rather than a Protocol
  or service layer per call.

Public `dict[str, Any]`, generic handler/context/result names, one file per noun,
fake-pure reducers and speculative API aliases are forbidden. Exact classes,
methods, signatures, private representation, boundary-model placement and cut
payload fields remain first-call-site DS Plan decisions.

First-use ownership is:

| Contract family | First real tracer | Later strengthening |
|---|---|---|
| one-PR subject, composition, detached step/posture, Timeline/artifact | DS1 | DS2–DS11 only from added call sites |
| provider observation, host delivery and readiness ingress | DS2 | DS7/DS9 add observation families |
| dashboard subnet/event/projection/publication and workflow Activity/manifest/occurrence identity | DS3 | DS4 executes the effect; DS5–DS8 add Activity families; DS9 composes closure |
| provider transport and lookup-first publication | DS4 | DS6/DS7 add Git/rerun operations; DS9 completes policies |
| agent protocol, runtime, workspace and exact delivery | DS5 | DS6 adds coding values |
| complete `AuthorityClaim` and first strong findings fence | DS5 | DS6/DS7 reuse it; DS9 completes the policy/lifecycle matrix |
| conversation, `MutWork`, coding and Git causal chain | DS6 | DS7 reuses it for repair |
| CI evidence, rerun and escalation | DS7 | DS12 qualifies combinations |
| timer protocol/custody and deferred wakes | DS8 | DS12 qualifies combinations |
| complete lifecycle and authority matrix | DS9 | DS10/DS11 consume fresh evidence |
| configured-repository unknown discovery | DS10 | DS11 fairly schedules discovery turns; DS12 qualifies recovery |
| catalog, runnable leases, multi-PR service/operator | DS11 | DS12 qualifies process behavior |
| journey/correspondence/evidence report | DS12 | DS13 consumes the report |
| cutover commands and no-return evidence | DS13 | removed when construction ends where specified |

## Cross-cutting identity contract

### PR subject

One readiness lifecycle is bound to one provider route, repository and pull
request. That subject cannot change after root creation. Host catalog identity,
readiness binding and provider routing must agree before work runs.

- **Fixed behavior:** immutable one-PR binding and fail-closed mismatch.
- **DS review:** concrete `Subject` representation and serialized field names
  in DS1; DS11 may extend portfolio inspection without changing identity.

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
its final operation grammar in this document: dashboard publication in DS3,
review in DS5, mutation in DS6, CI rerun/repair in DS7, timer/deferred work in
DS8 and any remaining lifecycle operation in DS9. Each grammar encodes the
stable PR subject, business source identity and operation-specific authority
required for provider lookup and user-visible idempotency, while omitting
topology labels such as `v5`. Current provider markers may supply correspondence
evidence; an implementer does not infer the grammar from exploration.

- **Fixed behavior/name:** the five identities above and no topology label.
- **DS review:** final operation grammar in the owning first-use DS3–DS9 tracer.

### Provider acquisition and observation identity

Acquisition identity records how provider evidence entered Hamsterdan:

```text
webhook acquisition = (ProviderRouteId, DeliveryId)
read acquisition    = (ProviderRouteId, ProviderReadId)
```

The webhook identity preserves exact `X-GitHub-Delivery`. A retry of a read that
may observe changed state receives a new `ProviderReadId`. `RouteGeneration`
and `CustodyGeneration` record/fence the acquisition context; neither belongs to
semantic observation equality.

`PullRequestSnapshot` is immutable provider-owned evidence containing stable
`PRSubject`, exact head/base `BranchTip(repository_id, ref, sha)`, lifecycle,
draft, tri-state mergeability and diagnostic provider update time.
`ObservationProvenance` carries bounded source-specific evidence. Webhook
event/action belongs only to webhook provenance. Readiness policy is a separate
`PolicySeen` observation and never a provider-authored snapshot field.

Focused observation identity is:

```text
ObservationKey = obs:v1:sha256:<digest>
canonical bytes = encode(version, subject, local incarnation,
                         observation family, focused semantics)
HistoryAdmissionId = admission:v1:sha256:<ObservationKey digest>
```

The canonical bytes and key are both persisted and compared. `v1` freezes key
encoding, not snapshot schema. Acquisition identity, provenance, policy,
receipt/provider times and route/custody generations are excluded from semantic
equality. Same key with different canonical bytes is a fatal semantic collision.

`HeadSeen` contains subject, local incarnation and exact head/base branch tips.
Draft, lifecycle, mergeability and policy use separate focused observation
families. The first locally admissible `HeadSeen` binds incarnation 1 as the
first lifecycle segment known to this root, not as provider-current authority.
DS9 alone owns successor incarnations and cut-specific `CurrentnessWitness`.

- **Fixed names:** `PullRequestSnapshot`, `ObservationProvenance`, `BranchTip`,
  `HeadSeen`, `PolicySeen`, `ObservationKey`, `HistoryAdmissionId`,
  `ProviderRouteId`, `DeliveryId`, `ProviderReadId`, `ActiveRouteBinding`,
  `RouteGeneration`, `CustodyGeneration`.
- **Fixed behavior:** identity/equality/collision/incarnation semantics and
  source-neutral admission compatibility.
- **DS review:** exact Python shapes, codecs and constructor/call signatures in
  DS2; read provenance fields in DS4; lifecycle/currentness fields in DS9.

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

Each concern module also exposes the smallest DS-ruled construction seam needed
to mount that exact production subnet independently. `build_net` composes those
same constructions; owner-local simulation cannot copy a fold or maintain a
second topology. DS3 rules the first concrete seam from the dashboard module,
its standalone scenario runner and the root call site together.

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
| Dashboard publication | `DashboardPublication` | `DashboardPublicationOutcome` closed family |
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

### Dashboard subnet

The dashboard concern owns four distinct meanings:

```text
DashboardEvent
  one workflow-owned fact relevant to the desired dashboard

DashboardProjection
  private durable desired, landed, pending and retained-failure state

DashboardPublication
  one immutable exact external command with stable operation identity

DashboardPublicationOutcome
  one closed workflow terminal family for that exact publication
```

`DashboardEvent` is not provider evidence. Lifecycle and other workflow folds
translate their owned observations/outcomes into this internal fact family.
`DashboardProjection` is not Activity work: History/Dispatch own occurrence and
execution custody, while the projection retains the exact logical pending
publication needed to match outcomes and enforce single-flight publication.
`DashboardPublication` does not carry held projection/recovery state merely to
transport it through the effect boundary.

The pure behavior is:

```text
fold one DashboardEvent or DashboardPublicationOutcome into DashboardProjection
  -> update desired, landed, pending or retained failure
  -> emit no publication while one exact publication is unresolved
  -> otherwise emit one DashboardPublication exactly when desired != landed
```

A provider closure observation carries its evidence-owned close instant into a
normal dashboard event. That event makes the desired document absorbingly
closed and supersedes desired documents that have not become Activities. An
already-issued publication is reconciled first; workflow then emits one final
closed publication. On the successful path, the lifecycle generation commits
close only after that publication lands. A terminal inability remains explicit
for DS9 policy; it cannot masquerade as alignment. A later fact cannot reopen
the dashboard, and a pure fold never calls a clock to create the close instant.

- **Fixed names:** `DashboardEvent`, `DashboardProjection`,
  `DashboardPublication`, `DashboardPublicationOutcome`.
- **Fixed behavior:** meaning split, immutable publication work, single-flight
  coalescing, exact outcome matching and final-close convergence order.
- **DS review:** DS3 rules concrete event variants, document/work/projection and
  terminal fields, operation grammar, construction seam and local scenario
  commands/observations. DS4 rules provider execution/admission signatures.
  DS9 rules terminal inability and lifecycle-close completion policy.

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

### Source-neutral ingress admission

One source-neutral readiness seam projects a `PullRequestSnapshot` plus
`ObservationProvenance` into zero or more focused workflow observations. DS2
implements webhook acquisition only. Provider reads introduced later must use
the same seam.

Each acquisition atomically stages:

```text
IngressManifest:
  acquisition identity
  snapshot/provenance digest references
  ordered unique-key IngressEntry values       # 0..N

AdmissionGrant:
  exact manifest
  subject
  lifecycle/incarnation binding
  route/custody generations
  policy revision
  snapshot/provenance digest references
```

There is exactly one immutable manifest and one immutable manifest-scoped grant
per acquisition, including empty projections. An empty manifest stages but
creates no Petrus History delivery. The grant means readiness may
classify/admit frozen manifest M under lifecycle binding B. It is not fresh
provider truth, effect authority or a mutable latest-subject grant.

Each entry receives one persisted closed `AdmissionDecision`:

```text
exact_duplicate | acquisition_collision | novel | corroborating
stale | semantic_collision | conflicting | incomparable
```

Same acquisition identity and content is an exact retry. Changed content under
the same identity is an acquisition collision and quarantines before History.
A distinct acquisition with the same key/canonical bytes is corroborating:
append one bounded deterministically deduplicated provenance reference and stop
at `ingress_entry_classified`; do not deliver, admit or fold again. Same key and
different canonical bytes is a fatal semantic collision. Contradictions persist
as non-retryable failure-as-data.

Petrus History is the sole workflow-admission ledger. `ObservationAdmission`
is a rebuildable projection/index from an admitted key, first entry and exact
History admission. No `ObservationLedger` or `AdmissionLedger` exists.

- **Fixed names:** `IngressManifest`, `IngressEntry`, `AdmissionGrant`,
  `AdmissionDecision`, `ObservationAdmission`.
- **Fixed behavior:** cardinality, ordering, classification, sole-ledger,
  corroboration and empty-manifest semantics.
- **DS review:** concrete codecs, storage rows, producer/consumer calls,
  refusal types and bounded provenance representation in DS2; DS7/DS9 extend
  observation families without changing admission identity.

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

DS9 may issue a `CurrentnessWitness` only for one admission/fence cut after a
confirming exact provider read and unchanged pre/post host `RouteGeneration`
and `CustodyGeneration`. It has no TTL and cannot be reused as general latest
truth. DS2 does not construct it.

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

At pinned Petrus `44cac5ff48ac371ebae56323941983f30db13c0d`, identified
delivery can return a prior acknowledgement but the public API cannot boundedly
resume one accepted-and-begun nonterminal occurrence. DS2 crash recovery is
blocked until Petrus implements, tests and releases a public
accept/resume-one-accepted-unfinished-occurrence seam and Hamsterdan pins and
qualifies it. Readiness must not access internal `Instance` state or collapse
`observation_accepted` and `observation_folded` to avoid this prerequisite.

### Readiness cuts

One readiness call returns after one cut:

| Cut | Maximum work before return |
|---|---|
| `ingress_staged` | recover/project one delivery and atomically store one bounded manifest plus grant |
| `ingress_entry_classified` | persist one entry decision; corroboration appends bounded deduplicated provenance and performs no fold |
| `ingress_entry_accepted` / `observation_accepted` | accept one novel frozen manifest entry into History |
| `ingress_entry_folded` / `observation_folded` | fold one accepted entry; the final fold may complete delivery posture |
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
  the first tracer that exercises each cut: DS1–DS4, DS8, DS10 and DS11
  respectively.

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
  admission in DS2, effect settlement in DS4 and close/service use in DS9/DS11.

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
not classify readiness outcomes. DS4 establishes two recovery mechanics for
later owners:

```text
exact-read one pull request -> PullRequestSnapshot + read provenance
list one bounded page of open pull-request candidate identities
  -> candidates + next-page/rate metadata
```

The list page is a discovery hint only. DS10 owns pass custody, configured
scope, candidate comparison, exact-read-before-registration and eligibility.

- **Fixed behavior:** complete bounded reads, metadata and ownership.
- **DS review:** exact read/list-page call and result names, response/rate/
  pagination values and finite limits in DS4; DS10 rules pass use.

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

### Delivery receipt and custody

Webhook receipt has three distinct layers:

1. GitHub→Amp HTTP receipt at the relay boundary;
2. host `InboxReceipt`, proving `delivery_retained` or a committed permanent
   refusal/quarantine; and
3. terminal `delivery_acknowledged`, after readiness reports accepted or
   already-accepted posture.

The Amp HTTP layer does not by itself prove that its physical 2xx follows host
retention; DS2 correspondence must establish that ordering or fail closed.
`delivery_retained` is the canonical host retention cut. Host acknowledgement
is an independently idempotent guarded `retained → acknowledged` compare-and-
swap. Pending posture never permits acknowledgement.

Raw body, signature and non-allowlisted headers remain transient. Normalized
delivery/snapshot evidence is retained through active and accepted-but-
unacknowledged custody. Terminal settlement atomically replaces it with a
bounded redacted `DeliveryTombstone`. No TTL, eviction or silent truncation may
remove evidence required for reconstruction, classification or collision proof.
Capacity refusal is typed and occurs before partial durable writes.

- **Fixed names:** `InboxReceipt`, `delivery_retained`,
  `delivery_quarantined`, `delivery_acknowledged`, `DeliveryTombstone`.
- **DS review:** durable schemas, calls, cut/refusal payloads, compaction and
  finite byte/row limits in DS2.

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
  JSON in DS11.

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
readiness inspection. DS11 applies the same durable fairness to known-subject
and repository-discovery turns without moving traversal into readiness.

- **Fixed behavior:** fairness and one-readiness-call turn.
- **DS review:** lease/store API and batch configuration in DS11.

### Configured-repository discovery custody

Host owns one bounded `RepositoryDiscoveryPass` at a time per configured
repository. The durable resume point is an explicit
`RepositoryDiscoveryPassBoundary`; provider pages are transient query windows.
`LastCompletedOpenPullRequestDiscoveryPass` supports inspection and scheduling
but is not an atomic-snapshot or completeness watermark.

One discovery turn lists one bounded page or exact-reads/classifies one unknown
candidate. Exact read precedes idempotent registration/enqueue. Closed, missing,
unauthorized and route-invalid candidates are classified without registration.
List absence never closes, revokes, deletes or proves catalog completeness.

- **Fixed names:** `RepositoryDiscoveryPass`,
  `RepositoryDiscoveryPassBoundary`,
  `LastCompletedOpenPullRequestDiscoveryPass`,
  `UnknownPullRequestDiscovery`.
- **DS review:** pass/candidate/registration calls, boundary representation,
  page-1 restart versus ETag-validated continuation, rate reserve, leases,
  deferral and finite limits in DS10.

### Host cuts

| Cut | Maximum work before return |
|---|---|
| `delivery_retained` | retain one verified normalized delivery under current binding/custody or refuse before partial write |
| `delivery_quarantined` | retain one bounded permanent acquisition collision/refusal record |
| `catalog_page_inspected` | inspect one bounded catalog/readiness page |
| `custody_item_disposed` | terminally dispose one host-owned non-workflow delivery |
| `repository_discovery_page_listed` | retain one bounded list-page result and next pass boundary |
| `repository_discovery_candidate_classified` | exact-read and classify one unknown candidate before any registration |
| `repository_discovery_pass_completed` | commit one completed pass boundary without a completeness claim |
| `subject_selected` | durably lease one due subject |
| `instance_opened` | open/reconstruct one readiness lifecycle |
| `readiness_step_returned` | call readiness once and preserve its nested cut unchanged |
| `delivery_acknowledged` | acknowledge one exact host delivery from accepted posture |
| `posture_recorded` | persist one subject's bounded wake/deadline hint |
| `agent_route_recorded` | settle one readiness-reported agent operation |
| `subject_requeued` | release one subject at tail sequence |
| `instance_closed` | close one instance/resource independently |

- **Fixed names/behavior:** all cuts and recovery boundaries.
- **DS review:** DS1/DS2 rule one-subject open/delivery/posture/acknowledgement
  cuts; DS5 adds route settlement; DS10 rules discovery cuts; DS11 rules
  selection/requeue/close organization.

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

Every byte, row, capacity, page, call, History scan, timeout, attempt, backoff,
lease, defer window, deterministic schedule, mutation, semantic-coverage,
checker, journal and artifact limit is finite. Numeric values are calibrated
from accepted fixtures and tested at −1 / limit / +1. This document does not
turn evidence seeds or example call sites into accepted constants/signatures.

## DS API-strengthening register

Each story must resolve its listed questions before implementation. Resolving
means updating this document and the DS record, not preserving the answer only
in a chat or plan.

| Story | Fixed before review | Questions the DS must settle |
|---|---|---|
| DS1 | one-PR ownership, sole composition, bounded step/posture, strict gate and core Timeline/artifact | subject/root/factory/result signatures, minimal Petrus replay cursor, gate diagnostics and first local/root evidence |
| DS2 | webhook-only snapshot/provenance, host delivery custody, source-neutral observation/key/manifest/grant/classification and real incarnation-1 `HeadSeen` fold | codecs, retain/stage/classify/admit/fold/ack calls, tombstones, collision/corroboration/refusal payloads and calibrated bounds |
| DS3 | workflow ownership, independently executable dashboard subnet, four dashboard meanings, manifest identity and first durable `DashboardPublication` | event/document/projection/publication/outcome fields, operation grammar, subnet/build/wiring APIs, scenario runner, public bounded repair-one-occurrence seam, occurrence projection and pending posture |
| DS4 | exact PR read, one bounded repository list page, lookup-first one-attempt provider effect and split Activity positions | read/list/transport/gateway/result APIs, pagination/rate metadata, marker lookup, claim/effect/terminal calls, terminal admission and physical metrics |
| DS5 | credential-free agent protocol, stable execution identity, exact delivery and first protected findings call | review values/codecs, lifecycle/store calls, Pi/workspace/route custody, complete claim/evidence APIs, findings fence, cancellation errors and bounds |
| DS6 | exact workflow→coding→Git→workflow causal contract | conversation/`MutWork`/coding/`Pushed` shapes, result digest, patch/Git/ref-CAS APIs and sensitivity evidence |
| DS7 | exact-head CI, workflow escalation and lookup-first rerun | CI evidence/state, rerun/repair operations, retry limits, stale/ambiguous errors and schedule reports |
| DS8 | integer-time workflow protocol and readiness timer custody | timer/custody/clock/wake APIs, reminder/deferred operations, cut transactions and resource keys |
| DS9 | complete lifecycle/currentness outcomes, known-subject exact-read convergence and operation-specific authority matrix | incarnation/witness/claim/evidence/generation extensions, remaining policy matrix, blocked/moved/conflict mappings and fence diagnostics |
| DS10 | bounded configured-repository discovery with exact-read-before-registration | pass/boundary/list-page/candidate/classification/registration APIs, continuation/rate/DST correspondence and calibrated portfolio bounds |
| DS11 | catalog, durable known/discovery-turn fairness and one-call host turns | catalog/page/lease/service/inspection/operator APIs, startup/shutdown aggregation and portfolio bounds |
| DS12 | twelve journey meanings, complete correspondence and explicit approvals | journey/shrink/report DSL, claim/fixture/process-kill protocols, evidence binding and unavailable policy |
| DS13 | one cutover, no migration and canonical Hamsterdan naming | operator command sequence, no-return marker, rollback record and cleanup evidence |

## Provenance

The detailed experiments that established these contracts remain under
[ES-010](../../exploration/es10-composable-hamsterdan-architecture/index.md).
They are useful for auditing rationale or experimental correspondence. They do
not supply missing API decisions during Delivery.
