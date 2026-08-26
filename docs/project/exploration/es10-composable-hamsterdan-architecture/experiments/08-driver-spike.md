# Experiment 8 — Driver mechanism spike

Session S8. Durable inputs: the ES-010 index and the accepted
[`07-step-contract.md`](07-step-contract.md). No other experiment record or
the engineering style contract was used. The executable evidence lives under
[`spikes/08-driver-mechanism/`](spikes/08-driver-mechanism/); it is
non-production exploration code.

Method: implement one retained-state model of the S7 workflow, readiness, and
host cuts; drive that exact model with an explicit loop, a data trampoline, and
a generator; serialize and discard the runtime after every returned cut; and
compare stack behavior, cancellation, fairness, inspectability, replay
vocabulary, type checking, and resource bounds. The pinned Petrus revision
`44cac5ff48ac371ebae56323941983f30db13c0d` was inspected only to answer S7's
two concrete public-seam questions.

## Verdict

Keep the **explicit step baseline**: each owner exposes one `step()`-shaped
operation returning the S7 result value, and production convenience drains are
ordinary finite loops with a validated budget. Do not introduce a trampoline
or generator as the workflow, readiness, or host driver mechanism.

The trampoline adds a second “what happens next” value even though durable
state already determines the next eligible step. If that bounce remains only
`step` it is redundant; if it names workflow/readiness lanes it becomes the
hidden scheduler S7 excludes. The generator adds a volatile frame. If the
frame carries authority, process reconstruction fails. If the frame is
disposable—as the passing spike requires—the generator is only syntax around
the explicit loop and adds cancellation and lifecycle concerns without
leverage.

This is a recommendation for checkpoint R3, not the R3 ruling. The R2 trees and
S7 contracts remain unchanged.

## Executable proof boundary

[`prototype.py`](spikes/08-driver-mechanism/prototype.py) gives all mechanisms
the same `World.step() -> StepResult` operation. The model contains:

- two PR subjects in a durable tail-requeue queue;
- bounded History replay of at most two records per page;
- one retained-occurrence repair per step;
- all 5 workflow, 16 readiness, and 10 host cut kinds named by S7;
- a durable effect ledger keyed by exact operation identity;
- a volatile observed-result cache that is deliberately absent from retained
  state; and
- a fixed maximum driver budget of 10,001 returned values.

`World.snapshot()` returns only serialized retained state and serialized effect
ledger state. `World.restore()` creates a fresh world with no observed result,
driver continuation, scheduler iterator, generator, or mutable handle from the
prior generation. Tests crash by taking that public snapshot after a returned
cut, dropping the world and driver, restoring, and creating a new driver. They
use no callback, monkeypatch, custom Dispatch, or private mutable runtime
access.

The host's `readiness_step_returned` result carries its readiness and workflow
cuts as nested detached references. This represents the three S7 driver
levels without allowing host to decode their semantics. Direct host custody,
posture, acknowledgement, route, requeue, and close writes remain separate
returned host cuts.

This model is intentionally not a miniature implementation of the R2 trees.
It tests only whether a control-flow spelling adds anything once the durable
step contract is fixed. Exp 9 owns generic deterministic runtime machinery;
Exp 10 owns module-real simulations.

## Three prototypes

### Explicit step

The explicit driver validates a finite budget, invokes `step()` once per loop
iteration, returns immediately on a non-progress disposition, and reports
budget exhaustion rather than false quiescence. Cancellation is checked before
the next call.

```text
for at most budget:
  result = step()
  if result is not Progressed:
    return result
return BudgetExhausted
```

There is no continuation value beyond durable state and the next ordinary call.

### Data trampoline

The trampoline uses an iterative `_Bounce(command="step")`. Every bounce still
calls the same `World.step()` and then creates the same bounce again. It avoids
recursion, but there is no recursion in the explicit baseline to remove. The
bounce carries no semantic authority in the passing prototype and therefore
adds no capability.

A richer bounce was rejected by construction. For example,
`Bounce(next="activity")` would duplicate readiness's durable lane eligibility;
after a crash either the bounce must become durable authority or readiness must
derive the answer again. The former creates a second scheduler, and the latter
makes the bounce redundant.

### Generator

The generator is the smallest viable spelling:

```text
while true:
  yield step()
```

It reaches every cut and does not recurse. On cancellation its frame can be
closed between yields. On crash the frame is discarded and a fresh generator
is created over the restored world. Therefore its instruction pointer, locals,
and yielded value cannot help reconstruction. If production started depending
on any of them, the mechanism would violate S7's durable-reconstruction rule.

