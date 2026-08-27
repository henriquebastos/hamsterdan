from __future__ import annotations

import unittest
from typing import Any

from evidence import run as run_evidence
from host_simulation import (
    DEFAULT_BUDGET,
    HostArtifactChecker,
    HostCommandError,
    HostFaultError,
    HostInputError,
    HostObservationError,
    HostSimulation,
)
from runtime import Artifact, LeafExecuted, LeafOffered, StepCompleted, Timeline, Waiting, replay

PR7 = "github:44:31:pr:7"
PR8 = "github:44:31:pr:8"
ROUTE = "installation:44:repository:31"


def open_host() -> tuple[HostSimulation, Timeline]:
    host = HostSimulation()
    return host, Timeline.open((host,), DEFAULT_BUDGET, seed=10)


def register(timeline: Timeline, subject: str, route: str = ROUTE) -> None:
    state = timeline.observe("host", "state").value
    if route not in state["routes"]:
        timeline.command("host", "register_route", {"route": route})
    timeline.command("host", "register_instance", {"subject": subject, "route": route})


def cut(timeline: Timeline) -> dict[str, Any]:
    result = timeline.step()
    if not isinstance(result, StepCompleted):
        raise TypeError(f"expected one completed host cut, observed {result!r}")
    return result.value


def progress_one_turn(timeline: Timeline, *, instance_open: bool) -> tuple[dict[str, Any], ...]:
    cuts = [cut(timeline)]
    if not instance_open:
        cuts.append(cut(timeline))
    cuts.extend((cut(timeline), cut(timeline), cut(timeline)))
    return tuple(cuts)


class StrictHostSurface(unittest.TestCase):
    """The host simulation rejects vocabulary and values it does not declare."""

    def test_unknown_commands_observations_faults_and_subjects_fail_loudly(self) -> None:
        host, timeline = open_host()

        with self.assertRaises(HostCommandError) as command:
            timeline.command("host", "invent", {})
        with self.assertRaises(HostObservationError) as observation:
            timeline.observe("host", "invent")
        with self.assertRaises(HostFaultError) as fault:
            host.arm_fault(timeline, "invent", payload={})
        with self.assertRaises(HostInputError) as subject:
            timeline.command("host", "wake", {"subject": "unknown", "reason": "timer", "at_us": 0})

        self.assertEqual(command.exception.args, ("unknown host command 'invent'",))
        self.assertEqual(observation.exception.args, ("unknown host observation 'invent'",))
        self.assertEqual(fault.exception.args, ("unknown host fault point 'invent'",))
        self.assertEqual(subject.exception.args, ("unknown host subject 'unknown'",))

    def test_command_and_fault_payloads_are_exact(self) -> None:
        host, timeline = open_host()
        register(timeline, PR7)

        with self.assertRaises(HostInputError) as command:
            timeline.command(
                "host",
                "wake",
                {"subject": PR7, "reason": "timer", "at_us": 0, "extra": True},
            )
        with self.assertRaises(HostInputError) as fault:
            host.arm_fault(
                timeline,
                "readiness.progress.unavailable",
                payload={"subject": PR7, "extra": True},
            )

        self.assertEqual(
            command.exception.args,
            ("wake payload must contain exactly: at_us, reason, subject",),
        )
        self.assertEqual(
            fault.exception.args,
            ("readiness.progress.unavailable payload must contain exactly: subject",),
        )


class FairHostScheduling(unittest.TestCase):
    """One unavailable PR returns at the tail before another due PR is selected."""

    def test_failure_isolated_progress_is_bounded_and_fairness_is_independently_checked(self) -> None:
        host, timeline = open_host()
        register(timeline, PR7)
        register(timeline, PR8)
        timeline.command("host", "wake", {"subject": PR7, "reason": "timer", "at_us": 0})
        timeline.command("host", "wake", {"subject": PR8, "reason": "webhook", "at_us": 0})
        host.arm_fault(
            timeline,
            "readiness.progress.unavailable",
            payload={"subject": PR7},
        )

        first = progress_one_turn(timeline, instance_open=False)
        second = progress_one_turn(timeline, instance_open=False)
        third = progress_one_turn(timeline, instance_open=True)
        state = timeline.observe("host", "state").value
        artifact = timeline.artifact("host-fair-failure")
        checked = HostArtifactChecker.check(artifact)

        self.assertEqual(
            [item["kind"] for item in first],
            [
                "subject_selected",
                "instance_opened",
                "readiness_step_returned",
                "posture_recorded",
                "subject_requeued",
            ],
        )
        self.assertEqual(first[2]["result"]["disposition"], "unavailable")
        self.assertEqual(second[0]["subject"], PR8)
        self.assertEqual(third[0]["subject"], PR7)
        self.assertEqual(state["service_order"], [PR7, PR8, PR7])
        self.assertEqual(state["readiness"][PR7]["progressed"], 1)
        self.assertEqual(state["readiness"][PR8]["progressed"], 1)
        self.assertEqual(checked["fair_cohorts"], 1)
        self.assertEqual(checked["authority_calls"], 3)


