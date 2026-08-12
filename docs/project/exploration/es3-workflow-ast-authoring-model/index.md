---
status: Thickening
opened: 2026-08-11
navigator: Henrique
---

# ES-003 — Workflow AST authoring model compiled to the Petri net

## Inquiry

Can the current low-level Petrus DSL become an internal representation,
with processes authored through a higher-level embedded Python DSL — and
what is the right layered architecture if so?

```text
Activities describe work.
Combinators describe process structure.
The Python DSL constructs a workflow AST.
A compiler lowers the AST into the existing Petri-net representation.
The existing event-sourced runtime, dispatcher, and workers execute it.
```

In this model activities are AST leaves, combinators are internal nodes
defining topology, types validate compatibility and support local
inference (never sufficient identity for topology), guards may be Python
expression objects compiled to the existing CEL representation, and
effect-oriented or generator-based activity syntax is a separate
hypothesis to test — not an assumed foundation.

## Relation to ES-002

ES-002 asked how the existing readiness workflow should be written down
and answered by regeneration: its combinator experiment closed with the
universal-combinator approach rejected — the 14 fragment families were
domain vocabulary, the economics negative for a single net, and the real
pain was binding plumbing (since fixed at the right layer by
RS-014–RS-017). ES-003 tests a different hypothesis: an authoring-forward
workflow AST as intermediate representation, evaluated by design
experiments rather than by regenerating the hand-written topology.
ES-002's evidence binds this story as prior art: the guard decomposition
audit (45/48 guards decidable over four atom kinds), the
smallest-existing-expression rule, and the prohibition on live
continuation state.

## Method — experiment series AX

The story runs as a sequence of small, isolated, reversible design
experiments, AX0–AX12, each answering one stated design question with the
smallest useful prototype and a recorded verdict before the next begins.
Program, rules, and status: [experiments/index.md](experiments/index.md).
All records and spike code live inside this directory; production
`topology.py` is never modified and remains the comparison oracle.

## Navigator rulings — 2026-08-11

- The entire investigation is exploration work with every artifact inside
  this exploration directory.
- Petrus is frozen at the pinned baseline
  `3b41f19aa68ed228e68324f7c6888371f805b560` for all experiments.
  Speculation about Petrus runtime changes — for example binding real
  types instead of nominal color strings — is welcome as a dependent
  analysis result and accumulates in the
  [Petrus speculation ledger](petrus-speculation.md), never inside an
  experiment's implementation.
- Literature, authors, and named concepts grounding the AX findings —
  structured programming, workflow-net soundness, structured
  concurrency, applicative/selective/arrow composition, effects as
  values, linear logic, idempotency doctrine, and net metrics —
  accumulate in the [theory reference ledger](theory-references.md)
  (Navigator direction 2026-08-12) so future digging starts from names,
  not memory.

## Progress

- [AX0 — Architecture map and baseline example](experiments/ax0-architecture-map/index.md)
  completed 2026-08-11. Verified the architecture map against the pinned
  checkout; corrected the working premise (nominal string colors with no
  class registry; CEL present but unused by the production net;
  activities dispatched by occurrence ID with frozen results; the Net
  absent from History, so any compiler must be deterministic for replay);
  selected the actions failure → rerun-or-repair fragment
  (`topology.py` L1461–1476 plus its two activity bridges) as the
  baseline example for AX1–AX11.
- [AX1 — Minimal workflow AST](experiments/ax1-minimal-ast/index.md)
  completed 2026-08-11 — Promising; continue. Three frozen nodes
  (`Activity`/`Sequence`/`Parallel`) with structural identity, origin as
  non-identity metadata, deterministic walk paths as `NetPath` seeds, and
  an origin-free canonical form + fingerprint for compile-determinism
  checks. Fourteen tests pass. Honest gap carried to AX2/AX3: the AST
  omits exactly the data semantics (colors, transforms, join meaning)
  the current DSL forces you to write.
- [AX2 — Lowering Activity and Sequence onto the frozen Net](experiments/ax2-lower-sequence/index.md)
  completed 2026-08-11 — Promising; continue. The lowering contract is a
  threaded fragment (entry place in, exit place out; `Sequence` owns
  nothing). The ~200-line compiler produces nets byte-identical to the
  hand-written DSL equivalent, executes unmodified through
  `Engine`/`InlineDispatch`, replays over a recompiled net, fails loudly
  against divergent compilation, and carries a two-way source map
  (AST address ↔ generated paths ↔ authoring line). Duplicate activity
  occurrences bind safely by exact handler `NetUri`. Ten tests pass.
  AX3 next: derive colors from typed signatures instead of explicit
  `request=`/`result=` declarations.
