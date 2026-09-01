# Copyright (c) 2026 Henrique Bastos

"""Durable subject registration and host-action custody."""

from __future__ import annotations

from contextlib import closing
import sqlite3
from typing import TYPE_CHECKING, TypeVar

from hamsterdan2.host.values import HostRecord, RegisteredPullRequest
from hamsterdan2.workflow.values import AwaitingObservation, PullRequestSubject


if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hamsterdan2.host.values import OpenPullRequestCommand


AuthorityResult = TypeVar("AuthorityResult")


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

MAX_REGISTRATION_IDENTITY_BYTES = 128


class HostCatalogError(Exception):
    """A host command conflicts with durable host custody."""


class ActionIdentityConflictError(HostCatalogError):
    """An action identity already belongs to a different PR subject."""


class SubjectRootConflictError(HostCatalogError):
    """A PR subject is already bound to a different readiness root."""


class HostCatalogCorruptionError(HostCatalogError):
    """Durable host authority has an impossible cardinality."""


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


def reconstruct_registration(
    row: sqlite3.Row,
    expected: RegisteredPullRequest,
) -> RegisteredPullRequest:
    correlation = (
        row["installation_id"],
        row["repository_id"],
        row["pull_request_number"],
        row["instance_id"],
        row["readiness_root"],
    )
    expected_key = subject_key(expected.subject)
    if any(value is None for value in correlation):
        raise HostCatalogCorruptionError(
            "invalid_subject_registration",
            expected_key,
            "replace the malformed host catalog before requesting readiness authority",
        )
    expected_correlation = (*expected_key, expected.instance_id, expected.readiness_root)
    if correlation != expected_correlation:
        raise SubjectRootConflictError(
            "subject_root_mismatch",
            expected_key,
            expected.instance_id,
            expected.readiness_root,
            "use the subject's derived readiness root or a fresh state root",
        )
    return expected


def registered_pull_request(
    connection: sqlite3.Connection,
    subject: PullRequestSubject,
) -> RegisteredPullRequest | None:
    rows = connection.execute(
        """
        SELECT CASE WHEN typeof(installation_id) = 'integer' AND installation_id > 0
                    THEN installation_id END AS installation_id,
               CASE WHEN typeof(repository_id) = 'integer' AND repository_id > 0
                    THEN repository_id END AS repository_id,
               CASE WHEN typeof(pull_request_number) = 'integer' AND pull_request_number > 0
                    THEN pull_request_number END AS pull_request_number,
               CASE WHEN typeof(instance_id) = 'text'
                          AND length(CAST(instance_id AS BLOB)) BETWEEN 1 AND ?
                    THEN instance_id END AS instance_id,
               CASE WHEN typeof(readiness_root) = 'text'
                          AND length(CAST(readiness_root AS BLOB)) BETWEEN 1 AND ?
                    THEN readiness_root END AS readiness_root
        FROM subject_roots
        WHERE installation_id = ? AND repository_id = ? AND pull_request_number = ?
        LIMIT 2
        """,
        (
            MAX_REGISTRATION_IDENTITY_BYTES,
            MAX_REGISTRATION_IDENTITY_BYTES,
            *subject_key(subject),
        ),
    ).fetchmany(2)
    if len(rows) > 1:
        raise HostCatalogCorruptionError(
            "duplicate_subject_registration",
            subject_key(subject),
            len(rows),
            "replace the malformed host catalog before requesting readiness authority",
        )
    if not rows:
        return None
    return reconstruct_registration(rows[0], registration_for(subject))


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
            "subject_root_mismatch",
            subject_key(expected.subject),
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

    def run_readiness_authority(
        self,
        subject: PullRequestSubject,
        action: Callable[[RegisteredPullRequest], AuthorityResult],
    ) -> AuthorityResult:
        """Fence one existing subject root while readiness owns its Engine."""
        with closing(connect(self._path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            registered = registered_pull_request(connection, subject)
            if registered is None:
                raise PullRequestNotRegisteredError(
                    subject_key(subject),
                    "register and open this pull request before requesting History acceptance",
                )
            return action(registered)
