from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

SPIKES = Path(__file__).parents[1]
sys.path.insert(0, str(SPIKES / "09-simulation-runtime"))
sys.path.insert(0, str(SPIKES / "03-workflow-shape"))

from runtime import (
    Budget,
    BudgetExceeded,
    LeafExecuted,
    LeafOffered,
    StepCompleted,
    Timeline,
    replay,
)
from workflow_simulation import V5MutationWorkflowSimulation, WorkflowSimulation

RESOURCE_LIMITS = {
    "workflow.commands": 8,
    "workflow.history_records": 128,
    "workflow.pending_activities": 1,
}

DEFAULT_BUDGET = Budget(
    operations=256,
    owner_steps=64,
    eligible_actions=1,
    leaf_calls=64,
    choice_draws=1,
    active_faults=4,
    generations=4,
    logical_time_us=0,
    journal_entries=1_024,
    artifact_bytes=1_000_000,
    resources=RESOURCE_LIMITS,
)

HEAD = {
    "identity": "head-1",
    "head": "abc123",
    "base": "def456",
    "policy": "required-ci",
    "incarnation": 1,
}
RUN = {
    "identity": "run-7-1",
    "head": "abc123",
    "run_id": 7,
    "attempt": 1,
    "conclusion": "failure",
    "fingerprint": "tests-red",
}
OPERATION = "rerun:tests-red:7:1"

V5_HEAD: dict[str, Any] = {
    "identity": "delivery-501:head",
    "head": "a" * 40,
    "base": "b" * 40,
    "mergeable": True,
    "policy": "policy-1",
    "strict_base": True,
    "base_current": True,
}
V5_COMMENT: dict[str, Any] = {
    "identity": "delivery-501:comment",
    "id": "501",
    "kind": "change",
    "arg": "rename the config key",
    "authorized": True,
}
V5_OPERATION = f"push:comment:501:{V5_HEAD['head']}:i1"
V5_WORK = {
    "op": "change",
    "op_key": V5_OPERATION,
    "head": V5_HEAD["head"],
    "base": V5_HEAD["base"],
    "policy": V5_HEAD["policy"],
    "incarnation": 1,
    "lineage": "",
    "kind": "change",
    "instruction": V5_COMMENT["arg"],
    "run_id": 0,
    "attempt": 0,
}
V5_BUDGET = replace(
    DEFAULT_BUDGET,
    operations=512,
    owner_steps=128,
    eligible_actions=16,
    leaf_calls=128,
    journal_entries=2_048,
    artifact_bytes=2_000_000,
    resources={
        "workflow.commands": 8,
        "workflow.history_records": 512,
        "workflow.pending_activities": 16,
    },
)


class WorkflowScenario:
    """The workflow is driven only through Timeline commands, steps, and observations."""

    def __init__(self, budget: Budget = DEFAULT_BUDGET) -> None:
        self.timeline = Timeline.open((WorkflowSimulation.fresh(),), budget, seed=10)

    def admit_failure(self) -> None:
        self.timeline.command("workflow", "observe.head", HEAD)
        self.timeline.command("workflow", "observe.run", RUN)

    def execute_until_request(self) -> LeafExecuted:
        for _ in range(16):
            offered = self.timeline.start()
            assert isinstance(offered, LeafOffered)
            executed = self.timeline.execute()
            assert isinstance(executed, LeafExecuted)
            assert isinstance(executed.value, dict)
            if executed.value["cut"] == "activity_requested":
                return executed
            assert isinstance(self.timeline.finish(), StepCompleted)
        raise AssertionError("workflow did not request its rerun within 16 bounded steps")

    def settle(self) -> None:
        for _ in range(16):
            state = self.timeline.observe("workflow", "state").value
            if state["ladder"]["settled"]:
                return
            assert isinstance(self.timeline.step(), StepCompleted)
        raise AssertionError("workflow did not fold its terminal within 16 bounded steps")