- [AX3 — Typed activities, ports, and basic inference](experiments/ax3-typed-ports/index.md)
  completed 2026-08-11 — Promising; continue. `@activity` definitions
  already carry resolved hints, so inference needs no new machinery;
  single in/out, multi-input with distinct colors, sinks (as a signal),
  and async infer safely, while unions, optionals, and generics are
  refused with reasons and remedies. The mandated same-type-two-places
  case is refused loudly by the frozen derivation and resolved by a
  ~60-line place-bound port handler above the runtime — named ports need
  no Petrus change. Sink probe recorded as ledger SP-2. Fourteen tests
  pass.
- [AX4 — Parallel split, execution, join](experiments/ax4-parallel-join/index.md)
  completed 2026-08-11 — Promising; continue. The lowering contract
  generalizes to place sets; the split is an explicit `passthrough`
  transition and the join is the downstream multi-input activity's own
  transition — no hidden aggregator. Key findings: concurrency is
  driving-policy territory (`choose_conservative` serializes,
  `choose_throughput` parallelizes) so the authoring layer needs no
  concurrency syntax; terminal branch failure halts loud, poisons the
  Engine, and resumes via `Engine.load` with the sibling's result
  durably parked; a `-> None` branch terminates but cannot feed a join;
  and the cross-case join mispairing hazard was *proven* by crossed
  completions (ledger SP-3) — instance-per-case discipline, not types,
  provides correlation. Twelve tests pass.
- [AX5 — Branching by output type](experiments/ax5-type-branching/index.md)
  completed 2026-08-11 — Promising; continue. The runtime routes tokens
  by color through typed arcs natively — but silently drops what no arc
  admits, and union variant identity is erased at the worker boundary
  today. Both gaps close above the frozen runtime: a
  `VariantPayloadConverter` stamps a durable `$variant` discriminator
  (refusing subclasses and unlisted types loudly), and a routing handler
  projects to exactly the matching variant place. Branching is explicit
  (`switch`/`case`), with the union return as trigger and exhaustiveness
  validator; same-color case exits get an explicit XOR merge. Ledger:
  SP-1 evidence extended, SP-4 (strict routing mode) added. Nineteen
  tests pass.
- [AX6 — Guard-based branching with a single data type](experiments/ax6-guard-branching/index.md)
  completed 2026-08-11 — Promising; continue. A typed root proxy
  (`on(Application)`) builds a frozen predicate AST via operator
  overloading, validated against the dataclass at construction (unknown
  fields, constant type mismatches, unguarded optional fields all fail
  with remedies) and compiled to the bare-variable CEL dialect Petrus
  filters evaluate. Overlap policy decided explicitly: cases lower
  ordered-exclusive (each conjoined with prior negations) so first match
  wins deterministically on the frozen runtime, and `otherwise` is
  mandatory because a token no input arc admits parks silently. Input
  arcs proved to be competition, not duplication — the mirror of AX5's
  output-side drop (SP-4 extended). Lambda *tracing* works as sugar over
  the same objects; source inspection rejected. Thirty-five tests pass.
- [AX7 — Hybrid type + guard routing](experiments/ax7-hybrid-routing/index.md)
  completed 2026-08-11 — Promising; continue. `hybrid()` fuses switch
  and branch: each `case(Approved, when=on(Approved).risk < 20, then=…)`
  lowers to one arc carrying *both* a color and a filter off an untyped
  pool place. The decisive frozen-runtime fact: `enabledness.admitted`
  gates on color **before** evaluating the filter, so a guard over the
  narrowed variant's fields can never raise on other variants — proven
  by running the Rejected route with warnings-as-errors. Guards stay
  rooted in declared types (structural guards rejected: they trade
  compile errors for parked tokens); totality is two-level — every
  variant covered, and per variant exactly one unguarded default, last.
  Fifteen tests pass.
- [AX8 — Loops, cycles, retries](experiments/ax8-loops-retries/index.md)
  completed 2026-08-11 — Promising; continue. The authoring AST stays a
  tree; `retry(...)` lowers to a net with exactly one loop-back arc.
  Retry state is durable token data (the retryable variant carries
  `attempt`), the retry guard compiles to CEL (`attempt < limit`), and
  retry/exhausted are complementary filtered arcs so no token parks.
  Re-arming is an explicit pure typed transform (retryable variant →
  original request) feeding the loop entry — workflow-level retry,
  distinct from worker retry. Bounded-ness comes from the durable
  counter, not a runtime loop detector; replay over the cyclic net
  works unchanged. The frozen runtime has no timer/delay primitive, so
  backoff is inexpressible durably (ledger SP-5). Fifteen tests pass.
