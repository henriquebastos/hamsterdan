# Experiment 10 — Host simulation

Session S10-host, one of the five independently owned Experiment 10 module
sessions. Durable inputs were the ES-010 index, accepted
[`06-host-narrowing.md`](06-host-narrowing.md), accepted
[`07-step-contract.md`](07-step-contract.md), accepted
[`09-simulation-runtime.md`](09-simulation-runtime.md), and the ruled R3
decision,
[`Timeline and coroutine stepper share bounded execution`](../../../decisions/records/2026-08-26T2012Z-timeline-and-coroutine-stepper-share-bounded-execution.md).
The repository baseline was local `main` and `origin/main` at
`cdc685e8f2b979057f15e851c35c482322c87dac`, which contains accepted S9.

Method: inventory the maintained host lifecycle, scheduler, route authority,
restart, and cleanup seams; mount one isolated host module on S9's exact
structural module and `Timeline` interface; replace readiness with a strict
deterministic lifecycle adapter; and exercise two PRs through fair selection,
route revocation, a committed readiness result with a lost response, crash,
lookup-first reconstruction, and cleanup. R2's host/readiness ownership and
R3's frame boundary were fixed inputs, not questions reopened here. No real
readiness application, workflow, provider, agent, HTTP host, or whole
Hamsterdan was constructed.

## Verdict

The ruled host boundary can run alone under S9's generic runtime, but the
maintained production host does not yet expose the bounded lifecycle and fair
scheduler seams needed to mount it directly.

The spike at
[`spikes/10-host-simulation/host_simulation.py`](spikes/10-host-simulation/host_simulation.py)
provides the experimental evidence:

```text
durable HostStore
  route generations + instance catalog + fair enqueue sequence + selected turn
            │
            ├─ open generation ──▶ process-local readiness lifecycles
            │                              │
            ▼                              ▼
  one host ActionRef              strict readiness.progress(
    subject_selected                reason,
    instance_opened                 fresh lifecycle evidence,
    readiness_step_returned         stable turn operation)
    posture_recorded
    subject_requeued
    instance_closed
```

`HostSimulation` is the only composition root in the experiment. It constructs
the deterministic readiness factory and owns its process lifetime. The S9
runtime sees only generic module, action, leaf, fault, resource, and artifact
values; no change added host semantics to
`spikes/09-simulation-runtime/runtime.py`.

The runtime's public `Timeline` starts, executes, and finishes one host owner
step. The host yields at most one actual leaf through `context.call`, and only
for `readiness.progress`. The spike does not import or address
`CoroutineStepper`; S9 keeps it internal. A crash discards the suspended frame,
leaf exception, and held return while the durable selected turn and readiness
operation ledger remain authoritative.

## Maintained production inventory

The current source confirms S6 and S7's diagnosis rather than supplying a
direct simulation mount:

| Concern | Maintained interface | Observed ownership and limit |
|---|---|---|
| Process construction and custody | `HostService.__init__` in `src/hamsterdan/host/service.py` | Constructs provider clients, route registry, webhook custody, runnable index, agent route/runtime custody, Dispatch path, and one-PR applications. It is the sole concrete composition root, but it also retains readiness-specific construction and Activity resolution that R2 removes. |
| Lifespan | `create_app` in `src/hamsterdan/host/api.py` | Reconciles registration, starts one worker, then orders `stop`, worker completion, and `close`. This is a real production lifecycle edge, not a bounded host simulation step. |
| Current one-PR seam | `ReadinessApplication` in `src/hamsterdan/host/protocol.py` | Exposes `process_observation`, `reconcile`, `settle`, durable Activity drains, stop, inspection, and close. It has no R2 `ReadinessFactory.inspect/open` plus bounded `ReadinessLifecycle.progress` seam. S5 already rules this protocol for deletion. |
| Runnable custody | `RunnableIndex` in `src/hamsterdan/host/runnable.py` | Durably coalesces reason rows and atomically takes distinct due instances, ordered by `(first_due, instance)`. It has no durable enqueue sequence, selection lease, or tail cursor, so it is deterministic but does not implement S7's weak fairness contract. |
| Scheduling | `HostService.project_pending`, `_activate_instance`, `run_due`, and `pump` | Projects up to 1,000 rows, selects up to 100 subjects, and isolates exceptions per instance. `_activate_instance` can consume repeated arrival batches and call readiness drains; `pump` also executes up to 20 Activities and scans loaded applications. These are useful current behavior but not one-cut host steps. |
| Route revocation | `_guard_durable_activity` and `PrReadinessV5Application.inactive_activity_result` use | Current host recognizes durable publication gates and asks the readiness application to create operation-specific inactive results before provider calls. R2 instead requires host to supply fresh lifecycle evidence while readiness owns the workflow-declared outcome. |
| Restart discovery | `HostService.sweep` | Scans `applications/*/*/*/history.jsonl`, opens each inferred subject, and isolates one failure from later PRs. R2 requires a host-owned instance catalog rather than treating readiness History paths as process discovery authority. |
| Crash/restart evidence | maintained integration tests around death before webhook acknowledgement, lost runnable hints, and due-instance failure | Current state reconstructs from webhook, History, timer, Dispatch, and runnable stores. The tests support durable recovery but reach coarse host calls and sometimes patch inside them because the one-cut lifecycle is absent. |
| Cleanup | `HostService.stop`, `settle_terminals_for_shutdown`, `abort`, `close`, and `_release` | Stop prevents new durable Attempts; graceful close settles loaded instances; abort skips semantic settlement; `_release` attempts every owned resource even after one close failure. Loaded applications are still iterated in one call rather than one bounded `instance_closed` cut. |

