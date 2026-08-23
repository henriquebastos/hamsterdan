# AX11 — the leading design applied to a real production fragment

- State: Completed, 2026-08-12.
- Question: does the AX1–AX10 leading design survive contact with a real
  fragment of `topology.py` — multiple data types, concurrency, guarded
  branches, data transformations, and explicit wiring — while running
  place-for-place identically on frozen Petrus, and what does it actually
  buy over the production DSL when measured, not admired?
- Verdict: **Promising; continue** — behavior parity is proven token-for-
  token against a production-style oracle on the frozen engine, replay
  over a recompiled net works, every generated transition maps back to an
  authoring line, and the DSL surfaces semantics production leaves
  implicit. The win is *not* line count (113 vs 95 — the authored version
  is slightly longer); it is explicitness, static checking, and zero
  separately registered callbacks.
- Spike: [`ax11_predicates.py`](ax11_predicates.py) (binding-guard
  predicate AST → CEL), [`ax11_ast.py`](ax11_ast.py) (fragment/scatter/
  choice/fold/update/retire nodes), [`ax11_compiler.py`](ax11_compiler.py)
  (lowering onto frozen `NetSpec`), [`ax11_fragment.py`](ax11_fragment.py)
  (the authored fragment), [`test_ax11_fragment.py`](test_ax11_fragment.py)
  — 22 tests including a production-style oracle.

## Fragment selection — and an honest scope note

The AX0 baseline (actions failure/rerun/repair) contains **no genuine
AND-parallel section**, so labeling it "parallel" would have faked the
AX11 requirement. AX11 instead uses the real **conversation-intent**
fragment of the former `src/hamsterdan/readiness/net/topology.py`, retained in
pre-consolidation Git history:

- the classification activity bridge (~line 1229);
- `_unpack_intents` (handler lines 189–203, wiring 1489–1491);
- the `accept_finding_intent`/`accept_reminder_intent` loop
  (wiring 1492–1506, handler `_accept_intent` 862–868);
- `_replyable`/`_authorize_reply` (971–996, wiring 1507–1517);
- the `reply_basis` retirement (1651–1656).

Its concurrency is **scatter concurrency**: one `IntentBatch` unpacks
into many independently progressing intent tokens across concern lanes
(review folds, human-state folds, reply authorization, change/recovery
hand-offs). That is real parallel token flow on one marking — but it is
*not* an AX4-style AND-split that duplicates one token, and there is no
AND-join. The fragment is reported as what it is; AX4 already proved the
AND-parallel lowering separately.

