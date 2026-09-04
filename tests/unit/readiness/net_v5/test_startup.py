"""Initial summary setup precedes effects without joining the update loop."""

import pytest
from harness import (
    comment,
    comment_held,
    deliver,
    deliver_held,
    one,
    release_one,
    see_head,
    spawn,
    spawn_held,
    tokens,
    world_of,
)
from petrus.impetus.history import ActivityRequested


def test_summary_is_the_only_activity_until_initial_publication_succeeds() -> None:
    engine, _, dispatch, definitions = spawn_held()
    hold = frozenset({"dash_gate"})
    deliver_held(
        engine,
        dispatch,
        definitions,
        "on_head",
        "HeadSeen",
        {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
        hold=hold,
    )
    comment_held(engine, dispatch, definitions, "question", "status", hold=hold)
    comment_held(engine, dispatch, definitions, "repair", "change", arg="repair the code", hold=hold)
    deliver_held(
        engine,
        dispatch,
        definitions,
        "on_runs",
        "RunSeen",
        {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "failure", "fingerprint": "fp1"},
        hold=hold,
    )

    assert [record.activity for record in engine.records if isinstance(record, ActivityRequested)] == ["dash_gate"]
    world = world_of(engine)
    assert world["agent_calls"] == 0
    assert world["comments"] == world["pushes"] == world["reruns"] == []

    release_one(engine, dispatch, definitions, "dash_gate")

    assert world["dashboard"]
    requested = {record.activity for record in engine.records if isinstance(record, ActivityRequested)}
    assert {"review_agent", "reply_gate", "git_gate", "rerun_gate"} <= requested
    assert world["pushes"] and world["comments"]
    assert tokens(engine, "startup.pending") == []
    assert tokens(engine, "startup.published") == []


@pytest.mark.parametrize("failure", ["retryable", "unknown"])
def test_failed_initial_summary_recovers_before_queued_work_starts(failure: str) -> None:
    engine, _ = spawn()
    world = world_of(engine)
    world["dash_mode"] = failure
    see_head(engine, "h1")
    comment(engine, "question", "status")
    assert world["agent_calls"] == 0
    assert world["comments"] == []
    memory = one(engine, "dash.memory")
    retained = memory["blocked"] or memory["faulted"]
    assert tokens(engine, "startup.pending")

    world["dash_mode"] = None
    comment(engine, "recover", "recover_publication", arg=f"dash:{retained['digest']}")

    assert world["dashboard"] and world["agent_calls"] == 1
    assert tokens(engine, "startup.pending") == []


@pytest.mark.parametrize("failure", ["retryable", "unknown"])
def test_later_summary_failure_does_not_suspend_reviews_or_replies(failure: str) -> None:
    engine, _ = spawn()
    world = world_of(engine)
    see_head(engine, "h1")
    initial_board = list(world["dashboard"])
    world["dash_mode"] = failure

    see_head(engine, "h2")
    comment(engine, "question", "status")

    assert world["dashboard"] == initial_board
    assert world["agent_calls"] == 2
    assert any(item["key"] == "reply:question" for item in world["comments"])
    assert tokens(engine, "startup.pending") == []


def test_close_while_initial_summary_is_in_flight_never_starts_the_agent() -> None:
    engine, _, dispatch, definitions = spawn_held()
    deliver_held(
        engine,
        dispatch,
        definitions,
        "on_head",
        "HeadSeen",
        {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
        hold=frozenset({"dash_gate"}),
    )
    deliver_held(
        engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "closed"}, hold=frozenset({"dash_gate"})
    )

    release_one(engine, dispatch, definitions, "dash_gate")

    assert world_of(engine)["agent_calls"] == 0
    assert one(engine, "review.done")["reason"] == "closed"


def test_initial_draft_defers_startup_until_the_pr_is_ready() -> None:
    engine, _ = spawn()
    deliver(engine, "on_draft", "DraftSeen", {})
    see_head(engine, "h1")
    assert world_of(engine)["dashboard"] == []
    assert world_of(engine)["agent_calls"] == 0
    assert tokens(engine, "startup.pending")

    deliver(engine, "on_ready", "ReadySeen", {})

    assert world_of(engine)["dashboard"]
    assert world_of(engine)["agent_calls"] == 1
    assert tokens(engine, "startup.pending") == []
