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

MAX_ROOT_IDENTITY_BYTES = 128


class ReadinessRootError(Exception):
    """A readiness runtime cannot safely use its durable root."""


class ReadinessRootConflictError(ReadinessRootError):
    """A readiness root is bound to a different instance or bridge identity."""


class ReadinessRootCorruptionError(ReadinessRootError):
    """Durable readiness-root authority has an impossible cardinality."""


class ReadinessRootMissingError(ReadinessRootError):
    """A later authority cut was requested before the readiness root existed."""


def root_binding_row(connection: sqlite3.Connection, *, instance_id: str) -> tuple[str, str] | None:
    rows = connection.execute(
        """
        SELECT CASE WHEN typeof(singleton) = 'integer' AND singleton = 1
                    THEN singleton END AS singleton,
               CASE WHEN typeof(instance_id) = 'text'
                          AND length(CAST(instance_id AS BLOB)) BETWEEN 1 AND ?
                    THEN instance_id END AS instance_id,
               CASE WHEN typeof(bridge_identity) = 'text'
                          AND length(CAST(bridge_identity AS BLOB)) BETWEEN 1 AND ?
                    THEN bridge_identity END AS bridge_identity
        FROM root_binding
        LIMIT 2
        """,
        (MAX_ROOT_IDENTITY_BYTES, MAX_ROOT_IDENTITY_BYTES),
    ).fetchall()
    if len(rows) > 1:
        raise ReadinessRootCorruptionError(
            "duplicate_root_binding",
            instance_id,
            len(rows),
            "replace the malformed readiness root before requesting authority",
        )
    if not rows:
        return None
    singleton, recorded_instance, recorded_bridge = rows[0]
    if singleton is None or recorded_instance is None or recorded_bridge is None:
        raise ReadinessRootCorruptionError(
            "invalid_root_binding",
            instance_id,
            "replace the malformed readiness root before requesting authority",
        )
    return (recorded_instance, recorded_bridge)


class ReadinessRoot:
    """Bind one storage path permanently to one instance and bridge identity."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def bind(self, *, instance_id: str, bridge_identity: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as connection, connection:
            connection.executescript(SCHEMA)
            row = root_binding_row(connection, instance_id=instance_id)
            if row is None:
                connection.execute(
                    "INSERT INTO root_binding (singleton, instance_id, bridge_identity) VALUES (1, ?, ?)",
                    (instance_id, bridge_identity),
                )
                return
            recorded_instance, recorded_bridge = row
            if recorded_instance != instance_id or recorded_bridge != bridge_identity:
                raise ReadinessRootConflictError(
                    "root_binding_mismatch",
                    instance_id,
                    bridge_identity,
                    "use a fresh readiness root when the instance or bridge identity differs",
                )

    def require_bound(self, *, instance_id: str, bridge_identity: str) -> None:
        if not self._path.is_file():
            raise ReadinessRootMissingError(
                instance_id,
                "open the registered readiness root before requesting History acceptance",
            )
        with closing(sqlite3.connect(self._path)) as connection:
            row = root_binding_row(connection, instance_id=instance_id)
        if row is None:
            raise ReadinessRootMissingError(
                instance_id,
                "open the registered readiness root before requesting History acceptance",
            )
        recorded_instance, recorded_bridge = row
        if recorded_instance != instance_id or recorded_bridge != bridge_identity:
            raise ReadinessRootConflictError(
                "root_binding_mismatch",
                instance_id,
                bridge_identity,
                "use a fresh readiness root when the instance or bridge identity differs",
            )
