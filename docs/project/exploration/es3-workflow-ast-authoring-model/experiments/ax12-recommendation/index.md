# AX12 — Final architecture recommendation

- State: Completed, 2026-08-12.
- Question: given AX0–AX11, what architecture should Hamsterdan choose
  for authoring processes above the Petrus net — and what should it
  refuse to build?
- Nature: synthesis only. No new prototype; every claim below cites the
  experiment that proved it. This record is the evidence base for a
  Navigator decision, not a commitment to implement.
- Overall verdict on the ES-003 hypothesis: **Promising with changes.**
  The layered model works end-to-end on frozen Petrus (AX2, AX11), but
  the original economics claim must be corrected: for dense real
  fragments the DSL is *not shorter* (AX11: 113 vs 95 lines). The
  defensible case is eliminated callback registration, eliminated
  repeated wiring, construction-time whole-classes-of-error rejection,
  written-down implicit policy, and full source mapping — not brevity.

## 1. Recommended layer model

```text
Authoring   pure frozen combinator values (AX1/AX10) + typed predicate
            expressions (AX6) + typed ports (AX3/AX11)
AST         immutable tree; origin metadata non-identity; canonical
            form + fingerprint (AX1)
Compiler    deterministic lowering onto the existing NetSpec/BuiltNet
            surface; emits derived handlers, converters, and CEL; owns
            the source map (AX2, AX5–AX8, AX11)
Net         frozen petrus.impetus.petrinet schema + NetDefinitionV3;
            byte-identical on recompilation — the replay contract (AX0)
Runtime     unchanged Engine/Instance/History/Dispatch/Workers; zero
            Petrus modifications were needed in eleven experiments
```

The compiler is not only a topology generator: it emits the above-runtime
glue the experiments proved necessary — place-bound port handlers (AX3),
variant-discriminating converters and routing handlers (AX5, AX7),
synthesized scatter routers and fold/update plumbing (AX11). That glue is
generated, deterministic, and invisible to the author.

## 2. Smallest useful set of AST nodes

Core (proven individually AX1–AX8): `Step` (leaf wrapping an
`ActivityDefinition`), `Sequence`, `Parallel`, `Switch`/`Case` (type
branch), `Branch`/`When`/`otherwise` (guard branch), hybrid `Case`
(type + guard, AX7), `Retry` (the one cyclic node, AX8), and `Origin`
as universal non-identity metadata.

State-machine extension (AX11 — real Hamsterdan fragments are
long-lived state machines, not one-shot pipelines): `Port`/`StatePort`/
`ReadPort`, `Fragment` (entry + reads + states + body), `Scatter`/`Lane`,
`Choice` with mandatory gap policy, `Fold`, `Update`, `Retire`, and the
policy constants `WAIT`/`DROP`/`EXIT`. AX11 showed the core alone cannot
express `topology.py`'s dominant shape; the extension is not optional.

Not recommended without new evidence: `race` and `optional` combinators
(never prototyped), and any node whose semantics the author cannot see
in the generated net.

## 3. Smallest useful set of combinators

`sequence`, `parallel`, `switch(case…)`, `branch(when…, otherwise=…)`,
`hybrid(case(type, when=…, then=…)…)`, `retry`, and — for state-machine
fragments — `fragment`, `scatter(lane…, rest=…)`, `choice(case…,
otherwise=…)`, `fold`, `update`, `retire`. Composition covers the rest:
AX7 showed `switch`+`branch` nesting expresses hybrid routing (worse
surface, same semantics), so new combinators need to *earn* their place
by flattening something composition makes crooked.

## 4. Type and port model

- Colors stay nominal strings (`cls.__name__`) — frozen-runtime fact
  (AX0). The authoring layer compensates where nominal identity fails.
- Local inference from `@activity` resolved hints is safe and needs no
  new machinery: single input/output, multi-input with distinct colors,
  async, `-> None` as terminal sink signal (AX3).
- Refused at inference, with remedies: unions at `step()` (they mean
  branching — use `switch`/`hybrid`), generics (`list[X]` erases — wrap
  in a named dataclass), `None`-typed inputs (AX3).
- Same-color ambiguity is the port model's reason to exist: two places
  with one type are refused by the frozen typed derivation, and resolved
  only by **named ports** binding parameter names to place paths via a
  compiler-emitted place-bound handler (AX3). Port names are bare
  identifiers because CEL binding guards address places by variable name
  (AX11).
- Multiple logical outputs are one result dataclass, or `update(…,
  emits=(…))` for state+work production (AX3, AX11). Tuples are refused
  (identity erasure).

## 5. Guard-expression model

