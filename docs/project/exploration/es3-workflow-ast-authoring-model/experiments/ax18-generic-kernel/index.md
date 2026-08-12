# AX18 — Generic kernel: the net-agnostic IR beneath the domain sugar

**Status:** complete — Promising; continue.
**Question:** Can the AX11–AX17 domain vocabulary (`fragment`, `scatter`,
`choice`, `fold`, `update`, `retire`) be desugared into a small,
net-agnostic Petri-fragment kernel whose primitives expose the actual
place/transition/arc semantics — while preserving deterministic
generated nets and source mapping — and can that kernel alone express
arbitrary-net shapes the domain AST has no words for?

**Hypothesis:** The domain vocabulary is *sugar*, not semantics: every
decision it embodies can be made in a desugaring stage whose output is
only places, transitions, arcs, rendered guards, and ready handlers.

## The kernel IR

Four notions, all plain frozen data ([ax18_kernel.py](ax18_kernel.py)):

1. **`KernelPlace(name, color)`** — name is identity (an identifier,
   because it is the root-scope place path *and* the CEL guard
   variable); color is a **nominal string**. No Python type exists at
   this layer: `PlaceSpec` accepts string colors directly, and the
   neutral net runs with zero Python models.
2. **`KernelTransition(name, arcs, guard, work)`** — the guard is an
   already-**rendered CEL string** whose variable scope is the
   transition's consume/read place names. Predicate objects, null
   safety (AX16), scope resolution, and exclusivity chaining are all
   authoring-layer duties that end *before* the kernel.
3. **`KernelArc(place, mode)`** with mode ∈ `consume | read | produce`.
   Arc order is meaningful and preserved verbatim — it is the wiring
   order, and serialized arc positions follow it (AX14's finding).
4. **`Work`** — exactly the three things the frozen runtime
   distinguishes: `None` (Petrus default-binds pure `passthrough`),
   `PetriWork(handler)` (a ready binding→outputs closure), and
   `ActivityWork(definition)` (string declaration now,
   `DerivedActivityHandler` post-build, dispatched through Motus).

`kernel_net(name, *nodes)` validates shape (identifier names, unique
names, declared-before-use arc references, no arc-less transitions);
`lower_kernel` replays the declaration onto `NetSpec` making **no
decisions** — every decision already happened upstream.

## Evidence

Seventeen tests ([test_ax18_kernel.py](test_ax18_kernel.py)), three claims:

### 1. The kernel says things the domain AST cannot

[ax18_neutral.py](ax18_neutral.py) hand-authors a domain-free net with
two same-color `Slot` places shuttling one token around a **cycle**,
liveness bounded by a `fuel` marking (three `Pellet` tokens, one burned
per lap), a read-arc guard on `meter.enabled` deciding a two-way
competition for the same place, a disconnected place, and **no handler
anywhere**. The frozen `Engine` runs it unchanged: three laps then
quiescence; flipping the meter routes the token to `drain` instead and
the fuel survives. Passthrough semantics surfaced one kernel rule worth
stating: a consumed token with no color-admitting output arc is
**silently dropped** (frozen `route` documents this) — a consume
without a matching produce is a retire *for that color*.

### 2. The domain vocabulary is sugar — byte-for-byte

[ax18_desugar.py](ax18_desugar.py) restates the AX11 compiler's
decisions (port resolution with same-color refusal, guard scope,
ordered-exclusive chaining, scope widening, routing/step handler
synthesis) but emits only kernel nodes.
`lower_kernel(desugar_fragment(f))` serializes **byte-identical** to
`compile_fragment(f)` for the full AX13 fragment (13 places, 8
transitions, three concerns), with identical `places`, `generated_by`,
and per-address guard CEL — and the real change scenario lands
place-by-place identically on both engines.

What byte-identity actually required (the deterministic-compilation
contract, now explicit): relative place order = first-touch order in
the authoring walk; relative transition order = walk order; per-
transition arc order = read → consume → produce.

### 3. Source mapping survives — with one honest loss

The two-stage pipeline maps `authorize_change` back to its
`ax13_fragment.py` construction site with its rendered guard. But AX11
records **policy-only entries** (WAIT gap policies, EXIT lanes) as
transition-less source-map rows, and the kernel has no transition-less
notion to hang them on. That asymmetry *is* the layer boundary: policy
knowledge belongs to the authoring layer's map, structure attribution
to the kernel's.

## True primitives vs sugar (the deliverable)

**Net-agnostic primitives** (sufficient for everything AX11–AX17 built,
plus cycles, same-color pairs, handler-less nets):

- named colored place (string color; name = identity = CEL variable)
- transition with ordered consume/read/produce arcs
- rendered CEL guard over input-place names
- work ∈ {passthrough, Petri handler, Motus activity}
- deterministic declaration order (places, transitions, arcs)
- source attribution per transition

**Domain sugar** (real decisions, but all pre-kernel): typed ports and
type-based resolution, `scatter` routing synthesis, `choice`
exclusivity chaining and scope widening, `fold`/`update` handler
synthesis and state re-production, `retire`, WAIT/EXIT policies,
predicate objects and their null-safety validation.

**Arbitrary-net features the kernel does *not* yet cover** (boundary,
stated): arc weights/multiplicity > 1, arc-level filters and color
inscriptions (frozen `ArcSpec` has them; the IR doesn't expose them),
inhibitor arcs (`arc` factory suggests support), timers, source
transitions (no-input; kernel permits the shape but nothing exercises
delivery), token-selection policies, and completion semantics. Each is
an additive field on `KernelArc`/`KernelTransition`, not a redesign.

## Verdict

**Promising; continue.** The kernel earns its layer: it is the first
representation in ES-003 that is *complete for the runtime* rather than
complete for the domain — everything the frozen engine can execute has
a spelling, and everything the domain AST says compiles into it without
residue (byte-identical). It also cleanly separates the two failure
vocabularies: authoring errors (ambiguous types, unsafe predicates,
non-exclusive routing) end before the kernel; kernel errors are purely
structural. The recommendation (AX19+/final) should present the
architecture as **authoring vocabulary → kernel IR → frozen NetSpec**,
with the kernel as the stable seam where alternative authoring styles
(AX10) and net evolution preflights (AX17) plug in.
