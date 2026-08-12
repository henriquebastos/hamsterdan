# AX21 — Typed effect outcomes: the at-least-once boundary classified

**Status:** complete — Promising; continue.
**Question:** The Navigator identified two kinds of idempotency: "if I
did this before, don't do it" (easy — dedup on the input) and "if I
did this before, it will now *fail* — but how do I know I did it?"
(hard — the failure needs classification). Can both live as net
structure on the frozen engine, with "already done" and "preconditions
changed" as *places* rather than exceptions?

**Hypothesis:** Kind one is the delivery door's operation-identity
dedup (proven in AX19). Kind two is lookup-first classification at the
effect itself, returning a **typed outcome routed by color** (the AX5
mechanism aimed at failure): `Applied | AlreadyApplied | Stale |
Transient`, each an output place with its own downstream path, and
only `Transient` loops.

## What was built

[ax21_boundary.py](ax21_boundary.py) authors the boundary in AX19
kernel notions over a fake external `Ledger` with the three real
behaviors — a compare-and-swap base, an operation-identity record (the
lookup target), and scheduled transient faults.
[test_ax21_boundary.py](test_ax21_boundary.py), twelve tests, every
behavioral one executing the frozen `Engine`.

The shape is a function signature — one entry, three typed exits,
`apply : Work → Done | Rejected | Exhausted` — the AX20 fractal again:

    submit → requests → [apply] → applied ─────────[finish]→ done
                 ▲            → already_applied ──[adopt]─→ done
                 │            → stale ──────────[abandon]→ rejected
                 └─[retry]──── transient ────────[give_up]→ exhausted
                    (attempts < 3)                (complement)

`apply` is the only transition that touches the ledger; it classifies
and never raises. Two successes converge on `done` (modes `applied` /
`adopted` — the AX5 later-merge). The retry cycle is the AX8
tree-authored loop with the AX20 complement discipline
(`attempts < 3` / its negation).

## Findings

- **The two idempotencies are two different mechanisms at two different
  net locations.** A repeated delivery identity never creates a second
  token (door; ledger invoked once). A duplicate *work* token — same
  operation through a different door — reaches the ledger, classifies
  `AlreadyApplied`, and is **adopted**: one application in the ledger,
  two tokens in `done`, no error anywhere. The "success wearing an
  error's clothes" is a normal path.
- **Classification order is doctrine, stated as code: lookup answers
  before preconditions.** An operation applied under base `e1` and
  redelivered after the base moved to `e2` is `AlreadyApplied`, *not*
  `Stale` — the work exists; the world merely moved on afterward. A
  boundary that checked preconditions first would wrongly discard a
  completed operation. This ordering is the experiment's sharpest
  transferable rule.
- **Stale is not an error.** A moved base routes to `rejected` and the
  engine quiesces normally — no exception, no error event, nothing
  applied. Restart is a fresh submit with current coordinates (the
  AX20 ruling carried through the boundary).
- **Only Transient loops, and the loop is bounded by construction.**
  Two scheduled faults → two retries → landing, with the attempt count
  in the token (`attempts == 2`, three invocations). A hundred faults →
  `exhausted` after `MAX_RETRIES`, engine quiesced — the complement
  guard ends the cycle; no infinite loop is expressible.
- **Replay never talks to the outside world.** The replay test resumes
  from history against a *fresh* ledger that would classify differently
  if consulted — the marking matches and `fresh_ledger.invocations ==
  0`. Petri-handler results are recorded history, not re-executed
  effects: exactly the durability property kind-two idempotency needs.
- **The structure stays bounded.** 8 places, 7 transitions, 16 arcs,
  2 guards (the complementary loop pair), max place degree 3 — the
  bounded-hub-degree invariant from the AX20 discussion, now asserted
  as a test rather than observed after the fact.

## Boundaries stated honestly

- The `Ledger` is a fake: real external systems distinguish these four
  outcomes with far messier evidence (timeouts where the effect may or
  may not have landed). The pattern *requires* the effect executor to
  return a classification; a timeout is `Transient` only if the
  operation is lookup-able on the next attempt — which the
  lookup-first ordering then resolves. The classification burden is
  real and lives in the activity author's territory.
- Exhaustiveness is handler discipline, not engine enforcement: a
  handler that returned an unrouted color would be a bug the kernel
  cannot catch today. A composition layer should own that check
  (outcome set ⊆ declared output places).
- Retry here is *workflow-level* (visible places, durable attempts,
  bounded loop). Worker-level retry beneath the dispatcher still exists
  for delivery faults; AX8's distinction stands — this experiment does
  not collapse the two.
- `MAX_RETRIES` is baked into the rendered guard; a parameterized net
  would carry it in a config token or regenerate the net (AX17
  evolution rules apply).

## Verdict

**Promising; continue.** The failure taxonomy is net structure on the
frozen runtime: outcomes are colors, "already done" and "preconditions
changed" are ordinary places with ordinary successors, retry is a
guarded bounded cycle, and replay is safe because recorded outcomes —
not re-executed effects — drive resumption. Together with AX20 this
completes the fenced-boundary story: AX20 decides *whether the work is
still valid*; AX21 decides *what the world said when we acted*. Both
decisions are typed exits of function-shaped subnets — the composition
layer (candidate AX22) can now treat `Work → Done | Rejected |
Exhausted` as a signature.
