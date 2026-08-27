# Experiment 9 — Hamsterdan simulation runtime

Session S9. Durable inputs: the ES-010 index, the accepted
[`07-step-contract.md`](07-step-contract.md), and the ruled R3 decision,
[`Timeline and coroutine stepper share bounded execution`](../../../decisions/records/2026-08-26T2012Z-timeline-and-coroutine-stepper-share-bounded-execution.md).
The repository baseline was local `main` and `origin/main` at
`2d7afa70edb518d55681e41ec6834fd2bcdec1ba`, which records accepted S8 and
ruled R3. The Petrus source inspected through the project pin was
`src/petrus/testing/dst.py` at
`44cac5ff48ac371ebae56323941983f30db13c0d`.

Method: inventory the generic Petrus DST behavior the maintained Hamsterdan
testing surface currently consumes; separate useful execution mechanics from
Petrus profile, checker, artifact, and compatibility policy; copy and adapt only
the useful mechanics into an isolated, provenance-marked spike; and execute two
independent generic modules under one runtime. The proof crosses R3's three
effect-adjacent positions, loses a response after a durable modeled effect,
reconstructs lookup-first without a saved frame, orders equal-time actions, and
replays its expanded artifact exactly. The R2 trees and R3 authority boundaries
are fixed inputs. No local module simulation or R4 question is in scope.

The Navigator accepted the S9 evidence, then confirmed a focused correction
from the separate review pass: every execution-budget failure must terminate
the runtime, discard process-local frames, and remain artifactable and exactly
replayable even when the live generation or journal capacity is exhausted.

## Verdict

Hamsterdan needs a small interpreter contract, not a second application model:

```text
durable module stores                    durable authority
       │
       ├─ open generation ──▶ eligible ActionRef values
       │                              │
       │                              ▼
       │                      Timeline selects one
       │                              │
       │                              ▼
       └──────────────────── internal CoroutineStepper
                                      │
                               zero or one leaf
                                      │
                            start ─ execute ─ finish
```

The runtime owns one logical clock, cross-module eligible-action ordering,
deterministic choice streams, occurrence faults, revocable process generations,
global and named resource budgets, a strict journal, one artifact version, and
exact replay. A module owns every semantic command, observation, action,
durable store, eligibility rule, retry, timer identity, and fairness position.
The runtime can select an `ActionRef`; it cannot invent one or decide what it
means.

The candidate at
[`spikes/09-simulation-runtime/runtime.py`](spikes/09-simulation-runtime/runtime.py)
and its executable contract at
[`spikes/09-simulation-runtime/test_runtime.py`](spikes/09-simulation-runtime/test_runtime.py)
meet the S9 exit criterion. They import only the Python standard library and
have no source dependency on Petrus or Hamsterdan. They are experiment code,
not production implementation.

## Current Petrus consumption inventory

The current maintained Hamsterdan test support imports 29 names from
`petrus.testing.dst` across four files under `src/hamsterdan/host/testing`:

```text
ApplyResult, BudgetV4, CheckResult, CheckerIdentity, Command,
CrashOperation, Disposition, ExecuteOperation, FairOperation, Fault,
FaultDisposition, FaultOperation, FinishOperation, GenerationStart,
Observation, ObservationRequest, ProfileIdentity, ReplayResult,
ResourceUsage, RestartOperation, ScenarioArtifact, ScenarioContext,
ScenarioRegistry, ScheduledCommand, StaleGeneration, Timeline, World,
digest_json, replay
```

Maintained unit and integration tests additionally name the Petrus API/version
constants, choice authority, terminal failure values, artifact encode/load
functions, and DST errors. Those imports resolve into these behavioral groups:

