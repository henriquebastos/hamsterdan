# Copyright (c) 2026 Henrique Bastos

"""First executable pulse through the CV21 host/readiness/bridge spine."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from petrus.impetus.history_store import SqliteHistoryStore

from hamsterdan2.host.catalog import ActionIdentityConflictError
from hamsterdan2.host.composition import build_hamsterdan
from hamsterdan2.host.values import ActionIdentity, HostRecord, OpenPullRequestCommand, RegisteredPullRequest
from hamsterdan2.readiness.root import ReadinessRootConflictError
from hamsterdan2.readiness.runtime import build_readiness_runtime
from hamsterdan2.workflow.values import AwaitingObservation, PullRequestSubject

import pytest


if TYPE_CHECKING:
    from pathlib import Path


def canonical_history(path: Path, instance_id: str) -> tuple[object, ...]:
    history = SqliteHistoryStore(path, instance_id)
    try:
        return history.records
    finally:
        history.close()


def first_command() -> OpenPullRequestCommand:
    return OpenPullRequestCommand(
        action_identity=ActionIdentity("trace:open:1"),
        subject=PullRequestSubject(installation_id=44, repository_id=31, pull_request_number=7),
    )


class TestFirstBridgedLifecycle:
    """One PR lifecycle reconstructs from its canonical Petrus History."""

    def test_fresh_object_graph_replays_the_recorded_open_action(self, tmp_path: Path) -> None:
        command = first_command()
        history_path = tmp_path / "instances" / "44" / "31" / "7" / "history.sqlite3"
        instance_id = "github:44:31:pr:7"

        first = build_hamsterdan(state_root=tmp_path).open_pull_request(command)
        created_history = canonical_history(history_path, instance_id)
        reconstructed = build_hamsterdan(state_root=tmp_path).open_pull_request(command)

        expected = HostRecord(
            action_identity=command.action_identity,
            posture=AwaitingObservation(subject=command.subject),
        )
        assert created_history
        assert first == expected
        assert reconstructed == expected
        assert canonical_history(history_path, instance_id) == created_history
        assert expected.model_dump(mode="json") == {
            "action_identity": "trace:open:1",
            "action": "open_pull_request",
            "posture": {
                "subject": {
                    "installation_id": 44,
                    "repository_id": 31,
                    "pull_request_number": 7,
                },
                "posture": "awaiting_observation",
            },
            "cut": "host_recorded",
        }
        assert (tmp_path / "catalog.sqlite3").is_file()
        assert (tmp_path / "instances" / "44" / "31" / "7" / "readiness.sqlite3").is_file()
        assert history_path.is_file()
        assert (tmp_path / "dispatch.sqlite3").is_file()


class TestHostApplicationPhases:
    """Registration and bounded execution remain independently usable phases."""

    def test_registration_binds_subject_to_root_before_readiness_opens(self, tmp_path: Path) -> None:
        command = first_command()
        application = build_hamsterdan(state_root=tmp_path)

        registered = application.register(command)

        assert registered == RegisteredPullRequest(
            subject=command.subject,
            instance_id="github:44:31:pr:7",
            readiness_root="instances/44/31/7",
        )
        assert not (tmp_path / registered.readiness_root / "history.sqlite3").exists()

        assert application.step(command) == HostRecord(
            action_identity=command.action_identity,
            posture=AwaitingObservation(subject=command.subject),
        )

    def test_one_action_identity_cannot_open_another_subject(self, tmp_path: Path) -> None:
        application = build_hamsterdan(state_root=tmp_path)
        original = first_command()
        conflicting = OpenPullRequestCommand(
            action_identity=original.action_identity,
            subject=PullRequestSubject(installation_id=44, repository_id=31, pull_request_number=8),
        )
        application.open_pull_request(original)

        with pytest.raises(ActionIdentityConflictError) as raised:
            application.open_pull_request(conflicting)

        assert raised.value.args == (
            "trace:open:1",
            (44, 31, 7),
            (44, 31, 8),
            "use a new action identity for the requested pull request",
        )
        assert not (tmp_path / "instances" / "44" / "31" / "8").exists()


class TestReadinessRuntimePhases:
    """Runtime construction binds collaborators without opening Petrus History."""

    def test_build_does_not_open_history_until_the_runtime_is_opened(self, tmp_path: Path) -> None:
        subject = PullRequestSubject(installation_id=44, repository_id=31, pull_request_number=7)
        readiness_root = tmp_path / "instances" / "44" / "31" / "7"
        history_path = readiness_root / "history.sqlite3"
        runtime = build_readiness_runtime(
            root_path=readiness_root,
            dispatch_path=tmp_path / "dispatch.sqlite3",
            instance_id="github:44:31:pr:7",
        )

        assert not history_path.exists()

        assert runtime.open(subject) == AwaitingObservation(subject=subject)
        assert history_path.is_file()

    def test_changed_bridge_identity_is_rejected_before_history_changes(self, tmp_path: Path) -> None:
        command = first_command()
        application = build_hamsterdan(state_root=tmp_path)
        application.open_pull_request(command)
        root = tmp_path / "instances" / "44" / "31" / "7"
        history_path = root / "history.sqlite3"
        created_history = canonical_history(history_path, "github:44:31:pr:7")
        with sqlite3.connect(root / "readiness.sqlite3") as connection:
            connection.execute("UPDATE root_binding SET bridge_identity = 'mutated'")
        next_command = OpenPullRequestCommand(
            action_identity=ActionIdentity("trace:open:2"),
            subject=command.subject,
        )

        with pytest.raises(ReadinessRootConflictError) as raised:
            build_hamsterdan(state_root=tmp_path).open_pull_request(next_command)

        assert raised.value.args == (
            "root_binding_mismatch",
            "github:44:31:pr:7",
            "workflow-bridge/head-seen-history-acceptance@2",
            "use a fresh readiness root when the instance or bridge identity differs",
        )
        assert canonical_history(history_path, "github:44:31:pr:7") == created_history
