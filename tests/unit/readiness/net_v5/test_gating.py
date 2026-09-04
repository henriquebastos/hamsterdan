"""Durable execution policy and crash projection for V5 publication gates."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from harness import fresh_world, make_activities
from petrus.engine import Engine, choose_throughput
from petrus.impetus.history import ActivityFailed, ActivityRequested, FiringCompleted, FiringFailed
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import ActivityFailure
from petrus.motus.dispatch import LocalDispatch

from hamsterdan.contracts.readiness_v5 import (
    AnnounceReq,
    CommentSeen,
    DashReq,
    ReplyReq,
)
from hamsterdan.readiness.net_v5 import build_net_v5, seed_marking
from hamsterdan.readiness.net_v5.gating import wire_gates
from hamsterdan.readiness.net_v5.topology import DERIVED, GATES

INSTANCE = "test:v5-publication-recovery"
QUEUE = "v5-publication:test"
PUBLICATION_QUEUES = {
    "reply_gate": QUEUE,
    "dash_gate": QUEUE,
    "announce_gate": QUEUE,
}


def _replace(marking: Marking, place: str, color: str, data: dict) -> Marking:
    path = NetPath(place)
    existing = marking.place(path)
    return marking.consume(path, existing).deposit(path, Token(color, data))


def _marking(work: ReplyReq | DashReq | AnnounceReq) -> Marking:
    marking = seed_marking(INSTANCE)
    # This fixture represents an already-started publication, including legacy History.
    pending = NetPath("startup.pending")
    marking = marking.consume(pending, marking.place(pending))
    if isinstance(work, ReplyReq):
        [memory] = marking.place(NetPath("conv.memory"))
        marking = _replace(
            marking,
            "conv.memory",
            "ConvMemory",
            {**memory.data, "pending": {work.id: work.text}},
        )
        place = "conv.reply_req"
    elif isinstance(work, DashReq):
        path = NetPath("dash.memory")
        marking = marking.consume(path, marking.place(path))
        place = "dash.pub_req"
    else:
        [snapshot] = marking.place(NetPath("ready.snap"))
        marking = _replace(
            marking,
            "ready.snap",
            "Snapshot",
            {**snapshot.data, "announcing": work.dump()},
        )
        place = "ready.announce_req"
    return marking.deposit(NetPath(place), Token(type(work).__name__, work.dump()))


def _open(root: Path, *, create: bool, marking: Marking | None = None) -> Engine:
    built = build_net_v5()
    definitions = {definition.declaration.name: definition for definition in make_activities(fresh_world())}
    history = JsonlHistoryStore(root / "history.jsonl")
    dispatch = LocalDispatch(
        root / "dispatch.sqlite3",
        instance=INSTANCE,
        activity_queues=PUBLICATION_QUEUES,
    )
    handlers = wire_gates(built, GATES, definitions, DERIVED)
    activities = tuple(definition.declaration for definition in definitions.values())
    if create:
        return Engine.create(
            built.net,
            INSTANCE,
            history=history,
            dispatch=dispatch,
            marking=marking,
            handlers=handlers,
            guards=dict(built.guards),
            activities=activities,
            policy=choose_throughput,
        )
    return Engine.load(
        built.net,
        INSTANCE,
        history=history,
        dispatch=dispatch,
        handlers=handlers,
        guards=dict(built.guards),
        activities=activities,
        policy=choose_throughput,
    )


def _requests(engine: Engine, activity: str, work: ReplyReq | DashReq | AnnounceReq) -> list[ActivityRequested]:
    return [
        record
        for record in engine.records
        if isinstance(record, ActivityRequested)
        and record.activity == activity
        and record.input == {"work": work.dump()}
    ]


def _advance_until(engine: Engine, condition, limit: int = 100) -> None:
    for _ in range(limit):
        if condition():
            return
        engine.advance()
    raise AssertionError(f"V5 Engine did not reach the expected state in {limit} advances")


def _retained(engine: Engine, work: ReplyReq | DashReq | AnnounceReq) -> bool:
    if isinstance(work, ReplyReq):
        [memory] = engine.marking.place(NetPath("conv.memory"))
        return memory.data["blocked"] == {work.id: work.text}
    if isinstance(work, DashReq):
        memories = engine.marking.place(NetPath("dash.memory"))
        if not memories:
            return False
        [memory] = memories
        return memory.data["blocked"] == {"entries": work.entries, "digest": work.digest}
    [snapshot] = engine.marking.place(NetPath("ready.snap"))
    return snapshot.data["blocked"] == work.dump()


def _operation(work: ReplyReq | DashReq | AnnounceReq) -> str:
    if isinstance(work, ReplyReq):
        return f"reply:{work.id}"
    if isinstance(work, DashReq):
        return f"dash:{work.digest}"
    return work.op


@pytest.mark.parametrize(
    ("activity", "work", "recover_op"),
    [
        ("reply_gate", ReplyReq(id="comment-7", text="exact reply"), "reply:comment-7"),
        (
            "dash_gate",
            DashReq(
                entries=["attempted"],
                digest="digest-attempted",
                desired_entries=["attempted", "newer"],
                desired_digest="digest-newer",
            ),
            "dash:digest-attempted",
        ),
        (
            "announce_gate",
            AnnounceReq(
                op="ready:head-1:i3",
                incarnation=3,
                head="head-1",
                base="base-1",
                policy="policy-1",
            ),
            "ready:head-1:i3",
        ),
    ],
)
def test_expired_publication_claim_projects_blocked_and_only_explicit_recovery_reissues(
    tmp_path: Path,
    activity: str,
    work: ReplyReq | DashReq | AnnounceReq,
    recover_op: str,
) -> None:
    engine = _open(tmp_path, create=True, marking=_marking(work))
    _advance_until(engine, lambda: bool(_requests(engine, activity, work)))
    [requested] = _requests(engine, activity, work)
    operation = _operation(work)
    worker = LocalDispatch(tmp_path / "dispatch.sqlite3", instance="worker").worker((QUEUE,))
    attempt = worker.claim()

    assert attempt is not None
    assert attempt.epoch == "1" and attempt.invocation.policy.attempts == 1
    assert requested.correlation == requested.idempotency == operation
    assert attempt.invocation.correlation == attempt.invocation.idempotency == operation
    assert attempt.invocation.input == {"work": work.dump()}

    with sqlite3.connect(tmp_path / "dispatch.sqlite3") as connection:
        connection.execute(
            "UPDATE impetus_local_dispatch_tasks SET deadline=0,attempt_deadline=0 WHERE instance=? AND occurrence=?",
            (INSTANCE, requested.occurrence),
        )
    assert worker.claim() is None  # the expired sole attempt becomes a durable terminal
    worker.close()
    engine.close()

    restarted = _open(tmp_path, create=False)
    _advance_until(restarted, lambda: _retained(restarted, work))
    failures = [record for record in restarted.records if isinstance(record, ActivityFailed)]

    assert len(failures) == 1
    assert failures[0].occurrence == requested.occurrence and failures[0].kind == "DeadlineExceeded"
    assert any(
        isinstance(record, FiringCompleted) and record.occurrence == requested.occurrence
        for record in restarted.records
    )
    assert not any(
        isinstance(record, FiringFailed) and record.occurrence == requested.occurrence for record in restarted.records
    )
    assert _requests(restarted, activity, work) == [requested]

    restarted.close()
    stable = _open(tmp_path, create=False)
    before = stable.records
    stable.advance()
    assert stable.records == before
    assert _requests(stable, activity, work) == [requested]

    stable.deliver(
        "on_comment",
        Token(
            "CommentSeen",
            CommentSeen(
                id=f"recover-{activity}",
                kind="recover_publication",
                arg=recover_op,
                authorized=True,
            ).dump(),
        ),
        identity=f"recover-{activity}",
    )

    def activity_requests():
        return [
            record
            for record in stable.records
            if isinstance(record, ActivityRequested) and record.activity == activity and record.correlation == operation
        ]

    _advance_until(stable, lambda: len(activity_requests()) == 2)
    original, recovered = activity_requests()

    assert original == requested
    assert recovered.occurrence != original.occurrence
    if isinstance(work, DashReq):
        original_work = original.input["work"]
        recovered_work = recovered.input["work"]
        effect_fields = ("entries", "digest", "desired_entries", "desired_digest", "landed")
        assert {field: recovered_work[field] for field in effect_fields} == {
            field: original_work[field] for field in effect_fields
        }
        assert recovered_work["blocked"] == {"entries": work.entries, "digest": work.digest}
        assert recovered_work["faulted"] == {}
    else:
        assert recovered.input == original.input == {"work": work.dump()}
    assert recovered.correlation == recovered.idempotency == operation
    stable.close()


def test_unknown_publication_failure_stays_projection_pending_and_fails_loudly(tmp_path: Path) -> None:
    work = AnnounceReq(
        op="ready:head-1:i3",
        incarnation=3,
        head="head-1",
        base="base-1",
        policy="policy-1",
    )
    engine = _open(tmp_path, create=True, marking=_marking(work))
    _advance_until(engine, lambda: bool(_requests(engine, "announce_gate", work)))
    [requested] = _requests(engine, "announce_gate", work)
    worker = LocalDispatch(tmp_path / "dispatch.sqlite3", instance="worker").worker((QUEUE,))
    attempt = worker.claim()
    assert attempt is not None
    worker.fail(
        attempt,
        ActivityFailure("unclassified provider terminal", kind="UnexpectedFailure", retryable=False),
    )
    worker.close()
    engine.close()

    restarted = _open(tmp_path, create=False)
    with pytest.raises(RuntimeError, match="UnexpectedFailure.*cannot be projected"):
        restarted.advance()

    history = JsonlHistoryStore(tmp_path / "history.jsonl").records
    assert (
        len(
            [
                record
                for record in history
                if isinstance(record, ActivityFailed) and record.occurrence == requested.occurrence
            ]
        )
        == 1
    )
    assert not any(isinstance(record, FiringFailed) and record.occurrence == requested.occurrence for record in history)


def test_restart_settles_a_legacy_unlanded_announcement_moved_without_posting(tmp_path: Path) -> None:
    legacy = {
        "op": "ready:h1:i1",
        "incarnation": 1,
        "head": "h1",
        "base": "b1",
        "policy": "p1",
    }
    marking = seed_marking(INSTANCE)
    # This fixture represents an already-started publication, including legacy History.
    pending = NetPath("startup.pending")
    marking = marking.consume(pending, marking.place(pending))
    [snapshot] = marking.place(NetPath("ready.snap"))
    retained = {
        **snapshot.data,
        "incarnation": 1,
        "phase": "running",
        "head": "h1",
        "base": "b1",
        "policy": "p1",
        "mergeable": True,
        "checks": "success",
        "review": "clear",
        "approval": True,
        "announcing": legacy,
    }
    retained.pop("strict_base")
    retained.pop("base_current")
    marking = _replace(marking, "ready.snap", "Snapshot", retained)
    marking = marking.deposit(NetPath("ready.announce_req"), Token("AnnounceReq", legacy))
    first = _open(tmp_path, create=True, marking=marking)
    _advance_until(
        first,
        lambda: any(
            isinstance(record, ActivityRequested) and record.activity == "announce_gate" for record in first.records
        ),
    )
    [requested] = [
        record
        for record in first.records
        if isinstance(record, ActivityRequested) and record.activity == "announce_gate"
    ]
    assert requested.input == {"work": legacy}
    first.close()

    world = fresh_world()
    world.update({"branch_head": "h1", "base_head": "b1", "policy": "p1"})
    world["authority"] = {"incarnation": 1, "phase": "running", "head": "h1", "base": "b1", "policy": "p1"}
    definitions = {definition.declaration.name: definition for definition in make_activities(world)}
    restarted = _open(tmp_path, create=False)
    worker = LocalDispatch(tmp_path / "dispatch.sqlite3", instance="worker").worker((QUEUE,))
    attempt = worker.claim()
    assert attempt is not None and attempt.invocation.input == {"work": legacy}
    worker.complete(attempt, definitions["announce_gate"](attempt.invocation, context=None))
    worker.close()
    _advance_until(
        restarted,
        lambda: (
            bool(restarted.marking.place(NetPath("ready.snap")))
            and restarted.marking.place(NetPath("ready.snap"))[0].data["announcing"] == {}
        ),
    )
    [settled] = restarted.marking.place(NetPath("ready.snap"))
    assert world["comments"] == []
    assert settled.data["base_current"] is False
    assert settled.data["candidate"] is False
    restarted.close()
