# AX5 — Branching by output type

- State: Completed, 2026-08-11.
- Question: can an activity returning `Approved | Rejected` lower to one
  typed place and arc per variant, with the runtime dispatching on the
  concrete token type — and should type-branching be implicit, explicit,
  or both?
- Prototype: [ax5_workflow_ast.py](ax5_workflow_ast.py) (`switch`/`case`
  nodes), [ax5_compiler.py](ax5_compiler.py) (`VariantPayloadConverter`,
  `VariantRoutingActivityHandler`, XOR-merge lowering), 19 tests in
  [test_ax5_switch.py](test_ax5_switch.py). Petrus untouched.

## What the frozen runtime does natively (tested, not presumed)

`route()` and `complete_firing` deposit a token on **every output arc
that admits it** and **silently drop** tokens no arc admits. Verified
with pure mini-nets:

- a variant-colored token routes to exactly its typed place;
- a token no arc admits **vanishes** — the transition fires, nothing is
  parked, no error is raised;
- a token admitted by a typed arc *and* an untyped arc **duplicates**
  onto both targets;
- input arcs gate enabledness by color too (`pool >> arc(color=...) >>
  transition`), so an input-side XOR also works today.

So yes — the runtime dispatches on concrete token type. But the drop
semantics mean the safety must come from above: **exhaustiveness at
construction, loud refusal at every boundary that could otherwise leak
into a drop.**

## The union does not survive dispatch by itself

With `-> Approved | Rejected`, `DataclassPayloadConverter.encode` falls
to JSON encoding of a dataclass and raises — variant identity is erased
at the Motus worker boundary today. The spike's answer is a
discriminating converter above the runtime:

- `VariantPayloadConverter.encode` requires the result to be *exactly*
  one declared member and stamps `{"$variant": "Approved", ...fields}`
  into the JSON-faithful frozen result — durable in History, so replay
  re-routes identically without importing domain classes;
- a **subclass is refused loudly at the worker boundary**
  (`got PremiumApproved — subclasses and unlisted types have no routing
  arc`), answering the subclass question: nominal colors make subtype
  routing unrepresentable, so the converter fails fast instead;
- `VariantRoutingActivityHandler.project` reads the durable
  discriminator, stamps `Token(variant, fields)`, and targets exactly
  the matching place — a forged unknown variant or a missing
  discriminator raises with the declared variants listed, never
  relying on the silent drop.

## Authoring syntax and lowering

Explicit combinator; the union annotation is the trigger and validator:

```python
sequence(
    switch(
        evaluate,                                  # Application -> Approved | Rejected
        case(Approved, then=step(provision)),      # Approved -> Outcome
        case(Rejected, then=step(notify)),         # Rejected -> Outcome
    ),
    step(archive),                                 # Outcome -> Receipt
)
```

- `switch()` refuses non-union activities (pointing at `step()`), and
  `step()` keeps refusing unions (AX3) — the two spellings partition
  the space.
- Exhaustiveness is unrepresentable to get wrong: missing cases,
  unknown cases, and duplicate cases all fail at construction with the
  full variant list.
- Union members must be dataclasses (converter requirement) and `None`
  is refused as a member — absence must be an explicit variant type.

Generated net: `w.0.evaluate` with one inherited-color arc per variant
(`w.0.on_approved(Approved)`, `w.0.on_rejected(Rejected)`), one branch
subtree per case, and — because both cases exit with `Outcome` — an
explicit XOR merge: `w.0.merge_0`/`w.0.merge_1` passthroughs into one
shared `w.0.out(Outcome)` place. Two producers into one place is plain
Petri; the merge avoids AX3's same-color fan-in ambiguity at the
downstream consumer entirely.

## Implicit, explicit, or both?

Explicit. The branch needs case bodies anyway, so there is no purely
implicit spelling that says *what happens next* — the union return
alone can only create dead variant places. The right division is: the
union **triggers** the requirement to branch (step() refuses it), the
`switch` combinator **states** the branch, and the types **validate**
coverage. An input-side XOR (typed arcs from an untyped place) is a
workable alternative lowering, but it still needs the same converter
stamping, so it buys nothing over projection routing while making the
decision place untyped — rejected for the main design, recorded as a
tested fallback.

## Execution, replay, and failure modes (tested)

- Approved path runs `provision` only; rejected path runs `notify`
  only; both reach `archive` through the merge on the unmodified
  Engine with `InlineDispatch`.
- Replay over deterministic recompilation reaches the same final
  marking — the discriminator lives in the frozen result, so routing
  replays from History.
- Forged unknown variant → projection raises listing declared
  variants (occurrence left projection-pending: fix-and-resume).
- Result without `$variant` → loud, names the converter.
- Handler construction refuses a topology missing a variant arc.

## Explicit / inferred / ambiguous

| Aspect | Status |
| --- | --- |
| Branch cases and their bodies | explicit (`switch`/`case`) |
| Variant set and coverage | inferred from the union, validated exhaustively |
| Variant places, typed arcs, XOR merge | generated, all observable |
| Subclass routing | unrepresentable → refused at the worker boundary |
| Unmatched produced token | runtime would drop silently → every layer above refuses first |

## Verdict

**Promising; continue.** The runtime's typed-arc routing carries the
branch natively; the two real gaps — variant identity across the worker
boundary and drop-vs-fail semantics — both close above the frozen
runtime with a converter and a routing handler. Speculation recorded:
SP-1 gains AX5 evidence (unions are the sharpest nominal-string
casualty), and SP-4 proposes an opt-in strict routing mode. AX6 next:
guard-based branching over one data type with a predicate AST compiled
to CEL.
