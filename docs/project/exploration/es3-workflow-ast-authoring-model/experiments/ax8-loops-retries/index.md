# AX8 — Loops, cycles, and retries from a tree-shaped AST

Completed 2026-08-11. **Verdict: Promising; continue.**

## Design question

Can a tree-shaped workflow AST represent a cyclic Petri net — and where
do loop state, loop guards, retry counts, and re-arming live when it
does?

## Hypothesis confirmed

*The authoring AST may remain a tree even when compilation produces a
cyclic graph.* `Retry` is one tree node; the cycle exists only in the
lowering, as exactly one loop-back arc (`w.rearm → w.entry`). The AST
stays traversable, printable, structurally comparable, and serializable
— nothing about authoring becomes graph-shaped.

## Authoring surface

```python
retry(
    charge,  # -> Confirmed | Transient | Fatal
    case(Confirmed, then=step(record)),
    case(Fatal, then=step(refund)),
    retryable=Transient,
    rearm=rearm_charge,        # pure typed: Transient -> ChargeRequest
    limit=3,
    exhausted=step(escalate),  # Transient at the attempt limit
)
```

Retry is the union machinery pointed backwards: the source activity
returns `Confirmed | Transient | Fatal` (AX5 variants, durable
`$variant`), the retryable variant splits on a compiled counter guard
(AX6 filters), and every other variant exits through its own case.

## Where everything lives — the experiment's stated questions

| Concern | Answer | Durability |
| --- | --- | --- |
| Loop state | The counter is a declared **domain field** on the retryable variant (`Transient.attempt: int`), validated to exist at construction | Token data — replayed, visible in every marking and predicate |
| Loop guard | `on(Transient).attempt < limit`, built with the AX6 typed proxy at construction, rendered to two CEL filters: `(attempt < 3)` loops, `!(attempt < 3)` exhausts | Net definition — serialized with `NetDefinitionV3` |
| Retry count semantics | `attempt` counts tries made; entry tokens start at 1; exhaustion exits after exactly `limit` durable attempts | History — `ActivityRequested.input` shows `attempt` 1, 2, 3 |
| Re-arming | A pure typed function `Transient -> ChargeRequest` lowered onto the frozen `derive_typed_transform`: inline, deterministic, no dispatch | Re-executed on replay like any pure handler |
| Timers/delays | **No timer primitive exists anywhere in frozen Petrus** (verified by search). "Wait then retry" is representable today only as worker-side delay inside an activity or as driving-policy pacing | Not representable declaratively — recorded honestly |

## Generated cyclic net

```text
w.entry(ChargeRequest) ──▶ charge ──▶ on_confirmed ─▶ record ────┐
       ▲                        ├───▶ on_fatal ─────▶ refund ────┤ XOR merge ─▶ w.out(Receipt)
       │                        └───▶ on_transient               │
       │                                ├─[(attempt < 3)]──▶ rearm
       │                                └─[!(attempt < 3)]─▶ to_exhausted ─▶ escalate ─┘
       └────────────────────────────────────── (the one loop-back arc)
```

The compiled network stays understandable: eight transitions, seven
places, and the cycle is one arc whose `generated_by` entry points at
the `retry` node's authoring line.

## Evidence (15 tests)

- Shape: retryable not in the union, counter field missing on the
  retryable variant (`Fatal` refused with the field inventory), rearm
  with the wrong parameter or return type, non-positive limit, and
  uncovered non-retryable variants — all construction errors with
  remedies.
- Lowering: the loop-back arc targets `w.entry` with the input color;
  the two counter filters sit on the retryable place's out-arcs; the
  source map resolves `w.rearm` and `w.to_exhausted` back to the retry
  node.
- Runtime: success after one retry (`charge, charge, record` — each
  attempt a separate durable activity round-trip); immediate fatal takes
  the error path without looping; exhaustion exits after exactly 3
  attempts; `ActivityRequested.input` shows the counter advancing
  1 → 2 → 3 in durable history.
- Replay: a run containing loop iterations replays over a freshly
  recompiled cyclic net to the same terminal state — nothing about
  cycles needed new replay machinery.
- **The honest limitation**: a type-correct rearm that forgets to
  increment passes every static check and loops forever. The compiler
  cannot prove counter progress; bounded driving (`did not quiesce`) is
  today's diagnostic. A future compiler could warn when the rearm is not
  syntactically `counter + 1`-shaped, but semantic progress is
  undecidable — recorded, not hidden.

## Workflow-level vs worker-level retry

These are different tools, not competitors:

- **Worker-level retry** (Dispatch redelivery, at-least-once execution)
  re-runs the *same* invocation. Invisible to the net, no per-attempt
  history facts, no routing on failure kind, no rearm transform — right
  for transient infrastructure faults where the invocation itself is
  idempotent.
- **Workflow-level retry** (this combinator) makes each attempt a
  durable fact with its own occurrence, routes by failure *type*
  (`Transient` loops, `Fatal` exits), can transform the request between
  attempts, bounds attempts with a durable guard, and gives the
  exhausted path first-class routing. Right when retrying is business
  behavior the process must observe.

A real system wants both; the authoring layer only needs to express the
second.

## Open questions carried forward

- `while_do`/`repeat_until` generalizations: the same lowering shape
  works (guard on the loop-back arc, body as the cycle), but the loop
  variable contract — which field, who advances it — needs the same
  explicitness `retry` has. Not spiked; `retry` was the sharpest
  instance.
- Backoff/delay between attempts needs either a timer speculation
  (SP-5) or worker-side sleeps; neither belongs in the topology today.
- Nested retries (retry inside a retry case) should compose by
  construction but were not exercised.
