---
status: Thickening
opened: 2026-08-10
navigator: Henrique
---

# ES-001 — Simplify the Petri Net at the Motus boundary

## Inquiry

Which parts of Hamsterdan's PR-readiness Petri Net are product workflow, which
are durable asynchronous-call semantics, and which are execution mechanics
that should be supplied by Petrus or Motus as reusable behavior or
configuration?

The analysis compares the current Hamsterdan topology with Petrus/Motus at the
pinned revision `116b0ddc460c0e04d4ad40c077158bd3498a4860` and uses Temporal's
Activity execution model as a design reference rather than a framework to copy.

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
  `henriquebastos/petrus@116b0ddc460c0e04d4ad40c077158bd3498a4860`.
- Temporal Activity execution:
  <https://docs.temporal.io/activity-execution>.
- Temporal Python Activity timeouts and retries:
  <https://docs.temporal.io/develop/python/activities/timeouts>.
