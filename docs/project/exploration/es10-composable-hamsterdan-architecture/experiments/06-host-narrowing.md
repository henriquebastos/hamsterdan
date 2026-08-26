# Experiment 6 — Host narrowing

Session S6. Durable inputs: the ES-010 index and the accepted S5 record,
[`05-readiness-tree.md`](05-readiness-tree.md). Source inspected at commit
`d5d7f06`: `host/service.py`, `host/api.py`, `host/__main__.py`,
`host/runnable.py`, `host/agenticus.py`, `host/pi_a2.py`,
`host/publication_qualification.py`, and the process-wide parts of
`host/binding.py` and `host/protocol.py`. Immediate consumers in
`github_app/config.py`, `github_app/auth.py`, `github_app/routing.py`,
`github_app/webhooks.py`, `agents/__init__.py`, `agents/pi.py`, and
`operator.py` were inspected only where needed to establish ownership. Targeted
existing host tests were read where they state route-revocation, independent-PR,
scheduler, restart, inspection, and qualification behavior.

Method: remove the S5 readiness tree from `HostService`, classify what remains
as process ownership or provider/agent implementation, apply the deletion test
to each proposed host module, and trace startup, one custodied webhook, route
revocation, agent-route repair, inspection, scheduling, and shutdown. S5's
readiness tree and S4's eight effect capability groups are inputs, not questions
reopened here.

## Verdict

The target host is a supervisor over process resources and readiness lifecycle
objects. It does not know workflow Activity names, terminal variants, Petrus
History records, Dispatch queues, or readiness grants.

```text
host/
  __init__.py                 # empty package marker; no facade
  __main__.py                 # CLI edge and process construction
  api.py                      # HTTP/lifespan adapter
  composition.py              # construct one readiness lifecycle from concrete effects
  service.py                  # process supervision and bounded multi-instance scheduling
  instances.py                # durable process-wide instance discovery
  inspection.py               # bounded process-wide detached inspection
  runnable.py                 # reconstructible per-instance wake hints
  qualification.py            # optional one-shot production correspondence faults
  agents/
    routing.py                # process route selection and operation-route custody
    pi.py                     # Pi runtime, direct-key, and opaque-state custody
  simulation/                 # Exp 10 owner; no production content from S6
```

The corresponding live support outside this tree is explicit:

```text
github_app/
  config.py                   # provider registration, portfolio, and secret-file input
  auth.py                     # App and installation client/token custody
  routing.py                  # provider installation/repository registry implementation
  webhooks.py                 # signature verification, normalization, and inbox implementation

agents/
  pi.py                       # credential-free protocol adapter
  pi_workspace.py             # S5-ruled credential-free workspace implementation

operator.py or operator/
  qualification.py            # bounded human-operated setup qualification
```

Host constructs and owns the lifetime of the GitHub objects even though their
implementation stays in `github_app`. Provider-specific validation does not
move into host merely because host holds the process resource. Likewise, host
owns the Pi runtime and its credentials, while the credential-free Pi request
and workspace adapters stay in `agents`.

`composition.py` is the only host module allowed to know both concrete provider
or agent implementations and the readiness construction seam. `service.py`
retains only the resulting readiness lifecycle object. A strict deterministic
readiness adapter can therefore replace the factory in host simulation without
constructing GitHub, agents, Petrus, or workflow.

## Current responsibility classification

