# AX13 — Sibling amortization: the second concern's marginal cost

- State: Completed, 2026-08-12.
- Question: AX11 showed the first authored fragment costs *more* lines
  than production (113 vs 95) because the vocabulary — ports, predicate
  roots, policies — is paid up front. Does the economics flip at the
  margin: what does the *next* sibling concern cost in each style?
- Verdict: **Promising; continue** — the amortization hypothesis holds.
  Growing the real change-intent concern onto the AX11 fragment costs
  **32 authored lines vs 38 production lines**, with zero new handler
  registrations (production adds two), no repeated read/state wiring
  (production repeats the authority read arc twice more plus the
  mutation-state read and state loop), and this time **no extra net
  elements**: the marginal growth is 2 places / 2 transitions / 8 arcs
  on *both* sides. A bonus property fell out proven: fragments are
  values — the grown fragment is reachable by `dataclasses.replace`
  surgery on AX11's committed AST, structurally equal and compiling to
  byte-identical nets.
- Spike: [`ax13_fragment.py`](ax13_fragment.py) (marginal material only —
  everything else imported from AX11),
  [`test_ax13_fragment.py`](test_ax13_fragment.py) — 11 tests,
  [`conftest.py`](conftest.py) (sys.path bridge to the AX11 modules).

## The sibling concern

Production's change-intent concern is the same lane shape AX11 modeled
for replies, on `topology.py`: `_mutation` (~line 944),
`_authorize_change` (~954), the `authorize_change` wiring (~1402–1414),
and the `change_basis` retire (~1657–1659). New state type
(`MutationState`), new work type (`ChangeRequest`), and a guard built
entirely from atoms the predicate AST already has (comparisons, boolean
fields, membership, conjunction).

One production semantics subtlety preserved verbatim and written down:
the change retire guard is the exact **complement** of the authorize
guard (`not _mutation`, which includes "concern busy") — so a valid
change intent against an in-flight mutation is *retired*, where the
reply lane *parks* it. The authored `choice` states both cases; its
mandatory `otherwise=WAIT` is unreachable by construction of the
complement, and the record says so instead of implying it.

## The marginal authoring, complete

```python
MUTATION_STATE = state_port("mutation_state", MutationState)
CHANGE_WORK = port("work_change", ChangeRequest)

MUTATION: Predicate = (
    CURRENT & AUTHORIZED
    & (_intent.blocking == True)
    & _intent.kind.one_of(*CHANGE_KINDS)
    & (_mutation_state.provisional == False)
    & (_mutation_state.change_in_flight == False)
    & (_mutation_state.repair_in_flight == False)
)

def authorize_change(authority, state, value) -> tuple[MutationState, ChangeRequest]:
    ...  # production _authorize_change semantics, as a pure typed function

CHANGE_LANE_BODY = choice(
    case(when=MUTATION, then=update(authorize_change, state=MUTATION_STATE, emits=(CHANGE_WORK,))),
    case(when=~MUTATION, then=retire()),
    otherwise=WAIT,  # unreachable: the two cases are complements — stated, not implied
)
```

Plus two changed lines in the fragment: `MUTATION_STATE` added to
`states=`, and the change lane's `then=EXIT` becoming
`then=CHANGE_LANE_BODY`. `CURRENT`, `AUTHORIZED`, `CHANGE_KINDS`, all
ports, all prior lanes, and the compiler are **imported unchanged** from
AX11.

## Measurements

| Marginal metric | Production | Authored |
| --- | --- | --- |
| Code lines for the concern | 38 (`_mutation` 8, `_authorize_change` 14, wiring 13, retire 3) | 32 (ports 2, predicate 9, function ~16, lane body 5) + 2 changed fragment lines |
| New handler registrations | 2 (`petri_handler(_authorize_change)`, retire guard binding) | 0 |
| Repeated wiring | authority read ×2, mutation-state read, state loop | none |
| Net growth (places/transitions/arcs) | +2 / +2 / +8 | +2 / +2 / +8 |
| Widening arcs beyond production | — | **0** — `~MUTATION`'s own roots already cover the negated predecessor's roots (asserted: `retire_change_basis` inputs are exactly authority read, mutation_state read, change_basis consume) |

Combined with AX11: first fragment 113 vs 95 (authored pays the
vocabulary), second concern 32 vs 38 (authored is cheaper and safer).
The crossover arrives at roughly the second sibling — and `topology.py`
has many siblings (ES-002 counted 14 fragment families).

## Evidence (11 tests)

- **Parity**: five scenarios place-for-place against a production-style
  oracle extended with the verbatim change wiring — idle-concern
  authorization (`change_in_flight` set, `change:` operation, work
  emitted), busy-concern retirement (not parking), non-blocking
  retirement, stale-epoch retirement, and a mixed batch exercising all
  four lanes plus the reply concern in one run.
- **Determinism and replay**: byte-identical recompilation;
  `Engine.load` over a recompiled net reaches the original marking.
- **Shape**: marginal growth asserted exactly (base 11/6/23 → grown
  13/8/31; production 13/8/30 — the one-arc AX11 reply-widening delta
  carries over unchanged, no new widening).
- **Source mapping**: `authorize_change` and `retire_change_basis` map
  to `ax13_fragment.py` origins.
- **Fragments are values**: `dataclasses.replace` surgery on AX11's
  `conversation_intents()` (add state port, swap the lane body) equals
  the restated fragment structurally and compiles to byte-identical
  serialized nets — origins are non-identity metadata (AX1's design
  decision paying off), so grown fragments can be authored *or*
  derived.

## What this changes in the AX12 picture

AX12 §17 flagged the economics risk on AX11's single-fragment evidence.
AX13 sharpens it: the LOC argument is not "the DSL is longer" but "the
DSL front-loads vocabulary the siblings then reuse" — marginal cost is
lower in lines *and* eliminates exactly the two burdens ES-002
identified (binding plumbing, per-concern repetition). The adoption
case for a multi-concern net is stronger than AX12 stated; the
single-fragment case is unchanged (predicate AST + CEL guards remain
the separable minimum).

## Runtime changes required

None. Frozen Petrus, unchanged compiler — AX13 wrote no new lowering
code at all, which is itself a finding: the AX11 node set absorbed a
second real concern without extension.
