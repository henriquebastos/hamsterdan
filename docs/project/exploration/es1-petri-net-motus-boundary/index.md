---
status: Promoted
opened: 2026-08-10
navigator: Henrique
---

# ES-001 — Simplify the Petri Net at the Motus boundary

## Inquiry

Which parts of Hamsterdan's PR-readiness Petri Net are product workflow, which
are durable asynchronous-call semantics, and which are execution mechanics
that should be supplied by Petrus or Motus as reusable behavior or
configuration?

The analysis began against Petrus/Motus at revision
`116b0ddc460c0e04d4ad40c077158bd3498a4860`. Petrus Activity Execution V2 was
subsequently accepted at `35d09023f40fac34dc84c54389466b669a79ec19` and is now
pinned by Hamsterdan. Temporal's Activity execution model remains a design
reference rather than a framework to copy.

## Executive judgment

The prior refinement removed the one aggregate reducer-style state machine, but
it did not make the executable graph small. The current Net has 46 places, 162
transitions, and 481 arcs. Of those transitions, 110 are retirement paths:

| Transition responsibility | Count |
| --- | ---: |
| Dormant/terminal transient absorption | 68 |
| Generic stale-authority retirement | 16 |
| Obsolete publication continuity | 6 |
| Superseded operation results | 8 |
| Basis/no-op retirement | 5 |
| Admission/lifecycle cleanup | 7 |
| **Total retirement** | **110** |

The right next simplification is not to collapse Activity request/result places
mechanically. Those places currently preserve a meaningful asynchronous-call
boundary: concern state stays present while work is in flight, authorization
latches become visible immediately, and a completed result rejoins the current
marking before it may update state. Petrus Activity bindings are frozen at
firing begin and produce outputs only at completion, so a direct transition can
otherwise project stale state or make an active concern disappear.

The strongest simplification is to let Motus own one logical Activity execution
across classified delayed retries, deadlines, heartbeats, and cancellation,
while Hamsterdan continues to own desired state, PR authority, operation
identity, provider reconciliation, business supersession, and acceptance
against the current marking.

## Current topology by responsibility

| Responsibility | Transitions | Assessment |
| --- | ---: | --- |
| Retirement | 110 | Dominant framework pressure; not all removable today |
| Business coordination | 20 | Mostly genuine PR-readiness behavior |
| Activity execution | 11 | Exact asynchronous boundaries; some bridges collapsible |
| Retry/timer | 7 | Publication retry is the principal Motus candidate |
| Admission/reconciliation | 6 | Subject/generation policy; remains application-owned |
| External ingress | 5 | Petrus delivery plus domain observation normalization |
| Lifecycle | 3 | Product meaning with framework cleanup pressure |

The six active concern tokens are still the right ownership boundary. Three of
them nevertheless retain local orchestration state:

- `ActionsState` mixes observed Actions facts with rerun operation/latch state.
- `MutationState` mixes repair budget, active operation, recovery, and
  provisional-head state.
- `PublicationState` aggregates finding, dashboard, conversation, and readiness
  publication workflows and their requested/operation/capability flags.

These are smaller state machines than the removed `Control`, but they remain
places to inspect after execution mechanics move out of the Net.

## What Petrus and Motus already own

At the pinned revision, the framework already supplies:

- a canonical `ActivityRequested` outbox committed with firing begin;
- exact redispatch after restart without rerunning Activity preparation;
- typed Activity declaration and deterministic result projection;
- occurrence-level request/result correlation;
- duplicate terminal acknowledgement and conflicting-terminal rejection;
- dispatch claims, attempt epochs, heartbeat leases, and stale-attempt fencing
  when a Worker/LocalDispatch topology is used;
- heartbeat checkpoint details delivered to a replacement attempt;
- frozen successful results and projection-only recovery after a crash.

Hamsterdan currently uses `DerivedActivityHandler` and production
`InlineDispatch`. It does not configure Motus execution attempts, heartbeat
behavior, correlation, or idempotency: each invocation receives the conservative
one-attempt default and occurrence-derived identities. Hamsterdan instead keeps
its business operation inside each request/result and scans History to recover
active operations.