| Responsibility | Current owner | Target owner and disposition |
|---|---|---|
| CLI parsing and process construction | `host/__main__.py` | Retain the thin edge in `host/__main__.py`; it reads module-owned configuration, constructs resources in dependency order, and selects serve/validate/inspect/operator-safe commands |
| HTTP ingress and lifespan | `host/api.py` | Retain in `host/api.py`; it bounds the request, delegates signed receipt to the GitHub webhook implementation, starts host supervision, and orders stop/close |
| GitHub registration and portfolio configuration | `github_app/config.py` | Retain provider-specific validation in `github_app`; host consumes one immutable snapshot and owns restart application |
| GitHub private key and webhook secret input | `github_app/config.py` plus `host/service.py` | File validation and provider credential values stay in `github_app`; `__main__`/composition transfer them only to GitHub clients and webhook custody. They never enter readiness construction values |
| Installation clients and token cache | `github_app/auth.py` | Retain in `github_app`; host owns one process lifetime and constructs repository-narrow operation clients for effect adapters |
| Provider route registry | `github_app/routing.py` | Retain the provider implementation in `github_app`; host owns reconciliation, route-generation observation, and lifecycle wake policy |
| Signed webhook normalization and durable inbox | `github_app/webhooks.py` | Retain the provider implementation in `github_app`; host owns its process lifetime, row disposition, subject scheduling, and the lifecycle view supplied to readiness |
| One-PR concrete construction | `host/service.py::_application` | Move to `host/composition.py`; construct S5 effects and readiness lifecycle, but retain no application cache or scheduling policy |
| Loaded-instance cache, locks, activation, sweeps, and worker | `host/service.py` | Narrow into `host/service.py`; use the readiness lifecycle seam and host-owned instance catalog rather than readiness files or protocol plumbing |
| Persisted-instance discovery | History path globbing in `HostService.sweep`, `reconcile_one`, and `work_state` | Replace with `host/instances.py`; no workflow file name or History shape is a discovery contract |
| Runnable hints and timer posture | `host/runnable.py` plus readiness-specific calls in `service.py` | Retain `RunnableIndex` mechanism in `host/runnable.py`; host records only detached readiness wait posture and never queries unresolved workflow publications |
| Agent composition and global operation-route custody | `host/agenticus.py` | Split to `host/agents/routing.py`; remove Petrus History decoding and readiness terminal knowledge |
| Credential-free routed agent calls | `host/agenticus.py::RoutedAgentRunner` | Move to S5's `readiness/effects/agents.py`; it adapts readiness work through the host-owned operation-route capability and credential-free `agents` runner |
| Pi installation, API-key, opaque connection state, runtime construction | `host/pi_a2.py` | Move intact by responsibility to `host/agents/pi.py`; this is trusted process and secret custody |
| Pi protocol and workspace execution | `agents/pi.py`, `host/pi_workspace.py` | Keep protocol adapter in `agents/pi.py`; move workspace implementation to `agents/pi_workspace.py` as ruled by S5 |
| Health and detached work posture | `HostService.health`, `work_state`, and `subject_state` | Aggregate in `host/inspection.py`; service supplies host-owned counters and readiness supplies detached per-instance inspection values |
| Raw one-instance History inspection | `host/__main__.py::inspect_instance` | Delete the host History decoder. The host inspector selects the cataloged subject and asks readiness's lifecycle/factory inspection seam for a bounded detached projection |
| Whole-state topology preflight | `host/binding.py::preflight_v5_state` | Delete with compatibility policy. Host validates its own catalog and stores; readiness validates each bound root it opens |
| Host readiness protocol and Activity resolver | `host/protocol.py`, `_resolve_activity`, `_guard_durable_activity` | Delete as ruled by S5. The lifecycle seam below replaces it; no host Activity lookup survives |
| Production qualification fault injection | `QualificationFault` inside `host/service.py` | Move to `host/qualification.py`; host composition injects its exact one-shot callbacks into concrete agent/publication adapters |
| Historical publication qualification record | `PublicationQualification` in `host/publication_qualification.py` | Delete from the replacement tree: it has no maintained source consumer, only historical qualification tests |
| Live atomic qualification setup evidence | setup values/functions in `host/publication_qualification.py`, consumed by `operator.py` | Move beside the human-operated command to `operator/qualification.py` (or a coherent `operator.py` until that file earns a package split); it is neither host supervision nor readiness execution |
| Shutdown | `api.py`, `HostService.stop/close/abort`, and direct application methods | Host retains process ordering; each readiness lifecycle receives stop and bounded terminal-settlement calls, then all owned resources close even if one close fails |

## Host-to-readiness construction seam

These are capability-signature pseudocode, not a recommendation for Python
`Protocol` classes. the engineering style contract owns the concrete dependency-injection style.

