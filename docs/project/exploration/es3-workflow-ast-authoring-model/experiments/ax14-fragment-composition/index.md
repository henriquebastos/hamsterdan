# AX14 — Fragment composition by explicit named-port identity

- State: Completed, 2026-08-12.
- Question: AX13 grew a sibling concern by *restating the whole
  fragment* (equivalently: `dataclasses.replace` surgery on the base
  AST). Can two concerns instead be authored as **independent fragment
  values** and composed into one deterministic net by explicit
  named-port identity — without mutating either source AST, and without
  Python type identity ever merging places?
- Verdict: **Promising; continue** — composition works and its oracle
  is exact: composing AX11's untouched base with the change concern as
  a separate hand-off fragment serializes **byte-for-byte identical**
  to AX13's restated monolith. The only AST growth composition demanded
  was `handoff_fragment` — a fragment whose entry tokens are adjudicated
  by a guarded `choice` instead of transformed by an activity — and the
  only compiler growth was sharing one `NetSpec`/place/transition
  namespace across lowerings plus a loud shared-name compatibility
  check. No new lowering semantics: the hand-off choice reuses AX11's
  lane-choice machinery verbatim.
- Spike: [`ax14_compose.py`](ax14_compose.py) (`compose`,
  `handoff_fragment`, ~90 lines of new logic),
  [`ax14_fragments.py`](ax14_fragments.py) (the scenario: AX11 base +
  change concern, both imported unchanged),
  [`test_ax14_compose.py`](test_ax14_compose.py) — 18 tests,
  [`conftest.py`](conftest.py) (sys.path bridge to AX11/AX13 modules).

## The composition surface

A fragment's composable surface is exactly its **named ports** — nothing
else. Two fragments compose where they deliberately spell the same port
name; everything else stays disjoint:

```python
# AX11's base, exactly as committed — change_basis lane still says then=EXIT
base = conversation_intents()

# the change concern as an independent value: entry IS the shared name
concern = handoff_fragment(
    "change-intents",
    entry=CHANGE_BASIS,          # port("change_basis", Intent) — the hand-off
    reads=(AUTHORITY,),          # read_port("authority", Authority) — shared context
    states=(MUTATION_STATE,),    # the concern's own state
    body=CHANGE_LANE_BODY,       # AX13's proven choice, unchanged
)

composed = compose("conversation-intents-change", base, concern)
```

Identity rules, exact and tested:

- **Merged**: same port name across fragments — and only after the
  declarations agree exactly in color *and* kind (`Port`/`ReadPort`/
  `StatePort`). `change_basis` and `authority` merge here; disagreement
  in color (`Port[ChangeRequest]` vs `Port[Intent]`) or kind
  (`StatePort[Authority]` vs `ReadPort[Authority]` — which would change
  arc semantics) raises `CompositionError` naming both fragments. The
  naive alternative — shared `place_specs` reuse — would silently keep
  the first declaration; the spike proves that hole must be closed.
- **Never merged**: same color, different names. The four
  Intent-colored ports (`intent_result`, `reply_basis`, `change_basis`,
  `recovery_basis`) remain four distinct places — AX3's ruling holds
  through composition.
- **One namespace**: transition names. A second concern generating
  `authorize_change` again fails through AX11's existing duplicate
  check; fragment names must be unique because they prefix the source
  map.
- **Nothing implicit**: a concern that forgets its `authority` read
  port fails at compose time with AX11's existing resolution error
  ("reads Authority, but the fragment declares no port of that type") —
  composition never reaches into a sibling fragment to satisfy a guard.

## What composition demanded (and what it did not)

- `handoff_fragment`: the consumer of another fragment's `EXIT` lane
  starts with a *decision*, not a transformation — the producer already
  routed the token. `Fragment.body` previously admitted only
  `ActivityStep | Scatter`; the hand-off shape needs a bare `Choice` as
  body. Its lowering is AX11's `_lower_lane` choice path applied to the
  entry port (`where=` routing stays with the producer's scatter).
- `compose(name, *fragments)`: lowers fragments **in argument order**
  into one shared `NetSpec`. Order is part of the composition's
  definition: reversing it yields identical places, transitions, guards,
  and arcs (proved as sets) but permutes serialized arc *positions*, so
  byte-determinism requires the authored order — explicit, not inferred.
- Source-map addresses gain a `/{fragment-name}` prefix. Cross-file
  traceability survives the seam: in the composed net,
  `authorize_change` maps to `/change-intents/...` with an
  `ax13_fragment.py` origin while `authorize_reply` maps to
  `/conversation-intents/...` with an `ax11_fragment.py` origin.
- **Not needed**: any change to predicates, folds, updates, scatter,
  activity lowering, guards, or the frozen runtime. No new speculation
  ledger entry — composition is entirely an authoring-layer concern.

## Evidence (18 tests)

- **Exact identity**: composed net byte-identical to the AX13 monolith
  (`serialize_net_definition` equality) — the strongest oracle
  available, since AX13 already proved that monolith against production
  wiring place-for-place. Composition is *the same net*, not a similar
  one.
- **Behavior parity**: three scenarios re-run against the AX13
  production oracle through the composed net — idle-concern
  authorization, busy-concern retirement, and a mixed batch whose
  findings/reply intents cross the base lanes while the change intent
  crosses the composition seam in one run.
- **Determinism and replay**: recomposition is byte-deterministic;
  `Engine.load` over a recomposed net reaches the original marking.
- **Sources are values**: after composing, both source fragments still
  equal freshly constructed ones; the base alone still compiles with
  its exit lane open (no `mutation_state`, no `authorize_change`).
- **Failure quality**: color conflict, kind conflict, duplicate
  transition, duplicate fragment name, missing context port, and
  non-choice hand-off body all fail with messages naming the port, the
  fragments (or the rule), and the remedy direction.

## What this changes in the AX12 picture

AX12's migration story was fragment-at-a-time with each fragment a
monolith; AX13 showed sibling growth is cheap but still required
restating (or surgically transforming) the base. AX14 removes that
constraint: concerns can live as independent values — in separate
files, owned separately, tested separately (AX13's lane body was reused
here *unchanged*) — and meet only at explicitly shared port names. That
is the shape `topology.py`'s 14 fragment families actually want: one
producer fragment scattering to hand-off places, sibling concern
fragments consuming them, `compose()` as the single assembly point.
Open follow-up, deliberately not tested here: whether a concern's
*provided/required* surface should be declared (and checked) rather
than discovered structurally at compose time — today an unconsumed
`EXIT` lane composes silently, which is also production's behavior for
`recovery_basis` in this slice.

## Runtime changes required

None. Frozen Petrus, byte-identical output to the already-proven
monolith — composition happened entirely above the compiler's existing
lowering vocabulary.
