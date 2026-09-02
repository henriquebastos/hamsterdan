# Copyright (c) 2026 Henrique Bastos

"""The one SQLite boundary for Hamsterdan application state."""

from __future__ import annotations

from contextlib import closing, contextmanager
import sqlite3
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


MAX_APPLICATION_PAGES = 131_072
MAX_INBOX_DELIVERIES = 10_000
MAX_PR_WORKFLOWS = 10_000
APPLICATION_TABLES = frozenset({"pr_workflows", "webhook_inbox"})
SCHEMA = """
CREATE TABLE IF NOT EXISTS pr_workflows (
    installation_id INTEGER NOT NULL,
    repository_id INTEGER NOT NULL,
    pull_request_number INTEGER NOT NULL,
    action_identity TEXT NOT NULL UNIQUE,
    workflow_id TEXT NOT NULL UNIQUE,
    bridge_identity TEXT NOT NULL CHECK (bridge_identity = 'workflow-bridge/head-seen-intake@4'),
    generation INTEGER NOT NULL CHECK (generation = 1),
    stage TEXT NOT NULL CHECK (stage = 'awaiting_observation'),
    checkpoint TEXT NOT NULL CHECK (checkpoint = 'pr_workflow_opened'),
    PRIMARY KEY (installation_id, repository_id, pull_request_number)
);
CREATE TABLE IF NOT EXISTS webhook_inbox (
    inbox_sequence INTEGER PRIMARY KEY,
    delivery_id TEXT NOT NULL UNIQUE,
    event TEXT NOT NULL,
    raw_body BLOB NOT NULL CHECK (
        typeof(raw_body) = 'blob' AND length(raw_body) BETWEEN 0 AND 1048576
    ),
    body_digest TEXT NOT NULL CHECK (
        typeof(body_digest) = 'text'
        AND length(body_digest) = 64
        AND body_digest NOT GLOB '*[^0-9a-f]*'
    ),
    collision_digest TEXT CHECK (
        collision_digest IS NULL
        OR (
            typeof(collision_digest) = 'text'
            AND length(collision_digest) = 64
            AND collision_digest NOT GLOB '*[^0-9a-f]*'
        )
    ),
    normalized_content TEXT CHECK (
        normalized_content IS NULL
        OR (
            typeof(normalized_content) = 'text'
            AND length(CAST(normalized_content AS BLOB)) BETWEEN 1 AND 16384
        )
    ),
    provider_route_id TEXT,
    installation_id INTEGER,
    repository_id INTEGER,
    pull_request_number INTEGER,
    observation_key TEXT,
    canonical_observation BLOB CHECK (
        canonical_observation IS NULL
        OR (
            typeof(canonical_observation) = 'blob'
            AND length(canonical_observation) BETWEEN 1 AND 8192
        )
    ),
    policy_revision TEXT,
    bridge_identity TEXT,
    history_delivery_identity TEXT,
    intake_authorized INTEGER NOT NULL DEFAULT 0 CHECK (intake_authorized IN (0, 1)),
    intake_outcome TEXT CHECK (intake_outcome IN ('recorded', 'duplicate', 'rejected')),
    intake_reason TEXT,
    duplicate_of_delivery_id TEXT,
    CHECK (
        (intake_outcome IS NULL AND intake_reason IS NULL AND duplicate_of_delivery_id IS NULL)
        OR (intake_outcome = 'recorded' AND intake_authorized = 1 AND intake_reason = 'accepted_by_history')
        OR (
            intake_outcome = 'duplicate'
            AND intake_authorized = 0
            AND intake_reason = 'same_observation'
            AND duplicate_of_delivery_id IS NOT NULL
        )
        OR (intake_outcome = 'rejected' AND intake_authorized = 0 AND intake_reason IS NOT NULL)
    ),
    CHECK (
        intake_authorized = 0
        OR (
            normalized_content IS NOT NULL
            AND provider_route_id IS NOT NULL
            AND installation_id IS NOT NULL
            AND repository_id IS NOT NULL
            AND pull_request_number IS NOT NULL
            AND observation_key IS NOT NULL
            AND canonical_observation IS NOT NULL
            AND policy_revision IS NOT NULL
            AND bridge_identity IS NOT NULL
            AND history_delivery_identity IS NOT NULL
        )
    ),
    FOREIGN KEY (installation_id, repository_id, pull_request_number)
        REFERENCES pr_workflows (installation_id, repository_id, pull_request_number),
    FOREIGN KEY (duplicate_of_delivery_id) REFERENCES webhook_inbox (delivery_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_intake_owner_per_observation
ON webhook_inbox (observation_key)
WHERE intake_authorized = 1;
"""


class ApplicationStorageError(Exception):
    """Hamsterdan application state cannot be trusted or extended."""


class ApplicationStorageCapacityError(ApplicationStorageError):
    """A configured finite application-storage limit was reached."""


class ApplicationStorageCorruptionError(ApplicationStorageError):
    """Application storage cannot be reconstructed under its declared schema."""


class ApplicationDatabase:
    """Construct connections to exactly two application-owned tables."""

    def __init__(self, path: Path, *, maximum_deliveries: int, maximum_workflows: int) -> None:
        self.path = path
        self.maximum_deliveries = maximum_deliveries
        self.maximum_workflows = maximum_workflows

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        maximum_deliveries: int = MAX_INBOX_DELIVERIES,
        maximum_workflows: int = MAX_PR_WORKFLOWS,
    ) -> ApplicationDatabase:
        if not 1 <= maximum_deliveries <= MAX_INBOX_DELIVERIES:
            raise ValueError(f"maximum deliveries must be between 1 and {MAX_INBOX_DELIVERIES}")
        if not 1 <= maximum_workflows <= MAX_PR_WORKFLOWS:
            raise ValueError(f"maximum workflows must be between 1 and {MAX_PR_WORKFLOWS}")
        path.parent.mkdir(parents=True, exist_ok=True)
        database = cls(
            path,
            maximum_deliveries=maximum_deliveries,
            maximum_workflows=maximum_workflows,
        )
        with closing(database.connect()) as connection, connection:
            connection.executescript(SCHEMA)
            database.verify(connection)
        return database

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        effective_maximum = connection.execute(f"PRAGMA max_page_count = {MAX_APPLICATION_PAGES}").fetchone()[0]
        pages = connection.execute("PRAGMA page_count").fetchone()[0]
        if effective_maximum > MAX_APPLICATION_PAGES or pages > MAX_APPLICATION_PAGES:
            connection.close()
            raise ApplicationStorageCorruptionError(
                "application_page_ceiling_exceeded",
                MAX_APPLICATION_PAGES,
                "use a fresh state root",
            )
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection

    def verify(self, connection: sqlite3.Connection) -> None:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%' LIMIT 3"
            ).fetchall()
        }
        if tables != APPLICATION_TABLES:
            raise ApplicationStorageCorruptionError(
                "application_table_set_mismatch",
                tuple(sorted(tables)),
                tuple(sorted(APPLICATION_TABLES)),
                "use a fresh state root",
            )
        workflow_count = connection.execute("SELECT COUNT(*) FROM pr_workflows").fetchone()[0]
        delivery_count = connection.execute("SELECT COUNT(*) FROM webhook_inbox").fetchone()[0]
        if workflow_count > self.maximum_workflows or delivery_count > self.maximum_deliveries:
            raise ApplicationStorageCorruptionError(
                "application_row_ceiling_exceeded",
                self.maximum_workflows,
                self.maximum_deliveries,
                "use a fresh state root",
            )