Explicit typed expression objects, never text, never source inspection:
`on(Application).score > 700` builds frozen predicate nodes (`FieldRef`,
`Compare`, `NullCheck`, `Membership`, `And`/`Or`/`Not`) validated
against the model at construction — unknown fields list alternatives,
constant type mismatches name both sides, optional fields demand a
left-conjunct null guard, `__bool__` raises so Python `and/or/not` fail
loudly (AX6). Lambda *tracing* over the same proxy is compatible sugar;
source/AST inspection is rejected (AX6). AX11 extended the same AST to
cross-root comparisons and map-key access with a mandatory presence
guard, compiling to binding-scoped transition guards. The ES-002 audit
bound the atom set: 45/48 production guards decompose into exactly these
atoms.

## 6. Does CEL remain the guard execution backend?

Yes — it becomes real for the first time. Production uses zero CEL
today (AX0); the experiments proved both CEL surfaces on the frozen
runtime: bare-variable **arc filters** for single-token routing
(AX6–AX8) and place-variable **transition guards** for multi-place
predicates (AX11). Both are durable in `NetDefinitionV3`, which Python
callables never were — history can finally *see* routing logic. Python
`typed_guard` remains the escape hatch for the two genuinely opaque
production atoms the audit found.

## 7. The role of Effect-oriented programming

Inside activities only — **Interpretation A** (AX9). A generator
activity yields frozen effect dataclasses; a transient worker-side
interpreter executes them, journaling completed effects through the
dispatch heartbeat-details channel so a crashed worker resumes
mid-program on the frozen runtime (proven: one `ReserveFunds` across a
crash). Generators are re-executed deterministic syntax; live frames
are never durable; divergence fails loudly. Interpretation B (effects
into topology) was built and rejected: 5× history, straight-line only,
types erased. Effects are an optional authoring convenience above the
activity boundary — not a foundation, and not a workflow layer.

## 8. Selected Python authoring syntax

Nested combinators are the semantic core and the default surface
(AX10): the source is the tree, constructors are fully typed,
refactoring is expression extraction, errors are positional. An
immutable fluent chain is permitted sugar for linear flows (it lowers
to identical nodes and forbids nothing). Rejected: context-manager
builders (mutable scope stack, statement-order structure, `None`-typed
calls) and generator workflow builders (handles cannot branch, loops
unroll). Generator syntax lives only inside activities (§7).

## 9. What remains explicit

