# Copyright (c) 2026 Henrique Bastos

"""Deterministic owner-local and root evidence for signed webhook custody."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, cast

from petrus.testing.dst import BudgetExhausted, Disposition, ExecuteOperation, Observation, encode_artifact

from hamsterdan2.github_app.simulation.webhooks import (
    EXPECTED_WEBHOOK,
    NORMALIZE_WEBHOOK_COMMAND,
    WEBHOOK_SIGNING_MATERIAL,
    build_github_webhook_world,
    replay_github_webhook,
)
from hamsterdan2.readiness.simulation.lifecycle import ReadinessState
from hamsterdan2.simulation.hamsterdan import (
    COLLIDE_WEBHOOK_COMMAND,
    DEFAULT_BUDGET,
    EXPECTED_DELIVERY,
    EXPECTED_QUARANTINED_DELIVERY,
    RECEIVE_WEBHOOK_COMMAND,
    HamsterdanChecker,
    build_hamsterdan_world,
    observe_hamsterdan,
    replay_hamsterdan,
)

import pytest


if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue


def checker_observation(value: JsonValue) -> Observation:
    return Observation(name="hamsterdan.state", value=value, instant=0, generation=1, sequence=0)


def retained_state(root: Path) -> dict[str, JsonValue]:
    world = build_hamsterdan_world(root=root)
    try:
        world.timeline().command(
            "hamsterdan.receive_webhook",
            RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
        )
        return cast("dict[str, JsonValue]", observe_hamsterdan(root).model_dump(mode="json"))
    finally:
        world.close()


class TestGitHubOwnerSimulation:
    """The provider boundary verifies and exactly replays its signed fixture."""

    def test_normalized_artifact_replays_without_raw_or_signing_material(self) -> None:
        world = build_github_webhook_world()
        try:
            result = world.timeline().command(
                "github_app.normalize_webhook",
                NORMALIZE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            world.timeline().finish(Disposition.QUIESCENT)
            artifact = world.artifact("ds2.github.normalize")
        finally:
            world.close()

        replayed = replay_github_webhook(artifact)
        encoded = encode_artifact(artifact)
        assert result.value == EXPECTED_WEBHOOK.model_dump(mode="json")
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest
        assert b"simulation-raw-only-marker" not in encoded
        assert WEBHOOK_SIGNING_MATERIAL.encode() not in encoded


class TestWebhookRootSimulation:
    """The cumulative root drives the real ASGI app and reconstructs custody."""

    def test_crash_after_custody_replays_from_a_fresh_root_as_an_exact_duplicate(self, tmp_path: Path) -> None:
        record_root = tmp_path / "record"
        world = build_hamsterdan_world(root=record_root)
        first_timeline = world.timeline()
        try:
            first = first_timeline.command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            first_timeline.crash("after_delivery_custodied")
            world.restart()
            second_timeline = world.timeline()
            reconstructed = second_timeline.command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            second_timeline.finish(Disposition.QUIESCENT)
            artifact = world.artifact("ds2.hamsterdan.after-delivery-custodied")
        finally:
            world.close()

        state = observe_hamsterdan(record_root)
        replayed = replay_hamsterdan(artifact, root=tmp_path / "replay")
        executions = [operation for operation in artifact.operations if isinstance(operation, ExecuteOperation)]
        first_value = cast("dict[str, JsonValue]", first.value)
        reconstructed_value = cast("dict[str, JsonValue]", reconstructed.value)
        assert first.disposition == "applied"
        assert first_value["disposition"] == "retained"
        assert reconstructed.disposition == "idempotent"
        assert reconstructed_value["disposition"] == "exact_duplicate"
        assert [execution.command.name for execution in executions] == [
            "hamsterdan.receive_webhook",
            "hamsterdan.receive_webhook",
        ]
        assert state.delivery.rows == 1
        assert state.delivery.retained == EXPECTED_DELIVERY
        assert state.readiness == ReadinessState(binding=None, history_records=0)
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest

    def test_changed_content_moves_the_root_observation_to_quarantine(self, tmp_path: Path) -> None:
        world = build_hamsterdan_world(root=tmp_path)
        try:
            world.timeline().command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            collision = world.timeline().command(
                "hamsterdan.receive_webhook",
                COLLIDE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            state = observe_hamsterdan(tmp_path)
        finally:
            world.close()

        collision_value = cast("dict[str, JsonValue]", collision.value)
        assert collision.disposition == "applied"
        assert collision_value["disposition"] == "quarantined"
        assert state.delivery.rows == 1
        assert state.delivery.retained == EXPECTED_QUARANTINED_DELIVERY
        assert state.delivery.retained is not None
        assert state.delivery.retained.webhook.snapshot.head.sha == "a" * 40


class TestWebhookCheckerSensitivity:
    """The independent root checker rejects delivery identity, route, and content mutations."""

    def test_changed_provider_route_identity_fails(self, tmp_path: Path) -> None:
        value = deepcopy(retained_state(tmp_path))
        delivery = cast("dict[str, JsonValue]", value["delivery"])
        retained = cast("dict[str, JsonValue]", delivery["retained"])
        retained["provider_route_id"] = "github:mutated"

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["delivery_route"] is False

    def test_changed_delivery_identity_fails(self, tmp_path: Path) -> None:
        value = deepcopy(retained_state(tmp_path))
        delivery = cast("dict[str, JsonValue]", value["delivery"])
        retained = cast("dict[str, JsonValue]", delivery["retained"])
        webhook = cast("dict[str, JsonValue]", retained["webhook"])
        provenance = cast("dict[str, JsonValue]", webhook["provenance"])
        provenance["delivery_id"] = "22222222-2222-4222-8222-222222222222"

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["delivery_identity"] is False

    def test_changed_normalized_content_fails(self, tmp_path: Path) -> None:
        value = deepcopy(retained_state(tmp_path))
        delivery = cast("dict[str, JsonValue]", value["delivery"])
        retained = cast("dict[str, JsonValue]", delivery["retained"])
        webhook = cast("dict[str, JsonValue]", retained["webhook"])
        snapshot = cast("dict[str, JsonValue]", webhook["snapshot"])
        head = cast("dict[str, JsonValue]", snapshot["head"])
        head["sha"] = "d" * 40

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["delivery_content"] is False


class TestWebhookRootResources:
    """Root custody reports and enforces finite delivery, file, and byte resources."""

    def test_delivery_resource_samples_stay_within_the_declared_budget(self, tmp_path: Path) -> None:
        world = build_hamsterdan_world(root=tmp_path)
        try:
            timeline = world.timeline()
            timeline.command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            timeline.finish(Disposition.QUIESCENT)
        finally:
            world.close()

        samples = [entry for entry in world.journal if entry.kind == "resource"]
        expected_names = set(DEFAULT_BUDGET.profile_resources)
        for sample in samples:
            value = cast("dict[str, JsonValue]", sample.value)
            usage = cast("dict[str, int]", value["usage"])
            assert set(usage) == expected_names
            assert all(usage[name] <= DEFAULT_BUDGET.profile_resources[name] for name in expected_names)
        assert any(
            cast("dict[str, int]", cast("dict[str, JsonValue]", sample.value)["usage"])["retained.host.deliveries"] == 1
            for sample in samples
        )

    def test_zero_delivery_budget_fails_when_custody_creates_the_first_row(self, tmp_path: Path) -> None:
        resources = {**DEFAULT_BUDGET.profile_resources, "retained.host.deliveries": 0}
        budget = DEFAULT_BUDGET.model_copy(update={"profile_resources": resources})
        world = build_hamsterdan_world(root=tmp_path, budget=budget)
        try:
            with pytest.raises(BudgetExhausted) as raised:
                world.timeline().command(
                    "hamsterdan.receive_webhook",
                    RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
                )
        finally:
            world.close()

        assert raised.value.bound == "profile_resources:retained.host.deliveries"
        assert raised.value.limit == 0
