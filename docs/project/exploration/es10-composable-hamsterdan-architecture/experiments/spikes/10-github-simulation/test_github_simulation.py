from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

SPIKE_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = SPIKE_ROOT.parent / "09-simulation-runtime"
sys.path[:0] = [str(SPIKE_ROOT), str(RUNTIME_ROOT)]

from github_simulation import (
    DEFAULT_BUDGET,
    GitHubChecker,
    GitHubSimulation,
    GitHubSimulationContractError,
    github_fault,
)
from runtime import Artifact, LeafExecuted, LeafOffered, StepCompleted, Timeline, replay

HEAD_A = "a" * 40
HEAD_B = "b" * 40
BASE_A = "c" * 40
BASE_B = "d" * 40
POLICY_A = "policy-a"
POLICY_B = "policy-b"


def authority(epoch: int, head: str, base: str, policy: str) -> dict[str, object]:
    return {"epoch": epoch, "head": head, "base": base, "policy": policy}


class GitHubSimulationContract(unittest.TestCase):
    """The GitHub module exposes strict bounded behavior through S9's Timeline."""

    def setUp(self) -> None:
        self.module = GitHubSimulation()
        self.timeline = Timeline.open((self.module,), DEFAULT_BUDGET, seed=7)

    def set_authority(self, value: dict[str, object]) -> None:
        self.timeline.command("github", "authority.set", value)

    def schedule_read(self, request: str) -> None:
        self.timeline.command(
            "github",
            "authority.read",
            {"request": request, "at_us": self.timeline.now_us},
        )

    def schedule_publication(
        self,
        request: str,
        operation: str,
        body: str,
        authored: dict[str, object],
    ) -> None:
        self.timeline.command(
            "github",
            "publication.request",
            {
                "request": request,
                "operation": operation,
                "body": body,
                "authority": authored,
                "at_us": self.timeline.now_us,
            },
        )

    def state(self) -> dict[str, Any]:
        return self.timeline.observe("github", "state").value

    def completed(self, result: object) -> StepCompleted:
        self.assertIsInstance(result, StepCompleted)
        return cast(StepCompleted, result)

    def test_unknown_commands_observations_faults_and_payloads_fail_loudly(self) -> None:
        with self.assertRaises(ValueError) as unknown_command:
            self.timeline.command("github", "invented", {})
        self.assertEqual(unknown_command.exception.args, ("unknown GitHub simulation command: invented",))

        with self.assertRaises(ValueError) as unknown_observation:
            self.timeline.observe("github", "invented")
        self.assertEqual(unknown_observation.exception.args, ("unknown GitHub simulation observation: invented",))

        with self.assertRaises(ValueError) as unknown_fault:
            github_fault(self.timeline, "invented", {"outcome": "stale"})
        self.assertEqual(unknown_fault.exception.args, ("unknown GitHub simulation fault: invented",))

        with self.assertRaises(ValueError) as malformed_authority:
            self.timeline.command(
                "github",
                "authority.set",
                {"epoch": 1, "head": HEAD_A, "base": BASE_A},
            )
        self.assertEqual(
            malformed_authority.exception.args,
            ("authority.set payload must contain exactly: base, epoch, head, policy",),
        )

        self.set_authority(authority(1, HEAD_A, BASE_A, POLICY_A))
        self.schedule_read("read-malformed-fault")
        github_fault(self.timeline, "read.response", {"outcome": "invented"})
        with self.assertRaises(ValueError) as malformed_fault:
            self.timeline.step()
        self.assertEqual(
            malformed_fault.exception.args,
            ("read.response fault outcome must be 'stale' or 'rate_limited'",),
        )

    def test_stale_read_fault_requires_prior_authority_version(self) -> None:
        self.set_authority(authority(1, HEAD_A, BASE_A, POLICY_A))
        github_fault(self.timeline, "read.response", {"outcome": "stale"})
        self.schedule_read("read-without-prior")

        with self.assertRaises(GitHubSimulationContractError) as missing_prior:
            self.timeline.step()

        self.assertEqual(
            missing_prior.exception.args,
            (
                (
                    "stale read.response requires prior and current authority versions; "
                    "set two authority versions before stepping"
                ),
            ),
        )

    def test_stale_and_rate_limited_reads_do_not_authorize_an_old_effect(self) -> None:
        old = authority(1, HEAD_A, BASE_A, POLICY_A)
        current = authority(2, HEAD_B, BASE_B, POLICY_B)
        self.set_authority(old)
        self.set_authority(current)

        github_fault(self.timeline, "read.response", {"outcome": "stale"})
        self.schedule_read("read-stale")
        stale = self.completed(self.timeline.step())

        github_fault(self.timeline, "read.response", {"outcome": "rate_limited"})
        self.schedule_read("read-limited")
        limited = self.completed(self.timeline.step())

        self.schedule_publication("publish-old", "ready:old", "Old readiness", old)
        moved = self.completed(self.timeline.step())
        state = self.state()

        self.assertEqual(
            stale.value,
            {
                "kind": "authority_read",
                "request": "read-stale",
                "status": "returned",
                "head": HEAD_A,
                "base": BASE_A,
            },
        )
        self.assertEqual(
            limited.value,
            {
                "kind": "authority_read",
                "request": "read-limited",
                "status": "boundary_failure",
                "error": "GitHubBoundaryError",
            },
        )
        self.assertEqual(
            moved.value,
            {
                "kind": "publication",
                "request": "publish-old",
                "operation": "ready:old",
                "status": "authority_moved",
            },
        )
        self.assertEqual(
            state["reads"],
            [
                {
                    "request": "read-stale",
                    "provider_version": 2,
                    "returned_version": 1,
                    "status": 200,
                },
                {
                    "request": "read-limited",
                    "provider_version": 2,
                    "returned_version": None,
                    "status": 429,
                },
            ],
        )
        self.assertEqual(state["effects"], [])
        self.assertFalse(any(call["kind"] == "post" for call in state["calls"]))
        self.assertEqual(GitHubChecker().check(state), ("stale_authority_read:read-stale",))

    def test_visible_identity_collisions_cover_payload_and_full_authority(self) -> None:
        initial = authority(1, HEAD_A, BASE_A, POLICY_A)
        self.set_authority(initial)
        self.schedule_publication("publish-one", "ready:stable", "Ready", initial)
        created = self.completed(self.timeline.step())

        self.schedule_publication("publish-payload", "ready:stable", "Different", initial)
        payload_collision = self.completed(self.timeline.step())

        moved = authority(2, HEAD_A, BASE_B, POLICY_B)
        self.set_authority(moved)
        self.schedule_publication("publish-authority", "ready:stable", "Ready", moved)
        authority_collision = self.completed(self.timeline.step())
        state = self.state()

        self.assertEqual(created.value["status"], "created")
        self.assertEqual(
            payload_collision.value,
            {
                "kind": "publication",
                "request": "publish-payload",
                "operation": "ready:stable",
                "status": "identity_collision",
            },
        )
        self.assertEqual(
            authority_collision.value,
            {
                "kind": "publication",
                "request": "publish-authority",
                "operation": "ready:stable",
                "status": "identity_collision",
            },
        )
        self.assertEqual(len(state["effects"]), 1)
        self.assertEqual(state["collisions"], ["ready:stable", "ready:stable"])
        self.assertEqual(GitHubChecker().check(state), ())

        conflicting_payload = deepcopy(state)
        conflicting_payload["effects"].append(
            {**conflicting_payload["effects"][0], "body": "different retained payload"}
        )
        self.assertEqual(
            GitHubChecker().check(conflicting_payload),
            ("effect_identity_collision:ready:stable",),
        )

        conflicting_authority = deepcopy(state)
        conflicting_authority["effects"].append(
            {
                **conflicting_authority["effects"][0],
                "authority": moved,
                "provider_authority": moved,
                "provider_version": 2,
            }
        )
        self.assertEqual(
            GitHubChecker().check(conflicting_authority),
            ("effect_identity_collision:ready:stable",),
        )

    def test_generated_hidden_acceptance_failure_crashes_recovers_and_replays_exactly(self) -> None:
        discovery = None
        for seed in range(16):
            module = GitHubSimulation()
            timeline = Timeline.open((module,), DEFAULT_BUDGET, seed=seed)
            current = authority(1, HEAD_A, BASE_A, POLICY_A)
            timeline.command("github", "authority.set", current)
            timeline.command(
                "github",
                "publication.request",
                {
                    "request": "publish-hidden",
                    "operation": "ready:hidden",
                    "body": "Ready",
                    "authority": current,
                    "at_us": 0,
                },
            )
            github_fault(
                timeline,
                "publication.acceptance",
                {"visibility": "generated", "response": "lost"},
            )

            offered = timeline.start()
            executed = timeline.execute()
            executed_state = cast(dict[str, Any], module.state())
            timeline.crash("after_hidden_acceptance")
            timeline = timeline.restart()
            recovered = timeline.step()
            state = timeline.observe("github", "state").value
            checker_findings = GitHubChecker().check(state)
            if any(effect["accepted_visible"] is False for effect in executed_state["effects"]):
                discovery = (
                    seed,
                    module,
                    timeline,
                    offered,
                    executed,
                    executed_state,
                    recovered,
                    state,
                    checker_findings,
                )
                break

        if discovery is None:
            self.fail("bounded seed campaign did not generate a hidden accepted effect")
        seed, module, timeline, offered, executed, executed_state, recovered, state, checker_findings = discovery
        self.assertIsInstance(offered, LeafOffered)
        self.assertIsInstance(executed, LeafExecuted)
        self.assertIsNone(executed.error)
        self.assertEqual(len(executed_state["effects"]), 1)
        self.assertEqual([effect["accepted_visible"] for effect in executed_state["effects"]], [False])
        self.assertEqual([effect["visible"] for effect in executed_state["effects"]], [True])
        self.assertEqual(
            [call["kind"] for call in executed_state["calls"]],
            ["pages", "fence", "post", "pages"],
        )
        recovered = self.completed(recovered)
        self.assertEqual(recovered.value["status"], "existing")
        self.assertEqual(checker_findings, ())
        self.assertEqual([effect["operation"] for effect in state["effects"]], ["ready:hidden"])
        self.assertEqual(
            [call["kind"] for call in state["calls"]],
            ["pages", "fence", "post", "pages", "pages"],
        )

        artifact = timeline.artifact("github-hidden-acceptance")
        encoded = artifact.encode()
        decoded = Artifact.decode(encoded)
        replayed_modules: list[GitHubSimulation] = []

        def build_modules() -> tuple[GitHubSimulation]:
            replayed = GitHubSimulation()
            replayed_modules.append(replayed)
            return (replayed,)

        report = replay(decoded, build_modules)

        self.assertTrue(report.exact)
        self.assertEqual(report.operations, len(artifact.operations))
        self.assertEqual(report.journal_digest, artifact.journal_digest)
        self.assertEqual(replayed_modules[-1].state(), module.state())
        self.assertEqual(GitHubChecker().check(replayed_modules[-1].state()), checker_findings)
        self.assertEqual(artifact.origin["seed"], seed)
        self.assertEqual(artifact.origin["draws"], {"github:effect_visibility": 1})
        self.assertNotIn("credential", encoded.decode())
        self.assertNotIn("installation_token", encoded.decode())
        self.assertNotIn("private_key", encoded.decode())


if __name__ == "__main__":
    unittest.main()
