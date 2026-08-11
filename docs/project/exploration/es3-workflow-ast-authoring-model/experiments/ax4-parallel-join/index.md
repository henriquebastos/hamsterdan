# AX4 — Parallel split, parallel execution, and join

- State: Completed, 2026-08-11.
- Question: how does an AND-parallel combinator lower onto the frozen
  Net so that starting branches, independent flow, waiting for all
  branches, and combining results are each observable — and where do the
  semantics actually live?
- Prototype: [ax4_workflow_ast.py](ax4_workflow_ast.py) (AST with
  AX3-style inferred leaves), [ax4_compiler.py](ax4_compiler.py)
  (place-set lowering), 12 tests in
  [test_ax4_parallel.py](test_ax4_parallel.py). Petrus untouched.

## Authoring syntax and AST

The leaf now takes the `@activity` definition directly (AX3's
carry-forward — no `request=`/`result=` repetition):

```python
sequence(
    step(receive_order),                  # OrderDraft -> Order
    parallel(
        step(reserve_inventory),          # Order -> Reservation
        step(calculate_taxes),            # Order -> TaxQuote
    ),
    step(charge_customer),                # (Reservation, TaxQuote) -> Receipt
)
```

`step()` reads `definition.parameters`/`definition.result` and stores
only symbolic colors; unions/generics are refused at construction with
AX3's reasons.

## The aggregation decision, made explicit

Among the candidate models (multi-port downstream activity, generated
aggregation dataclass place, separate typed tokens + join transition,
explicit `join` combinator, implicit join), this spike chose:

> Branch results stay **separate typed tokens**; the **join is the
> downstream activity's own transition**, whose Petri enabledness (one
> token on every input place) is the synchronization. The split is an
> explicit generated transition bound to the frozen `passthrough`
> handler.

Nothing is hidden: the split, both branch flows, the parked
intermediate token, and the joining transition are all visible in the
net, the marking, and History.

## Generated net

```diagram
                       ┌──────────────────┐
w.entry(OrderDraft) ──▶│w.0.receive_order │──▶ w.0.out(Order)
                       └──────────────────┘        │
                                            ┌──────▼─────┐
                             ┌──────────────│ w.1.split  │─────────────┐
                             ▼              └────────────┘             ▼
                      w.1_0.in(Order)                           w.1_1.in(Order)
                             │                                         │
                 ┌───────────▼────────────┐              ┌────────────▼───────────┐
                 │w.1_0.reserve_inventory │              │ w.1_1.calculate_taxes  │
                 └───────────┬────────────┘              └────────────┬───────────┘
                             ▼                                        ▼
                   w.1_0.out(Reservation)                    w.1_1.out(TaxQuote)
                             │              ┌────────────┐            │
                             └─────────────▶│   w.2.     │◀───────────┘
                                            │charge_     │
                                            │customer    │──▶ w.2.out(Receipt)
                                            └────────────┘
```

7 places, 5 transitions, 12 arcs; every generated path is deterministic
from the AST address (`/1` → `w.1.split`, branch `i` → scope `w.1_i`),
and the source map covers the split and join both ways.

## Findings

### Concurrency is driving policy, not topology

The first "failure" was no failure: with the default
`choose_conservative` policy only one branch activity was ever in
flight — that policy deliberately begins no second candidate while an
activity result is outstanding. `choose_throughput` dispatches both
branches concurrently because their consumed selections are
structurally independent. The topology *enables* parallelism; the
Engine's driving policy *decides* it. The authoring layer therefore
needs no concurrency syntax at all — a genuinely clean separation the
experiment did not anticipate.

### Synchronization and data semantics (tested)

- Join waits: with only the Reservation completed, the token parks
  durably on `w.1_0.out` and `charge_customer` is not requested;
  completing the TaxQuote enables it.
- Multi-input invocation input is a **per-parameter dict**
  (`{"reservation": {...}, "taxes": {...}}`) — the AX3 named-parameter
  derivation carries through dispatch, so traceability survives the
  join.
- End-to-end through unmodified `Engine`/`InlineDispatch`: split
  duplicates one Order to both branches, receipt combines both results.
- Replay over deterministic recompilation reaches the same final
  marking. No runtime change anywhere.

### One branch fails → stop-on-terminal-failure

`ActivityFailed` + `FiringFailed` commit durably, then the drive halts
with `RuntimeError` and the Engine **poisons itself**; inspection and
continuation go through a fresh `Engine.load` over the same history.
After reload: the join never fired, the completed sibling's Reservation
is still parked at the join. The runtime neither cancels nor
compensates the sibling — that policy void (cancel? compensate? park
forever?) is real and deliberately out of AX4's scope.

### One branch produces no output

A `-> None` branch still owns a `NoneType`-colored exit place (SP-2's
spelling leak), so it works as a **terminal side-effect branch** — the
workflow simply ends with multiple exit places — but it is rejected
with a `LoweringError` when anything downstream must join it: no
parameter can consume `NoneType`. Honest outcome: compile-time
rejection, not silent completion.

### Ambiguity and shape errors (tested messages)

- Branch consuming the wrong color: named node, address, origin line,
  expected vs. actual colors.
- Two branches producing the same color into one consumer: refused with
  "named ports are required (AX3)" — the AX4 spike demands ports but
  does not yet offer port syntax; AX3's place-bound handler is the
  known resolution, and the authoring surface for it is carried
  forward.
- Downstream activity that ignores a branch output: refused, listing
  the unconsumed places.

### The correlation hazard, proven not presumed

Two cases seeded into one Engine instance, completions deliberately
crossed: the join **mispaired** them — rum's reservation was charged
with tea's tax quote (`[("rum", 1), ("tea", 2)]`). Place FIFO pairs
whatever arrives first; neither types nor topology provide case
identity. This is standard colored-Petri behavior, and Hamsterdan's
production discipline (one Engine instance per PR) is what actually
prevents it. Above-runtime mitigation exists if ever needed: the
Engine's `SelectionPolicy` seam could pair bindings by a correlation
key. Recorded in the speculation ledger (SP-3).

## Explicit / inferred / ambiguous

| Aspect | Status |
| --- | --- |
| Split transition, branch flows, join transition | explicit in the net |
| Branch entry colors, join parameter matching | inferred from signatures |
| Concurrency | neither — driving policy at Engine construction |
| Same-color branch results | ambiguous → compile error, ports required |
| Cross-case pairing | ambiguous by design → instance-per-case discipline |
| Sibling fate after one branch fails | open policy question (not AX4's) |

## Verdict

**Promising; continue.** The place-set contract
(`lower(node, entries) -> exits`) generalizes AX2 cleanly; split and
join are observable, honest, and executable on the unmodified runtime;
the driving-policy finding removes a whole concern from the authoring
layer. Carried forward: port-binding authoring syntax (needed the
moment two branches share a result color), the post-failure sibling
policy, and result aggregation into a single dataclass (deferred —
separate typed tokens sufficed here). AX5 next: branching by output
type.
