# Experiment 8 — Timeline and coroutine stepper spike (amended)

Session S8. Durable inputs: the ES-010 index and the accepted
[`07-step-contract.md`](07-step-contract.md). No other experiment record or
the engineering style contract was used. All executable evidence remains under
[`spikes/08-driver-mechanism/`](spikes/08-driver-mechanism/); no production,
maintained test, or configuration file changes in this experiment.

The first S8 pass compared an explicit loop, `_Bounce(command="step")`, and a
generator wrapped around one monolithic `World.step()`. That pass was accepted
as executed evidence, but its trampoline conclusion answered the wrong
question. The Navigator meant normal deep Python calls whose leaf operation can
return control to a Timeline, like async I/O, not recursion elimination or a data
instruction describing the next owner. This amendment retains the valid
durability evidence, adds the intended callable-coroutine candidate, and
replaces the mechanism recommendation. R2 and S7 remain fixed. The Navigator
accepted the amended record and ruled R3 in
[`Timeline and coroutine stepper share bounded execution`](../../../decisions/records/2026-08-26T2012Z-timeline-and-coroutine-stepper-share-bounded-execution.md).

## Verdict

R3 selects a **Timeline over a callable coroutine stepper**, with production
using the same stepper through an explicit bounded drain.

Production owners write ordinary nested `async` code. At an S7 leaf they
`await perform(actual_callable)`. Python carries that callable through the
suspended host/readiness/workflow call stack to a generic `CoroutineStepper`.
The stepper can stop before invoking it, invoke it once while withholding its
result, or send the result back through normal returns. Production's `step()`
composes those phases. The simulation-facing `Timeline` may interpose between
them.

The callable is live code, not a durable instruction or scheduler choice.
Durable host, readiness, workflow, Activity, timer, and effect stores remain the
only recovery authority. A coroutine frame may preserve ordinary locals while
the process lives, but restart always discards the frame and creates a new entry
coroutine from durable state.

Keep the first pass's other conclusions:

- an explicit finite loop remains the production drain;
- `_Bounce(command="step")` is a redundant **data trampoline**, not the
  intended candidate;
- a `while: yield step()` generator is only a consumer wrapper; and
- no continuation frame may choose a subject, lane, candidate, retry, or fair
  position.

The amended candidate adds leverage the first pass did not test: it preserves
normal layered code while exposing the deep leaf to production and simulation
through one execution mechanism.

### Names and ownership

- `Timeline` is the public simulation/debugging concept. S8 gives it `step`,
  `run_until_before`, `run_until_after`, and the three-phase controls needed for
  the proof. S9 owns its clock, journal, faults, crash generations, artifacts,
  and replay.
- `CoroutineStepper` is the internal production-shaped mechanism. It advances
  one entry coroutine through at most one callable and one ordinary return.
- `run(budget)` is the spike's finite production-drain proof. Delivery may keep
  that method or express the same loop as a separate `drain(stepper.step, ...)`.

“Driver” remains only in the historical name of the first-pass comparison and
in Ariad's human/agent role. It is not the target runtime API.

## Corrected mechanism

### Owner code is code

[`coroutine_prototype.py`](spikes/08-driver-mechanism/coroutine_prototype.py)
contains actual nested functions:

```python
async def host_once(self):
    readiness = await self.readiness_once(subject)
    return host_result(readiness)

async def readiness_once(self, subject):
    phase = await self.workflow_once(subject)
    return await self.activity_once(subject, phase)

async def activity_once(self, subject, phase):
    observation = await perform(
        partial(self.observe_or_execute_activity, subject)
    )
    return effect_observed(observation)
```

The prototype spells result construction directly rather than through the
abbreviated helper names above. The structure is the point: ordinary calls,
locals, exceptions, and returns direct control. No value says
`next="activity"` or `command="workflow.step"`.

`perform` uses Python's existing coroutine protocol to yield the callable:

```python
@coroutine
def perform(operation):
    return (yield operation)
```