The generator may remain an optional consumer-side presentation adapter over
step results. It is not selected as an architectural driver.

## Evidence

[`test_prototype.py`](spikes/08-driver-mechanism/test_prototype.py) executes the
same schedules for every mechanism.

| Evidence | Explicit step | Data trampoline | Generator | Finding |
|---|---|---|---|---|
| Baseline two-subject run | 207 results: 206 cut results then `Terminal` | identical | identical | Control-flow spelling does not change semantics |
| Cut vocabulary | 31 distinct S7 cut kinds | identical | identical | All inspectability comes from `StepResult`, not the driver |
| Crash after every returned cut | 206 reconstructions | 206 | 206 | 618 crash schedules reach the same semantic terminal state |
| Accepted effect followed by crash | recovery observes the same operation by lookup with 0 new effect calls | identical | identical after frame deletion | Durable operation identity and provider ledger, not continuation, prevent duplication |
| Effect-call bound | one call for each of two operation identities | identical | identical | Each step uses at most one external call |
| History-page bound | at most two records | identical | identical | Driver spelling does not provide resource bounds; the step does |
| Cancellation after seven cuts | stops before another call; restored driver continues | stops before another bounce; restored bounce is trivial | closes between yields; restored frame begins from retained state | Cancellation is cleanest without a continuation lifecycle |
| Two-subject fairness | 40 selections alternate and each turn invokes one readiness step | identical | identical | Durable queue/cursor provides fairness; mechanism does not |
| Long drive | 10,001 iterative calls without recursion | identical | identical, with one live frame | All have constant call-stack shape; the evidence report itself is bounded by the configured budget |
| Static checks | Ruff and `ty` pass | pass | pass | Types do not distinguish the candidates, but generator/trampoline add names and state |

The no-crash traces are exactly equal, including cut identity, nesting,
admission posture, rows, calls, and effect source. After a crash at
`activity_effect_observed`, the local semantic phase intentionally has not
advanced. Reconstruction observes the durable provider result by lookup,
returns `activity_effect_observed` again with zero calls, and only then records
the Activity terminal. Exactly one provider mutation remains recorded.

Recovery can consume one additional fair service turn. The final workflow,
readiness, custody, and effect state is equal to the no-crash terminal state,
while the monotonic host turn sequence may be greater. Treating scheduler
sequence as if it were workflow semantic state would be wrong; a replay with a
crash has an extra recovery allocation, and exact simulation replay records it.

The spike's `DriverReport` retains up to the fixed 10,001 result budget for
comparison. A production drain should retain only its bounded public report or
stream results to its bounded journal; this evidence collector is not a
production output-shape proposal.

## Cancellation and interruption boundary

All three mechanisms can stop between steps. None can make an external call
interruptible merely by changing Python control flow. An effect call still
needs the S7 adapter-owned timeout/cancellation contract, and an ambiguous
interruption still needs lookup-first recovery under the same operation
identity.

This distinction rejects a misleading generator argument: throwing into or
closing a generator cannot establish whether a remote effect landed. It only
changes a volatile local frame. The next generation must consult durable
provider truth exactly as the explicit baseline does.

Likewise, a stop requested after effect observation may suppress a new claim,
but it cannot suppress terminal settlement for the already-observed operation.
That is readiness eligibility, not driver cancellation policy.

## Fairness and scheduler ownership

The model persists subject order and puts each serviced subject at the tail.
Every selected subject receives exactly one readiness call before another
selection. With two continuously eligible subjects, selections alternate under
all mechanisms.

Neither a trampoline nor a generator improves this bound:

- A trampoline that chooses the next subject duplicates the host runnable
  index and cursor.
- A generator that retains iteration position loses that position on process
  death unless it is copied into durable host state.
- Once selection position is durable host state, both mechanisms merely read
  the same state that an explicit step reads.

Readiness lane fairness has the same result. The durable or reconstructible
lane cursor belongs to readiness; the outer driver calls one step and cannot
fairly override dependency ordering from outside.

## Pinned Petrus seam assessment

The mechanism spike confirms both S7 integration gaps. Control-flow syntax
cannot repair either one.

### Bounded load and reconciliation

At the pinned Petrus revision:

1. `Engine.load()` constructs `Instance.resume(...)` before returning an
   Engine. That resume consumes canonical History without a records-and-bytes
   page budget exposed to the caller.
2. `Engine.history_page(after, limit)` is a detached observation over the
   already resumed in-memory History. It cannot bound construction.
3. The first `Engine.advance()` calls `Coordinator.drive()`, which marks itself
   reconciled and then `_reconcile()` processes cancellation repairs, every
   undispatched in-flight invocation, every projection-pending occurrence, and
   every pure in-flight occurrence before observing and applying up to one
   normal action.