The production inventory establishes a correspondence boundary: the spike uses
the accepted target lifecycle names because that interface does not exist in
maintained source. Importing `HostService` would have simulated today's coarse
drains and workflow-specific route handling rather than the ruled host module.

## Exact local simulation interface

The mounted object implements S9's unchanged structural contract:

```text
HostSimulation:
  name = "host"
  open(context) -> HostGeneration
  drop(generation) -> None
  close(generation) -> None
  resource_usage(generation | None) -> exact gauges

HostGeneration:
  command(name, payload, context) -> StrictJSON
  observe(name, payload, context) -> StrictJSON
  eligible_actions(context) -> tuple[ActionRef, ...]
  async step(action, context) -> StrictJSON
```

The host module exposes at most one eligible action. S9 may interleave that
action with other modules in Experiment 11, but it cannot select a PR or invent
a host action. The durable host store selects the next subject, retains the
selected turn across crash, and controls each following cut.

### Commands

| Command | Exact payload | Meaning |
|---|---|---|
| `register_route` | `route` | Create one active route at generation 1; exact replay is idempotent. |
| `register_instance` | `subject`, `route` | Bind one PR to an existing active route and create its deterministic readiness state. A contradictory binding or registration on a revoked route fails. |
| `wake` | `subject`, `reason`, `at_us` | Add or coalesce one bounded wake under a monotonic enqueue sequence. |
| `revoke_route` | `route` | Commit `active -> revoked`, advance the route generation once, and wake every bound subject on that route. |
| `readiness_close_failure` | `subject`, `enabled` | Configure only the deterministic adapter's cleanup failure used by the resource proof. |
| `stop` | no fields | Prevent new scheduling and make loaded lifecycles eligible for one-at-a-time graceful close. |

Unknown commands, missing or additional fields, unknown subjects/routes,
booleans used as integers, malformed identifiers, and invalid transitions raise
named host simulation errors. A generation rejects any action other than the
single `ActionRef` derived from durable state.

### Observations

| Observation | Exact payload | Detached result |
|---|---|---|
| `state` | none | Routes, subjects, selected turn, service order, loaded process resources, deterministic readiness counts/evidence, and bounded cleanup diagnostics. |
| `instance` | `subject` | One subject's route, custody generation, and last detached readiness result. |

Unknown observation names and unknown payload fields fail loudly. Observations
contain no credential, provider payload, workflow value, exception text, or
process-local callable.

### Faults

The local `HostSimulation.arm_fault` entry validates the point and payload
before delegating to `Timeline.fault`:

| Point | Exact payload | Effect |
|---|---|---|
| `readiness.progress.unavailable` | `subject` | The strict readiness call raises before committing an operation; host records a secret-free unavailable result and tail requeues that subject. |
| `readiness.progress.after_commit` | `subject`, `response_lost=true` | Readiness durably commits one operation result, then raises before the host receives it. |

S9 replay re-applies only faults that already passed the local entry. The
runtime remains generic and does not acquire a host fault catalog.

## Strict deterministic readiness adapter

The adapter implements only the lifecycle behavior the host needs to prove:

```text
factory.open(subject, lifecycle_view) -> lifecycle

lifecycle.progress(
  reason="runnable",
  lifecycle_evidence={
    route_generation,
    route_status,
    custody_generation,
  },
  operation=selected_turn_identity,
) -> detached result

lifecycle.close(abort | graceful | release)
```

