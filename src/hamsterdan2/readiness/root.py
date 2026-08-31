# Copyright (c) 2026 Henrique Bastos

"""Durable identity binding for one fresh readiness root."""

from __future__ import annotations

from contextlib import closing
import sqlite3
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS root_binding (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    instance_id TEXT NOT NULL,
    bridge_identity TEXT NOT NULL
);
"""


class ReadinessRootError(Exception):
    """A readiness runtime cannot safely use its durable root."""


class ReadinessRootConflictError(ReadinessRootError):
    """A readiness root is bound to a different instance or bridge identity."""


class ReadinessRoot:
    """Bind one storage path permanently to one instance and bridge identity."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def bind(self, *, instance_id: str, bridge_identity: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as connection, connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                "SELECT instance_id, bridge_identity FROM root_binding WHERE singleton = 1"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO root_binding (singleton, instance_id, bridge_identity) VALUES (1, ?, ?)",
                    (instance_id, bridge_identity),
                )
                return
            recorded_instance, recorded_bridge = row
            if recorded_instance != instance_id or recorded_bridge != bridge_identity:
                raise ReadinessRootConflictError(
                    instance_id,
                    recorded_instance,
                    recorded_bridge,
                    bridge_identity,
                    "use a fresh readiness root when the instance or bridge identity differs",
                )