4. Direct Engine construction is guarded by a private construction token, and
   the provider composition door is private. Hamsterdan cannot split this work
   through a supported public composition seam.

Therefore current Petrus cannot expose S7's `history_page_replayed` and
`occurrence_repaired` as bounded production steps. A small public upstream
provider/runtime seam is required. The capability—not an API name ruled here—is
a provider-owned load cursor with explicit record and byte budgets, one retained
occurrence repair per call, and an `Engine ready` result before ordinary
advancement. Calling `Engine.load()` or first `advance()` and relabeling it as
one step remains invalid.

### Activity claim, effect, and terminal

At the same revision, `Worker.run_available(limit=1)` enters `_drain()`, claims
one Attempt, and calls private `_execute()`. `_execute()` resolves and invokes
the Activity, JSON-normalizes its result, and calls `complete()` or `fail()`
before returning. The asynchronous Worker likewise combines invocation and
terminal reporting inside its private execution path.

`WorkerDispatch` exposes claim and terminal custody operations, but Petrus does
not expose its Activity resolution/execution as a public “execute one Attempt
and return a detached observation without reporting it” operation. Reimplementing
private Worker behavior in readiness would duplicate Motus execution and move
that ownership across the R2 seam.

Therefore S7's `activity_attempt_claimed`, `activity_effect_observed`, and
`activity_terminal_recorded` cuts need a public Petrus/Motus single-Attempt
execution seam, or an equivalent upstream composition explicitly supported by
Petrus. The observed value may remain a volatile optimization between adjacent
steps; after its loss, the Activity's ruled lookup-first operation must derive
the terminal again. S8 does not choose the final upstream API.

These are candidate delivery dependencies, not production defects introduced
by this experiment and not a reason to alter R2.

## Recommendation for checkpoint R3

The plain question is: **should Hamsterdan's bounded production and simulation
drivers call an explicit step in a finite loop, or should another continuation
mechanism sit between the caller and durable state?**

Concrete example: findings publication lands, the process dies before its
Activity terminal is recorded, and the host later selects that PR again. The
next action must come from retained Activity custody, provider operation truth,
readiness posture, and host queue state. A lost bounce or generator frame must
not decide whether to publish, record, or requeue.

Options and consequences:

1. **Rule the explicit step baseline.** One public result crosses one cut;
   finite loops are convenience callers. This has the fewest states and makes
   budgets, cancellation, replay, and inspection direct.
2. **Rule a data trampoline.** A trivial bounce is harmless but redundant. A
   meaningful bounce duplicates scheduler state and needs new durable authority.
3. **Rule a generator.** A disposable frame is a presentation wrapper with no
   leverage. An authoritative frame is unrecoverable and invalid.

Recommendation: rule option 1 and explicitly reject trampoline or generator
continuations as durable or scheduler authority. This leaves local
consumer-side iteration style reversible and does not prescribe whether an
implementation uses a `for` or `while` statement internally.

No decision record is recommended. The result preserves the S7 baseline, is
not surprising once durable authority is fixed, and remains mechanically easy
to revisit. The accepted S7/S8 exploration records are sufficient unless the
Navigator wants the ruling discoverable outside ES-010.

## S9 handoff

S9 remains blocked on the R3 ruling. If R3 accepts the recommendation, S9 may
assume:

- one runtime turn invokes one module-owned step and records its detached
  result;
- convergence helpers are validated finite loops over that same operation;
- runtime cancellation occurs between steps, while operation interruption is a
  module/adapter contract;
- eligible ordering and fairness cursors remain with module or host durable
  state, never the generic runtime;
- replay journals contain commands, choices, cut results, budgets, and crash
  generations, not continuation frames; and
- the S8 prototype's domain model is evidence only and must not be copied into
  the generic simulation runtime.

The two Petrus seam gaps remain inputs to later Delivery expansion. Exp 9 can
model the public target capabilities but must not hide current production calls
behind coarse simulated steps.

## Exit assessment

All three mechanisms were prototyped outside production and compared over the
same contract. Fresh construction after every returned cut reaches terminal
state from serialized authority alone. Stack, cancellation, fairness,
inspectability, replay vocabulary, typing, and resource evidence are explicit.
Generator-frame authority and trampoline scheduling are rejected.

The alternatives add no leverage, so the explicit step baseline remains the
selected recommendation. Experiment 8 meets its exit criterion and the
Navigator accepted the record. R3 remains unruled pending a separate mechanism
ruling.
