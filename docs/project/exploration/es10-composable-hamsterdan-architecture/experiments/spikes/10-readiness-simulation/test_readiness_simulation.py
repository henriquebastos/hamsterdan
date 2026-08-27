from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from typing import Any, cast

import pytest
from readiness_simulation import (
    DEFAULT_BUDGET,
    ReadinessChecker,
    ReadinessModule,
    arm_readiness_fault,
)
from runtime import Artifact, LeafExecuted, LeafOffered, StepCompleted, Timeline, Waiting, replay

from hamsterdan.agents.protocol import CodingRequest, CodingResult
from hamsterdan.contracts.readiness_v5 import MutWork
from hamsterdan.host.git_publish import payload_digest
from hamsterdan.host.v5.mutation import V5MutationGate

HEAD = "a" * 40
BASE = "b" * 40
MOVED_HEAD = "d" * 40
OPERATION = f"push:comment:9:{HEAD}:i3"
AUTHORITY: dict[str, Any] = {
    "phase": "running",
    "incarnation": 3,
    "head": HEAD,
    "base": BASE,
    "policy": "policy-1",
}
WORK: dict[str, Any] = {
    "op": "change",
    "op_key": OPERATION,
    "head": HEAD,
    "base": BASE,
    "policy": "policy-1",
    "incarnation": 3,
    "lineage": "",
    "kind": "change",
    "instruction": "rename the config key",
    "run_id": 0,
    "attempt": 0,
}


def coding_result(*, message: str = "Apply requested change", status: str = "changed") -> CodingResult:
    request = V5MutationGate.request("owner/repo", 7, MutWork(**WORK))
    changed = status == "changed"
    return CodingResult(
        kind=request.kind,
        repository=request.repository,
        pull_request=request.pull_request,
        epoch=request.epoch,
        head=request.head,
        base=request.base,
        ref=request.ref,
        status=status,
        reproduction_status="not_attempted",
        diff="diff --git a/a b/a\n" if changed else "",
        changed_files=["a"] if changed else [],
        validation_evidence=[{"command": "synthetic", "result": "passed"}] if changed else [],
        proposed_commit_message=message if changed else "",
    )


