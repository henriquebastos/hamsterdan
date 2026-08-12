"""AX19 focused tests — each stated AX18 boundary feature, exercised.

One tiny neutral net per feature, every one executed by the frozen
engine. The claim under test: weight, inhibit, per-arc CEL filters,
timers, and source-transition delivery are *additive fields* on the
kernel IR — declared, lowered, and honored with no kernel redesign.
"""

from __future__ import annotations

import pytest
from ax19_kernel import (
    BoundaryArc,
    BoundaryTransition,
    KernelPlace,
    KernelShapeError,
    Mode,
    boundary_net,
    consume,
    inhibit,
    lower_boundary,
    produce,
)
from petrus.engine import Engine, SimulatedClock
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Delay, Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data

# -- harness ------------------------------------------------------------------


def run(net, seeds: dict[str, tuple[Token, ...]], *, clock=None, instance="ax19") -> Engine:
    lowered = lower_boundary(net)
    engine = Engine.create(
        lowered.built.net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking({NetPath(name): tokens for name, tokens in seeds.items()}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
        clock=clock,
    )
    drive_bounded(engine)
    return engine


def job(n: int) -> Token:
    return Token("Job", {"n": n})


# -- declaration-time refusals ---------------------------------------------------


class TestShape:
    def test_a_produce_filter_is_refused_because_it_would_not_execute(self) -> None:
        # Frozen output arcs admit by color only (the AX11 scatter
        # finding). Declaring a produce filter must fail loudly, not
        # serialize into a net that silently ignores it.
        with pytest.raises(KernelShapeError, match="admit by color only"):
            BoundaryArc("out", Mode.PRODUCE, filter="n > 0")

    def test_weights_below_one_are_meaningless(self) -> None:
        with pytest.raises(KernelShapeError, match="weight >= 1"):
            consume("queue", weight=0)


# -- weight: multiplicity is enabledness, not iteration ---------------------------


class TestWeight:
    def test_a_weight_two_consume_takes_pairs_and_strands_the_odd_token(self) -> None:
        net = boundary_net(
            "ax19-weight",
            KernelPlace("queue", "Job"),
            KernelPlace("done", "Job"),
            BoundaryTransition(name="batch", arcs=(consume("queue", weight=2), produce("done"))),
        )
        engine = run(net, {"queue": (job(1), job(2), job(3))})
        # one firing moved a pair; the third token cannot enable weight=2
        assert len(place_data(engine, "done")) == 2
        assert place_data(engine, "queue") == [{"n": 3}]


# -- inhibit: enabled only while the place is empty --------------------------------


def inhibit_net():
    return boundary_net(
        "ax19-inhibit",
        KernelPlace("inbox", "Job"),
        KernelPlace("block", "Flag"),
        KernelPlace("out", "Job"),
        BoundaryTransition(name="process", arcs=(consume("inbox"), inhibit("block"), produce("out"))),
    )


class TestInhibit:
    def test_a_flag_token_freezes_the_transition(self) -> None:
        engine = run(inhibit_net(), {"inbox": (job(1),), "block": (Token("Flag", {}),)})
        assert place_data(engine, "inbox") == [{"n": 1}]
        assert place_data(engine, "out") == []

    def test_an_empty_inhibitor_place_enables_it(self) -> None:
        engine = run(inhibit_net(), {"inbox": (job(1),)})
        assert place_data(engine, "inbox") == []
        assert place_data(engine, "out") == [{"n": 1}]


# -- per-arc CEL filter: admission per token, scope = the token's own fields -------


class TestFilter:
    def test_the_filter_admits_matching_tokens_and_parks_the_rest(self) -> None:
        # The filter's variable scope is the token's bare data fields —
        # not place names (that is the guard scope). Grade-b essays are
        # not retired and not erred: they simply never bind.
        net = boundary_net(
            "ax19-filter",
            KernelPlace("submissions", "Essay"),
            KernelPlace("published", "Essay"),
            BoundaryTransition(
                name="publish",
                arcs=(consume("submissions", filter='grade == "a"'), produce("published")),
            ),
        )
        engine = run(
            net,
            {"submissions": (Token("Essay", {"grade": "b", "id": 1}), Token("Essay", {"grade": "a", "id": 2}))},
        )
        assert place_data(engine, "published") == [{"grade": "a", "id": 2}]
        assert place_data(engine, "submissions") == [{"grade": "b", "id": 1}]


# -- timers: maturation is derived from the virtual clock, never stored ------------


def timer_net(timers) -> object:
    return boundary_net(
        "ax19-timer",
        KernelPlace("pending", "Job"),
        KernelPlace("escalated", "Job"),
        BoundaryTransition(name="escalate", arcs=(consume("pending"), produce("escalated")), timers=timers),
    )


class TestTimer:
    def test_a_delay_gates_the_firing_behind_simulated_time(self) -> None:
        # The coordinator never fires an immature binding: when only
        # timed work remains it *observes* the pending maturation, and
        # the SimulatedClock jumps forward deterministically. The drive
        # therefore quiesces with the firing stamped at anchor+duration —
        # the Delay gates in virtual time, it does not park the token.
        clock = SimulatedClock(at=0)
        engine = run(timer_net((Delay(10),)), {"pending": (job(1),)}, clock=clock)
        assert place_data(engine, "escalated") == [{"n": 1}]
        assert place_data(engine, "pending") == []
        assert clock.now() >= 10  # time had to advance to maturity first

    def test_without_the_timer_the_clock_never_moves(self) -> None:
        # The contrast that proves gating: the identical net minus the
        # Delay fires at instant zero.
        clock = SimulatedClock(at=0)
        engine = run(timer_net(()), {"pending": (job(1),)}, clock=clock)
        assert place_data(engine, "escalated") == [{"n": 1}]
        assert clock.now() == 0


# -- source transitions: the shape is kernel data, firing is the deliver door ------


class TestDelivery:
    def make(self):
        net = boundary_net(
            "ax19-source",
            KernelPlace("inbox", "Job"),
            BoundaryTransition(name="ingest", arcs=(produce("inbox"),)),
        )
        [transition] = [node for node in net.nodes if isinstance(node, BoundaryTransition)]
        assert transition.is_source
        lowered = lower_boundary(net)
        assert lowered.built.net.is_source(lowered.transitions["ingest"])
        engine = Engine.create(
            lowered.built.net,
            "ax19-source",
            history=InMemoryHistoryStore(),
            dispatch=InlineDispatch({}),
            marking=Marking({}),
            handlers=dict(lowered.handlers),
            guards=dict(lowered.built.guards),
            activities=(),
        )
        return engine

    def test_external_delivery_lands_through_the_source_transition(self) -> None:
        engine = self.make()
        engine.deliver("ingest", job(1), identity="op-1")
        drive_bounded(engine)
        assert place_data(engine, "inbox") == [{"n": 1}]

    def test_delivery_identity_deduplicates_the_at_least_once_door(self) -> None:
        engine = self.make()
        first = engine.deliver("ingest", job(1), identity="op-1")
        repeat = engine.deliver("ingest", job(1), identity="op-1")
        drive_bounded(engine)
        assert place_data(engine, "inbox") == [{"n": 1}]  # one landing, not two
        assert type(first).__name__ != type(repeat).__name__  # the repeat is a prior acknowledgement
