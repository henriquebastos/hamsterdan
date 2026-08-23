from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from petrus.testing.dst import CheckResult, Disposition, InvariantViolation, Observation
from pydantic import JsonValue, ValidationError

from hamsterdan.host.testing.readiness_coverage import (
    CoverageRun,
    collect_readiness_coverage,
    encode_readiness_coverage,
    load_readiness_coverage,
)
from hamsterdan.host.testing.readiness_world import (
    BASE,
    HEAD,
    READINESS_POLICY_DIGEST,
    ReadinessChecker,
    ReadinessWorld,
    replay_readiness,
)


@pytest.fixture(scope="module")
def duplicate_delivery_run(tmp_path_factory: pytest.TempPathFactory) -> CoverageRun:
    root = tmp_path_factory.mktemp("readiness-coverage")
    world = ReadinessWorld(root / "live")
    timeline = world.timeline()
    timeline.set_pull_request(
        head=HEAD,
        base=BASE,
        policy=READINESS_POLICY_DIGEST,
        lifecycle="active",
        strict_base=True,
        base_current=True,
        mergeable=True,
    )
    timeline.set_ci(head=HEAD, required_checks=("build",), checks={"build": "success"})
    timeline.set_review(head=HEAD, status="clear")
    delivery = timeline.emit_webhook("pull_request", action="synchronize")
    timeline.deliver_webhook(delivery)
    while timeline.pending():
        timeline.step()
    timeline.deliver_webhook(delivery)
    timeline.converge()
    artifact = world.artifact("coverage-duplicate-delivery-v1")
    world.close()
    replayed = replay_readiness(artifact, root / "replay")
    return CoverageRun(artifact=artifact, replay=replayed)


def test_coverage_requires_adapter_checker_and_observed_outcome(
    duplicate_delivery_run: CoverageRun,
) -> None:
    report = collect_readiness_coverage((duplicate_delivery_run,))
    dimensions = {dimension.name: dimension for dimension in report.dimensions}

    duplicate = dimensions["duplicate_delivery"]
    assert duplicate.status == "covered"
    assert duplicate.evidence[0].adapters == ("webhook.redelivery",)
    assert duplicate.evidence[0].checkers == ("readiness.no_duplicate_effect",)
    assert duplicate.evidence[0].outcomes == ("webhook.duplicate",)

    timer = dimensions["timer_lifecycle"]
    assert timer.status == "uncovered"
    assert timer.evidence[0].adapters == ()
    assert timer.evidence[0].checkers == ("readiness.timer_custody",)
    assert timer.evidence[0].outcomes == ("timer.armed",)

    assert dimensions["fair_convergence"].status == "covered"
    assert dimensions["checker_activation"].status == "covered"
    assert dimensions["exact_replay"].status == "covered"
    assert dimensions["ci_rerun_repair"].status == "blocked"
    assert dimensions["agent_terminal_fault_cuts"].status == "blocked"
    assert dimensions["stale_rate_limited_reads"].status == "blocked"
    assert dimensions["history_dispatch_fault_cuts"].status == "blocked"


def test_failed_boundary_cannot_borrow_an_earlier_checker_witness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ReadinessChecker.check

    def fail_duplicate(checker: ReadinessChecker, observation: Observation) -> CheckResult:
        result = original(checker, observation)
        state = cast(dict[str, JsonValue], observation.value)
        bounds = cast(dict[str, JsonValue], state["bounds"])
        usage = cast(dict[str, JsonValue], bounds["usage"])
        if cast(int, usage["retained.provider.delivery_attempts"]) >= 2:
            return CheckResult(passed=False, detail={"forced": "duplicate boundary failure"})
        return result

    monkeypatch.setattr(ReadinessChecker, "check", fail_duplicate)
    world = ReadinessWorld(tmp_path / "live")
    timeline = world.timeline()
    timeline.set_pull_request(
        head=HEAD,
        base=BASE,
        policy=READINESS_POLICY_DIGEST,
        lifecycle="active",
        strict_base=True,
        base_current=True,
        mergeable=True,
    )
    timeline.set_ci(head=HEAD, required_checks=("build",), checks={"build": "success"})
    timeline.set_review(head=HEAD, status="clear")
    delivery = timeline.emit_webhook("pull_request", action="synchronize")
    timeline.deliver_webhook(delivery)
    while timeline.pending():
        timeline.step()
    try:
        with pytest.raises(InvariantViolation, match="independent-model"):
            timeline.deliver_webhook(delivery)
        artifact = world.artifact("coverage-failed-duplicate-boundary-v1")
    finally:
        world.close()

    report = collect_readiness_coverage((CoverageRun(artifact),))
    duplicate = next(dimension for dimension in report.dimensions if dimension.name == "duplicate_delivery")
    assert duplicate.status == "uncovered"


