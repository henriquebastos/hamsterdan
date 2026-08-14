"""AX4 — the comparison: production braid vs the tower, same instruments.

The quarantine lifts here (ES-006 method rule 4): production
``topology.py`` is opened for the first time in this exploration and
measured with exactly the helpers that measured AX1-AX3. Read-only —
production behavior untouched.

Every number in ``ax4-comparison.md`` is pinned by these tests.
"""

from hamsterdan.readiness.net.topology import build_net
from test_ax1_work_net import (
    build_work_net_collapsed,
    build_work_net_explicit,
    fragments,
    is_acyclic,
    metrics,
)
from test_ax2_case_net import build_case_net_grid


class TestProductionMeasured:
    def test_production_inventory(self) -> None:
        assert metrics(build_net()) == {
            "P": 46,
            "T": 69,
            "A": 309,
            "ratio": 2.687,
            "read_arcs": 94,
            "inhibit_arcs": 0,
            "filters": 0,
            "guards": 48,
        }

    def test_production_is_one_braid(self) -> None:
        """Everything is transitively connected to everything: no
        concern can be read, tested, or replayed in isolation."""
        built = build_net()
        assert fragments(built) == 1
        assert not is_acyclic(built)

    def test_production_fan_shapes(self) -> None:
        """19 transitions join 2 tokens, 7 join 3, one joins 8; the
        admission place feeds 7 competing transitions."""
        net = build_net().net
        transition_names = {str(t) for t in net.transitions}
        fan_in: dict[str, int] = {}
        for a in net.arcs:
            if a.is_consume and str(a.target) in transition_names:
                fan_in[str(a.target)] = fan_in.get(str(a.target), 0) + 1
        histogram: dict[int, int] = {}
        for count in fan_in.values():
            histogram[count] = histogram.get(count, 0) + 1
        assert histogram == {1: 35, 2: 19, 3: 7, 8: 1}

        place_names = {str(p) for p in net.places}
        out: dict[str, int] = {}
        for a in net.arcs:
            if a.is_consume and str(a.source) in place_names:
                out[str(a.source)] = out.get(str(a.source), 0) + 1
        assert max(out.items(), key=lambda kv: kv[1]) == ("admission", 7)


class TestTheHeadline:
    def test_v2_totals_against_production(self) -> None:
        """Same product contract; the tower's V2 needs a third of the
        arcs, no read arcs, and no guards."""
        production = metrics(build_net())
        case = metrics(build_case_net_grid())
        work = metrics(build_work_net_explicit())

        v2_arcs = case["A"] + work["A"]
        assert (production["A"], v2_arcs) == (309, 99)

        for measure in ("read_arcs", "guards", "filters", "inhibit_arcs"):
            assert case[measure] == work[measure] == 0
        assert production["read_arcs"] == 94
        assert production["guards"] == 48

    def test_arc_density_tells_the_story(self) -> None:
        """Work < 1, coordination slightly > 1, braid ~2.7."""
        assert metrics(build_work_net_explicit())["ratio"] == 0.85
        assert metrics(build_work_net_collapsed())["ratio"] == 0.833
        assert metrics(build_case_net_grid())["ratio"] == 1.409
        assert metrics(build_net())["ratio"] == 2.687