Current safe framework-boundary improvements are therefore limited but real:

1. use supported Engine in-flight/projection state rather than manually folding
   History for unresolved Activity requests;
2. configure Motus invocation idempotency/correlation from the exact work
   operation rather than parsing it back out of request payloads;
3. remove Activity result paths that have no workflow consequence;
4. collapse only authorization bridges that establish no pending state.

## What Motus is missing

Current `ExecutionPolicy` contains only:

```python
@dataclass(frozen=True)
class ExecutionPolicy:
    attempts: int = 1
    heartbeat_timeout: int = 30
```

Attempts retry immediately and every ordinary exception is treated alike.
There is no backoff, jitter, retryability disposition, per-attempt timeout,
overall execution deadline, Activity cancellation, or typed failure projection
into the Net. Terminal Activity failure records `ActivityFailed` and
`FiringFailed`, then halts the Engine drive; it does not produce an application
result token.

The minimal coherent enhancement is conceptually:

```python
@dataclass(frozen=True)
class RetryPolicy:
    maximum_attempts: int | None = 1
    initial_interval: float = 0
    backoff_coefficient: float = 2
    maximum_interval: float | None = None
    jitter: float = 0

@dataclass(frozen=True)
class ExecutionPolicy:
    retry: RetryPolicy = RetryPolicy()
    start_to_close_timeout: float | None = None
    schedule_to_close_timeout: float | None = None
    heartbeat_timeout: float | None = None

class ActivityError(Exception):
    kind: str
    retryable: bool
    retry_after: float | None
    details: object

class ActivityHandler:
    def prepare(self, binding: Binding) -> ActivityInvocation: ...
    def project(self, binding: Binding, result: object) -> HandlerResult: ...
    def project_failure(
        self, binding: Binding, failure: ActivityFailureInfo
    ) -> HandlerResult: ...
```

Required behavior:

- one durable invocation, correlation, and idempotency identity across attempts;
- durable next-eligible attempt time across restart;
- explicit retryable, non-retryable, canceled, timed-out, and exhausted outcomes;
- separate per-attempt and aggregate deadlines;
- deterministic terminal-failure projection exactly once;
- the same projection-after-crash guarantee as successful completion;
- cooperative cancellation delivered through execution context/heartbeat;
- stable attempt identity and checkpoint details exposed to Activity code.

Hamsterdan currently uses `InlineDispatch`; delayed execution policy cannot be a
blocking sleep inside it. Adopting durable backoff also requires a Motus dispatch
provider capable of retaining next-attempt eligibility, or equivalent durable
Engine scheduling semantics.

## Temporal Activity lens

Temporal treats an Activity Execution as a logical operation spanning multiple
Activity Task attempts. Its useful reference capabilities are:

- declarative retry policy with initial interval, backoff coefficient, maximum
  interval/attempts, non-retryable failure types, and per-failure retry delay;
- schedule-to-close, start-to-close, schedule-to-start, and heartbeat timeouts;
- heartbeat details available to a replacement attempt;
- cooperative cancellation delivered to heartbeating Activities;
- stable Activity identity distinct from one attempt/task token;
- optional asynchronous completion by an external system.

Motus already has the conceptual distinction between stable invocation and
fenced operational attempt, plus heartbeat details. The useful adaptation is a
smaller set: classified backoff, start-to-close, schedule-to-close, stable
identity, checkpoint details, and later cooperative cancellation. Motus should
not copy Temporal's unlimited-retry default, workflow model, local/child
Activity taxonomy, or asynchronous completion before a concrete use case.

## What must remain in Hamsterdan

| Concern | Why Motus cannot own it |
| --- | --- |
| PR/head/base/policy authority | Motus custody does not know current GitHub authority |
| Fresh pre-effect fencing | Cancellation and attempt epochs can race with an external write |
| Provider operation lookup | Only the GitHub adapter knows whether an ambiguous write happened |
| Desired publication state | Comment/check content and replacement rules are product semantics |
| Same-generation supersession | A newer desired projection can obsolete an older operation on the same head |
| Business retry | Re-review, one rerun, repair budget, and human intervention change workflow meaning |
| Result acceptance | Completed work must join current concern ownership, not its frozen begin binding |

