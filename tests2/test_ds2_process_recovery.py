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

from hamsterdan2.readiness.simulation.lifecycle import ReadinessState
from hamsterdan2.simulation.hamsterdan import EXPECTED_DELIVERY, HostState, observe_hamsterdan
from hamsterdan2.simulation.process import CUSTODY_DEATH_SCENARIO, CUSTODY_RECOVERY_SCENARIO


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
        assert interrupted.readiness == ReadinessState(binding=None, history_records=0)
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
