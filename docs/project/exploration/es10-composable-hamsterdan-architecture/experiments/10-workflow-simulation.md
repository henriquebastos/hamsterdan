# Experiment 10 — workflow simulation

Session S10 workflow fan-out. Durable inputs: the ES-010 index, accepted
[`09-simulation-runtime.md`](09-simulation-runtime.md), accepted
[`03-workflow-shape.md`](03-workflow-shape.md), accepted
[`07-step-contract.md`](07-step-contract.md), and the fixed R3 decision,
[`Timeline and coroutine stepper share bounded execution`](../../../decisions/records/2026-08-26T2012Z-timeline-and-coroutine-stepper-share-bounded-execution.md).
The repository baseline was local `main` and `origin/main` at
`cdc685e8f2b979057f15e851c35c482322c87dac`, which contains accepted S9. The
Petrus project pin was `44cac5ff48ac371ebae56323941983f30db13c0d`.

Method: mount one isolated workflow module on S9's exact structural module
interface; use the accepted S3 workflow package and real Petrus Engine,
History, Dispatch, and Activity interfaces; drive one failed-run observation
through an Activity request and typed terminal fold; lose the process-local
frame at the committed request cut; reload only from retained state; and
exactly replay both the recovery scenario and a checker-detected semantic
failure. Tests were written first and initially failed because the workflow
module did not exist. No production source or maintained test was changed.

## Verdict

The accepted workflow shape can run alone under S9's runtime interface. The
candidate at
[`spikes/10-workflow-simulation/workflow_simulation.py`](spikes/10-workflow-simulation/workflow_simulation.py)
turns strict observation commands into real `Engine.deliver()` calls, exposes
only workflow-owned `advance` actions, executes one real `Engine.advance()` per
S9 owner step, reconstructs pending Activity dispatch through `Engine.load()`,
and folds one real typed terminal. Its executable contract is
[`spikes/10-workflow-simulation/test_workflow_simulation.py`](spikes/10-workflow-simulation/test_workflow_simulation.py).

The independent checker also found a correspondence gap: a typed
`RerunLanded` whose `op` differs from the requested operation still reaches the
S3 terminal fold. A future production boundary must own and enforce that
correlation before admitting a terminal. This session does not choose that
owner or change production.

This is sufficient workflow-local evidence for Experiment 10's exit criterion:
one meaningful workflow failure is generated and exactly replayed without
constructing readiness, GitHub, agents, host, or whole Hamsterdan. It is not
evidence for R4 or production promotion.

## Real interface and cut inventory

The simulation uses the accepted S3 defining-module workflow API directly:

```text
build_net()
seed_marking(instance)
GATES
MANIFEST
wire_gates(built, GATES, activity_definitions, MANIFEST)

HeadSeen / RunSeen
RerunReq -> RerunLanded | RerunMoved | RerunFault
VariantPayloadConverter
```

It uses these real Petrus execution interfaces rather than simulating their
behavior with dictionaries:

| Seam | Use in the workflow module | Authority shown |
|---|---|---|
| `Engine.create()` | create the first workflow execution from the S3 Net and seed marking | workflow marking begins in Petrus History |
| `Engine.deliver()` | admit typed `HeadSeen` and `RunSeen` tokens with delivery identities | observation admission is a workflow command, not runtime meaning |
| `Engine.advance()` | execute one coordinator action behind one `context.call()` leaf | S9 bounds each exposed owner step to one named effect-adjacent cut |
| `ActivityDefinition` and `VariantPayloadConverter` | encode the real `RerunReq` request and `RerunLanded` terminal union | the port shape and terminal variant are not test-only substitutes |
| `InMemoryDispatch` | expose the pending `rerun_gate` invocation and admit its typed terminal | Dispatch is process-local and reconstructible, not durable authority |
| `InMemoryHistoryStore` | retain deliveries, transitions, Activity request, and terminal across generations | History is the execution authority in this experiment |
| `Engine.load()` | rebuild Engine and pending Dispatch after generation loss | recovery does not serialize a coroutine, Engine, or Dispatch object |

The experiment names four observable cuts:

```text
workflow_action_committed
activity_requested
activity_request_reconstructed
activity_terminal_projected
```

