# Lens 3 — What worked, and why

The patterns that survived contact with the frozen engine, each with
the code that proves it and the experiment that owns the evidence.
These are the load-bearing results the
[unified candidate spec](05-unified-candidate-spec.md) is built from.

---

## 1. The frozen runtime is already sufficient (AX0–AX26, all of them)

Twenty-seven experiments — sequences, typed ports, parallel joins,
type routing, CEL guards, hybrid arcs, cycles, effect journals,
composition, evolution, kernel features, claim/fence, typed outcomes,
blocks, merge/loop/holding, parallel policies, the failure rail, a
typed façade — and **zero Petrus changes were needed**. Everything
lives above the runtime: handlers, converters, compilers, validators.
This is the single most consequential result: the authoring model is
adoptable without touching the engine, and every speculation about
engine changes stayed speculation
([ledger](../petrus-speculation.md)).

The contract that makes it safe (AX0, proven in AX2 and every arc
since): the Net is absent from History, so the compiler must be
deterministic — same source, byte-identical net:

```python
# test_ax18_kernel.py — the determinism proof pattern, used everywhere
direct = compile_fragment(conversation_intents_with_change())
via_kernel = compile_via_kernel(conversation_intents_with_change())
assert definition_bytes(via_kernel.built.net) == definition_bytes(direct.built.net)
```

## 2. Blocks: function-shaped subnets as frozen values (AX22)

The unit of composition that everything converged on — one typed
entry, named typed exits, purity metadata, kernel nodes inside:

```python
@dataclass(frozen=True)
class Block:
    """A function-like subnet value: one entry, named typed exits."""
    name: str
    nodes: tuple[KernelNode, ...]
    entry: Port
    exits: Mapping[str, Port]        # e.g. {"applied": Port(...), "stale": Port(...)}
    pure: bool
    contexts: Mapping[str, Port] = field(default_factory=dict)   # AX23
```

Why it works: it realizes the Navigator's constraint — *control
statements may only call functions*. Work has function shape (enter,
run, exit with a named result); control flow is combinators over those
values. Compare the two layers on the same job:

```python
# Kernel layer (AX18) — you say every place, arc, and transition:
KernelTransition("judge", arcs=(consume("charge_out"),
                                produce("judge_yes"), produce("judge_no")))

# Block layer (AX22/23) — you say what the work is; topology is derived:
judge = classify("judge", _judge, accepts="Receipt",
                 outcomes={"yes": "Receipt", "no": "Review"}, pure=True)
```

## 3. Composition by port fusion — no glue, ever (AX2, AX22)

`then(a, b, on="out")` renames b's entry place to a's exit place.
No adapter transition, no extra event, no hidden state:

```python
flow = then(disposable(validate()), apply_at(world), on="out")
flow = rename_exit(then(flow, finish(), on="applied"), "out", "done")
flow = rename_exit(then(flow, record(), on="stale"), "out", "rejected")
return check_sound(flow)
```

Why it works: handlers address output arcs by *color*, not absolute
place name, so fusion never invalidates a leaf (AX22). The same idea
scaled up: AX14's `compose(name, *fragments)` merges whole concerns by
explicitly shared port names — byte-identical to the hand-restated
monolith — and AX17 showed a superset composition loads over a live
history with **zero migration**, parked tokens becoming deferred
capability.

## 4. The generic kernel IR under the sugar (AX18/AX19)

Four data shapes express any net the frozen engine can run — including
shapes the sugar has no words for (cycles, handler-less competition,
disconnected places):

```python
KernelPlace(name, color)                     # name is identity; color is nominal
BoundaryArc(place, mode, weight=1, filter=None)   # consume/read/produce/inhibit
KernelTransition(name, arcs, guard=None, work=None, label=None)
KernelNet(name, nodes)
```