- [AX9 — Effect-oriented activity authoring](experiments/ax9-effect-authoring/index.md)
  completed 2026-08-12 — Promising with changes: **Interpretation A
  only**. Effects are frozen dataclass values a generator activity
  yields; a worker-side interpreter journals each completed effect into
  the frozen dispatch's heartbeat-details channel, which
  `LocalWorkerDispatch.claim` durably hands to the next attempt — a
  crashed worker resumed mid-program with zero Petrus changes (proven:
  `ReserveFunds` performed once across a retried attempt). The net sees
  one activity; generators are re-executed deterministic syntax, never
  durable frames; divergence fails loudly. Interpretation B (tracing
  effects into net structure) was built and rejected: straight-line
  only, 5 transitions/history pairs where A needs 1, and every
  intermediate place erased to an untyped `dict`. Ledger SP-6 records
  the checkpoint-channel constraints (64 KiB cap, slot exclusivity,
  policy plumbing). Twelve tests pass.
- [AX10 — Python authoring-style comparison](experiments/ax10-authoring-styles/index.md)
  completed 2026-08-12 — Promising; continue. Four spellings were forced
  to produce one canonical AST on a genuinely nested example. Nested
  combinators remain the core and default surface (typed constructors,
  positional error messages, refactor-by-expression). An immutable
  fluent chain is permitted sugar for linear flows — the probe shows it
  degenerates to nested combinator expressions at the first multi-step
  branch. Context-manager builders are rejected (mutable scope stack,
  statement-order structure, `None`-typed calls, runtime-only misuse
  detection). Generator builders are rejected for structure: handles
  refuse `if` (the AX9-B boundary re-proven at this layer) and Python
  loops merely unroll — generators stay inside activities (AX9-A).
  Sixteen tests pass.
- [AX11 — Leading design on a real production fragment](experiments/ax11-real-fragment/index.md)
  completed 2026-08-12 — Promising; continue. The real conversation-intent
  fragment of `topology.py` (classification bridge, `unpack_intents`
  scatter, the `accept_*_intent` folds, `authorize_reply`, and the
  `reply_basis` retire) was authored as ports + scatter lanes + guarded
  choices + typed folds/updates, importing production domain truth
  (`fold_intent`, `operation`, `effect_payload`, the strict contracts)
  rather than re-authoring it. The compiled net matches the
  production-style oracle place-for-place across five scenarios on
  frozen Petrus (11 places, 6 identically named transitions; 23 vs 22
  arcs — one visible read-arc from mechanical ordered-exclusivity scope
  widening the source map records). Replay over a recompiled net works;
  compilation is byte-deterministic. Honest findings: the fragment's
  concurrency is scatter concurrency, not AX4 AND-parallel (reported as
  such); authored LOC is slightly *higher* (113 vs 95) because implicit
  policy (`WAIT` parks, `rest=DROP`) must be written down — the gains
  are zero separately registered callbacks, no repeated read/state
  wiring, construction-time overlap/gap/shape/type errors, and full
  transition→source-line mapping. Twenty-two tests pass.
- [AX12 — Final architecture recommendation](experiments/ax12-recommendation/index.md)
  completed 2026-08-12 — series verdict: **Promising with changes**.
  Synthesis only, every claim cited to its experiment: layered model
  (pure combinator AST → deterministic compiler emitting nets *and*
  above-runtime glue → unchanged frozen Petrus); core + state-machine
  node sets; named ports over nominal colors; typed predicate AST with
  CEL as the now-proven guard backend; effects inside activities only
  (AX9-A); nested combinators as default surface with an immutable
  fluent façade permitted. The corrected economics claim is central:
  the DSL does not shrink dense fragments (AX11) — its case is zero
  callback registration, written-down implicit policy, construction-time
  error classes, and total source mapping. Migration is oracle-parity
  fragment-at-a-time; the separable minimum adoption is the predicate
  AST + CEL guards alone. Seventeen sections; open risks tied to ledger
  entries SP-1–SP-6. Standing note (Navigator, 2026-08-12): AX12 is a
  synthesis *snapshot* — the goal remains exploration and variation;
  the story is retold and decided only after the variations run.
