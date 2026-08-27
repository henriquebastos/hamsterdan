from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

from hamsterdan.agents.protocol import AgentProtocolError

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "09-simulation-runtime"))

from agents_simulation import (
    AGENT_BUDGET,
    AgentsChecker,
    AgentsSimulation,
    canceled_coding_submission,
    production_port_submissions,
    run_failure_proof,
)
from runtime import StepCompleted, Timeline, replay


class AgentFailureRecoveryContract(unittest.TestCase):
    """Runtime loss and a lost delivery response recover from durable identities."""

    def test_failure_reconstructs_without_duplicate_run_or_terminal_acceptance(self) -> None:
        proof = run_failure_proof()

        self.assertTrue(proof.replay.exact)
        self.assertTrue(proof.check.passed, proof.check.violations)
        self.assertEqual(proof.final["state"], "delivered")
        self.assertEqual(proof.final["run_source"], "lookup")
        self.assertEqual(proof.final["delivery_source"], "lookup")
        self.assertEqual(proof.final["runtime_starts"], 1)
        self.assertEqual(proof.final["terminal_lookups"], 1)
        self.assertEqual(proof.final["delivery_attempts"], 2)
        self.assertEqual(proof.final["accepted_deliveries"], 1)
        self.assertEqual(proof.crash_phases, ("executed", "executed"))

        encoded = proof.artifact.encode().lower()
        for forbidden in (b"password", b"private_key", b"api_key", b"credential"):
            self.assertNotIn(forbidden, encoded)


class AgentCancellationContract(unittest.TestCase):
    """Cancellation becomes one typed terminal without running the operation."""

    def test_accepted_operation_cancels_and_delivers_once(self) -> None:
        module = AgentsSimulation()
        timeline = Timeline.open((module,), AGENT_BUDGET)
        submission = canceled_coding_submission()
        operation, attempt = submission["operation"], submission["attempt"]

        timeline.command("agents", "submit", submission)
        accepted = timeline.step()
        self.assertIsInstance(accepted, StepCompleted)
        self.assertEqual(accepted.action.name, "accept")
        timeline.command(
            "agents",
            "cancel",
            {"operation": operation, "attempt": attempt, "reason": "authority-moved"},
        )

        canceled = timeline.step()
        delivered = timeline.step()
        final = timeline.observe(
            "agents",
            "operation",
            {"operation": operation, "attempt": attempt},
        ).value

        self.assertEqual((canceled.action.name, delivered.action.name), ("cancel", "deliver"))
        self.assertEqual(final["state"], "delivered")
        self.assertEqual(final["terminal_kind"], "failure")
        self.assertEqual(final["terminal_status"], "canceled")
        self.assertEqual(final["runtime_starts"], 0)
        self.assertEqual(final["cancel_calls"], 1)
        self.assertEqual(final["accepted_deliveries"], 1)

        timeline.observe("agents", "state")
        artifact = timeline.artifact("agent-cancellation")
        check = AgentsChecker.check(artifact)
        report = replay(artifact, lambda: (AgentsSimulation(),))
        self.assertTrue(check.passed, check.violations)
        self.assertTrue(report.exact)


class ProductionPortCorrespondenceContract(unittest.TestCase):
    """Every production AgentRunner request kind crosses the strict submit command."""

    def test_review_conversation_and_coding_requests_are_admitted(self) -> None:
        module = AgentsSimulation()
        timeline = Timeline.open((module,), AGENT_BUDGET)

        for submission in production_port_submissions():
            with self.subTest(kind=submission["kind"]):
                result = timeline.command("agents", "submit", submission)
                self.assertEqual(result["kind"], submission["kind"])
                self.assertEqual(result["state"], "submitted")

        state = timeline.observe("agents", "state").value
        self.assertEqual([item["kind"] for item in state["operations"]], ["coding", "conversation", "review"])


