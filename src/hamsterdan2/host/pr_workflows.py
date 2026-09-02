# Copyright (c) 2026 Henrique Bastos

"""Durable PR workflow identities in the shared application database."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from pydantic import ValidationError

from hamsterdan2.host.database import ApplicationDatabase, ApplicationStorageCapacityError
from hamsterdan2.host.values import OpenPullRequestCommand, PullRequestWorkflow
from hamsterdan2.readiness.workflow_bridge import BRIDGE_IDENTITY
from hamsterdan2.workflow.values import PullRequestIdentity


if TYPE_CHECKING:
    from collections.abc import Callable
    import sqlite3

    from hamsterdan2.workflow.values import AwaitingObservation


AuthorityResult = TypeVar("AuthorityResult")
MAX_IDENTITY_BYTES = 128


class PullRequestWorkflowError(Exception):
    """A PR identity conflicts with durable application authority."""


class ActionIdentityConflictError(PullRequestWorkflowError):
    """An action identity already belongs to another PR identity."""


class PullRequestNotRegisteredError(PullRequestWorkflowError):
    """The requested PR identity has no durable workflow."""


class PullRequestWorkflowCorruptionError(PullRequestWorkflowError):
    """A durable PR workflow row cannot be reconstructed exactly."""


def pr_key(pr_identity: PullRequestIdentity) -> tuple[int, int, int]:
    return (
        pr_identity.installation_id,
        pr_identity.repository_id,
        pr_identity.pull_request_number,
    )


def workflow_for(command: OpenPullRequestCommand) -> PullRequestWorkflow:
    installation_id, repository_id, pull_request_number = pr_key(command.pr_identity)
    return PullRequestWorkflow(
        action_identity=command.action_identity,
        pr_identity=command.pr_identity,
        workflow_id=f"github:{installation_id}:{repository_id}:pr:{pull_request_number}",
        bridge_identity=BRIDGE_IDENTITY,
    )


def workflow_rows(
    connection: sqlite3.Connection,
    pr_identity: PullRequestIdentity,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT installation_id, repository_id, pull_request_number,
               action_identity, workflow_id, bridge_identity,
               generation, stage, checkpoint
        FROM pr_workflows
        WHERE installation_id = ? AND repository_id = ? AND pull_request_number = ?
        LIMIT 2
        """,
        pr_key(pr_identity),
    ).fetchall()


def reconstruct_workflow(row: sqlite3.Row, pr_identity: PullRequestIdentity) -> PullRequestWorkflow:
    try:
        workflow = PullRequestWorkflow(
            action_identity=row["action_identity"],
            pr_identity=PullRequestIdentity(
                installation_id=row["installation_id"],
                repository_id=row["repository_id"],
                pull_request_number=row["pull_request_number"],
            ),
            workflow_id=row["workflow_id"],
            bridge_identity=row["bridge_identity"],
            generation=row["generation"],
            stage=row["stage"],
            checkpoint=row["checkpoint"],
        )
    except ValidationError, TypeError, ValueError:
        raise PullRequestWorkflowCorruptionError(
            "malformed_pr_workflow",
            pr_key(pr_identity),
            "use a fresh state root",
        ) from None
    if workflow.pr_identity != pr_identity:
        raise PullRequestWorkflowCorruptionError(
            "pr_workflow_identity_mismatch",
            pr_key(pr_identity),
            "use a fresh state root",
        )
    return workflow


def selected_workflow(
    connection: sqlite3.Connection,
    pr_identity: PullRequestIdentity,
) -> PullRequestWorkflow | None:
    rows = workflow_rows(connection, pr_identity)
    if len(rows) > 1:
        raise PullRequestWorkflowCorruptionError(
            "duplicate_pr_workflow",
            pr_key(pr_identity),
            "use a fresh state root",
        )
    return None if not rows else reconstruct_workflow(rows[0], pr_identity)


