"""AX29 focused tests — the descent seam, both depths, refusals intact.

The claims under test:

- In-block descent works and stays governed: a hand-built Block using
  kernel arc filters (no handler) routes by value, composes through
  the ordinary combinators with the same eager refusals, passes
  ``check_sound``, and runs through the same ``first_motion`` harness
  as any algebra block — including replay.
- Descent widens expression honestly: two same-colored exits are
  refused by ``classify`` (its handler addresses outputs by color) but
  are meaningful in a filter-routed Block.
- The refusal boundary is exact: an inhibitor arc inside a Block is
  refused by ``check_sound``; the same arc below the algebra is legal
  kernel authoring.
- The below-block splice keeps every authority at its level:
  ``check_sound`` still governs the block part first, the kernel shape
  law governs the union (undeclared place, cross-level name
  collision), and the frozen engine runs and replays the result —
  including tokens that arrived through the delivery door.
- The inhibitor's guarantee is observed, not assumed: with the arc,
  exactly one order is dispatched at quiescence (peak occupancy one
  across the whole acknowledged run); the identical splice without it
  holds both orders in ``dispatched``. Acknowledgements fire the
  ``acknowledge`` source transition only through ``Engine.deliver``
  with operation identity.
"""

from __future__ import annotations

import pytest
from ax19_kernel import BoundaryTransition, KernelPlace, KernelShapeError, LoweredBoundary, consume, inhibit, produce
from ax23_blocks import Block, CompositionError, Port, classify, then
from ax28_motion import first_motion
from ax29_descent import express_triage, intake, order_triage, splice_throttle
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch

# -- hand composition below the algebra (the honest run surface down there) ------------


