from __future__ import annotations

import gc
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from petrus.testing.dst import (
    API_COMPATIBILITY,
    ARTIFACT_VERSION,
    BudgetExhausted,
    BudgetV4,
    Disposition,
    DstError,
    FailureOperation,
    InvariantViolation,
    Observation,
    ResourceUsage,
    StaleGeneration,
)

from hamsterdan.host.service import HostService
from hamsterdan.host.testing._readiness_contract import SUBJECT, strict_digest
from hamsterdan.host.testing._readiness_provider import ReadinessProviderTruth
from hamsterdan.host.testing.readiness_world import (
    BASE,
    CHECKER_IDENTITY,
    DEFAULT_BUDGET,
    HEAD,
    PROFILE_IDENTITY,
    PROFILE_RESOURCE_LIMITS,
    READINESS_POLICY_DIGEST,
    REMINDER_DELAY,
    ReadinessChecker,
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
    assert API_COMPATIBILITY == "petrus.testing.dst/v4"
    assert ARTIFACT_VERSION == 4
    assert isinstance(DEFAULT_BUDGET, BudgetV4)
    assert DEFAULT_BUDGET.profile_resources == PROFILE_RESOURCE_LIMITS
    assert PROFILE_IDENTITY.model_dump(mode="json") == {
        "name": "hamsterdan.readiness.v5-world",
        "version": 2,
        "digest": "sha256:937b60ac87644fd2d97c5c4c529e760a254293ac49cc633c741f0226a2e92e5d",
    }
    assert CHECKER_IDENTITY.model_dump(mode="json") == {
        "name": "hamsterdan.readiness.independent-model",
        "version": 4,
        "digest": "sha256:05134192a4e6df87fada8cb73c5f67d85ebff6eb94c70f247258a2b51a434f9a",
    }


def test_profile_resources_are_detached_complete_and_survive_generation_drop(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    try:
        timeline.set_pull_request(
            head="c" * 40,
            base=BASE,
            policy=READINESS_POLICY_DIGEST,
            lifecycle="active",
            strict_base=True,
            base_current=True,
            mergeable=True,
        )
        live_samples = [entry for entry in world.world.journal if entry.kind == "resource"]
        assert live_samples
        assert all(set(entry.value["usage"]) == set(DEFAULT_BUDGET.profile_resources) for entry in live_samples)
        assert live_samples[0].value["usage"]["retained.profile.dropped_generations"] == 0

        timeline.crash("resource-accounting-generation-drop")
        dropped = world.profile.resource_usage(None)

        assert isinstance(dropped, ResourceUsage)
        assert set(dropped.values) == set(DEFAULT_BUDGET.profile_resources)
        assert dropped.values["retained.provider.authorities"] == 2
        assert dropped.values["retained.host.sqlite_rows"] > 0
        assert dropped.values["retained.profile.dropped_generations"] == 1
        assert dropped.values["pending.profile.proposals"] == 0
        [after_drop] = [
            entry
            for entry in world.world.journal
            if entry.kind == "resource" and entry.name == "crash:resource-accounting-generation-drop"
        ]
        assert after_drop.generation is None
        assert after_drop.value["usage"] == dropped.model_dump(mode="json")["values"]
    finally:
        world.close()


def test_profile_resource_exhaustion_retains_and_replays_the_exact_failed_attempt(tmp_path: Path) -> None:
    limits = dict(DEFAULT_BUDGET.profile_resources)
    limits["retained.provider.authorities"] = 1
    budget = DEFAULT_BUDGET.model_copy(update={"profile_resources": limits})
    world = ReadinessWorld(tmp_path / "live", budget=budget)
    timeline = world.timeline()
    try:
        with pytest.raises(BudgetExhausted, match="profile_resources:retained.provider.authorities"):
            timeline.set_pull_request(
                head="c" * 40,
                base=BASE,
                policy=READINESS_POLICY_DIGEST,
                lifecycle="active",
                strict_base=True,
                base_current=True,
                mergeable=True,
            )
        artifact = world.artifact("readiness-profile-resource-exhaustion-v4")
        failure = artifact.operations[-1]
        assert artifact.version == 4
        assert isinstance(failure, FailureOperation)
        assert failure.accepted_operations == 1
        assert failure.failure.kind == "budget_exhausted"
        assert failure.failure.bound == "profile_resources:retained.provider.authorities"
    finally:
        world.close()

    replayed = replay_readiness(artifact, tmp_path / "replay")
    assert replayed.outcome == "pass"
    assert replayed.disposition == Disposition.BUDGET_EXHAUSTED.value
    assert replayed.failure == failure.failure


def test_dropped_generation_resource_exhaustion_replays_the_crash_attempt(tmp_path: Path) -> None:
    limits = dict(DEFAULT_BUDGET.profile_resources)
    limits["retained.profile.dropped_generations"] = 0
    budget = DEFAULT_BUDGET.model_copy(update={"profile_resources": limits})
    world = ReadinessWorld(tmp_path / "live", budget=budget)
    timeline = world.timeline()
    try:
        with pytest.raises(BudgetExhausted, match="profile_resources:retained.profile.dropped_generations"):
            timeline.crash("dropped-generation-resource-bound")
        artifact = world.artifact("readiness-dropped-generation-resource-exhaustion-v4")
        failure = artifact.operations[-1]
        assert isinstance(failure, FailureOperation)
        assert failure.attempt.kind == "crash"
        assert failure.accepted_operations == 1
        assert failure.failure.kind == "budget_exhausted"
        assert failure.failure.bound == "profile_resources:retained.profile.dropped_generations"
    finally:
        world.close()

    replayed = replay_readiness(artifact, tmp_path / "replay")
    assert replayed.outcome == "pass"
    assert replayed.disposition == Disposition.BUDGET_EXHAUSTED.value
    assert replayed.failure == failure.failure


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
    assert final.value["actual"]["readiness_published"] is True
    assert final.value["provider"]["accepted_by_kind"]["readiness"] == 1
    assert final.value["provider"]["lookup_recoveries"] >= 1
    assert final.value["custody"][delivery] == "terminal"

    artifact = world.artifact("hamsterdan-readiness-ambiguity-restart-v1")
    operations = len(artifact.operations)
    journal_entries = len(world.world.journal)
    retained = json.dumps(artifact.model_dump(mode="json"), sort_keys=True)
    assert "readiness-world-private-key" not in retained
    assert "readiness-world-webhook-secret" not in retained
    assert final.value["bounds"]["limits"] == PROFILE_RESOURCE_LIMITS
    assert all(value <= PROFILE_RESOURCE_LIMITS[name] for name, value in final.value["bounds"]["usage"].items())
    world.close()

    replayed = replay_readiness(artifact, tmp_path / "replay")
    assert replayed.outcome == "pass"
    assert replayed.disposition == Disposition.CONVERGED.value
    assert replayed.operations == operations
    assert replayed.journal_entries == journal_entries


def test_real_host_recovers_one_ambiguous_reminder_after_timer_maturity_and_crash(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path / "live")
    timeline = world.timeline()
    clean_green(timeline, response_lost=False)
    while timeline.pending():
        timeline.step()

    timer = "timer:github:44:31:pr:7:i1:s0"
    armed = timeline.observe().value
    assert armed["facts"]["timers"] == [{"identity": timer, "status": "scheduled", "blocks_readiness": False}]
    assert armed["timer_custody"] == {
        "operations": [
            {
                "identity": "timer-command:github:44:31:pr:7:g1",
                "generation": 1,
                "applied_at": 0,
                "acknowledged": True,
            }
        ],
        "timers": [
            {
                "identity": timer,
                "incarnation": 1,
                "sequence": 0,
                "head": HEAD,
                "due_at": REMINDER_DELAY,
                "state": "armed",
                "matured_at": None,
                "maturity_delivered": False,
            }
        ],
    }

    timeline.lose_effect_response("reminder")
    timeline.advance_time(REMINDER_DELAY)
    accepted = timeline.run_until(
        "reminder effect accepted",
        lambda state: state["provider"]["response_losses"] == ["reminder"],
    )
    assert accepted.value["provider"]["accepted_by_kind"]["reminder"] == 1

    timeline.crash("after_reminder_acceptance_before_projection")
    timeline = world.restart()
    final = timeline.converge()
    next_timer = "timer:github:44:31:pr:7:i1:s1"
    assert final.value["facts"]["timers"] == [
        {"identity": timer, "status": "acknowledged", "blocks_readiness": False},
        {"identity": next_timer, "status": "scheduled", "blocks_readiness": False},
    ]
    assert final.value["expected"]["ready"] is True
    assert final.value["actual"]["readiness_published"] is True
    assert final.value["provider"]["accepted_by_kind"]["reminder"] == 1
    assert final.value["provider"]["lookup_recoveries"] >= 1
    assert [item["state"] for item in final.value["timer_custody"]["timers"]] == ["matured", "armed"]

    artifact = world.artifact("hamsterdan-readiness-reminder-ambiguity-restart-v1")
    operations = len(artifact.operations)
    world.close()

    replayed = replay_readiness(artifact, tmp_path / "replay")
    assert replayed.outcome == "pass"
    assert replayed.disposition == Disposition.CONVERGED.value
    assert replayed.operations == operations


def test_real_v5_recovers_one_ambiguous_authorized_git_publication_after_crash(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path / "live")
    timeline = world.timeline()
    clean_green(timeline, response_lost=False)
    while timeline.pending():
        timeline.step()

    comment = 501
    timeline.set_human_comment(comment=comment, fixture="change")
    delivery = timeline.emit_webhook("issue_comment", action="created")
    conversation_operation = f"conversation:owner/repo:pr:7:delivery:{delivery}"
    timeline.set_agent_terminal(
        operation=conversation_operation,
        fixture="conversation_change",
        status="changed",
    )
    publication_operation = f"push:comment:{comment}:{HEAD}:i1"
    coding_operation = f"mutation:owner/repo:pr:7:{publication_operation}"
    timeline.set_agent_terminal(operation=coding_operation, fixture="coding", status="changed")
    timeline.fault_git_publication(publication_operation, "ref_cas")
    timeline.deliver_webhook(delivery)
    accepted = timeline.run_until(
        "Git ref update accepted without a response",
        lambda state: len(state["provider"].get("git_publications", [])) == 1,
    )
    publication = accepted.value["provider"]["git_publications"][0]
    new_head = publication["result_head"]
    assert publication["operation"] == publication_operation
    assert publication["response_lost"] is True

    timeline.crash("after_git_ref_acceptance_before_recovery")
    timeline = world.restart()
    while timeline.pending():
        timeline.step()
    timeline.set_ci(head=new_head, required_checks=("build",), checks={"build": "success"})
    timeline.set_review(head=new_head, status="clear")
    head_delivery = timeline.emit_webhook("pull_request", action="synchronize")
    timeline.deliver_webhook(head_delivery)
    while timeline.pending():
        timeline.step()

    recovery_comment = 502
    timeline.set_human_comment(
        comment=recovery_comment,
        fixture=f"recover:{publication_operation}",
    )
    recovery_delivery = timeline.emit_webhook("issue_comment", action="created")
    timeline.set_agent_terminal(
        operation=f"conversation:owner/repo:pr:7:delivery:{recovery_delivery}",
        fixture="conversation_recover",
        status="clear",
    )
    timeline.deliver_webhook(recovery_delivery)
    final = timeline.converge()

    assert final.value["expected"]["violations"] == []
    assert final.value["expected"]["ready"] is True
    assert final.value["actual"]["readiness_published"] is True
    recovery_identity = f"github-delivery:{recovery_delivery}"
    assert final.value["provider"]["git_publications"] == [
        publication | {"recovered": True, "recovery_identity": recovery_identity}
    ]
    assert final.value["provider"]["git_reconciliations"] >= 3
    assert [item["variant"] for item in final.value["git_custody"]["terminals"]] == ["FaultM", "Pushed"]

    assert final.value["provider"]["git_publications"][0]["recovery_identity"] == recovery_identity
    assert final.value["provider"]["admitted_recoveries"] == [
        {"operation": publication_operation, "identity": recovery_identity}
    ]

    corrupted = deepcopy(final.value)
    corrupted["provider"]["admitted_recoveries"] = []
    sensitivity = ReadinessChecker().check(
        Observation(
            name="readiness.state",
            value=corrupted,
            instant=world.world.instant,
            generation=world.world.generation,
            sequence=0,
        )
    )
    assert sensitivity.passed is False
    assert sensitivity.detail["git_custody_parity"] is False
    assert sensitivity.detail["git_custody_mismatches"][0]["field"] == "recovery_authorization"

    corrupted = deepcopy(final.value)
    corrupted["git_custody"]["terminals"][-1]["result_head"] = "d" * 40
    sensitivity = ReadinessChecker().check(
        Observation(
            name="readiness.state",
            value=corrupted,
            instant=world.world.instant,
            generation=world.world.generation,
            sequence=0,
        )
    )
    assert sensitivity.passed is False
    assert any(mismatch["field"] == "terminal_result_head" for mismatch in sensitivity.detail["git_custody_mismatches"])

    artifact = world.artifact("hamsterdan-v5-git-ambiguity-restart-v1")
    operations = len(artifact.operations)
    world.close()

    replayed = replay_readiness(artifact, tmp_path / "replay")
    assert replayed.outcome == "pass"
    assert replayed.disposition == Disposition.CONVERGED.value
    assert replayed.operations == operations


def test_checker_rejects_timer_custody_that_differs_from_independent_schedule(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    clean_green(timeline, response_lost=False)
    try:
        while timeline.pending():
            timeline.step()
        corrupted = deepcopy(timeline.observe().value)
        corrupted["timer_custody"]["timers"][0]["head"] = "c" * 40

        result = ReadinessChecker().check(
            Observation(
                name="readiness.state",
                value=corrupted,
                instant=world.world.instant,
                generation=world.world.generation,
                sequence=0,
            )
        )

        assert result.passed is False
        assert result.detail["timer_custody_parity"] is False
        assert result.detail["timer_custody_mismatches"] == [
            {
                "identity": "timer:github:44:31:pr:7:i1:s0",
                "field": "head",
                "expected": HEAD,
                "observed": "c" * 40,
            }
        ]
    finally:
        world.close()


def test_checker_rejects_timer_maturity_before_the_independent_deadline(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    clean_green(timeline, response_lost=False)
    try:
        while timeline.pending():
            timeline.step()
        timeline.advance_time(REMINDER_DELAY)
        settled = timeline.converge()
        corrupted = deepcopy(settled.value)
        corrupted["timer_custody"]["timers"][0]["matured_at"] = REMINDER_DELAY - 1

        result = ReadinessChecker().check(
            Observation(
                name="readiness.state",
                value=corrupted,
                instant=world.world.instant,
                generation=world.world.generation,
                sequence=0,
            )
        )

        assert result.passed is False
        assert result.detail["timer_custody_parity"] is False
        assert result.detail["timer_custody_mismatches"] == [
            {
                "identity": "timer:github:44:31:pr:7:i1:s0",
                "field": "matured_at",
                "expected": REMINDER_DELAY,
                "observed": REMINDER_DELAY - 1,
            }
        ]
    finally:
        world.close()


def test_provider_head_movement_allows_projection_lag_without_retroactive_effect_failure(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    clean_green(timeline, response_lost=False)
    try:
        while timeline.pending():
            timeline.step()
        before = timeline.observe().value
        assert before["expected"]["ready"] is True
        assert before["actual"]["readiness_published"] is True

        timeline.set_pull_request(
            head="c" * 40,
            base=BASE,
            policy=READINESS_POLICY_DIGEST,
            lifecycle="active",
            strict_base=True,
            base_current=True,
            mergeable=True,
        )

        moved = timeline.observe().value
        assert moved["expected"]["blockers"] == ["current_authority_admission"]
        assert moved["expected"]["violations"] == []
        assert moved["actual"]["readiness_published"] is False
        assert moved["host"]["snapshot"]["head"] == HEAD
    finally:
        world.close()


def test_provider_effect_retains_authored_full_authority_when_same_head_authority_moves() -> None:
    truth = ReadinessProviderTruth()
    authored = truth.authority
    operation = f"ready:{HEAD}:i1"
    truth.bind_effect_authority("readiness", operation, authored)
    accepted_under = replace(authored, base="d" * 40, policy="policy:changed")
    truth.set_authority(accepted_under)

    response = truth.request(
        "POST",
        "/repos/owner/repo/issues/7/comments",
        {"body": (f"readiness\n\n<!-- hamsterdan:readiness operation={operation} head={HEAD} -->")},
    )

    assert response.status == 201
    [effect] = truth.observation()["effects"]
    assert effect["authority"] == authored.dump()
    assert effect["provider_authority_at_acceptance"] == accepted_under.dump()


def test_delayed_old_delivery_admits_current_provider_authority_at_custody_execution(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
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
    delayed = timeline.emit_webhook("pull_request", action="synchronize")
    try:
        timeline.set_pull_request(
            head="c" * 40,
            base=BASE,
            policy=READINESS_POLICY_DIGEST,
            lifecycle="active",
            strict_base=True,
            base_current=True,
            mergeable=True,
        )
        timeline.set_ci(head="c" * 40, required_checks=("build",), checks={"build": "success"})
        timeline.set_review(head="c" * 40, status="clear")
        timeline.deliver_webhook(delayed)
        while timeline.pending():
            timeline.step()

        state = timeline.observe().value
        assert state["facts"]["authority"]["admitted"]["head"] == "c" * 40
        assert state["host"]["snapshot"]["head"] == "c" * 40
        assert state["expected"]["ready"] is True
        assert state["expected"]["violations"] == []
    finally:
        world.close()


def test_checker_rejects_stale_snapshot_even_when_old_and_current_heads_are_ready(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    clean_green(timeline, response_lost=False)
    try:
        while timeline.pending():
            timeline.step()
        timeline.set_pull_request(
            head="c" * 40,
            base=BASE,
            policy=READINESS_POLICY_DIGEST,
            lifecycle="active",
            strict_base=True,
            base_current=True,
            mergeable=True,
        )
        timeline.set_ci(head="c" * 40, required_checks=("build",), checks={"build": "success"})
        timeline.set_review(head="c" * 40, status="clear")
        delivery = timeline.emit_webhook("pull_request", action="synchronize")
        timeline.deliver_webhook(delivery)
        while timeline.pending():
            timeline.step()

        stale = deepcopy(timeline.observe().value)
        stale["host"]["snapshot"]["head"] = HEAD
        result = ReadinessChecker().check(
            Observation(
                name="readiness.state",
                value=stale,
                instant=world.world.instant,
                generation=world.world.generation,
                sequence=0,
            )
        )

        assert result.passed is False
        assert result.detail["ready_parity"] is True
        assert result.detail["snapshot_parity"] is False
    finally:
        world.close()


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


def test_identical_webhook_emission_remains_idempotent_after_logical_time_moves(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    try:
        delivery = timeline.emit_webhook("issue_comment", action="created")
        timeline.advance_time(7)
        fixture = "issue_comment:created"

        repeated = timeline.command(
            "readiness.github.webhook.emit",
            {
                "subject": SUBJECT,
                "delivery": delivery,
                "event": "issue_comment",
                "fixture": fixture,
                "digest": strict_digest({"event": "issue_comment", "fixture": fixture}),
            },
        )

        assert repeated.disposition == "idempotent"
        assert len(world.profile.truth.emitted) == 1
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

        assert world.profile.truth.admitted == []
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