| Generic behavior consumed today | Petrus owner | Current Hamsterdan use | S9 disposition |
|---|---|---|---|
| Strict JSON detachment and canonical digest | `_strict_json`, `digest_json` | Contract identities, bounded detached commands, observations, journal evidence | Copy and own the strict JSON and digest mechanics without Pydantic |
| Deterministic seeded draws | `ChoiceStreams`, `ChoiceProvenance`, `ChoiceAuthority` | Generated campaign choices and provenance | Keep SHA-256 counter streams; replace the closed Petrus authority enum with namespaced runtime/module streams and record each draw in its operation |
| Logical clock and total-order queue | `World.instant`, `_Queued`, `_enqueue*`, `_step` | Timed profile commands and deterministic execution | Keep one integer-microsecond clock and deterministic ordering; replace the profile-owned queue with module-declared eligible actions |
| Occurrence faults | `Fault`, `_ActiveFault`, `ScenarioContext.faults`, `World._faults` | Named provider and effect failures | Keep module/point/occurrence/payload matching; remove Petrus disposition and profile identity |
| Revocable crash generations | `World._crash`, `_restart`, `_require_generation`, Petrus `Timeline` | Crash/reload and stale-handle rejection | Keep revocable generation-bound Timelines; mount several independent module generations instead of one profile generation |
| Global and retained-resource bounds | `BudgetV4`, `ResourceUsage`, `_reserve_action`, `_sample_resources` | Campaign termination and profile resource ceilings | Keep hard global limits plus exact named resource gauges; remove the single `profile_resources` namespace |
| Expanded attempts and failures | `World._attempt`, `FailureOperation`, `BudgetFailure` | Replayable terminal budget failures | Keep one dense operation stream and terminal replayable budget failures; remove Petrus disposition/invariant policy |
| Journal and digest | `JournalEntry`, `World._record`, `_journal_digest` | Exact replay and semantic coverage evidence | Keep dense entries with clock and generation; add scheduler choices and fault matches; omit checker-owned entries from the runtime |
| Artifact and exact replay | `ScenarioArtifact`, `encode_artifact`, `decode_artifact`, `replay`, `_replay_operations` | Persisted deterministic evidence and semantic coverage | Keep strict canonical encoding, byte refusal, expanded replay, and final journal comparison; define one Hamsterdan-owned version with no compatibility readers |
| Profile/checker framework | `ScenarioProfile`, `ProfileIdentity`, `ScenarioRegistry`, `Checker`, checker cadence | One fixed readiness World and independent readiness model | Do not copy. Exp 10 modules own local vocabularies and checkers; composition supplies module builders directly |
| Fair/converged scenario protocol | `begin_fair`, `finish`, `Disposition`, `run_until` | Campaign completion and coverage labels | Do not copy. Durable modules own fairness; `Waiting` and finite `run(step_budget)` are runtime mechanics, while semantic completion is a module observation |
| Outer process harness | `ProcessRunSpec`, `ProcessSession`, `run_process_scenario`, progress frames | Petrus process-death qualification machinery, not the runtime seam used by the mounted modules | Do not copy. S9 proves generation loss; real process death remains separate correspondence evidence |

This inventory explains why wrapping Petrus `World` is the wrong boundary. Its
execution mechanics are useful, but its one-profile identity, checker cadence,
fair/converged lifecycle, and versioned artifact family encode the current
readiness campaign rather than a composable Hamsterdan runtime.

## Copy-and-own ledger

Every adapted mechanism comes from the exact Petrus commit named above. The
spike module repeats that provenance in its module docstring and states that no
synchronization or artifact-compatibility contract survives.