class HostRecoveryAndAuthority(unittest.TestCase):
    """Host recovery reuses readiness authority and observes route revocation freshly."""

    def test_lost_readiness_response_without_crash_records_posture_requeues_and_looks_up_once(self) -> None:
        host, timeline = open_host()
        register(timeline, PR7)
        timeline.command("host", "wake", {"subject": PR7, "reason": "timer", "at_us": 0})
        host.arm_fault(
            timeline,
            "readiness.progress.after_commit",
            payload={"subject": PR7, "response_lost": True},
        )

        selected = cut(timeline)
        opened = cut(timeline)
        ambiguous = cut(timeline)
        posture = cut(timeline)
        requeued = cut(timeline)
        retry_selected = cut(timeline)
        recovered = cut(timeline)
        recovered_posture = cut(timeline)
        released = cut(timeline)
        state = timeline.observe("host", "state").value
        artifact = timeline.artifact("host-response-lost-without-crash")
        checked = HostArtifactChecker.check(artifact)
        waiting = timeline.step()

        self.assertEqual(
            [
                selected["kind"],
                opened["kind"],
                ambiguous["kind"],
                posture["kind"],
                requeued["kind"],
                retry_selected["kind"],
                recovered["kind"],
                recovered_posture["kind"],
                released["kind"],
            ],
            [
                "subject_selected",
                "instance_opened",
                "readiness_step_returned",
                "posture_recorded",
                "subject_requeued",
                "subject_selected",
                "readiness_step_returned",
                "posture_recorded",
                "subject_requeued",
            ],
        )
        self.assertEqual(ambiguous["result"]["posture"], "ambiguous")
        self.assertEqual(requeued["disposition"], "requeued")
        self.assertEqual(retry_selected["identity"], selected["identity"])
        self.assertEqual(recovered["result"]["source"], "lookup")
        self.assertEqual(released["disposition"], "released")
        self.assertIsNone(state["selected"])
        self.assertIsNone(state["subjects"][PR7]["due_at_us"])
        self.assertEqual(state["service_order"], [PR7, PR7])
        self.assertEqual(state["readiness"][PR7]["operations"], 1)
        self.assertEqual(state["readiness"][PR7]["progressed"], 1)
        self.assertEqual(state["readiness"][PR7]["lookups"], 1)
        self.assertEqual(checked["authority_calls"], 2)
        if not isinstance(waiting, Waiting):
            self.fail(f"completed host should be waiting, observed {waiting!r}")
        self.assertIsNone(waiting.next_at_us)

    def test_lost_readiness_response_crashes_reconstructs_lookup_first_and_replays_exactly(self) -> None:
        host, timeline = open_host()
        register(timeline, PR7)
        register(timeline, PR8)
        timeline.command("host", "wake", {"subject": PR7, "reason": "timer", "at_us": 0})
        timeline.command("host", "wake", {"subject": PR8, "reason": "timer", "at_us": 0})
        host.arm_fault(
            timeline,
            "readiness.progress.after_commit",
            payload={"subject": PR7, "response_lost": True},
        )

        self.assertEqual(cut(timeline)["kind"], "subject_selected")
        self.assertEqual(cut(timeline)["kind"], "instance_opened")
        offered = timeline.start()
        self.assertIsInstance(offered, LeafOffered)
        executed = timeline.execute()
        self.assertIsInstance(executed, LeafExecuted)
        if executed.error is None:
            self.fail("readiness response-loss fault did not raise")
        self.assertEqual(executed.error.kind, "ReadinessResponseLost")
        timeline.crash("after_readiness_commit")
        timeline = timeline.restart()

        self.assertEqual(cut(timeline)["kind"], "instance_opened")
        recovered = cut(timeline)
        self.assertEqual(recovered["kind"], "readiness_step_returned")
        self.assertEqual(recovered["result"]["source"], "lookup")
        self.assertEqual(cut(timeline)["kind"], "posture_recorded")
        self.assertEqual(cut(timeline)["kind"], "subject_requeued")
        progress_one_turn(timeline, instance_open=False)

        timeline.command("host", "revoke_route", {"route": ROUTE})
        revoked = progress_one_turn(timeline, instance_open=True)
        state = timeline.observe("host", "state").value
        artifact = timeline.artifact("host-response-lost-route-revoked")
        encoded = artifact.encode()
        decoded = Artifact.decode(encoded)
        replayed = replay(decoded, lambda: (HostSimulation(),))
        checked = HostArtifactChecker.check(decoded)

        self.assertEqual(revoked[1]["result"]["posture"], "route_revoked")
        self.assertEqual(revoked[1]["result"]["route_generation"], 2)
        self.assertEqual(state["routes"][ROUTE], {"generation": 2, "status": "revoked"})
        self.assertEqual(state["readiness"][PR7]["progressed"], 1)
        self.assertEqual(state["readiness"][PR7]["blocked"], 1)
        self.assertEqual(state["readiness"][PR7]["operations"], 2)
        self.assertEqual(state["readiness"][PR7]["lookups"], 1)
        self.assertEqual(state["cleanup"]["attempts"], [{"mode": "abort", "subject": PR7}])
        self.assertTrue(replayed.exact)
        self.assertEqual(replayed.operations, len(artifact.operations))
        self.assertEqual(replayed.journal_digest, artifact.journal_digest)
        self.assertEqual(checked["authority_calls"], 4)
        self.assertNotIn("ReadinessResponseLost", encoded.decode())