Motus idempotency prevents neither a duplicated GitHub side effect nor stale PR
mutation by itself. Stable provider markers, lookup-first recovery, and fresh
authority checks remain mandatory on every attempt.

## False simplifications

### Collapse every Activity into one transition

Unsafe with current Petrus semantics. Consumed concern tokens disappear at
firing begin, read bindings are frozen, and pending state cannot be emitted
until completion. Dashboard/change/repair could be authorized repeatedly or
could restore stale state after authority changes.

### Remove result places because Motus correlates completion

Motus correlation proves which firing completed. It does not prove that the
operation still owns the current dashboard, mutation, review, or Actions state.
The result place is the asynchronous mailbox that allows a current-marking join.

### Remove business operation IDs

Occurrence identity is execution correlation. Hamsterdan operation identity is
desired-state ownership and provider idempotency. Same-generation publication
supersession requires the latter even when the former is exact.

### Delete all retirement transitions or add reset arcs only

Resetting queued tokens does not prevent an already-running Activity from
projecting a late result. Safe scoped cleanup requires atomic scope closure,
pending-Activity cancellation, and deterministic drop/quarantine of completion
racing with closure.

### Use one Engine per PR generation

This removes many in-net stale joins but creates a PR-level supervisor, atomic
generation handoff, cross-History routing, continuity transfer, cancellation,
archival, and authority fencing outside the generation Net. It moves rather
than removes complexity and is not recommended without first-class Petrus
instance/scope support.

## Story thickened — instance scheduling and scoped effects

Integrating Activity Execution V2 exposed a deeper boundary than publication
retry. Durable Dispatch separates authorization from execution, but the current
Worker contract resolves implementations globally by Activity name while
Hamsterdan's `PrReadinessActivities` is composed with one PR's authority,
publisher, clients, and provider-reconciliation behavior. A permanent Worker per
PR preserves that locality but duplicates resident infrastructure. A shared
Worker avoids duplication only by introducing application-specific routing that
must reconstruct the correct PR context after restart.

The useful synthesis is to keep workflow state partitioned by Instance while
sharing scheduling and execution infrastructure. One Engine/History per PR is
analogous to a resumable activation record: the static Net need not carry a
scope field through every token or filter one global marking. This does not
require one thread or Worker per Instance. It requires one advancing owner per
Instance at a time and a scheduler capable of resuming runnable Instances.

The programming-language-runtime lens separates three scopes that must not
collapse into an ambient service locator:

1. workflow scope identifies the durable Instance that authorized work;
2. implementation binding identifies the host-composed Activity module that
   interprets a named effect;
3. Attempt execution context carries operational identity, heartbeat, deadline,
   and checkpoint behavior.

Live clients, credentials, Engines, markings, and callables must not enter the
durable invocation. Durable implementation selection must be reconstructible
from stable scope and binding identity after process loss. Dynamic test
overrides may be ephemeral, but production retries cannot depend on a closure or
mutable global patch that disappears on restart.

`PrReadinessActivities` already resembles the desired developer surface: a
cohesive Activity module whose methods share external capabilities. Treating
such a module as an effect interpreter is preferable to calling it an actor,
which would imply mailbox, identity, residency, and private mutable state that
are not required. A host may compose a default module, decorate it, replace it,
or overlay selected operations without requiring inheritance. Petrus should
provide only the neutral resolution seam if evidence shows that applications
otherwise rebuild it.

The Activity boundary remains semantic. One Activity may coordinate several
external systems when it owns one safely reconcilable logical operation across
all of them. Lookup-first recovery and stable operation identity then remain
inside the Activity module. Durable branching, waiting, compensation decisions,
human intervention, and meaningful intermediate business states belong in the
Net instead. Operational mechanics leaking into the Net and durable workflow
decisions hiding inside Activities are dual failure modes.

## Candidate runtime shape

The current candidate is not yet an accepted framework contract:

