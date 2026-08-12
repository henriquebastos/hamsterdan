# AX19 — Kernel boundary: the stated non-coverage, proven additive

**Status:** complete — Promising; continue.
**Question:** AX18 closed claiming its non-coverage — arc weights,
per-arc CEL filters, inhibitor arcs, timers, external delivery — is
"additive fields, not redesigns." Is that true on the frozen runtime?

**Hypothesis:** Each feature is one new field on `KernelArc` or
`KernelTransition` (or, for delivery, no field at all), lowered
verbatim onto what the frozen `ArcSpec`/`TransitionSpec` already carry,
and honored by the frozen engine.

## What was built

[ax19_kernel.py](ax19_kernel.py) restates the AX18 kernel with exactly
the additions ([test_ax19_boundary.py](test_ax19_boundary.py), ten
tests, every one executing the frozen `Engine`):

- **`weight`** on input arcs — multiplicity is *enabledness*: a
  weight-2 consume takes pairs and strands the odd token, with
  passthrough forwarding both moved tokens.
- **`Mode.INHIBIT`** — the frozen arc factory's third input
  inscription: one `Flag` token freezes the transition; the empty
  place enables it. This is the classic beyond-plain-PN feature, and it
  was already sitting in the frozen `_ArcFactory`.
- **`filter`** on input arcs — a rendered CEL string whose variable
  scope is the **token's own bare data fields** (frozen
  `compile_filter` contract), distinct from a guard's binding-wide
  place-name scope. A non-matching token is neither retired nor erred:
  it never binds. This is the "CEL filters on arcs" capability from the
  original project context, reached through the kernel for the first
  time in ES-003.
- **`timers`** — frozen `Delay`/`Until` carried verbatim on the
  transition. Finding worth recording: under `SimulatedClock` the
  coordinator *observes* the pending `next_maturation` when only timed
  work remains, so the clock jumps to maturity deterministically — a
  `Delay` gates the firing in **virtual time** (the firing is stamped
  at anchor+duration; `clock.now()` proves the jump), it does not park
  the token awaiting an external nudge. The no-timer contrast net fires
  at instant zero.
- **Source transitions and delivery** — a produce-only transition is
  recognized by frozen `Net.is_source`; it fires only through
  `engine.deliver(source, tokens, identity=...)`. Delivery identity
  deduplicates: the repeated identity returns a prior acknowledgement
  and lands nothing. The kernel's only duty is permitting the shape —
  delivery is an engine door, not net structure, and operation identity
  lives exactly where the project's at-least-once doctrine wants it.

One declaration-time refusal was added rather than a capability:
a **produce filter is rejected loudly** — frozen output arcs admit by
color only (the AX11 scatter finding), so a declared-but-ignored output
filter would be the worst kind of lie. The kernel now states the
asymmetry: admission intelligence exists on input arcs only.

## Consequence for the primitive inventory

The AX18 four-notion kernel extends to the full frozen surface with:

- `KernelArc(place, mode, weight=1, filter=None)`, mode gaining
  `INHIBIT`, filter forbidden on `PRODUCE`;
- `KernelTransition(..., timers=())`;
- no delivery primitive — sources are a *shape*, delivery is runtime.

Nothing in AX18's structure moved: places, transitions, work variants,
guard strings, declaration-order determinism, and the desugaring
pipeline are untouched. Remaining unexercised frozen surface, stated:
arc `color` inscriptions (narrowing admission below the place color),
weighted/filtered *read* and *inhibit* variants beyond weight 1,
`Until` at runtime (declared and carried, only `Delay` driven), token
selection policies, and lifecycle scopes on delivery. All are the same
kind of additive field; none threaten the layer.

## Verdict

**Promising; continue.** The kernel boundary claim survives contact
with the frozen runtime: every stated non-coverage feature lowered as
one field and executed unchanged. The primitive inventory for "any
Petri net this runtime can express" is now: named string-colored
places; transitions with ordered weighted/filtered
consume/read/inhibit/produce arcs; rendered CEL guards (place-name
scope) and filters (token-field scope); work ∈ {passthrough, Petri
handler, Motus activity}; timers; and deterministic declaration order —
with delivery, identity, scopes, and clocks belonging to the engine,
not the net.