class BoundedHostCleanup(unittest.TestCase):
    """Shutdown releases one readiness resource per cut and continues after failure."""

    def test_cleanup_failure_does_not_skip_the_next_loaded_instance(self) -> None:
        _host, timeline = open_host()
        register(timeline, PR7)
        register(timeline, PR8)
        timeline.command("host", "wake", {"subject": PR7, "reason": "timer", "at_us": 0})
        timeline.command("host", "wake", {"subject": PR8, "reason": "timer", "at_us": 0})
        progress_one_turn(timeline, instance_open=False)
        progress_one_turn(timeline, instance_open=False)
        timeline.command("host", "readiness_close_failure", {"subject": PR7, "enabled": True})
        timeline.command("host", "stop", {})

        first = cut(timeline)
        middle = timeline.observe("host", "state").value
        second = cut(timeline)
        final = timeline.observe("host", "state").value

        self.assertEqual((first["kind"], first["subject"], first["disposition"]), ("instance_closed", PR7, "failed"))
        self.assertEqual(middle["loaded"], [PR8])
        self.assertEqual((second["kind"], second["subject"], second["disposition"]), ("instance_closed", PR8, "closed"))
        self.assertEqual(final["loaded"], [])
        self.assertEqual(
            final["cleanup"],
            {
                "attempts": [
                    {"mode": "graceful", "subject": PR7},
                    {"mode": "graceful", "subject": PR8},
                ],
                "errors": [{"error_class": "ReadinessCloseFailed", "subject": PR7}],
            },
        )


class ExecutableEvidence(unittest.TestCase):
    """The retained host failure scenario reports exact replay evidence."""

    def test_evidence_scenario_is_exact_and_names_its_correspondence(self) -> None:
        evidence = run_evidence()

        self.assertTrue(evidence["replay_exact"])
        self.assertEqual(evidence["crash_phases"], ["executed"])
        self.assertEqual(evidence["service_order"], [PR7, PR8, PR7])
        self.assertEqual(evidence["progressed"], {PR7: 1, PR8: 1})
        self.assertEqual(evidence["blocked"], {PR7: 1, PR8: 0})
        self.assertEqual(evidence["lookups"], {PR7: 1, PR8: 0})
        self.assertEqual(evidence["route"], {"generation": 2, "status": "revoked"})
        self.assertEqual(evidence["authority_calls"], 4)
        self.assertEqual(evidence["fair_cohorts"], 1)
        self.assertEqual(evidence["cleanup_attempts"], [{"mode": "abort", "subject": PR7}])
        self.assertTrue(evidence["process_error_absent"])


if __name__ == "__main__":
    unittest.main()