def test_coverage_is_deterministic_strict_json(
    duplicate_delivery_run: CoverageRun,
) -> None:
    first = duplicate_delivery_run
    second = CoverageRun(
        artifact=first.artifact.model_copy(update={"scenario_id": "coverage-duplicate-delivery-copy-v1"}),
        replay=first.replay.model_copy(update={"scenario_id": "coverage-duplicate-delivery-copy-v1"}),
    )

    forward = collect_readiness_coverage((first, second))
    reverse = collect_readiness_coverage((second, first))
    encoded = encode_readiness_coverage(forward)

    assert encoded == encode_readiness_coverage(reverse)
    assert load_readiness_coverage(encoded) == forward
    assert b"readiness-world-private-key" not in encoded
    assert b"readiness-world-webhook-secret" not in encoded


def test_coverage_rejects_unknown_contradictory_and_over_budget_evidence(
    duplicate_delivery_run: CoverageRun,
) -> None:
    report = collect_readiness_coverage((duplicate_delivery_run,))
    unknown = report.model_dump(mode="json")
    duplicate = next(item for item in unknown["dimensions"] if item["name"] == "duplicate_delivery")
    duplicate["evidence"][0]["adapters"] = ["webhook.unknown"]
    with pytest.raises(ValidationError):
        load_readiness_coverage(json.dumps(unknown).encode())

    contradictory = report.model_dump(mode="json")
    timer = next(item for item in contradictory["dimensions"] if item["name"] == "timer_lifecycle")
    timer["status"] = "covered"
    with pytest.raises(ValidationError, match="covered dimension requires complete scenario evidence"):
        load_readiness_coverage(json.dumps(contradictory).encode())

    extra = report.model_dump(mode="json")
    extra["percentage"] = 100
    with pytest.raises(ValidationError):
        load_readiness_coverage(json.dumps(extra).encode())

    runs = tuple(
        CoverageRun(
            artifact=duplicate_delivery_run.artifact.model_copy(update={"scenario_id": f"coverage-copy-{index}"}),
            replay=duplicate_delivery_run.replay.model_copy(update={"scenario_id": f"coverage-copy-{index}"}),
        )
        for index in range(17)
    )
    with pytest.raises(ValueError, match="at most 16 scenario runs"):
        collect_readiness_coverage(runs)


def test_coverage_rejects_replay_or_scenario_identity_contradictions(
    duplicate_delivery_run: CoverageRun,
) -> None:
    replay = duplicate_delivery_run.replay.model_copy(update={"disposition": Disposition.QUIESCENT.value})
    with pytest.raises(ValueError, match="replay disposition does not match"):
        collect_readiness_coverage((CoverageRun(duplicate_delivery_run.artifact, replay),))

    changed_expected = duplicate_delivery_run.artifact.expected.model_copy(
        update={"journal_digest": "sha256:" + "0" * 64}
    )
    changed = duplicate_delivery_run.artifact.model_copy(update={"expected": changed_expected})
    with pytest.raises(ValueError, match="scenario identity is contradictory"):
        collect_readiness_coverage(
            (
                duplicate_delivery_run,
                CoverageRun(changed, duplicate_delivery_run.replay),
            )
        )