def require_action_matches(
    connection: sqlite3.Connection,
    command: OpenPullRequestCommand,
) -> None:
    action_rows = connection.execute(
        """
        SELECT installation_id, repository_id, pull_request_number
        FROM pr_workflows WHERE action_identity = ? LIMIT 2
        """,
        (command.action_identity,),
    ).fetchall()
    if len(action_rows) > 1:
        raise PullRequestWorkflowCorruptionError(
            "duplicate_action_identity",
            command.action_identity,
            "use a fresh state root",
        )
    if not action_rows:
        return
    action_pr = PullRequestIdentity(
        installation_id=action_rows[0]["installation_id"],
        repository_id=action_rows[0]["repository_id"],
        pull_request_number=action_rows[0]["pull_request_number"],
    )
    if action_pr != command.pr_identity:
        raise ActionIdentityConflictError(
            command.action_identity,
            pr_key(action_pr),
            pr_key(command.pr_identity),
            "use a new action identity",
        )


def require_expected_workflow(
    recorded: PullRequestWorkflow | None,
    expected: PullRequestWorkflow,
) -> None:
    if recorded is not None and recorded != expected:
        raise PullRequestWorkflowCorruptionError(
            "pr_workflow_binding_mismatch",
            pr_key(expected.pr_identity),
            "use a fresh state root",
        )


def require_open_projection(
    stage: AwaitingObservation,
    expected: PullRequestIdentity,
) -> None:
    if stage.pr_identity != expected or stage.stage != "awaiting_observation":
        raise PullRequestWorkflowError("history_open_projection_mismatch")


def append_workflow(
    connection: sqlite3.Connection,
    workflow: PullRequestWorkflow,
    *,
    maximum_workflows: int,
) -> None:
    count = connection.execute("SELECT COUNT(*) FROM pr_workflows").fetchone()[0]
    if count >= maximum_workflows:
        raise ApplicationStorageCapacityError("pr_workflow_capacity_exhausted")
    connection.execute(
        """
        INSERT INTO pr_workflows (
            installation_id, repository_id, pull_request_number,
            action_identity, workflow_id, bridge_identity,
            generation, stage, checkpoint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            *pr_key(workflow.pr_identity),
            workflow.action_identity,
            workflow.workflow_id,
            workflow.bridge_identity,
            workflow.generation,
            workflow.stage,
            workflow.checkpoint,
        ),
    )


def require_workflow(
    connection: sqlite3.Connection,
    pr_identity: PullRequestIdentity,
) -> PullRequestWorkflow:
    workflow = selected_workflow(connection, pr_identity)
    if workflow is None:
        raise PullRequestNotRegisteredError(
            pr_key(pr_identity),
            "open this PR workflow before requesting authority",
        )
    return workflow


class PullRequestWorkflows:
    """Open and fence one PR workflow through the application database."""

    def __init__(self, database: ApplicationDatabase) -> None:
        self._database = database

    def open(
        self,
        command: OpenPullRequestCommand,
        open_history: Callable[[PullRequestWorkflow], AwaitingObservation],
    ) -> PullRequestWorkflow:
        expected = workflow_for(command)
        with self._database.transaction() as connection:
            require_action_matches(connection, command)
            recorded = selected_workflow(connection, command.pr_identity)
            require_expected_workflow(recorded, expected)
            opened = recorded or expected
            require_open_projection(open_history(opened), command.pr_identity)
            if recorded is None:
                append_workflow(
                    connection,
                    opened,
                    maximum_workflows=self._database.maximum_workflows,
                )
            return opened

    def workflow(self, pr_identity: PullRequestIdentity) -> PullRequestWorkflow | None:
        with self._database.connect() as connection:
            return selected_workflow(connection, pr_identity)

    def run_authority(
        self,
        pr_identity: PullRequestIdentity,
        action: Callable[[PullRequestWorkflow], AuthorityResult],
    ) -> AuthorityResult:
        with self._database.transaction() as connection:
            return action(require_workflow(connection, pr_identity))