Port names and every place identity; branch cases and their bodies;
gap policies (`otherwise=`, `rest=` — construction errors if omitted);
state ownership of every fold and update; work emission; retry limits
and the re-arm transform; the join (the downstream multi-input
activity's own transition — no hidden aggregator, AX4); variant
discrimination (`$variant` stamped durably, AX5).

## 10. What may be inferred safely

Colors from single unambiguous annotations; handler and converter
derivation; arc structure from `fold`/`update`/`reads` declarations
(consume/read/state loops); guard scope (which places a predicate
binds — including mechanical scope widening for ordered exclusivity,
recorded in the source map); the variant set from a union return;
exhaustiveness *validation* (never exhaustiveness silence).

## 11. What must never be inferred

Global type→place matching (AX3's mandated ambiguity case breaks it —
the frozen derivation itself refuses it); subclass routing (nominal
colors cannot represent it; refuse loudly, AX5); union identity across
the worker boundary without a durable discriminator (AX5); branching
from a union return alone (dead variant places; `switch` must state the
branch, AX5); unmatched-token policy (the runtime silently drops
produced orphans and silently parks unadmitted tokens — SP-4; policy
must be written); concurrency (driving-policy territory, not syntax,
AX4); cross-case correlation at joins (proven mispairing — instance-
per-case discipline, SP-3).

## 12. Validation and error-reporting strategy

Four stages, each failing before the next can hide the fault:
(1) **construction** — shape errors, predicate typing, totality,
overlap, null safety (AX5–AX7, AX11); (2) **lowering** — port
resolution, same-color ambiguity, undeclared-port predicates (AX11);
(3) **frozen Petrus bind** — typed derivation, CEL compilation,
structural net validation (AX0); (4) **runtime boundaries** — converters
and projections refuse forged variants, missing discriminators, and
unroutable results loudly rather than reaching the silent drop (AX5).
Error style is a contract: name the offense, list the alternatives,
spell the remedy (tested in every experiment; ten dedicated error tests
in AX11 alone).

## 13. Serialization and versioning strategy

The durable artifact remains `NetDefinitionV3` — the AST is not stored.
That works only because compilation is **byte-deterministic** (proven
AX2, AX11: identical serialized definitions across runs), since
`Instance.resume` demands the identical Net and history never carries
it (AX0). Version by fingerprint: the AST's origin-free canonical form
(AX1) plus compiler version identifies a compiled net; replay of an old
history requires the fingerprint-matching source and compiler. Changing
a workflow is therefore the same operation it is today — a new net for
new instances — and the AST layer adds a checkable identity where
hand-written topology has none.

## 14. Source mapping

Two-way and total: AST walk-path address ↔ generated `NetPath`/`NetUri`
↔ authoring `file:line` (`Origin` captured at construction, non-identity
metadata). Decisions that generate *no* element are still recorded —
`WAIT` parks, `EXIT` lanes, ordered-exclusivity scope widening (AX11) —
so a developer reading a runtime transition or a parked token can reach
the authoring line, and the absence of a transition is documented rather
than implied. `CompiledWorkflow.filters`/`source_map` expose the exact
CEL per element for debugging (AX6, AX11).

## 15. Migration strategy from the current DSL

No big bang; the two DSLs are not rivals at runtime because both produce
the same frozen net model.

1. Adopt the AX11 method as the migration instrument: author a fragment
   in the DSL, keep the hand-written topology as oracle, prove
   place-for-place parity on identical seeds, then let the compiled form
   own the fragment.
2. Start with new fragments (no oracle debt) and the fragments with the
   worst callback/wiring density.
3. Domain truth (contracts, folds, `operation`/`effect_payload`) is
   imported by the authored form, never re-authored (AX11) — migration
   moves expression, not semantics.
4. `topology.py` remains authoritative for unmigrated fragments
   indefinitely; the architecture contract (`readiness/net` owns
   decisions) is unchanged.
5. Only after several real fragments migrate should any production
   compiler package exist; until then the spike layout is the reference
   implementation.

## 16. Rejected alternatives and why

- **Universal-combinator regeneration** (ES-002): domain vocabulary
  masqueraded as structure; negative economics; prior art binding this
  series.
- **Context-manager builder** (AX10): structure from mutable statement
  order; runtime-only misuse detection; untypeable.
- **Generator workflow builder** (AX10): symbolic handles refuse `if`;
  Python loops unroll — cycles need `retry` anyway.
- **Lambda source/AST inspection** (AX6): exists only to rescue
  `and/or/not`; costs source availability, serialization, stable
  mapping. Tracing over the typed proxy delivers the sugar without it.
- **Structural (untyped) guards** (AX7): trade compile errors for
  parked tokens; the color-first admission gate is what makes typed
  narrowing sound.
- **Implicit type-branching from union returns** (AX5): can only create
  dead variant places; the union triggers and validates, `switch`
  states.
- **Input-side XOR lowering for `switch`** (AX5): works, buys nothing
  over projection routing, leaves the decision place untyped — recorded
  fallback.
- **Effects as net structure** (AX9-B): 5× history, straight-line only,
  type erasure.
- **Raw overlapping guards as authoring surface** (AX6): legal Petri
  nondeterminism remains available as plain Petrus, but `branch()`
  compiles ordered-exclusive; nondeterministic routing must be chosen
  by dropping to the lower layer, never stumbled into.

## 17. Open technical risks

- **Nominal colors** (SP-1): unions and generics are compensated above
  the runtime with converters and wrappers; real type binding would
  simplify the compiler but is Petrus-lane work.
- **Silent drop / silent park** (SP-4): the compiler closes both
  surfaces for generated nets; hand-written nets and future compilers
  remain exposed. An opt-in strict routing mode is the recorded
  speculation.
- **Join correlation** (SP-3): instance-per-case discipline is a
  convention, not a mechanism; multi-case instances would need
  compiler-stamped correlation keys plus a `SelectionPolicy`.
- **No durable timers** (SP-5): retry *pacing* (backoff) is
  inexpressible durably; AX8's retry is bounded but immediate.
- **Effect checkpoint channel** (SP-6): 64 KiB cap, slot exclusivity,
  and `DerivedActivityHandler`'s hard-coded `ExecutionPolicy()` gate
  real multi-attempt resume.
- **Ordered-exclusive filter growth**: linear in case position; fine at
  workflow scale, worth watching for wide branches.
- **Pool FIFO fairness** (AX7) under mixed-color load: untested.
- **The economics risk**: AX11's LOC parity means adoption sold as
  "less code" will disappoint. The case is safety, explicitness, and
  traceability; if the Navigator does not value those over brevity,
  the correct decision is to keep the current DSL and adopt only the
  predicate AST (§5–6), which is separable and pays for itself.
