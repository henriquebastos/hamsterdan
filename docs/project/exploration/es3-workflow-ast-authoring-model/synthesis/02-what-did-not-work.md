# Lens 2 — What did not work, and why

Every entry: the attempt, the code we actually wrote or considered,
the evidence that killed it, and what replaced it. These are paid-for
negative results — the fastest way to not re-litigate them later.

Ordered roughly from authoring surface down to runtime semantics.

---

## 1. The context-manager builder (AX10)

**Attempt:** derive workflow structure from `with` blocks — familiar,
imperative-looking.

```python
# REJECTED (test_ax10_styles.py) — structure from statement order
def context_manager():
    flow = WorkflowBuilder()
    flow.do("receive_order")
    with flow.parallel():
        with flow.branch():
            flow.do("reserve_inventory")
            flow.do("confirm_reservation")
        with flow.branch():
            flow.do("calculate_taxes")
    with flow.retry(limit=3):
        flow.do("charge_customer")
    return flow.build()
```

**Why it died:** structure lives in a mutable scope stack and
statement *order*, not in values. `flow.do(...)` returns `None`, so
the type checker sees nothing and assigned "results" would fake
dataflow. Misuse (`branch()` outside `parallel()`, reuse after
`build()`) is detectable only at runtime. Nothing is serializable or
diffable until execution finishes.

**Instead:** nested combinators — the expression *is* the AST
(AX10, AX22).

## 2. The generator/imperative workflow builder (AX10)

**Attempt:** `@workflow def process(): order = yield activity(...)` —
the most natural-looking spelling.

```python
# REJECTED (test_ax10_styles.py ~L151) — handles are symbolic
def test_branching_on_a_step_result_is_refused(self) -> None:
    def branching():
        approved = yield "evaluate"
        if approved:
            yield "ship"

    with pytest.raises(TypeError, match="symbolic at authoring time"):
        build_workflow(branching)
```

