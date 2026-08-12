"""AX21 focused tests — the classified at-least-once boundary, driven.

The claim under test: the two idempotencies are two different net
mechanisms — identity dedup at the delivery door (kind one) and
lookup-first typed-outcome classification at the effect (kind two) —
and "already done" and "preconditions changed" are *places*, not
exceptions. Every behavioral test executes the frozen ``Engine``.
"""

from __future__ import annotations

from ax19_kernel import BoundaryTransition, lower_boundary
from ax21_boundary import MAX_RETRIES, RETRY, Ledger, effect_boundary, work
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data

# -- harness ------------------------------------------------------------------

PLACES = ("requests", "applied", "already_applied", "stale", "transient", "done", "rejected", "exhausted")
INTERIOR = ("requests", "applied", "already_applied", "stale", "transient")


def engine_for(ledger: Ledger, *, history=None, instance: str = "ax21") -> Engine:
    lowered = lower_boundary(effect_boundary(ledger))
    return Engine.create(
        lowered.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking({}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )


def assert_sound(engine: Engine) -> None:
    """The AX20 soundness discipline: a terminal path leaves no
    interior marking — every request reaches exactly one typed exit."""
    for interior in INTERIOR:
        assert place_data(engine, interior) == [], f"{interior} leaked marking"


# -- Applied: the plain path ---------------------------------------------------


class TestApplied:
    def test_the_effect_lands_once_and_exits_through_done(self) -> None:
        ledger = Ledger()
        engine = engine_for(ledger)
        engine.deliver("submit", work("op-1"), identity="d-1")
        drive_bounded(engine)
        assert [d["mode"] for d in place_data(engine, "done")] == ["applied"]
        assert ledger.applied == {"op-1": "change"}
        assert ledger.invocations == 1
        assert_sound(engine)


# -- the two idempotencies, distinguished --------------------------------------


class TestKindOneDoorDedup:
    def test_a_repeated_delivery_identity_never_reaches_the_ledger_twice(self) -> None:
        # Kind one: "if I did this before, don't do it" — answered at
        # the door, by operation identity, before any token exists.
        ledger = Ledger()
        engine = engine_for(ledger)
        engine.deliver("submit", work("op-1"), identity="d-1")
        engine.deliver("submit", work("op-1"), identity="d-1")
        drive_bounded(engine)
        assert len(place_data(engine, "done")) == 1
        assert ledger.invocations == 1


class TestKindTwoLookupFirst:
    def test_a_duplicate_work_token_is_adopted_not_reapplied(self) -> None:
        # Kind two: "how do I know I did this before?" — the ledger's
        # operation record answers, and the answer routes to a *place*.
        # Two distinct deliveries carry the same operation: the second
        # apply classifies AlreadyApplied and adopts the prior result.
        ledger = Ledger()
        engine = engine_for(ledger)
        engine.deliver("submit", work("op-1"), identity="d-1")
        engine.deliver("submit", work("op-1"), identity="d-2")
        drive_bounded(engine)
        assert sorted(d["mode"] for d in place_data(engine, "done")) == ["adopted", "applied"]
        assert ledger.applied == {"op-1": "change"}  # exactly one application
        assert ledger.invocations == 2  # the lookup itself is idempotent
        assert_sound(engine)

    def test_lookup_answers_before_preconditions(self) -> None:
        # The classification-order doctrine: an operation applied under
        # an old base, redelivered after the base moved, is
        # AlreadyApplied — not Stale. The work exists; the world merely
        # moved on afterward.
        ledger = Ledger()
        engine = engine_for(ledger)
        engine.deliver("submit", work("op-1", base="e1"), identity="d-1")
        drive_bounded(engine)
        ledger.base = "e2"  # the world moves on
        engine.deliver("submit", work("op-1", base="e1"), identity="d-2")
        drive_bounded(engine)
        assert sorted(d["mode"] for d in place_data(engine, "done")) == ["adopted", "applied"]
        assert place_data(engine, "rejected") == []


# -- Stale: preconditions changed is not an error --------------------------------


class TestStale:
    def test_a_moved_base_routes_to_rejected_without_applying(self) -> None:
        ledger = Ledger(base="e2")
        engine = engine_for(ledger)
        engine.deliver("submit", work("op-1", base="e1"), identity="d-1")
        drive_bounded(engine)  # quiesces normally: no exception, no error path
        assert place_data(engine, "done") == []
        assert len(place_data(engine, "rejected")) == 1
        assert ledger.applied == {}
        assert_sound(engine)

    def test_restart_is_a_fresh_submit_with_current_preconditions(self) -> None:
        # The AX20 ruling carried through the boundary: discard, then
        # re-enter through the same door with fresh coordinates.
        ledger = Ledger(base="e2")
        engine = engine_for(ledger)
        engine.deliver("submit", work("op-1", base="e1"), identity="d-1")
        drive_bounded(engine)
        engine.deliver("submit", work("op-2", base="e2"), identity="d-2")
        drive_bounded(engine)
        assert [d["mode"] for d in place_data(engine, "done")] == ["applied"]
        assert ledger.applied == {"op-2": "change"}


# -- Transient: the only outcome that loops ----------------------------------------


class TestRetry:
    def test_transient_faults_loop_until_the_effect_lands(self) -> None:
        ledger = Ledger(faults=2)
        engine = engine_for(ledger)
        engine.deliver("submit", work("op-1"), identity="d-1")
        drive_bounded(engine)
        [done] = place_data(engine, "done")
        assert done["mode"] == "applied"
        assert done["attempts"] == 2  # two retries, then the landing
        assert ledger.invocations == 3
        assert_sound(engine)

    def test_spent_retries_exit_through_exhausted_not_an_infinite_loop(self) -> None:
        ledger = Ledger(faults=100)
        engine = engine_for(ledger)
        engine.deliver("submit", work("op-1"), identity="d-1")
        drive_bounded(engine)  # quiesces: the complement guard ends the cycle
        assert place_data(engine, "done") == []
        [exhausted] = place_data(engine, "exhausted")
        assert exhausted["attempts"] == MAX_RETRIES
        assert ledger.invocations == MAX_RETRIES + 1
        assert ledger.applied == {}
        assert_sound(engine)


# -- the shape itself ----------------------------------------------------------------


class TestShape:
    def transitions(self) -> dict[str, BoundaryTransition]:
        return {node.name: node for node in effect_boundary(Ledger()).nodes if isinstance(node, BoundaryTransition)}

    def test_the_loop_guards_are_complements_and_everything_else_is_guardless(self) -> None:
        transitions = self.transitions()
        assert transitions["retry"].guard == RETRY
        assert transitions["give_up"].guard == f"!({RETRY})"
        for name in ("submit", "apply", "finish", "adopt", "abandon"):
            assert transitions[name].guard is None

    def test_no_place_exceeds_the_bounded_hub_degree(self) -> None:
        # The AX20/AX21 structural invariant: place degree is a small
        # constant independent of net size — no shared-state hubs.
        net = lower_boundary(effect_boundary(Ledger())).built.net
        degree: dict[str, int] = {}
        for transition in net.transitions:
            for arc in net.inputs(transition):
                degree[str(arc.source)] = degree.get(str(arc.source), 0) + 1
            for arc in net.outputs(transition):
                degree[str(arc.target)] = degree.get(str(arc.target), 0) + 1
        assert max(degree.values()) <= 3

    def test_the_whole_boundary_costs_eight_places_seven_transitions_sixteen_arcs(self) -> None:
        net = lower_boundary(effect_boundary(Ledger())).built.net
        arcs = sum(len(net.inputs(t)) + len(net.outputs(t)) for t in net.transitions)
        assert (len(tuple(net.places)), len(tuple(net.transitions)), arcs) == (8, 7, 16)


# -- replay: recorded outcomes, not re-executed effects -------------------------------


class TestReplay:
    def test_replay_reaches_the_same_marking_without_touching_the_ledger(self) -> None:
        # The durability question behind kind two: on replay, the
        # boundary's outcomes must come from history, not from a second
        # conversation with the outside world.
        history = InMemoryHistoryStore()
        live_ledger = Ledger(faults=1)
        original = engine_for(live_ledger, history=history, instance="ax21-replay")
        original.deliver("submit", work("op-1"), identity="d-1")
        drive_bounded(original)

        fresh_ledger = Ledger()  # would classify differently if consulted
        recompiled = lower_boundary(effect_boundary(fresh_ledger))
        resumed = Engine.load(
            recompiled.built.net,
            "ax21-replay",
            history=history,
            dispatch=InlineDispatch({}),
            handlers=dict(recompiled.handlers),
            guards=dict(recompiled.built.guards),
            activities=(),
        )
        for name in PLACES:
            assert place_data(resumed, name) == place_data(original, name)
        assert fresh_ledger.invocations == 0  # replay never called outside
