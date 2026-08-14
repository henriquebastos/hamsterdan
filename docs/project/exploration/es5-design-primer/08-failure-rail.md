# 8 — The failure rail

**Rely on this: the rail carries what nobody modeled; modeled outcomes
carry what somebody did.**

## What it is

Railway-oriented failure handling as pure structure over the algebra —
no engine feature, no exception magic. `attempt` totalizes a step:
whatever the step's body raises becomes a durable, JSON-safe *failure
envelope* (kind, message, source, retryable, cause chain) leaving
through a dedicated `failed` exit. Chaining attempted steps merges
their rails structurally, so after any chain there is exactly **one**
failure place — visible, on-path, typed. Steps after a failure never
run. `recover` rejoins the success track with a total handler that
receives the envelope.

The doctrine that keeps the rail honest: a *domain* outcome may never
ride it. An exit that means something ("stale", "rejected",
"exhausted") is typed vocabulary from concept 5 — the rail refuses to
swallow it, structurally, because rails merge by the failure color
only.

## The idea

```python
pipeline = rail_then(rail_then(parse(), enrich()), store())
# exits: out | failed        ← exactly one rail place for the whole chain

healed = recover(pipeline, handler=fallback_fn)   # envelope in, success out
# exits: out                 ← total again

# refused, by color: an exit named "failed" carrying DomainRefusal
# will not fuse into the rail — model it or rename it.
```

## What it does not do

- It does not replace outcome classification at gates (concept 2's
  "moved is not an error" stays a modeled exit).
- It does not retry — pair it with concept 7 when a failure is worth
  re-attempting.
- It does not preserve stack traces as behavior: the envelope is
  durable data for routing and diagnosis, exact through JSON
  round-trips.

## What it compiles to

No new machinery — the rail is three arrangements of chapter 3/4
rules, which is why it needed only ~60 spike lines:

```python
# condensed exact — ax25_rail.py
attempt(name, fn)          # outcomes(name, totalized(fn),
                           #   {"out": returns, "failed": FAILURE})
                           # fn raises → envelope token on "failed"
rail_then(a, b)            # then(a, b, on="out")
                           #   + merge both "failed" exits → ONE place
recover(block, handler)    # then(block, handler, on="failed")
                           #   + merge recovery back into "out"
```

```diagram
in ─▶ [parse] ─▶ ok ─▶ [enrich] ─▶ ok ─▶ [store] ─▶ out
          │                │                │
          └────────────────┴────────────────┴──▶ failed (Failure)
                                                 one place — merged,
                                                 not three conventions
```

Mechanics: [chapter 16](16-how-the-authoring-compiles.md). Exact
code: [ax25_rail.py](../es3-workflow-ast-authoring-model/experiments/ax25-failure-rail/ax25_rail.py).

## How it relates

- Concept 5's modeled outcomes are the rail's complement — the refusal
  between them is the design line.
- Concept 6: rail effectful parallel branches *before* the join.
- Concept 2's `fault` outcomes usually feed the rail's terminal end.

## Why trust it

ES-003 AX25 built the rail as ~60 lines of arrangement over the
unchanged algebra: one failure place per chain (counted, not assumed),
exact envelope round-trip asserted, and the domain-exit refusal tested
— the doctrine exists as a failing test, not a guideline.