- [AX13 — Sibling amortization](experiments/ax13-sibling-amortization/index.md)
  completed 2026-08-12 — Promising; continue. The variation attacking
  AX11's LOC-parity finding: growing the real change-intent concern
  (`_mutation`/`_authorize_change`/`change_basis` retire) onto the AX11
  fragment costs 32 authored lines vs 38 production lines, zero new
  handler registrations (production adds two), no repeated wiring, and
  identical marginal net growth (+2/+2/+8 both sides — no widening this
  time, since `~MUTATION`'s roots cover its predecessor's). The
  economics flip at the second sibling: the first fragment pays the
  vocabulary, siblings reuse it. Bonus property proven: fragments are
  values — `dataclasses.replace` surgery on AX11's committed AST equals
  the restated fragment and compiles byte-identically. No compiler
  changes were needed to absorb the new concern. Eleven tests pass.
- [AX14 — Fragment composition](experiments/ax14-fragment-composition/index.md)
  completed 2026-08-12 — Promising; continue. The variation attacking
  AX13's remaining constraint: sibling growth still restated (or
  surgically transformed) the base AST. Concerns can instead be
  independent fragment values composed by explicit named-port identity:
  `compose(name, *fragments)` lowers fragments in argument order into
  one shared spec, merging places only where port *names* coincide and
  refusing loudly when a shared name disagrees in color or kind — while
  same-color/different-name ports stay distinct (AX3's ruling survives
  composition). The one AST addition is `handoff_fragment` (an entry
  adjudicated by a guarded choice — the shape every consumer of an
  `EXIT` lane takes); it reuses AX11's lane-choice lowering verbatim.
  The oracle is exact: AX11's untouched base composed with the change
  concern serializes byte-for-byte identical to AX13's restated
  monolith, and both source fragments remain untouched values. Fragment
  order is explicit and part of the definition (reversal preserves the
  element sets but permutes arc positions). Cross-file source mapping
  survives the seam. No runtime or ledger impact. Eighteen tests pass.
- [AX15 — Recovery concern](experiments/ax15-recovery-concern/index.md)
  completed 2026-08-12 — Promising; continue. Production's hardest
  routing decision (`_recoverable_publication`: five tokens, open-map
  arguments, a nested optional recovery request identity-matched
  against the current authority, three targets, hand-built complement
  retire) authored as a third composed hand-off concern — with **zero**
  compiler or AST growth. Behavior matches a verbatim production oracle
  across all recovery scenarios, including a run where recovery
  unblocks a parked reply through the shared emit seam. Per-target
  predicate specialization beats production's read-everything wiring
  (54 vs 56 arcs) while the generated `otherwise` reproduces
  `reject_recovery`'s exact scope mechanically. Chief discovery: celpy
  has no `!= null` overload for struct values — the presence rendering
  in the shared AX11 predicate module now emits `!(x == null)`, proven
  by regression tests on Petrus's own `compile_guard` path (committed
  byte-parity evidence unaffected). Two `validate_null_safety` holes
  are demonstrated and recorded as refinements: child refs do not
  inherit parent optionality, and right-hand comparison operands escape
  checking. Twenty-two tests pass.