| Petrus source at `44cac5f` | Hamsterdan candidate | Treatment |
|---|---|---|
| `_strict_json`, `digest_json` | `_strict_json`, `digest_json` | Adapted nearly structurally; retained strict Python-type and finite-number refusal; removed `JsonValue` and Pydantic |
| `ChoiceStreams._index`, `ChoiceStreams._digest`, `ChoiceProvenance` | `_Choices._index`, per-operation choice tape, artifact `origin` | Retained SHA-256 counter and rejection sampling; changed stream authority and replay to exact recorded options/selection |
| `_Queued`, `World.instant`, `_enqueue*`, `World._step` | `ActionRef`, `_Runtime._eligible_actions`, `_Runtime.start` | Reworked. Modules expose durable eligibility; runtime selects the earliest instant and records a deterministic tie draw instead of owning semantic commands |
| `Fault`, `_ActiveFault`, `ScenarioContext.faults`, `World._faults` | `Fault`, `_ActiveFault`, `_Faults`, `_ModuleContext.faults` | Adapted occurrence matching; namespaced by module and point; no profile or disposition |
| `World._generation_id`, `_crash`, `_restart`, `_require_generation`, Petrus `Timeline` | `_Runtime.generation`, `crash`, `restart`, `_require_current`, public `Timeline` | Adapted to one generation containing several module mounts; preserved stale-handle refusal |
| `BudgetV4`, `ResourceUsage`, `_reserve_action`, `_sample_resources`, `_exhaust` | `Budget`, `_resource_usage`, `_checked_resources`, preflight counters, `BudgetExceeded` | Flattened global measures and replaced profile resources with an exact union of module gauges |
| `World._attempt`, `FailureOperation`, `BudgetFailure` | `_Runtime._boundary` and `kind="failure"` operations | Adapted accepted/not-accepted attempt capture and exact terminal replay; omitted semantic invariant disposition |
| `JournalEntry`, `World._record`, `_journal_digest` | strict journal dictionaries, `_Runtime._record`, `digest_json` | Adapted dense ordering, clock, generation, kind, name, and detached value |
| `ScenarioArtifact`, `encode_artifact`, `decode_artifact` | `Artifact`, `Artifact.encode`, `Artifact.decode` | Replaced four Petrus versions and `petrus.testing.dst/v4` with only `hamsterdan-simulation` version 1 |
| `replay`, `_replay_operations`, `_replay_operation`, `_replay_attempt` | `replay`, `_Runtime._expected_operation`, `_append_operation`, `assert_replayed` | Adapted expanded replay; module order and operation choice tapes replace profile/checker registries |
| `ScenarioProfile`, identities, registry, checkers, fair/finish protocol, process runner | none | Deliberately omitted |

No code is imported from `petrus.testing.dst`; future Petrus changes do not flow
into this candidate. Conversely, this code creates no Petrus maintenance
obligation.

## Exact module boundary

The candidate uses a structural module contract. Names below are signatures,
not an instruction to add Python `Protocol` classes in production.

```text
SimulationModule:
  name: str
  open(context: ModuleContext) -> Generation
  drop(generation: Generation) -> None
  close(generation: Generation) -> None
  resource_usage(generation: Generation | None) -> dict[str, int]

Generation:
  command(name: str, payload: StrictJSON, context: ModuleContext) -> StrictJSON
  observe(name: str, payload: StrictJSON, context: ModuleContext) -> StrictJSON
  eligible_actions(context: ModuleContext) -> tuple[ActionRef, ...]
  async step(action: ActionRef, context: StepContext) -> StrictJSON

ModuleContext:
  now_us: int
  generation: int
  choose(stream: str, options: Sequence[str]) -> str
  faults(point: str) -> tuple[Fault, ...]

StepContext extends ModuleContext:
  call(name: str, payload: StrictJSON, operation: Callable[[], StrictJSON])
    -> awaitable StrictJSON
```

`ActionRef(module, name, identity, eligible_at_us)` is detached scheduling
metadata, not semantic state. The generation computes it from the module's
durable store. `open` reconstructs a process-local generation from that store;
`drop` simulates abrupt generation loss; `close` releases a replay generation.
The durable store itself lives outside the returned generation object. A module
may have no action, one future action, or several eligible actions; the runtime
does not call another module through this contract.

The candidate deliberately rejects awaitable leaf results. Deterministic
adapters complete one modeled leaf synchronously under `Timeline.execute()`;
the owner remains ordinary async Python because `context.call()` is awaited.
A production invocation implementation may await its real leaf while preserving
the same `start / execute / finish` phase machine. That invocation detail does
not change the synchronous Timeline API or permit a second leaf.

## Exact Timeline API

S9 fixes the public simulation/debugging surface as follows:

```text
Timeline.open(modules, budget, *, seed=0) -> Timeline

timeline.generation: int
timeline.now_us: int

timeline.command(module, name, payload) -> StrictJSON
timeline.observe(module, name, payload=None) -> Observation
timeline.advance(to_us) -> int
timeline.fault(module, point, *, occurrence=1, payload=None) -> Fault

timeline.start() -> LeafOffered | StepCompleted | Waiting
timeline.execute() -> LeafExecuted
timeline.finish() -> StepCompleted
timeline.step() -> StepCompleted | Waiting
timeline.run(step_budget) -> RunResult

timeline.crash(cut) -> None
timeline.restart() -> Timeline
timeline.artifact(scenario_id) -> Artifact

Artifact.encode() -> bytes
Artifact.decode(payload) -> Artifact
replay(artifact, build_modules) -> ReplayResult
```

