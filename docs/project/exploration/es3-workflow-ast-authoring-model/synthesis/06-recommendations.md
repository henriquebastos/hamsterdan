# Lens 5 — Recommendations

**Status: candidate recommendations for Navigator decision — nothing
here is decided.** Every recommendation is argued from quoted code and
measured results; the snippets are the facts, the prose is the
argument. Each entry states what to adopt or avoid, the evidence for,
the honest cost against, and a confidence grade:

- **High** — proven by running spike code with focused tests, on more
  than one shape, against the frozen engine.
- **Medium** — proven in one shape or resting partly on judgment;
  a bounded follow-up could change it.

Section D lists the decisions the evidence *cannot* make — only the
Navigator can.

---

## A. What to adopt

### R1 — Make blocks + the combinator algebra the general authoring layer; keep the current DSL as the compile target

**Confidence: High** (AX22, AX23, AX11/AX13/AX15 oracle parity, AX18
determinism).

The fact — what authoring a real concern looks like today
(production `topology.py`, quoted in AX0):

```python
rerun = t.authorize_rerun(
    handler=petri_handler(_rerun),
    guards=typed_guard(_first_failure, converter=PydanticPayloadConverter()),
)
(p.authority, p.mutation_state) >> arc.read() >> rerun
(p.actions_state, p.actions_basis) >> rerun >> (p.actions_state, work.p.actions_rerun)
```

The fact — the same kind of meaning under the algebra (runs today,
`ax28_one_file.py`; general vocabulary, zero Hamsterdan words):

```python
def order_workflow() -> Block:
    gathered = then(receive(), par("gather", {"inventory": reserve(), "taxes": taxes()},
                                   returns="Quote"), on="out")
    charged = then(gathered, charge(), on="out")
    return then(charged, judge(), on="out")
```

**For:** every value is frozen and inspectable; every mistake is an
eager `CompositionError` at the call site (wrong color, missing exit,
duplicate name — with the alternatives in the message); zero callback
registration; cycles from a tree (`loop`), mutual exclusion as visible
structure (`holding`), all of it lowering deterministically —
byte-identical net from equal source — onto the frozen engine. Three
production fragments were reproduced token-for-token against the
production oracle (AX11/AX13/AX15).

**Against (the honest costs):** it is *not* less code — measured 113
authored lines vs ~95 production for the same 11-place fragment
(AX11); the economics only turn positive at the second concern (32 vs
38 lines with zero new registrations, AX13). It is a new vocabulary to
learn, and all names are provisional. The case rests on safety,
explicitness, and amortization — never brevity.

### R2 — Keep the layered surface, governed by the two-depth descent law

**Confidence: High** (AX18/AX19 for the kernel boundary; AX29 for the
seam).

The layer model (spec §1) with descent proven: L1 kernel nodes, L2
blocks + combinators, L3 typed façade, L4 sugar. The fact — descent
*widens* expression without leaving governance (`ax29_descent.py`):

```python
# In-block descent: value routing no combinator spells — no handler,
# the token's own data decides; still then/check_sound/first_motion
BoundaryTransition(
    name="expedite",
    arcs=(consume("triage_in", filter="amount < 100.0"), produce("express")),
)
```

And the boundary is semantic, not arbitrary: an inhibitor arc inside a
`Block` is refused by `check_sound` ("inhibitor arcs are outside the
block algebra" — it is non-flow, so it would break what entry→exit
reachability means), while the same arc one level down is legal kernel
authoring governed by `KernelShapeError`.

**For:** progressive disclosure holds in both directions — upward
(sugar over the algebra) and downward (kernel authoring under it) —
with no check weakened anywhere; each authority keeps its
jurisdiction.

**Against:** below-block descent loses the conveniences (a
`LoweredBoundary` has no ports, so no `first_motion`; engine assembly
is manual). Whether a supported *re-wrap* back to `Block` should exist
is an open decision (D5).

### R3 — Adopt the typed façade with pyright as the edit-time authority; the deterministic compiler stays the judge

**Confidence: High for pyright; Medium for the CI story** (AX26).

