"""Execute the retained Experiment 10 host failure and exact replay proof."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from host_simulation import DEFAULT_BUDGET, HostArtifactChecker, HostSimulation
from runtime import Artifact, LeafExecuted, LeafOffered, StepCompleted, Timeline, replay

PR7 = "github:44:31:pr:7"
PR8 = "github:44:31:pr:8"
ROUTE = "installation:44:repository:31"


class Evidence(TypedDict):
    artifact_bytes: int
    authority_calls: int
    blocked: dict[str, int]
    cleanup_attempts: list[dict[str, str]]
    crash_phases: list[str]
    fair_cohorts: int
    final_generation: int
    journal_digest: str
    journal_entries: int
    lookups: dict[str, int]
    operations: int
    process_error_absent: bool
    progressed: dict[str, int]
    replay_exact: bool
    route: dict[str, int | str]
    scenario: str
    service_order: list[str]


def _cut(timeline: Timeline) -> dict[str, Any]:
    result = timeline.step()
    if not isinstance(result, StepCompleted):
        raise TypeError(f"expected one completed host cut, observed {result!r}")
    return result.value


def _turn(timeline: Timeline, *, instance_open: bool) -> None:
    _cut(timeline)
    if not instance_open:
        _cut(timeline)
    _cut(timeline)
    _cut(timeline)
    _cut(timeline)


def run() -> Evidence:
    host = HostSimulation()
    timeline = Timeline.open((host,), DEFAULT_BUDGET, seed=10)
    timeline.command("host", "register_route", {"route": ROUTE})
    timeline.command("host", "register_instance", {"subject": PR7, "route": ROUTE})
    timeline.command("host", "register_instance", {"subject": PR8, "route": ROUTE})
    timeline.command("host", "wake", {"subject": PR7, "reason": "timer", "at_us": 0})
    timeline.command("host", "wake", {"subject": PR8, "reason": "timer", "at_us": 0})
    host.arm_fault(
        timeline,
        "readiness.progress.after_commit",
        payload={"subject": PR7, "response_lost": True},
    )

    _cut(timeline)
    _cut(timeline)
    offered = timeline.start()
    if not isinstance(offered, LeafOffered):
        raise TypeError(f"expected readiness leaf, observed {offered!r}")
    executed = timeline.execute()
    if not isinstance(executed, LeafExecuted) or executed.error is None:
        raise TypeError(f"expected lost readiness response, observed {executed!r}")
    timeline.crash("after_readiness_commit")
    timeline = timeline.restart()

    _cut(timeline)
    recovered = _cut(timeline)
    if recovered["result"]["source"] != "lookup":
        raise AssertionError(f"expected lookup-first recovery, observed {recovered!r}")
    _cut(timeline)
    _cut(timeline)
    _turn(timeline, instance_open=False)

    timeline.command("host", "revoke_route", {"route": ROUTE})
    _turn(timeline, instance_open=True)
    state: Any = timeline.observe("host", "state").value
    artifact = timeline.artifact("host-response-lost-route-revoked")
    encoded = artifact.encode()
    decoded = Artifact.decode(encoded)
    replayed = replay(decoded, lambda: (HostSimulation(),))
    checked = HostArtifactChecker.check(decoded)
    crash_phases = [operation["result"]["phase"] for operation in artifact.operations if operation["kind"] == "crash"]
    if artifact.generation is None:
        raise AssertionError("live evidence scenario ended without a generation")

    evidence: Evidence = {
        "artifact_bytes": len(encoded),
        "authority_calls": checked["authority_calls"],
        "blocked": {subject: state["readiness"][subject]["blocked"] for subject in (PR7, PR8)},
        "cleanup_attempts": state["cleanup"]["attempts"],
        "crash_phases": crash_phases,
        "fair_cohorts": checked["fair_cohorts"],
        "final_generation": artifact.generation,
        "journal_digest": artifact.journal_digest,
        "journal_entries": len(artifact.journal),
        "lookups": {subject: state["readiness"][subject]["lookups"] for subject in (PR7, PR8)},
        "operations": len(artifact.operations),
        "process_error_absent": "ReadinessResponseLost" not in encoded.decode(),
        "progressed": {subject: state["readiness"][subject]["progressed"] for subject in (PR7, PR8)},
        "replay_exact": replayed.exact,
        "route": state["routes"][ROUTE],
        "scenario": artifact.scenario_id,
        "service_order": state["service_order"],
    }
    return evidence


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
