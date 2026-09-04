from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from deployment.observation import observe


def state(root: Path) -> Path:
    history = root / "applications/44/31/7/history.jsonl"
    history.parent.mkdir(parents=True)
    history.write_text(
        json.dumps(
            {
                "record": "ActivityCompleted",
                "instant": 123,
                "occurrence": 207,
                "transition": "conv.reply",
                "result": {"$variant": "ReplyBlocked", "text": "SECRET-REPLY"},
                "input": {"token": "SECRET-INPUT"},
            }
        )
        + "\n"
    )
    with sqlite3.connect(root / "activity-dispatch.sqlite3") as db:
        db.executescript("""
            CREATE TABLE impetus_local_dispatch_schema(component TEXT, version INTEGER);
            INSERT INTO impetus_local_dispatch_schema VALUES('dispatch',3);
            CREATE TABLE impetus_local_dispatch_tasks(
                sequence INTEGER, instance TEXT, occurrence INTEGER, epoch INTEGER, deadline INTEGER,
                schedule_start INTEGER, attempt_start INTEGER, attempt_deadline INTEGER, available_at INTEGER,
                invocation TEXT, claimant TEXT);
            CREATE TABLE impetus_local_dispatch_terminals(instance TEXT, occurrence INTEGER);
        """)
        db.execute(
            "INSERT INTO impetus_local_dispatch_tasks VALUES(1,?,207,1,200,100,101,300,100,?,?)",
            (
                "github:44:31:pr:7",
                json.dumps({"activity": "reply_gate", "input": "SECRET-INVOCATION"}),
                "SECRET-CLAIMANT",
            ),
        )
        db.execute("INSERT INTO impetus_local_dispatch_terminals VALUES('github:44:31:pr:7',207)")
    with sqlite3.connect(root / "webhooks.sqlite3") as db:
        db.execute(
            "CREATE TABLE inbox(delivery_id TEXT,event TEXT,status TEXT,attempts INTEGER,error_class TEXT,next_attempt_at REAL,observation TEXT)"
        )
        for pr in (7, 8):
            db.execute(
                "INSERT INTO inbox VALUES(?, 'pull_request','pending',0,NULL,0,?)",
                (
                    f"delivery-{pr}",
                    json.dumps(
                        {
                            "installation_id": 44,
                            "repository_id": 31,
                            "pull_request_number": pr,
                            "body": "SECRET-WEBHOOK",
                        }
                    ),
                ),
            )
    return history


def test_operator_can_correlate_blocked_reply_without_exporting_payloads(tmp_path: Path) -> None:
    history = state(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    events = observe(tmp_path, 44, 31, 7)

    assert [event["layer"] for event in events] == ["history", "dispatch", "inbox"]
    assert events[0]["result_variant"] == "ReplyBlocked"
    assert events[0]["occurrence"] == events[1]["occurrence"] == 207
    assert events[1]["state"] == "terminal"
    assert events[2]["delivery_id"] == "delivery-7"
    assert "SECRET" not in json.dumps(events)
    assert before == {path: path.read_bytes() for path in before}
    assert history.exists()


def test_observation_refuses_symlinked_state(tmp_path: Path) -> None:
    history = state(tmp_path)
    target = history.with_suffix(".original")
    history.rename(target)
    history.symlink_to(target)

    with pytest.raises(ValueError, match="symlink"):
        observe(tmp_path, 44, 31, 7)


def test_observation_refuses_an_unknown_dispatch_schema(tmp_path: Path) -> None:
    state(tmp_path)
    with sqlite3.connect(tmp_path / "activity-dispatch.sqlite3") as db:
        db.execute("UPDATE impetus_local_dispatch_schema SET version=99")

    with pytest.raises(ValueError, match="schema 3"):
        observe(tmp_path, 44, 31, 7)