It rejects unknown subjects, reasons, evidence fields, statuses, backward route
generations, close modes, and fault payloads. Every first operation records one
detached result under the host's stable selected-turn identity. Repeating that
identity returns `source="lookup"`; it cannot perform a second semantic
progress. An active route returns one `progressed/quiescent` result. A revoked
route returns one `waiting/route_revoked` result. This latter branch lives in
the readiness adapter, not in host scheduling, so the spike preserves R2's
ruling that host supplies lifecycle evidence but never manufactures a workflow
terminal.

The adapter is not a readiness model. It has no workflow state, Activity name,
typed terminal, provider truth, timer, History, Dispatch, or agent operation.
Its sole purpose is to make incorrect host calls observable and deterministic.

## Host cuts, fairness, and recovery authority

One service turn is disclosed as separate S7 cuts:

```text
subject_selected
  -> instance_opened                 when no process-local lifecycle is loaded
  -> readiness_step_returned         exactly one readiness leaf
  -> posture_recorded
  -> subject_requeued                tail retry or release
```

Graceful shutdown exposes one `instance_closed` per loaded lifecycle. A failed
close is recorded by error class, removes that process handle, and leaves the
next resource eligible. Abrupt `drop` attempts every process-local lifecycle
with mode `abort`; that nonsemantic generation cleanup is bounded by the exact
`host.loaded` resource limit. Retained host/readiness state survives either
path.

Fairness uses `(due_at_us, enqueue_sequence)` rather than lexical subject
identity. Selecting a subject clears its old queue position. An unavailable
result gets a fresh tail sequence, so subjects already due retain precedence.
The focused failure proof selected:

```text
PR 7 unavailable -> PR 8 progressed -> PR 7 retried and progressed
```

One continuously due PR therefore cannot reset itself ahead of a peer through
an immediate failure wake. Every selection, retry, route generation, and
selected turn remains in `HostStore`, outside the generation object.

For response loss, the readiness operation result and selected host turn are
both durable before process loss. The lifecycle object and suspended owner
frame are not. The new generation first opens a new lifecycle, then invokes
`readiness.progress` with the same turn identity. The adapter finds the retained
operation and returns lookup evidence. Only after that result does host record
posture and release the turn.

If the process does not crash after the response is lost, host first persists
the ambiguous result and advances the selected turn to `returned`. The next
cuts therefore record posture and tail-requeue the subject instead of calling
readiness again from the same selected phase. The queued subject retains only
the stable readiness operation identity. When selected again, it performs one
lookup of the committed result, records that recovered posture, and releases;
it does not create a second semantic readiness operation.

## Bounds

`DEFAULT_BUDGET` applies S9's generic hard bounds:

```text
operations             512
owner_steps            128
eligible_actions         8   # host emits at most one
leaf_calls              64   # one per readiness_step_returned
choice_draws            16
active_faults           16
generations             16
logical_time_us  1,000,000
journal_entries      2,048
artifact_bytes   2,000,000
```

The module supplies an exact resource-key union on every S9 boundary:

```text
host.routes                 <= 8
host.instances              <= 8
host.runnable               <= 8
host.loaded                 <= 8
host.readiness_operations  <= 64
host.cleanup_errors         <= 8
```

Commands admit one route, subject, wake, or stop transition. A step exposes one
action and affects at most one PR. The deterministic adapter performs one
operation lookup or one result commit. Graceful cleanup closes one lifecycle
per step. No call drains host, readiness, or all subjects to quiescence.

## Independent checker

`HostArtifactChecker` is used only for properties where a different derivation
can catch a correlated implementation error:

1. It derives finite-cohort fairness from artifact `wake` commands and
   `subject_selected` actions. It does not inspect enqueue sequences or
   `HostStore`; selecting one subject twice before all initially due peers have
   appeared fails the checker.
2. It reconstructs route status/generation from `register_route`,
   `register_instance`, and `revoke_route` commands, then compares that expected
   authority with every offered `readiness.progress` leaf payload. It does not
   read the module's route table or lifecycle evidence log.

Cleanup order, operation cardinality, strict input failures, and replay equality
use direct invariants instead of second implementations. A second cleanup or
readiness model would repeat the implementation rather than add independent
evidence.

## Meaningful failure and exact replay

The executable proof is
[`spikes/10-host-simulation/evidence.py`](spikes/10-host-simulation/evidence.py):