The fact — the pinned catch matrix: **pyright 1.1.411 rejects 8/9**
deliberate composition mistakes from source text alone, zero false
positives, zero annotation burden; **ty 0.0.63 rejects 4/9** (precise
inference, incomplete enforcement — its solver does not yet fail
unsatisfiable generic constraints). The 9th hole is closed by
inference over declaration:

```python
# ax26_typed.py — t_fn infers ports from the signature; declaring
# ports twice was the one mistake both checkers missed (TypeVar
# union-widening), so the API removes the redundancy instead
both     = t_par2("both", first=reserve, second=taxes)
routed   = t_route(judge, when_yes=settle, when_no=escalate, returns=Done)
workflow: TBlock[Raw, Done] = t_then(t_then(t_then(parse, both), charge), routed)
```

**For:** most composition errors move into the editor, on the exact
offending line, before anything runs — and the layering held under
fire: during the spike ty caught a bug pyright accepted, pyright
caught eight ty missed, and the runtime `CompositionError` layer
caught one both checkers were happy with. Checkers advise; the
deterministic layer decides.

**Against:** fixed-arity ceiling (`t_par2`/`t_par3`, two-way choice —
Python lacks mapped types; the runtime algebra handles the general
case); this repo's CI currently runs ty, which today enforces less
than half of what pyright does on these patterns (D7).

### R4 — Adopt the predicate AST compiled to CEL as the guard model; it is also the separable minimum adoption

**Confidence: High** (AX6/AX7/AX15/AX16; ES-002 guard audit).

The fact — authoring is operator overloading on typed field
references, and the CEL output is exact (`test_ax6_guards.py`):

```python
app = on(Application)
FAST = (app.score > 700) & (app.applicant.age >= 18)

assert FAST.cel() == "((score > 700) && (applicant.age >= 18))"
assert app.applicant.country.one_of("US", "BR").cel() == '(applicant.country in ["US", "BR"])'
assert app.note.is_not_null().cel() == "(note != null)"
```

The supporting audit fact: 45 of 48 production guards decompose into
four decidable atom kinds (ES-002); only two are genuinely opaque and
stay as Python `typed_guard`s. Production currently uses **zero** CEL
filters, so this capacity is idle in the engine today.

**For:** guards become frozen, serializable, diffable values with
structural equality; branch overlap becomes *declarable policy*
(ordered `branch`/`otherwise`) instead of silent nondeterminism;
null-safety is validated by absorption semantics (AX16) rather than
field ordering. This piece is adoptable alone — no blocks, no façade —
which makes it the lowest-risk first step (spec §11).

**Against:** celpy's `x != null` needed care (AX15); the two opaque
atoms remain Python callbacks forever; a second guard language in the
codebase until migration completes.

### R5 — Keep effects inside activities; never compile effects into net structure

**Confidence: High** (AX9 Interpretation B rejection; AX21).

The fact — the effect journal and typed outcomes live at the worker
boundary, and the failure rail refuses to swallow modeled outcomes
(`test_ax25_rail.py`):

```python
block = rail_then(rail_then(parse(), enrich(world)), store(world))
assert sorted(block.exits) == ["failed", "out"]     # exactly ONE rail place
assert block.exits["failed"].color == FAILURE       # the unmodeled envelope

# and: a classify exit named "failed" with a DOMAIN color is refused
# fusion — "the rail carries what nobody modeled; classify carries
# what somebody did"
```

**For:** compiling yielded effects into places/transitions
(Interpretation B) died on evidence: generator frames are not durable
state, the net explodes in size, and the engine would own suspension
it cannot replay safely. Interpretation A — effects as values
interpreted transiently inside one activity, with a journal
(lookup-first idempotency, at-least-once per effect) and *typed
outcomes* (`Applied / AlreadyApplied / Stale / Exhausted`) as the
activity's declared exits — keeps durability where the History already
is.