`command`, `observe`, and `fault` route by exact module name. Unknown names or
non-strict payloads fail loudly. `advance` never moves backward and never
auto-runs work. `start`, `execute`, and `finish` expose R3's three phases;
`step` composes those phases; `run` is only a finite loop over `step` and
reports local step-budget exhaustion rather than inventing convergence.

`Timeline` is bound to one generation. After `crash`, every method on that
object fails `StaleGeneration`; only `restart()` on the most recently crashed
Timeline returns the newly bound object. Normal artifact creation requires a
live generation and no suspended owner step. A terminal execution-budget
failure discards any suspended frame and permits its bound Timeline to emit the
final artifact even when generation restart itself exhausted its budget.

## Execution semantics

### Clock and eligible-action scheduling

`now_us` is the only time. It is a non-negative integer count of microseconds.
Modules use the same value when producing `ActionRef`s and observations.

`start()` asks every live generation for its complete bounded tuple of actions.
It then:

1. returns `Waiting(next_at_us)` when no action is eligible, without advancing
   the clock;
2. selects the smallest `eligible_at_us` not greater than `now_us`;
3. sorts equal-time candidates by `(module, name, identity)` to create a stable
   option set; and
4. uses the `runtime:event_order` choice stream when more than one candidate
   remains.

The runtime owns only this cross-module interleaving. A module's durable state
owns lane priority, retries, timer maturity, and fair cursors. If one readiness
lane must precede another, its generation exposes only the permitted action.
If host fairness selects one subject, the host module's durable scheduler state
produces that `ActionRef`. There is no runtime-level workflow, lane, subject, or
provider scheduler.

### Deterministic choices

Each draw is keyed by `(algorithm, seed, stream, ordinal, probe)` and uses
SHA-256 rejection sampling. Runtime streams are reserved under `runtime:*`;
module calls are automatically prefixed with the module name. Streams do not
perturb one another.

Discovery uses the seed. Replay does not trust the seed to recreate a draw: an
expanded operation contains the exact stream, ordinal, ordered option list,
and selected option. Replay requires the module to present that same option
set and applies the recorded selection. Missing, additional, reordered, or
renamed choices fail `ReplayMismatch`. The seed and final per-stream draw
counts remain artifact provenance, not replay authority.

### Fault controller

`fault(module, point, occurrence, payload)` arms one exact occurrence. A module
can consume matching faults only through its context and interprets the strict
payload itself. Unmatched faults and occurrence counters survive generation
crashes. A match is journaled. The runtime knows neither the point vocabulary
nor whether a match means response loss, unavailability, delay, or another
module-defined outcome.

### CoroutineStepper and R3 authority

The internal `CoroutineStepper` accepts one selected owner coroutine and has
four relevant states:

```text
new ── start ──▶ offered ── execute ──▶ executed ── finish ──▶ completed
                       ╲                    ╲
                        ╲ crash              ╲ crash
                         └──────────────▶ closed
```

An owner may return without a leaf during `start`, or it may await one
`context.call`. `execute` calls that leaf once and holds its returned value or
exact exception outside the suspended owner. `finish` sends or throws the
process-local outcome back through the ordinary Python stack. Yielding a second
leaf closes the frame and raises `OneLeafViolation`.

The public `LeafExecuted` value makes the debugging cut inspectable, but the
leaf value, exception object, exception text, and owner-return value do not
enter the artifact. Expanded `execute` and `finish` operations retain only
action/leaf identity and `returned`, `raised`, or `completed` control outcome.
The executable contract explicitly proves that a `ResponseLost` exception is
visible at the debugging cut but absent from encoded artifact bytes.

No coroutine, frame, callable, local return, or exception is durable authority.
The runtime does not serialize or identify them. This is the R3 boundary, not
an artifact optimization.

### Crash generations and recovery

