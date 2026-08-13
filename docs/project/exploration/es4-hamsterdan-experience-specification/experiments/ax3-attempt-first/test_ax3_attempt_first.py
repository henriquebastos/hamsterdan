"""ES-004 AX3 focused tests — the operation is the fence.

Claims under test:

- Shape M attempt-first needs NO authority context: the subnet is
  context-free, and its transition count drops versus the fenced
  AX2 style.
- The CAS gate turns a moved branch into the `moved` (discarded)
  exit — kind-2 idempotency as classification, never an error, never
  a forced push.
- Kind-1 at the git gate: commit trailers make replay reuse the
  existing commit; a trailer collision is a fault.
- The comment gate without a pre-fence: a stale comment LANDS
  (GitHub-verified behavior), marked outdated, identifiable by the
  head in its marker — toleration, not prevention.
"""

from __future__ import annotations

from ax23_blocks import BoundaryTransition, Mode, check_sound, compile_block
from ax3_attempt_first import fresh_world, mutation_subnet, publish_comment
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data

REQUEST = {"operation": "op-change-7", "expected_head": "h1"}


def run(block, seed_color, seed_data, instance="es4-ax3"):
    lowered = compile_block("es4-ax3-net", block)
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


# -- structure: the fence transition is gone -----------------------------------------


def test_shape_m_is_context_free_and_smaller():
    block = mutation_subnet(fresh_world())
    assert block.contexts == {}  # no authority place, no read arcs — nothing ambient
    assert set(block.exits) == {"committed", "moved", "fault", "failed"}
    transitions = [n for n in block.nodes if isinstance(n, BoundaryTransition)]
    assert len(transitions) == 3  # AX2's fenced style needed 5 for the same span
    assert all(len([a for a in t.arcs if a.mode is Mode.CONSUME]) == 1 for t in transitions)
    check_sound(block)


# -- the CAS gate ---------------------------------------------------------------------


def test_happy_path_commits_and_returns_provisional_head():
    world = fresh_world(head="h1")
    block = mutation_subnet(world)
    engine = run(block, "ChangeRequest", REQUEST)
    [result] = exit_data(engine, block, "committed")
    assert result == {"provisional_head": "commit-of-op-change-7", "reused": False}
    assert world["branch"]["head"] == "commit-of-op-change-7"


def test_moved_branch_is_a_classified_discard_not_an_error():
    """The agent worked (money spent); the CAS rejects; the branch is
    untouched; the exit says 'preconditions changed'. No pre-check
    anywhere — the provider's own atomicity carried the fence."""
    world = fresh_world(head="h2-someone-pushed")
    block = mutation_subnet(world)
    engine = run(block, "ChangeRequest", REQUEST)
    [moved] = exit_data(engine, block, "moved")
    assert moved == {"expected": "h1", "actual": "h2-someone-pushed"}
    assert world["agent_runs"] == 1
    assert world["branch"]["head"] == "h2-someone-pushed"  # we never forced anything
    assert exit_data(engine, block, "committed") == []


def test_kind1_replay_reuses_the_commit_by_trailers():
    world = fresh_world(head="h1")
    block = mutation_subnet(world)
    run(block, "ChangeRequest", REQUEST)
    replay_world_head = world["branch"]["head"]
    block2 = mutation_subnet(world)
    engine = run(block2, "ChangeRequest", REQUEST, instance="es4-ax3-replay")
    [result] = exit_data(engine, block2, "committed")
    assert result == {"provisional_head": replay_world_head, "reused": True}
    assert world["agent_runs"] == 2  # the work reran; the WORLD effect did not


def test_trailer_collision_is_a_fault():
    world = fresh_world(head="h1")
    world["branch"] = {"head": "h1", "trailers": {"operation": "op-change-7", "digest": "someone-elses"}}
    block = mutation_subnet(world)
    engine = run(block, "ChangeRequest", REQUEST)
    [fault] = exit_data(engine, block, "fault")
    assert fault == {"kind": "trailer_collision", "operation": "op-change-7"}


# -- the comment gate, attempt-first ---------------------------------------------------


def test_stale_comment_lands_as_tolerated_outdated_noise():
    """GitHub-verified: a comment for a moved head cannot fail. It
    lands, flagged outdated, forever identifiable by the head in its
    marker. Supersession — not prevention — owns staleness here."""
    world = fresh_world(head="h9-current")
    block = publish_comment(world)
    engine = run(block, "FindingPublicationRequest", {"operation": "op-review-3", "head": "h2-old"})
    [result] = exit_data(engine, block, "acknowledged")
    assert result == {"comment_id": 1, "reused": False}
    [comment] = world["comments"]
    assert comment["outdated"] is True
    assert comment["marker"] == ["finding", "op-review-3", "h2-old"]  # self-identifying


def test_current_comment_lands_clean():
    world = fresh_world(head="h2")
    block = publish_comment(world)
    engine = run(block, "FindingPublicationRequest", {"operation": "op-review-4", "head": "h2"})
    [comment] = world["comments"]
    assert comment["outdated"] is False
    assert exit_data(engine, block, "acknowledged") == [{"comment_id": 1, "reused": False}]