`activity_requested` is the meaningful crash cut. The real
`Engine.advance()` leaf has appended the `ActivityRequested` occurrence and
made the invocation pending, but S9 has not returned the leaf result through
the suspended owner frame. Crashing there discards the frame, Engine, Dispatch,
and generation. The replacement generation calls `Engine.load()` against the
retained History and reconstructs the same pending occurrence and operation.

This cut is exact for the current fresh bounded scenario. It does not erase
S7's dependency gap: a first `Engine.load()` may reconcile more than one
historical occurrence before returning.

## Exact local simulation interface

The module implements S9's public module/generation split without a facade or
runtime extension:

```text
WorkflowSimulation:
  name = "workflow"
  fresh()
  open(context) -> generation
  drop(generation)
  close(generation)
  resource_usage(generation | None)

generation:
  command(name, payload, context)
  observe(name, payload, context)
  eligible_actions(context)
  async step(action, context)
```

The local vocabulary is closed:

| Kind | Name | Exact meaning |
|---|---|---|
| command | `observe.head` | deliver one `HeadSeen` from exactly `identity`, `head`, `base`, `policy`, and `incarnation` |
| command | `observe.run` | deliver one `RunSeen` from exactly `identity`, `head`, `run_id`, `attempt`, `conclusion`, and `fingerprint` |
| command | `terminal.rerun` | admit only a `landed` terminal for the exact operation of the one pending `rerun_gate` invocation |
| observation | `state` | project generation loads, History size, escalation ladder, pending Activity, and recorded terminal |
| observation | `check` | independently derive and compare request/terminal operation correlation |
| action | `advance` | run exactly one real `Engine.advance()` behind `context.call("engine.advance", ...)` |
| fault | `terminal.rerun.corrupt_operation` | replace the admitted typed terminal's `op` while preserving its other production-shaped fields |

Payloads must be plain dictionaries with exactly the declared fields. Text is
non-empty printable ASCII, integers are non-negative and not booleans,
`observe.run` accepts only the declared conclusion vocabulary, and
`terminal.rerun` accepts only `landed`. Unknown command, observation, action,
field, and terminal variant values fail loudly.

S9 deliberately leaves fault-point vocabulary with each module but provides
no declaration hook when a fault is armed. Therefore an unknown point cannot
be rejected at `Timeline.fault()` time through the fixed interface. The one
declared fault validates its payload exactly when matched. Adding a generic
fault catalog to S9 solely for this module would change the accepted runtime
interface, so this remains an explicit interface limit rather than a local
override.

## Bounds and retained authority

The proof uses S9 global bounds plus these exact workflow gauges:

| Gauge | Proof limit | Source |
|---|---:|---|
| `workflow.commands` | 8 | retained admitted observations and terminal commands |
| `workflow.history_records` | 128 | real Petrus History length |
| `workflow.pending_activities` | 1 | requested occurrences minus recorded terminals |

The executable contract separately lowers `workflow.commands` to one, attempts
a second command, observes terminal `BudgetExceeded`, emits the failure
artifact, and replays it exactly. Thus resource exhaustion is explicit rather
than an unbounded or silently dropped operation.

Authority is split as follows:

| Retained across generation loss | Rebuilt or discarded with the generation |
|---|---|
| Petrus History | `Engine` |
| accepted observation/terminal transcript | `InMemoryDispatch` pending projection |
| observation delivery identities and their exact commands | Activity definition handle |
| whether the workflow instance has been created | eligible-action turn and `ready` cache |
| generation-load diagnostic count | suspended coroutine and held leaf result |

The transcript is not workflow execution authority: History and the rebuilt
Engine own the marking, Activity request, and terminal fold. It exists to
enforce delivery-identity conflicts and to give the checker an independent
input derivation. No frame, callable, Engine object, Dispatch object, or local
return participates in recovery.

## Independent checker

The checker is included only for the operation-correlation property, where it
supplies a genuinely different semantic derivation. From the retained admitted
commands alone, it selects the latest head and run and derives:

```text
if run.conclusion == "failure" and run.head == head.head:
    expected = "rerun:{fingerprint}:{run_id}:{attempt}"
else:
    expected = none
```

It then reads the real History independently and requires the
`ActivityRequested.correlation` and typed terminal result `op` to equal that
derived value. It does not call the S3 request-building transition, inspect the
ladder fold to infer success, reuse a `RerunReq`, or trust the terminal command's
operation as the expected value.

No shadow model duplicates the Net marking or transition rules. State
observations project real Engine, Dispatch, and History state because a second
implementation there would provide no independent semantic derivation.

