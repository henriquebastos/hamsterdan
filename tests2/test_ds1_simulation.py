# Copyright (c) 2026 Henrique Bastos

"""Deterministic owner-local and root evidence for the first bridged lifecycle."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, cast

from petrus.testing.dst import BudgetExhausted, Disposition, ExecuteOperation, Observation, encode_artifact

from hamsterdan2.readiness.simulation.lifecycle import (
    OPEN_READINESS_COMMAND,
    build_readiness_world,
    replay_readiness,
)
from hamsterdan2.simulation.hamsterdan import (
    DEFAULT_BUDGET,
    OPEN_PULL_REQUEST_COMMAND,
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


def opened_state(root: Path) -> dict[str, JsonValue]:
    world = build_hamsterdan_world(root=root)
    try:
        world.timeline().command(
            "hamsterdan.open_pull_request",
            OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
        )
        return cast("dict[str, JsonValue]", observe_hamsterdan(root).model_dump(mode="json"))
    finally:
        world.close()


class TestReadinessOwnerSimulation:
    """Readiness executes and replays the real bridge-mounted lifecycle locally."""

    def test_owner_local_artifact_replays_from_a_fresh_root(self, tmp_path: Path) -> None:
        world = build_readiness_world(root=tmp_path / "record")
        try:
            result = world.timeline().command(
                "readiness.open_lifecycle",
                OPEN_READINESS_COMMAND.model_dump(mode="json"),
            )
            world.timeline().finish(Disposition.QUIESCENT)
            artifact = world.artifact("ds1.readiness.open")
        finally:
            world.close()

        replayed = replay_readiness(artifact, root=tmp_path / "replay")

        assert result.value == {
            "subject": {
                "installation_id": 44,
                "repository_id": 31,
                "pull_request_number": 7,
            },
            "posture": "awaiting_observation",
        }
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest
        encoded = encode_artifact(artifact)
        assert b"hamsterdan." not in encoded
        assert b"net_v5" not in encoded
        assert b"readiness_v5" not in encoded


class TestHamsterdanRootSimulation:
    """The root Timeline reconstructs and exactly replays one bounded host action."""

    def test_crash_after_host_cut_reconstructs_as_an_idempotent_action(self, tmp_path: Path) -> None:
        world = build_hamsterdan_world(root=tmp_path / "record")
        first_timeline = world.timeline()
        try:
            first = first_timeline.command(
                "hamsterdan.open_pull_request",
                OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            )
            first_timeline.crash("after_host_recorded")
            world.restart()
            second_timeline = world.timeline()
            reconstructed = second_timeline.command(
                "hamsterdan.open_pull_request",
                OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            )
            second_timeline.finish(Disposition.QUIESCENT)
            artifact = world.artifact("ds1.hamsterdan.after-host-cut")
        finally:
            world.close()

        replayed = replay_hamsterdan(artifact, root=tmp_path / "replay")
        executions = [operation for operation in artifact.operations if isinstance(operation, ExecuteOperation)]

        assert first.disposition == "applied"
        assert reconstructed.disposition == "idempotent"
        assert [execution.command.name for execution in executions] == [
            "hamsterdan.open_pull_request",
            "hamsterdan.open_pull_request",
        ]
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest

    def test_crash_before_host_cut_reconstructs_and_opens_once(self, tmp_path: Path) -> None:
        world = build_hamsterdan_world(root=tmp_path / "record")
        first_timeline = world.timeline()
        try:
            first_timeline.crash("before_host_recorded")
            world.restart()
            second_timeline = world.timeline()
            opened = second_timeline.command(
                "hamsterdan.open_pull_request",
                OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            )
            second_timeline.finish(Disposition.QUIESCENT)
            artifact = world.artifact("ds1.hamsterdan.before-host-cut")
        finally:
            world.close()

        replayed = replay_hamsterdan(artifact, root=tmp_path / "replay")

        assert opened.disposition == "applied"
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)


class TestHamsterdanCheckerSensitivity:
    """The independent root checker detects each ruled DS1 identity mutation."""

    def test_changed_subject_fails(self, tmp_path: Path) -> None:
        value = deepcopy(opened_state(tmp_path))
        host = cast("dict[str, JsonValue]", value["host"])
        subjects = cast("list[dict[str, JsonValue]]", host["subjects"])
        subject = cast("dict[str, JsonValue]", subjects[0]["subject"])
        subject["pull_request_number"] = 8

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["subject_binding"] is False

    def test_changed_action_identity_fails(self, tmp_path: Path) -> None:
        value = deepcopy(opened_state(tmp_path))
        host = cast("dict[str, JsonValue]", value["host"])
        records = cast("list[dict[str, JsonValue]]", host["records"])
        records[0]["action_identity"] = "trace:mutated:1"

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["action_identity"] is False

    def test_changed_bridge_identity_fails(self, tmp_path: Path) -> None:
        value = deepcopy(opened_state(tmp_path))
        readiness = cast("dict[str, JsonValue]", value["readiness"])
        binding = cast("dict[str, JsonValue]", readiness["binding"])
        binding["bridge_identity"] = "workflow-bridge/mutated@1"

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["readiness"] is False


class TestHamsterdanResourceBounds:
    """Every root scenario boundary reports finite retained and pending resources."""

    def test_resource_samples_stay_within_the_declared_budget(self, tmp_path: Path) -> None:
        world = build_hamsterdan_world(root=tmp_path)
        try:
            timeline = world.timeline()
            timeline.command(
                "hamsterdan.open_pull_request",
                OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
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

    def test_lowered_file_budget_fails_at_the_first_created_file(self, tmp_path: Path) -> None:
        resources = {**DEFAULT_BUDGET.profile_resources, "retained.state.files": 0}
        budget = DEFAULT_BUDGET.model_copy(update={"profile_resources": resources})

        with pytest.raises(BudgetExhausted) as raised:
            build_hamsterdan_world(root=tmp_path, budget=budget)

        assert raised.value.bound == "profile_resources:retained.state.files"
        assert raised.value.limit == 0
