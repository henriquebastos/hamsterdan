# AX15 — Production's hardest guard as a composed recovery concern

- State: Completed, 2026-08-12.
- Question: `_recoverable_publication` is the densest routing decision
  in the production net — five tokens (Authority, three publication
  states, the Intent), open-map `arguments["target"]`/`["operation"]`,
  a nested *optional* recovery request whose identity must match the
  current authority exactly, three target-specific recovery
  transitions, and a hand-built complement retire. Can the AX14
  composition model author it as a third independent hand-off concern —
  and does the predicate DSL survive its first genuinely hard guard?
- Verdict: **Promising; continue** — the concern composes onto the
  untouched AX11 base and AX14 change concern with **no compiler or AST
  changes at all**; behavior matches a verbatim production oracle
  across all recovery scenarios; per-target predicate specialization
  yields a *smaller* net than production (54 vs 56 arcs). The
  experiment's chief discovery is a **runtime dialect fact**: celpy has
  no `!= null` overload for struct-typed values, so the presence
  rendering had to change — and two real holes in
  `validate_null_safety` are now demonstrated by failing-shaped tests
  and recorded as refinements.
- Spike: [`ax15_recovery.py`](ax15_recovery.py) (~94 code lines:
  ports, per-target predicates, three pure updates, the choice lane,
  composition), [`test_ax15_recovery.py`](test_ax15_recovery.py) —
  22 tests, [`conftest.py`](conftest.py) (sys.path bridge).
  One shared-module fix: `NullCheck.cel` in
  [`ax11_predicates.py`](../ax11-real-fragment/ax11_predicates.py).

## Production baseline

`topology.py` `_recoverable_publication` (~998–1035),
`_recover_publication` (~1038–1055), and the recovery wiring
(~1520–1569): one generic five-parameter Python predicate shared by
three `recover_publication.{target}` transitions plus a
`reject_recovery` retire guarded by the hand-written complement.
Because the shared closure needs all its parameters, **every** recovery
transition reads all three publication states — including the two it
never judges. ~107 lines across predicate, handler, and wiring.

## Authored form

The concern is a fourth `handoff_fragment` on the base scatter's
`recovery_basis` lane; production's if/elif dispatch becomes three
`case`s with **target-specialized predicates**, and the complement
retire is not authored at all — it is the mandatory `otherwise`,
generated as the conjunction of case negations (exactly what production
wrote by hand):

```python
RECOVERY_INTENT = (
    CURRENT & AUTHORIZED
    & (_intent.kind == "recover_publication")
    & _intent.arguments["target"].present()
    & _intent.arguments["operation"].present()
)

def _recoverable(target, state_root, prefix) -> Predicate:
    ...
    return (
        RECOVERY_INTENT
        & (_intent.arguments["target"] == target)
        & (blocked == True) & owned.present()
        & (_intent.arguments["operation"] == owned)
        & recovery.present()                       # MUST precede nested reads
        & (_intent.arguments["operation"] == recovery.operation)
        & (recovery.epoch == _authority.epoch)
        & ...
    )

RECOVERY_LANE_BODY = choice(
    case(when=CONVERSATION_RECOVERABLE, then=update(recover_conversation, ...)),
    case(when=DASHBOARD_RECOVERABLE,   then=update(recover_dashboard, ...)),
    case(when=READINESS_RECOVERABLE,   then=update(recover_readiness, ...)),
    otherwise=retire(),
)

composed = compose("conversation-intents-full",
                   conversation_intents(), change_concern(), recovery_concern())
```

Production's one three-way `_recover_publication` handler becomes three
pure single-state updates — each provably total, because its guard
already proved its own recovery present.

## Results

- **Behavior parity.** The composed net matches the production oracle
  place-for-place across: all three recovery targets; wrong owned
  operation; missing `target` argument (exercises `has()` in the
  generated complement); stale recovery identity (epoch mismatch); and
  a four-intent run where recovery *unblocks a parked reply in the same
  run*, both producers emitting into the shared
  `work_conversation_reply` seam.
- **Shape.** Marginal recovery growth: authored +4 places / +4
  transitions / +23 arcs; production +4/+4/+26. The specialized
  predicates bind only the state each case judges (ordered-exclusivity
  widening included: dashboard reads cp, readiness reads cp+dp). The
  generated `otherwise` retire reads **exactly** production
  `reject_recovery`'s five inputs — the complement's scope is the union
  of the case scopes, mechanically.
- **Replay and determinism.** Composition is byte-deterministic;
  `Engine.load` over a freshly recomposed net replays a recovery run to
  the identical marking.
- **Traceability.** All three recovery transitions map to their
  `ax15_recovery.py` authoring site through the composed source map;
  the three source fragments remain untouched values after composition.

## The dialect discovery: presence must render `!(x == null)`

The recovery guard is the exploration's first *executed* null check
over a struct-typed optional field — and it failed. celpy's frozen
dialect defines `== null` for every value shape but `!= null` only for
scalars: `state.conversation_recovery != null` **raises
`CELEvalError`** when the recovery is present, enabledness reads the
error as not-satisfied, and the binding parks **silently** (the earlier
compile-only probes could not see this). The fix, applied to the shared
AX11 `NullCheck.cel`:

- open map key: `has(path)` (unchanged);
- declared nullable field, presence: `!(path == null)` (was
  `path != null`);
- absence: `path == null` (unchanged).

Four regression tests prove it on Petrus's own `compile_guard` path:
presence of a parked recovery → `true`; absence → `false`, not error;
the rejected `!= null` spelling raises on present structs; map-key
`has()` still distinguishes missing keys. The full exploration suite
(235 tests) stays green — no committed guard ever used non-map
presence, so AX13/AX14 byte-parity evidence is unaffected.

This is evidence about the **predicate backend**, not a Petrus change:
the silent-parking failure mode (guard evaluation error ⇒ token parks
with only a diagnostic) is worth remembering when weighing SP-class
runtime speculation about guard error surfacing.

## Validation holes demonstrated (recorded, not retrofitted)

Two tests document what `validate_null_safety` should catch but does
not today:

1. **Child refs do not inherit parent optionality** — an unguarded
   `state.conversation_recovery.epoch` passes validation yet is
   undecidable when the parent is absent. The recovery guard is sound
   only because `.present()` precedes the nested access and CEL `&&`
   short-circuits; **ordering is the author's obligation**. Refinement:
   a child ref should inherit the parent's optionality until a
   `.present()` conjunct secures the path.
2. **Only the left side of a comparison is checked** — an optional
   field on the right escapes validation.

Both refinements belong to the shared predicate module's next
iteration, not to this spike.

## Explicit / inferred / ambiguous

- Explicit: the hand-off port (`recovery_basis`), every case predicate,
  the per-target state/emit ports, composition order.
- Inferred: guard scope (from predicate roots), the complement retire
  and its widened scope, read-vs-consume arc modes, ordered-exclusivity
  widening.
- Author's obligation (not yet validated): `.present()` before nested
  optional access.