- [AX16 — Null-safety validation](experiments/ax16-null-safety-validation/index.md)
  completed 2026-08-12 — Promising; continue. AX15's "conjoin
  `.present()` *before* nested reads" author obligation is replaced by
  a validator — and revised: celpy implements CEL's commutative,
  error-absorbing logic (`error && false == false` in both orders,
  proven on Petrus's own `compile_guard` path), so guard soundness is
  **sibling membership, not position** — a risky read is safe iff some
  conjunct anywhere in the same all-of is false whenever the path is
  absent, dually for any-of (`.is_null()`; `.present()` has the wrong
  polarity there and secures nothing). `validate_guard(predicate,
  *root_types)` recomputes risk points from the root dataclasses —
  closing v1's three holes: inherited parent optionality, both
  comparison sides, order-dependence — validates AX15's real recovery
  guards clean, and catches the variant with its presence conjunct
  removed. Second finding: the two evaluators disagree — celpy equality
  on a null leaf is total while `holds()` crashes with a raw
  `TypeError` on the identical predicate, so the conservative refusal
  stays until the evaluators align (refinements recorded). No shared or
  production modules changed. Twenty-one tests pass.
- [AX17 — Net evolution](experiments/ax17-net-evolution/index.md)
  completed 2026-08-12 — Promising; continue. The adoption path for
  fragment composition, tested as a generic runtime question: one
  durable history, two same-name compositions (base+change vs
  base+change+recovery), real engines over one store. Five rules: the
  net name is the process identity (a renamed structural twin is a
  foreign trace, so version cannot live in the name); superset resume
  is total and zero-migration (one `Engine.load`, old places replay
  identically, new places arrive empty); a token parked on a hand-off
  place before the consuming concern existed is consumed after
  evolution — WAIT + composition = deferred capability; an unseeded
  state place starves the joined concern visibly (and its generated
  `otherwise` with it), making minimal guard scope a *compatibility*
  property, not just an economy — `recover_conversation`'s inputs
  prove ⊆ the narrow net's places, `recover_dashboard`'s prove not;
  and narrowing audits live state only — ended firings of removed
  transitions resume silently (Petrus's documented posture), so
  concern removal needs an authoring-layer preflight, not runtime
  trust. Eight tests pass.
- [AX18 — Generic kernel](experiments/ax18-generic-kernel/index.md)
  completed 2026-08-12 — Promising; continue. The primitive question,
  answered structurally: a four-notion net-agnostic IR — named
  string-colored places (name is identity and CEL variable), transitions
  with ordered consume/read/produce arcs, rendered CEL guard strings,
  and work ∈ {passthrough, Petri handler, Motus activity} — is complete
  for the frozen runtime. A hand-authored neutral net (same-color place
  pair, marking-bounded cycle, read-arc-guarded competition, no handlers,
  no Python types) runs unchanged on the frozen Engine; and the full
  AX13 fragment desugared through the kernel serializes **byte-identical**
  to the AX11 compiler's output with identical source attribution — so
  fragment/scatter/choice/fold/update/retire are proven sugar, every
  domain decision ending before the kernel. One honest loss: policy-only
  source-map rows (WAIT/EXIT) have no kernel home — that asymmetry is
  the layer boundary. Stated non-coverage: arc weights, arc filters,
  inhibitors, timers, delivery — additive fields, not redesigns.
  Seventeen tests pass.
- [AX19 — Kernel boundary](experiments/ax19-kernel-boundary/index.md)
  completed 2026-08-12 — Promising; continue. AX18's non-coverage
  claim, proven on the frozen engine: weight (enabledness multiplicity:
  pairs move, the odd token strands), inhibit (one flag token freezes
  the transition), per-arc CEL filters (token-field scope, distinct
  from guard place-name scope; non-matching tokens never bind), timers
  (a `Delay` gates in *virtual* time — the coordinator observes
  `next_maturation` and the SimulatedClock jumps to maturity, stamping
  the firing at anchor+duration), and source-transition delivery with
  identity dedup (a shape plus an engine door, not a net primitive).
  Each landed as one field on `KernelArc`/`KernelTransition`; nothing
  in AX18 moved. One refusal added: a produce filter is rejected at
  declaration because frozen output arcs admit by color only — a
  declared-but-ignored filter would lie. Ten tests pass.
- [AX20 — Function-like subnets](experiments/ax20-function-subnet/index.md)
  completed 2026-08-12 — Promising; continue. The Navigator's diagnosis
  (control places as global state smear guards across the net) answered
  with a function-call shape on the frozen engine: entry routes by
  per-token arc filter and *consumes* the concern's state token — a
  structural mutex, no `change_in_flight` flag anywhere in the
  serialized net; the interior is a guardless linear pipe reading no
  shared state; two complementary exit guards fence the moving
  authority exactly once — commit emits the effect and releases the
  state updated, discard throws the whole run away and releases it
  unchanged, with restart being a fresh submit through the same door.
  Entry blindness collapses "stale at entry" and "moved mid-flight"
  into one fence-judged case, under the stated contract that inputs
  carry the authority coordinates they were issued under. Soundness
  tested, not asserted: no interior marking survives either terminal
  path; the state token is conserved; replay reaches the same marking.
  Boundaries stated: the fence is atomic with effect *emission* only
  (external effects keep their own current-authority fencing); the
  interior must stay pure; the claim serializes the concern. Fifteen
  tests pass.
- [AX21 — Typed effect outcomes](experiments/ax21-effect-outcomes/index.md)
  completed 2026-08-12 — Promising; continue. The Navigator's two
  idempotencies proven as two different net mechanisms at two different
  locations: identity dedup at the delivery door (kind one), and
  lookup-first classification at the effect itself (kind two), whose
  answer is a **typed outcome routed by color** — `Applied |
  AlreadyApplied | Stale | Transient`, each a place, none an exception.
  "Already done" is adopted (a success wearing an error's clothes);
  "preconditions changed" routes to rejected and quiesces normally;
  only Transient loops, bounded by the AX20 complement discipline.
  Sharpest transferable rule: **lookup answers before preconditions** —
  an operation applied under an old base then redelivered is
  AlreadyApplied, not Stale. Replay resumes against a fresh fake ledger
  with zero invocations: recorded outcomes, not re-executed effects,
  drive resumption. The boundary is a function signature —
  `apply : Work → Done | Rejected | Exhausted` — ready for the
  composition layer. Twelve tests pass.