## Crash, reload, and exact replay proof

The passing scenario executes this sequence:

1. deliver `HeadSeen(head="abc123")` and a failed
   `RunSeen(fingerprint="tests-red", run_id=7, attempt=1)`;
2. step the real Net until occurrence 8 requests `rerun_gate` with operation
   `rerun:tests-red:7:1`;
3. crash after the request leaf commits but before its result returns to the
   owner;
4. restart generation 2 and reconstruct the same pending occurrence through
   `Engine.load()`;
5. admit a typed `RerunLanded` through real Dispatch;
6. step until the real ladder settles to one landed rung; and
7. encode and exactly replay the complete expanded artifact from fresh module
   construction.

Decisive evidence:

```text
operations          37
journal entries     78
artifact bytes      32,084
final generation    2
request occurrence  8
request records     4 added at the crash cut
final History       61 records
final ladder        fingerprint=tests-red, rungs=1, settled=landed
journal digest      sha256:d015ab13256c96e8eb8f3a1fed90fe94150c51236d30be4841c729dcda74ada6
replay              exact
```

## Meaningful failure and checker sensitivity

The counterexample follows the same observation-to-request path, then arms
`terminal.rerun.corrupt_operation` with replacement
`rerun:other:99:9`. The module still constructs the real typed `RerunLanded`
variant with the request's fingerprint, run ID, and attempt, but injects the
wrong `op`. The current S3 fold accepts that typed terminal. The independent
checker reports exactly:

```text
RerunLanded terminal operation 'rerun:other:99:9' does not match requested operation 'rerun:tests-red:7:1'
```

The failing artifact evidence is:

```text
operations          32
journal entries     67
artifact bytes      27,796
final generation    1
journal digest      sha256:6d4d1a23b4b4c8809fbc15ecff186cd738ac6b7348c26ce10cefaa048f87d116
fault match         terminal.rerun.corrupt_operation
replay              exact, including the checker-visible violation
```

This is a meaningful workflow failure rather than a synthetic runtime error:
the request and terminal are each well-typed, but they disagree about which
durable operation settled. Exact replay reconstructs the same disagreement
without any other Hamsterdan module.

## Production seam gaps and correspondence limits

The experiment records four gaps and makes no production correction:

1. **Bounded first load.** Current Petrus `Engine.load()` may perform multi-
   occurrence reconciliation. The fresh scenario's steps are bounded, but this
   does not close S7's load correspondence gap.
2. **Effect observation versus terminal recording.** `InMemoryDispatch.complete()`
   synchronously supplies the typed terminal for projection into History. It
   does not prove the future readiness split between observing an external
   effect and durably recording its Activity terminal.
3. **Terminal correlation ownership.** The accepted S3 terminal fold trusts a
   typed terminal and does not independently compare its `op` with the request.
   Before production promotion, one boundary must reject a mismatched terminal
   before the fold. The likely correction is at the Activity/adapter admission
   boundary, where both invocation identity and decoded terminal are present;
   ownership remains for a later ruling rather than this fan-out session.
4. **Fault declaration timing.** The fixed S9 interface can validate a declared
   fault payload when consumed but cannot reject an unknown point when armed.
   S10 does not reopen the runtime contract to add a catalog.

The proof is intentionally narrow. It uses S3's reduced three-loop workflow,
not the complete nine-loop target or current whole readiness implementation.
History is in memory but retained across simulated generation loss. Crash is
in-process frame loss, not operating-system process death. Terminal injection
is synchronous. There is no provider, credential, host custody, concurrent
execution, durable database, external effect, or whole-application routing in
this session.

## Exit assessment

The candidate supplies one isolated workflow simulation under S9's exact
Timeline/module interface, uses the accepted workflow package and real Petrus
step/Activity seams, declares a strict local command-observation-action-fault
surface, exposes exact resource bounds, and retains only History and explicit
module state across a process-local frame boundary. Its recovery scenario
crosses observation, Activity request, crash, reload, typed terminal, and fold.
Its independent checker detects a well-typed but miscorrelated terminal, and
both the passing recovery and failing counterexample replay exactly.

The workflow part of Experiment 10 therefore meets its local exit criterion,
subject to Navigator acceptance. This record does not update the ES-010 index,
compose another module, begin Experiment 11, or propose R4.