```text
provider ingress
  -> durable observation inbox
  -> Instance scheduler claims one runnable Instance
  -> Engine delivers observations and advances to quiescence
  -> scoped Activity instructions enter shared durable custody
  -> executor resolves a host-composed Activity module
  -> terminal result wakes the owning Instance
  -> Engine accepts against current ownership or retires as superseded
```

Webhook processing may become durable ingress rather than the special inline
path that performs complete reconciliation. Startup recovery, observations,
Activity terminals, Petri timers, and delayed Attempts could then share one
scheduler path. A periodic full sweep remains a recovery mechanism rather than
the primary scheduler. Serialization remains mandatory per Instance, but may be
implemented by a single scheduler, actor mailbox, durable lease, or database
claim instead of a permanent thread and in-memory lock per Instance.

PostgreSQL may eventually consolidate History, observation inboxes, Activity
custody, runnable-instance indexes, and leases while preserving logical
partitioning by Instance. It does not solve implementation resolution,
authority fencing, or workflow ownership by itself and must not substitute for
an explicit scope contract.

## Co-equal simplification test

The framework inquiry and the application topology must be evaluated together:

> What is the smallest provider-neutral execution-scope contract that lets many
> isolated Engine Instances share durable scheduling and Activity infrastructure
> while producing the smallest Petri Net that still expresses all durable
> business decisions explicitly?

A healthy dashboard/readiness slice should approach:

```text
current facts
  -> authorize immutable request and record current operation
  -> external Activity owns Attempts, deadlines, and reconciliation
  -> terminal typed result rejoins current authority and operation ownership
  -> accept and fold, or retire as superseded
```

No Net place should exist solely for Attempt count, retry delay, claim,
heartbeat, deadline, worker availability, provider connection, retry maturation,
or reissuing the same logical operation. The Net must continue to express
requested work, exact operation ownership, capability blocking, current
authority, supersession, and accepted business outcome.

Complexity is evidence in all directions:

- retry/due/reissue and operational lifecycle places suggest runtime mechanics
  leaked into the Net;
- Activities containing durable branching, waits, compensation policy, or
  hidden progress state suggest workflow leaked into the effect layer;
- large Activity-name routers, routing fields repeated in business payloads,
  serialized closures, one thread per Instance, or application reimplementation
  of Worker behavior suggest missing host-composition primitives.

Any Petrus enhancement must preserve the trivial application path. A scope or
resolver abstraction that enables distributed composition by making simple
inline applications framework-heavy is not acceptable.

## Next learning movement

The inquiry continues in a Petrus-owned exploration, with Hamsterdan providing
the application pressure and target Net. It should produce evidence for:

1. whether exposing only `instance` on `ActivityAttempt` and execution context
   is sufficient, or a richer neutral scope is necessary;
2. whether Activity resolution belongs in Worker, execution context, or host
   composition outside Petrus;
3. how default Activity modules and reconstructible scoped overrides compose;
4. whether one scheduler path can replace inline webhook reconciliation without
   weakening latency, restart, authority, or isolation;
5. how shared Local or PostgreSQL custody preserves per-Instance result routing;
6. whether the resulting dashboard/readiness Net actually loses the lease,
   retry, due, reissue, and associated retirement topology without hiding
   workflow decisions elsewhere.

The production CR-003 implementation remains paused until this exploration
reaches a reviewed conclusion. Activity Execution V2 remains accepted and
pinned; the unresolved question is composition and scheduling, not retry-policy
correctness.

## Simplifications available with current Petrus

The conservative candidate retains request/result boundaries and publication
retry continuity while making the following focused changes:

1. Remove unused `attempts` from dashboard/readiness lease tokens.
2. Remove `reminder_result`, behaviorless `accept_reminder`, and its three
   retirement paths; a custom Activity handler can project no token.
3. Collapse `start_conversation -> work.conversation -> execute.conversation`
   into one Activity transition because it creates no pending concern state.
4. Deliver Actions observations only to `actions_result`; successful acceptance
   emits the `actions_basis` used for rerun/repair decisions.
5. Route each classified intent only to its applicable mutation, reply, or
   concern-fold place instead of cloning it into three places and retiring two.
