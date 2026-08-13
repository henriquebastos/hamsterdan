# Lens 1 — What we did: the experiment map

One entry per experiment: the question, the verdict, the takeaway, and
what to read (in order) if you dig in. Authoring-surface snippets are
quoted verbatim from the spike code so you can see what an author
writes without opening the files.

All paths are relative to
[`../experiments/`](../experiments/index.md), where the series rules
and status table also live.

---

## Arc 1 — Foundations (AX0–AX12): can an AST lower onto the frozen engine at all?

### AX0 — Architecture map and baseline

**Question:** what is the actual current architecture, and which real
fragment is the baseline for everything after?
**Verdict:** complete; baseline selected.
**Takeaway:** four working premises were *corrected* before any design
work: (1) Petrus token/place types ("colors") are nominal strings —
`type Color = str`, the DSL stores `cls.__name__`; (2) CEL filters
exist in the engine but production uses **zero** of them — all 48
production guards are Python `typed_guard` callbacks; (3) activities
are not callbacks on transitions — work is dispatched by *transition
occurrence ID* through `ActivityRequested` → `Dispatch` →
`ActivityCompleted`; (4) the Net is **absent** from History, so any
compiler must be deterministic — same source, byte-identical net — or
old histories will not replay. The baseline fragment: the actions
failure → rerun-or-repair decision, `topology.py` L1461–1476.

**Read:** `ax0-architecture-map/index.md` (the map). There is no spike
code; it points into production sources.

What production authoring looks like — the "before" for the whole
series (quoted in the AX0 record):

```python
rerun = t.authorize_rerun(
    handler=petri_handler(_rerun),
    guards=typed_guard(_first_failure, converter=PydanticPayloadConverter()),
)
(p.authority, p.mutation_state) >> arc.read() >> rerun
(p.actions_state, p.actions_basis) >> rerun >> (p.actions_state, work.p.actions_rerun)
```

### AX1 — Minimal workflow AST

**Question:** is a three-node AST (`Activity`, `Sequence`, `Parallel`)
a useful IR — traversable, printable, deterministic?
**Verdict:** Promising; continue.
**Takeaway:** frozen dataclass nodes with structural identity work;
source location (`origin`) is retained but excluded from equality, so
equal source produces equal ASTs and equal fingerprints. `walk()`
yields deterministic child-index paths (`/1/0`) that later seed
generated net paths — the source map falls out of the tree shape. The
honest gap: this AST says nothing about data (colors, transforms, join
meaning), which is exactly what the low-level DSL forces you to write.

```python
sequence(
    activity(review),
    parallel(
        activity(actions_discovery),
        activity(conversation),
    ),
    activity(dashboard_publish),
)
```

**Read:** `ax1-minimal-ast/index.md`, then `workflow_ast.py` (nodes,
walk, canonical form, fingerprint), then `test_workflow_ast.py`.

### AX2 — Lowering Activity and Sequence

**Question:** can the smallest compiler lower a sequence onto the
frozen `Net`, with a clear fragment contract and no runtime changes?
**Verdict:** Promising; continue.
**Takeaway:** the lowering contract is a *threaded fragment* — a
function from one entry place to one exit place; `Sequence` owns no
glue (no adapter places, no passthrough transitions). N activities
lower to exactly N transitions, N+1 places, 2N arcs, **byte-identical**
to the hand-written DSL equivalent. Replay over a recompiled net works;
a divergent net fails loudly (`token records on w.1.out: not a place
of this net`). This established the determinism-and-replay contract
every later experiment inherited.

```text
w.entry(Draft) ──▶ w.0.review ──▶ w.0.out(Review) ──▶ w.1.publish ──▶ w.1.out(Publication)
                   handler="review"                    handler="publish"
```

**Read:** `ax2-lower-sequence/index.md`, then `ax2_compiler.py`, then
`test_ax2_compiler.py` (byte-equivalence, replay, divergence refusal).

### AX3 — Typed activities, ports, inference