class TestWorkflowRecovery:
    """A real workflow request survives frame loss and folds one typed terminal after reload."""

    def test_request_crash_reload_terminal_fold_and_exact_replay(self) -> None:
        scenario = WorkflowScenario()
        scenario.admit_failure()

        requested = scenario.execute_until_request()
        assert requested.value == {
            "activity": "rerun_gate",
            "cut": "activity_requested",
            "operation": OPERATION,
            "ready": True,
            "records_added": 4,
        }
        scenario.timeline.crash("activity_requested_before_owner_return")
        scenario.timeline = scenario.timeline.restart()
        assert isinstance(scenario.timeline.step(), StepCompleted)
        assert scenario.timeline.observe("workflow", "state").value["pending"] == {
            "activity": "rerun_gate",
            "occurrence": 8,
            "operation": OPERATION,
        }

        scenario.timeline.command(
            "workflow",
            "terminal.rerun",
            {"operation": OPERATION, "variant": "landed"},
        )
        scenario.settle()

        assert scenario.timeline.observe("workflow", "state").value == {
            "generation_loads": 2,
            "history_records": 61,
            "ladder": {"fingerprint": "tests-red", "rungs": 1, "settled": "landed"},
            "pending": None,
            "terminal": {
                "occurrence": 8,
                "op": OPERATION,
                "variant": "RerunLanded",
            },
        }
        assert scenario.timeline.observe("workflow", "check").value == {
            "expected_operation": OPERATION,
            "ok": True,
            "violations": [],
        }

        artifact = scenario.timeline.artifact("workflow-reload")
        report = replay(artifact, lambda: (WorkflowSimulation.fresh(),))

        assert report.exact
        assert report.operations == len(artifact.operations)
        assert report.journal_digest == artifact.journal_digest


class TestWorkflowCheckerSensitivity:
    """The independent checker catches a typed terminal that breaks request correlation."""

    def test_corrupted_terminal_operation_generates_an_exact_counterexample(self) -> None:
        scenario = WorkflowScenario()
        scenario.admit_failure()
        scenario.execute_until_request()
        scenario.timeline.finish()
        scenario.timeline.fault(
            "workflow",
            "terminal.rerun.corrupt_operation",
            payload={"replacement": "rerun:other:99:9"},
        )

        scenario.timeline.command(
            "workflow",
            "terminal.rerun",
            {"operation": OPERATION, "variant": "landed"},
        )
        scenario.settle()

        assert scenario.timeline.observe("workflow", "check").value == {
            "expected_operation": OPERATION,
            "ok": False,
            "violations": [
                f"RerunLanded terminal operation 'rerun:other:99:9' does not match requested operation '{OPERATION}'"
            ],
        }
        artifact = scenario.timeline.artifact("workflow-terminal-correlation")

        assert replay(artifact, lambda: (WorkflowSimulation.fresh(),)).exact
        assert any(
            entry["kind"] == "fault_match" and entry["name"] == "terminal.rerun.corrupt_operation"
            for entry in artifact.journal
        )


class TestWorkflowSurface:
    """The local simulation rejects undeclared vocabulary and exposes hard resource bounds."""

    @pytest.mark.parametrize(
        ("name", "payload", "message"),
        [
            ("observe.unknown", {}, "unknown workflow command 'observe.unknown'"),
            (
                "observe.run",
                {**RUN, "surprise": True},
                "observe.run requires exactly attempt, conclusion, fingerprint, head, identity, run_id",
            ),
            (
                "terminal.rerun",
                {"operation": OPERATION, "variant": "invented"},
                "terminal.rerun variant must be 'landed'",
            ),
        ],
    )
    def test_unknown_commands_and_inputs_fail_loudly(self, name: str, payload: object, message: str) -> None:
        scenario = WorkflowScenario()

        with pytest.raises(ValueError) as raised:
            scenario.timeline.command("workflow", name, payload)

        assert raised.value.args == (message,)

    def test_unknown_observation_fails_loudly(self) -> None:
        scenario = WorkflowScenario()

        with pytest.raises(ValueError) as raised:
            scenario.timeline.observe("workflow", "marking")

        assert raised.value.args == ("unknown workflow observation 'marking'",)

    def test_command_resource_exhaustion_is_explicit_and_replayable(self) -> None:
        budget = replace(DEFAULT_BUDGET, resources={**RESOURCE_LIMITS, "workflow.commands": 1})
        scenario = WorkflowScenario(budget)
        scenario.timeline.command("workflow", "observe.head", HEAD)

        with pytest.raises(BudgetExceeded) as raised:
            scenario.timeline.command("workflow", "observe.run", RUN)

        assert (raised.value.bound, raised.value.limit) == ("resource:workflow.commands", 1)
        artifact = scenario.timeline.artifact("workflow-command-budget")
        assert replay(artifact, lambda: (WorkflowSimulation.fresh(),)).exact
        assert artifact.operations[-1]["accepted"] is True