1. Register PR 7 and PR 8 on one active route and wake both at logical time 0.
2. Select PR 7, open its lifecycle, and offer one `readiness.progress` leaf for
   `turn:1` under route generation 1.
3. The readiness adapter commits the result for `turn:1`; the named occurrence
   fault loses its response.
4. Crash at Timeline phase `executed`, before the exception or result returns
   through the owner frame. Abrupt cleanup releases PR 7's process-local
   lifecycle.
5. Restart generation 2, reopen PR 7, and repeat `turn:1`. The adapter returns
   `source="lookup"`; PR 7 has one semantic progress.
6. Release PR 7's turn. PR 8 receives the next fair turn and progresses
   independently.
7. Revoke the route, advancing it to generation 2 and waking both bound PRs.
   PR 7 receives fresh revoked evidence; the readiness adapter records one
   blocked posture without another active-route progress.
8. Encode, strictly decode, and exactly replay the S9 artifact with a fresh
   `HostSimulation` builder. Run the independent checker against the decoded
   artifact.

Executed evidence:

```text
scenario              host-response-lost-route-revoked
operations            33
journal entries       71
artifact bytes        32,509
final generation      2
crash phases          executed
service order         PR 7, PR 8, PR 7
semantic progress     PR 7 = 1, PR 8 = 1
blocked after revoke  PR 7 = 1
lookup recoveries     PR 7 = 1
checker               1 fair cohort, 4 current-authority calls
abrupt cleanup        PR 7 lifecycle attempted once
journal digest        sha256:7627983d6782a005328f8738196cc912e30f1d0cd47d4ad2e1d6c13d314163f0
replay                exact
```

The encoded artifact contains no `ReadinessResponseLost` class name, exception
message, callable, frame, held leaf result, or owner return. Its recovery
authority is the durable host selection plus readiness operation ledger.

The cleanup contract separately loads both PR lifecycles, configures PR 7's
close to fail, stops the host, and executes two `instance_closed` cuts. PR 7
returns `failed`; PR 8 still closes on the next cut; the final loaded-resource
set is empty and the diagnostic contains only `ReadinessCloseFailed` plus the
subject identity.

### Pre-acceptance durable-turn correction

Parent review identified that the initial `ReadinessResponseLost` handler
returned an ambiguous cut before storing `selected.result` or changing the
selected phase. Without an immediate crash, the next eligible action was
therefore another `readiness_step_returned` call rather than the disclosed
posture cut. The correction routes the ambiguous failure-as-data through the
same durable `result` and `returned` transition as every other readiness
return. A single `retry_operation` on the subject carries the stable operation
identity across the fair queue.

The no-crash regression now proves this exact sequence:

```text
subject_selected(turn:1)
instance_opened
readiness_step_returned(ambiguous)
posture_recorded
subject_requeued(requeued)
subject_selected(turn:1)
readiness_step_returned(source=lookup)
posture_recorded
subject_requeued(released)
Waiting(next_at_us=None)
```

The final state has no selected turn or runnable subject, one readiness
operation, one semantic progress, one lookup, and exactly two
`readiness.progress` calls. The existing `executed`-phase crash proof remains
byte-for-byte unchanged: 33 operations, 71 journal entries, 32,509 encoded
bytes, and digest
`sha256:7627983d6782a005328f8738196cc912e30f1d0cd47d4ad2e1d6c13d314163f0`.

## Gaps requiring production seams

These are correspondence gaps for later Delivery, not changes authorized by
this experiment:

1. **Bounded readiness lifecycle.** The maintained `ReadinessApplication`
   protocol has coarse `process_observation`, `reconcile`, and `settle` methods.
   Production needs the accepted factory/inspection/lifecycle seam and one-cut
   `admit`, `progress`, `settle_terminal`, stop, and close behavior before the
   real host can replace the strict adapter.
2. **Fair runnable authority.** `RunnableIndex.take_due` orders equal-time work
   lexically and deletes due rows on selection. Production needs the S7 durable
   enqueue sequence or equivalent cursor, a recoverable selection lease, and
   tail requeue so a failed lexical-first PR cannot monopolize a small limit.
3. **One-cut host service.** `_activate_instance`, `run_due`, and `pump` still
   combine selection, application opening, multiple custody rows, readiness
   drains, posture, acknowledgement, and Activity execution. Production needs
   the separate host cuts exercised here and only finite loops over them.
