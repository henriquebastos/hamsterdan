# Lens 4 — The unified candidate specification

**Status: a candidate for Navigator discussion — not a decision.** No
ADR, roadmap item, or production work follows from this document until
it is reviewed and we decide together. Names are provisional. Every
feature is annotated with the experiment that proved it; anything
*unproven* is marked as such. Code marked **proposal** is idealized
(consistent renaming of proven spike APIs); everything else is quoted
from spikes that run today.

## 1. The layer model

Five layers. The bottom one exists and stays frozen; the four above it
were each proven as spikes on top of it.

```diagram
┌────────────────────────────────────────────────────────────────────┐
│ L4  STATIC FAÇADE (advisory)          proven: AX26                 │
│     TypedDicts as colors; TBlock[I,O]; purity as subtype;          │
│     t_fn signature inference. pyright/ty reject mistakes at        │
│     edit time. Lowers away completely.                             │
├────────────────────────────────────────────────────────────────────┤
│ L3  SUGAR (expands to L2, zero new concepts)                       │
│     failure rail (AX25) · retry shape (AX8/AX23) · domain          │
│     vocabularies like scatter/lane/choice/fold (AX11–AX15)         │
├────────────────────────────────────────────────────────────────────┤
│ L2  BLOCK ALGEBRA (the authoritative composition layer)            │
│     Block = one typed entry, named typed exits, purity,            │
│     declared contexts. Combinators fuse ports. CompositionError    │
│     is the authority.       proven: AX20–AX24                      │
├────────────────────────────────────────────────────────────────────┤
│ L1  KERNEL IR (the arbitrary-net floor)                            │
│     KernelPlace / BoundaryArc / KernelTransition / KernelNet +     │
│     weights, filters, inhibitors, timers, delivery.                │
│     Deterministic lowering; escape hatch for shapes the algebra    │
│     has no words for.       proven: AX18–AX19                      │
├────────────────────────────────────────────────────────────────────┤
│ L0  FROZEN PETRUS RUNTIME (unchanged, 27/27 experiments)           │
│     Engine / Instance / History / Dispatch / Workers; nominal      │
│     string colors; event-sourced replay; byte-identical            │
│     recompilation as the replay contract.  proven: AX0, AX2        │
└────────────────────────────────────────────────────────────────────┘
```

Rules between layers: each layer lowers **only** to the layer below;
lowering is deterministic (same source → byte-identical net, AX2/AX18);
an author may drop one layer down deliberately (algebra → kernel for
exotic topology) but sugar never smuggles in concepts its lower layer
lacks (AX25 proved the discipline is achievable: the rail is pure
arrangement).

## 2. The primitives (L1 — smallest useful set)

Proven shapes, quoted from AX18/AX19:

```python
KernelPlace(name: str, color: str)              # name is identity, color nominal
BoundaryArc(place: str, mode: Mode,             # CONSUME | READ | PRODUCE | INHIBIT
            weight: int = 1,
            filter: str | None = None)          # rendered CEL; refused on PRODUCE
KernelTransition(name, arcs, guard=None,        # guard: rendered CEL
                 work=None,                     # ActivityWork | PetriWork | None
                 label=None, origin=None)
KernelNet(name, nodes)
```

Plus timers (`Delay`/`Until`) and external delivery
(`engine.deliver(transition, data, identity=...)` with deduplicating
identity) — all proven runnable on the frozen engine (AX19).

## 3. The block model (L2 — the unit of composition)

Proven shape, quoted from AX23:

```python
@dataclass(frozen=True)
class Block:
    """A function-like subnet value: one entry, named typed exits, and
    declared context ports for ambient state."""
    name: str
    nodes: tuple[KernelNode, ...]
    entry: Port                        # Port(place, color)
    exits: Mapping[str, Port]          # named, typed
    pure: bool
    contexts: Mapping[str, Port]       # ambient state, declared or refused
```

Doctrines attached to the shape:

