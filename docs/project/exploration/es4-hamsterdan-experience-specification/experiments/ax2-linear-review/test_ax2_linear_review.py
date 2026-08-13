"""ES-004 AX2 focused tests — linearity, discard, and the two
idempotency kinds, on the review subnet expressed as a block chain.

Claims under test:

- The AX1 contract compiles and is sound: exits are exactly
  {acknowledged, stale, failed, blocked} plus the declared authority
  context — the shared exit vocabulary made real.
- Happy path runs entry→acknowledged linearly; stale authority
  discards BEFORE the gate (the world never sees the publication).
- Kind-1 idempotency: lookup-first returns the existing comment.
- Kind-2 shape: capability failure is a classified exit (blocked),
  not an exception.
- The net is measurably linear (Navigator's arcs-to-nodes hunch).
- The algebra's `pure` cannot express "disposable effect" — captured
  as a shaped gap, not patched.
"""

from __future__ import annotations

import pytest
from ax23_blocks import CompositionError, check_sound, compile_block, disposable
from ax2_linear_review import AgentOutage, fresh_world, prepare_basis, review_subnet, run_agent
from ax25_rail import rail_then
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data

AUTHORITY = {"epoch": 3, "head": "h2", "base_head": "b1"}
REQUEST = {"epoch": 3, "head": "h2", "base_head": "b1", "operation": "op-review-3"}


def run(block, world, request=REQUEST, authority=AUTHORITY, instance="es4-ax2"):
    lowered = compile_block("es4-ax2-review", block)
    engine = Engine.create(
        lowered.built.net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking(
            {
                NetPath(block.entry.place): (Token("ReviewRequest", dict(request)),),
                NetPath("authority"): (Token("Authority", dict(authority)),),
            }
        ),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )
    drive_bounded(engine)
    return engine


def exit_data(engine, block, name):
    return place_data(engine, block.exits[name].place)


# -- contract shape ------------------------------------------------------------------


def test_exits_are_exactly_the_ax1_vocabulary():
    block = review_subnet(fresh_world())
    assert set(block.exits) == {"acknowledged", "stale", "failed", "blocked"}
    assert set(block.contexts) == {"authority"}
    assert block.exits["acknowledged"].color == "FindingPublicationResult"
    assert block.exits["stale"].color == "StaleAuthority"
    assert block.exits["failed"].color == "Failure"
    assert block.exits["blocked"].color == "RecoverableFault"
    check_sound(block)


def test_the_net_is_measurably_linear():
    """Navigator's hunch: a linear net keeps arcs proportional to
    nodes. Here every transition has exactly one consume (plus at
    most one declared context read), so arcs ≈ places + exits — no
    combinatorial wiring anywhere."""
    from ax23_blocks import BoundaryTransition, KernelPlace, Mode

    block = review_subnet(fresh_world())
    places = [n for n in block.nodes if isinstance(n, KernelPlace)]
    transitions = [n for n in block.nodes if isinstance(n, BoundaryTransition)]
    arcs = [arc for t in transitions for arc in t.arcs]
    consumes = [a for a in arcs if a.mode is Mode.CONSUME]
    # strict linearity: every transition consumes exactly one token
    assert all(len([a for a in t.arcs if a.mode is Mode.CONSUME]) == 1 for t in transitions)
    # the whole subnet: 5 work transitions, no hidden fan-in
    assert len(transitions) == 5
    assert len(consumes) == len(transitions)
    # arcs stay linear in node count (here: below 1.2 arcs per node)
    assert len(arcs) / (len(places) + len(transitions)) < 1.2


# -- behavior ------------------------------------------------------------------------


def test_happy_path_publishes_once():
    world = fresh_world()
    block = review_subnet(world)
    engine = run(block, world)
    [result] = exit_data(engine, block, "acknowledged")
    assert result == {"comment_id": 1, "reused": False}
    assert world["agent_runs"] == 1
    assert [c["marker"] for c in world["comments"]] == [["finding", "op-review-3", "h2"]]
    for other in ("stale", "failed", "blocked"):
        assert exit_data(engine, block, other) == []


def test_stale_authority_discards_before_the_gate():
    """Work ran (the agent was paid) but the world was never touched:
    the fence catches the moved head and the token exits 'stale'."""
    world = fresh_world()
    block = review_subnet(world)
    engine = run(block, world, authority={"epoch": 4, "head": "h3", "base_head": "b1"})
    [discard] = exit_data(engine, block, "stale")
    assert discard == {"basis": [3, "h2", "b1"], "authority": [4, "h3", "b1"]}
    assert world["agent_runs"] == 1  # the work happened…
    assert world["comments"] == []  # …and was discarded, unpublished
    assert exit_data(engine, block, "acknowledged") == []


def test_kind1_idempotency_lookup_first_reuses_the_comment():
    world = fresh_world()
    world["comments"].append({"id": 7, "marker": ["finding", "op-review-3", "h2"], "findings": []})
    block = review_subnet(world)
    engine = run(block, world)
    [result] = exit_data(engine, block, "acknowledged")
    assert result == {"comment_id": 7, "reused": True}
    assert len(world["comments"]) == 1  # no duplicate


def test_transient_agent_failure_takes_the_rail():
    world = fresh_world()
    world["agent_down"] = True
    block = review_subnet(world)
    engine = run(block, world)
    [envelope] = exit_data(engine, block, "failed")
    assert envelope["kind"] == "AgentOutage"
    assert envelope["source"] == "run_agent"
    assert envelope["retryable"] is True
    assert world["comments"] == []


def test_capability_failure_is_a_classified_exit_not_an_exception():
    world = fresh_world()
    world["github_down"] = True
    block = review_subnet(world)
    engine = run(block, world)
    [fault] = exit_data(engine, block, "blocked")
    assert fault == {"kind": "capability", "operation": "op-review-3", "retryable": True}
    assert world["agent_runs"] == 1


# -- the shaped gap ------------------------------------------------------------------


def test_the_algebra_cannot_say_disposable_effect():
    """AX1 classified the agent call as a *disposable effect*: it
    spends money but mutates nothing observable. The ES-003 algebra
    only knows pure/effectful, so `disposable` refuses the interior —
    the purity model needs a third level. Captured, not patched."""
    world = fresh_world()
    interior = rail_then(prepare_basis(), run_agent(world))
    with pytest.raises(CompositionError, match="not pure"):
        disposable(interior)