4. **Host-owned instance discovery.** `sweep` still discovers PRs from readiness
   `history.jsonl` paths. Production needs S6's bounded durable instance catalog
   and readiness-owned detached inspection.
5. **Route revocation ownership.** Current durable-publication handling still
   recognizes Activity gates and participates in inactive-result construction.
   Production must pass fresh route/custody generations to readiness and stop
   decoding or manufacturing workflow outcomes.
6. **Bounded shutdown.** Current `_release` correctly attempts later resources
   after one failure, but one call walks all loaded applications and process
   resources. Production needs a configured shutdown page/cut budget, one
   readiness lifecycle close per `instance_closed`, and explicit abort after
   budget exhaustion while retained semantic work remains durable.

The S7 Petrus bounded-load and split Activity-execution gaps do not arise inside
this host-only adapter, remain open for readiness/workflow correspondence, and
are not hidden by this result.

## Correspondence limits

- The durable stores are in-memory experiment objects retained across S9
  generation loss. SQLite durability, filesystem safety, and operating-system
  process death remain production correspondence evidence.
- The readiness lifecycle is strict and deterministic but intentionally has no
  workflow semantics. This proof cannot establish workflow correctness,
  provider-effect recovery, Activity typing, timer behavior, or readiness
  durability.
- The Timeline records interleavings; it does not claim real thread/process
  concurrency, lock behavior, cancellation timing, or wall-clock deadlines.
- No GitHubKit client, credential, webhook payload, Pi runtime, agent request,
  Petrus Engine/History/Dispatch/Worker, or real readiness application enters
  the spike.
- Route revocation proves fresh host evidence and ownership direction. It does
  not prove a particular workflow blocked terminal; that R2 behavior belongs to
  readiness/workflow simulation and remains fixed.
- Resource gauges prove named counts within this scenario and hard refusal at
  configured S9 limits. They do not measure production memory, file descriptors,
  database rows, payload bytes, or shutdown time.
- This is a local host simulation. Experiment 11 owns composition with the
  other local simulations and any cross-module checker.

## TDD and verification

The first focused run failed at import because `host_simulation.py` did not yet
exist. After implementing the smallest mounted host contract, five behavioral
contracts passed. A sixth test was added red before `evidence.py` existed, then
passed with the executable retained scenario. Parent pre-acceptance review then
supplied the no-crash response-loss counterexample. The seventh test failed
because the expected recovered call observed `Waiting`: the old sequence had
consumed the lookup before posture/requeue. It passed after the durable result,
returned phase, and queued retry identity were implemented.

Focused simulation checks:

```text
PYTHONPATH=../09-simulation-runtime:. uv run --frozen python -m unittest -v test_host_simulation.py
Ran 7 tests in 0.039s
OK

uv run --frozen ruff check host_simulation.py evidence.py test_host_simulation.py
All checks passed!

uv run --frozen ruff format --check host_simulation.py evidence.py test_host_simulation.py
3 files already formatted

uv run --frozen ty check --project /home/user/workspace/repo \
  --extra-search-path ../09-simulation-runtime \
  host_simulation.py evidence.py test_host_simulation.py
All checks passed!
```

Repository checks:

```text
scripts/check quick
10 passed in 1.85s

scripts/check full
9 relay tests passed
44 demo/live tests passed
source distribution and wheel built
1165 Python tests passed in 96.32s
```

Only these paths changed:

```text
docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/10-host-simulation.md
docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/spikes/10-host-simulation/evidence.py
docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/spikes/10-host-simulation/host_simulation.py
docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/spikes/10-host-simulation/test_host_simulation.py
```

No ES-010 index, production source, maintained test, configuration, roadmap,
decision, debt, worklog, runtime state, Experiment 11, or R4 surface changed.

## Exit assessment

The host module runs alone on S9's exact Timeline/module interface with strict
commands, observations, local fault admission, named resource bounds, one-cut
actions, and a strict readiness lifecycle adapter. Two independent PRs make
bounded fair progress; route revocation is fresh monotonic authority supplied
to readiness; a committed readiness result with a lost response survives an
`executed`-phase crash and recovers lookup-first without a frame; without a
crash the ambiguous result advances through posture, fair requeue, and one
lookup recovery without duplicate semantic progress; graceful and abrupt
cleanup are bounded and continue after a local close failure; and the meaningful
failure artifact replays exactly under an independent fairness and authority
checker.

Experiment 10's host exit criterion is met within the correspondence limits
above. The result awaits Navigator acceptance. It does not rule the combined
Experiment 10 design or checkpoint R4.
