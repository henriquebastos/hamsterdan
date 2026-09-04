"""Read-only, payload-free projections of production runtime stores."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

ATOM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,255}\Z")
MAX_HISTORY_BYTES = 64 * 1024 * 1024


def atom(value: object) -> str | None:
    return value if isinstance(value, str) and ATOM.fullmatch(value) else None


def number(value: object) -> int | float | None:
    return value if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value) else None


def regular(path: Path) -> Path:
    if path.resolve() != path.absolute() or not path.is_file():
        raise ValueError("Observation requires regular files without symlink components")
    return path


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{regular(path).as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.row_factory = sqlite3.Row
    return connection


def observe(root: Path, installation: int, repository: int, pr: int) -> list[dict[str, object]]:
    if min(installation, repository, pr) <= 0:
        raise ValueError("Observation identifiers must be positive")
    instance = f"github:{installation}:{repository}:pr:{pr}"
    path = regular(root / "applications" / str(installation) / str(repository) / str(pr) / "history.jsonl")
    with path.open("rb") as stream:
        content = stream.read(MAX_HISTORY_BYTES + 1)
    if len(content) > MAX_HISTORY_BYTES:
        raise ValueError("History exceeds the observation size bound")
    events: list[dict[str, object]] = []
    for sequence, line in enumerate(content.splitlines(), start=1):
        record = json.loads(line)
        result = record.get("result")
        failure = record.get("failure")
        events.append(
            {
                "layer": "history",
                "instance": instance,
                "sequence": sequence,
                "record": atom(record.get("record")),
                "instant": number(record.get("instant")),
                "occurrence": number(record.get("occurrence")),
                "transition": atom(record.get("transition")),
                "activity": atom(record.get("activity")),
                "result_variant": atom(result.get("$variant")) if isinstance(result, dict) else None,
                "failure_kind": atom(failure.get("kind")) if isinstance(failure, dict) else None,
            }
        )
    database = connect(root / "activity-dispatch.sqlite3")
    try:
        version = database.execute(
            "SELECT version FROM impetus_local_dispatch_schema WHERE component='dispatch'"
        ).fetchone()
        if version is None or version[0] != 3:
            raise ValueError("Observation requires LocalDispatch schema 3")
        rows = database.execute(
            "SELECT t.occurrence,t.epoch,t.deadline,t.schedule_start,t.attempt_start,t.attempt_deadline,t.available_at,"
            "json_extract(t.invocation,'$.activity') AS activity,"
            "CASE WHEN r.occurrence IS NOT NULL THEN 'terminal' WHEN t.claimant IS NULL THEN 'queued' ELSE 'claimed' END AS state "
            "FROM impetus_local_dispatch_tasks t LEFT JOIN impetus_local_dispatch_terminals r "
            "ON t.instance=r.instance AND t.occurrence=r.occurrence WHERE t.instance=? ORDER BY t.sequence",
            (instance,),
        )
        for row in rows:
            event: dict[str, object] = {
                key: number(row[key])
                for key in (
                    "occurrence",
                    "epoch",
                    "deadline",
                    "schedule_start",
                    "attempt_start",
                    "attempt_deadline",
                    "available_at",
                )
            }
            event.update(layer="dispatch", instance=instance, activity=atom(row["activity"]), state=row["state"])
            events.append(event)
    finally:
        database.close()
    database = connect(root / "webhooks.sqlite3")
    try:
        rows = database.execute(
            "SELECT delivery_id,event,status,attempts,error_class,next_attempt_at FROM inbox "
            "WHERE json_extract(observation,'$.installation_id')=? "
            "AND json_extract(observation,'$.repository_id')=? "
            "AND json_extract(observation,'$.pull_request_number')=? ORDER BY rowid",
            (installation, repository, pr),
        )
        for row in rows:
            events.append(
                {
                    "layer": "inbox",
                    "instance": instance,
                    "delivery_id": atom(row["delivery_id"]),
                    "event": atom(row["event"]),
                    "status": atom(row["status"]),
                    "attempts": number(row["attempts"]),
                    "error_class": atom(row["error_class"]),
                    "next_attempt_at": number(row["next_attempt_at"]),
                }
            )
    finally:
        database.close()
    return events