```text
ReadinessFactory.inspect(subject, root) -> ReadinessInspection

ReadinessFactory.open(
  subject,
  root,
  workflow_settings,
  effects,                 # the accepted S4 capabilities
  lifecycle_view,          # fresh host route/custody evidence
  clock,
) -> ReadinessLifecycle
```

`host/composition.py` owns the production factory implementation. Host
simulation injects a strict deterministic factory with the same calls.
Readiness simulation bypasses this host factory and constructs the S5
application directly from deterministic S4 effects and lifecycle evidence.

The construction values contain no HTTP request, GitHubKit object, installation
token, Pi runtime, webhook database, runnable index, Engine, Dispatch, Worker,
or simulation truth. Concrete S5 effect adapters may close over repository-
narrow GitHub and agent collaborators; the readiness application sees only
readiness-owned capabilities.

The factory has a read-only `inspect` operation because startup must understand
retained readiness state before selecting a process-wide agent route. That
inspection is readiness-owned: it may decode its own History and custody, but
it returns only bounded detached values such as subject binding, lifecycle
posture, wait posture, and agent-operation posture. Host does not gain a generic
History reader.

## Lifecycle and custody interface

The lifecycle seam has two parts: a fresh host-owned view that readiness may
consult at its authority cuts, and bounded commands/results exchanged by the
supervisor.

```text
LifecycleView.observe(subject, tracked_delivery=None) -> LifecycleEvidence

LifecycleEvidence:
  route_generation       monotonic host generation
  route_status           active | revoked
  custody_generation     monotonic same-subject custody generation
  earliest_pending       delivery identity | none
  tracked_delivery       unknown | pending | failed | terminal | none
```

The generations prevent an active → revoked → active route change, or a
pending → terminal custody change, from looking unchanged across a fresh
authority read. Host advances the relevant generation whenever route or
same-subject custody state changes. Readiness compares fresh evidence around
provider evidence as required by S4 authority composition; it does not read
host tables.

`tracked_delivery` exists for a specific retained blocker. For example, a
review may durably defer on delivery `D2`. On reconstruction, readiness asks
whether `D2` is terminal through this view. It does not query `inbox`, and host
does not inspect the review loop to decide what clearing `D2` means.

```text
ReadinessLifecycle.admit(delivery, lifecycle_evidence) -> AdmissionResult
ReadinessLifecycle.progress(reason, lifecycle_evidence) -> ProgressResult
ReadinessLifecycle.inspect() -> ReadinessInspection
ReadinessLifecycle.stop() -> None
ReadinessLifecycle.settle_terminal() -> ProgressResult
ReadinessLifecycle.close(mode) -> None
```

S7 owns the exact `progress`/`settle_terminal` step vocabulary, dispositions,
and cuts. S6 fixes their ownership and bounds: one call cannot drain a workflow,
run an arbitrary number of Activities, or process another PR.

The detached results needed by host are:

```text
AdmissionResult:
  delivery_id
  disposition            accepted | already_accepted | retained
  posture                 next readiness wait/wake posture
  settled_agent_routes    bounded operation identities

ProgressResult:
  disposition            progressed | waiting | terminal | unavailable
  posture                 next readiness wait/wake posture
  settled_agent_routes    bounded operation identities

ReadinessInspection:
  subject
  binding_status
  lifecycle_posture
  work_posture
  agent_routes            bounded operation -> live | settled
  error_class             closed, secret-free value | none
```

The names are candidate semantic fields, not frozen schemas. They establish
that host needs no Activity definition, workflow transition, typed terminal,
History record, or private runtime dictionary.

### Custody handoff

One webhook follows this order:

```text
GitHub webhook implementation verifies, normalizes, and durably accepts D1
  -> host inbox custody identifies PR subject S and wakes S
  -> host claims D1 as the due head for S
  -> host reads LifecycleEvidence for S
  -> readiness.admit(D1, evidence)
  -> readiness durably retains manifest/grant and folds D1, or reports retained
  -> host acknowledges D1 only after AdmissionResult says accepted/already_accepted
  -> host records returned posture and agent-route settlements
```