6. Prove whether `reminder_due` can re-emit directly to `reminder.timer` with a
   fresh production instant, then remove `reminder.rearm` if replay agrees.
7. Replace host History parsing with supported Engine occurrence projections
   and map work operation identity into Motus invocation identity.

Estimated result, subject to executable topology tests:

| Metric | Current | Conservative target |
| --- | ---: | ---: |
| Places | 46 | 43–44 |
| Transitions | 162 | 155–157 |
| Retirement transitions | 110 | about 107 |
| Arcs | 481 | 465–472 |

This is useful cleanup, not the large simplification.

## Recommended Motus-enhanced target

After classified delayed retry and terminal-failure projection exist, migrate
dashboard/readiness publication first:

```text
Hamsterdan
  current concerns + desired operation
        -> authorize and latch pending
        -> exact Activity request

Motus Activity Execution
  authority check on every attempt
        -> provider lookup/reconciliation
        -> classified retry with durable backoff
        -> deadlines / heartbeat / cancellation
        -> one terminal outcome

Hamsterdan
  terminal result + current authority + owning operation
        -> accept / superseded / capability-blocked
```

This removes the dashboard/readiness lease, retry, and due places and their
delay/reissue/retirement paths. Conversation transport retry can follow. Review
reconciliation and mutation repair budgets remain business-level workflows.

Estimated result:

| Metric | Current | Motus-enhanced target |
| --- | ---: | ---: |
| Places | 46 | 37–39 |
| Transitions | 162 | 132–136 |
| Retirement transitions | 110 | 85–90 |
| Arcs | 481 | 395–415 |

Current dashboard/readiness behavior retries every `ok=False` after five minutes
without a budget. Broad `RuntimeError` catches therefore retry programming
errors, stale authority, permission failures, and transport failures alike. The
migration must first classify failures:

| Failure | Target behavior |
| --- | --- |
| Disconnect, rate limit, provider 5xx | Motus retry with backoff |
| Ambiguous transmitted write | Provider lookup/recovery, then retry |
| Stale authority | Non-retryable superseded outcome |
| Definite capability/permission absence | Non-retryable capability outcome |
| Invalid payload or identity collision | Fail loud as invariant violation |
| Unknown runtime failure | Non-retryable by default |

An explicit overall retry budget is preferable to preserving infinite retry,
but choosing that budget is a product/operations decision.

## Radical Petrus-native target

The large retirement reduction requires first-class generation/Activity scopes:

```text
One PR History

scope g7
  Authority + concern tokens + transient calls

supersede / draft / terminal
  -> atomically close g7
  -> reset queued g7 tokens
  -> cancel pending g7 Activities
  -> late g7 completion: acknowledge and drop/quarantine
  -> optionally create g8
```

Minimal framework semantics include a durable scope on each invocation,
atomic scope close/reset, cooperative cancellation, deterministic first-wins
ordering against completion, and replay-stable late-completion disposition.
Begin-time latch outputs and late-bound completion joins would be separate
advanced primitives if Petrus later wants to remove more request/result places.

Estimated result if all those primitives exist:

| Metric | Current | Scoped target |
| --- | ---: | ---: |
| Places | 46 | 28–34 |
| Transitions | 162 | 45–70 |
| Retirement transitions | 110 | 5–15 |
| Arcs | 481 | 160–260 |

This is a core Petrus evolution, not an immediate Hamsterdan refactor.

## Candidate and recommended sequence

### Candidate

Evolve Motus around one durable logical Activity execution, using Temporal's
retry/timeout/cancellation model as a reference, then simplify Hamsterdan at
that boundary without surrendering current-authority and desired-state policy.

### Sequence

1. Apply and verify the small current-Petrus simplifications.
2. Specify and build Motus classified backoff, deadlines, stable identity, and
   terminal-failure projection; retain one-attempt defaults.
3. Migrate dashboard/readiness publication and remove their retry subnets.
4. Migrate conversation transport retry and selected provider failures.
5. Reassess `PublicationState`, `ActionsState`, and `MutationState` after
   operational latches move; split only independently evolving facts.