class InjectedCodingAgent:
    def __init__(self, result: CodingResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def code(
        self,
        repository_url: str,
        request: CodingRequest,
        *,
        operation: str,
        attempt: int,
        is_current: object = None,
    ) -> CodingResult:
        self.calls.append(
            {
                "repository_url": repository_url,
                "request": request,
                "operation": operation,
                "attempt": attempt,
            }
        )
        assert callable(is_current) and cast(Callable[[], bool], is_current)()
        return self.result


def build_readiness() -> tuple[ReadinessModule]:
    return (ReadinessModule(),)


class TestReadinessSimulationContract:
    """Readiness recovers one accepted hidden Git effect under its real mutation gate."""

    def open(self, *, provider: dict[str, object] = AUTHORITY) -> Timeline:
        timeline = Timeline.open(build_readiness(), DEFAULT_BUDGET, seed=10)
        timeline.command("readiness", "admit_grant", AUTHORITY)
        timeline.command("readiness", "set_provider_authority", provider)
        timeline.command("readiness", "request_mutation", WORK)
        return timeline

    def lose_response_and_recover(self) -> tuple[Timeline, dict[str, object], dict[str, object]]:
        timeline = self.open()
        arm_readiness_fault(
            timeline,
            "git_response_lost",
            {"operation": OPERATION},
            occurrence=1,
        )

        offered = timeline.start()
        assert isinstance(offered, LeafOffered)
        assert offered.leaf.name == "mutation.git_gate"
        timeline.crash("after_activity_attempt_claimed")
        timeline = timeline.restart()

        assert isinstance(timeline.start(), LeafOffered)
        executed = timeline.execute()
        assert isinstance(executed, LeafExecuted)
        assert executed.error is None
        assert cast(dict[str, object], executed.value)["variant"] == "FaultM"
        timeline.crash("after_activity_effect_observed")
        timeline = timeline.restart()

        ambiguous = cast(dict[str, object], timeline.observe("readiness", "state").value)
        ambiguous_check = cast(dict[str, object], timeline.observe("readiness", "check").value)
        assert ambiguous_check == {
            "passed": True,
            "status": "recoverable_ambiguity",
            "violations": [],
            "facts": {
                "accepted_effects": 1,
                "agent_calls": 1,
                "pending_requests": 1,
                "terminals": 0,
            },
        }

        recovered = timeline.step()
        assert isinstance(recovered, StepCompleted)
        assert recovered.value == {
            "cut": "activity_terminal_recorded",
            "operation": OPERATION,
            "variant": "Pushed",
        }
        timeline.crash("after_activity_terminal_recorded")
        timeline = timeline.restart()

        final = cast(dict[str, object], timeline.observe("readiness", "state").value)
        assert timeline.observe("readiness", "check").value == {
            "passed": True,
            "status": "settled",
            "violations": [],
            "facts": {
                "accepted_effects": 1,
                "agent_calls": 1,
                "pending_requests": 0,
                "terminals": 1,
            },
        }
        assert isinstance(timeline.start(), Waiting)
        return timeline, ambiguous, final

    def test_response_loss_crosses_durable_cuts_and_replays_exactly(self) -> None:
        timeline, ambiguous, final = self.lose_response_and_recover()

        provider = cast(dict[str, object], ambiguous["provider"])
        [publication] = cast(list[dict[str, object]], provider["publications"])
        assert publication["operation"] == OPERATION
        assert publication["response_lost"] is True
        assert publication["recovered"] is False
        assert ambiguous["terminals"] == []

        final_provider = cast(dict[str, object], final["provider"])
        [recovered_publication] = cast(list[dict[str, object]], final_provider["publications"])
        assert recovered_publication["recovered"] is True
        assert final_provider["authority"] == AUTHORITY | {"head": recovered_publication["result_head"]}
        assert final["claims"] == [OPERATION]
        [terminal] = cast(list[dict[str, object]], final["terminals"])
        assert terminal == {
            "operation": OPERATION,
            "variant": "Pushed",
            "value": {
                "op": "change",
                "op_key": OPERATION,
                "head": HEAD,
                "new_head": recovered_publication["result_head"],
                "incarnation": 3,
                "lineage": "",
            },
        }
        assert [call["kind"] for call in cast(list[dict[str, object]], final_provider["calls"])] == [
            "reconcile",
            "claim",
            "agent",
            "claim",
            "claim",
            "publish_accepted",
            "reconcile",
        ]

        artifact = timeline.artifact("readiness-response-lost")
        decoded = Artifact.decode(artifact.encode())
        report = replay(decoded, build_readiness)

        assert report.exact
        assert report.operations == len(artifact.operations)
        assert report.journal_digest == artifact.journal_digest
        assert [operation["result"]["phase"] for operation in artifact.operations if operation["kind"] == "crash"] == [
            "offered",
            "executed",
            "idle",
        ]

    def test_current_authority_movement_fails_before_agent_or_git_effect(self) -> None:
        timeline = self.open(provider=AUTHORITY | {"head": MOVED_HEAD})

        completed = timeline.step()

        assert isinstance(completed, StepCompleted)
        assert completed.value["variant"] == "FaultM"
        state = cast(dict[str, object], timeline.observe("readiness", "state").value)
        provider = cast(dict[str, object], state["provider"])
        assert provider["publications"] == []
        assert [call["kind"] for call in cast(list[dict[str, object]], provider["calls"])] == [
            "reconcile",
            "claim",
        ]
        assert timeline.observe("readiness", "check").value == {
            "passed": True,
            "status": "fenced",
            "violations": [],
            "facts": {
                "accepted_effects": 0,
                "agent_calls": 0,
                "pending_requests": 0,
                "terminals": 1,
            },
        }

    def test_checker_derives_duplicate_physical_acceptance_from_observable_calls(self) -> None:
        _timeline, ambiguous, _final = self.lose_response_and_recover()
        corrupted = deepcopy(ambiguous)
        provider = cast(dict[str, object], corrupted["provider"])
        publications = cast(list[dict[str, object]], provider["publications"])
        assert len(publications) == 1
        calls = cast(list[dict[str, object]], provider["calls"])
        [accepted] = [call for call in calls if call["kind"] == "publish_accepted"]
        calls.append(accepted | {"sequence": cast(int, calls[-1]["sequence"]) + 1})

        report = ReadinessChecker().check(corrupted)

        assert report["passed"] is False
        assert cast(dict[str, object], report["facts"])["accepted_effects"] == 2
        assert report["violations"] == [
            {
                "operation": OPERATION,
                "rule": "one_effect_acceptance_per_operation",
                "observed": 2,
            }
        ]

    def test_checker_derives_lookup_first_recovery_from_observable_call_order(self) -> None:
        _timeline, _ambiguous, final = self.lose_response_and_recover()
        corrupted = deepcopy(final)
        provider = cast(dict[str, object], corrupted["provider"])
        [publication] = cast(list[dict[str, object]], provider["publications"])
        publication["recovered"] = False
        calls = cast(list[dict[str, object]], provider["calls"])
        assert calls[-1]["kind"] == "reconcile"
        calls[-1] = calls[-1] | {"kind": "agent"}

        report = ReadinessChecker().check(corrupted)

        assert report["passed"] is False
        assert report["violations"] == [{"operation": OPERATION, "rule": "recovery_is_lookup_first"}]


class TestInjectedCodingDependency:
    """Readiness publishes the exact injected CodingResult while retaining its standalone default."""

    def run_changed(self, message: str) -> tuple[InjectedCodingAgent, dict[str, object]]:
        result = coding_result(message=message)
        agent = InjectedCodingAgent(result)
        timeline = Timeline.open((ReadinessModule(runner=agent),), DEFAULT_BUDGET, seed=10)
        timeline.command("readiness", "admit_grant", AUTHORITY)
        timeline.command("readiness", "set_provider_authority", AUTHORITY)
        timeline.command("readiness", "request_mutation", WORK)

        completed = timeline.step()

        assert isinstance(completed, StepCompleted)
        assert completed.value["variant"] == "Pushed"
        state = cast(dict[str, object], timeline.observe("readiness", "state").value)
        provider = cast(dict[str, object], state["provider"])
        [publication] = cast(list[dict[str, object]], provider["publications"])
        assert publication["coding_result_digest"] == payload_digest(
            {"schema_version": 1, "coding_result": asdict(result)}
        )
        assert [call["kind"] for call in cast(list[dict[str, object]], provider["calls"])] == [
            "reconcile",
            "claim",
            "agent",
            "claim",
            "claim",
            "publish_accepted",
        ]
        return agent, publication

    def test_valid_result_change_alters_the_accepted_publication(self) -> None:
        first_agent, first = self.run_changed("Apply requested change")
        second_agent, second = self.run_changed("Apply bounded rename")

        assert len(first_agent.calls) == len(second_agent.calls) == 1
        assert first["operation"] == second["operation"] == OPERATION
        assert first["payload_digest"] == second["payload_digest"]
        assert first["coding_result_digest"] != second["coding_result_digest"]
        assert first["result_head"] != second["result_head"]

    def test_unchanged_injected_result_declines_without_a_git_effect(self) -> None:
        agent = InjectedCodingAgent(coding_result(status="unchanged"))
        timeline = Timeline.open((ReadinessModule(runner=agent),), DEFAULT_BUDGET, seed=10)
        timeline.command("readiness", "admit_grant", AUTHORITY)
        timeline.command("readiness", "set_provider_authority", AUTHORITY)
        timeline.command("readiness", "request_mutation", WORK)

        completed = timeline.step()

        assert isinstance(completed, StepCompleted)
        assert completed.value["variant"] == "DeclinedM"
        state = cast(dict[str, object], timeline.observe("readiness", "state").value)
        provider = cast(dict[str, object], state["provider"])
        assert provider["publications"] == []
        assert len(agent.calls) == 1


class TestReadinessVocabularyContract:
    """The local simulation refuses every undeclared command, observation, fault, and payload."""

    def test_unknown_vocabulary_and_malformed_inputs_fail_loudly(self) -> None:
        timeline = Timeline.open(build_readiness(), DEFAULT_BUDGET, seed=10)

        with pytest.raises(ValueError) as unknown_command:
            timeline.command("readiness", "invent", {})
        assert unknown_command.value.args == (
            "unknown readiness command 'invent'; expected admit_grant, request_mutation, or set_provider_authority",
        )
        with pytest.raises(ValueError) as malformed_authority:
            timeline.command("readiness", "admit_grant", {"head": HEAD})
        assert malformed_authority.value.args == (
            "authority payload must contain exactly ['base', 'head', 'incarnation', 'phase', 'policy']",
        )
        with pytest.raises(ValueError) as unknown_observation:
            timeline.observe("readiness", "invent")
        assert unknown_observation.value.args == ("unknown readiness observation 'invent'; expected check or state",)
        with pytest.raises(ValueError) as unknown_fault:
            arm_readiness_fault(timeline, "invent", {}, occurrence=1)
        assert unknown_fault.value.args == ("unknown readiness fault 'invent'; expected git_response_lost",)
        with pytest.raises(ValueError) as malformed_fault:
            arm_readiness_fault(timeline, "git_response_lost", {}, occurrence=1)
        assert malformed_fault.value.args == ("git_response_lost payload must contain exactly ['operation']",)