def seam_engine(lowered: LoweredBoundary, entry_place: str, tokens: tuple[Token, ...], *, store=None) -> Engine:
    store = store if store is not None else InMemoryHistoryStore()
    return Engine.create(
        lowered.built.net,
        "seam-1",
        history=store,
        dispatch=InlineDispatch({}),
        marking=Marking({NetPath(entry_place): tokens}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )


def place_data(engine: Engine, name: str) -> list[dict]:
    return [token.data for token in engine.marking.place(NetPath(name))]


def drive_watching(engine: Engine, watched: str, limit: int = 50) -> int:
    """Advance to quiescence, returning the maximum token count the
    watched place held at any step — the observation that makes the
    inhibitor's structural guarantee a fact, not a comment."""
    peak = len(place_data(engine, watched))
    for _ in range(limit):
        if not engine.advance().ready:
            return peak
        peak = max(peak, len(place_data(engine, watched)))
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def raw(sku: str, amount: float) -> Token:
    return Token("Raw", {"sku": sku, "amount": amount})


# -- in-block descent -------------------------------------------------------------------


class TestInBlockDescent:
    def test_kernel_filters_route_by_value_with_no_handler(self) -> None:
        cheap = first_motion(order_triage(), {"sku": "s-1", "amount": 50.0})
        assert cheap.settled == {"express": [{"sku": "s-1", "amount": 50.0}], "standard": []}
        dear = first_motion(order_triage(), {"sku": "s-2", "amount": 500.0})
        assert dear.settled == {"express": [], "standard": [{"sku": "s-2", "amount": 500.0}]}

    def test_the_descended_block_replays_like_any_other(self) -> None:
        motion = first_motion(order_triage(), {"sku": "s-1", "amount": 50.0})
        assert motion.replay().settled == motion.settled

    def test_the_algebra_still_refuses_bad_composition_eagerly(self) -> None:
        # A hand-built Block is not exempt from the eager refusals:
        # fusing its Order exit into a Raw entry is refused by color.
        with pytest.raises(CompositionError, match="colors differ"):
            then(express_triage(), intake(), on="express")

    def test_check_sound_still_governs_descended_nodes(self) -> None:
        stranded = Block(
            name="stranded",
            nodes=(
                KernelPlace("way_in", "Order"),
                KernelPlace("way_out", "Order"),
                KernelPlace("nowhere", "Order"),
                BoundaryTransition(name="step", arcs=(consume("way_in"), produce("way_out"))),
            ),
            entry=Port("way_in", "Order"),
            exits={"out": Port("way_out", "Order")},
            pure=True,
        )
        with pytest.raises(CompositionError, match="nowhere"):
            first_motion(stranded, {"sku": "s", "amount": 1.0})

    def test_same_colored_exits_need_descent(self) -> None:
        # classify addresses outputs by color, so it refuses duplicate
        # outcome colors; the filter-routed Block means them. Both
        # halves pinned: the refusal and the descent that lifts it.
        with pytest.raises(CompositionError, match="outcome colors must be distinct"):
            classify(
                "triage",
                lambda o: ("express", o),
                accepts="Order",
                outcomes={"express": "Order", "standard": "Order"},
            )
        assert {port.color for port in express_triage().exits.values()} == {"Order"}


# -- the refusal boundary ---------------------------------------------------------------


class TestRefusalBoundary:
    def test_an_inhibitor_inside_a_block_is_refused(self) -> None:
        gated = Block(
            name="gated",
            nodes=(
                KernelPlace("gate_in", "Order"),
                KernelPlace("gate_out", "Order"),
                BoundaryTransition(
                    name="pass_gate", arcs=(consume("gate_in"), inhibit("gate_out"), produce("gate_out"))
                ),
            ),
            entry=Port("gate_in", "Order"),
            exits={"out": Port("gate_out", "Order")},
            pure=True,
        )
        with pytest.raises(CompositionError, match="inhibitor arcs are outside the block algebra"):
            first_motion(gated, {"sku": "s", "amount": 1.0})


# -- below-block descent: the L1 splice -------------------------------------------------


class TestSplice:
    def test_the_inhibitor_holds_dispatch_until_acknowledged(self) -> None:
        # Two orders arrive; nothing is acknowledged yet. With the
        # inhibitor, exactly one order is dispatched at quiescence and
        # the other waits upstream — a structural throttle, whatever
        # the driving policy.
        lowered = splice_throttle("throttle", intake(), lane="out")
        engine = seam_engine(lowered, "intake_in", (raw("s-1", 5.0), raw("s-2", 7.0)))
        peak = drive_watching(engine, "dispatched")
        assert peak == 1
        assert len(place_data(engine, "dispatched")) == 1
        assert len(place_data(engine, "intake_out")) == 1
        assert place_data(engine, "settled") == []

    def test_the_counterfactual_without_the_arc_reaches_two(self) -> None:
        # The same splice minus the one arc under test: both orders sit
        # in dispatched at quiescence — the throttle came from the
        # inhibitor, not from the driving policy.
        lowered = splice_throttle("throttle", intake(), lane="out", inhibited=False)
        engine = seam_engine(lowered, "intake_in", (raw("s-1", 5.0), raw("s-2", 7.0)))
        drive_watching(engine, "dispatched")
        assert len(place_data(engine, "dispatched")) == 2

    def test_acknowledgements_arrive_through_the_delivery_door(self) -> None:
        # The 'acknowledge' source transition fires only through
        # Engine.deliver with operation identity — the at-least-once
        # boundary at the seam. Each ack releases exactly one order;
        # the peak occupancy of dispatched never exceeds one across
        # the whole acknowledged run.
        lowered = splice_throttle("throttle", intake(), lane="out")
        engine = seam_engine(lowered, "intake_in", (raw("s-1", 5.0), raw("s-2", 7.0)))
        peak = drive_watching(engine, "dispatched")

        engine.deliver("acknowledge", Token("Ack", {}), identity="ack-1")
        peak = max(peak, drive_watching(engine, "dispatched"))
        assert len(place_data(engine, "settled")) == 1

        engine.deliver("acknowledge", Token("Ack", {}), identity="ack-2")
        peak = max(peak, drive_watching(engine, "dispatched"))
        assert sorted(order["sku"] for order in place_data(engine, "settled")) == ["s-1", "s-2"]
        assert peak == 1

    def test_check_sound_still_governs_the_block_part(self) -> None:
        healthy = intake()
        broken = Block(
            name=healthy.name,
            nodes=(*healthy.nodes, KernelPlace("orphan", "X")),
            entry=healthy.entry,
            exits=dict(healthy.exits),
            pure=healthy.pure,
        )
        with pytest.raises(CompositionError, match="orphan"):
            splice_throttle("throttle", broken, lane="out")

    def test_the_kernel_shape_law_governs_the_splice(self) -> None:
        # A splice transition referencing a place nobody declared is
        # the kernel's refusal, at the kernel's level.
        with pytest.raises(KernelShapeError, match="undeclared place"):
            lowered_nodes = intake().nodes
            from ax19_kernel import boundary_net

            boundary_net(
                "bad-splice",
                *(node for node in lowered_nodes if isinstance(node, KernelPlace)),
                *(node for node in lowered_nodes if isinstance(node, BoundaryTransition)),
                BoundaryTransition(name="dispatch", arcs=(consume("no_such_place"), produce("intake_out"))),
            )

    def test_cross_level_name_collisions_are_refused(self) -> None:
        # The splice may not silently shadow a block place: one
        # namespace, one shape law.
        colliding = Block(
            name="colliding",
            nodes=(
                KernelPlace("collide_in", "Order"),
                KernelPlace("dispatched", "Order"),
                BoundaryTransition(name="step", arcs=(consume("collide_in"), produce("dispatched"))),
            ),
            entry=Port("collide_in", "Order"),
            exits={"out": Port("dispatched", "Order")},
            pure=True,
        )
        with pytest.raises(KernelShapeError, match="duplicate place 'dispatched'"):
            splice_throttle("throttle", colliding, lane="out")

    def test_the_spliced_net_replays_including_deliveries(self) -> None:
        store = InMemoryHistoryStore()
        lowered = splice_throttle("throttle", intake(), lane="out")
        engine = seam_engine(lowered, "intake_in", (raw("s-1", 5.0), raw("s-2", 7.0)), store=store)
        drive_watching(engine, "dispatched")
        engine.deliver("acknowledge", Token("Ack", {}), identity="ack-1")
        drive_watching(engine, "dispatched")

        recompiled = splice_throttle("throttle", intake(), lane="out")
        resumed = Engine.load(
            recompiled.built.net,
            "seam-1",
            history=store,
            dispatch=InlineDispatch({}),
            handlers=dict(recompiled.handlers),
            guards=dict(recompiled.built.guards),
            activities=(),
        )
        for name in ("intake_in", "intake_out", "dispatched", "ack", "settled"):
            assert place_data(resumed, name) == place_data(engine, name), f"replay diverged at {name!r}"
