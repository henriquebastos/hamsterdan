# Copyright (c) 2026 Henrique Bastos

"""Deterministic owner-local and root evidence for the first bridged lifecycle."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, cast

from petrus.engine import Engine
from petrus.testing.dst import BudgetExhausted, Disposition, ExecuteOperation, Observation, encode_artifact

from hamsterdan2.readiness.runtime import MAX_HISTORY_RECORDS, HistoryCapacityError
from hamsterdan2.readiness.simulation.ingress import STAGE_ACQUISITION_COMMAND
from hamsterdan2.readiness.simulation.lifecycle import (
    ACCEPT_STAGED_OBSERVATION_COMMAND,
    OPEN_READINESS_COMMAND,
    ReadinessChecker,
    build_readiness_world,
    observe_readiness,
    readiness_resource_usage,
    replay_readiness,
)
from hamsterdan2.readiness.simulation.lifecycle import (
    DEFAULT_BUDGET as READINESS_BUDGET,
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

    def test_staging_and_history_acceptance_are_separate_fresh_root_replay_cuts(self, tmp_path: Path) -> None:
        record_root = tmp_path / "record"
        world = build_readiness_world(root=record_root)
        try:
            timeline = world.timeline()
            timeline.command(
                "readiness.open_lifecycle",
                OPEN_READINESS_COMMAND.model_dump(mode="json"),
            )
            timeline.command(
                "readiness.stage_acquisition",
                STAGE_ACQUISITION_COMMAND.model_dump(mode="json"),
            )
            staged = observe_readiness(record_root)
            accepted = timeline.command(
                "readiness.accept_staged_observation",
                ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
            timeline.finish(Disposition.QUIESCENT)
            artifact = world.artifact("cv21.ds2.readiness-history-acceptance")
        finally:
            world.close()

        state = observe_readiness(record_root)
        replayed = replay_readiness(artifact, root=tmp_path / "replay")
        accepted_value = cast("dict[str, JsonValue]", accepted.value)
        assert staged.staging is not None
        assert staged.history_records == 21
        assert staged.in_flight_occurrences == 0
        assert not staged.accepted
        assert staged.delivery is None
        assert accepted.disposition == "applied"
        assert accepted_value["disposition"] == "accepted"
        assert accepted_value["finished"] is False
        assert accepted_value["folded"] is False
        assert state.history_records == 23
        assert state.in_flight_occurrences == 1
        assert state.accepted
        assert not state.folded
        assert state.delivery is not None
        assert state.delivery.record_order == ("ExternalEventDelivered", "FiringBegun")
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest

    @pytest.mark.parametrize(
        ("path", "replacement", "detail"),
        [
            pytest.param(("binding", "bridge_identity"), "workflow-bridge/mutated@1", "bridge_identity"),
            pytest.param(("staging", "manifest", "policy_revision"), "policy:mutated", "staging_authority"),
            pytest.param(
                ("staging", "grant", "grant_id"),
                f"grant:v1:sha256:{'f' * 64}",
                "grant",
            ),
            pytest.param(
                ("staging", "manifest", "entries", 0, "observation_key"),
                f"obs:v1:sha256:{'f' * 64}",
                "observation_key",
            ),
            pytest.param(
                ("staging", "manifest", "entries", 0, "observation", "head", "sha"),
                "c" * 40,
                "staging_authority",
                id="bridge-input-observation",
            ),
            pytest.param(("delivery", "source"), "on_mutated", "history_delivery"),
            pytest.param(("delivery", "token_color"), "Mutated", "history_delivery"),
            pytest.param(("delivery", "token_payload", "head"), "c" * 40, "history_delivery"),
            pytest.param(
                ("delivery", "delivery_identity"),
                f"history-delivery:v1:sha256:{'f' * 64}",
                "delivery_identity",
            ),
            pytest.param(("delivery", "occurrence"), 2, "occurrence"),
            pytest.param(("in_flight_occurrences",), 2, "in_flight_occurrences"),
            pytest.param(("staging",), None, "staging_authority", id="missing-staging"),
            pytest.param(
                ("delivery", "record_order"),
                ["FiringBegun", "ExternalEventDelivered"],
                "history_delivery",
            ),
            pytest.param(("accepted",), False, "accepted"),
            pytest.param(("folded",), True, "accepted"),
        ],
    )
    def test_owner_checker_rejects_changed_acceptance_evidence(
        self,
        tmp_path: Path,
        path: tuple[str | int, ...],
        replacement: JsonValue,
        detail: str,
    ) -> None:
        root = tmp_path / detail
        world = build_readiness_world(root=root)
        try:
            timeline = world.timeline()
            timeline.command("readiness.open_lifecycle", OPEN_READINESS_COMMAND.model_dump(mode="json"))
            timeline.command("readiness.stage_acquisition", STAGE_ACQUISITION_COMMAND.model_dump(mode="json"))
            timeline.command(
                "readiness.accept_staged_observation",
                ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
        finally:
            world.close()
        value = cast("dict[str, JsonValue]", observe_readiness(root).model_dump(mode="json"))
        target: object = value
        for part in path[:-1]:
            if isinstance(part, int):
                assert isinstance(target, list)
                target = target[part]
            else:
                assert isinstance(target, dict)
                target = target[part]
        final = path[-1]
        assert isinstance(final, str)
        assert isinstance(target, dict)
        target[final] = replacement

        result = ReadinessChecker().check(
            Observation(name="readiness.state", value=value, instant=0, generation=1, sequence=0)
        )

        assert not result.passed
        if detail in cast("dict[str, JsonValue]", result.detail):
            assert cast("dict[str, JsonValue]", result.detail)[detail] is False

    def test_owner_checker_rejects_an_added_entry_order(self, tmp_path: Path) -> None:
        root = tmp_path / "entry-order"
        world = build_readiness_world(root=root)
        try:
            timeline = world.timeline()
            timeline.command("readiness.open_lifecycle", OPEN_READINESS_COMMAND.model_dump(mode="json"))
            timeline.command("readiness.stage_acquisition", STAGE_ACQUISITION_COMMAND.model_dump(mode="json"))
            timeline.command(
                "readiness.accept_staged_observation",
                ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
        finally:
            world.close()
        value = cast("dict[str, JsonValue]", observe_readiness(root).model_dump(mode="json"))
        staging = cast("dict[str, JsonValue]", value["staging"])
        manifest = cast("dict[str, JsonValue]", staging["manifest"])
        entries = cast("list[JsonValue]", manifest["entries"])
        second = deepcopy(cast("dict[str, JsonValue]", entries[0]))
        second["order"] = 1
        second["observation_key"] = f"obs:v1:sha256:{'f' * 64}"
        entries.append(second)

        result = ReadinessChecker().check(
            Observation(name="readiness.state", value=value, instant=0, generation=1, sequence=0)
        )

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["staging_authority"] is False

    def test_history_observation_uses_one_bounded_public_page(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = tmp_path / "history-page"
        world = build_readiness_world(root=root)
        try:
            world.timeline().command(
                "readiness.open_lifecycle",
                OPEN_READINESS_COMMAND.model_dump(mode="json"),
            )
        finally:
            world.close()
        calls: list[tuple[int, int]] = []
        original = Engine.history_page

        def observed_page(engine: Engine, after: int, limit: int) -> dict[str, object]:
            calls.append((after, limit))
            return original(engine, after, limit)

        monkeypatch.setattr(Engine, "history_page", observed_page)

        state = observe_readiness(root)

        assert state.history_records == 21
        assert calls == [(0, MAX_HISTORY_RECORDS)]

    def test_history_observation_rejects_an_oversized_frontier_before_checker_scans(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = tmp_path / "history-frontier"
        world = build_readiness_world(root=root)
        try:
            world.timeline().command(
                "readiness.open_lifecycle",
                OPEN_READINESS_COMMAND.model_dump(mode="json"),
            )
        finally:
            world.close()

        def oversized_page(engine: Engine, after: int, limit: int) -> dict[str, object]:
            del engine
            assert (after, limit) == (0, MAX_HISTORY_RECORDS)
            return {"frontier": MAX_HISTORY_RECORDS + 1, "records": []}

        monkeypatch.setattr(Engine, "history_page", oversized_page)

        with pytest.raises(HistoryCapacityError) as raised:
            observe_readiness(root)

        assert raised.value.args == (
            "history_capacity_exceeded",
            "records",
            MAX_HISTORY_RECORDS + 1,
            MAX_HISTORY_RECORDS,
        )


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

    def test_zero_in_flight_budget_rejects_the_unfinished_acceptance(self, tmp_path: Path) -> None:
        resources = {
            **READINESS_BUDGET.profile_resources,
            "retained.readiness.in_flight_occurrences": 0,
        }
        budget = READINESS_BUDGET.model_copy(update={"profile_resources": resources})
        world = build_readiness_world(root=tmp_path, budget=budget)
        try:
            timeline = world.timeline()
            timeline.command("readiness.open_lifecycle", OPEN_READINESS_COMMAND.model_dump(mode="json"))
            timeline.command("readiness.stage_acquisition", STAGE_ACQUISITION_COMMAND.model_dump(mode="json"))
            with pytest.raises(BudgetExhausted) as raised:
                timeline.command(
                    "readiness.accept_staged_observation",
                    ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
                )
        finally:
            world.close()

        assert raised.value.bound == "profile_resources:retained.readiness.in_flight_occurrences"
        assert raised.value.limit == 0

    def test_lowered_file_budget_fails_at_the_first_created_file(self, tmp_path: Path) -> None:
        resources = {**DEFAULT_BUDGET.profile_resources, "retained.state.files": 0}
        budget = DEFAULT_BUDGET.model_copy(update={"profile_resources": resources})

        with pytest.raises(BudgetExhausted) as raised:
            build_hamsterdan_world(root=tmp_path, budget=budget)

        assert raised.value.bound == "profile_resources:retained.state.files"
        assert raised.value.limit == 0

    def test_owner_resource_observation_stops_at_the_fixed_file_ceiling(self, tmp_path: Path) -> None:
        for index in range(READINESS_BUDGET.profile_resources["retained.state.files"] + 1):
            (tmp_path / f"state-{index}").touch()

        with pytest.raises(RuntimeError) as raised:
            readiness_resource_usage(tmp_path)

        assert raised.value.args == (
            "state_file_capacity_exceeded",
            READINESS_BUDGET.profile_resources["retained.state.files"],
        )

    def test_owner_resource_observation_stops_at_the_fixed_byte_ceiling(self, tmp_path: Path) -> None:
        maximum_bytes = READINESS_BUDGET.profile_resources["retained.state.bytes"]
        (tmp_path / "oversized-state").write_bytes(b"x" * (maximum_bytes + 1))

        with pytest.raises(RuntimeError) as raised:
            readiness_resource_usage(tmp_path)

        assert raised.value.args == ("state_byte_capacity_exceeded", maximum_bytes)