6. Explore scopes/reset/cancellation only as a separate Petrus architecture
   story, not as incidental Hamsterdan cleanup.

### Navigator direction — two independent lanes

The Navigator accepted the candidate on 2026-08-10 with two parallel lanes:

- Lane 1 is production refinement. The current Hamsterdan thread owns it and a
  dedicated Petrus subthread owns the upstream Motus changes. Accepted Petrus
  lands first; Hamsterdan then pins and integrates it. Both repositories use
  direct-to-`main` delivery without pull requests.
- Lane 3 is a disposable, self-contained study on remote experimental branches.
  Its Hamsterdan thread creates and owns its own Petrus subthread. It does not
  report to Lane 1, and Lane 1 neither consumes nor accommodates its prototype.
- The study preserves findings and measurements, never mergeable implementation.
  After Lane 1 is complete, any scoped-lifecycle implementation starts again
  from fresh accepted branches and the recorded evidence.

The independent study remains in this Exploratory Story. The accepted
production candidate is promoted to Workbench RS-002.

The Navigator accepted the remaining lifecycle-scope candidate on 2026-08-11.
Production implementation is owned by
[RS-003](../../workbench/rs-003-first-class-lifecycle-scopes.md). Lane 3 remains
disposable evidence; production starts again from current accepted Petrus and
Hamsterdan `main`.

### Production lifecycle-scope conclusion

The scoped target was validated from fresh accepted production branches rather
than by merging the experiment. Petrus revision
`b0bb336a077b70b6d702aef26acbf8ad1381f9b3` supplies exact lifecycle identity,
provenance, append-ordered close/reset, commit-first cancellation, and late
terminal disposition. Hamsterdan uses those mechanics through a staged
command/scope-boundary/commit protocol repaired before ordinary reconciliation.

The Net moved from 40 places, 138 transitions, 412 arcs, and 91 retirement
transitions to 43 places, 67 transitions, 266 arcs, and 17 retirements. This
confirms the experiment's architectural claim without forcing its numerical
estimate: lifecycle cleanup belongs to the runtime boundary, while
same-generation ownership and acceptance remain workflow. The extra explicit
boundary and recovery facts are preferable to hidden host state or an assumed
cross-component transaction.

The work also resolved terminal exhaustion. Motus retries one logical execution;
after exhaustion, only an exact trusted recovery intent may authorize one new
occurrence, retaining stable provider-effect identity for lookup-first
reconciliation. Unknown terminal failures are nonrecoverable workflow faults.
Neither path creates an autonomous Petri retry loop.

### Production publication-ownership conclusion

The post-scope reassessment found one remaining false serialization boundary:
finding, conversation, dashboard, and readiness publication still shared one
23-field `PublicationState` token. RS-004 replaced it with four concrete strict
Pydantic tokens. Each result and authorization transition now consumes only its
owner; exact retained recovery requests are typed and private to workflow state,
and operation absence is `None` rather than an empty string.

The topology moved from 43 places, 67 transitions, and 266 arcs to 46 places,
69 transitions, and 309 arcs while retaining 17 retirement transitions. This is
a clarity gain rather than a regression: three places expose four independent
owners, two transitions expose three recovery branches instead of one dynamic
router, and arcs expose genuine relational reads. Restart evidence for every
recoverable publication channel confirms one fresh occurrence with stable
provider identity and no stale self-loop.

No new Petrus contract or host infrastructure was needed. This reinforces the
boundary: Motus owns execution, lifecycle scopes own generation cleanup, each
business publication owns its state, and the host composes them.

### Production host-activation conclusion

The post-publication review retained `ActionsState` because observation and
rerun form one protocol, and retained `MutationState` because it is the exact
change/repair mutual-exclusion boundary. Splitting either would add relational
joins or recreate locking rather than expose independent business ownership.

The actual false coupling was outside the Net. Webhooks, runnable timers,
Activity terminals, and sweeps advanced one PR through different host call
stacks. RS-005 converged them on one per-Instance activation: pre-settle frozen
terminals, apply selected custody or provider reconciliation, post-settle,
record runnable posture, then acknowledge custody under one lock. Deferred and
bounded webhook batches fence sweep reconciliation; strict-bound inactive
Instances remain settlement-repairable even when their noncanonical wake is
lost.

