# AX3 — Typed activities, ports, and basic inference

- State: Completed, 2026-08-11.
- Question: what can the compiler safely infer from Python type hints on
  activity signatures, how are multiple logical inputs/outputs
  represented, and how must the DSL disambiguate two places that share
  one type?
- Prototype: [ax3_inference.py](ax3_inference.py) (`infer_ports` +
  `PlaceBoundActivityHandler`), 14 tests in
  [test_ax3_inference.py](test_ax3_inference.py). Petrus untouched.

## What is safely inferable

`@activity`/`@async_activity` already resolve full type hints into
`definition.parameters` and `definition.result` — the compiler needs no
new signature machinery. From those, `infer_ports` derives:

| Signature shape | Inference | Verdict |
| --- | --- | --- |
| `def f(order: Order) -> Report` | `{order: "Order"}` → `"Report"` | safe |
| `def f(a: Order, b: Report) -> Decision` | one color per parameter | safe (distinct colors) |
| `-> None` | result `None` — a *sink signal*, not a color | safe as a signal |
| async variants | identical (annotations are the source) | safe |
| `-> Approved \| Rejected` | **refused**: unions mean branching → one typed place per variant (AX5) | never infer |
| `-> Decision \| None` | **refused** as a union | never infer |
| `-> list[Decision]` | **refused**: nominal name erases to `list` and would collide globally; remedy: wrap in a named dataclass | never infer |
| `(nothing: None)` input | **refused**: an input must carry a token | never infer |

Every refusal is an `InferenceError` carrying the activity, the
parameter, the reason, and the remedy.

## The mandated ambiguity case — two places, one type

Net: `primary(CreditReport)` and `secondary(CreditReport)` both feed
`assess(primary: CreditReport, secondary: CreditReport) -> Decision`.

- The frozen typed derivation **refuses loudly and correctly**:
  `parameter 'primary' (CreditReport) requires exactly one matching
  input arc, found 2`. The engine already enforces "types are not
  sufficient identity for topology" at this boundary (AX0's finding,
  now demonstrated).
- `PlaceBoundActivityHandler` — ~60 lines of spike code implementing the
  same `prepare`/`project` protocol — binds each **parameter name to one
  source place path** instead. Place identity is always unambiguous.
  The asymmetric test payload (`primary.score * 1000 + secondary.score`
  → `7002` vs `2007` when bindings are swapped) proves role assignment
  is real, not accidental ordering.
- Bad port declarations fail at construction with the input-place list
  in the message; incomplete bindings name the missing parameters.

**Conclusion: named ports are implementable entirely above the frozen
runtime.** An `ActivityHandler` is just user code; the compiler can emit
place-bound handlers whenever colors alone cannot identify inputs.

## Multiple logical outputs

The runtime-native representation is **one result dataclass** (the
result color routes to output arcs). Tuples share the `list` problem
(`tuple.__name__` erases members). Splitting a compound result into
per-field tokens is possible with a generated pure handler but is AX4's
join/aggregation territory — deferred there deliberately.

## Sinks (probed, not speculated)

`DerivedActivityHandler` refuses a no-output activity (`return type
NoneType matches no output arc`) and accepts a place explicitly colored
`"NoneType"` — mechanically workable, semantically ugly. The compiler
can generate a `NoneType`-colored completion place today; a first-class
sink notion is Petrus-lane speculation (ledger SP-2).

## Sources

A no-input activity cannot exist on the frozen runtime: a transition
with no input arcs is a source transition, and the Instance fail-fast
rejects binding an `ActivityHandler` to it (recoverable impure work
belongs downstream of the delivered fact). Workflows therefore start
from a delivered or seeded token, never from a no-input activity — the
AST layer should make this unrepresentable rather than discover it at
bind time.

## Principle validated

> Combinators define topology. Types validate compatibility and support
> local inference.

Local inference (this activity's own arcs) is safe and already engine-
enforced. Global inference ("find any place with this type") is exactly
what the ambiguity case breaks — the DSL must offer named ports, and the
compiler must treat same-color fan-in as an error unless ports are
declared.

## Verdict

**Promising; continue.** Inference needs zero new signature machinery,
refusals are precise and remediable, and the port question has a proven
above-the-runtime answer. Carried forward: AX4 owns compound-result
aggregation; AX5 owns union lowering; the AST leaf should accept an
`ActivityDefinition` directly and drop AX2's explicit `request=`/`result=`
for the single-input/single-output case.
