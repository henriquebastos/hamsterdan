"""Executable fact for chapter 15's worked example.

Builds the refund workflow's lowered net with today's Petrus spec DSL
(`petrus.impetus.dsl.NetSpec`) — exactly the snippet quoted in
`15-from-spec-to-net.md` — and asserts the structure the chapter
claims: 5 places, 4 transitions, 9 arcs (`arcs/(P+T) = 1.0`), the two
CEL-filtered triage arcs, and the typed exits. The snippet in the doc
and this test must stay identical.
"""

from petrus.impetus.dsl import BuiltNet, NetSpec, arc


class RefundRequest: ...


class Approved: ...


class Refunded: ...


class Discarded: ...


class Notified: ...


def build_refund_net() -> BuiltNet:
    # -- the snippet quoted in 15-from-spec-to-net.md, verbatim -----------
    net = NetSpec("refund")
    p, t = net.p, net.t

    (
        p.refund_request(RefundRequest)
        >> arc(filter="amount > 500")
        >> t.human_approval(handler="human_approval")
        >> p.approved(Approved)
    )
    (
        p.refund_request
        >> arc(filter="amount <= 500")
        >> t.auto_approve(handler="auto_approve")
        >> p.approved
    )
    p.approved >> t.refund(handler="refund") >> (p.refunded(Refunded), p.discarded(Discarded))
    p.refunded >> t.notify(handler="notify") >> p.notified(Notified)

    return net.build()
    # ----------------------------------------------------------------------


class TestRefundNetSpec:
    def test_node_inventory_matches_the_chapter(self) -> None:
        net = build_refund_net().net
        assert sorted(str(place) for place in net.places) == [
            "approved",
            "discarded",
            "notified",
            "refund_request",
            "refunded",
        ]
        assert sorted(str(transition) for transition in net.transitions) == [
            "auto_approve",
            "human_approval",
            "notify",
            "refund",
        ]

    def test_arc_economy_is_one(self) -> None:
        net = build_refund_net().net
        assert len(net.arcs) == 9
        assert len(net.arcs) / (len(net.places) + len(net.transitions)) == 1.0

    def test_triage_arcs_carry_the_cel_filters(self) -> None:
        net = build_refund_net().net
        filtered = sorted(
            (str(one.source), str(one.target), str(one.filter))
            for one in net.arcs
            if one.filter is not None
        )
        assert filtered == [
            ("refund_request", "auto_approve", "amount <= 500"),
            ("refund_request", "human_approval", "amount > 500"),
        ]

    def test_refund_gate_fans_out_to_both_typed_exits(self) -> None:
        net = build_refund_net().net
        from_refund = sorted(
            (str(one.target), one.color) for one in net.arcs if str(one.source) == "refund"
        )
        assert from_refund == [("discarded", "Discarded"), ("refunded", "Refunded")]