The Net remains at 46 places, 69 transitions, 309 arcs, and 17 retirements.
Conceptual clarity improved without changing workflow topology or adding a
Petrus, database, actor-runtime, or HA abstraction. This confirms that a
complicated call graph can be infrastructure leakage even when the Petri graph
is already expressing the right business ownership.

### Production application-command conclusion

The next boundary inspection found that `PrReadinessApplication` was largely
cohesive: provider reconciliation, generation lifecycle repair, and effect
composition share real ordering and fencing invariants. Splitting those
responsibilities would relocate the same concepts across more objects.

The removable responsibility was an ignored dictionary projection and three
application entry points retained for tests. RS-006 made
`activate(trigger, *, comment=None) -> None` the sole command, privatized its
one reconciliation pass, and moved tests to canonical snapshots, lifecycle
places, derived waits, and observed effects. Public `reconcile`,
`route_comment`, and `projection` were deleted without replacement.

This removed 44 net production lines without changing the Net, provider ordering,
lifecycle protocol, Activities, or runtime. One remaining genuine candidate is
duplicate comment admission across service and application; unlike the deleted
query API, that is a security-boundary choice and requires explicit Navigator
direction.

### Production comment-admission conclusion

The Navigator chose one provider-ingress trust owner. RS-007 moved GitHub
event/action, bot, actor type, association, exact-mention, whitespace, and raw
type policy into `github_app.webhooks.admit_conversation`. Authenticated raw
observations remain durable custody; accepted input crosses the host as a
strict, frozen `AdmittedConversation` containing only audit identity and
mention-stripped text.

`PrReadinessApplication` now reconciles provider truth, binds current
epoch/head, and delivers the already-admitted conversation. It no longer knows
provider actor types, configured mention syntax, or trusted-association policy.
Malformed authenticated values fail terminally before application construction
rather than wedging immediately due custody.

This removes 45 net lines from host application/service code while adding one
neutral contract and total provider validation; the overall production diff is
seven net lines larger. The clarity gain is ownership, not line-count theater.
No Net, custody schema, lifecycle, Activity, authority, scheduler, or Petrus
semantics changed.

### Production Actions-assessment conclusion

The next boundary inspection found duplicate GitHub Actions assessment in
application reconciliation and durable Activity discovery. The copies selected
required jobs and derived conclusions independently, and had already diverged:
only reconciliation normalized provider `pending` into the strict domain values
`queued` or `in_progress`.

RS-008 retained explicit exact-run selection and moved the cohesive remainder
into `GitHubAuthority.actions_evidence(run, required_checks)`. The provider now
owns required-job attachment, pending normalization, supported terminal
validation, and deterministic failed-job evidence. Reconciliation retains
observation identity and current workflow context; the Activity retains fresh
authority fencing and operation context. This narrower two-step API preserves
the Activity's important absent-run-before-policy ordering and avoids a broad
snapshot or consumer-mode flag.

The unused `VerifiedSnapshot` aggregate was deleted. No Net, lifecycle,
Activity execution, scheduler, storage, or Petrus behavior changed. This
reinforces the clarity rule: unify provider interpretation, but do not hide
consumer-specific sequencing or authority behind an apparently convenient
aggregate.

### Production host-runtime surface conclusion

The following host pass found two false forms of optionality. `HostService`
looked up application terminal settlement and unresolved-publication inspection
dynamically even though every production application implements both and safe
activation ordering requires them. RS-009 made those calls direct and moved
test doubles onto the real mandatory interface.

`AgentRouteStore.reconstruct_before_redispatch()` and `.resolve()` had no
production callers and duplicated the canonical `claim()` and `settle()`
protocol. Deleting them leaves one operation that atomically validates active
composition and reconstructs exact persisted ownership, and one operation that
settles terminal ownership.