This low-level generator is the implementation of one awaitable, analogous to
an event-loop Future yielding control. It is not the rejected generator
mechanism that loops over and yields already-completed `step()` results.

### One semantic step has three controllable phases

```text
offer()
  resume host → readiness → workflow/Activity
  return the actual leaf callable without executing it

execute_pending()
  execute that callable once
  retain its value outside the suspended owners

finish_step()
  send the value into the leaf await
  let ordinary returns unwind to one top-level StepResult
```

Production uses:

```python
stepper = world.stepper()
result = await stepper.step()
```

`step()` composes all three phases and returns one S7 result. A production drain
is a validated finite loop over that method. Tests and simulations can instead
use:

```python
timeline = world.timeline()
operation = await timeline.run_until_before(
    LayeredWorld.observe_or_execute_activity
)
operation, observation = await timeline.execute_pending()
result = timeline.finish_step()
```

The breakpoint names the callable itself. Stable `CutRef` data remains the
record of what happened and the replay-artifact vocabulary; it does not tell
the runtime what code to execute.

The stepper rejects an owner step that yields a second leaf before returning:

```text
one owner step awaited more than one operation;
return and let the production stepper allocate another step
```

This turns S7's “no hidden inner drain” rule into an executable structural
check. Row, byte, call, and elapsed-time budgets still belong to the yielded
leaf operation and its owner; coroutine syntax does not create those bounds.

### The stepper routes returns, not work

The stepper advances Python's coroutine protocol and invokes the callable it is
given. It never chooses:

- the next PR subject or host turn;
- a readiness lane;
- a workflow candidate;
- an Activity retry or provider operation;
- timer order; or
- a fairness cursor.

Those decisions remain in the R2 owners and their durable or reconstructible
state. Host composition supplies the sibling-owned callable at the ruled seam;
normal nested calls do not authorize sibling packages to import concrete
implementations from one another.

## Crash and recovery behavior

The focused model keeps a durable tail-requeue queue, per-subject Activity
phase, host selection/posture/release state, and a provider ledger keyed by
operation identity. Its observed Activity value is process-local and omitted
from `snapshot()`.

The effect path exposes all three relevant positions without a callback:

```text
before leaf
  observe_or_execute_activity is offered but has not run

after leaf, before return
  provider ledger records acceptance
  result is held by the stepper outside readiness

after owner return
  host returns readiness_step_returned(activity_effect_observed)
  volatile observation may accelerate the next adjacent step
```

At either post-effect position, restart discards the coroutine and volatile
observation. A fresh host entry reaches the same callable from retained
Activity phase and host scheduling state. `observe_or_execute_activity` looks
up the same operation, returns the accepted result with zero new effect calls,
and readiness later records the Activity terminal. The coroutine is useful
while live but never required for correctness.

An interruption while the callable itself is running remains an adapter-owned
ambiguous effect. The stepper cannot prove whether a remote mutation landed.
The S4 operation identity, authority fence, timeout/cancellation policy, and
lookup-first recovery contract remain required.

## Executable evidence

The executable record now has two complementary models.

### Original whole-cut comparison

[`prototype.py`](spikes/08-driver-mechanism/prototype.py) and
[`test_prototype.py`](spikes/08-driver-mechanism/test_prototype.py) retain the
first pass's broad comparison:

| Evidence | Result |
|---|---|
| S7 vocabulary | all 5 workflow, 16 readiness, and 10 host cut kinds reached |
| Baseline | 206 progress results followed by `Terminal` for two subjects |
| Crash reconstruction | explicit loop, data trampoline, and generator each reconstruct after all 206 returned cuts: 618 schedules total |
| Effect recovery | one provider mutation per operation; post-effect crash re-observes by lookup |
| Resource bounds | at most two History rows and one external call per result |
| Fairness | 40 selections alternate, with one readiness call per selected subject |
| Long run | 10,001 iterative calls without stack growth |

That model proves the durable S7 contract but not the intended deep-call
trampoline: every mechanism wraps the same monolithic `World.step()`.

### Corrected layered-call comparison

