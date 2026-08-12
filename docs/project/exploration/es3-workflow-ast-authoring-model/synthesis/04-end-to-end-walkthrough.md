# Lens — How it works: one workflow through every representation

One canonical workflow — **receive an order → in parallel (reserve
inventory, calculate taxes) → charge → judge and route** — traced
through every intermediate representation, from the line an author
types to a replayed marking.

Everything below is **real captured output**, not idealized: it comes
from [`capture_walkthrough.py`](capture_walkthrough.py), which runs the
actual spike code (AX26 typed façade → AX23 algebra → AX18/19 kernel →
frozen Petrus engine). The full deterministic capture is committed as
[`walkthrough-capture.txt`](walkthrough-capture.txt); re-run the script
from the repo root to regenerate it:

```bash
.venv/bin/python docs/project/exploration/es3-workflow-ast-authoring-model/synthesis/capture_walkthrough.py
```

The one idea to hold before reading: **authoring and execution never
happen at the same time.** Stages 1–5 happen when the developer writes
and compiles code — no engine exists yet, nothing has side effects.
Stages 6–8 happen at runtime, possibly days later, possibly resumed
after a crash. Each stage exists to *validate something* before the
next stage is allowed to happen:

```diagram
 AUTHORING TIME (stages 1–5)                      RUNTIME (stages 6–8)
┌─────────────────────────────────────────────┐  ┌──────────────────────────────┐
│ 1 authoring expression   (editor + pyright) │  │ 6 engine execution           │
│         │ typed composition                 │  │      │ firings append to     │
│         ▼                                   │  │      ▼                       │
│ 2 typed value TBlock[Raw, Done]  (advisory) │  │ 7 persisted History          │
│         │ .inner                            │  │      │ replay over the       │
│         ▼                                   │  │      ▼ recompiled net        │
│ 3 Block value    (composition invariants)   │  │ 8 identical marking          │
│         │ nodes                             │  └──────────────────────────────┘
│         ▼                                   │        ▲
│ 4 kernel places/transitions/arcs            │        │ byte-identical
│         │ check_sound + lower               │        │ recompilation is what
│         ▼                                   │        │ makes replay legal
│ 5 serialized NetDefinition (deterministic) ─┼────────┘
└─────────────────────────────────────────────┘
```

---

## Stage 1 — The authoring expression

What the author writes, in `cases_good.py` (AX26). Typed leaves first —
plain functions with TypedDict signatures:

```python
def _parse(raw: Raw) -> Order: ...
def _reserve(order: Order) -> Reservation: ...
def _taxes(order: Order) -> Taxes: ...
def _charge(joined: Join2[Reservation, Taxes]) -> Receipt: ...
def _judge(receipt: Receipt) -> tuple[Literal["yes"], Receipt] | tuple[Literal["no"], Review]: ...

parse   = t_pure("parse", _parse, accepts=Raw, returns=Order)
reserve = t_step("reserve", _reserve, accepts=Order, returns=Reservation)
taxes   = t_pure("taxes", _taxes, accepts=Order, returns=Taxes)
charge  = t_step("charge", _charge, accepts=Join2[Reservation, Taxes], returns=Receipt)
judge   = t_split("judge", _judge, accepts=Receipt, yes=Receipt, no=Review)
```

then the composition — the entire workflow, no places, transitions, or
arcs mentioned anywhere:

```python
both     = t_par2("both", first=reserve, second=taxes)
routed   = t_route(judge, when_yes=settle, when_no=escalate, returns=Done)
workflow = t_then(t_then(t_then(parse, both), charge), routed)
```

