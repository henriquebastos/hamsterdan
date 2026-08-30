# Copyright (c) 2026 Henrique Bastos

"""One bounded Petrus execution for one replacement readiness lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING

from petrus.engine.sqlite import create_engine, load_engine
from petrus.impetus.history_store import SqliteHistoryStore
from petrus.motus.dispatch import LocalDispatch

from hamsterdan2.readiness.root import ReadinessRoot
from hamsterdan2.readiness.workflow_bridge import BridgedWorkflow, build_workflow, project_awaiting_observation


if TYPE_CHECKING:
    from pathlib import Path

    from hamsterdan2.workflow.values import AwaitingObservation, PullRequestSubject


def has_canonical_history(path: Path, instance_id: str) -> bool:
    return history_record_count(path, instance_id) > 0


def history_record_count(path: Path, instance_id: str) -> int:
    history = SqliteHistoryStore(path, instance_id)
    try:
        return len(history.records)
    finally:
        history.close()


class ReadinessRuntime:
    """Open one PR lifecycle without exposing its Petrus collaborators."""

    def __init__(
        self,
        *,
        root: ReadinessRoot,
        history_path: Path,
        instance_id: str,
        workflow: BridgedWorkflow,
        dispatch: LocalDispatch,
    ) -> None:
        self._root = root
        self._history_path = history_path
        self._instance_id = instance_id
        self._workflow = workflow
        self._dispatch = dispatch

    def open(self, subject: PullRequestSubject) -> AwaitingObservation:
        self._root.bind(instance_id=self._instance_id, bridge_identity=self._workflow.identity)
        options = {
            "dispatch": self._dispatch,
            "handlers": self._workflow.handlers,
            "guards": self._workflow.guards,
            "activities": self._workflow.activities,
        }
        engine = (
            load_engine(path=self._history_path, net=self._workflow.net, instance=self._instance_id, **options)
            if has_canonical_history(self._history_path, self._instance_id)
            else create_engine(
                path=self._history_path,
                net=self._workflow.net,
                instance=self._instance_id,
                marking=self._workflow.marking,
                **options,
            )
        )
        try:
            return project_awaiting_observation(
                snapshot=engine.snapshot(),
                subject=subject,
                instance_id=self._instance_id,
            )
        finally:
            engine.close()


def build_readiness_runtime(
    *,
    root_path: Path,
    dispatch_path: Path,
    instance_id: str,
) -> ReadinessRuntime:
    return ReadinessRuntime(
        root=ReadinessRoot(root_path / "readiness.sqlite3"),
        history_path=root_path / "history.sqlite3",
        instance_id=instance_id,
        workflow=build_workflow(instance_id),
        dispatch=LocalDispatch(dispatch_path, instance=instance_id),
    )