**Against:** journal limits are real (64 KiB heartbeat cap, one
exclusive slot, AX9); at-least-once per effect means every effect must
be idempotent or classified (the two idempotency kinds the Navigator
named: "did it before → skip" and "did it before → now it fails →
classify as already-done").

### R6 — Ship the two operational surfaces as general primitives: `first_motion` and `review`

**Confidence: High for the mechanisms; the defaults are open
decisions** (AX28, AX27).

The fact — the entire infrastructure surface of a complete authoring
file (`ax28_one_file.py`, output verbatim):

```python
motion = first_motion(order_workflow(), {"sku": "sku-1", "amount": 10.0},
                      net_name="order", instance="order-1")
```

```text
net definition: 5732 canonical bytes
history records: 39
exits: {'settled': [{'sku': 'sku-1', 'total': 12.0}], 'review': []}
replay: rebuilt marking matches, place by place
```

The measured burden it removes: 33 hand-composed `Engine.create` sites
across 22 spike files, ~8 infrastructure names each — none carrying
workflow meaning. The same unchanged harness drove a
linear+parallel+branching net *and* a cyclic retry net.

The fact — generated authoring needs no new authority
(`ax27_review.py`): `review(name, source)` is total (every candidate
becomes structured `Feedback`), all ten characteristic generator
mistakes are refused at their expected stage, **five of ten messages
carry the concrete fix verbatim** (`its exits are ['out']` — pinned as
a counted test), the repair-loop test closes mechanically from the
message alone, and with `Engine` monkeypatch-poisoned, review still
succeeds — it provably cannot execute the net.

**For:** these close the two DX gaps the governing target named — one
file to first motion, and a deterministic feedback loop for
machine-generated authoring — with zero changes to kernel, algebra, or
runtime, and without hiding a single durable artifact (`Motion`
exposes definition bytes, History records, and replay; `store_defaulted`
labels the in-memory default instead of faking durability).

**Against:** the run surface has a known bounded gap (dispatched
Activity leaves need dispatch bindings, AX21 territory — not built);
review's trust contract is real (reviewing authoring source *is*
executing Python; the pyright stage is the no-execution alternative);
and a generation loop that stops at review is incomplete by
construction — two residue mistake classes are catchable only at the
opt-in motion stage.

### R7 — Migrate fragment-at-a-time with oracle parity; never big-bang

**Confidence: High** (AX11/AX13/AX15 pattern; AX14; AX17).

The fact — the parity proof pattern used three times against real
production fragments (`test_ax18_kernel.py` shows the determinism
half):

```python
direct = compile_fragment(conversation_intents_with_change())
via_kernel = compile_via_kernel(conversation_intents_with_change())
assert definition_bytes(via_kernel.built.net) == definition_bytes(direct.built.net)
```

Re-author one production concern as blocks; prove token-for-token
equality against the production net on the same scenarios; compose
concerns by explicit named-port identity (AX14); evolve the live net
by superset under the same name with one durable History across
compositions (AX17). No step requires a Petrus change; no step is
irreversible; the separable minimum (R4 alone) is available if
everything else is deferred.

**Against:** superset-only evolution is the safe lane; *narrowing* a
net needs a whole-trace preflight that was shaped (AX17) but never
built — a real gap to close before any narrowing migration.

---

## B. What not to build

Each of these was tried or seriously costed, and killed by evidence.
Full records in [lens 2](02-what-did-not-work.md); the two most
tempting are quoted so the temptation dies here.

**B1 — Context-manager / generator workflow builders (AX10).** The
most natural-looking spellings, and both rejected:

```python
# REJECTED — structure lives in a mutable scope stack and statement
# order; flow.do() returns None, so types see nothing; misuse is
# detectable only at runtime; nothing serializes until build()
with flow.parallel():
    with flow.branch():
        flow.do("reserve_inventory")
```

The expression must *be* the AST — values, not statement effects.

**B2 — Effects compiled into net structure (AX9, Interpretation B).**
Generator frames as durable state, net-size explosion, engine-owned
suspension. See R5 — this is its mirror image.

**B3 — Lambda / Python-AST inspection for guards (AX6).** Unstable
across Python versions, unserializable, and the failure modes are
opaque. Explicit expression objects won on every criterion (R4).

**B4 — Implicit branching from union annotations, and type-only
topology (AX5, AX0/AX3/AX14).** `-> Approved | Rejected` does not
create a branch, and "find any place with this type" dies the moment
two places share a color — the frozen engine itself refuses it
(`parameter 'primary' (CreditReport) requires exactly one matching
input arc, found 2`), and AX14 made the rule structural: composition
merges places only on explicitly declared matching port names, never
on color equality. Combinators define topology; types validate
compatibility — never identity.