`crash(cut)` is an expanded operation and may run while the stepper is idle,
offered, or executed. It records the phase and detached action/leaf identities,
closes any frame without returning the held result to the owner, drops every
live module generation, and revokes the Timeline. It retains only runtime
mechanics that cross generations: the clock, operation/journal prefixes,
choice ordinals, armed faults, counters, and generation sequence.

`restart()` opens fresh generations against the modules' retained stores and
returns generation `n + 1`. Modules recover scheduling and effect authority
from those stores. In the pair proof, the modeled effect commits, raises
`ResponseLost`, and the runtime crashes in `executed`. The replacement
generation finds the operation in its durable effect ledger and returns
`source="lookup"`; total effect cardinality remains one. The discarded frame
and held exception contribute nothing to recovery.

## Budgets and resource accounting

`Budget` has these exact measures:

| Measure | Meaning |
|---|---|
| `operations` | accepted Timeline operations; an over-limit attempt becomes a terminal expanded failure |
| `owner_steps` | completed owner coroutine steps; checked before another eligible action can expose or execute a leaf |
| `eligible_actions` | maximum aggregate `ActionRef` values returned by all modules at one scheduler decision |
| `leaf_calls` | maximum executed leaf callables |
| `choice_draws` | maximum draws across all streams |
| `active_faults` | maximum simultaneously armed faults |
| `generations` | maximum opened crash generations, including the initial generation |
| `logical_time_us` | maximum clock instant |
| `journal_entries` | maximum dense journal entries |
| `artifact_bytes` | maximum canonical encoded artifact bytes, below a fixed 4 MiB decoder ceiling |
| `resources[name]` | exact named live/retained resource gauge supplied by one mounted module |

Booleans, non-finite values, non-integers, unknown resource keys, duplicate
keys, and out-of-range values are rejected. `journal_entries` must admit the
initial generation and resource entries. The union of module resource names
must exactly equal the budget map on every boundary; a missing, additional, or
duplicate gauge is a contract failure. Resource samples are journaled after
generation open and accepted operations, and remain available after a crash by
calling each mount with no live generation.

Every execution-budget failure is appended as a final expanded `failure`
containing the attempted kind/request, whether its operation callback returned,
any detached control result, and exact bound/limit. It terminalizes the runtime,
closes a suspended frame without returning its held result, and refuses later
operations. The originating Timeline can still emit the failure artifact when
the runtime has no live generation. Replay must fail at that same attempt and
match the artifact exactly.

Owner-step capacity is checked before selecting the next eligible action, so
exhaustion cannot execute one extra leaf effect merely to discover the bound.
The interpreter also reserves the two post-operation journal entries before it
accepts a successful operation record. If that reserve is unavailable after a
module callback returned, the final failure records `accepted=true`; replay
repeats the callback and exhausts the same journal boundary. Artifact byte
refusal remains an encoding-output bound rather than a Timeline operation.

## Journal, artifact, and replay

The journal is a dense sequence of strict entries:

```text
position, instant_us, generation, kind, name, value
```

It records generation open/load, expanded operations, deterministic choices,
fault matches, resource samples, and budget failures. The journal is diagnostic
evidence; module stores remain semantic authority.

The only artifact is `format="hamsterdan-simulation", version=1`:

```text
scenario_id
ordered module names
complete Budget
expanded operations and per-operation choice tapes
complete journal and canonical SHA-256 digest
final clock and live generation
choice algorithm, discovery seed, and final draw counts
```

Encoding is canonical strict JSON. Decoding refuses duplicate keys,
non-finite numbers, unknown/missing top-level fields, unsupported versions,
non-dense positions, a mismatched journal digest, non-terminal failure records,
and byte-limit violations. There is no Petrus profile/checker identity, no
`petrus.testing.dst/v4`, no V1–V4 reader, no migration path, and no generic
compatibility field.

`replay(artifact, build_modules)` constructs fresh modules and requires their
ordered names to match. It drives each expanded operation through the same
Timeline methods, applies exact choice tapes, reproduces a terminal budget
failure where present, and then requires exact equality of:

- every expanded operation;
- every journal entry;
- the final logical instant and generation; and
- the journal digest.

The builder, not an artifact registry, owns module construction. Artifacts
contain no Python import path, callable, frame, or profile factory.

## Independent-pair proof