**Why it died:** the yielded handle is symbolic at authoring time — it
cannot answer `if`. A Python `for` loop merely *unrolls* into repeated
AST nodes at authoring time; it cannot create a durable cycle (AX8's
`retry`/AX23's `loop` remain necessary). What remains — linear yields —
is combinators with extra ceremony.

**Instead:** combinator values; generators appear only *inside* an
activity as effect syntax (AX9-A), never as workflow structure.

## 3. Effects compiled into net structure — Interpretation B (AX9) {#effects-as-net-structure}

**Attempt:** trace an effect generator symbolically and lower each
`yield` into its own transition — the Petri engine owns suspension.

**Why it died, measured:** the three-effect `settle_payment` program
became **5 transitions, 6 places, 5 `ActivityRequested` records**
versus 1 transition and 1 record pair under Interpretation A — 5×
history inflation for the same behavior. It is straight-line only:
`if reservation.approved:` raises `TraceBranchError` because a
symbolic proxy cannot answer `__bool__` — restoring control flow would
require rebuilding the entire combinator layer *inside* the effect
language. Intermediate types erased into untyped `dict` environment
tokens.

**Instead:** Interpretation A — effects interpreted inside one
transition's worker, journaled on the existing heartbeat channel,
generator re-executed deterministically on retry (never persisted).
An effect that *deserves* History visibility becomes an ordinary
workflow activity — B's benefits without B's machinery.

## 4. Lambda / Python-AST inspection for guards (AX6)

**Attempt:** let authors write plain `lambda app: app.score > 700 and
app.age >= 18` and inspect the source.

**Why it died:** it only rescues the `and/or/not` keywords, and the
price is source availability at runtime, closure handling,
serialization, and stable source mapping. Meanwhile operator
overloading covers everything else and fails *at construction*.

**Instead:** explicit expression objects — `on(Application).score >
700` builds a typed predicate AST; `__bool__` raises with the remedy
when someone writes `and`:

```python
# ax6_predicates.py — the refusal that teaches
(app.score > 700) & (app.applicant.age >= 18)   # predicate AST
app.score > 700 and app.age >= 18               # raises: use & | ~
```

## 5. Implicit branching from a union annotation (AX5)

**Attempt:** `def evaluate(a) -> Approved | Rejected` silently
generates a branch per variant.

**Why it died:** a return annotation cannot state the case *bodies*;
compiling it alone creates dead variant places. Worse, the underlying
engine behavior is dangerous to leave implicit: a produced token is
routed onto **every** admitting arc, **silently dropped** if none
admit, **duplicated** if several do (measured in AX5's control tests).

**Instead:** the union *validates* — `switch`/`classify` *states* the
routing, and exhaustiveness (missing/unknown/duplicate variants) fails
at construction. Type-based branching is explicit-only.

## 6. Type-only topology — "find any place with this type" (AX0/AX3/AX14)

**Attempt:** the original inquiry's temptation — let types identify
where things connect.

**Why it died:** the frozen engine's own typed derivation refuses two
same-color input arcs (`parameter 'primary' (CreditReport) requires
exactly one matching input arc, found 2`) — and it is right to. AX14
made the rule structural: composition merges places **only on
explicitly declared matching port names**, never on color equality.

**Instead:** the standing principle — combinators define topology;
types validate compatibility and support *local* inference. Named
ports (AX3's `PlaceBoundActivityHandler`, AX22's `Port`) resolve all
same-type ambiguity above the runtime.

## 7. Tuples and generic containers as multi-output (AX3)

**Attempt:** `-> tuple[Reservation, TaxQuote]` or `-> list[Decision]`
for multiple logical outputs.

**Why it died:** nominal colors erase the useful identity —
`list[Decision]`'s name erases to `list` and collides globally.

**Instead:** one named dataclass result per logical output shape, or
separate typed tokens joined downstream (AX4); the AX24 aggregate
uses a canonicalized parameterized color (`Join2[Reservation, Taxes]`)
so even generic joins stay nominal and unique.

## 8. Ordering as the null-safety criterion (AX15 → AX16)

**Attempt:** v1 validator required `.present()` to appear *before* a
risky optional read, left-to-right.

```python
# v1 would refuse this; celpy evaluates it FINE (test_ax16_validation.py ~L67):
reversed_order = (_RECOVERY.operation == "op-r") & _RECOVERY.present()
# error && false == false — in both orders. Absorption is commutative.
```

**Why it died:** measured celpy semantics — `error && false == false`
in both orders; `true || error == true` in both orders. Ordering was
never the criterion; *membership* in the sibling set is. v1 also
missed inherited parent optionality and right-hand references
entirely.

**Instead:** AX16's `validate_guard`: a risky read is safe iff a
sibling guarantees the correct absorption polarity (`.present()`
under `&`, `.is_null()` under `|`).

## 9. `x != null` for presence in celpy (AX15)

**Attempt:** the natural CEL spelling for "field is present".

**Why it died:** celpy **raises `CELEvalError`** on `x != null` for
present struct-valued fields; enabledness treats the error as
unsatisfied and the binding parks *silently* — the worst failure mode
in the codebase (nothing fails, nothing fires).

**Instead:** presence renders as `!(x == null)`, fixed once in the
shared `NullCheck.cel`, tested against the real evaluator.

## 10. FIFO joins across workflow instances (AX4)

**Attempt (control experiment):** let an AND-join pair whatever tokens
arrive first.

**Why it died:** two interleaved cases crossed — rum's reservation
paired with tea's tax quote (`[("rum", 1), ("tea", 2)]`). Topology and
colors provide **no correlation**.

**Instead:** correlation is an architectural discipline: one engine
instance per case (this project's one-engine-per-PR rule). A join can
only combine tokens that share an instance. Never assume the net
protects you here.

## 11. Structural (untyped) guards (AX7)

**Attempt:** let predicates operate on whatever fields the token
happens to have.

**Why it died:** it trades construction-time field errors for runtime
warnings and silently parked tokens. With typed roots, a guard over a
wrong or absent field fails while the author is still typing.

**Instead:** predicates are rooted in a declared type (`on(Approved)`)
and validated against the case's *narrowed* variant (AX7); the engine
checks color before filter, so the narrowing is sound at runtime too.

## 12. The "less code" sales pitch (AX11)

**Attempt (expectation, not code):** the high-level DSL would shrink
real fragments.

**Why it died:** measured — 113 authored lines vs ~95 production for
the same 11-place fragment. Writing down previously implicit policy
(`WAIT`, `DROP`, `otherwise=`) costs lines. The honest economics
arrived in AX13: the *second* concern cost 32 vs 38 lines with zero
new registrations — vocabulary amortizes; adjectives don't.

**Instead:** the case rests on safety, explicit policy, zero callback
registration, construction-time errors, and total source mapping —
never on brevity.

## 13. Declaring ports twice — the redundancy hole (AX26)

**Attempt:** `t_step("parse", _parse, accepts=Raw, returns=Order)` —
declare ports *and* have a typed function.

**Why it died (as the only static hole):** with two sources for the
output type (fn's return and `returns=`), pyright *widens* the TypeVar
to `Raw | Order` instead of reporting the conflict; ty solves to
`Unknown`. Both checkers miss a leaf whose declaration contradicts its
function — case 9 of 9, the only shared miss.

```python
# cases_bad.py — both checkers accept this lie (expect-hole):
contradiction = t_step("lie", _parse, accepts=Raw, returns=Raw)  # _parse returns Order!

# t_fn closes it: the signature is the single source of truth
parse_fn: TPure[Raw, Order] = t_fn(_parse, pure=True)
```

**Instead:** signature inference (`t_fn`) — one source of truth feeds
both the checker and the runtime colors. Sharpened AX3's conclusion:
inference is not merely convenient, it is *safer* than declaration.

## 14. Fail-fast parallelism over effectful branches (AX24)

**Attempt:** race branches and abort losers — for any branches.

**Why it died:** abandoned branches still *ran*; their effects
happened. Composable Functions deleted their `first` combinator for
exactly this; we turned the deletion into an admission rule:
`par_fail_fast` refuses impure branches *and* context-touching ones
(even a pure block wrapped in `holding` — abandoned work may not have
held a shared resource). Losers drain into a visible `abandoned` exit
as inspectable debris — never silently vanished.

**Instead:** the `par` all-policy tolerates effects precisely because
it abandons nothing; fail-fast is reserved for pure, disposable work.

## 15. Domain outcomes on the failure rail (AX25)

**Attempt (refused by design):** let a domain refusal ride the
`failed` rail because it happens to be named `failed`.

**Why it died:** it would erase exactly the type information the
algebra exists to keep — `Applied / AlreadyApplied / Stale /
Exhausted` collapsing into one undifferentiated "error" strips the
downstream net of its ability to route on meaning. The refusal is
structural: rails merge by color (`Failure`), and a `DomainRefusal`
exit is refused fusion with the error message pointing to a typed exit
(AX21).

**Doctrine:** *the rail carries what nobody modeled; classify carries
what somebody did.*

## 16. Smaller rejections worth remembering

- **Input-side XOR lowering for `switch` (AX5):** works, buys nothing
  over output-side typed places, and leaves the decision place
  untyped. Rejected as the main lowering.
- **`None` as a union member / `NoneType` places (AX3/AX5):** absence
  must be an explicit variant type; a `None`-typed input cannot carry
  a token.
- **Construction-time AST normalization (AX1):** flattening nested
  sequences would destroy the authoring shape the source map needs.
  Canonicalize for *fingerprints*, never in place.
- **Raw overlapping guards in `branch()` (AX6):** nondeterministic
  competition is not an authoring-layer feature; authors who want
  Petri nondeterminism drop to the kernel deliberately.
- **Entry/exit-pairs-with-glue as the fragment contract (AX2):**
  sequences own no glue; fusion beats adapters. Foreshadowed AX22's
  port fusion.
- **Universal-combinator regeneration (pre-series, ES-002):** the 14
  fragment families were domain vocabulary masquerading as structure;
  economics negative. ES-003 exists because that died.
- **Relying on the resume door for whole-trace compatibility (AX17):**
  resume audits *live* state only; a narrowed net can silently accept
  a history whose removed transitions already ended. Preflight belongs
  in the authoring layer.
- **`t_step` lowering through always-pure `transform` (AX26):** the
  typed façade's "effectful" story contradicted the runtime `pure`
  flag until a runtime purity test caught it. Static types assert;
  only the deterministic layer verifies.