The host inbox remains canonical until readiness returns its exact delivery
identity as accepted. A crash after readiness commit but before host
acknowledgement replays `D1`; readiness returns `already_accepted`, and host can
acknowledge without provider reconciliation. A readiness exception leaves `D1`
pending under the host's bounded retry policy. This preserves the current
host-before-workflow authority cut without a shared database.

Host passes one due delivery at a time. Readiness owns canonical fold order for
the accepted delivery; host owns row order and does not send `D2` before `D1`
leaves pending custody. S7 may define a larger bounded batch only if it retains
these identities and acknowledgement cuts.

### Route revocation

Current host behavior is workflow-specific:

```text
route revoked
  -> host recognizes reply_gate / dash_gate / announce_gate
  -> host decodes each invocation
  -> host fabricates ReplyBlocked / DashBlocked / ABlocked
```

The target seam is:

```text
route generation G becomes revoked
  -> host commits route status and wakes every cataloged subject on that route
  -> readiness observes LifecycleEvidence(route_status=revoked, generation=G)
  -> readiness performs its own lifecycle/authority handling
  -> host records only detached posture and route settlements
```

Host never resolves an Activity name and never manufactures a workflow
terminal. Which readiness terminal or lifecycle outcome queued publications
receive after revocation remains an R2 ruling below. The host seam supports the
ruling without predetermining it.

Revocation also fences construction: a new unbound subject is not opened on a
revoked route. A previously cataloged and readiness-bound subject may be opened
in inspection/recovery mode so readiness can settle retained state without a
provider call. The readiness factory validates its own subject binding; host
does not infer validity from the presence of `history.jsonl`.

## Agent-route lifecycle without host History decoding

Current `AgentRouteStore.activate()` scans every History and knows all of:

- `execute.review`, `execute.conversation`, `execute.repair`,
  `execute.change`, `review.agent`, and `mut.git_gate` transition names;
- review terminal variants including `RoundDeferred`;
- mutation terminal variants including `FaultM`; and
- how to derive a mutation agent operation from a workflow `op_key` and binding.

`readiness.runtime` separately performs nearly the same terminal scan. This is
duplicate workflow interpretation under a process-wide store.

The target keeps global route custody but reverses the information flow:

```text
startup
  -> host InstanceCatalog enumerates subjects and roots
  -> ReadinessFactory.inspect(subject, root) reports bounded agent-route posture
  -> host AgentRouteStore idempotently marks reported settled operations
  -> unresolved operation routes fence an incompatible process route
  -> host atomically activates the selected process route
  -> host constructs readiness lifecycles and begins scheduling

runtime
  -> readiness folds an agent terminal under workflow rules
  -> ProgressResult reports the resulting settled operation identity
  -> host AgentRouteStore idempotently settles that identity
```

`RoundDeferred` and `FaultM` remain live because readiness reports them as
live; host does not know those names. Conversation classification settlement,
review settlement, and mutation settlement use the same operation-posture
output. A crash between the readiness fold and route-store settlement is
repaired by readiness inspection on restart. A crash in the opposite direction
is harmless because host settlement is idempotent and follows readiness's
durable report.

The operation-route store retains only process semantics: immutable operation
to composition binding, active composition, live/settled status, and atomic
refusal of an incompatible route while live operations exist. Deleting
workflow decoding also removes its need to read readiness bindings or paths.

## Process-wide discovery and inspection

### Instance catalog

Current discovery uses `applications/*/*/*/history.jsonl`. That makes one
workflow file both process registry and workflow authority. The target
`InstanceCatalog` is a host-owned durable mapping:

```text
subject -> relative readiness root + provider route identity
```

Host registers the subject before the first readiness open. A crash after
registration but before readiness initialization leaves a discoverable entry;
the readiness factory decides whether the root is new, bound, incomplete, or
invalid. The catalog does not copy head, base, policy, workflow phase, History
identity, Activity state, or readiness authority.