The contract mounts `alpha` and `beta`, two instances of one deliberately
generic module shape. Each has a separate durable store containing scheduled
operation times, durable effect markers, completion identities, and recovery
sources. Neither module references the other.

The executed scenario proves:

1. `alpha` is selected at logical instant 1, then crashes in `offered` before
   its leaf runs; generation 2 reconstructs and executes it once.
2. An occurrence fault makes `alpha` commit an effect and lose its response at
   instant 2; the runtime crashes in `executed`; generation 3 recovers the same
   operation lookup-first without a duplicate effect.
3. `beta` returns normally at instant 3, then the runtime crashes in `idle`;
   generation 4 preserves completion.
4. Independent `alpha` and `beta` actions both become eligible at instant 10;
   one `runtime:event_order` draw chooses the first and the second remains
   eligible for the next step.
5. Detached observations from both modules report instant 10 under the same
   clock, and a fresh pair replays the encoded artifact exactly.

The resulting evidence was:

```text
operations          36
journal entries     87
artifact bytes      29,185
final generation    4
final instant_us    10
choice draws        alpha:marker=3, beta:marker=2, runtime:event_order=1
crash phases        offered, executed, idle
journal digest      sha256:4b2a24de140d92164ae26eaab8898c1aaf10c0fe3e5f10051dce11052d2b7d80
replay              exact
```

Additional contracts prove the one-leaf rule; terminal operation-budget
failure; pre-effect owner-step exhaustion; exact journal exhaustion after an
accepted callback; frame disposal and exact replay after leaf-call exhaustion;
artifact emission and exact replay after restart-generation exhaustion;
artifact byte refusal; invalid, boolean, non-finite, and construction-inadequate
budget refusal; and static semantic independence.

## Semantic-independence proof

The runtime source is parsed with Python AST. Its import roots are only:

```text
collections.abc, dataclasses, hashlib, inspect, json, math, re, typing,
__future__
```

Neither `petrus` nor `hamsterdan` is imported. AST identifiers named
`workflow`, `readiness`, `github`, `agent`, or `host` are absent. More
importantly, the runtime's closed vocabulary is mechanical:

```text
module, command, observation, action, eligible_at_us, leaf, choice, fault,
clock, generation, resource, operation, journal, artifact, replay
```

The module owns every point at which application meaning could enter: names,
payloads, action identity, durable state, eligibility, fault interpretation,
and observation values. Therefore the proof is not merely “no forbidden
import”; there is no runtime branch capable of deciding workflow, readiness,
GitHub, agent, or host behavior.

## Deliberate omissions and correspondence boundary

- S9 defines no module command, observation, fault catalog, checker, or expected
  semantic model. Those belong to Exp 10's local simulations.
- S9 defines no whole-Hamsterdan routing or cross-module property. Those belong
  to Exp 11.
- The candidate explores recorded interleavings, not real process/thread
  parallelism. Real concurrency remains correspondence evidence.
- Generation loss is executed in-process against retained stores. Operating
  system process death remains correspondence evidence; no Petrus process
  runner was copied.
- Deterministic leaf adapters are synchronous. Production may await a real leaf
  inside the same phase mechanism, but Timeline does not run an event loop or
  admit opaque awaitables.
- The candidate is one readable spike file rather than the final
  `simulation/{runtime,clock,scheduling,faults,artifacts,replay}.py` package.
  Production splitting is a delivery concern and is not evidence for adding
  more interfaces now.
- Petrus bounded-load and split Activity-execution seams from S7/R3 remain
  dependency correspondence gaps. S9 neither hides nor solves them.

## Exit assessment

The runtime candidate defines every mechanism named by Experiment 9, carries
exact copy-and-own provenance, removes Petrus profile/artifact/compatibility
assumptions, and keeps durable scheduling and recovery authority with mounted
modules. Its pair proof shares one clock and scheduler across independent
stores, reaches all three R3 crash positions, preserves lookup-first recovery,
records deterministic equal-time ordering, and replays exactly without a
Petrus testing import.

The Navigator accepted Experiment 9 and confirmed its focused post-acceptance
budget-terminalization correction. The corrected experiment meets its exit
criterion. This record does not start Experiment 10 or rule R4.
