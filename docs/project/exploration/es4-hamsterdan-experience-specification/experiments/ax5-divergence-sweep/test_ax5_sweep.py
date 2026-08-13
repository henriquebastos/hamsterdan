"""ES-004 AX5 focused tests — the sweep's numbers are derived, not
quoted.

Claims under test:

- The production net's shape is what the document says: 46 places,
  69 transitions, 309 arcs, 94 reads, `authority` read 37 times and
  touched by more than half of all transitions.
- The category inventory is COMPLETE: every read arc in the built net
  belongs to exactly one category, and the per-category populations
  match the document's tables.
- The measured spike fragments carry ZERO read arcs and an arcs/node
  ratio near 1, against production's 2.69 — the Navigator's
  state-spread heuristic, quantified on real compiled nets.
"""

from __future__ import annotations

from ax4_composition import fresh_world, mutation_with_announcement
from ax5_inventory import CATEGORY, EXPECTED_READS
from ax23_blocks import compile_block
from ax2_linear_review import fresh_world as review_world
from ax2_linear_review import review_subnet
from hamsterdan.readiness.net.topology import build_net


def production_reads():
    net = build_net().net
    return [(str(arc.target), str(arc.source)) for arc in net.arcs if arc.is_read]


# -- the production shape, pinned ---------------------------------------------------------


def test_production_net_shape():
    net = build_net().net
    places, transitions, arcs = list(net.places), list(net.transitions), list(net.arcs)
    assert (len(places), len(transitions), len(arcs)) == (46, 69, 309)
    assert len([a for a in arcs if a.is_read]) == 94
    assert round(len(arcs) / (len(places) + len(transitions)), 2) == 2.69


def test_authority_is_a_global_hub():
    net = build_net().net
    authority_readers = {str(a.target) for a in net.arcs if a.is_read and str(a.source) == "authority"}
    authority_reads = [a for a in net.arcs if a.is_read and str(a.source) == "authority"]
    assert len(authority_reads) == 37
    assert len(authority_readers) > len(list(net.transitions)) / 2  # more than half of all transitions


# -- the inventory is complete -------------------------------------------------------------


def test_every_read_arc_is_categorized():
    uncategorized = sorted({t for t, _ in production_reads()} - set(CATEGORY))
    assert uncategorized == [], f"read arcs with no category: {uncategorized}"


def test_category_populations_match_the_document():
    counts: dict[str, int] = {}
    for transition, _ in production_reads():
        counts[CATEGORY[transition]] = counts.get(CATEGORY[transition], 0) + 1
    assert counts == EXPECTED_READS
    assert sum(counts.values()) == 94  # nothing double-counted, nothing dropped


# -- the spread heuristic, measured ----------------------------------------------------------


def _shape(block, name):
    net = compile_block(name, block).built.net
    places, transitions, arcs = list(net.places), list(net.transitions), list(net.arcs)
    reads = [a for a in arcs if a.is_read]
    return len(places), len(transitions), len(arcs), len(reads)


def test_spike_fragments_have_no_reads_and_near_linear_ratio():
    """AX2's review chain still carries its fence-era authority read;
    the AX4 attempt-first composition carries none. Both stay near
    ratio 1 where production sits at 2.69."""
    p2, t2, a2, r2 = _shape(review_subnet(review_world()), "ax5-review")
    assert (p2, t2, a2) == (10, 5, 16) and r2 == 1  # the fence read AX3 retired
    assert round(a2 / (p2 + t2), 2) == 1.07

    p4, t4, a4, r4 = _shape(mutation_with_announcement(fresh_world()), "ax5-composed")
    assert r4 == 0  # attempt-first: zero ambient reads
    assert a4 / (p4 + t4) < 1.2