On restart, host enumerates the catalog under an explicit bound and asks the
readiness factory to inspect each entry. A missing, unsafe, contradictory, or
uninspectable root degrades that subject and remains visible; host does not
silently delete it or infer a replacement from directory contents. The
replacement tree has no old-topology preflight or filesystem fallback.

Deleting `instances.py` would force host back to scanning readiness internals
or require another process owner to duplicate discovery. It therefore earns a
deep module separate from provider routing and runnable hints.

### Inspection

`host/inspection.py` composes detached process facts:

- configured/reconciled installation and repository counts;
- webhook inbox counts and bounded failures;
- cataloged, loaded, degraded, and terminal instance counts;
- runnable hint counts and earliest due instant;
- process agent-route posture;
- scheduler error classes; and
- bounded readiness-provided inspection for one selected subject.

It owns safe file selection, output bounds, secret-free error classification,
and JSON-facing shape. It does not parse History. Readiness owns the projection
from its records into unresolved work, lifecycle, authority, and agent-route
posture. The current `inspect-instance` user capability survives, but its
implementation becomes host aggregation over a readiness-owned detached
inspection rather than a second History codec.

Deleting `inspection.py` would put JSON/operator shape and cross-resource
aggregation back into `__main__` and `HostService`. It therefore survives the
deletion test. It remains read-only and must not construct a running host merely
to inspect state.

## Independent progress and scheduler bounds

The current `RunnableIndex` has useful properties worth retaining: wake reasons
coalesce by instance/kind/identity, timer posture is replaceable, corruption is
reconstructible, and due subjects are selected deterministically. Current host
drivers are nevertheless too coarse for the target:

- `_activate_instance` may drain every pending row for one subject;
- `application.settle()` contains nested 500-step readiness drains;
- `pump()` runs custody projection, up to 100 due instances, then up to 20
  durable Activities across loaded applications; and
- immediate failure re-wakes can repeatedly precede still-due subjects when a
  caller uses a smaller limit.

S6 fixes these multi-instance invariants; S7 fixes exact step values and
budgets:

1. One readiness lifecycle object owns exactly one PR subject and cannot make
   progress for another subject.
2. One host scheduling turn selects at most a configured number of distinct
   subjects and invokes at most one bounded readiness progress call per selected
   subject.
3. A subject with pending host custody cannot execute an effect against an
   older readiness grant. Other subjects remain eligible.
4. A failed or immediately re-woken subject is ordered behind already-due
   unclaimed subjects. Durable enqueue sequence or an equivalent cursor must
   prevent one degraded PR from monopolizing a bounded scheduler limit.
5. Readiness posture is a hint, not canonical workflow state. Lost or corrupt
   hints reconstruct from the instance catalog plus readiness inspection.
6. Scheduler failure is isolated and classified per subject. It re-wakes only
   that subject and does not stop later selected subjects.
7. No host call loops until global quiescence. Convenience sweeps and drains are
   explicitly bounded loops over the same production calls used by simulation.
8. Every custody query, catalog scan, readiness inspection, scheduler claim,
   shutdown settlement, and returned operation list has an explicit count or
   byte bound.

Concrete two-PR scenario:

```text
PR 7 has deferred webhook D7 and a repeatedly failing readiness step
PR 8 has a due timer

turn 1: host calls PR 7 once; failure is retained and PR 7 is requeued behind PR 8
turn 2: host calls PR 8 once; its timer progresses
turn 3: PR 7 may retry when eligible
```

No fairness claim depends on thread parallelism. Production and simulation use
recorded bounded selections; real process/thread concurrency remains separate
correspondence evidence.

## Startup and shutdown routes

### Startup

```text
parse host/provider/agent configuration and secret-file paths
  -> validate host-owned catalog/runnable/route stores
  -> construct GitHub App clients, provider route registry, and webhook custody
  -> reconcile one complete configured provider portfolio before workers start
  -> inspect every bounded catalog entry through ReadinessFactory.inspect
  -> repair process agent-route custody from readiness-owned operation posture
  -> activate the selected process agent route
  -> construct Pi runtime and one-PR readiness lifecycles as they are activated
  -> project reconstructible wake hints
  -> start HTTP ingress and bounded supervisor loop
```