**What this stage validates:** pyright (and, partially, ty) checks the
composition *as you type*. Swap `reserve` and `charge` and the editor
reports `"Order" is not the same as "Join2[Reservation, Taxes]"` on
the offending argument. Eight of nine deliberate mistakes fail here
(AX26's pinned catch matrix) — before any code runs.

## Stage 2 — The typed value

```text
type(workflow)  = TBlock
static type     = TBlock[Raw, Done]   (revealed identically by pyright and ty)
```

`workflow` is an ordinary frozen Python value. Its static type says:
give it a `Raw`, it will produce a `Done`. This layer is **advisory** —
it exists so mistakes fail in the editor; it adds nothing at runtime
and lowers away completely in the next stage.

## Stage 3 — The Block value (the algebra's view)

`workflow.inner` is the untyped AX23 `Block` — the composition
algebra's structured value (captured verbatim):

```text
name    = '(((parse >> par[both](first, second)) >> charge) >> ((judge >> settle) >> escalate))'
pure    = False
entry   = Port(place='parse_in', color='Raw')
exits:
  'out': Port(place='settle_out', color='Done')
contexts: {}
```

Note the shape: the whole workflow is itself a block with **one entry
and one exit** — composition is closed. The name records the
composition history; the TypedDicts have become nominal color
*strings* (`'Raw'`, `'Done'`).

**What this stage validates:** the deterministic composition rules —
color-mismatched fusion, unknown exits, duplicate leaf names, impure
blocks passed to `disposable`, non-total branches passed to `par` —
all raise `CompositionError` here, with remedies in the message. This
is the authoritative check; the editor layer was only its shadow.

## Stage 4 — The kernel nodes (AX18/19 IR)

Inside the block: 11 places and 9 transitions, all named, all typed
(captured verbatim):

```text
places (name: color):
  parse_in: Raw            reserve_in: Order        charge_out: Receipt
  parse_out: Order         reserve_out: Reservation judge_yes: Receipt
  both_out: Join2[Reservation, Taxes]               judge_no: Review
  taxes_in: Order          taxes_out: Taxes         settle_out: Done

transitions (arcs as mode(place)):
  parse:     consume(parse_in), produce(parse_out)
  reserve:   consume(reserve_in), produce(reserve_out)
  taxes:     consume(taxes_in), produce(taxes_out)
  both:      consume(parse_out), produce(reserve_in), produce(taxes_in)
  both_join: consume(reserve_out), consume(taxes_out), produce(both_out)
  charge:    consume(both_out), produce(charge_out)
  judge:     consume(charge_out), produce(judge_yes), produce(judge_no)
  settle:    consume(judge_yes), produce(settle_out)
  escalate:  consume(judge_no), produce(settle_out)
```

As a net — every AX24/AX23 semantic decision is *visible structure*:

```diagram
                        ┌─────────┐
 Raw ──▶(parse_in)──▶───│  parse  │──▶(parse_out: Order)
                        └─────────┘         │
                                       ┌────▼────┐   AND-split (par "both")
                        ┌──────────────│  both   │──────────────┐
                        ▼              └─────────┘              ▼
                  (reserve_in)                             (taxes_in)
                        │                                       │
                  ┌─────▼─────┐                           ┌─────▼─────┐
                  │  reserve  │                           │   taxes   │
                  └─────┬─────┘                           └─────┬─────┘
                        ▼                                       ▼
                 (reserve_out)                            (taxes_out)
                        │              ┌───────────┐            │
                        └─────────────▶│ both_join │◀───────────┘   AND-join:
                                       └─────┬─────┘                one token per
                                             ▼                      branch, waits
                          (both_out: Join2[Reservation, Taxes])     for both
                                       ┌─────▼─────┐
                                       │  charge   │
                                       └─────┬─────┘
                                        (charge_out)
                                       ┌─────▼─────┐
                                       │   judge   │  classify: exactly one of
                                       └─┬───────┬─┘  the two places gets a token
                                 ▼───────┘       └───────▼
                          (judge_yes: Receipt)   (judge_no: Review)
                            ┌────▼────┐            ┌─────▼─────┐
                            │ settle  │            │ escalate  │
                            └────┬────┘            └─────┬─────┘
                                 └────────▶ ◀────────────┘        merge: both
                                    (settle_out: Done)            exits fused
                                                                  into one place
```

**What this stage contributes:** this is the *arbitrary-net floor* —
anything expressible on the frozen engine is expressible here, whether
or not the sugar above has a word for it. Note there are no hidden
elements: the split, the join, and the merge each cost exactly the
places and transitions you can count.

## Stage 5 — Soundness check and the serialized definition

```text
check_sound: passed (every node lies on an entry→exit path)
serialized NetDefinition: 6985 bytes, deterministic
```

`check_sound` refuses stranded nodes (a place no path reaches, an exit
nothing produces into) *before* lowering. Then the block lowers to a
Petrus `NetDefinition` — the serialization boundary. An excerpt of the
captured JSON (full version in
[`walkthrough-capture.txt`](walkthrough-capture.txt)):

```json
{
  "definition": {
    "arcs": [
      {"color": "Raw", "filter": null, "mode": "consume",
       "position": 0, "source": "parse_in", "target": "parse", "weight": 1},
      ...
    ],
    "places": [
      {"color": "Join2[Reservation, Taxes]", "path": "both_out"},
      {"color": "Receipt", "path": "charge_out"},
      ...
    ],
    "transitions": [
      {"guards": [], "handler": {"kind": "anonymous",
       "uri": "transition:/parse#handler"}, "path": "parse", "timers": []},
      ...
    ]
  },
  "format": "petrus-net-definition",
  "version": 3
}
```

**What this stage validates:** determinism. Recompiling the same
source must produce these exact bytes — that is the replay contract
(the Net is not stored in History; it is re-supplied at resume, AX0).
Stage 8 asserts it.

## Stage 6 — Execution on the frozen engine

Now, and only now, runtime begins. A `Raw` token is seeded on the
entry place and the engine advances until quiescent. The captured
marking after every advance — watch the parallel section (advances
2–5):

```text
seed: Raw{'payload': 'ab'} placed on 'parse_in'

initial marking:
  parse_in: [Raw{"payload": "ab"}]

after advance 1:
  parse_out: [Order{"amount": 2, "sku": "ab"}]

after advance 2:                                  ← the AND-split fired:
  reserve_in: [Order{"amount": 2, "sku": "ab"}]     ONE Order copied into
  taxes_in:   [Order{"amount": 2, "sku": "ab"}]     BOTH branch entries

after advance 3:                                  ← branches are independent:
  reserve_out: [Reservation{"hold_id": "H-ab", "sku": "ab"}]
  taxes_in:    [Order{"amount": 2, "sku": "ab"}]    taxes hasn't run yet;
                                                    reserve's result parks
after advance 4:
  reserve_out: [Reservation{"hold_id": "H-ab", "sku": "ab"}]
  taxes_out:   [Taxes{"tax": 0}]

after advance 5:                                  ← the AND-join fired only
  both_out: [Join2[Reservation, Taxes]{              once BOTH inputs existed
    "first": {"hold_id": "H-ab", "sku": "ab"}, "second": {"tax": 0}}]

after advance 6:
  charge_out: [Receipt{"total": 4}]

after advance 7:                                  ← judge classified: total 4
  judge_yes: [Receipt{"total": 4}]                   is < 100, so "yes"; the
                                                     judge_no place stays empty
after advance 8:
  settle_out: [Done{"ok": true}]

quiesced after 8 advances
```

Two things worth noticing. The parked `reserve_out` at advance 3 is
AX4's durable join in action — a completed branch waits as ordinary
marking, indefinitely if need be. And the token *data* is exactly the
TypedDict dicts from stage 1 — nothing was wrapped or bridged.

## Stage 7 — The persisted History

Every firing appended records. The captured 44-record History (types
only; each also carries paths, tokens, and identities):

```text
 0  InstanceCreated          ← the instance is bound to the net NAME
 1  TokensInitialized        ← the seed marking
 2  CandidateSelected ┐
 3  FiringBegun       │  one firing = this record group
 4  TokensConsumed    │  (parse: consumed Raw, produced Order)
 5  TokensProduced    │
 6  FiringCompleted   ┘
 7–12   the split (note TWO TokensProduced: reserve_in and taxes_in)
13–17   reserve fires
18–22   taxes fires
23–28   the join (note TWO TokensConsumed: reserve_out and taxes_out)
29–33   charge fires
34–38   judge fires
39–43   settle fires
```

**What this stage is:** the durable truth. The marking in stage 6 is
*derived* state; these records are the source of it. Note what is
absent: the net itself. History stores what happened, not the program.

## Stage 8 — Replay

A fresh process recompiles the workflow from source and loads the same
History (captured):

```text
recompiled lowering is byte-identical: True
replayed marking equals live marking on every place: True

final marking after replay:
  settle_out: [Done{"ok": true}]
```

This closes the loop: because stage 5 is deterministic, the recompiled
net is byte-identical, so the 44 records replay onto it and reconstruct
the exact marking — no handler re-runs, no side effects repeat (AX21
asserted this with a fresh would-lie ledger: zero invocations during
replay). If the source had drifted, the load would fail loudly —
`token records on <place>: not a place of this net` (AX2) — never
silently.

---

## Where each stage's rules were established

| Stage | Representation | Established by |
|---|---|---|
| 1 | typed authoring expression | AX26 (façade), AX10 (combinator style), AX3 (`t_fn` inference) |
| 2 | `TBlock[I, O]` typed value | AX26 |
| 3 | `Block` (ports, exits, purity, contexts) | AX22, AX23 |
| 4 | kernel places/transitions/arcs | AX18, AX19; `par` shape AX24; classify/merge AX23 |
| 5 | `check_sound` + deterministic `NetDefinition` | AX22 (soundness), AX2/AX18 (byte determinism) |
| 6 | engine execution, parked joins | AX4 (join semantics, driving policy), frozen Petrus |
| 7 | event-sourced History | AX0 (map), AX8 (durable attempts), AX21 (outcome records) |
| 8 | replay over recompiled net | AX2, AX11, AX17, AX21 |

Not shown in this workflow (deliberately, to keep one deep trace):
CEL guards on arcs (AX6/AX7/AX15/AX16 — stage 4 would show `guard=`
strings and stage 5 non-empty `guards` lists), loops (AX8/AX23 — stage
4 would show a cycle, stage 6 repeated firings with a rising counter),
context reads and `holding` (AX20/AX23 — stage 4 would show
`read(authority)` arcs and a state-token bracket), and the failure
rail (AX25 — one extra `Failure`-colored place with `attempt`
envelopes). Each is a local addition to the same pipeline; the
[experiment map](01-experiment-map.md) links the spike where each is
run and asserted.
