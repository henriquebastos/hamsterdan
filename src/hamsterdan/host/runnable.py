"""Durable, reconstructible wake hints for PR workflow Instances."""

from __future__ import annotations

import math
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

_MAX_INSTANCE = 256
_MAX_KIND = 64
_MAX_IDENTITY = 256
_SCHEMA_COLUMNS = (
    (0, "instance", "TEXT", 1, None, 1),
    (1, "kind", "TEXT", 1, None, 2),
    (2, "identity", "TEXT", 1, None, 3),
    (3, "due_at", "REAL", 1, None, 0),
)


def _identifier(value: str, maximum: int, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > maximum:
        raise ValueError(f"{label} must be a non-empty bounded identifier")
    return value


def _instant(value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("due_at must be finite")
    return result


class RunnableIndex:
    """One-row-per-reason SQLite hint index; never canonical workflow state."""

    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._closed = False
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.exists():
            try:
                candidate = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
                try:
                    self._validate(candidate)
                except BaseException:
                    candidate.close()
                    raise
                self._db = candidate
            except sqlite3.DatabaseError, RuntimeError:
                self._replace_disposable(path)
                self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        else:
            self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS wakes (
            instance TEXT NOT NULL,
            kind TEXT NOT NULL,
            identity TEXT NOT NULL,
            due_at REAL NOT NULL,
            PRIMARY KEY(instance, kind, identity)
          );
          CREATE INDEX IF NOT EXISTS wakes_due ON wakes(due_at, instance);
        """)

    @staticmethod
    def _validate(database: sqlite3.Connection) -> None:
        if database.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise RuntimeError("RunnableIndex database is corrupt")
        objects = database.execute(
            "SELECT type,name,tbl_name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        if objects != [("index", "wakes_due", "wakes"), ("table", "wakes", "wakes")]:
            raise RuntimeError("RunnableIndex schema is incompatible")
        columns = tuple(database.execute("PRAGMA table_info(wakes)"))
        if columns != _SCHEMA_COLUMNS:
            raise RuntimeError("RunnableIndex schema is incompatible")
        index = tuple(database.execute("PRAGMA index_info(wakes_due)"))
        if index != ((0, 3, "due_at"), (1, 0, "instance")):
            raise RuntimeError("RunnableIndex schema is incompatible")

    @staticmethod
    def _replace_disposable(path: Path) -> None:
        quarantine = path.with_name(f"{path.name}.corrupt")
        for suffix in ("-wal", "-shm"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        os.replace(path, quarantine)

    def wake(self, instance: str, due_at: float, kind: str, identity: str) -> None:
        values = (
            _identifier(instance, _MAX_INSTANCE, "instance"),
            _identifier(kind, _MAX_KIND, "reason kind"),
            _identifier(identity, _MAX_IDENTITY, "reason identity"),
            _instant(due_at),
        )
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO wakes(instance,kind,identity,due_at) VALUES(?,?,?,?) "
                "ON CONFLICT(instance,kind,identity) DO UPDATE SET due_at=MIN(due_at,excluded.due_at)",
                values,
            )

    def replace_timer(self, instance: str, due_at: float | None) -> None:
        instance = _identifier(instance, _MAX_INSTANCE, "instance")
        with self._lock, self._db:
            if due_at is None:
                self._db.execute("DELETE FROM wakes WHERE instance=? AND kind='petri-timer'", (instance,))
            else:
                self._db.execute(
                    "INSERT INTO wakes(instance,kind,identity,due_at) VALUES(?,'petri-timer','next-maturation',?) "
                    "ON CONFLICT(instance,kind,identity) DO UPDATE SET due_at=excluded.due_at",
                    (instance, _instant(due_at)),
                )

    def cancel_timer(self, instance: str) -> None:
        self.replace_timer(instance, None)

    def take_due(self, limit: int = 100, *, now: float | None = None) -> tuple[str, ...]:
        limit = max(1, min(int(limit), 1000))
        instant = _instant(self._clock() if now is None else now)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                rows = self._db.execute(
                    "SELECT instance,MIN(due_at) AS first_due FROM wakes WHERE due_at<=? "
                    "GROUP BY instance ORDER BY first_due,instance LIMIT ?",
                    (instant, limit),
                ).fetchall()
                instances = tuple(str(row[0]) for row in rows)
                if instances:
                    placeholders = ",".join("?" for _ in instances)
                    self._db.execute(
                        f"DELETE FROM wakes WHERE due_at<=? AND instance IN ({placeholders})",
                        (instant, *instances),
                    )
                self._db.execute("COMMIT")
                return instances
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM wakes").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._db.close()


__all__ = ["RunnableIndex"]