Why it works: it is the floor that keeps the sugar honest — every
combinator *desugars* to this, byte-for-byte identical to direct
compilation (AX18), and boundary features (weights, input filters,
inhibitors, timers, external delivery with deduplicating identity) are
additive fields, proven runnable one by one (AX19). Declaration-time
refusals encode engine truths permanently — e.g. a produce-side filter
is refused because frozen output arcs admit by color only.

## 5. Claim/fence: linearity restored, optimism made safe (AX20)

The answer to "the net has no visible sequences — state places couple
everything." Enter by consuming the concern's single state token
(structural mutex — the token's *location* is the lock); run a pure,
disposable interior; judge validity exactly once at the exit:

```python
# ax20_subnet.py — the two exits are the only authority readers
BoundaryTransition("commit",
    arcs=(read("authority"), consume("draft"), consume("claimed"),
          produce("work"), produce("state")),
    guard=FENCE)
BoundaryTransition("discard",
    arcs=(read("authority"), consume("draft"), consume("claimed"),
          produce("rejected"), produce("state")),
    guard=f"!({FENCE})")
```

Why it works: complementary guards guarantee exactly one terminal
route; no `in_flight` boolean can drift; do-then-validate (compute
optimistically, discard if the world moved) replaces
check-before-start — safe *because* the interior is pure, which is why
`disposable` refuses effectful blocks. AX23's `holding` packaged the
same bracket as a combinator.

## 6. Typed effect outcomes and lookup-first idempotency (AX21)

Both kinds of idempotency became net structure. Outcomes are colors
routed to ordinary places — "already done" is data, not an exception:

```python
def apply(self, op: str, base: str, payload: str) -> str:
    if op in self.applied:   # lookup-first: BEFORE any precondition
        return "already"     # -> AlreadyApplied (done is done, even if base moved)
    if base != self.base:
        return "stale"       # -> Stale (preconditions changed; do not retry)
    if self.faults > 0:
        self.faults -= 1
        return "transient"   # -> Transient (the only outcome allowed to loop)
    self.applied[op] = payload
    return "applied"
```

Why it works: the classification order is the doctrine — an operation
found done is `AlreadyApplied` even if the base has since moved;
checking preconditions first would misclassify it as `Stale`. Only
`Transient` retries, bounded by an attempt count carried durably in
the token (AX8's shape). Replay reaches the same marking without
consulting the outside world (asserted with a would-lie fresh ledger).

## 7. Merge, loop, holding: cycles from a tree (AX8, AX23)

All three completions are *place fusions*, so the authoring expression
stays a tree of values while the net gains cycles and convergence:

```python
# bounded retry: loop an exit back to the entry — AX21's discipline, AX8's shape
return loop(then(bump, judge, on="out"), on="again")

# convergence: two same-colored exits become one
flow = merge(flow, "first_time", "repeat", into="done")
```

Why it works: `loop` refuses looping the only exit ("would leave no
way out") and color mismatches; `merge` refuses differing colors and
double-production; `check_sound` still verifies every node lies on an
entry→exit path, exempting only *declared* context places. Loop
boundedness stays data-driven (the counter in the token) — the honest
limit AX8 already recorded.

## 8. Parallel with the join policy in the net (AX24)

Two policies, both structurally visible, neither implicit:

- `par` — AND-split copies the input to every branch; every branch
  runs (effects welcome — nothing is abandoned); AND-join consumes one
  token per branch into a `{branch: data}` aggregate. Sound because
  **totality is a precondition**: every branch must have exactly one
  exit, so the join never waits on a token that cannot come. Branches
  with variants totalize first; a downstream `classify` splits the
  aggregate — which is exactly error accumulation.
- `par_fail_fast` — one `armed` once-only token (AX20's claim shape)
  consumed by the all-ok join or exactly one abort; losers drain into
  a visible `abandoned` exit. Cost is linear (2+3n transitions).
  Admissible **only** over pure, context-free branches.

Why it works: the Composable Functions totality insight transferred to
durable nets, and their deleted-`first` lesson became a purity
admission rule instead of a footnote.

## 9. The failure rail as visible sugar (AX25)

`attempt` / `rail_then` / `recover` — railway-oriented failure in ~60
lines of arrangement over existing combinators, zero new concepts:

```python
# attempt: exception -> durable JSON envelope on the `failed` exit
#   (kind, message, source block, retryable, cause chain — exact
#    json.loads(json.dumps(e)) == e round-trip asserted)
# rail_then: compose on ok; MERGE the two rails -> one Failure place per chain
# recover: total handler consumes the envelope, rejoins the success track
```

Why it works: the rail is an ordinary *place* — on-path, inspectable,
`check_sound`-visible; a mid-chain failure leaves its envelope there
with `source: "enrich"` and the downstream world untouched. And the
scope doctrine keeps it honest: **the rail carries what nobody
modeled; classify carries what somebody did** — typed domain outcomes
are refused fusion by color.

## 10. Typed predicates compiled to CEL, validated by absorption (AX6, AX7, AX15, AX16)

The guard pipeline: typed proxy → predicate AST → rendered CEL string
on the arc/transition — with authoring-time field validation, ordered-
exclusive lowering (each case conjoined with prior negations), and
mandatory `otherwise=`. It survived the hardest production guard
(AX15) and *shrank* the net doing it (56 → 54 arcs). Null safety is
enforced by the validator on the true criterion — sibling membership,
not order — because celpy absorbs errors commutatively
(`error && false == false` both ways). Presence renders as
`!(x == null)` because `x != null` raises in celpy.

```python
(
    RECOVERY_INTENT
    & (_intent.arguments["target"] == target)
    & owned.present()
    & (_intent.arguments["operation"] == owned)
    & recovery.present()
    & (recovery.epoch == _authority.epoch)
    & (recovery.head == _authority.head)
)   # the AX15 recovery guard — five tokens, nested optionals, identity match
```

## 11. The typed façade: types as colors, checked in the editor (AX26)

TypedDicts as domain types double as colors — plain dicts at runtime,
so tokens flow through the frozen engine with zero bridging.
`TBlock[I, O]` is total by construction; `TChoice` cannot enter
`t_then` until routed; purity is a subtype (`TPure <: TBlock`);
`t_fn` infers ports from the signature (single source of truth):

```python
prepared: TBlock[Raw, Reservation] = t_then(parse, reserve)   # middle types checked
both: TBlock[Order, Join2[Reservation, Taxes]] = t_par2("both", first=reserve, second=taxes)
routed: TBlock[Receipt, Done] = t_route(judge, when_yes=settle, when_no=escalate, returns=Done)
```

Why it works: pyright 1.1.411 rejects 8/9 deliberate composition
mistakes at edit time with zero false positives and zero annotation
burden; both checkers reveal identical precise types on hover. And the
layering held under fire — during the spike, ty caught a bug pyright
accepted, pyright caught eight ty missed, and AX23's own runtime rules
caught one both checkers were happy with. Three layers, three
different catches: **checkers advise; the deterministic
CompositionError layer remains the authority.**

## 12. Determinism, source mapping, replay — the spine (AX1, AX2, AX11, AX17)

Every layer preserves three invariants:

- **Determinism:** frozen values, origin as non-identity metadata,
  canonical fingerprints, first-touch place order, authoring-walk
  transition order, per-transition read→consume→produce arc order.
  Same source → byte-identical net, always asserted.
- **Source mapping:** deterministic AST walk paths seed generated net
  paths; AX11 mapped every generated transition back to an authoring
  line. A runtime marking is explainable in authoring terms.
- **Replay:** recompile from source, `Engine.load` over the recorded
  history, identical marking — proven per-experiment and again in the
  [walkthrough](04-end-to-end-walkthrough.md); divergence fails loudly
  (`not a place of this net`), never silently.
