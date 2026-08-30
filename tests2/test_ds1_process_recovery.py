# Copyright (c) 2026 Henrique Bastos

"""Actual child-process loss and reconstruction around the DS1 host cut."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import socket
from typing import TYPE_CHECKING

from petrus.testing.dst import (
    ExecuteOperation,
    ProcessBudget,
    ProcessRunResult,
    ProcessRunSpec,
    SubmitAttempt,
    run_process_scenario,
)

from hamsterdan2.simulation.hamsterdan import EXPECTED_RECORD, EXPECTED_REGISTRATION, observe_hamsterdan
from hamsterdan2.simulation.process import (
    AFTER_DEATH_SCENARIO,
    AFTER_RECOVERY_SCENARIO,
    BEFORE_DEATH_SCENARIO,
    BEFORE_RECOVERY_SCENARIO,
    LOCK_HOLDER_SCENARIO,
)


if TYPE_CHECKING:
    from pathlib import Path


PROCESS_BUDGET = ProcessBudget(
    wall_clock_ms=10_000,
    termination_grace_ms=500,
    input_bytes=64_000,
    progress_bytes=4_194_304,
)
CONTENDER_BUDGET = ProcessBudget(
    wall_clock_ms=500,
    termination_grace_ms=100,
    input_bytes=64_000,
    progress_bytes=4_194_304,
)
LOCK_HOLDER_BUDGET = ProcessBudget(
    wall_clock_ms=2_500,
    termination_grace_ms=100,
    input_bytes=64_000,
    progress_bytes=4_194_304,
)


def run_process(*, scenario_id: str, entrypoint: str, root: Path) -> ProcessRunResult:
    return run_process_scenario(
        ProcessRunSpec(
            scenario_id=scenario_id,
            entrypoint=entrypoint,
            payload={"state_root": str(root)},
            budget=PROCESS_BUDGET,
        )
    )


def run_lock_holder(*, root: Path, ready_socket: Path) -> ProcessRunResult:
    return run_process_scenario(
        ProcessRunSpec(
            scenario_id=LOCK_HOLDER_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:hold_before_host_recorded",
            payload={"state_root": str(root), "ready_socket": str(ready_socket)},
            budget=LOCK_HOLDER_BUDGET,
        )
    )


class TestProcessDeathBeforeHostRecord:
    """Readiness survives child death before the host transaction commits its record."""

    def test_fresh_process_reconstructs_from_canonical_history(self, tmp_path: Path) -> None:
        root = tmp_path / "state"

        death = run_process(
            scenario_id=BEFORE_DEATH_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:die_before_host_recorded",
            root=root,
        )
        interrupted = observe_hamsterdan(root)
        recovery = run_process(
            scenario_id=BEFORE_RECOVERY_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:recover_before_host_recorded",
            root=root,
        )
        reconstructed = observe_hamsterdan(root)

        assert death.outcome == "harness_failure"
        assert death.returncode == -9
        assert death.failure is not None
        assert death.failure.kind == "child_failure"
        assert isinstance(death.unfinished_attempt, SubmitAttempt)
        assert death.unfinished_attempt.command.name == "hamsterdan.open_pull_request"
        assert death.prefix.operations == []
        assert interrupted.host.subjects == [EXPECTED_REGISTRATION]
        assert interrupted.host.records == []
        assert interrupted.readiness.binding is not None
        assert interrupted.readiness.history_records == 21
        assert recovery.outcome == "completed"
        assert recovery.artifact is not None
        executions = [
            operation for operation in recovery.artifact.operations if isinstance(operation, ExecuteOperation)
        ]
        assert [execution.result.disposition for execution in executions] == ["applied"]
        assert reconstructed.host.records == [EXPECTED_RECORD]
        assert reconstructed.readiness.history_records == 21


class TestConcurrentEngineExclusion:
    """Host custody admits only one readiness Engine callback for a PR root."""

    def test_contender_cannot_enter_readiness_while_the_first_action_holds_custody(self, tmp_path: Path) -> None:
        root = tmp_path / "state"
        ready_socket = tmp_path / "readiness.sock"
        with (
            socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener,
            ThreadPoolExecutor(max_workers=1) as processes,
        ):
            listener.bind(str(ready_socket))
            listener.listen(1)
            holder_future = processes.submit(run_lock_holder, root=root, ready_socket=ready_socket)
            notification, _ = listener.accept()
            with notification:
                assert notification.recv(64) == b"readiness-opened"
            contender = run_process_scenario(
                ProcessRunSpec(
                    scenario_id=BEFORE_RECOVERY_SCENARIO,
                    entrypoint="hamsterdan2.simulation.process:recover_before_host_recorded",
                    payload={"state_root": str(root)},
                    budget=CONTENDER_BUDGET,
                )
            )
            holder = holder_future.result()

        interrupted = observe_hamsterdan(root)
        recovery = run_process(
            scenario_id=BEFORE_RECOVERY_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:recover_before_host_recorded",
            root=root,
        )

        assert holder.outcome == "harness_failure"
        assert holder.failure is not None
        assert holder.failure.kind == "wall_clock_timeout"
        assert isinstance(holder.unfinished_attempt, SubmitAttempt)
        assert holder.prefix.operations == []
        assert contender.outcome == "harness_failure"
        assert contender.failure is not None
        assert contender.failure.kind == "wall_clock_timeout"
        assert contender.unfinished_attempt is None
        assert contender.prefix.operations == []
        assert contender.prefix.journal == []
        assert contender.prefix.generation is None
        assert interrupted.host.records == []
        assert interrupted.readiness.history_records == 21
        assert recovery.outcome == "completed"
        assert recovery.artifact is not None
        executions = [
            operation for operation in recovery.artifact.operations if isinstance(operation, ExecuteOperation)
        ]
        assert [execution.result.disposition for execution in executions] == ["applied"]


class TestProcessDeathAfterHostRecord:
    """The host record makes reconstruction idempotent after actual child death."""

    def test_fresh_process_replays_the_recorded_action(self, tmp_path: Path) -> None:
        root = tmp_path / "state"

        death = run_process(
            scenario_id=AFTER_DEATH_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:die_after_host_recorded",
            root=root,
        )
        recorded = observe_hamsterdan(root)
        recovery = run_process(
            scenario_id=AFTER_RECOVERY_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:recover_after_host_recorded",
            root=root,
        )
        reconstructed = observe_hamsterdan(root)

        assert death.outcome == "harness_failure"
        assert death.returncode == -9
        assert death.failure is not None
        assert death.failure.kind == "child_failure"
        assert death.unfinished_attempt is None
        executions = [operation for operation in death.prefix.operations if isinstance(operation, ExecuteOperation)]
        assert [execution.result.disposition for execution in executions] == ["applied"]
        assert death.prefix.last_check is not None
        assert recorded.host.records == [EXPECTED_RECORD]
        assert recorded.readiness.history_records == 21
        assert recovery.outcome == "completed"
        assert recovery.artifact is not None
        executions = [
            operation for operation in recovery.artifact.operations if isinstance(operation, ExecuteOperation)
        ]
        assert [execution.result.disposition for execution in executions] == ["idempotent"]
        assert reconstructed == recorded
