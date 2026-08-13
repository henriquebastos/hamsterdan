"""ES-004 AX4 focused tests — typed named ports are the whole seam.

Claims under test:

- Two independently authored subnets (AX3 shape M, AX3 comment gate)
  fuse through one named typed port plus a pure adapter; the result
  is sound, context-free, and keeps every other exit intact.
- A color mismatch is caught at COMPOSITION time with an error naming
  both ports — the typed port replaces the shared-place discipline.
- The same static check catches protocol drift: AX2's fence-era
  publisher refuses to compose into an attempt-first chain, because
  its entry color still encodes the fence protocol.
- End to end on the real engine: committed → announced → acknowledged;
  moved → nothing announced.
- The full control loop (AX7 Execute in, AX6 CommitGateFired out,
  confirmed resume) runs with ZERO control places in the compiled
  net — and mutation serialization falls out of the control state
  where production needs MutationState.change_in_flight.
"""

from __future__ import annotations

import pytest
from ax2_linear_review import draft_publication, publish_findings
from ax2_linear_review import fresh_world as fence_era_world
from ax4_composition import announce_commit, fresh_world, mutation_with_announcement
from ax6_quiescence import CommitGateFired, ObservedOpen, Quiescent, Resume, Running, step
from ax7_conversations import Decline, Execute, service
from ax23_blocks import BoundaryTransition, CompositionError, check_sound, compile_block, then
from ax3_attempt_first import mutation_subnet, publish_comment
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data


def run(block, seed_color, seed_data, instance="es4-ax4"):
    lowered = compile_block("es4-ax4-net", block)
    engine = Engine.create(
        lowered.built.net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking({NetPath(block.entry.place): (Token(seed_color, dict(seed_data)),)}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )
    drive_bounded(engine)
    return engine


def exit_data(engine, block, name):
    return place_data(engine, block.exits[name].place)


# -- structure: one port consumed, everything else intact --------------------------------


def test_two_subnets_fuse_through_one_typed_port():
    block = check_sound(mutation_with_announcement(fresh_world()))
    assert block.contexts == {}  # NO shared control place — the AX4 claim itself
    assert set(block.exits) == {"acknowledged", "moved", "fault", "failed"}
    transitions = [n for n in block.nodes if isinstance(n, BoundaryTransition)]
    assert len(transitions) == 5  # 3 (shape M) + 1 adapter + 1 comment gate


# -- the static seam: typed ports replace shared-place discipline -------------------------


def test_color_mismatch_is_caught_at_composition_time():
    world = fresh_world()
    with pytest.raises(CompositionError) as caught:
        then(mutation_subnet(world), publish_comment(world), on="committed")
    assert "ProvisionalHead" in str(caught.value)
    assert "FindingPublicationRequest" in str(caught.value)


def test_fence_era_protocol_drift_is_caught_by_the_same_check():
    """AX2's publisher still accepts `FencedPublication` — its entry
    color encodes the fence protocol AX3 retired. The port refuses the
    anachronism statically; no runtime surprise, no silent misroute."""
    with pytest.raises(CompositionError) as caught:
        then(draft_publication(), publish_findings(fence_era_world()), on="out")
    assert "FindingPublicationRequest" in str(caught.value)
    assert "FencedPublication" in str(caught.value)


# -- behavior on the real engine -----------------------------------------------------------


def test_committed_work_flows_through_the_port_and_gets_announced():
    world = fresh_world(head="h1")
    block = mutation_with_announcement(world)
    engine = run(block, "ChangeRequest", {"operation": "op-change-7", "expected_head": "h1"})
    [ack] = exit_data(engine, block, "acknowledged")
    assert ack == {"comment_id": 1, "reused": False}
    [comment] = world["comments"]
    assert comment["marker"] == ["finding", "announce-commit-of-op-change-7", "commit-of-op-change-7"]
    assert world["branch"]["head"] == "commit-of-op-change-7"


def test_moved_branch_never_reaches_the_announcement_subnet():
    world = fresh_world(head="h2-someone-pushed")
    block = mutation_with_announcement(world)
    engine = run(block, "ChangeRequest", {"operation": "op-change-7", "expected_head": "h1"})
    [moved] = exit_data(engine, block, "moved")
    assert moved == {"expected": "h1", "actual": "h2-someone-pushed"}
    assert exit_data(engine, block, "acknowledged") == []
    assert world["comments"] == []  # the downstream subnet simply never fired


# -- the loop back through control: data, not a place ---------------------------------------


def test_the_full_loop_runs_with_zero_control_places():
    """AX7 Execute in → net → AX6 CommitGateFired out → confirmed
    resume. The compiled net contains no authority, mutation-state, or
    control place — the loop is closed by values crossing ports."""
    world = fresh_world(head="h1")
    block = mutation_with_announcement(world)

    state = Running(epoch=3, head="h1")
    outcome = service(state, "change")
    assert outcome == Execute("change", epoch=3, head="h1")

    engine = run(block, "ChangeRequest", {"operation": "op-change-7", "expected_head": outcome.head})
    [committed_head] = {c["marker"][2] for c in world["comments"]}

    state, actions = step(state, CommitGateFired(committed_head))
    assert state == Quiescent(3, "h1", expected=committed_head)

    state, actions = step(state, ObservedOpen(committed_head))
    assert state == Running(4, committed_head)
    assert actions == (Resume(4, committed_head, "confirmed"),)

    lowered = compile_block("es4-ax4-net", block)
    place_names = {str(path) for path in lowered.built.net.places}
    assert not {name for name in place_names if "authority" in name or "state" in name or "control" in name}
    assert block.contexts == {}


def test_mutation_serialization_needs_no_change_in_flight_flag():
    """Production serializes mutations via MutationState.change_in_flight,
    read-arced into authorize_change (topology.py:1426,1672). Here the
    same guarantee is a consequence of control state: while our commit
    awaits observation, a second change conversation is DECLINED — no
    flag, no place, no read arc."""
    state = Quiescent(3, "h1", expected="commit-of-op-change-7")
    outcome = service(state, "change")
    assert isinstance(outcome, Decline)
    assert "awaits observation" in outcome.reason


# -- the payload-thinness finding -----------------------------------------------------------


def test_ports_check_colors_not_payload_fields():
    """Recorded limitation, not a triumph: the adapter composes even
    though `ProvisionalHead` lost the original `operation` — color
    compatibility cannot promise field compatibility. The marker is
    derived from the head; the port contract needs payload shape too
    (fed to AX5 as a design requirement)."""
    block = then(mutation_subnet(fresh_world()), announce_commit(), on="committed")
    assert "out" in block.exits  # fused despite the thin payload — the gap this test records
