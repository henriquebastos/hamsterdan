"""AX4 — the verdict census, pinned as executable evidence.

Three artifacts are measured side by side, read-only:

1. PRODUCTION — `hamsterdan.readiness.net.topology.build_net()`,
   untouched (this file only imports and measures it).
2. V5 COHABITED — AX1's authored net.
3. V5 SHARDED — AX3's derived nine-way assembly.

Every structural count quoted in ax4-verdict.md is asserted here, so
the comparison can never silently drift from the code it describes
(test-suite sizes and approximate line counts are cited, not
asserted). The interpretation (what the numbers mean, what to
recommend) lives in the Markdown; this file owns only the facts.

THREE DIRECTIONAL PREFIX METRICS are reported, because they measure
different things and conflating them would cook the books:

- STRICT (AX3's `seams()`): arcs between two NAMED prefixes. In
  production the prefixes are operational sections, so this counts
  CROSS-SECTION arcs; only in V5, where every prefix is a declared
  loop owner, does it read as cross-loop custody.
- BROAD INPUT (the AX3 profile lens): input arcs whose endpoint
  prefixes differ, INCLUDING an empty prefix. This measures distance
  from the shardable-net profile — production's root-level places
  (authority, actions_state, ...) all count here, because unowned
  state is exactly what the profile refuses.
- BROAD OUTPUT: output arcs whose endpoint prefixes differ, again
  including empty. This is topology anatomy, not custody: in V5 it
  includes the 8 root ingress-door feeds alongside the 74 seams.

Only the strict metric speaks to coupling (and only in V5 to custody);
the broad metrics and the unowned-node census speak to
profile distance and ownership coverage.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

import pytest
import test_ax1_complete_v5 as ax1
from hamsterdan.readiness.net.topology import ACTIVITY_TRANSITIONS, build_net
from test_ax3_sharded import NINE, loop_of, seams, split


@pytest.fixture(scope="module")
def prod():
    return build_net()


@pytest.fixture(scope="module")
def v5():
    return ax1.build_v5_net()


@pytest.fixture(scope="module")
def shards(v5):
    return split(v5, NINE)


def _census(net) -> dict:
    places = {str(p) for p in net.places}
    transitions = {str(t) for t in net.transitions}
    inputs = [
        a for a in net.arcs if str(a.source) in places and str(a.target) in transitions
    ]
    outputs = [
        a for a in net.arcs if str(a.source) in transitions and str(a.target) in places
    ]
    broad_in = [a for a in inputs if loop_of(str(a.source)) != loop_of(str(a.target))]
    named_in = [a for a in broad_in if loop_of(str(a.source)) and loop_of(str(a.target))]
    broad_out = [a for a in outputs if loop_of(str(a.source)) != loop_of(str(a.target))]
    doors = {t for t in transitions if not any(str(a.target) == t for a in net.arcs)}
    return {
        "P": len(net.places),
        "T": len(net.transitions),
        "A": len(net.arcs),
        "modes": {m: sum(1 for a in net.arcs if str(a.mode) == m) for m in ("consume", "read", "inhibit")},
        "filters": sum(1 for a in net.arcs if getattr(a, "filter", None) is not None),
        "cross_in_broad": len(broad_in),
        "cross_in_named": len(named_in),
        "cross_in_unowned": len(broad_in) - len(named_in),
        "cross_out_broad": len(broad_out),
        "seams_strict": len(seams(net)),
        "unowned_places": sum(1 for p in places if not loop_of(p)),
        "unowned_transitions": sum(1 for t in transitions - doors if not loop_of(t)),
        "ingress_doors": len(doors),
        "ratio": round(len(net.arcs) / (len(net.places) + len(net.transitions)), 2),
    }


class TestProductionShape:
    """The untouched braided topology, measured — never modified."""

    def test_the_census(self, prod) -> None:
        assert _census(prod.net) == {
            "P": 46,
            "T": 69,
            "A": 309,
            "modes": {"consume": 215, "read": 94, "inhibit": 0},
            "filters": 0,
            # 92 inputs violate the shardable profile; only 11 connect
            # two named sections, the other 81 involve an UNOWNED root
            # endpoint (decomposed in test_the_unowned_input_anatomy)
            "cross_in_broad": 92,
            "cross_in_named": 11,
            "cross_in_unowned": 81,
            "cross_out_broad": 72,
            "seams_strict": 12,  # named->named outputs, AX3's definition
            "unowned_places": 33,
            "unowned_transitions": 25,  # non-ingress; the 7 doors are exempt
            "ingress_doors": 7,
            "ratio": 2.69,
        }

    def test_the_unowned_input_anatomy(self, prod) -> None:
        """The 81 unowned-endpoint profile violations decompose as 79
        unowned-place -> named-transition plus 2 named-place ->
        unowned-transition. Of the 79, 40 originate at the nine
        root cohort places (37 read + 3 consume) and 39 at OTHER root
        places (generation control, admission, seed/dormant/terminal,
        recovery and basis/result buffers) — so the cohort is the
        largest single contributor, not the whole story. The
        non-cohort source set is asserted exactly so the attribution
        cannot drift."""
        net = prod.net
        places = {str(p) for p in net.places}
        transitions = {str(t) for t in net.transitions}
        broad = [
            a
            for a in net.arcs
            if str(a.source) in places
            and str(a.target) in transitions
            and loop_of(str(a.source)) != loop_of(str(a.target))
        ]
        from_unowned = [
            a for a in broad if not loop_of(str(a.source)) and loop_of(str(a.target))
        ]
        to_unowned = [
            a for a in broad if loop_of(str(a.source)) and not loop_of(str(a.target))
        ]
        assert (len(from_unowned), len(to_unowned)) == (79, 2)
        cohort = {
            "authority",
            "actions_state",
            "review_state",
            "human_state",
            "mutation_state",
            "finding_publication_state",
            "conversation_publication_state",
            "dashboard_publication_state",
            "readiness_publication_state",
        }
        assert cohort <= places
        from_cohort = [a for a in from_unowned if str(a.source) in cohort]
        assert len(from_cohort) == 40
        modes = {m: sum(1 for a in from_cohort if str(a.mode) == m) for m in ("read", "consume")}
        assert modes == {"read": 37, "consume": 3}
        others = Counter(
            str(a.source) for a in from_unowned if str(a.source) not in cohort
        )
        assert sum(others.values()) == 39
        assert dict(others) == {
            "generation_commit": 6,
            "admission": 4,
            "recovery_basis": 4,
            "generation_start": 3,
            "generation_stop": 3,
            "dormant": 3,
            "seed": 3,
            "terminal": 1,
            "actions_basis": 1,
            "actions_result": 1,
            "change_basis": 1,
            "change_result": 1,
            "conversation_basis": 1,
            "conversation_result": 1,
            "dashboard_result": 1,
            "finding_result": 1,
            "readiness_result": 1,
            "repair_result": 1,
            "reply_basis": 1,
            "review_result": 1,
        }

    def test_the_wiring_registries(self, prod) -> None:
        assert len(prod.guards) == 48
        assert len(prod.handlers) == 33  # fold handlers
        assert len(ACTIVITY_TRANSITIONS) == 11  # activity bindings
        # bound callables total: 33 + 11 = 44

    def test_production_is_outside_the_shardable_profile(self, prod) -> None:
        """The AX3 splitter REFUSES the production net — that refusal
        is itself a measurement. The FIRST refusal is the unowned-node
        clause (58 nodes: 33 places + 25 non-ingress transitions have
        no section owner); the braid clause (92 foreign inputs) would
        refuse it next. No AX3 placement is accepted for the current
        topology."""
        sections = {loop_of(str(p)) for p in prod.net.places} - {""}
        with pytest.raises(ValueError, match="nodes without a loop owner"):
            split(prod, dict.fromkeys(sections, "all"))


class TestV5Shape:
    """AX1's authored net, measured against the same yardsticks."""

    def test_the_census(self, v5) -> None:
        assert _census(v5.net) == {
            "P": 85,
            "T": 77,
            "A": 312,
            "modes": {"consume": 312, "read": 0, "inhibit": 0},
            "filters": 0,
            "cross_in_broad": 0,  # zero under BOTH metrics
            "cross_in_named": 0,
            "cross_in_unowned": 0,
            "cross_out_broad": 82,  # 74 named seams + 8 ingress-door feeds
            "seams_strict": 74,
            "unowned_places": 0,
            "unowned_transitions": 0,
            "ingress_doors": 8,
            "ratio": 1.93,
        }

    def test_the_wiring_registries(self, v5) -> None:
        assert v5.guards == {}  # zero guards, asserted — not implied
        world = ax1.fresh_world()
        defs = {d.declaration.name: d for d in ax1.make_activities(world)}
        handlers = ax1._wire(v5, defs)
        assert len(handlers) == 69
        activity_bound = sum(
            1 for h in handlers.values() if type(h).__name__.endswith("ActivityHandler")
        )
        assert activity_bound == 8  # fold handlers: 69 - 8 = 61
        assert len(defs) == 8