The fragment satisfies every other AX11 requirement: seven data types
(`ConversationClassificationRequest`, `IntentBatch`, `Intent`,
`Authority`, `ReviewState`, `HumanState`, `ConversationPublicationState`,
`ConversationPublicationRequest`), typed guards, data transformations
(`fold_intent`, `_authorize_reply`'s state+work production), and eleven
explicitly wired places.

## What is authored — production vs the leading design

Domain truth is **imported, not re-authored**: the authored fragment uses
the same `hamsterdan.contracts.readiness` models, the same
`fold_intent` fold, and the same `operation`/`effect_payload` identity
derivation as production. Only the expression of topology, routing, and
guards changes.

Production (excerpt — closures over binding tuples, wiring by `>>`):

```python
tr = getattr(t, f"accept_{name}")(
    handler=petri_handler(lambda b, o, typ=owner_type: _accept_intent(b, o, typ)),
    guards=_guard(
        lambda a, state, value, selected=kinds: (
            _current(a, value) and value.authorized and value.kind in selected
        )
    ),
)
p.authority >> arc.read() >> tr
(owner, p.intent_result) >> tr >> owner
```

Authored (the same semantics as declared structure):

```python
scatter(
    unpack_intents,
    lane(
        INTENT_RESULT,
        where=_intent.kind.one_of(*FINDING_KINDS, *REMINDER_KINDS),
        then=choice(
            case(
                when=CURRENT & AUTHORIZED & _intent.kind.one_of(*FINDING_KINDS),
                then=fold(accept_finding_intent, state=REVIEW_STATE),
            ),
            case(
                when=CURRENT & AUTHORIZED & _intent.kind.one_of(*REMINDER_KINDS),
                then=fold(accept_reminder_intent, state=HUMAN_STATE),
            ),
            otherwise=WAIT,   # stale/unauthorized intents park — production implies this
        ),
    ),
    lane(
        REPLY_BASIS,
        where=_intent.kind == "reply",
        then=choice(
            case(when=REPLYABLE, then=update(authorize_reply, state=PUBLICATION_STATE,
                                             emits=(REPLY_WORK,))),
            case(when=~VALID_REPLY, then=retire()),
            otherwise=WAIT,   # valid but the concern is busy
        ),
    ),
    lane(CHANGE_BASIS, where=_intent.kind.one_of(*CHANGE_KINDS), then=EXIT),
    lane(RECOVERY_BASIS, where=_intent.kind == "recover_publication", then=EXIT),
    rest=DROP,               # production drops kind "status" silently; here it is written
)
```

Guards are typed predicate expressions over declared ports
(`on(Authority)`, `on(Intent)`, `on(ConversationPublicationState)`),
composed with `&`/`|`/`~`, compiled to binding-scoped CEL transition
guards such as:

```text
(reply_basis[0].data.epoch == authority[0].data.epoch) &&
has(reply_basis[0].data.arguments.message) &&
(conversation_publication_state[0].data.conversation_requested == false)
```

Folds and updates are **pure typed functions**
(`(Authority, ReviewState, Intent) -> ReviewState`); the binding plumbing
production writes by hand (`_values`, `_route`, `_put`, hydration) is
synthesized by the compiler.

## Generated net and source mapping

Compiled net: **11 places, 6 transitions, 23 arcs**. Production oracle:
11 places, 6 transitions, **22 arcs**. Transition and place names match
one-for-one (`classify_conversation`, `unpack_intents`,
`accept_finding_intent`, `accept_reminder_intent`, `authorize_reply`,
`retire_reply_basis`).

The one-arc delta is honest and visible: ordered exclusivity compiles
`case(when=~VALID_REPLY, then=retire())` as
`!(REPLYABLE) && ~VALID_REPLY`-equivalent scope, so the retire transition
gains a **read arc on `conversation_publication_state`** that production
avoids by hand-simplifying to `not _valid_reply`. The compiler does not
prove predicate implications (`~VALID_REPLY ⟹ ~REPLYABLE`); it widens
scope mechanically and records it in the source map:

```text
/body/1/lanes/reply_basis/cases/1 -> retire_reply_basis
   retire on lane 'reply_basis' (scope widened by read arcs on
   ['ConversationPublicationState'])
```

Every transition maps to an AST address and an `ax11_fragment.py` file:line
origin (captured at construction), and both `WAIT` park decisions are
recorded as source-map entries even though they generate **no** transition
— the absence is documented rather than implied.

## Measurements

| Metric | Production | Authored |
| --- | --- | --- |
| Authoring code lines (non-comment, same scope) | ~95 | ~113 |
| Explicit places in authoring code | 11 (typed at first mention) | 11 named ports |
| Explicit transitions in authoring code | 6 | 0 (all generated) |
| Explicit arcs in authoring code | 22 via `>>` chains | 0 (23 generated) |
| Separately registered callbacks | 6 handler bindings (5 `petri_handler` closures + 1 string handler bridged to a `DerivedActivityHandler` elsewhere) | 0 — functions referenced inline; handlers derived by the compiler |
| Repeated wiring | `p.authority >> arc.read() >> tr` ×3; `owner >> tr >> owner` state loops ×3 | none — derived from `fold`/`update`/`reads` declarations |
| Routing table checked for overlap | no (hand-written dict, nobody checks) | yes — overlapping lanes refused at construction |
| Unmatched-token policy | implicit (silent drop / silent park) | mandatory `rest=` and `otherwise=` (construction error if omitted) |
| Guard checkability | opaque lambdas, tested only by running | typed predicate AST; unknown fields, impossible literals, and absent-key access fail at authoring time |

LOC parity deserves emphasis: for a fragment this dense the authored form
is **not shorter**. The reduction hypothesis from ES-002 holds only for
the plumbing (callbacks, repeated read/state wiring); the semantic content
— four predicates, four routing lanes, five cases, three state folds —
is irreducible and now occupies *more* surface because previously implicit
policy (`WAIT`, `DROP`) must be written.

## Behavior, replay, and errors

- **Parity**: five scenario tests drive identical seeds through frozen
  `Engine` and compare all eleven places token-for-token against the
  production-style oracle: mixed seven-intent batch, busy-concern
  parking, empty-message retirement, missing-key retirement (the CEL
  `has()` presence guard), stale-epoch retirement.
- **Determinism**: two `compile_fragment` runs serialize to identical
  `NetDefinitionV3` bytes.
- **Replay**: `Engine.load` over a *recompiled* net replays 26 history
  records to the original marking, with exactly one `ActivityRequested`
  (no re-dispatch). One test-helper bug was found during this experiment
  — `history or InMemoryHistoryStore()` silently replaced an empty
  caller-supplied store because `HistoryStore.__len__ == 0` is falsey —
  a spike bug, not a runtime issue, but a warning for any future API
  that accepts optional store arguments.
- **Error quality** (10 tests): unknown predicate fields list
  alternatives; impossible enum literals name the declared values;
  map-key comparison without a presence guard is refused with the fix
  spelled out; overlapping lanes name the contested kind; missing
  `rest`/`otherwise` policies are construction errors; `update` return
  shape is checked against `state=` + `emits=`; two same-type state
  ports fail lowering with "types never identify places"; a predicate
  over an undeclared port type names the missing declaration;
  non-identifier port names are refused (CEL binding guards need
  identifier-shaped place variables).

## Explicit, inferred, ambiguous

- Explicit: every port name, every lane predicate, every case, both gap
  policies, state ownership of each fold, work emission of `update`.
- Inferred: handler derivation, hydration types (from function
  signatures), arc structure (consume/read/state loops), guard scope
  (which places a predicate binds), scope widening for ordered
  exclusivity.
- Ambiguity handled, not hidden: same-color state ports are a lowering
  error; predicates resolve to ports by declared type only when exactly
  one port of that type exists.

## Does the DSL hide Petri semantics?

Checked deliberately. `WAIT` is precisely "no transition admits this
token" — the DSL writes the park down instead of leaving it as an
absence. The scatter's routing handler is a synthesized pure function,
same as production's `_unpack_intents`. The ordered-exclusivity read-arc
widening is surfaced in the source map. Nothing observed in the
generated net is unreachable from the authored source; nothing in the
authored source pretends the net does something it does not.

## Runtime changes required

None. Petrus remains frozen at the pinned baseline; the compiler lowers
onto the existing `NetSpec`/`BuiltNet`/CEL/`DerivedActivityHandler`
surface, and all 22 tests run on the unmodified engine. No new entry was
added to the [Petrus speculation ledger](../../petrus-speculation.md):
the scope-widening arc is compiler behavior, not runtime evidence.