class StrictAgentVocabularyContract(unittest.TestCase):
    """Unknown commands, observations, operations, and credential-shaped input fail loud."""

    def test_unknown_and_secret_shaped_inputs_are_rejected_without_state_change(self) -> None:
        module = AgentsSimulation()
        timeline = Timeline.open((module,), AGENT_BUDGET)
        submission = production_port_submissions()[0]

        with self.assertRaisesRegex(ValueError, "unknown agents command"):
            timeline.command("agents", "invent", {})
        with self.assertRaisesRegex(ValueError, "unknown agents observation"):
            timeline.observe("agents", "invent")
        with self.assertRaisesRegex(ValueError, "unknown agent operation"):
            timeline.command(
                "agents",
                "cancel",
                {"operation": "review:missing", "attempt": 1, "reason": "authority-moved"},
            )

        secret_shaped = dict(submission)
        secret_shaped["request"] = {**submission["request"], "api_key": "not-a-real-secret"}
        with self.assertRaisesRegex(ValueError, "credential-shaped field"):
            timeline.command("agents", "submit", secret_shaped)

        self.assertEqual(timeline.observe("agents", "state").value["operations"], [])

    def test_coding_non_object_terminal_uses_protocol_validation_without_mutation(self) -> None:
        module = AgentsSimulation()
        timeline = Timeline.open((module,), AGENT_BUDGET)
        submission = canceled_coding_submission()
        timeline.command("agents", "submit", submission)
        timeline.step()

        with self.assertRaisesRegex(AgentProtocolError, "result must be a JSON object"):
            timeline.command(
                "agents",
                "terminal",
                {
                    "operation": submission["operation"],
                    "attempt": submission["attempt"],
                    "result": [],
                },
            )

        state = timeline.observe(
            "agents",
            "operation",
            {"operation": submission["operation"], "attempt": submission["attempt"]},
        ).value
        self.assertEqual(state["state"], "accepted")
        self.assertFalse(state["runtime_terminal_available"])


class IndependentAgentCheckerContract(unittest.TestCase):
    """The checker derives counts from the artifact rather than trusting module state."""

    def test_checker_preserves_delivered_state_on_idempotent_resubmit(self) -> None:
        module = AgentsSimulation()
        timeline = Timeline.open((module,), AGENT_BUDGET)
        submission = canceled_coding_submission()
        operation, attempt = submission["operation"], submission["attempt"]
        timeline.command("agents", "submit", submission)
        timeline.step()
        timeline.command(
            "agents",
            "cancel",
            {"operation": operation, "attempt": attempt, "reason": "authority-moved"},
        )
        timeline.step()
        timeline.step()

        repeated = timeline.command("agents", "submit", submission)
        timeline.observe("agents", "state")
        artifact = timeline.artifact("agent-idempotent-resubmit")
        check = AgentsChecker.check(artifact)
        report = replay(artifact, lambda: (AgentsSimulation(),))

        self.assertEqual(repeated["state"], "delivered")
        self.assertTrue(check.passed, check.violations)
        self.assertTrue(report.exact)

    def test_checker_state_survives_a_rejected_submit_collision(self) -> None:
        module = AgentsSimulation()
        timeline = Timeline.open((module,), AGENT_BUDGET)
        submission = canceled_coding_submission()
        operation, attempt = submission["operation"], submission["attempt"]
        timeline.command("agents", "submit", submission)
        timeline.step()
        timeline.command(
            "agents",
            "cancel",
            {"operation": operation, "attempt": attempt, "reason": "authority-moved"},
        )
        timeline.step()
        timeline.step()
        collision = {
            **submission,
            "request": {
                **submission["request"],
                "ref": "hamsterdan/mutation/collision",
            },
        }

        with self.assertRaisesRegex(ValueError, "identity collides"):
            timeline.command("agents", "submit", collision)

        final = timeline.observe(
            "agents",
            "operation",
            {"operation": operation, "attempt": attempt},
        ).value
        timeline.observe("agents", "state")
        artifact = timeline.artifact("agent-rejected-submit-collision")
        check = AgentsChecker.check(artifact)
        report = replay(artifact, lambda: (AgentsSimulation(),))

        self.assertEqual(final["state"], "delivered")
        self.assertTrue(check.passed, check.violations)
        self.assertTrue(report.exact)

    def test_checker_rejects_a_corrupted_delivery_count(self) -> None:
        proof = run_failure_proof()
        operations = list(proof.artifact.operations)
        final = dict(operations[-1])
        result = dict(final["result"])
        value = dict(result["value"])
        operation = dict(value["operations"][0])
        operation["accepted_deliveries"] = 2
        value["operations"] = [operation]
        result["value"] = value
        final["result"] = result
        operations[-1] = final
        corrupted = replace(proof.artifact, operations=tuple(operations))

        check = AgentsChecker.check(corrupted)

        self.assertFalse(check.passed)
        self.assertIn("accepted_deliveries expected 1, observed 2", check.violations)


class AgentResourceBoundContract(unittest.TestCase):
    """The module refuses excess retained operations before changing its store."""

    def test_operation_bound_rejects_before_mutation(self) -> None:
        module = AgentsSimulation(max_operations=1)
        timeline = Timeline.open((module,), AGENT_BUDGET)
        first, second, *_ = production_port_submissions()

        timeline.command("agents", "submit", first)
        with self.assertRaisesRegex(ValueError, "operation bound"):
            timeline.command("agents", "submit", second)

        operations = timeline.observe("agents", "state").value["operations"]
        self.assertEqual([item["operation"] for item in operations], [first["operation"]])


if __name__ == "__main__":
    unittest.main()