**Question:** what can be inferred from Python type hints, and how do
two places with the same type get distinguished?
**Verdict:** Promising; continue.
**Takeaway:** existing `@activity` definitions already expose resolved
annotations, so single-in/single-out inference is free. The decisive
finding is the ambiguity case: the frozen engine's own typed
derivation *correctly refuses* two same-color inputs (`parameter
'primary' (CreditReport) requires exactly one matching input arc,
found 2`), and a ~60-line `PlaceBoundActivityHandler` resolves it by
binding parameter names to *place paths* — named ports need no engine
change. Refused with reasons: union returns (unions mean branching),
`list[Decision]` (nominal name erases to `list`), `None` inputs. The
governing principle the whole series kept: **combinators define
topology; types validate compatibility and support local inference.**

**Read:** `ax3-typed-ports/index.md` (the inference matrix), then
`ax3_inference.py`, then `test_ax3_inference.py`.

### AX4 — Parallel split and join

**Question:** how does AND-parallelism lower so that split, independent
flow, waiting, and result combination are each observable?
**Verdict:** Promising; continue.
**Takeaway:** split is an explicit generated passthrough transition;
the *downstream multi-input activity transition is the join* — branch
results stay separate typed tokens parked durably until all inputs
exist. Two discoveries with long shadows: (1) apparent concurrency
failures were the engine's *driving policy* (`choose_conservative`
serializes; `choose_throughput` interleaves) — topology only enables
concurrency; (2) FIFO joining mispaired tokens from two interleaved
cases — **correlation is not provided by topology or colors**; the
project's one-engine-per-PR discipline is what makes joins safe.

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

**Read:** `ax4-parallel-join/index.md`, then `test_ax4_parallel.py`
(parked joins, policy discovery, crossed-case mispairing), then
`ax4_compiler.py`.

### AX5 — Branching by output type

**Question:** can `evaluate() -> Approved | Rejected` lower to one
place and arc per variant, with runtime dispatch on concrete type?
**Verdict:** Promising; continue.
**Takeaway:** first, the danger was measured: the frozen engine routes
a produced token onto *every* admitting arc, **silently drops** it if
none admit, and **duplicates** it if several do. The design answer:
`switch` is explicit (the union annotation *validates* exhaustiveness;
it never generates topology by itself), and a `VariantPayloadConverter`
stamps `{"$variant": "Approved", ...}` into the durable JSON so the
discriminator survives serialization. Subclasses are refused at the
worker boundary rather than silently unrouted.

```python
sequence(
    switch(
        evaluate,                                  # Application -> Approved | Rejected
        case(Approved, then=step(provision)),
        case(Rejected, then=step(notify)),
    ),
    step(archive),
)
```

**Read:** `ax5-type-branching/index.md`, then `ax5_compiler.py`
(converter, variant routing), then `test_ax5_switch.py` (the native
silent-drop/duplication probes are the must-read tests).

### AX6 — Guard-based branching (predicate DSL)

**Question:** can explicit Python expression objects route same-typed
tokens by value, compiling to CEL arc filters, with overlap and
no-match policies explicit?
**Verdict:** Promising; continue.
**Takeaway:** `on(Type)` builds a typed proxy whose operators produce a
predicate AST validated at authoring time (unknown fields, impossible
comparisons fail immediately). Compilation makes first-match
deterministic by *conjoining each case with the negations of all
earlier cases*; `otherwise=` is mandatory and compiles to the negation
of everything — the frozen engine's silent no-match parking becomes
unrepresentable. Python `and/or/not` cannot be overloaded, so
`__bool__` raises with the remedy (`&`/`|`/`~`); lambda/source
inspection was evaluated and rejected.

```python
app = on(Application)

sequence(
    branch(
        when((app.score > 700) & (app.applicant.age >= 18), then=step(fast_track)),
        when(app.score > 500, then=step(senior_review)),
        otherwise=step(manual_review),
    ),
    step(archive),
)
```

**Read:** `ax6-guard-branching/index.md`, then `ax6_predicates.py`
(the proxy and CEL rendering), then `test_ax6_guards.py`.

### AX7 — Hybrid routing (type + guard on one arc)

**Question:** can one case carry both a type constraint and a value
predicate without exposing low-level arcs?
**Verdict:** Promising; continue.
**Takeaway:** the enabling engine fact: an arc's nominal color is
checked *before* its CEL filter, so a predicate over `Approved` fields
never evaluates against a `Rejected` token. `case(Type, when=...)`
lowers to a single arc carrying both inscriptions. Construction
requires every union variant covered and exactly one unguarded default
per variant — guarded-only variants are refused because unmatched
values would park silently. Guards are validated against the *narrowed*
type: a `risk` guard on a variant without that field fails at
authoring.

