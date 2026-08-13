# 7 — Cycles

**Rely on this: author trees, compile cycles — and put the loop
variable where it durably lives, which is often with the provider.**

## What it is

The authoring expression stays a tree even when the compiled net is
cyclic: a `loop` fuses one named exit back to the block's own entry.
Loop *state* (the retry counter, the attempt number) rides in the
token data, evolved by an ordinary step; the loop *guard* is an
ordinary outcomes-decision that either takes the looping exit or one
of the terminal exits.

Two kinds of repetition, two owners:

- **Transport retry** (the network blipped) — the worker's job,
  invisible to the net (concept 2).
- **Domain retry** (attempt, classify, maybe re-attempt) — workflow
  structure, authored as a loop with a bounded counter and an explicit
  exhaustion exit.

## The idea

```python
attempt_once = outcomes("attempt", try_fn,
    accepts=Job,
    outcomes={
        "done":      Result,
        "retryable": Job,          # counter incremented inside try_fn's token
        "exhausted": Exhausted,    # tries >= limit → terminal exit, not an error
    })

retrying = loop(attempt_once, on="retryable")
# exits now: done | exhausted — the looping exit is consumed by the cycle
```

When the process itself is the iteration, don't loop at all — let the
world carry the variable. The escalation-ladder shape:

```text
failure@attempt=1 → rerun once → reproduced failure
→ repair (once per fingerprint) → new head → next generation
→ same fingerprint again → escalate to the human rung
```

Each rung emits at most one identity-deduped operation; "iteration" is
the next generation arriving from outside; boundedness is structural.

## What it does not do

- No termination proofs: a loop's progress depends on token data, so
  composition cannot decide it. The honest tool is bounded driving
  with a directed diagnostic (concept 14), never silent spinning.
- No hidden loop state: if the counter isn't in the token or with the
  provider, it doesn't exist.
- Timers for pacing between attempts are typed ingress (concept 12),
  not sleeps inside the net.

## What it compiles to

One rename. `loop(block, on="retryable")` rewrites the looping exit's
place to be the block's **own entry place** — that single substitution
is the entire cycle:

```diagram
before:  in ─▶ [attempt] ─▶ done
                        └─▶ retryable        ← a normal exit place
                        └─▶ exhausted

after:   in ─▶ [attempt] ─▶ done             ← "retryable" arcs now
          ▲             │                       produce into "in"
          └─────────────┘
               [attempt] ─▶ exhausted
```

No loop node, no iteration counter in the structure — the counter
rides in the token (evolved by `try_fn`), and the guard is the
ordinary outcomes-decision that chose `retryable`. Refused when the
looping exit is the block's only exit (no way out). Mechanics:
[chapter 16](16-how-the-authoring-compiles.md). Exact code:
[ax23_blocks.py](../es3-workflow-ast-authoring-model/experiments/ax23-completed-algebra/ax23_blocks.py)
(`loop`).

## How it relates

- Concept 5 supplies the loop guard (it's just an outcomes-decision).
- Concept 10's epoch machine is the generational "loop" at case scale.
- Concept 12 paces retries durably.

## Why trust it

ES-003 AX8 compiled cycles from tree ASTs and replayed them; AX23's
`loop` ran the data-driven bounded retry on the real engine. ES-004
AX10 showed production's one real cycle is domain structure whose loop
variable was GitHub's all along — the monotonic fence over `(run_id,
attempt, conclusion)` replaced a place, a transition, a predicate, and
three read arcs.
