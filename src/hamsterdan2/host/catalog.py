# Copyright (c) 2026 Henrique Bastos

"""Durable subject registration and host-action custody."""

from __future__ import annotations

from contextlib import closing
import sqlite3
from typing import TYPE_CHECKING

from hamsterdan2.host.values import HostRecord, RegisteredPullRequest
from hamsterdan2.workflow.values import AwaitingObservation, PullRequestSubject


if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hamsterdan2.host.values import OpenPullRequestCommand


SCHEMA = """
CREATE TABLE IF NOT EXISTS subject_roots (
    installation_id INTEGER NOT NULL,
    repository_id INTEGER NOT NULL,
    pull_request_number INTEGER NOT NULL,
    instance_id TEXT NOT NULL UNIQUE,
    readiness_root TEXT NOT NULL UNIQUE,
    PRIMARY KEY (installation_id, repository_id, pull_request_number)
);
CREATE TABLE IF NOT EXISTS host_records (
    action_identity TEXT PRIMARY KEY,
    installation_id INTEGER NOT NULL,
    repository_id INTEGER NOT NULL,
    pull_request_number INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action = 'open_pull_request'),
    posture TEXT NOT NULL CHECK (posture = 'awaiting_observation'),
    cut TEXT NOT NULL CHECK (cut = 'host_recorded'),
    FOREIGN KEY (installation_id, repository_id, pull_request_number)
        REFERENCES subject_roots (installation_id, repository_id, pull_request_number)
);
"""


class HostCatalogError(Exception):
    """A host command conflicts with durable host custody."""


class ActionIdentityConflictError(HostCatalogError):
    """An action identity already belongs to a different PR subject."""


class SubjectRootConflictError(HostCatalogError):
    """A PR subject is already bound to a different readiness root."""


class PullRequestNotRegisteredError(HostCatalogError):
    """A step was requested before its subject/root registration."""


def subject_key(subject: PullRequestSubject) -> tuple[int, int, int]:
    return (subject.installation_id, subject.repository_id, subject.pull_request_number)


def registration_for(subject: PullRequestSubject) -> RegisteredPullRequest:
    installation_id, repository_id, pull_request_number = subject_key(subject)
    return RegisteredPullRequest(
        subject=subject,
        instance_id=f"github:{installation_id}:{repository_id}:pr:{pull_request_number}",
        readiness_root=f"instances/{installation_id}/{repository_id}/{pull_request_number}",
    )


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def subject_from_row(row: sqlite3.Row) -> PullRequestSubject:
    return PullRequestSubject(
        installation_id=row["installation_id"],
        repository_id=row["repository_id"],
        pull_request_number=row["pull_request_number"],
    )


def action_subject(connection: sqlite3.Connection, action_identity: str) -> PullRequestSubject | None:
    row = connection.execute(
        """
        SELECT installation_id, repository_id, pull_request_number
        FROM host_records
        WHERE action_identity = ?
        """,
        (action_identity,),
    ).fetchone()
    return None if row is None else subject_from_row(row)


def reject_action_conflict(
    *,
    action_identity: str,
    recorded: PullRequestSubject | None,
    requested: PullRequestSubject,
) -> None:
    if recorded is not None and recorded != requested:
        raise ActionIdentityConflictError(
            action_identity,
            subject_key(recorded),
            subject_key(requested),
            "use a new action identity for the requested pull request",
        )


def registered_pull_request(
    connection: sqlite3.Connection,
    subject: PullRequestSubject,
) -> RegisteredPullRequest | None:
    row = connection.execute(
        """
        SELECT installation_id, repository_id, pull_request_number, instance_id, readiness_root
        FROM subject_roots
        WHERE installation_id = ? AND repository_id = ? AND pull_request_number = ?
        """,
        subject_key(subject),
    ).fetchone()
    if row is None:
        return None
    return RegisteredPullRequest(
        subject=subject_from_row(row),
        instance_id=row["instance_id"],
        readiness_root=row["readiness_root"],
    )


def bind_subject(
    connection: sqlite3.Connection,
    expected: RegisteredPullRequest,
) -> RegisteredPullRequest:
    recorded = registered_pull_request(connection, expected.subject)
    if recorded is None:
        connection.execute(
            """
            INSERT INTO subject_roots (
                installation_id, repository_id, pull_request_number, instance_id, readiness_root
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (*subject_key(expected.subject), expected.instance_id, expected.readiness_root),
        )
        return expected
    if recorded != expected:
        raise SubjectRootConflictError(
            subject_key(expected.subject),
            recorded.instance_id,
            recorded.readiness_root,
            expected.instance_id,
            expected.readiness_root,
            "use the subject's original readiness root or a fresh state root",
        )
    return recorded


def replayed_record(connection: sqlite3.Connection, action_identity: str) -> HostRecord | None:
    row = connection.execute(
        """
        SELECT action_identity, installation_id, repository_id, pull_request_number, action, posture, cut
        FROM host_records
        WHERE action_identity = ?
        """,
        (action_identity,),
    ).fetchone()
    if row is None:
        return None
    subject = subject_from_row(row)
    return HostRecord(
        action_identity=row["action_identity"],
        action=row["action"],
        posture=AwaitingObservation(subject=subject, posture=row["posture"]),
        cut=row["cut"],
    )


def append_record(connection: sqlite3.Connection, record: HostRecord) -> None:
    connection.execute(
        """
        INSERT INTO host_records (
            action_identity, installation_id, repository_id, pull_request_number, action, posture, cut
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.action_identity,
            *subject_key(record.posture.subject),
            record.action,
            record.posture.posture,
            record.cut,
        ),
    )


class HostCatalog:
    """Serialize one bounded action while retaining its subject and detached result."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @classmethod
    def from_path(cls, path: Path) -> HostCatalog:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(connect(path)) as connection:
            connection.executescript(SCHEMA)
        return cls(path)

    def register(self, command: OpenPullRequestCommand) -> RegisteredPullRequest:
        expected = registration_for(command.subject)
        with closing(connect(self._path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            reject_action_conflict(
                action_identity=command.action_identity,
                recorded=action_subject(connection, command.action_identity),
                requested=command.subject,
            )
            return bind_subject(connection, expected)

    def step(
        self,
        command: OpenPullRequestCommand,
        action: Callable[[RegisteredPullRequest], AwaitingObservation],
    ) -> HostRecord:
        """Hold host custody through readiness so two Engines cannot share one History."""
        with closing(connect(self._path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            replayed = replayed_record(connection, command.action_identity)
            if replayed is not None:
                reject_action_conflict(
                    action_identity=command.action_identity,
                    recorded=replayed.posture.subject,
                    requested=command.subject,
                )
                return replayed
            registered = registered_pull_request(connection, command.subject)
            if registered is None:
                raise PullRequestNotRegisteredError(
                    subject_key(command.subject),
                    "call register with this command before requesting its step",
                )
            record = HostRecord(
                action_identity=command.action_identity,
                posture=action(registered),
            )
            append_record(connection, record)
            return record