No replacement Protocol or adapter was needed. No Net, provider, lifecycle,
Activity execution, scheduler, storage schema, or Petrus behavior changed. The
clarity gain is that required recovery behavior is now syntactically required,
while route custody exposes only the operations production actually composes.

### Production registration-evidence conclusion

RS-010 separated GitHub registration interpretation from host composition.
`GitHubAppClients.registration_inventory(config)` now owns exact App and
installation authority, permissions/events, suspension, bounded same-origin
pagination, repository cardinality and shape, and duplicate identity rejection.
It returns one immutable `RegistrationInventory`; `HostService` atomically
reconciles routes only after that complete value exists.

Adversarial review showed why this was more than moving code. The old host
parser could silently discard malformed repository rows and then replace a
valid registry with a partial portfolio. The provider boundary is now
all-or-nothing, status-checked, continuation-authoritative, exact-type checked,
and secret-safe across installation-token parsing failures. Provider failure
cannot mutate the current registry or host installation identity.

No new provider facade or file was required: App authentication already owned
registration and unrestricted inventory clients, frozen provider values already
had a home, and the existing bounded transport supplied safe HTTP and Link
semantics. No Net, lifecycle, Activity execution, scheduler, storage schema, or
Petrus behavior changed.

### Production agent-execution identity conclusion

RS-011 removed an ambient host/agent handshake. Activities previously called
`agent_dispatch(operation, attempt)` to claim durable route custody and place a
Pi execution identity in a `ContextVar`, then made a separate `AgentRunner`
call which implicitly consumed it. The runner protocol now carries the logical
operation and Attempt directly.

One host-owned `RoutedAgentRunner` claims exact logical route ownership before
the qualification seam or provider delegate. It forwards the unchanged pair;
`PiNativeRunner` alone derives the stable per-Attempt runtime identity used by
runtime, workspace, Episode, and Turn. This preserves one logical route across
coding retries while making each provider Attempt distinct and replay-stable.
Legacy Amp remains explicitly composed and receives no Pi identity semantics.

The correction reinforces the execution-scope conclusion: pass the smallest
immutable identity required by the callee, keep durable ownership at the host
composition edge, and let provider adapters derive provider-local identity. A
general scope container, ambient runtime scope, or serialized execution object
would be larger and less explicit. No Net topology changed.

### Production execution-scope conclusion

The production lane validated a smaller contract than a general workflow or
actor scope. Petrus exposes the authorizing Instance to a shared Worker and
lets the host resolve `(instance, activity)` to a reconstructible
implementation, with the ordinary Activity map as fallback. Hamsterdan keeps
one independently replayable Engine/History per PR and composes one shared
durable publication Worker plus a noncanonical runnable-instance hint index.

This boundary resolves the earlier false choice between one Worker thread per
PR and one service-wide Petri marking. It does not serialize application
objects, introduce a general ActivityScope container, or move scheduling into
Petrus. The host owns exclusivity and wake policy; Motus owns logical execution
and Attempts; the Net owns authorization and acceptance. Under that division,
dashboard/readiness operational retry topology was removed and the Net reached
40 places, 139 transitions, and 415 arcs. Applying the same boundary to
conversation publication then removed its final logical reissue transition,
reaching 40 places, 138 transitions, and 412 arcs. Broader lifecycle scopes
remain an independent study rather than a prerequisite.

## Required experiments

- retryable failure twice, then success under one stable invocation;
- non-retryable failure projects one typed terminal outcome;
- ambiguous provider completion is recovered by stable identity;
- successful terminal followed by projection crash reloads without another
  provider call;
- cancellation racing with publication still fails Hamsterdan's fresh fence;
- same-generation stale dashboard completion cannot acknowledge newer desire;
- timer self-loop receives a fresh delay across replay;
- scoped close racing with Activity completion is deterministic before any
  retirement transition is removed.

## Sources

- Petrus/Motus pinned source and tests at
  `henriquebastos/petrus@cb9cb63c3938c9318a99c9f605a0364b3c81bd6b`.
- Temporal Activity execution:
  <https://docs.temporal.io/activity-execution>.
- Temporal Python Activity timeouts and retries:
  <https://docs.temporal.io/develop/python/activities/timeouts>.
