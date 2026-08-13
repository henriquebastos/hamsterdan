"""AX29 — the descent seam: one file mixing algebra blocks with kernel authoring.

Progressive disclosure has two directions. AX28 proved the upward one
(one call to first motion); this file is the downward one: what an
author writes when the combinators do not spell the semantics they
need, and which authority governs each depth.

Two descent depths appear side by side:

- **In-block descent.** ``express_triage`` is a Block whose nodes are
  hand-written kernel dataclasses using vocabulary no combinator
  spells: per-arc CEL filters that route by value with *no handler at
  all*, and two same-colored exits (``classify`` refuses those — its
  handler addresses outputs by color; a filter-routed Block may mean
  them). The algebra still owns the result completely: eager refusals
  at composition, ``check_sound`` at compile, ``first_motion`` as the
  run surface.

- **Below-block descent.** The one construct ``check_sound`` refuses
  inside a block — an inhibitor arc, which is *non-flow* and therefore
  breaks entry→exit reachability's meaning — is composed below the
  algebra at the boundary-net level. ``splice_throttle`` shows the
  seam's law: ``check_sound`` still governs the block part first, the
  kernel's own shape law (``KernelShapeError``) governs the union, and
  the run surface is manual, as it honestly must be below the algebra.
"""

from __future__ import annotations

from ax19_kernel import (
    BoundaryTransition,
    KernelPlace,
    LoweredBoundary,
    PetriWork,
    boundary_net,
    consume,
    inhibit,
    lower_boundary,
    produce,
)
from ax23_blocks import Block, Port, check_sound, then, transform
from petrus.impetus.petrinet import Token

# -- the algebra part: ordinary combinators -------------------------------------------


def intake() -> Block:
    return transform(
        "intake",
        lambda r: {"sku": r["sku"], "amount": r["amount"]},
        accepts="Raw",
        returns="Order",
    )


# -- in-block descent: kernel vocabulary inside an ordinary Block ----------------------


def express_triage() -> Block:
    """Route by value with per-arc CEL filters — declarative admission,
    no handler, no classifier function. The token's own data decides
    which arc admits it (the AX19 filter contract)."""
    return Block(
        name="triage",
        nodes=(
            KernelPlace("triage_in", "Order"),
            KernelPlace("express", "Order"),
            KernelPlace("standard", "Order"),
            BoundaryTransition(
                name="expedite",
                arcs=(consume("triage_in", filter="amount < 100.0"), produce("express")),
            ),
            BoundaryTransition(
                name="queue_standard",
                arcs=(consume("triage_in", filter="amount >= 100.0"), produce("standard")),
            ),
        ),
        entry=Port("triage_in", "Order"),
        exits={"express": Port("express", "Order"), "standard": Port("standard", "Order")},
        pure=True,
    )


def order_triage() -> Block:
    """The mixed workflow: an algebra leaf composed with a descended
    Block through the ordinary combinator — same refusals, same
    soundness check, same run surface."""
    return then(intake(), express_triage(), on="out")


# -- below-block descent: the L1 splice ------------------------------------------------


def splice_throttle(net_name: str, upstream: Block, *, lane: str, inhibited: bool = True) -> LoweredBoundary:
    """Fuse a dispatch-until-acknowledged throttle below the algebra:
    the inhibitor keeps ``dispatch`` disabled while ``dispatched``
    holds an unacknowledged token — a structural guarantee no block
    combinator can spell — and acknowledgements arrive from outside
    through the engine's delivery door (the ``acknowledge`` source
    transition, fired only by ``Engine.deliver`` with operation
    identity).

    The seam's law, in order: ``check_sound`` governs the block part
    first; then ``boundary_net``'s shape law governs the union.
    ``inhibited=False`` exists only as the experiment's counterfactual
    knob — the same splice minus the one arc under test.
    """
    check_sound(upstream)
    port = upstream.exits[lane]
    gate = (inhibit("dispatched"),) if inhibited else ()

    def confirm_work(binding, outputs):
        [order] = [token for token in binding.tokens if token.color == port.color]
        [target] = [arc.target for arc in outputs if arc.color == port.color]
        return {target: (Token(port.color, dict(order.data)),)}

    extra = (
        KernelPlace("dispatched", port.color),
        KernelPlace("ack", "Ack"),
        KernelPlace("settled", port.color),
        BoundaryTransition(name="dispatch", arcs=(consume(port.place), *gate, produce("dispatched"))),
        BoundaryTransition(name="acknowledge", arcs=(produce("ack"),)),  # source: the delivery door
        BoundaryTransition(
            name="confirm",
            arcs=(consume("dispatched"), consume("ack"), produce("settled")),
            work=PetriWork(confirm_work),
        ),
    )
    nodes = (*upstream.nodes, *extra)
    places = tuple(node for node in nodes if isinstance(node, KernelPlace))
    transitions = tuple(node for node in nodes if isinstance(node, BoundaryTransition))
    return lower_boundary(boundary_net(net_name, *places, *transitions))
