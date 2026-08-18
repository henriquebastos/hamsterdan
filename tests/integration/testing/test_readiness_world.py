from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest
from petrus.testing.dst import (
    API_COMPATIBILITY,
    ARTIFACT_VERSION,
    Disposition,
    DstError,
    FailureOperation,
    InvariantViolation,
    StaleGeneration,
)

from hamsterdan.host.service import HostService
from hamsterdan.host.testing.readiness_world import (
    BASE,
    CHECKER_IDENTITY,
    HEAD,
    PROFILE_IDENTITY,
    PROFILE_LIMITS,
    READINESS_POLICY_DIGEST,
    ReadinessWorld,
    replay_readiness,
)


def clean_green(timeline, *, response_lost: bool = True) -> str:
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
    if response_lost:
        timeline.lose_effect_response("readiness")
    timeline.deliver_webhook(delivery)
    return delivery


def test_profile_and_checker_compatibility_identities_are_stable() -> None:
    assert API_COMPATIBILITY == "petrus.testing.dst/v3"
    assert ARTIFACT_VERSION == 3
    assert PROFILE_IDENTITY.model_dump(mode="json") == {
        "name": "hamsterdan.readiness.production-world",
        "version": 1,
        "digest": "sha256:6d47f75e43b1011a8a666323b51d3e3d0ef361d876a3e5bde5ceff00ea9699dd",
    }
    assert CHECKER_IDENTITY.model_dump(mode="json") == {
        "name": "hamsterdan.readiness.independent-model",
        "version": 1,
        "digest": "sha256:75de395e559a673b41f391de6a61300486a308d186eefd451e2cbcd769250cdc",
    }