class V5MutationScenario:
    """The current production V5 Net declares mutation work while unrelated Activities stay held."""

    def __init__(self) -> None:
        self.timeline = Timeline.open((V5MutationWorkflowSimulation.fresh(),), V5_BUDGET, seed=10)

    def request_mutation(self, comment: dict[str, Any] = V5_COMMENT) -> dict[str, Any]:
        self.timeline.command("workflow", "observe.head", V5_HEAD)
        for _ in range(16):
            state = cast(dict[str, Any], self.timeline.observe("workflow", "state").value)
            if state["life_state"]["head"] == V5_HEAD["head"]:
                break
            assert isinstance(self.timeline.step(), StepCompleted)
        else:
            raise AssertionError("real V5 workflow did not admit the head within 16 bounded steps")
        self.timeline.command("workflow", "observe.comment", comment)
        for _ in range(64):
            state = cast(dict[str, Any], self.timeline.observe("workflow", "state").value)
            if state["pending"] is not None:
                return state
            assert isinstance(self.timeline.step(), StepCompleted)
        raise AssertionError("real V5 workflow did not request git_gate within 64 bounded steps")

    def settle(self) -> dict[str, Any]:
        for _ in range(64):
            state = cast(dict[str, Any], self.timeline.observe("workflow", "state").value)
            if (
                state["terminal"] is not None
                and state["mutation_state"] is not None
                and state["life_state"]["expected"]
            ):
                return state
            assert isinstance(self.timeline.step(), StepCompleted)
        raise AssertionError("real V5 workflow did not fold Pushed within 64 bounded steps")


class TestRealV5MutationWorkflow:
    """The simulation executes production conversation and mutation folds without shadow semantics."""

    def test_authorized_comment_reaches_one_exact_production_git_gate(self) -> None:
        scenario = V5MutationScenario()

        state = scenario.request_mutation()

        pending = state["pending"]
        assert pending == {
            "activity": "git_gate",
            "occurrence": pending["occurrence"],
            "operation": V5_OPERATION,
            "idempotency": V5_OPERATION,
            "work": V5_WORK,
        }
        assert state["request"] == {
            "activity": "git_gate",
            "occurrence": pending["occurrence"],
            "correlation": V5_OPERATION,
            "idempotency": V5_OPERATION,
            "work": V5_WORK,
        }
        assert set(state["held_activities"]) > {"git_gate"}
        assert state["source"] == "hamsterdan.readiness.net_v5.topology.build_net_v5"

    def test_pending_work_reconstructs_and_real_pushed_fold_replays_exactly(self) -> None:
        scenario = V5MutationScenario()
        state = scenario.request_mutation()
        occurrence = state["pending"]["occurrence"]
        scenario.timeline.crash("v5_mutation_requested")
        scenario.timeline = scenario.timeline.restart()
        for _ in range(16):
            reloaded = scenario.timeline.observe("workflow", "state").value
            if reloaded["pending"] is not None:
                break
            assert isinstance(scenario.timeline.step(), StepCompleted)
        else:
            raise AssertionError("real V5 git_gate was not reconstructed")
        assert reloaded["pending"]["occurrence"] == occurrence
        assert reloaded["pending"]["work"] == V5_WORK
        pushed = {
            "op": "change",
            "op_key": V5_OPERATION,
            "head": V5_HEAD["head"],
            "new_head": "c" * 40,
            "incarnation": 1,
            "lineage": "",
        }

        scenario.timeline.command(
            "workflow",
            "terminal.mutation",
            {"occurrence": occurrence, "value": pushed},
        )
        settled = scenario.settle()

        assert settled["terminal"] == {
            "occurrence": occurrence,
            "operation": V5_OPERATION,
            "variant": "Pushed",
            "value": pushed,
        }
        assert settled["request"] == {
            "activity": "git_gate",
            "occurrence": occurrence,
            "correlation": V5_OPERATION,
            "idempotency": V5_OPERATION,
            "work": V5_WORK,
        }
        assert settled["mutation_state"]["state"] == "idle"
        assert settled["life_state"]["expected"] == pushed["new_head"]
        assert scenario.timeline.observe("workflow", "check").value == {
            "ok": True,
            "violations": [],
        }
        artifact = scenario.timeline.artifact("real-v5-workflow-mutation")
        assert replay(artifact, lambda: (V5MutationWorkflowSimulation.fresh(),)).exact

    def test_unauthorized_comment_never_declares_mutation_work(self) -> None:
        scenario = V5MutationScenario()
        scenario.timeline.command("workflow", "observe.head", V5_HEAD)
        scenario.timeline.command(
            "workflow",
            "observe.comment",
            {**V5_COMMENT, "identity": "delivery-502:comment", "authorized": False},
        )
        for _ in range(64):
            result = scenario.timeline.step()
            if not isinstance(result, StepCompleted):
                break

        state = scenario.timeline.observe("workflow", "state").value

        assert state["pending"] is None
        assert state["request"] is None
        assert "git_gate" not in state["held_activities"]