```python
approved = on(Approved)

hybrid(
    evaluate,  # -> Approved | Rejected
    case(Approved, when=approved.risk < 20, then=step(auto_processing)),
    case(Approved, then=step(senior_approval)),
    case(Rejected, then=step(manual_processing)),
)
```

**Read:** `ax7-hybrid-routing/index.md`, then `ax7_workflow_ast.py`
(the totality rules), then `test_ax7_hybrid.py`.

### AX8 — Loops, cycles, retries

**Question:** can a tree-shaped AST represent a cyclic net — and where
do loop state, guards, and retry counts live?
**Verdict:** Promising; continue.
**Takeaway:** the hypothesis held: `retry(...)` stays one tree node;
compilation introduces exactly one loop-back arc. Retry state is an
explicit *domain field* on the retryable variant (durable, visible in
History as attempts 1, 2, 3); re-arming is a pure typed transform, not
worker dispatch. The stated limit: the compiler cannot prove counter
progress — a type-correct rearm that forgets to increment loops
forever; bounded driving reports `did not quiesce`. Workflow-level
retry (new durable occurrence per attempt) and worker-level retry
(invisible redelivery) are deliberately *not* collapsed.

```python
retry(
    charge,  # -> Confirmed | Transient | Fatal
    case(Confirmed, then=step(record)),
    case(Fatal, then=step(refund)),
    retryable=Transient,
    rearm=rearm_charge,        # pure typed: Transient -> ChargeRequest
    limit=3,
    exhausted=step(escalate),
)
```

**Read:** `ax8-loops-retries/index.md` (the state-location table),
then `ax8_compiler.py`, then `test_ax8_retry.py`.

### AX9 — Effect-oriented activity authoring