No readiness effect runs before portfolio replacement and agent-route
activation complete. A failure before service construction closes every
independently created resource. A catalog/readiness contradiction fails closed
for that subject and is visible in health; policy may fail the whole startup
when process route safety cannot be established.

### Shutdown

Graceful shutdown stops ingress admission and scheduler claims, calls `stop()`
on loaded readiness lifecycles so no new effect Attempt starts, and then spends
a configured number/deadline of `settle_terminal()` calls across subjects with
the same fairness rule. It closes every readiness lifecycle and process
resource even when one settlement or close fails. Unsettled semantic work stays
durable for restart.

Abrupt abort performs no semantic settlement. It closes local handles and
relies on retained host custody, readiness state, provider operation identity,
and lookup-first recovery. Neither path claims to cancel an effect already
accepted by an external system.

## Deletion test

### `composition.py`

Deleting it would return repository-narrow GitHub client construction, agent
route adaptation, S4 effect construction, qualification callbacks, and
readiness factory arguments to `HostService`. It survives as the sole
one-instance concrete composition module. It owns no scheduling or workflow
policy.

### `service.py`

Deleting it would make HTTP lifespan, simulation, or operator code reproduce
portfolio startup, custody dispatch, activation, fairness, reconciliation,
failure isolation, and shutdown ordering. It survives as process supervision,
but loses provider projection, readiness construction details, Activity
resolution, History discovery, and workflow settlement.

### `instances.py`

Deleting it would make workflow files the process discovery API again. It
survives as the minimal durable catalog, distinct from provider routes,
readiness subject binding, and runnable hints.

### `inspection.py`

Deleting it would mix read-only bounded aggregation into the CLI or service.
It survives. The raw History decoder does not: readiness's own inspection
projection replaces it.

### `runnable.py`

Deleting it would require rescanning every readiness instance on every process
tick or treating readiness wait posture as process state. It survives as
reconstructible hints with the fairness invariant above. Its exact target
schema waits for S7.

### `qualification.py`

The disabled-by-default production fault controller spans agent and comment
effect construction, is exact one-shot process state, and is used only for real
correspondence qualification. Deleting the module would put environment
parsing and fault matching back in `service.py`. It therefore survives as an
optional host composition concern, not a workflow or simulation fault model.

The old `PublicationQualification` record fails the deletion test because no
maintained source calls it. It dies with replacement-tree historical test
cleanup. Atomic setup qualification survives, but beside its sole maintained
consumer in operator support rather than under host.

### `host/agents/routing.py` and `host/agents/pi.py`

The route module hides process-wide immutable operation/composition custody and
atomic route activation. The Pi module hides secret input, opaque retained
connection state, runtime construction, and erasure. Deleting either leaks
process authority into readiness or credential-free agent code. They remain
separate because route custody does not require a Pi runtime and Pi custody does
not interpret readiness operations.

## Multi-instance invariants

1. Every cataloged subject has one deterministic readiness root and at most one
   loaded lifecycle per host process.
2. Readiness validates subject/root binding; host catalogs and selects but does
   not decode workflow authority.
3. Provider route generation and same-subject custody generation are fresh
   host evidence available at every readiness authority cut.
4. Host acknowledges a webhook only after readiness durably accepts that exact
   delivery identity and returns posture successfully.
5. Route revocation prevents new unbound activation and wakes retained bound
   instances; host never creates their workflow outcome.
6. One PR's custody, readiness failure, timer, agent operation, or corrupt hint
   cannot prevent another due PR from receiving a bounded turn.
7. Agent operations bind immutably to one process composition until readiness
   reports the operation settled; host never infers settlement from workflow
   names or result variants.
8. Runnable and health state are reconstructible process projections, not
   workflow authority.
9. Credentials remain in host-owned provider/Pi resources and concrete effect
   adapters. They never enter lifecycle values, readiness inspection, workflow,
   agent requests, logs, or simulation commands.