[`coroutine_prototype.py`](spikes/08-driver-mechanism/coroutine_prototype.py) and
[`test_coroutine_prototype.py`](spikes/08-driver-mechanism/test_coroutine_prototype.py)
add the missing mechanism evidence:

| Evidence | Observed result | Finding |
|---|---|---|
| Deep call route | `host_once → readiness_once → workflow_once/activity_once → actual callable` | Owners remain ordinary Python; no return instruction algebra |
| Callable breakpoint | `run_until_before(LayeredWorld.observe_or_execute_activity)` returns its bound callable | Simulation identifies executable code, not a string command |
| Three effect positions | before leaf, after leaf before return, and after returned event all reached through public Timeline methods | No callback, monkeypatch, custom Dispatch, or private state mutation |
| Baseline drain | 32 progress results then `Terminal` | Production-shaped drain is a finite loop over the same `step()` |
| Returned-result crashes | all 32 progress positions reconstruct to the baseline semantic state | Coroutine frames are disposable |
| Focused effect crashes | all three positions recover; post-effect positions report lookup and zero new calls | Provider truth and operation identity, not the frame, recover ambiguity |
| Effects | exactly one mutation for each of two operation identities | At-least-once execution converges without duplicate provider mutation |
| Fairness | eight selections alternate `pr-1`, `pr-2`; one readiness call per selection | Durable host queue chooses; stepper only routes |
| Bound enforcement | every result has at most one external call; a second awaited leaf raises | The owner cannot hide a second semantic operation |
| Cancellation | cancelling after seven results executes no further callable; restore converges | Cancellation is between leaves; durable work survives |

The amendment deliberately does not import current `src/` runtime objects.
S7 already established that current `Engine.load()`, `V5Runtime.drain()`,
`PrReadinessV5Application.settle()`, Worker execution, and host activation hide
the target cuts. A thin async wrapper around those coarse methods would validate
the coroutine syntax while preserving the production mismatch. Exp 10 owns
module-real simulations after S9 fixes the generic runtime interface and the
required production seams exist. The Navigator's permission to import current
source remains useful for a focused check, but no current source import was
needed to answer S8's mechanism question honestly.

Executed amendment evidence:

```text
uv run --frozen pytest -q -o addopts= test_prototype.py test_coroutine_prototype.py
28 passed

uv run --frozen ruff format --check ... && uv run --frozen ruff check ...
4 files already formatted
All checks passed!

uv run --frozen ty check prototype.py coroutine_prototype.py
All checks passed!
```

## Comparison and trade-offs

| Mechanism | Ordinary deep calls | Stop before/after leaf | Durable authority | Added leverage | Decision |
|---|---|---|---|---|---|
| Direct explicit `step()` | only if each layer manually returns after its owned operation | after public result; pre-leaf needs another prepare/execute API | durable state | simplest outer drain, but does not itself route a deep callable | retain as outer drain |
| Data `_Bounce(command="step")` | no; it wraps the same step | no new position | disposable or invalid | none | reject |
| `while: yield step()` generator | no; it yields completed results | after public result only | frame must be disposable | optional iteration syntax | reject as architecture |
| Timeline + coroutine stepper | yes, through normal `await` | yes: offer, execute, finish | frame disposable; stores authoritative | deep inspectability without a data instruction language | select for R3 |

The callable coroutine costs one small generic stepper and makes owner step
functions async even when their pure decisions remain synchronous. It also
requires one clear rule: only the stepper advances those owner coroutines; they
are not simultaneously scheduled as `asyncio.Task`s. The Timeline wraps that
mechanism for simulation without becoming a second scheduler. In return, this
removes prepare/execute plumbing from every owner seam and gives production and
simulation the same lower-level execution boundary.

Exceptions preserve normal Python semantics. The stepper injects a leaf failure
back through `throw`, so owner `try`/`except` blocks can classify it. Durable
failure records remain data where replay requires them. Cancellation closes the
frame between leaves; it does not manufacture a terminal for an in-flight
external call.