def test_world_refuses_unknown_commands_and_undeclared_provider_calls(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    try:
        with pytest.raises(ValueError, match="unknown readiness command"):
            timeline.command("readiness.unknown", {})
        with pytest.raises(ValueError, match="required_checks must be unique"):
            timeline.set_ci(head=HEAD, required_checks=("build", "build"), checks={"build": "success"})
        with pytest.raises(ValueError, match="unsupported readiness effect target"):
            timeline.fault_effect("undeclared", "before_acceptance")
        with pytest.raises(AssertionError, match="undeclared provider request"):
            world.profile.truth.request("DELETE", "/repos/owner/repo/pulls/7")
    finally:
        world.close()


def test_real_host_recovers_one_ambiguous_readiness_effect_after_crash_and_exact_replay(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path / "live")
    timeline = world.timeline()
    delivery = clean_green(timeline)

    accepted = timeline.run_until(
        "readiness effect accepted",
        lambda state: state["provider"]["response_losses"] == ["readiness"],
    )
    accepted_state = accepted.value
    assert accepted_state["custody"][delivery] == "terminal"
    assert accepted_state["provider"]["accepted_by_kind"]["readiness"] == 1
    assert accepted_state["motus"]["terminals"] >= 1
    assert accepted_state["facts"]["admitted_observations"] == [f"github-delivery:{delivery}"]

    stale = timeline
    timeline.crash("after_readiness_terminal_before_projection")
    gc.collect()
    assert world.profile.dropped_generations_alive() == 0
    with pytest.raises(StaleGeneration):
        stale.observe()
    with pytest.raises(StaleGeneration):
        stale.pending()
    with pytest.raises(StaleGeneration):
        stale.step()

    timeline = world.restart()
    with pytest.raises(StaleGeneration):
        stale.pending()
    with pytest.raises(StaleGeneration):
        stale.step()
    final = timeline.converge()
    assert final.value["expected"]["ready"] is True
    assert final.value["host"]["ready"] is True
    assert final.value["provider"]["accepted_by_kind"]["readiness"] == 1
    assert final.value["provider"]["lookup_recoveries"] >= 1
    assert final.value["custody"][delivery] == "terminal"

    artifact = world.artifact("hamsterdan-readiness-ambiguity-restart-v1")
    operations = len(artifact.operations)
    journal_entries = len(world.world.journal)
    retained = json.dumps(artifact.model_dump(mode="json"), sort_keys=True)
    assert "readiness-world-private-key" not in retained
    assert "readiness-world-webhook-secret" not in retained
    assert final.value["bounds"]["limits"] == PROFILE_LIMITS
    assert all(value <= PROFILE_LIMITS[name] for name, value in final.value["bounds"]["usage"].items())
    world.close()

    replayed = replay_readiness(artifact, tmp_path / "replay")
    assert replayed.outcome == "pass"
    assert replayed.disposition == Disposition.CONVERGED.value
    assert replayed.operations == operations
    assert replayed.journal_entries == journal_entries


def test_fair_phase_refuses_new_external_events(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    timeline.begin_fair()
    try:
        with pytest.raises(DstError, match="fair phase"):
            timeline.set_ci(head=HEAD, required_checks=("build",), checks={"build": "success"})
    finally:
        world.close()


def test_duplicate_delivery_is_one_independent_admission_and_logical_time_is_explicit(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    try:
        result = timeline.advance_time(7)
        assert result.value == {"target": 7}
        assert world.world.instant == 7

        delivery = clean_green(timeline, response_lost=False)
        while world.world.pending():
            world.world.step()
        duplicate = timeline.deliver_webhook(delivery)
        state = timeline.observe().value

        assert duplicate.disposition == "idempotent"
        assert state["provider"]["accepted_by_kind"]["readiness"] == 1
        assert state["facts"]["admitted_observations"] == [f"github-delivery:{delivery}"]
        assert state["custody"][delivery] == "terminal"
    finally:
        world.close()


def test_unexpected_retained_custody_cannot_be_normalized_as_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = HostService._record_posture
    failed = False

    def fail_once(host: HostService, instance: str, outcome: object | None) -> None:
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("simulated unexpected posture failure")
        original(host, instance, outcome)

    monkeypatch.setattr(HostService, "_record_posture", fail_once)
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    delivery = clean_green(timeline, response_lost=False)
    try:
        with pytest.raises(InvariantViolation, match="independent-model"):
            world.world.step()

        assert [event.delivery for event in world.profile.truth.admitted] == [delivery]
        assert world.profile.truth.custody_actions == [
            {
                "expected": {"delivery": delivery, "disposition": "completed"},
                "observed": {"delivery": delivery, "disposition": "retained"},
            }
        ]
        check, failure = world.world.journal[-2:]
        assert check.kind == "check"
        assert check.value["result"]["detail"]["custody_action_mismatches"] == world.profile.truth.custody_actions
        assert failure.kind == "failure"
        assert failure.value["failure"]["kind"] == "invariant_failure"
    finally:
        world.close()


def test_terminally_disposed_custody_cannot_be_normalized_as_semantic_admission(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    clean_green(timeline, response_lost=False)
    while world.world.pending():
        world.world.step()
    delivery = timeline.emit_webhook("issue_comment", action="created")
    timeline.deliver_webhook(delivery)
    try:
        with pytest.raises(InvariantViolation, match="independent-model"):
            world.world.step()

        assert world.profile.truth.custody_actions[-1] == {
            "expected": {"delivery": delivery, "disposition": "completed"},
            "observed": {"delivery": delivery, "disposition": "disposed"},
        }
        artifact = world.artifact("disposed-custody-invariant-v3")
        failure = artifact.operations[-1]
        assert isinstance(failure, FailureOperation)
        assert failure.attempt.kind == "step"
        assert failure.accepted_operations == 1
        assert failure.failure.kind == "invariant_failure"
    finally:
        world.close()

    replayed = replay_readiness(artifact, tmp_path / "replay")
    assert replayed.outcome == "pass"
    assert replayed.disposition == Disposition.INVARIANT_FAILURE.value
    assert replayed.failure is not None
    assert replayed.failure.kind == "invariant_failure"
