# 2 — Work and routing

**Rely on this: the net routes, workers work — and every effect is
attempted, classified, and identified, never prevented or assumed.**

## What it is

Side-effecting work (an *activity*) is never executed by the net. The
net records that work was requested; a dispatcher hands it to a worker
outside; the completion re-enters the net as a token. Delivery is
at-least-once, so every effect needs three disciplines:

1. **Operation identity** — a deterministic name for this exact piece
   of work (`dashboard:{epoch}:{head}:{digest}`), so a replayed or
   duplicated request collapses into the same operation.
2. **Lookup-first** — before doing, look whether it was already done
   (the marker comment, the commit trailer). Handles idempotency kind
   one: *"did this before → skip."*
3. **Outcome classification** — when doing it again *fails because the
   world changed*, that is not an error. Handles idempotency kind two:
   *"preconditions changed → already done, or moot → take the
   matching exit."*

The posture is **attempt-first**: do not pre-check whether the world
will accept the effect; attempt it and classify what the provider
actually said.

## The idea

```python
# an activity declares its domain outcomes as typed exits — not exceptions
activity("advance_ref",
    outcomes={
        "committed": ProvisionalHead,     # it worked
        "moved":     BranchMoved,         # CAS refused: world changed — NOT an error
        "fault":     NonrecoverableFault, # genuinely broken
    },
    identity=lambda job: f"advance:{job.epoch}:{job.head}",
)
```

The gate's own refusal *is* the staleness signal — no separate
staleness checking machinery.

## What it does not do

- It does not make effects exactly-once. At-least-once plus identity
  plus lookup-first is the whole guarantee.
- It does not put retry loops in the net for transport failures —
  transport retry is the worker's job; the net sees only *domain*
  outcomes (concept 7 covers workflow-level retry).
- It does not encode effects as net structure. Complex multi-effect
  activities stay inside one activity, interpreted by the worker; a
  live generator frame is never durable state.

## How it relates

- Concept 8 catches what no outcome modeled (the failure rail).
- Concept 9 narrows "effect" to exactly two gate types.
- Concept 10's epochs make stale completions inert on arrival.

## Why trust it

ES-001 established the ownership split (engine/dispatcher/worker,
at-least-once). ES-003 AX21 ran typed outcomes with lookup-first on the
real engine; AX9 proved effects-inside-one-activity and killed
effects-as-net-structure. ES-004 AX3 demonstrated attempt-first on the
git CAS gate: stale authority → agent ran, fence refused,
`world.comments == []`.