10. Every external effect remains at-least-once with stable operation identity,
    a fresh authority cut where required, and lookup-first recovery.
11. Shutdown bounds new claims and settlement work; process exit does not imply
    remote cancellation or exactly-once completion.
12. Host simulation can replace readiness with a strict adapter that rejects
    unknown subjects, calls, evidence generations, and result shapes. Readiness
    simulation constructs readiness without host, HTTP, provider registry,
    process route store, or runnable index.

## R2 questions kept open

S6 fixes who reports route/custody state and who interprets workflow outcomes.
It does not choose the following behavior.

### Review provider-evidence failure

Plain question: when final provider evidence for an agent review cannot be
obtained, should workflow receive a new typed terminal or continue receiving the
current generic failure path?

Concrete example: the agent returns a review, but the final head/authority read
times out before readiness can prove that the result still addresses the PR.

- Add a typed workflow terminal: the Net can distinguish unavailable evidence
  from agent inability, at the cost of a new durable workflow branch.
- Keep the generic failure: the tree stays smaller, but workflow cannot state
  or test that distinction directly.

S4 left this open. S6 adds no preference because host narrowing supplies no new
semantic evidence about the right workflow behavior.

### Deliberately weaker publication fencing

Plain question: should reply, reminder, and dashboard publication retain their
current weaker authority fence, or use the full current grant/head/base/policy
fence used by findings and readiness announcement?

Concrete example: the PR head moves after a reminder is requested but before
the comment call. Today the reminder may still publish under stable operation
identity, while a readiness announcement must prove the exact current grant.

- Preserve the asymmetry: conversational continuity remains available across
  some authority movement, but publication policy is intentionally nonuniform.
- Apply the full fence: all publications share stronger stale-authority
  rejection, but reminders/replies/dashboard may be suppressed after movement.

S4 deliberately left this open. The lifecycle view supports either ruling.

### Queued publication after route revocation

Plain question: what readiness-owned outcome should an already-requested
publication receive when its installation or repository route is revoked?

Concrete example: `DashReq` is durable, the installation is suspended, and the
response was not yet claimed. Current host fabricates `DashBlocked` without a
provider call.

- Preserve operation-specific blocked terminals inside readiness: current
  visible behavior is retained, but readiness must own the mapping for every
  affected Activity.
- Close/cancel through readiness lifecycle semantics: revocation becomes one
  lifecycle boundary and late terminals are quarantined or folded according to
  that boundary, but current blocked-terminal behavior changes.

Recommendation for R2: decide this with the workflow tree in view. Regardless
of outcome, reject a third option where host decodes Activity work and creates
the terminal; that violates the now-evidenced ownership seam.

## Exit assessment

Every responsibility named by experiment 6 has one target owner. The host tree
retains trusted process construction, credentials, webhook custody lifetime,
provider and agent route custody, durable discovery, bounded runnable work,
multi-instance activation, reconciliation, detached inspection, qualification
faults, and shutdown. One-PR Petrus execution, workflow interpretation,
authority-grant meaning, typed Activity outcomes, and agent-terminal
classification remain in the accepted S5 readiness tree.

The factory and lifecycle seams remove shared webhook-table access and host
History decoding. Monotonic route/custody evidence carries revocation and
same-PR blockers without making them a ninth S4 effect capability. Readiness
reports agent-operation posture after its own durable interpretation. The
instance catalog removes History-file discovery, while host inspection
aggregates readiness-owned detached projections. Scheduler invariants preserve
independent PR progress and require bounded fair turns without preempting S7's
exact step design.

A strict host simulation can replace readiness with deterministic lifecycle
objects and exercise two PRs, route revocation, fair scheduling, crash, and
resource cleanup. A readiness simulation can construct the S5 application from
typed effects and lifecycle evidence without host. Experiment 6 therefore
meets its exit criterion. S4's review-failure and publication-fencing questions,
plus the exact readiness outcome for queued work after revocation, remain
visible for checkpoint R2; R2 is not ruled by this record.