**Question:** do yielded effect values improve activity authoring —
and do effects belong inside one transition (A) or compiled into net
structure (B)?
**Verdict:** Promising with changes — **Interpretation A only.**
**Takeaway:** A works on the frozen engine: the worker re-constructs
the generator on every attempt, replays journaled effect results into
it, and executes only the first unjournaled effect — the journal rides
the existing dispatch heartbeat channel, so a successor attempt resumes
after a crash (proven: `ReserveFunds` performed once, `SendPayment`
twice). Generator frames are never durable state; the generator is
*re-executed deterministically*, with effect fingerprints catching
divergence. B was built and rejected: see
[02-what-did-not-work.md](02-what-did-not-work.md#effects-as-net-structure).

```python
def settle_payment(payment: Payment) -> Settlement:
    reservation = yield ReserveFunds(payment.account_id, payment.amount)
    result = yield SendPayment(reservation.reservation_id)
    yield EmitEvent("payment_settled", result.reference)
    return Settlement(reference=result.reference)
```

**Read:** `ax9-effect-authoring/index.md` (the full A/B comparison),
then `ax9_effects.py` (the replay interpreter), then
`test_ax9_effects.py` (the crash/resume proof).

### AX10 — Authoring styles compared

**Question:** which embedded-Python spelling authors the AST — nested
combinators, fluent chain, context-manager builder, or generator —
judged on a *nested* example?
**Verdict:** Promising; continue — nested combinators are the semantic
core and default surface; an immutable fluent chain is acceptable sugar
for linear flows; context-manager and generator builders are rejected.
**Takeaway:** nested combinators *are* the AST — extracted
subexpressions are reusable immutable values, and the type checker sees
every argument position. The fluent chain degenerates into nested
`Flow.start(...)` the moment a branch has two steps. The rejections
(mutable scope-stack state; symbolic handles that cannot answer `if`)
are detailed in [02-what-did-not-work.md](02-what-did-not-work.md).

**Read:** `ax10-authoring-styles/index.md` (the rubric), then
`test_ax10_styles.py` (all four spellings of the same AST,
side by side — the fastest way to form your own opinion).

### AX11 — The real fragment

**Question:** does the design survive a real production fragment,
measured — not admired?
**Verdict:** Promising; continue.
**Takeaway:** the conversation-intent fragment (11 places, 6
transitions, 22 arcs in production) was re-authored with
scatter/lane/choice/fold vocabulary and proven **token-for-token
equal** against a production-style oracle across five scenarios; a
recompiled net replayed 26 history records. The honest economics: 113
authored lines vs ~95 production — *more*, because implicit policy
(`WAIT`, `DROP`) must now be written down. What you actually buy: zero
separately registered callbacks (production had six), no repeated
wiring, ten classes of construction-time errors, and a total
transition→source-line map.

```python
scatter(
    unpack_intents,
    lane(
        INTENT_RESULT,
        where=_intent.kind.one_of(*FINDING_KINDS, *REMINDER_KINDS),
        then=choice(
            case(when=CURRENT & AUTHORIZED & _intent.kind.one_of(*FINDING_KINDS),
                 then=fold(accept_finding_intent, state=REVIEW_STATE)),
            ...
            otherwise=WAIT,  # stale/unauthorized intents park, as production implies
```

**Read:** `ax11-real-fragment/index.md` (measurements), then
`ax11_fragment.py` (the full authored fragment), then
`test_ax11_fragment.py` (the oracle and parity scenarios).

### AX12 — Early recommendation (superseded)

**Question:** given AX0–AX11, what architecture should be chosen?
**Verdict:** Promising with changes — **superseded by this synthesis.**
**Takeaway:** a faithful midpoint snapshot: layered model (combinator
AST → deterministic compiler → frozen runtime), CEL as guard backend,
effects inside activities only, nested combinators as default surface.
It predates blocks, the kernel, port fusion, typed outcomes, parallel
policies, the rail, and the typed façade — read it only as history.

**Read:** `ax12-recommendation/index.md`, knowing
[05-unified-candidate-spec.md](05-unified-candidate-spec.md) is the
current version of the same document.

---

## Arc 2 — Composition (AX13–AX23): what is the right unit?

### AX13 — Sibling amortization

**Question:** AX11 cost more lines than production — does the
economics flip for the *next* concern?
**Verdict:** Promising; continue.
**Takeaway:** yes: adding the change-intent sibling cost 32 authored
lines vs 38 production, zero new handler registrations (production
adds two), and identical marginal net growth (+2 places / +2
transitions / +8 arcs on both sides). The vocabulary is paid once;
siblings reuse it. Bonus: fragments are values — `dataclasses.replace`
on the committed AX11 AST produces a byte-identical compiled net.

**Read:** `ax13-sibling-amortization/index.md`, then
`ax13_fragment.py` (the entire marginal cost, in one file).

### AX14 — Fragment composition

**Question:** can concerns be authored as *independent fragment
values* composed by name — no AST surgery?
**Verdict:** Promising; continue.
**Takeaway:** `compose(name, *fragments)` merges places **only when
explicitly declared port names match** (agreeing in color and port
kind); same color under different names never merges. Composed(AX11
base, independent change concern) is byte-for-byte identical to AX13's
restated monolith. Composition order is semantic for serialization —
determinism again.

```python
def change_concern():
    return handoff_fragment(
        "change-intents",
        entry=CHANGE_BASIS,        # the shared hand-off port
        reads=(AUTHORITY,),
        states=(MUTATION_STATE,),
        body=CHANGE_LANE_BODY,     # AX13's proven lane body, unchanged
    )

compose("conversation-intents-change", conversation_intents(), change_concern())
```

**Read:** `ax14-fragment-composition/index.md`, then
`ax14_compose.py` (the identity rules), then `test_ax14_compose.py`.

### AX15 — The hardest production guard

**Question:** does the predicate DSL survive `_recoverable_publication`
— five tokens, open maps, nested optionals, identity matching?
**Verdict:** Promising; continue.
**Takeaway:** three target-specialized predicates replaced production's
generic five-token closure and *shrank* the net (56 → 54 arcs); the
mandatory `otherwise=retire()` mechanically generated the complement
production wrote by hand. It also exposed a celpy dialect defect:
`x != null` **raises** on present struct fields — presence must render
as `!(x == null)` — and revealed that the v1 null-safety validator had
holes, which became AX16's question.

**Read:** `ax15-recovery-concern/index.md`, then `ax15_recovery.py`
(the recovery predicate is the best showcase of the DSL under load),
then `test_ax15_recovery.py`.

### AX16 — Null safety is a sibling-set property

**Question:** can the "conjoin `.present()` first" author obligation
become a validator — and is ordering even the right criterion?
**Verdict:** Promising; continue — ordering is the *wrong* criterion.
**Takeaway:** measured celpy semantics: `error && false == false` in
**both orders** (and `true || error == true` in both orders) — CEL
absorbs errors commutatively. So a risky read is safe if *any sibling*
in the conjunction guarantees false-when-absent — membership, not
position. `validate_guard` (v2) closes all three v1 holes: inherited
parent optionality, right-hand references, and the bogus ordering
requirement.

**Read:** `ax16-null-safety-validation/index.md` (the absorption
table), then `ax16_validation.py`, then `test_ax16_validation.py`
(`TestAbsorptionSemantics` proves it against the real engine).

### AX17 — Net evolution

**Question:** when is `resume(net', history)` sound for a net the
history was not recorded under?
**Verdict:** Promising; continue.
**Takeaway:** the net *name* is process identity (structurally
identical net under another name = refused as a foreign trace).
Superset evolution under the same name is a **zero-migration**
operation: old places replay identically, new places start empty — and
a token parked on an unconsumed hand-off place becomes *deferred
capability*, consumed once the new concern is composed in. Caveat:
resume audits live state only; narrowing can slip through if the
removed structure has no live tokens.

**Read:** `ax17-net-evolution/index.md` (the five evolution rules),
then `test_ax17_evolution.py`.

### AX18 — The generic kernel

**Question:** can the domain vocabulary desugar into a small,
net-agnostic Petri IR that can also express nets the sugar has no
words for?
**Verdict:** Promising; continue.
**Takeaway:** the whole IR is four shapes — `KernelPlace(name, color)`,
`KernelArc(place, mode)` with `consume/read/produce`,
`KernelTransition(name, arcs, guard, work)`, `KernelNet(name, nodes)`.
Desugaring the full AX13 fragment through it reproduces the direct
compilation **byte-for-byte**. The kernel spells cycles, same-color
place pairs, disconnected places, and handler-less competition — the
arbitrary-net floor under the structured sugar.

```python
KernelTransition(
    name="shuttle_right",
    arcs=(read("meter"), consume("left"), consume("fuel"), produce("right")),
    guard="meter[0].data.enabled == true",
    label="move the slot right while the meter is on, burning one pellet",
)
```

**Read:** `ax18-generic-kernel/index.md`, then `ax18_kernel.py` (the
whole IR in one file), then `ax18_neutral.py` (the arbitrary-net
example), then `test_ax18_kernel.py` (byte-identity proof).

### AX19 — Kernel boundary features

**Question:** are arc weights, input filters, inhibitors, timers, and
external delivery really "additive fields" on the frozen runtime?
**Verdict:** Promising; continue.
**Takeaway:** yes — `weight`, `filter`, `Mode.INHIBIT` on arcs;
`Delay`/`Until` timers (deterministic under `SimulatedClock`);
produce-only transitions fired via `engine.deliver(...)` whose
delivery *identity deduplicates* the at-least-once door. One loud
refusal encoded permanently: a **produce filter** is rejected at
declaration, because frozen output arcs admit by color only and the
filter would silently not execute.

**Read:** `ax19-kernel-boundary/index.md`, then `ax19_kernel.py`
(`BoundaryArc` is the shape everything later imports), then
`test_ax19_boundary.py` (one runnable net per feature).

### AX20 — The function-shaped subnet (claim/fence)

**Question:** can a subnet behave like a function call — enter through
a claiming boundary, run a linear disposable interior, judge validity
once at exit?
**Verdict:** Promising; continue.
**Takeaway:** this answered the Navigator's "missing linearity"
diagnosis. Entry *consumes the concern's single state token* — the
token's location is a structural mutex, no `in_flight` flags. The
interior is pure and reads nothing ambient. Only the two complementary
exits read authority: `commit` (guard `FENCE`) emits work and returns
updated state; `discard` (guard `!(FENCE)`) throws the run away and
returns the claim unchanged. Do-then-validate replaces
check-before-start.

```python
BoundaryTransition(
    name="commit",
    arcs=(read("authority"), consume("draft"), consume("claimed"),
          produce("work"), produce("state")),
    guard=FENCE,
    label="fence once; emit the effect; release the state updated",
)
```

**Read:** `ax20-function-subnet/index.md`, then `ax20_subnet.py` (the
whole topology, heavily annotated), then `test_ax20_subnet.py`.

### AX21 — Typed effect outcomes

**Question:** can both kinds of idempotency — "did it, skip" and "did
it, now it fails" — live as net structure?
**Verdict:** Promising; continue.
**Takeaway:** the outcome vocabulary `Applied | AlreadyApplied | Stale
| Transient` routes by color into ordinary places; "already done" and
"preconditions changed" are *places, not exceptions*. The doctrine:
**lookup answers before preconditions** — an operation found after the
base moved is `AlreadyApplied`, not `Stale`. Only `Transient` loops
(bounded, attempt count durable in the token). Replay never consults
the outside world.

```python
def apply(self, op, base, payload) -> str:
    if op in self.applied:      # lookup-first: before any precondition
        return "already"
    if base != self.base:       # compare-and-swap: the moved base
        return "stale"
    ...
```

**Read:** `ax21-effect-outcomes/index.md`, then `ax21_boundary.py`,
then `test_ax21_boundary.py`
(`TestKindTwoLookupFirst::test_lookup_answers_before_preconditions`).

### AX22 — Structured composition (blocks)

**Question:** *what if control statements could only call functions?*
Can composition whose only operands are function-like blocks produce
sound-by-construction nets?
**Verdict:** Promising; continue.
**Takeaway:** the arc's centerpiece. A `Block` is a frozen value: one
typed entry `Port`, named typed exit `Port`s, kernel nodes inside, and
a purity flag. `then(a, b, on="out")` composes by **port fusion** —
the downstream entry place is renamed to the upstream exit place; no
glue transition, no extra event, no state. `check_sound` verifies
every node lies on an entry→exit path; `disposable` refuses effectful
interiors at authoring time. Purity propagates through composition.

```python
@dataclass(frozen=True)
class Block:
    """A function-like subnet value: one entry, named typed exits."""
    name: str
    nodes: tuple[KernelNode, ...]
    entry: Port
    exits: Mapping[str, Port]
    pure: bool
```

**Read:** `ax22-structured-composition/index.md`, then
`ax22_blocks.py` (the algebra), then `test_ax22_blocks.py` (the
pipeline test is a complete worked example).

### AX23 — The completed algebra

**Question:** do `merge`, `loop`, and context ports fit as combinators
— without touching leaves, fusion, or the engine?
**Verdict:** Promising; continue.
**Takeaway:** all three are *place-fusion* operations. `merge` unifies
same-colored exits into one; `loop(block, on="again")` fuses an exit
back to the entry — the authoring expression stays a tree while the
net becomes cyclic (AX8's hypothesis, now algebraic). `holding`
brackets a block with an AX20-style claim: consume a context token at
entry, return it at every exit. The capstone test composes
claim + disposable prep + fence + lookup-first outcomes + bounded
transient loop + merge + release — the full AX20+AX21 story from the
algebra alone.

```python
def bounded_retry() -> Block:
    bump = transform("bump", lambda d: {**d, "tries": d["tries"] + 1},
                     accepts="Job", returns="Attempt")
    judge = classify("judge",
                     lambda d: ("done", d) if d["tries"] >= 3 else ("again", d),
                     accepts="Attempt", outcomes={"done": "Done", "again": "Job"},
                     pure=True)
    return loop(then(bump, judge, on="out"), on="again")
```

**Read:** `ax23-completed-algebra/index.md`, then `ax23_blocks.py`
(the seven combinators), then `test_ax23_blocks.py` (the capstone at
the end is the single best test in the series).

---

## Arc 3 — Composable Functions (AX24–AX26): stress-testing against a proven library

Context for all three: [../composable-functions.md](../composable-functions.md)
analyzes seasonedcc's TypeScript library and found five independent
convergences with our doctrines plus one true gap — the algebra had no
parallel combinator, and with it no answer to totality and join policy.

### AX24 — Parallel blocks

**Question:** can a parallel combinator join soundly in the presence of
failure, with the join policy explicit in the net?
**Verdict:** Promising; continue.
**Takeaway:** two policies, both visible. `par` (AND-join, all
branches): sound *because* every branch must be total (exactly one
exit) — the join can never wait on a token that cannot come; branches
with variants totalize first, and a downstream `classify` splits the
aggregate (error accumulation falls out). `par_fail_fast`: admissible
only over **pure, context-free** branches (their deleted `first`
combinator, turned into our admission rule); one `armed` once-only
token; losers drain into a visible `abandoned` exit — 2+3n transitions,
not the 2^n naive blowup. One honest extension: fan-out/fan-in handlers
address arcs *positionally*, because a split produces one datum into N
same-colored places.

**Read:** `ax24-parallel-blocks/index.md`, then `ax24_parallel.py`,
then `test_ax24_parallel.py` (includes the canonical inquiry example
end to end).

### AX25 — The failure rail

**Question:** can railway-oriented failure handling be pure sugar over
the algebra — without collapsing AX21's typed outcomes into one error
channel?
**Verdict:** Promising; continue (scope rule held as doctrine).
**Takeaway:** the rail is a *place*, not a hidden channel. `attempt`
totalizes a leaf (exception → durable JSON envelope: kind, message,
source, retryable, cause chain — exact round-trip asserted);
`rail_then` merges rails structurally into **one** `Failure` place per
chain (counted, not assumed); `recover` demands a total handler that
rejoins the success track, consuming the rail exit. Zero kernel,
algebra, or runtime changes — ~60 lines of arrangement. The doctrine:
**the rail carries what nobody modeled; classify carries what somebody
did** — a domain exit named `failed` is refused fusion by color.

**Read:** `ax25-failure-rail/index.md`, then `ax25_rail.py`, then
`test_ax25_rail.py` (the domain-exit refusal test is the doctrine).

### AX26 — Build-time type checking

**Question:** how far can pyright and ty move composition errors to
edit time?
**Verdict:** Promising; continue — pyright is the edit-time authority
today; ty tracked; the deterministic compiler stays the final judge.
**Takeaway:** a ~190-line generic façade — TypedDicts as colors (plain
dicts at runtime, zero bridging), `TBlock[I, O]` always total,
`TChoice` deliberately *not* a `TBlock` until routed, purity as a
subtype — lowers unchanged to AX23/AX24. The pinned catch matrix:
**pyright 1.1.411 rejects 8/9** deliberate mistakes with zero false
positives and zero annotation burden; **ty 0.0.63 rejects 4/9** (its
generic solver does not yet fail unsatisfiable constraints — precise
inference, incomplete enforcement). The shared 9th hole (declaring
ports twice → TypeVar union-widening) is closed by `t_fn`, which
infers ports from the signature alone: **inference is safer than
declaration.**

```python
both     = t_par2("both", first=reserve, second=taxes)
routed   = t_route(judge, when_yes=settle, when_no=escalate, returns=Done)
workflow: TBlock[Raw, Done] = t_then(t_then(t_then(parse, both), charge), routed)
```

**Read:** `ax26-static-typing/index.md` (the catch matrix), then
`ax26_typed.py`, then `cases_bad.py` (each mistake annotated with the
runtime error it twins), then `test_ax26_static.py` (the pinned
harness).

---

## Arc 4 — Progressive disclosure (AX27–AX29): does the algebra meet the governing DX target?

After AX26 the Navigator recorded a governing product target (see the
[exploration index](../index.md)): preserve full runtime power and
every honest low-level escape hatch; make a Hamsterdan-scale flow
radically simple to author, ideally one file to first motion; keep the
primitives general — reusable for *any* net, never Hamsterdan-shaped.
Arc 4 tested the algebra against that target from three directions:
above it (a machine generating authoring code), at it (the run
surface), and below it (descent to kernel authoring).

### AX28 — One file to first motion

**Question:** can a single general call take *any* authored Block to a
quiescent instance on the frozen engine, keeping every durable
artifact (canonical definition, History, marking, replay) inspectable
and every validation intact — or does "radically simple" start hiding
semantics?
**Verdict:** Promising; continue (store default explicitly tabled).
**Takeaway:** the composition burden was real and it was *harness*
work, never authoring meaning: the prior spikes hand-compose
`Engine.create` at 33 call sites across 22 files, each touching ~8
infrastructure names; the one-file example touches **one**. The
127-line `first_motion(block, data)` reads everything it needs off the
Block itself (entry port names the seed place and color; exits name
the observation points; `compile_block` carries handlers, guards, and
`check_sound`) — so a wrongly-colored injection is unrepresentable and
generality holds: the same unchanged harness drove a
linear+parallel+branching net *and* a cyclic retry net. The returned
`Motion` exposes rather than wraps — `.definition`, `.records`,
`.settled`, `.replay()` — so first motion *teaches* the durable
contract instead of hiding it:

```text
net definition: 5732 canonical bytes
history records: 39
exits: {'settled': [{'sku': 'sku-1', 'total': 12.0}], 'review': []}
replay: rebuilt marking matches, place by place
```

**Read:** `ax28-first-motion/index.md`, then `ax28_one_file.py` (the
whole authoring experience in 102 lines), then `ax28_motion.py`, then
`test_ax28_motion.py` (the cyclic-net generality test is the point).

### AX27 — Generated authoring against the composition authority

**Question:** the Deer Workflow comparison raised the generated-
authoring route — an agent emits authoring source and iterates against
deterministic feedback. Do the algebra's existing refusals actually
behave as that feedback loop: total review, repair-grade messages, and
a guarantee that review never executes the net?
**Verdict:** Promising; continue (trust contract and residue boundary
are load-bearing findings).
**Takeaway:** no new authority was needed — a ~120-line total
`review(name, source)` stages the existing refusals (`source` → parse,
`author` → eager `CompositionError`s, `sound` → `check_sound`) and
every one of ten characteristic generator mistakes lands at its
expected stage; **five of ten messages carry the concrete fix
verbatim** (pinned as a counted test, e.g. `its exits are ['out']`),
and the repair-loop test closes mechanically from the message alone.
Review provably never executes the net (`Engine` poisoned, review
still succeeds). Two honest residue mistakes pass every pre-motion
stage — an undeclared runtime outcome and a data-driven
non-termination — so the full loop is **static → review → opt-in
motion**, each stage catching what the earlier ones cannot.

**Read:** `ax27-generated-authoring/index.md`, then `ax27_review.py`,
then `ax27_corpus.py` (the ten mistakes plus two residue cases), then
`test_ax27_review.py` (the repair-loop test).

### AX29 — The descent seam

**Question:** progressive disclosure promises descent to lower-level
APIs for unusual semantics. Does the descent actually compose — does
each level's validation still govern its level, or does the escape
hatch quietly weaken soundness checks?
**Verdict:** Promising; continue (the two-depth law is the seam's
doctrine).
**Takeaway:** descent has **two depths with different laws, both
governed**. *In-block* descent — a hand-built `Block` from raw kernel
nodes, using per-arc CEL filters that route by value with no handler
and two same-colored exits (semantics `classify` refuses) — stays
entirely under the algebra: eager refusals at `then`, `check_sound`,
and AX28's `first_motion` runs and replays it unchanged. *Below-block*
descent — the inhibitor arc, refused inside blocks because it is
non-flow — splices legally at the boundary-net level, where
`check_sound` still governs the block part first and
`KernelShapeError` governs the union. The
dispatch-until-acknowledged throttle is observed, not assumed: exactly
one order dispatched at quiescence with the arc, both without it; acks
arrive as `Engine.deliver` source firings; replay rebuilds the marking
including delivered tokens. Honest cost: a `LoweredBoundary` has no
ports, so below the algebra the run surface is manual.

```python
# ax29_descent.py — in-block descent: value routing no combinator spells
BoundaryTransition(
    name="expedite",
    arcs=(consume("triage_in", filter="amount < 100.0"), produce("express")),
)
```

**Read:** `ax29-descent-seam/index.md`, then `ax29_descent.py` (both
depths side by side), then `test_ax29_descent.py` (the
inhibitor-counterfactual test is the doctrine).