class TestShardedShape:
    """AX3's nine-way assembly: all growth is generated transport."""

    def test_the_census_totals(self, shards) -> None:
        P = sum(len(p.net.places) for p in shards.values())
        T = sum(len(p.net.transitions) for p in shards.values())
        A = sum(len(p.net.arcs) for p in shards.values())
        assert (P, T, A) == (199, 217, 604)
        assert round(A / (P + T), 2) == 1.45
        assert sum(len(p.routes_out) for p in shards.values()) == 38
        assert sum(len(p.doors_in) for p in shards.values()) == 26
        # protocol handler registrations: one pump + one ack fold per
        # route, all backed by the SAME two shared functions
        protocol = [h for p in shards.values() for h in p.courier_handlers.values()]
        assert len(protocol) == 76
        assert len({id(h) for h in protocol}) == 2

    def test_the_generated_input_arcs(self, shards) -> None:
        """The shard nets are NOT zero-input under the prefix lens:
        each of the 38 routes contributes one named mailbox-proxy ->
        courier.pump_* input arc, so the aggregate is 38 strict and
        38 broad cross-prefix inputs — every one of them generated
        protocol plumbing (the target is always a courier pump), zero
        of them authored."""
        strict = broad = 0
        targets = set()
        for plan in shards.values():
            places = {str(p) for p in plan.net.places}
            transitions = {str(t) for t in plan.net.transitions}
            for a in plan.net.arcs:
                s, t = str(a.source), str(a.target)
                if s in places and t in transitions and loop_of(s) != loop_of(t):
                    broad += 1
                    if loop_of(s) and loop_of(t):
                        strict += 1
                    targets.add(t)
        assert (strict, broad) == (38, 38)
        assert all(t.startswith("courier.pump_") for t in targets)

    def test_the_door_census(self, shards, v5) -> None:
        """Across the nine shard nets there are 72 no-input (source)
        transitions, and they are NOT one census: 8 are the authored
        external ingress doors (same as cohabited V5), 38 are
        generated per-route acknowledgement doors, and 26 are
        generated delivery doors — one per inbound route target."""
        authored_doors = {
            str(t)
            for t in v5.net.transitions
            if not any(str(a.target) == str(t) for a in v5.net.arcs)
        }
        assert len(authored_doors) == 8
        source_transitions = [
            str(t)
            for p in shards.values()
            for t in p.net.transitions
            if not any(str(a.target) == str(t) for a in p.net.arcs)
        ]
        assert len(source_transitions) == 72
        authored = [t for t in source_transitions if t in authored_doors]
        acks = [t for t in source_transitions if t.startswith("on_ack_")]
        deliveries = [t for t in source_transitions if t.startswith("on_courier_")]
        assert (len(authored), len(acks), len(deliveries)) == (8, 38, 26)
        assert len(authored) + len(acks) + len(deliveries) == 72
        # the authored doors are name-identical to cohabited V5's doors
        assert set(authored) == authored_doors

    def test_the_growth_is_entirely_generated(self, v5, shards) -> None:
        """+114 places, +140 transitions (254 nodes), +292 arcs — all
        of it courier machinery matching AX3's per-route formula, and
        every non-courier node is an authored object."""
        routes = sum(len(p.routes_out) for p in shards.values())
        doors = sum(len(p.doors_in) for p in shards.values())
        dP = sum(len(p.net.places) for p in shards.values()) - len(v5.net.places)
        dT = sum(len(p.net.transitions) for p in shards.values()) - len(v5.net.transitions)
        dA = sum(len(p.net.arcs) for p in shards.values()) - len(v5.net.arcs)
        assert (dP, dT, dA) == (114, 140, 292)
        assert dP == 3 * routes
        assert dT == 3 * routes + doors
        assert dA == 7 * routes + doors
        authored_p = {str(p) for p in v5.net.places}
        authored_t = {str(t) for t in v5.net.transitions}
        for plan in shards.values():
            for p in plan.net.places:
                name = str(p)
                assert name in authored_p or name.startswith("courier.")
            for t in plan.net.transitions:
                name = str(t)
                assert name in authored_t or name.startswith(
                    ("courier.", "on_courier_", "on_ack_")
                )

    def test_the_engine_state_isolation_numbers(self, shards) -> None:
        """Engine-STATE isolation in numbers (not a blast-radius
        claim: host, process, transport, and storage failure were not
        isolated by ES-007): the largest shard (life, 103 nodes) is
        smaller than production's whole net (115); the smallest (dash)
        is 21. AX3 proved the review-shard resurrection path."""
        sizes = {
            shard: len(p.net.places) + len(p.net.transitions) for shard, p in shards.items()
        }
        assert sizes["life"] == 103  # < 46 + 69 = 115 (production)
        assert sizes["dash"] == 21
        assert max(sizes.values()) == sizes["life"]