## Pinned Petrus seam assessment

The corrected mechanism does not change the two S7 integration gaps confirmed
against Petrus `44cac5ff48ac371ebae56323941983f30db13c0d`.

1. `Engine.load()` resumes unbounded canonical History before returning, and
   first `advance()` reconciles all retained occurrences before one normal
   action. Hamsterdan still needs a supported bounded load cursor, record/byte
   budgets, and one-occurrence reconciliation seam.
2. `Worker.run_available(limit=1)` still combines claim, Activity resolution
   and invocation, normalization, and terminal report. Hamsterdan still needs a
   supported single-Attempt seam separating claim, effect observation, and
   terminal recording.

The callable coroutine can route those future operations once public; it cannot
split a coarse dependency call by syntax. Reimplementing Petrus private behavior
in Hamsterdan remains outside R2.

## Checkpoint R3 ruling

The plain question is: **should one bounded owner step be written as ordinary
nested async code that yields its actual leaf callable to a coroutine stepper,
with Timeline as the public debugger, or should every layer manually return
control through explicit prepare/execute values?**

Concrete example: a findings publication effect lands while
`workflow/readiness` is nested below host. Simulation must stop after the
provider call but before readiness records the terminal. After process loss,
the same production entry must reconstruct, call the same operation lookup-first,
and continue without a saved Python frame.

Options:

1. **Direct explicit owner APIs.** Add enough prepare/execute/record methods for
   each layer to expose the leaf. This avoids a coroutine stepper but repeats
   continuation plumbing and encourages control flow to become data.
2. **Timeline plus coroutine stepper.** Keep normal code, let the stepper route
   one callable and its result, and discard frames on restart. Timeline exposes
   the debugger positions; production uses the same stepper in a finite drain.
3. **Data trampoline or completed-result generator.** These remain wrappers
   around `step()` and do not solve the deep-call problem.

R3 rules option 2. Explicit bounded `step()` and `drain()` remain
the caller-facing production operations; `Timeline` is the simulation-facing
API; and `CoroutineStepper` is their shared cross-layer execution mechanism.
Explicitly forbid serialized frames, callable identity in durable artifacts,
Timeline- or stepper-owned scheduling choices, and more than one yielded leaf
per owner step.

The decision record linked above promotes the ruling. Unlike the first pass's
no-mechanism baseline, R3 deliberately shapes production owner APIs and the
simulation runtime. It does not authorize production implementation or settle
the exact final Timeline API.

## S9 handoff

S9 is unblocked by R3 and may assume:

- `Timeline` is the public deterministic execution surface;
- `CoroutineStepper` can `offer`, execute, and return one callable without
  knowing domain semantics;
- ordinary production uses composed `step()` and finite `drain(budget)`;
- Timeline control may stop before the callable, after it, or after the owner
  result, and S9 adds clock, journal, faults, crash, artifacts, and replay;
- replay artifacts record commands, deterministic choices, stable `CutRef`
  results, budgets, and crash generations, never callables or coroutine frames;
- reconstruction creates a fresh owner entry from durable module and adapter
  state;
- owner state, not the runtime, selects subjects, lanes, candidates, retries,
  timers, and fairness positions; and
- the spike's domain model is evidence only and must not be copied into the
  generic simulation runtime.

Exp 9 may model the two required Petrus capabilities but must not hide current
coarse production calls behind fine simulated names.

## Exit assessment

The original three spellings and the corrected callable-coroutine candidate are
now executable outside production. The evidence covers stack behavior,
cancellation, host fairness, callable and cut inspectability, replay vocabulary,
typing, one-call bounds, every returned-result reconstruction, and the exact
pre-effect/post-effect/pre-return positions that motivated the clarification.
Recovery uses serialized authority and the provider ledger only.

Timeline plus the callable coroutine stepper adds real leverage while keeping
the live frame disposable, so S8's amended recommendation is option 2 above.
The Navigator accepted the amended record, which meets experiment 8's exit
criterion. R3 is ruled and S9 may begin when separately authorized.
