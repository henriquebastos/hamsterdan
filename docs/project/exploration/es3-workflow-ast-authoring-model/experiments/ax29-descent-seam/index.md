# AX29 — The descent seam: mixing algebra blocks with kernel authoring

**Status:** complete — Promising; continue (with the two-depth law
below held as the seam's doctrine).
**Question:** the governing target promises progressive disclosure
*downward* too: advanced users descend to lower-level Petrus APIs when
they need unusual semantics. Does the descent actually compose? One
file mixing ordinary algebra blocks with hand-written kernel authoring
— does each level's validation still govern its level, or does the
escape hatch quietly weaken soundness checks and composition refusals?

**Hypothesis:** descent has two distinct depths with different laws,
and both stay governed. *In-block* descent — hand-built `Block`s whose
nodes use kernel vocabulary no combinator spells (arc filters,
weights, guards, timers) — remains fully owned by the algebra: eager
refusals, `check_sound`, `first_motion`. *Below-block* descent — the
one construct `check_sound` refuses inside a block, the inhibitor arc
— steps to the boundary-net level, where the kernel's own shape law
governs, and the block part is still checked first.

## What was built

[ax29_descent.py](ax29_descent.py) — one authoring file, both depths
side by side:

- **In-block descent:** `express_triage` is a `Block` built from raw
  `KernelPlace`/`BoundaryTransition` dataclasses using per-arc CEL
  filters (`amount < 100.0`) that route by value with *no handler at
  all* — declarative admission, the AX19 filter contract — and two
  same-colored exits, which `classify` refuses (its handler addresses
  outputs by color) but a filter-routed Block may mean.
  `order_triage` composes it with an ordinary `transform` leaf through
  the ordinary `then`.
- **Below-block descent:** `splice_throttle` fuses a
  dispatch-until-acknowledged throttle below the algebra: an inhibitor
  keeps `dispatch` disabled while `dispatched` holds an unacknowledged
  token, and acknowledgements arrive from outside through the engine's
  delivery door — an `acknowledge` *source* transition fired only by
  `Engine.deliver` with operation identity. The seam's law, in order:
  `check_sound` governs the block part first; `boundary_net`'s shape
  law (`KernelShapeError`) governs the union.

[test_ax29_descent.py](test_ax29_descent.py), thirteen tests on the
frozen engine.

## Findings

- **In-block descent stays completely governed.** The hand-built Block
  routes by value through kernel filters, composes through `then` with
  the same eager color refusals, is checked by `check_sound` (a
  stranded hand-written place is refused), and runs *and replays*
  through the unmodified `first_motion` — the AX28 harness needed
  zero changes for a descended block. Descent widens expression
  without leaving the algebra's jurisdiction.
- **The refusal boundary is exact and meaningful.** An inhibitor arc
  inside a `Block` is refused by `check_sound` ("inhibitor arcs are
  outside the block algebra") — inhibition is *non-flow*, so it would
  break what entry→exit reachability means. The same arc below the
  algebra is legal kernel authoring. The line between the two depths
  is a semantic law, not a missing feature.
- **The splice keeps every authority at its level.** A broken upstream
  block is refused by `CompositionError` before the splice exists; a
  splice transition referencing an undeclared place, or a splice place
  shadowing a block place, is refused by `KernelShapeError`. One
  namespace, two laws, no gaps — and no check was weakened to let the
  seam through.
- **The inhibitor's guarantee is observed, not assumed.** With the
  arc: exactly one order dispatched at quiescence, peak occupancy one
  across the whole acknowledged run. Without it (the same splice minus
  one arc — the experiment's counterfactual knob): both orders sit in
  `dispatched`. A first attempt showed why the counterfactual needs
  care: with a freely-firing confirm, the conservative driving policy
  drains `dispatched` inside the same advance and hides the
  difference — the throttle became observable only when confirmation
  required an external ack, which is also the realistic shape.
- **The delivery door works at the seam.** External acknowledgements
  fire the source transition through `Engine.deliver` with operation
  identity, each ack releases exactly one order, and replay over the
  same History — *including* the delivered tokens — rebuilds the
  marking place by place on a fresh lowering.
- **The run surface is honestly manual below the algebra.** A
  `LoweredBoundary` is not a `Block`: it has no entry/exit ports, so
  `first_motion` cannot drive it, and the test hand-composes
  `Engine.create`. That is the seam's real cost — descend below the
  algebra and you also descend below its conveniences. A future
  bounded question: whether a spliced net can be re-wrapped as a Block
  (declared ports over the union) to climb back up; not attempted
  here.

## Limits

- The splice composes at names (`upstream.exits[lane].place`); it is
  arrangement code an author writes, not new vocabulary — deliberately.
  Whether a blessed `splice` primitive belongs in the kernel layer is
  a product question, not proven need.
- Timers and weights were not re-exercised here (AX19 owns them); the
  in-block depth demonstrated filters, the below-block depth
  inhibitors and delivery.

## Verdict

**Promising; continue.** The escape hatch composes without weakening
anything: in-block descent keeps the algebra's full government
(including AX28's run surface, unchanged), below-block descent swaps
in the kernel's own law exactly where the algebra's meaning ends, and
the boundary between them — the inhibitor — is a principled semantic
line. Progressive disclosure holds in both directions. Carry forward:
the re-wrap question (spliced net back to Block) and whether descent
patterns like the acknowledged throttle deserve names in the kernel
layer's vocabulary.