- **Work is function-shaped; control combines work.** Control-flow
  combinators take only blocks (the Navigator's "control statements
  may only call functions", AX22).
- **Types are compatibility, never identity.** Ports merge by declared
  *name* (agreeing in color and kind); same color never merges
  anything (AX3, AX14).
- **Purity is metadata with teeth:** `disposable` and `par_fail_fast`
  refuse impure or context-touching blocks (AX20, AX23, AX24).
  Unproven: verifying the declared purity against the handler body —
  it remains declared, not checked.
- **Ambient state is declared or refused:** context `reads=` emit read
  arcs; `holding` brackets a claim; `check_sound` exempts only
  declared context places (AX23).

## 4. The combinators (smallest useful set)

All proven; signatures from AX22/AX23/AX24, sugar from AX25:

| Combinator | Semantics | Proven |
|---|---|---|
| `transform(name, fn, accepts, returns)` | pure 1→1 leaf | AX22 |
| `classify(name, fn, accepts, outcomes, reads=)` | 1→n typed routing leaf | AX22/AX23 |
| `then(a, b, on=)` | port fusion; no glue | AX22 |
| `rename_exit(block, old, new)` | exit renaming | AX22 |
| `merge(block, *exits, into=)` | fuse same-colored exits | AX23 |
| `loop(block, on=)` | fuse exit to entry; cycle from a tree | AX23 (shape AX8) |
| `holding(block, context=, color=)` | claim bracket (structural mutex) | AX23 (shape AX20) |
| `disposable(block)` | purity gate for optimistic work | AX22 (shape AX20) |
| `par(name, branches, returns=)` | AND-join; totality precondition | AX24 |
| `par_fail_fast(name, branches, returns=, failure=)` | purity-gated race; visible drains | AX24 |
| `check_sound(block)` | every node on an entry→exit path | AX22/AX23 |
| **Sugar:** `attempt` / `rail_then` / `recover` | failure rail; scope doctrine | AX25 |
| **Sugar:** bounded retry | `loop` + counter + classify | AX23/AX21/AX8 |

Not recommended (never prototyped, flagged since AX12): `race` beyond
`par_fail_fast`, `optional` execution. Do not spec what no experiment
ran.

## 5. The type and port model

- Colors remain **nominal strings** at L0/L1 (frozen fact, AX0). At
  L4, Python types *are* the authoring colors: `_color(tp)`
  canonicalizes a TypedDict or parameterized generic
  (`Join2[Reservation, Taxes]`) into the color string (AX26).
- TypedDicts preferred for token data: plain dicts at runtime, zero
  bridging through the engine (AX26). Dataclasses served the earlier
  arcs (AX3–AX11) and remain valid; compound results are one named
  type, never tuples or bare generics (AX3).
- Multiple logical inputs = named parameters bound to places
  (AX3's place-bound handler); multiple logical outputs = named typed
  exits (AX22) or a `classify` split.
- **Never inferred:** topology from types (AX0/AX3/AX14); joins across
  same-colored places without named ports; correlation (one engine
  instance per case is the discipline, AX4).
- **Safely inferred:** single-in/single-out ports from signatures —
  `t_fn` proved inference is *safer* than declaration because
  redundancy creates the one static hole both checkers share (AX26).

## 6. The guard model

Explicit expression objects (never lambda inspection, AX6):

```python
app = on(Application)                       # typed proxy
(app.score > 700) & (app.applicant.age >= 18)   # predicate AST, validated at authoring
```

- Compiled to CEL on arcs/transitions; CEL **remains the execution
  backend** — now proven against celpy under production-hard guards
  (AX6/AX7/AX15), including the two dialect facts: presence renders
  `!(x == null)` (AX15) and error absorption is commutative (AX16).
- Routing is ordered-exclusive: each case conjoined with prior
  negations; `otherwise=` mandatory — no-match parking is
  unrepresentable in the authored surface (AX6). Overlap policy:
  refused at the algebra layer; deliberate nondeterminism drops to L1.
- Null safety validated on the sibling-membership criterion
  (`validate_guard` v2, AX16).
- Hybrid cases carry type + predicate on one arc; guards validated
  against the narrowed variant (AX7).

## 7. The role of effect-oriented programming

Inside activities only (AX9, Interpretation A):

- Effects as dataclass values; generator as authoring syntax,
  **re-executed deterministically** on each attempt with journaled
  results replayed in — generator frames are never durable state.
- Journal rides the existing dispatch heartbeat (65,536-byte cap,
  at-least-once per effect — a crash between perform and checkpoint
  repeats that effect).
- An effect deserving History visibility becomes an ordinary workflow
  activity — that is B's benefit without B's 5× record inflation.
- At the *workflow* level, effects appear as typed outcomes:
  `Applied | AlreadyApplied | Stale | Transient`, lookup-first
  classification, only `Transient` loops (AX21).

## 8. The authoring syntax

Nested combinator values as the semantic core and default surface
(AX10); the L4 typed façade as the recommended spelling of those same
values (AX26); an immutable fluent chain permitted as sugar for linear
flows only (AX10). Context-manager and generator builders rejected
(see [lens 2](02-what-did-not-work.md)). The **proposal** spelling,
consolidating the proven pieces under one provisional naming scheme:

```python
# PROPOSAL — proven mechanics, provisional names
# leaves: signature inference (t_fn, AX26) as the default
parse   = pure_step(_parse)                      # TPure[Raw, Order]
reserve = step(_reserve)                         # TBlock[Order, Reservation]
judge   = split(_judge, yes=Receipt, no=Review)  # TChoice — not composable until routed

# composition
workflow = (
    parse
    >> par("both", first=reserve, second=taxes)  # AND-join, totality enforced (AX24)
    >> charge
    >> route(judge, yes=settle, no=escalate, returns=Done)  # explicit convergence (AX26)
)
```

The `>>` operator over typed block values is **unproven** as spelled
(spikes used `t_then(...)`) but is a mechanical `__rshift__` alias;
everything else above ran.

## 9. Validation and error strategy

Three layers, each proven to catch what the others miss (AX26 caught
one bug per layer during a single spike):

1. **Editor (advisory):** pyright as the edit-time authority (8/9);
   ty tracked as its generic solver matures (4/9 today, identical
   inference). Pin both; assert the catch matrix in tests so a version
   bump that changes the story fails loudly (AX26's harness).
2. **Composition (authoritative):** deterministic `CompositionError`s
   with remedies in the message — fusion mismatches, non-totality,
   purity violations, guard field errors, null-safety, exhaustiveness,
   soundness. Never delete a compiler check because a checker
   duplicates it (AX26 doctrine).
3. **Runtime (last resort, loud):** divergent recompilation fails at
   load (`not a place of this net`); unroutable worker outputs are
   refused at the worker boundary, never silently dropped (AX5).

## 10. Serialization, versioning, source mapping

- Serialization boundary: the existing `NetDefinition` v3 (see the
  [walkthrough](04-end-to-end-walkthrough.md), stage 5). Blocks and
  predicates are frozen values and serialize naturally; the AST is
  diffable and fingerprintable (AX1).
- Versioning: the net **name is process identity** (AX17). Superset
  evolution under the same name is zero-migration; narrowing requires
  an authoring-layer whole-trace preflight (unbuilt — see risks).
- Source mapping: deterministic walk paths seed generated paths;
  every generated transition maps to an authoring line (AX2, AX11).
  Policy-only records (WAIT/EXIT lanes) live above the kernel — a
  known, accepted layer boundary (AX18).

## 11. Migration strategy (unchanged in kind since AX12, re-founded on blocks)

Fragment-at-a-time with oracle parity, exactly as the spikes did it:
re-author one production concern as blocks, prove token-for-token
equality against the production net on the same scenarios
(AX11/AX13/AX15 pattern), then compose concerns (AX14) and evolve the
live net by superset (AX17). The separable minimum adoption remains
the predicate AST + CEL guards alone. No step requires a Petrus
change; no step is irreversible.

## 12. Rejected alternatives

Sixteen, each with evidence — the whole of
[lens 2](02-what-did-not-work.md). Headlines: context-manager and
generator builders; effects as net structure; lambda inspection;
implicit union branching; type-only topology; ordering-based null
safety; fail-fast over effectful branches; domain outcomes on the
rail; the "less code" pitch.

## 13. Open technical risks

- **Correlation at joins** is architectural discipline
  (one-engine-per-case), not machinery (AX4). A future multi-case
  engine would reopen this.
- **Loop progress is unprovable** at composition time; bounds are
  data-driven counters (AX8/AX23). Diagnostics: bounded driving
  reports non-quiescence.
- **No durable timers in the frozen baseline's production surface**
  were exercised for retry pacing (AX8); AX19's timer probes are
  engine-level only. Backoff remains worker-side.
- **ty enforcement gap** (generic constraints, 4/9 most-valuable
  checks) until its solver matures — CI currently relies on ty (AX26).
- **Fixed-arity static ceiling:** `t_par2`/`t_par3`, two-way choice;
  Python lacks mapped types. The runtime algebra handles the general
  case (AX26).
- **Purity is declared, not verified** (AX22). A lint limiting
  context-reading steps (fence-once placement) was proposed, not built
  (AX23).
- **Whole-trace evolution preflight** for narrowing nets: shaped by
  AX17, not built.
- **Effect journal limits:** 64 KiB heartbeat cap, one exclusive slot,
  at-least-once per effect (AX9).
- **Aggregate join tokens are dict-shaped inside** unless typed via
  the façade's `Join2`-style record colors (AX24).
- **Sugar-vocabulary sprawl:** AX11's domain words (scatter/fold/…)
  vs the algebra's general words — which surface production authors
  actually get is a product decision this spec deliberately leaves
  open for the Navigator.
