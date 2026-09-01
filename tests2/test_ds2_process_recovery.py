# Copyright (c) 2026 Henrique Bastos

"""Actual process loss after durable webhook custody and before acknowledgement."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from petrus.testing.dst import (
    ExecuteOperation,
    ProcessBudget,
    ProcessRunSpec,
    SubmitAttempt,
    run_process_scenario,
)

from hamsterdan2.readiness.simulation.lifecycle import EXPECTED_HISTORY_DELIVERY_IDENTITY, ReadinessState
from hamsterdan2.simulation.hamsterdan import (
    EXPECTED_DELIVERY,
    EXPECTED_STAGING,
    OPEN_PULL_REQUEST_COMMAND,
    RECEIVE_WEBHOOK_COMMAND,
    STAGE_WEBHOOK_COMMAND,
    HostState,
    build_hamsterdan_world,
    observe_hamsterdan,
)
from hamsterdan2.simulation.process import (
    CUSTODY_DEATH_SCENARIO,
    CUSTODY_RECOVERY_SCENARIO,
    HISTORY_ACCEPTANCE_DEATH_SCENARIO,
    HISTORY_ACCEPTANCE_RECOVERY_SCENARIO,
    STAGING_DEATH_SCENARIO,
    STAGING_RECOVERY_SCENARIO,
)


if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue


PROCESS_BUDGET = ProcessBudget(
    wall_clock_ms=10_000,
    termination_grace_ms=500,
    input_bytes=64_000,
    progress_bytes=4_194_304,
)


def run_custody_process(*, scenario_id: str, entrypoint: str, root: Path):
    return run_process_scenario(
        ProcessRunSpec(
            scenario_id=scenario_id,
            entrypoint=entrypoint,
            payload={"state_root": str(root)},
            budget=PROCESS_BUDGET,
        )
    )


class TestProcessDeathBeforeWebhookAcknowledgement:
    """Committed custody survives SIGKILL while the acknowledgement is absent."""

    def test_fresh_process_classifies_the_signed_redelivery_as_an_exact_duplicate(self, tmp_path: Path) -> None:
        root = tmp_path / "state"

        death = run_custody_process(
            scenario_id=CUSTODY_DEATH_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:die_after_delivery_custodied",
            root=root,
        )
        interrupted = observe_hamsterdan(root)
        recovery = run_custody_process(
            scenario_id=CUSTODY_RECOVERY_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:recover_delivery_custody",
            root=root,
        )
        reconstructed = observe_hamsterdan(root)

        assert death.outcome == "harness_failure"
        assert death.returncode == -9
        assert death.failure is not None
        assert death.failure.kind == "child_failure"
        assert isinstance(death.unfinished_attempt, SubmitAttempt)
        assert death.unfinished_attempt.command.name == "hamsterdan.receive_webhook"
        assert death.prefix.operations == []
        assert interrupted.delivery.rows == 1
        assert interrupted.delivery.retained == EXPECTED_DELIVERY
        assert interrupted.host == HostState(subjects=[], records=[])
        assert interrupted.readiness == ReadinessState(
            binding=None,
            history_records=0,
            in_flight_occurrences=0,
        )
        assert recovery.outcome == "completed"
        assert recovery.artifact is not None
        executions = [
            operation for operation in recovery.artifact.operations if isinstance(operation, ExecuteOperation)
        ]
        assert [execution.result.disposition for execution in executions] == ["idempotent"]
        receipt = cast("dict[str, JsonValue]", executions[0].result.value)
        assert receipt == {
            "custody": "durable",
            "provider_route_id": "github:primary",
            "delivery_id": "11111111-1111-4111-8111-111111111111",
            "custody_generation": 1,
            "disposition": "exact_duplicate",
        }
        assert reconstructed == interrupted
        assert sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()) == [
            "deliveries.sqlite3"
        ]


class TestProcessDeathBeforeStagingAcknowledgement:
    """Committed source-neutral staging survives SIGKILL before caller success."""

    def test_fresh_authority_reconstructs_and_reoffers_without_second_authority(self, tmp_path: Path) -> None:
        root = tmp_path / "state"
        custody = run_custody_process(
            scenario_id=CUSTODY_RECOVERY_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:recover_delivery_custody",
            root=root,
        )

        death = run_custody_process(
            scenario_id=STAGING_DEATH_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:die_after_staging_durable",
            root=root,
        )
        interrupted = observe_hamsterdan(root)
        recovery = run_custody_process(
            scenario_id=STAGING_RECOVERY_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:recover_staging_custody",
            root=root,
        )
        reconstructed = observe_hamsterdan(root)

        assert custody.outcome == "completed"
        assert death.outcome == "harness_failure"
        assert death.returncode == -9
        assert isinstance(death.unfinished_attempt, SubmitAttempt)
        assert death.unfinished_attempt.command.name == "hamsterdan.stage_webhook"
        assert death.prefix.operations == []
        assert interrupted.ingress.posture == EXPECTED_STAGING
        assert interrupted.ingress.resources.manifests == 1
        assert interrupted.ingress.resources.entries == 1
        assert interrupted.ingress.resources.grants == 1
        assert interrupted.ingress.resources.decisions == 1
        assert interrupted.readiness == ReadinessState(
            binding=None,
            history_records=0,
            in_flight_occurrences=0,
            staging=EXPECTED_STAGING,
        )
        assert recovery.outcome == "completed"
        assert recovery.artifact is not None
        executions = [
            operation for operation in recovery.artifact.operations if isinstance(operation, ExecuteOperation)
        ]
        assert [execution.result.disposition for execution in executions] == ["idempotent"]
        posture = cast("dict[str, JsonValue]", executions[0].result.value)
        assert posture["disposition"] == "exact_duplicate"
        assert reconstructed == interrupted
        assert reconstructed.ingress.resources.manifests == 1
        assert not list(root.rglob("history.sqlite3"))
        assert sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()) == [
            "deliveries.sqlite3",
            "readiness-ingress.sqlite3",
        ]


class TestProcessDeathBeforeHistoryAcceptanceAcknowledgement:
    """Committed acceptance survives SIGKILL without completing the occurrence."""

    def test_fresh_authority_exact_reoffers_the_same_unfinished_occurrence(self, tmp_path: Path) -> None:
        root = tmp_path / "state"
        world = build_hamsterdan_world(root=root)
        try:
            timeline = world.timeline()
            timeline.command(
                "hamsterdan.open_pull_request",
                OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            )
            timeline.command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            timeline.command(
                "hamsterdan.stage_webhook",
                STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
        finally:
            world.close()

        death = run_custody_process(
            scenario_id=HISTORY_ACCEPTANCE_DEATH_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:die_after_history_accepted",
            root=root,
        )
        interrupted = observe_hamsterdan(root)
        recovery = run_custody_process(
            scenario_id=HISTORY_ACCEPTANCE_RECOVERY_SCENARIO,
            entrypoint="hamsterdan2.simulation.process:recover_history_acceptance",
            root=root,
        )
        reconstructed = observe_hamsterdan(root)

        assert death.outcome == "harness_failure"
        assert death.returncode == -9
        assert isinstance(death.unfinished_attempt, SubmitAttempt)
        assert death.unfinished_attempt.command.name == "hamsterdan.accept_staged_observation"
        assert death.prefix.operations == []
        assert interrupted.readiness.history_records == 23
        assert interrupted.readiness.accepted
        assert not interrupted.readiness.folded
        assert interrupted.readiness.delivery is not None
        assert interrupted.readiness.delivery.delivery_identity == EXPECTED_HISTORY_DELIVERY_IDENTITY
        assert interrupted.readiness.delivery.occurrence == 1
        assert recovery.outcome == "completed"
        assert recovery.artifact is not None
        executions = [
            operation for operation in recovery.artifact.operations if isinstance(operation, ExecuteOperation)
        ]
        assert [execution.command.name for execution in executions] == ["hamsterdan.accept_staged_observation"]
        assert [execution.result.disposition for execution in executions] == ["idempotent"]
        acceptance = cast("dict[str, JsonValue]", executions[0].result.value)
        assert acceptance["disposition"] == "accepted"
        assert acceptance["occurrence"] == 1
        assert acceptance["finished"] is False
        assert acceptance["folded"] is False
        assert reconstructed == interrupted
        files = [path for path in root.rglob("*") if path.is_file()]
        locks = [path for path in files if path.parent.name == ".impetus-sqlite-locks"]
        retained = sorted(str(path.relative_to(root)) for path in files if path not in locks)
        assert len(locks) == 1
        assert locks[0].stat().st_size == 0
        assert retained == [
            "catalog.sqlite3",
            "deliveries.sqlite3",
            "dispatch.sqlite3",
            "instances/44/31/7/history.sqlite3",
            "instances/44/31/7/readiness.sqlite3",
            "readiness-ingress.sqlite3",
        ]