**B5 — The "less code" pitch (AX11).** Measured false (113 vs ~95
lines). Selling brevity would set the adoption argument up to fail;
the honest pitch is safety, explicit policy, amortization (R1).

**B6 — A generation loop that stops at pre-motion review (AX27).**
Two residue mistake classes pass every static and review stage; the
loop must include opt-in motion or it is incomplete by construction.

---

## C. Conclusions the series is entitled to

1. **The frozen runtime is sufficient.** Thirty experiments, every
   combinator, every surface, both descent depths — zero Petrus
   changes needed or made. The authoring model is adoptable without
   touching the engine (every engine speculation stayed in the
   [ledger](../petrus-speculation.md)).
2. **The unit of composition is the block, not the workflow AST.**
   One typed entry, named typed exits, purity metadata, composed by
   port fusion — the Navigator's "control statements may only call
   functions" intuition, made structural and proven against
   production oracles.
3. **Validation is layered, and every layer earned its keep:** editor
   (pyright, 8/9) → eager `CompositionError` (call-site, with the fix
   in the message) → `check_sound` (net-level, the descent safety
   net) → bounded motion (the only stage that can catch data-driven
   residue). Each layer caught bugs the others missed, in the spikes
   themselves.
4. **Determinism is the load-bearing contract.** The Net is absent
   from History, so same source must produce a byte-identical net —
   asserted in every arc, and the reason replay, evolution, and
   generated authoring all work.
5. **The DX target is met by the evidence so far:** one file to first
   motion with one infrastructure name (AX28); deterministic
   repair-grade feedback for generated authoring (AX27); governed
   descent for unusual semantics (AX29) — all as *general* primitives,
   none Hamsterdan-shaped.
6. **What was disproven matters as much:** builders that hide
   structure in statement order, effects as net structure, type-only
   wiring, lambda inspection, brevity as the pitch — each has a
   recorded corpse with the evidence that killed it, so none needs
   re-litigating.

## D. Decisions only the Navigator can make

The evidence narrows these; it cannot settle them.

| # | Decision | The options the evidence supports | Where the evidence sits |
|---|---|---|---|
| D1 | **Default authoring spelling** for production authors | L2 algebra (`then`/`par`/`classify`); L3 typed façade (`t_then`/`t_par2`, editor-checked); L4 domain sugar (AX11's scatter/fold words) — or L3-over-L2 with sugar reserved | Spec §8; AX22–AX26; lens 1 arcs 2–3 |
| D2 | **Run-surface ownership** — where `first_motion` lives (authoring package beside the compiler vs host runtime) and what its production name is | Either placement works; the harness has zero workflow knowledge | AX28 |
| D3 | **The store default** — in-memory-with-label (current), demand an explicit store, or default durable | `store_defaulted` makes the current choice honest but still a choice | AX28 findings |
| D4 | **Live observation** — whether watching a running net belongs in ES-003's scope or elsewhere | Untested either way; deliberately not probed | Tabled at the governing target |
| D5 | **The descent adapter** — supported re-wrap of a spliced boundary net back to `Block` (with `first_motion` restored), or keep below-block descent honestly manual | Two-depth law proven; re-wrap deliberately unbuilt | AX29 |
| D6 | **Overlapping-guard policy default** — ordered priority (current spike), refuse overlap, or expose Petri nondeterminism as opt-in | All three implementable; ordered priority is what the spike ships | AX6 |
| D7 | **CI type-checker** — adopt pyright for the authoring surface (8/9), keep ty-only (4/9 today), or run both | Catch matrix pinned; repo CI currently runs ty | AX26 |
| D8 | **Sugar vocabulary** — whether Hamsterdan gets domain words (scatter/fold/…) above the general algebra, and who owns them | Amortization proven for vocabulary, not adjectives | AX11/AX13; generality ruling |
| D9 | **Productization itself** — whether any of this leaves the exploration: which recommendation set (R1–R7), in what order, under what roadmap item | This document is the input to that conversation, not its output | Everything above |

---

*Written 2026-08-13, at the close of AX29, over 599 passing
exploration tests and the pinned Petrus baseline
`3b41f19aa68ed228e68324f7c6888371f805b560`. Supersedes nothing;
extends the synthesis. The next move is the Navigator's.*
