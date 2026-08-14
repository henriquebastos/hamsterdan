"""AX3 — the V3 variant: PR lifecycle and epoch management as TWO nets.

V2 (AX2) holds lifecycle and epoch management in one case net. V3
splits them:

- **pr net** — lifecycle only. Same (state x observation) grid as
  AX2, but instead of emitting spawn/abandon requests it emits
  lifecycle FACTS for the epoch net: ``head_seen``, ``went_active``,
  ``went_dormant``, ``went_terminal``.
- **epoch net** — instance management only. Consumes those facts,
  holds its own state (running / idle / finished), owns the
  spawn/abandon pipelines from AX2.

The split's price is measured, not argued: four cross-net fact
colors (plus the routing machinery to move them, which the shipped
runtime does not provide), and a second state cell whose states
shadow the first (running≈active, idle≈dormant, finished≈terminal).
Every claim in ``ax3-v3-split.md`` is asserted here.
"""

from petrus.impetus.dsl import BuiltNet, NetSpec
from test_ax1_work_net import is_acyclic, metrics
from test_ax2_case_net import (
    build_case_net_grid,
    cycles_removed_by,
    instance_pipelines,
)

# -- colors ----------------------------------------------------------------


class ObservedOpen: ...


class ObservedDraft: ...


class ObservedClosed: ...


class PrActive: ...


class PrDormant: ...


class PrTerminal: ...


# cross-net facts: the pr net emits, the epoch net consumes
class HeadSeen: ...       # open observed while active; head in data


class WentActive: ...     # resumed; head in data


class WentDormant: ...


class WentTerminal: ...


class EpochRunning: ...   # (epoch, head, instance handle)


class EpochIdle: ...      # no instance should exist


class EpochFinished: ...  # absorbing


CROSS_NET_FACTS = ("head_seen", "went_active", "went_dormant", "went_terminal")


# -- the pr net: lifecycle only ---------------------------------------------


def build_pr_net() -> BuiltNet:
    net = NetSpec("pr")
    p, t = net.p, net.t

    p.active(PrActive)
    p.dormant(PrDormant)
    p.terminal(PrTerminal)
    p.observed_open(ObservedOpen)
    p.observed_draft(ObservedDraft)
    p.observed_closed(ObservedClosed)

    (
        (p.active, p.observed_open)
        >> t.note_open(handler="note_open")
        >> (p.active, p.head_seen(HeadSeen))
    )
    (
        (p.active, p.observed_draft)
        >> t.suspend(handler="suspend")
        >> (p.dormant, p.went_dormant(WentDormant))
    )
    (
        (p.active, p.observed_closed)
        >> t.close(handler="close")
        >> (p.terminal, p.went_terminal(WentTerminal))
    )
    (
        (p.dormant, p.observed_open)
        >> t.resume(handler="resume")
        >> (p.active, p.went_active(WentActive))
    )
    (p.dormant, p.observed_draft) >> t.note_draft(handler="note_draft") >> p.dormant
    (
        (p.dormant, p.observed_closed)
        >> t.close_dormant(handler="close_dormant")
        >> (p.terminal, p.went_terminal)
    )

    return net.build()


# -- the epoch net: instance management only ---------------------------------


def build_epoch_net() -> BuiltNet:
    net = NetSpec("epoch")
    p, t = net.p, net.t

    p.running(EpochRunning)
    p.idle(EpochIdle)
    p.finished(EpochFinished)
    p.head_seen(HeadSeen)
    p.went_active(WentActive)
    p.went_dormant(WentDormant)
    p.went_terminal(WentTerminal)

    from test_ax2_case_net import AbandonRequest, SpawnRequest

    (
        (p.running, p.head_seen)
        >> t.head_check(handler="head_check")
        >> (p.running, p.abandon_request(AbandonRequest), p.spawn_request(SpawnRequest))
    )
    (p.idle, p.went_active) >> t.start(handler="start") >> (p.running, p.spawn_request)
    (
        (p.running, p.went_dormant)
        >> t.retire(handler="retire")
        >> (p.idle, p.abandon_request)
    )
    (
        (p.running, p.went_terminal)
        >> t.finish_running(handler="finish_running")
        >> (p.finished, p.abandon_request)
    )
    (p.idle, p.went_terminal) >> t.finish_idle(handler="finish_idle") >> p.finished

    instance_pipelines(net)
    return net.build()


# -- the asserted facts -------------------------------------------------------


class TestMeasuredShape:
    def test_pr_net_inventory(self) -> None:
        assert metrics(build_pr_net()) == {
            "P": 10,
            "T": 6,
            "A": 23,
            "ratio": 1.438,
            "read_arcs": 0,
            "inhibit_arcs": 0,
            "filters": 0,
            "guards": 0,
        }

    def test_epoch_net_inventory(self) -> None:
        assert metrics(build_epoch_net()) == {
            "P": 14,
            "T": 8,
            "A": 28,
            "ratio": 1.273,
            "read_arcs": 0,
            "inhibit_arcs": 0,
            "filters": 0,
            "guards": 0,
        }

    def test_both_are_state_cells(self) -> None:
        pr, epoch = build_pr_net(), build_epoch_net()
        assert not is_acyclic(pr) and not is_acyclic(epoch)
        assert cycles_removed_by(pr, {"active", "dormant", "terminal"})
        assert cycles_removed_by(epoch, {"running", "idle", "finished"})


class TestThePriceOfTheSplit:
    def test_v3_costs_more_nodes_than_v2_for_the_same_behavior(self) -> None:
        v2 = metrics(build_case_net_grid())
        pr, epoch = metrics(build_pr_net()), metrics(build_epoch_net())
        v2_nodes = v2["P"] + v2["T"]
        v3_nodes = pr["P"] + pr["T"] + epoch["P"] + epoch["T"]
        assert v2_nodes == 22
        assert v3_nodes == 38
        assert pr["A"] + epoch["A"] == 51 > v2["A"] == 31

    def test_four_cross_net_fact_colors_appear_in_both_nets(self) -> None:
        """Every split boundary token is a place in BOTH nets — the
        routing between them is machinery the shipped runtime does not
        provide."""
        pr_places = {str(p) for p in build_pr_net().net.places}
        epoch_places = {str(p) for p in build_epoch_net().net.places}
        assert set(CROSS_NET_FACTS) <= pr_places
        assert set(CROSS_NET_FACTS) <= epoch_places

    def test_the_epoch_net_states_shadow_the_pr_net_states(self) -> None:
        """running/idle/finished exist only to mirror active/dormant/
        terminal across the boundary: every epoch-net state change is
        triggered by a pr-net lifecycle fact, never by a domain fact."""
        net = build_epoch_net().net
        state = {"running", "idle", "finished"}
        transition_names = {str(t) for t in net.transitions}
        movers = set()
        for a in net.arcs:
            if str(a.source) in state and str(a.target) in transition_names:
                movers.add(str(a.target))
        triggers = {
            name: sorted(
                str(a.source)
                for a in net.arcs
                if str(a.target) == name and str(a.source) not in state
            )
            for name in movers
        }
        assert triggers == {
            "head_check": ["head_seen"],
            "start": ["went_active"],
            "retire": ["went_dormant"],
            "finish_running": ["went_terminal"],
            "finish_idle": ["went_terminal"],
        }
