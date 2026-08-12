# AX9 — Effect-oriented activity authoring

- State: Completed, 2026-08-12.
- Question: does describing an activity's work as yielded effect values
  improve authoring of complex activities — and do effects belong inside
  one Petri transition (Interpretation A) or compiled into net structure
  (Interpretation B)?
- Verdict: **Promising with changes** — Interpretation A only. Effects
  are an *activity-authoring* mechanism interpreted transiently inside a
  worker; they must not become a workflow-structure source language.
- Spike: [`ax9_effects.py`](ax9_effects.py) (A),
  [`ax9_tracing.py`](ax9_tracing.py) (B),
  [`test_ax9_effects.py`](test_ax9_effects.py) — 12 tests.

## The program under test

```python
def settle_payment(payment: Payment) -> Settlement:
    reservation = yield ReserveFunds(payment.account_id, payment.amount)
    result = yield SendPayment(reservation.reservation_id)
    yield EmitEvent("payment_settled", result.reference)
    return Settlement(reference=result.reference)
```

Effects are frozen dataclass values with worker-side handlers registered
in an `EffectRuntime` (`{effect type: EffectHandler(perform, result)}`).
Nothing about the generator is ever durable.

## Interpretation A: journaled interpreter inside one activity

`effect_activity(program, runtime=...)` adapts the generator to the
frozen synchronous `Activity` protocol — the same duck-typed surface
`petrus.motus.activity.ActivityDefinition` implements, except this
definition **uses** its execution context instead of discarding it.

The durable state is a JSON journal of completed effects
(`[{"effect": fingerprint, "result": encoded}, ...]`), not a frame:

- Every attempt reconstructs the generator from scratch and replays it
  deterministically: journaled steps get their recorded results
  `send`-ed back in; only the first un-journaled effect executes.
- The journal rides the frozen dispatch's **heartbeat details channel**.
  This is the decisive discovery: `LocalWorkerDispatch.claim` returns
  the details persisted by the previous attempt's last heartbeat
  (`SELECT ... t.details` into `ActivityAttempt.latest_details`), so a
  crashed worker's successor resumes mid-program with **zero Petrus
  changes**. Proven end-to-end: attempt 1 journals `ReserveFunds` then
  fails retryably inside `SendPayment`; attempt 2 re-reserves nothing
  (`ReserveFunds` performed exactly once, `SendPayment` twice).
- The Petri net sees **one** activity: three effects produced exactly one
  `ActivityRequested`/`ActivityCompleted` pair through `Engine` +
  `InlineDispatch`.

Semantics made explicit rather than hidden:

- **At-least-once per effect.** A crash after an effect performs but
  before its journal heartbeat lands re-performs that one effect on the
  next attempt (proven with a heartbeat that dies between perform and
  checkpoint). Effect handlers carry the same idempotency obligation
  activity implementations already carry — the journal narrows the
  redo window from "the whole activity" to "one effect", it does not
  eliminate it.
- **Determinism is a contract, not a hope.** Each yielded effect is
  fingerprinted (`TypeName:{canonical json}`); replay divergence raises
  `NondeterministicEffectProgram` naming the step, the journaled
  fingerprint, and the yielded one.
- **Loud registry.** An unregistered effect type fails listing the known
  effects; a plain (non-generator) function is refused toward
  `petrus.motus.activity`.

Boundaries found on the frozen runtime:

- `InlineDispatch` resets `latest_details=None` on every inline retry
  attempt, so journal resume is real only under `LocalDispatch` (and
  presumably other persistent providers). Inline execution still works —
  it just re-runs the program from an empty journal.
- Heartbeat details are capped at 65,536 encoded bytes and are one
  exclusive slot per occurrence: an effect journal competes with any
  other use of heartbeat details, and long programs with fat results
  will not fit. A production design needs journal size accounting.
- `DerivedActivityHandler.prepare` constructs invocations with the
  default `ExecutionPolicy()` (attempts=1); multi-attempt resume
  requires the policy to reach the invocation — a binding-layer concern
  the spike sidestepped by dispatching by hand.

## Interpretation B: effects compiled into net structure

The same generator is traced **once at compile time** with symbolic
proxies (`TraceValue` recording field paths), producing a static
`EffectProgramGraph` — steps with `Ref`-wired arguments — which lowers
to a linear net: enter → one activity transition per effect (threading
an environment token) → return projection.

It works, and that is exactly what condemns it:

- **Straight-line only.** `if reservation.approved:` raises
  `TraceBranchError` at trace time, because a proxy cannot answer
  `__bool__`. Any control flow must come back as workflow combinators —
  at which point B *is* the AX1–AX8 authoring model wearing a generator
  costume, with worse error locality and hidden topology.
- **Net and history inflation.** The three-effect program became 5
  transitions, 6 places, and 5 `ActivityRequested` records versus 1
  under A.
- **Type erasure.** Every intermediate place is an untyped `dict`
  environment token — the typed places the whole workflow layer fights
  for disappear. Recovering them means generating per-step dataclass
  types, i.e., building a compiler for a worse source language.
- What B genuinely buys — per-effect durability in History, native
  cancellation between effects, per-effect observability — is available
  by authoring those steps as ordinary workflow activities when they
  deserve it.

## Comparison

| Concern | A (journaled interpreter) | B (compiled structure) |
| --- | --- | --- |
| Durability | journal in heartbeat details (LocalDispatch) | native History per effect |
| Replay | deterministic re-execution against journal | ordinary net replay |
| Worker crash | resume from last journaled effect | resume at last completed transition |
| Idempotency window | one effect | one effect |
| Serialization | JSON journal, 64 KiB cap | unbounded History |
| Cancellation | between-effect heartbeats only | between transitions, native |
| Observability | opaque inside one activity (journal visible) | full, but noisy |
| Net size | 1 transition | grows per effect |
| Control flow | full Python (deterministic) | none — traced straight-line |
| Ergonomics | natural imperative code | generator that lies about being code |

## Where effect-oriented programming belongs

**Inside activities, as an optional worker-side idiom** — Interpretation
A. The workflow AST (AX1–AX8) remains the only structure language; the
Petri net remains the only durable topology; effects give a complex
activity internal checkpoints without inventing places or transitions.
Generators are used strictly as re-executed deterministic syntax; live
frames never persist. Interpretation B is rejected: it duplicates the
combinator layer with a weaker, opaquer source language.

Follow-up carried to the ledger: SP-6 (the heartbeat-details channel as
de-facto checkpoint store — size cap, exclusivity, and policy plumbing
through `DerivedActivityHandler`).
