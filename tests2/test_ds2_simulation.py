# Copyright (c) 2026 Henrique Bastos

"""Deterministic owner-local and root evidence for signed webhook custody."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import sqlite3
from typing import TYPE_CHECKING, cast

from petrus.testing.dst import (
    BudgetExhausted,
    CheckResult,
    CheckerIdentity,
    Disposition,
    ExecuteOperation,
    Observation,
    encode_artifact,
)

from hamsterdan2.github_app.simulation.webhooks import (
    EXPECTED_WEBHOOK,
    NORMALIZE_WEBHOOK_COMMAND,
    WEBHOOK_SIGNING_MATERIAL,
    build_github_webhook_world,
    replay_github_webhook,
)
from hamsterdan2.readiness.ingress_values import PolicyRevision
from hamsterdan2.readiness.runtime import AcceptedObservationNotFoundError, ObservationNotFoldedError
from hamsterdan2.readiness.simulation.ingress import (
    DEFAULT_BUDGET as INGRESS_BUDGET,
)
from hamsterdan2.readiness.simulation.ingress import (
    EXPECTED_ACQUISITION,
    EXPECTED_CANONICAL_BYTES,
    POLICY_REVISION,
    STAGE_ACQUISITION_COMMAND,
    IngressChecker,
    build_ingress_world,
    ingress_checker_identity,
    ingress_profile_identity,
    observe_ingress,
    replay_ingress,
)
from hamsterdan2.readiness.simulation.ingress import (
    PROFILE_IDENTITY as INGRESS_PROFILE_IDENTITY,
)
from hamsterdan2.readiness.simulation.ingress import (
    RESOURCE_LIMITS as INGRESS_RESOURCE_LIMITS,
)
from hamsterdan2.readiness.simulation.lifecycle import (
    EXPECTED_HISTORY_DELIVERY_IDENTITY,
    FOLDED_HISTORY_RECORDS,
    FOLD_ACCEPTED_OBSERVATION_COMMAND,
    OPEN_READINESS_COMMAND,
    ReadinessChecker,
    ReadinessState,
    build_readiness_world,
    readiness_state,
    replay_readiness,
)
from hamsterdan2.readiness.simulation.lifecycle import (
    PROFILE_IDENTITY as READINESS_PROFILE_IDENTITY,
)
from hamsterdan2.simulation.hamsterdan import (
    ACCEPT_STAGED_OBSERVATION_COMMAND,
    COLLIDE_WEBHOOK_COMMAND,
    COLLISION_WEBHOOK_FIXTURE_DIGEST,
    COMPLETE_OBSERVATION_DELIVERY_COMMAND,
    DEFAULT_BUDGET,
    EXPECTED_DELIVERY,
    EXPECTED_QUARANTINED_DELIVERY,
    EXPECTED_RECORD,
    EXPECTED_STAGING,
    OPEN_PULL_REQUEST_COMMAND,
    ORIGINAL_WEBHOOK_FIXTURE_DIGEST,
    RECEIVE_WEBHOOK_COMMAND,
    STAGE_WEBHOOK_COMMAND,
    STAGING_POLICY_REVISION,
    HamsterdanChecker,
    build_hamsterdan_world,
    hamsterdan_checker_identity,
    hamsterdan_profile_identity,
    host_state,
    observe_hamsterdan,
    replay_hamsterdan,
    root_resource_usage,
)
from hamsterdan2.simulation.hamsterdan import (
    PROFILE_IDENTITY as ROOT_PROFILE_IDENTITY,
)
from hamsterdan2.simulation.hamsterdan import (
    RESOURCE_LIMITS as ROOT_RESOURCE_LIMITS,
)

import pytest


if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue


def checker_observation(value: JsonValue) -> Observation:
    return Observation(name="hamsterdan.state", value=value, instant=0, generation=1, sequence=0)


def replace_path_value(
    value: dict[str, JsonValue],
    path: tuple[str | int, ...],
    replacement: JsonValue,
) -> None:
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


def staged_state(root: Path) -> dict[str, JsonValue]:
    world = build_hamsterdan_world(root=root)
    try:
        world.timeline().command(
            "hamsterdan.receive_webhook",
            RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
        )
        world.timeline().command(
            "hamsterdan.stage_webhook",
            STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
        )
        return cast("dict[str, JsonValue]", observe_hamsterdan(root).model_dump(mode="json"))
    finally:
        world.close()


def accepted_state(root: Path) -> dict[str, JsonValue]:
    world = build_hamsterdan_world(root=root)
    try:
        timeline = world.timeline()
        timeline.command(
            "hamsterdan.open_pull_request",
            OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
        )
        timeline.command(
            "hamsterdan.receive_webhook",
            RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
        )
        timeline.command(
            "hamsterdan.stage_webhook",
            STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
        )
        timeline.command(
            "hamsterdan.accept_staged_observation",
            ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
        )
        return cast("dict[str, JsonValue]", observe_hamsterdan(root).model_dump(mode="json"))
    finally:
        world.close()


def folded_state(root: Path) -> dict[str, JsonValue]:
    world = build_hamsterdan_world(root=root)
    try:
        timeline = world.timeline()
        for command_name, command in (
            ("hamsterdan.open_pull_request", OPEN_PULL_REQUEST_COMMAND),
            ("hamsterdan.receive_webhook", RECEIVE_WEBHOOK_COMMAND),
            ("hamsterdan.stage_webhook", STAGE_WEBHOOK_COMMAND),
            ("hamsterdan.accept_staged_observation", ACCEPT_STAGED_OBSERVATION_COMMAND),
            ("hamsterdan.fold_accepted_observation", FOLD_ACCEPTED_OBSERVATION_COMMAND),
        ):
            timeline.command(command_name, command.model_dump(mode="json"))
        return cast("dict[str, JsonValue]", observe_hamsterdan(root).model_dump(mode="json"))
    finally:
        world.close()


def completed_state(root: Path) -> dict[str, JsonValue]:
    world = build_hamsterdan_world(root=root)
    try:
        timeline = world.timeline()
        for command_name, command in (
            ("hamsterdan.open_pull_request", OPEN_PULL_REQUEST_COMMAND),
            ("hamsterdan.receive_webhook", RECEIVE_WEBHOOK_COMMAND),
            ("hamsterdan.stage_webhook", STAGE_WEBHOOK_COMMAND),
            ("hamsterdan.accept_staged_observation", ACCEPT_STAGED_OBSERVATION_COMMAND),
            ("hamsterdan.fold_accepted_observation", FOLD_ACCEPTED_OBSERVATION_COMMAND),
            ("hamsterdan.complete_observation_delivery", COMPLETE_OBSERVATION_DELIVERY_COMMAND),
        ):
            timeline.command(command_name, command.model_dump(mode="json"))
        return cast("dict[str, JsonValue]", observe_hamsterdan(root).model_dump(mode="json"))
    finally:
        world.close()


def collision_staged_state(root: Path) -> dict[str, JsonValue]:
    world = build_hamsterdan_world(root=root)
    try:
        world.timeline().command(
            "hamsterdan.receive_webhook",
            RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
        )
        world.timeline().command(
            "hamsterdan.receive_webhook",
            COLLIDE_WEBHOOK_COMMAND.model_dump(mode="json"),
        )
        world.timeline().command(
            "hamsterdan.stage_webhook",
            STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
        )
        return cast("dict[str, JsonValue]", observe_hamsterdan(root).model_dump(mode="json"))
    finally:
        world.close()


def staged_ingress_state(root: Path) -> dict[str, JsonValue]:
    world = build_ingress_world(root=root)
    try:
        world.timeline().command(
            "readiness.stage_acquisition",
            STAGE_ACQUISITION_COMMAND.model_dump(mode="json"),
        )
        return cast("dict[str, JsonValue]", observe_ingress(root).model_dump(mode="json"))
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


class TestReadinessIngressOwnerSimulation:
    """Readiness-owned staging replays from a fresh root with finite evidence."""

    def test_novel_staging_artifact_replays_with_exact_resources(self, tmp_path: Path) -> None:
        world = build_ingress_world(root=tmp_path / "record")
        try:
            staged = world.timeline().command(
                "readiness.stage_acquisition",
                STAGE_ACQUISITION_COMMAND.model_dump(mode="json"),
            )
            world.timeline().finish(Disposition.QUIESCENT)
            artifact = world.artifact("cv21.ds2.readiness-ingress")
        finally:
            world.close()

        replayed = replay_ingress(artifact, root=tmp_path / "replay")
        samples = [entry for entry in world.journal if entry.kind == "resource"]
        staged_value = cast("dict[str, JsonValue]", staged.value)
        assert staged.disposition == "applied"
        assert staged_value["disposition"] == "novel"
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest
        assert encode_artifact(artifact).count(EXPECTED_CANONICAL_BYTES) == 2
        assert all(
            cast("dict[str, int]", cast("dict[str, JsonValue]", sample.value)["usage"])[name]
            <= INGRESS_BUDGET.profile_resources[name]
            for sample in samples
            for name in INGRESS_BUDGET.profile_resources
        )

    @pytest.mark.parametrize(
        ("path", "replacement", "detail"),
        [
            pytest.param(
                ("acquisition", "custody_generation"),
                2,
                "acquisition_evidence",
                id="acquisition-generation",
            ),
            pytest.param(
                ("acquisition", "webhook", "snapshot", "provider_updated_at"),
                "2026-08-30T12:34:57Z",
                "acquisition_evidence",
                id="acquisition-provider-time",
            ),
            pytest.param(
                ("posture", "disposition"),
                "exact_duplicate",
                "disposition",
                id="disposition",
            ),
            pytest.param(
                ("posture", "manifest", "acquisition", "provider_route_id"),
                "github:mutated",
                "acquisition",
                id="acquisition",
            ),
            pytest.param(
                ("posture", "manifest", "manifest_id"),
                f"manifest:v1:sha256:{'f' * 64}",
                "manifest",
                id="manifest",
            ),
            pytest.param(
                ("posture", "manifest", "policy_revision"),
                "policy:mutated",
                "manifest",
                id="policy",
            ),
            pytest.param(
                ("posture", "manifest", "entries", 0, "observation_key"),
                f"obs:v1:sha256:{'f' * 64}",
                "key",
                id="key",
            ),
            pytest.param(
                ("posture", "manifest", "entries", 0, "canonical_bytes"),
                "{}",
                "canonical_bytes",
                id="canonical-bytes",
            ),
            pytest.param(
                ("posture", "manifest", "entries", 0, "observation", "draft"),
                True,
                "observation",
                id="observation",
            ),
            pytest.param(
                ("posture", "grant", "grant_id"),
                f"grant:v1:sha256:{'f' * 64}",
                "grant",
                id="grant-identity",
            ),
            pytest.param(
                ("posture", "grant", "manifest_id"),
                f"manifest:v1:sha256:{'f' * 64}",
                "grant",
                id="grant-manifest",
            ),
            pytest.param(
                ("posture", "grant", "manifest_digest"),
                "f" * 64,
                "grant",
                id="grant-digest",
            ),
            pytest.param(
                ("posture", "decisions", 0, "observation_key"),
                f"obs:v1:sha256:{'f' * 64}",
                "decision",
                id="decision-identity",
            ),
            pytest.param(
                ("resources", "grants"),
                2,
                "resources",
                id="resources",
            ),
            pytest.param(
                ("resources", "acquisition_bytes"),
                0,
                "acquisition_bytes",
                id="acquisition-bytes",
            ),
        ],
    )
    def test_owner_checker_rejects_changed_staging_authority(
        self,
        tmp_path: Path,
        path: tuple[str | int, ...],
        replacement: JsonValue,
        detail: str,
    ) -> None:
        value = staged_ingress_state(tmp_path)
        target: object = value
        for part in path[:-1]:
            if isinstance(part, int):
                assert isinstance(target, list)
                target = target[part]
            else:
                assert isinstance(target, dict)
                target = target[part]
        final = path[-1]
        if isinstance(final, int):
            assert isinstance(target, list)
            target[final] = replacement
        else:
            assert isinstance(target, dict)
            target[final] = replacement

        result = IngressChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)[detail] is False

    def test_owner_checker_rejects_an_added_ordered_entry(self, tmp_path: Path) -> None:
        value = staged_ingress_state(tmp_path)
        posture = cast("dict[str, JsonValue]", value["posture"])
        manifest = cast("dict[str, JsonValue]", posture["manifest"])
        entries = cast("list[JsonValue]", manifest["entries"])
        second = deepcopy(cast("dict[str, JsonValue]", entries[0]))
        second["order"] = 1
        second["observation_key"] = f"obs:v1:sha256:{'f' * 64}"
        entries.append(second)

        result = IngressChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["entry_order"] is False

    def test_owner_world_enforces_the_sqlite_page_budget(self, tmp_path: Path) -> None:
        resources = {
            **INGRESS_BUDGET.profile_resources,
            "retained.readiness.ingress.database_pages": 0,
        }
        budget = INGRESS_BUDGET.model_copy(update={"profile_resources": resources})

        with pytest.raises(BudgetExhausted) as raised:
            build_ingress_world(root=tmp_path, budget=budget)

        assert raised.value.bound == "profile_resources:retained.readiness.ingress.database_pages"
        assert raised.value.limit == 0


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
        assert state.readiness == ReadinessState(
            binding=None,
            history_records=0,
            in_flight_occurrences=0,
        )
        assert state.ingress.posture is None
        assert state.ingress.resources.manifests == 0
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest

    def test_separate_authority_command_stages_once_without_history_or_fold(self, tmp_path: Path) -> None:
        record_root = tmp_path / "record"
        world = build_hamsterdan_world(root=record_root)
        try:
            receipt = world.timeline().command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            custody_only = observe_hamsterdan(record_root)
            staged = world.timeline().command(
                "hamsterdan.stage_webhook",
                STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            world.timeline().finish(Disposition.QUIESCENT)
            artifact = world.artifact("cv21.ds2.source-neutral-staging")
        finally:
            world.close()

        state = observe_hamsterdan(record_root)
        replayed = replay_hamsterdan(artifact, root=tmp_path / "replay")
        staged_value = cast("dict[str, JsonValue]", staged.value)
        assert receipt.disposition == "applied"
        assert custody_only.ingress.posture is None
        assert custody_only.readiness == ReadinessState(
            binding=None,
            history_records=0,
            in_flight_occurrences=0,
        )
        assert staged.disposition == "applied"
        assert staged_value["disposition"] == "novel"
        assert state.ingress.posture is not None
        assert state.ingress.posture.disposition == "novel"
        assert state.ingress.resources.manifests == 1
        assert state.ingress.resources.entries == 1
        assert state.ingress.resources.grants == 1
        assert state.ingress.resources.decisions == 1
        assert state.readiness == ReadinessState(
            binding=None,
            history_records=0,
            in_flight_occurrences=0,
            staging=state.ingress.posture,
        )
        assert not (record_root / "dispatch.sqlite3").exists()
        assert not list(record_root.rglob("history.sqlite3"))
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest

    def test_custody_staging_and_unfinished_history_acceptance_are_distinct_replay_cuts(
        self,
        tmp_path: Path,
    ) -> None:
        record_root = tmp_path / "record"
        world = build_hamsterdan_world(root=record_root)
        try:
            timeline = world.timeline()
            timeline.command(
                "hamsterdan.open_pull_request",
                OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            )
            timeline.command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            custody = observe_hamsterdan(record_root)
            timeline.command(
                "hamsterdan.stage_webhook",
                STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            staging = observe_hamsterdan(record_root)
            accepted = timeline.command(
                "hamsterdan.accept_staged_observation",
                ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
            timeline.finish(Disposition.QUIESCENT)
            artifact = world.artifact("cv21.ds2.history-accepted-unfinished")
        finally:
            world.close()

        state = observe_hamsterdan(record_root)
        replayed = replay_hamsterdan(artifact, root=tmp_path / "replay")
        accepted_value = cast("dict[str, JsonValue]", accepted.value)
        assert custody.delivery.rows == 1
        assert custody.ingress.posture is None
        assert custody.readiness.history_records == 21
        assert not custody.readiness.accepted
        assert staging.ingress.posture is not None
        assert staging.ingress.posture.disposition == "novel"
        assert staging.readiness.staging == staging.ingress.posture
        assert staging.readiness.history_records == 21
        assert not staging.readiness.accepted
        assert accepted.disposition == "applied"
        assert accepted_value["disposition"] == "accepted"
        assert accepted_value["finished"] is False
        assert accepted_value["folded"] is False
        assert state.readiness.history_records == 23
        assert state.readiness.in_flight_occurrences == 1
        assert state.readiness.staging == state.ingress.posture
        assert state.readiness.accepted
        assert not state.readiness.folded
        assert state.readiness.delivery is not None
        assert state.readiness.delivery.source == "on_head"
        assert state.readiness.delivery.token_color == "HeadSeen"
        assert state.readiness.delivery.delivery_identity == EXPECTED_HISTORY_DELIVERY_IDENTITY
        assert state.readiness.delivery.occurrence == 1
        assert state.readiness.delivery.record_order == ("ExternalEventDelivered", "FiringBegun")
        assert state.host.records == [EXPECTED_RECORD]
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest

    def test_full_cumulative_tracer_exposes_fold_and_host_completion_as_separate_replay_cuts(
        self,
        tmp_path: Path,
    ) -> None:
        record_root = tmp_path / "record"
        world = build_hamsterdan_world(root=record_root)
        try:
            timeline = world.timeline()
            timeline.command(
                "hamsterdan.open_pull_request",
                OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            )
            opened = observe_hamsterdan(record_root)
            timeline.command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            custody = observe_hamsterdan(record_root)
            timeline.command(
                "hamsterdan.stage_webhook",
                STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            staged = observe_hamsterdan(record_root)
            timeline.command(
                "hamsterdan.accept_staged_observation",
                ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
            accepted = observe_hamsterdan(record_root)
            fold_result = timeline.command(
                "hamsterdan.fold_accepted_observation",
                FOLD_ACCEPTED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
            folded = observe_hamsterdan(record_root)
            completion_result = timeline.command(
                "hamsterdan.complete_observation_delivery",
                COMPLETE_OBSERVATION_DELIVERY_COMMAND.model_dump(mode="json"),
            )
            timeline.finish(Disposition.QUIESCENT)
            artifact = world.artifact("cv21.ds2.complete-tracer")
        finally:
            world.close()

        completed = observe_hamsterdan(record_root)
        replayed = replay_hamsterdan(artifact, root=tmp_path / "replay")
        fold_value = cast("dict[str, JsonValue]", fold_result.value)
        completion_value = cast("dict[str, JsonValue]", completion_result.value)
        assert opened.readiness.history_records == 21
        assert opened.delivery.rows == 0
        assert custody.delivery.rows == 1
        assert custody.ingress.posture is None
        assert staged.ingress.posture == EXPECTED_STAGING
        assert staged.readiness.history_records == 21
        assert accepted.readiness.history_records == 23
        assert accepted.readiness.in_flight_occurrences == 1
        assert accepted.readiness.fold_posture is None
        assert accepted.delivery.completion_rows == 0
        assert fold_result.disposition == "applied"
        assert fold_value["cut"] == "observation_folded"
        assert folded.readiness.history_records == FOLDED_HISTORY_RECORDS
        assert folded.readiness.in_flight_occurrences == 0
        assert folded.readiness.fold_posture is not None
        assert folded.readiness.fold_posture.cut == "observation_folded"
        assert folded.readiness.delivery is not None
        assert folded.readiness.delivery.record_order == (
            "ExternalEventDelivered",
            "FiringBegun",
            "TokensProduced",
            "FiringCompleted",
        )
        assert folded.readiness.delivery.produced_place == "life.heads"
        assert folded.readiness.delivery.produced_entries == ()
        assert folded.readiness.delivery.completed_transition == "on_head"
        assert folded.delivery.completion_rows == 0
        assert completion_result.disposition == "applied"
        assert completion_value["cut"] == "host_delivery_completed"
        assert completed.readiness == folded.readiness
        assert completed.delivery.completion_rows == 1
        assert completed.delivery.completion is not None
        assert completed.delivery.completion.history_delivery_identity == EXPECTED_HISTORY_DELIVERY_IDENTITY
        assert completed.delivery.completion.workflow_cut == "observation_folded"
        assert completed.delivery.completion.cut == "host_delivery_completed"
        assert root_resource_usage(record_root).values["pending.motus.tasks"] == 0
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest

    def test_fresh_root_exact_retries_append_neither_fold_nor_host_completion(self, tmp_path: Path) -> None:
        root = tmp_path / "state"
        completed_state(root)
        before = observe_hamsterdan(root)
        world = build_hamsterdan_world(root=root)
        try:
            folded = world.timeline().command(
                "hamsterdan.fold_accepted_observation",
                FOLD_ACCEPTED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
            completed = world.timeline().command(
                "hamsterdan.complete_observation_delivery",
                COMPLETE_OBSERVATION_DELIVERY_COMMAND.model_dump(mode="json"),
            )
            world.timeline().finish(Disposition.QUIESCENT)
        finally:
            world.close()

        assert folded.disposition == "idempotent"
        assert completed.disposition == "idempotent"
        assert observe_hamsterdan(root) == before

    def test_fold_and_host_completion_refuse_out_of_order_without_hidden_action(self, tmp_path: Path) -> None:
        root = tmp_path / "state"
        world = build_hamsterdan_world(root=root)
        try:
            timeline = world.timeline()
            for name, command in (
                ("hamsterdan.open_pull_request", OPEN_PULL_REQUEST_COMMAND),
                ("hamsterdan.receive_webhook", RECEIVE_WEBHOOK_COMMAND),
                ("hamsterdan.stage_webhook", STAGE_WEBHOOK_COMMAND),
            ):
                timeline.command(name, command.model_dump(mode="json"))
            with pytest.raises(AcceptedObservationNotFoundError):
                timeline.command(
                    "hamsterdan.fold_accepted_observation",
                    FOLD_ACCEPTED_OBSERVATION_COMMAND.model_dump(mode="json"),
                )
            assert observe_hamsterdan(root).readiness.history_records == 21
            timeline.command(
                "hamsterdan.accept_staged_observation",
                ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
            with pytest.raises(ObservationNotFoldedError):
                timeline.command(
                    "hamsterdan.complete_observation_delivery",
                    COMPLETE_OBSERVATION_DELIVERY_COMMAND.model_dump(mode="json"),
                )
        finally:
            world.close()

        state = observe_hamsterdan(root)
        assert state.readiness.history_records == 23
        assert state.readiness.in_flight_occurrences == 1
        assert state.delivery.completion_rows == 0

    def test_late_collision_preserves_fold_completion_and_quarantine_evidence(self, tmp_path: Path) -> None:
        root = tmp_path / "state"
        world = build_hamsterdan_world(root=root)
        try:
            timeline = world.timeline()
            for name, command in (
                ("hamsterdan.open_pull_request", OPEN_PULL_REQUEST_COMMAND),
                ("hamsterdan.receive_webhook", RECEIVE_WEBHOOK_COMMAND),
                ("hamsterdan.stage_webhook", STAGE_WEBHOOK_COMMAND),
                ("hamsterdan.accept_staged_observation", ACCEPT_STAGED_OBSERVATION_COMMAND),
                ("hamsterdan.fold_accepted_observation", FOLD_ACCEPTED_OBSERVATION_COMMAND),
                ("hamsterdan.receive_webhook", COLLIDE_WEBHOOK_COMMAND),
                ("hamsterdan.complete_observation_delivery", COMPLETE_OBSERVATION_DELIVERY_COMMAND),
            ):
                timeline.command(name, command.model_dump(mode="json"))
            timeline.finish(Disposition.QUIESCENT)
        finally:
            world.close()

        state = observe_hamsterdan(root)
        assert state.delivery.retained == EXPECTED_QUARANTINED_DELIVERY
        assert state.ingress.posture == EXPECTED_STAGING
        assert state.readiness.fold_posture is not None
        assert state.readiness.fold_posture.head.sha == "a" * 40
        assert state.delivery.completion_rows == 1
        assert state.delivery.completion is not None
        assert state.delivery.completion.history_delivery_identity == EXPECTED_HISTORY_DELIVERY_IDENTITY


class TestReadinessLifecycleOwnerSimulation:
    """The readiness owner proves unfinished acceptance and exact fold separately."""

    def test_owner_world_folds_only_after_acceptance_and_replays_from_a_fresh_root(self, tmp_path: Path) -> None:
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
            timeline.command(
                "readiness.accept_staged_observation",
                ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
            accepted = readiness_state(
                record_root / "instance",
                dispatch_path=record_root / "dispatch.sqlite3",
                ingress_path=record_root / "readiness-ingress.sqlite3",
            )
            fold = timeline.command(
                "readiness.fold_accepted_observation",
                FOLD_ACCEPTED_OBSERVATION_COMMAND.model_dump(mode="json"),
            )
            timeline.finish(Disposition.QUIESCENT)
            artifact = world.artifact("cv21.ds2.readiness-fold")
        finally:
            world.close()

        state = readiness_state(
            record_root / "instance",
            dispatch_path=record_root / "dispatch.sqlite3",
            ingress_path=record_root / "readiness-ingress.sqlite3",
        )
        replayed = replay_readiness(artifact, root=tmp_path / "replay")
        assert accepted.history_records == 23
        assert accepted.in_flight_occurrences == 1
        assert accepted.fold_posture is None
        assert fold.disposition == "applied"
        assert state.history_records == FOLDED_HISTORY_RECORDS
        assert state.in_flight_occurrences == 0
        assert state.fold_posture is not None
        assert state.fold_posture.cut == "observation_folded"
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest


class TestWebhookRootCollisionSimulation:
    """The cumulative root preserves quarantine separately from readiness authority."""

    def test_quarantined_acquisition_stages_one_empty_collision_manifest_and_replays(self, tmp_path: Path) -> None:
        record_root = tmp_path / "record"
        world = build_hamsterdan_world(root=record_root)
        try:
            world.timeline().command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            world.timeline().command(
                "hamsterdan.receive_webhook",
                COLLIDE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            staged = world.timeline().command(
                "hamsterdan.stage_webhook",
                STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            world.timeline().finish(Disposition.QUIESCENT)
            artifact = world.artifact("cv21.ds2.quarantined-source-neutral-staging")
        finally:
            world.close()

        state = observe_hamsterdan(record_root)
        replayed = replay_hamsterdan(artifact, root=tmp_path / "replay")
        assert staged.disposition == "applied"
        assert state.ingress.posture is not None
        assert state.ingress.posture.disposition == "acquisition_collision"
        assert state.ingress.posture.manifest.entries == ()
        assert state.ingress.resources.manifests == 1
        assert state.ingress.resources.entries == 0
        assert state.ingress.resources.grants == 1
        assert state.ingress.resources.decisions == 1
        assert state.readiness == ReadinessState(
            binding=None,
            history_records=0,
            in_flight_occurrences=0,
            staging=state.ingress.posture,
        )
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

    def test_later_delivery_collision_preserves_the_original_eligible_staging_authority(self, tmp_path: Path) -> None:
        world = build_hamsterdan_world(root=tmp_path)
        try:
            world.timeline().command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            world.timeline().command(
                "hamsterdan.stage_webhook",
                STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            collision = world.timeline().command(
                "hamsterdan.receive_webhook",
                COLLIDE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            state = observe_hamsterdan(tmp_path)
        finally:
            world.close()

        assert collision.disposition == "applied"
        assert state.delivery.retained == EXPECTED_QUARANTINED_DELIVERY
        assert state.ingress.acquisition is not None
        assert not state.ingress.acquisition.quarantined
        assert state.ingress.posture is not None
        assert state.ingress.posture.disposition == "novel"
        assert len(state.ingress.posture.manifest.entries) == 1


class TestSimulationProfileIdentitySensitivity:
    """Replay profile identities bind every fixed input and resource contract."""

    def test_ingress_profile_identity_binds_provider_diagnostic_time(self) -> None:
        changed_snapshot = EXPECTED_ACQUISITION.webhook.snapshot.model_copy(
            update={
                "provider_updated_at": (
                    EXPECTED_ACQUISITION.webhook.snapshot.provider_updated_at + timedelta(seconds=1)
                )
            }
        )
        changed_webhook = EXPECTED_ACQUISITION.webhook.model_copy(update={"snapshot": changed_snapshot})
        changed_acquisition = EXPECTED_ACQUISITION.model_copy(update={"webhook": changed_webhook})

        changed_identity = ingress_profile_identity(
            acquisition=changed_acquisition,
            policy_revision=POLICY_REVISION,
            observation_request=IngressChecker.request,
            resource_limits=INGRESS_RESOURCE_LIMITS,
        )

        assert changed_identity.digest != INGRESS_PROFILE_IDENTITY.digest

    def test_ingress_profile_identity_binds_staging_policy(self) -> None:
        changed_identity = ingress_profile_identity(
            acquisition=EXPECTED_ACQUISITION,
            policy_revision=PolicyRevision("policy:mutated"),
            observation_request=IngressChecker.request,
            resource_limits=INGRESS_RESOURCE_LIMITS,
        )

        assert changed_identity.digest != INGRESS_PROFILE_IDENTITY.digest

    def test_ingress_profile_identity_binds_one_resource_gauge(self) -> None:
        changed_resources = {
            **INGRESS_RESOURCE_LIMITS,
            "retained.readiness.ingress.database_pages": INGRESS_RESOURCE_LIMITS[
                "retained.readiness.ingress.database_pages"
            ]
            - 1,
        }

        changed_identity = ingress_profile_identity(
            acquisition=EXPECTED_ACQUISITION,
            policy_revision=POLICY_REVISION,
            observation_request=IngressChecker.request,
            resource_limits=changed_resources,
        )

        assert changed_identity.digest != INGRESS_PROFILE_IDENTITY.digest

    def test_root_profile_identity_binds_exact_webhook_fixtures(self) -> None:
        changed_identity = hamsterdan_profile_identity(
            original_webhook_fixture_digest=f"sha256:{'f' * 64}",
            collision_webhook_fixture_digest=COLLISION_WEBHOOK_FIXTURE_DIGEST,
            staging_policy_revision=STAGING_POLICY_REVISION,
            ingress_profile_identity=INGRESS_PROFILE_IDENTITY,
            readiness_profile_identity=READINESS_PROFILE_IDENTITY,
            resource_limits=ROOT_RESOURCE_LIMITS,
        )

        assert changed_identity.digest != ROOT_PROFILE_IDENTITY.digest

    def test_root_profile_identity_binds_staging_policy(self) -> None:
        changed_identity = hamsterdan_profile_identity(
            original_webhook_fixture_digest=ORIGINAL_WEBHOOK_FIXTURE_DIGEST,
            collision_webhook_fixture_digest=COLLISION_WEBHOOK_FIXTURE_DIGEST,
            staging_policy_revision=PolicyRevision("policy:mutated"),
            ingress_profile_identity=INGRESS_PROFILE_IDENTITY,
            readiness_profile_identity=READINESS_PROFILE_IDENTITY,
            resource_limits=ROOT_RESOURCE_LIMITS,
        )

        assert changed_identity.digest != ROOT_PROFILE_IDENTITY.digest

    def test_root_profile_identity_binds_delegated_owner_profiles(self) -> None:
        changed_ingress_identity = INGRESS_PROFILE_IDENTITY.model_copy(update={"digest": f"sha256:{'f' * 64}"})

        changed_identity = hamsterdan_profile_identity(
            original_webhook_fixture_digest=ORIGINAL_WEBHOOK_FIXTURE_DIGEST,
            collision_webhook_fixture_digest=COLLISION_WEBHOOK_FIXTURE_DIGEST,
            staging_policy_revision=STAGING_POLICY_REVISION,
            ingress_profile_identity=changed_ingress_identity,
            readiness_profile_identity=READINESS_PROFILE_IDENTITY,
            resource_limits=ROOT_RESOURCE_LIMITS,
        )

        assert changed_identity.digest != ROOT_PROFILE_IDENTITY.digest

    def test_root_profile_identity_binds_one_resource_gauge(self) -> None:
        changed_resources = {
            **ROOT_RESOURCE_LIMITS,
            "retained.readiness.ingress.database_pages": ROOT_RESOURCE_LIMITS[
                "retained.readiness.ingress.database_pages"
            ]
            - 1,
        }

        changed_identity = hamsterdan_profile_identity(
            original_webhook_fixture_digest=ORIGINAL_WEBHOOK_FIXTURE_DIGEST,
            collision_webhook_fixture_digest=COLLISION_WEBHOOK_FIXTURE_DIGEST,
            staging_policy_revision=STAGING_POLICY_REVISION,
            ingress_profile_identity=INGRESS_PROFILE_IDENTITY,
            readiness_profile_identity=READINESS_PROFILE_IDENTITY,
            resource_limits=changed_resources,
        )

        assert changed_identity.digest != ROOT_PROFILE_IDENTITY.digest


class TestWebhookCheckerSensitivity:
    """The independent root checker rejects delivery identity, route, and content mutations."""

    def test_root_checker_identity_binds_the_ingress_checker_identity(self) -> None:
        changed_ingress_identity = CheckerIdentity(
            name=IngressChecker.identity.name,
            version=IngressChecker.identity.version,
            digest=f"sha256:{'f' * 64}",
        )

        changed_root_identity = hamsterdan_checker_identity(
            ingress_checker_identity=changed_ingress_identity,
            readiness_checker_identity=ReadinessChecker.identity,
        )

        assert changed_root_identity.digest != HamsterdanChecker.identity.digest

    def test_root_checker_identity_binds_the_readiness_checker_identity(self) -> None:
        changed_readiness_identity = CheckerIdentity(
            name=ReadinessChecker.identity.name,
            version=ReadinessChecker.identity.version,
            digest=f"sha256:{'f' * 64}",
        )

        changed_root_identity = hamsterdan_checker_identity(
            ingress_checker_identity=IngressChecker.identity,
            readiness_checker_identity=changed_readiness_identity,
        )

        assert changed_root_identity.digest != HamsterdanChecker.identity.digest

    @pytest.mark.parametrize(
        ("path", "replacement"),
        [
            pytest.param(
                ("readiness", "binding", "bridge_identity"),
                "workflow-bridge/mutated@1",
                id="bridge",
            ),
            pytest.param(
                ("ingress", "posture", "manifest", "manifest_id"),
                f"manifest:v1:sha256:{'f' * 64}",
                id="manifest",
            ),
            pytest.param(
                ("ingress", "posture", "grant", "grant_id"),
                f"grant:v1:sha256:{'f' * 64}",
                id="grant",
            ),
            pytest.param(
                ("ingress", "posture", "decisions", 0, "entry_order"),
                1,
                id="entry-order",
            ),
            pytest.param(
                ("ingress", "posture", "manifest", "entries", 0, "observation_key"),
                f"obs:v1:sha256:{'f' * 64}",
                id="entry-key",
            ),
            pytest.param(("readiness", "delivery", "source"), "on_mutated", id="source"),
            pytest.param(("readiness", "delivery", "token_color"), "Mutated", id="token-color"),
            pytest.param(
                ("readiness", "delivery", "token_payload", "head"),
                "c" * 40,
                id="token-head",
            ),
            pytest.param(
                ("readiness", "delivery", "token_payload", "base"),
                "c" * 40,
                id="token-base",
            ),
            pytest.param(
                ("readiness", "delivery", "token_payload", "mergeable"),
                True,
                id="token-mergeable",
            ),
            pytest.param(
                ("readiness", "delivery", "token_payload", "policy"),
                "policy:mutated",
                id="token-policy",
            ),
            pytest.param(
                ("readiness", "delivery", "token_payload", "strict_base"),
                False,
                id="token-strict-base",
            ),
            pytest.param(
                ("readiness", "delivery", "token_payload", "base_current"),
                True,
                id="token-base-current",
            ),
            pytest.param(
                ("readiness", "delivery", "delivery_identity"),
                f"history-delivery:v1:sha256:{'f' * 64}",
                id="history-identity",
            ),
            pytest.param(("readiness", "delivery", "occurrence"), 2, id="occurrence"),
            pytest.param(
                ("readiness", "in_flight_occurrences"),
                2,
                id="in-flight-occurrences",
            ),
            pytest.param(("readiness", "staging"), None, id="missing-readiness-staging"),
            pytest.param(
                ("readiness", "delivery", "record_order"),
                ["FiringBegun", "ExternalEventDelivered"],
                id="record-order",
            ),
            pytest.param(("readiness", "accepted"), False, id="accepted"),
            pytest.param(("readiness", "folded"), True, id="folded"),
        ],
    )
    def test_root_checker_independently_rejects_changed_history_acceptance(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        path: tuple[str | int, ...],
        replacement: JsonValue,
    ) -> None:
        value = accepted_state(tmp_path)
        replace_path_value(value, path, replacement)

        def accept_readiness(checker: ReadinessChecker, observation: Observation) -> CheckResult:
            del checker, observation
            return CheckResult(passed=True, detail={})

        def accept_ingress(checker: IngressChecker, observation: Observation) -> CheckResult:
            del checker, observation
            return CheckResult(
                passed=True,
                detail={
                    "acquisition": True,
                    "manifest": True,
                    "entry_order": True,
                    "key": True,
                    "canonical_bytes": True,
                    "observation": True,
                    "grant": True,
                    "decision": True,
                    "acquisition_bytes": True,
                    "resources": True,
                },
            )

        monkeypatch.setattr(ReadinessChecker, "check", accept_readiness)
        monkeypatch.setattr(IngressChecker, "check", accept_ingress)

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["history_acceptance"] is False

    @pytest.mark.parametrize(
        ("path", "replacement"),
        [
            pytest.param(("readiness", "history_records"), 24, id="record-count"),
            pytest.param(("readiness", "in_flight_occurrences"), 1, id="unfinished-remains"),
            pytest.param(
                ("readiness", "delivery", "record_order"),
                ["ExternalEventDelivered", "FiringBegun", "FiringCompleted", "TokensProduced"],
                id="terminal-order",
            ),
            pytest.param(("readiness", "delivery", "produced_place"), "life.other", id="produced-place"),
            pytest.param(("readiness", "delivery", "produced_entries"), [None], id="produced-entries"),
            pytest.param(
                ("readiness", "delivery", "produced_tokens", 0, "color"),
                "Mutated",
                id="produced-color",
            ),
            pytest.param(
                ("readiness", "delivery", "produced_tokens", 0, "data", "head"),
                "c" * 40,
                id="produced-token",
            ),
            pytest.param(
                ("readiness", "delivery", "completed_transition"),
                "on_mutated",
                id="completed-transition",
            ),
            pytest.param(("readiness", "delivery", "folded"), False, id="delivery-folded"),
            pytest.param(("readiness", "folded"), False, id="readiness-folded"),
            pytest.param(
                ("readiness", "fold_posture", "subject", "installation_id"),
                45,
                id="posture-subject",
            ),
            pytest.param(
                ("readiness", "fold_posture", "instance_id"),
                "github:45:31:pr:7",
                id="posture-instance",
            ),
            pytest.param(
                ("readiness", "fold_posture", "bridge_identity"),
                "workflow-bridge/mutated@3",
                id="posture-bridge",
            ),
            pytest.param(
                ("readiness", "fold_posture", "manifest_id"),
                f"manifest:v1:sha256:{'f' * 64}",
                id="posture-manifest",
            ),
            pytest.param(
                ("readiness", "fold_posture", "grant_id"),
                f"grant:v1:sha256:{'f' * 64}",
                id="posture-grant",
            ),
            pytest.param(
                ("readiness", "fold_posture", "manifest_digest"),
                "f" * 64,
                id="posture-manifest-digest",
            ),
            pytest.param(("readiness", "fold_posture", "entry_order"), 1, id="posture-entry"),
            pytest.param(
                ("readiness", "fold_posture", "observation_key"),
                f"obs:v1:sha256:{'f' * 64}",
                id="posture-key",
            ),
            pytest.param(
                ("readiness", "fold_posture", "delivery_identity"),
                f"history-delivery:v1:sha256:{'f' * 64}",
                id="posture-delivery",
            ),
            pytest.param(("readiness", "fold_posture", "occurrence"), 2, id="posture-occurrence"),
            pytest.param(("readiness", "fold_posture", "phase"), "stopped", id="posture-phase"),
            pytest.param(("readiness", "fold_posture", "local_incarnation"), 2, id="posture-incarnation"),
            pytest.param(("readiness", "fold_posture", "head", "repository_id"), 33, id="posture-head-repository"),
            pytest.param(("readiness", "fold_posture", "head", "ref"), "mutated", id="posture-head-ref"),
            pytest.param(("readiness", "fold_posture", "head", "sha"), "c" * 40, id="posture-head-sha"),
            pytest.param(("readiness", "fold_posture", "base", "repository_id"), 33, id="posture-base-repository"),
            pytest.param(("readiness", "fold_posture", "base", "ref"), "mutated", id="posture-base-ref"),
            pytest.param(("readiness", "fold_posture", "base", "sha"), "c" * 40, id="posture-base-sha"),
            pytest.param(("readiness", "fold_posture", "mergeable"), True, id="posture-mergeable"),
            pytest.param(
                ("readiness", "fold_posture", "policy_revision"),
                "policy:mutated",
                id="posture-policy",
            ),
            pytest.param(("readiness", "fold_posture", "strict_base"), False, id="posture-strict-base"),
            pytest.param(("readiness", "fold_posture", "base_current"), True, id="posture-base-current"),
            pytest.param(("readiness", "fold_posture", "finished"), False, id="posture-finished"),
            pytest.param(("readiness", "fold_posture", "folded"), False, id="posture-folded"),
            pytest.param(("readiness", "fold_posture", "cut"), "mutated", id="posture-cut"),
        ],
    )
    def test_readiness_checker_rejects_each_changed_terminal_or_fold_projection_field(
        self,
        tmp_path: Path,
        path: tuple[str | int, ...],
        replacement: JsonValue,
    ) -> None:
        value = folded_state(tmp_path)
        replace_path_value(value, path, replacement)
        readiness = cast("dict[str, JsonValue]", value["readiness"])

        try:
            result = ReadinessChecker().check(checker_observation(readiness))
        except ValueError:
            return

        assert not result.passed

    @pytest.mark.parametrize(
        ("path", "replacement"),
        [
            pytest.param(("delivery", "completion_rows"), 2, id="row-count"),
            pytest.param(
                ("delivery", "completion", "provider_route_id"),
                "github:mutated",
                id="provider-route",
            ),
            pytest.param(
                ("delivery", "completion", "delivery_id"),
                "22222222-2222-4222-8222-222222222222",
                id="delivery",
            ),
            pytest.param(("delivery", "completion", "custody_generation"), 2, id="generation"),
            pytest.param(
                ("delivery", "completion", "subject", "repository_id"),
                32,
                id="subject",
            ),
            pytest.param(
                ("delivery", "completion", "instance_id"),
                "github:44:32:pr:7",
                id="instance",
            ),
            pytest.param(
                ("delivery", "completion", "bridge_identity"),
                "workflow-bridge/mutated@3",
                id="bridge",
            ),
            pytest.param(
                ("delivery", "completion", "manifest_id"),
                f"manifest:v1:sha256:{'f' * 64}",
                id="manifest",
            ),
            pytest.param(
                ("delivery", "completion", "grant_id"),
                f"grant:v1:sha256:{'f' * 64}",
                id="grant",
            ),
            pytest.param(
                ("delivery", "completion", "manifest_digest"),
                "f" * 64,
                id="manifest-digest",
            ),
            pytest.param(("delivery", "completion", "entry_order"), 1, id="entry"),
            pytest.param(
                ("delivery", "completion", "observation_key"),
                f"obs:v1:sha256:{'f' * 64}",
                id="key",
            ),
            pytest.param(
                ("delivery", "completion", "history_delivery_identity"),
                f"history-delivery:v1:sha256:{'f' * 64}",
                id="history-delivery",
            ),
            pytest.param(("delivery", "completion", "occurrence"), 2, id="occurrence"),
            pytest.param(
                ("delivery", "completion", "workflow_cut"),
                "mutated",
                id="workflow-cut",
            ),
            pytest.param(("delivery", "completion", "cut"), "mutated", id="completion-cut"),
            pytest.param(
                ("readiness", "fold_posture", "delivery_identity"),
                f"history-delivery:v1:sha256:{'f' * 64}",
                id="cross-owner-history",
            ),
            pytest.param(("readiness", "delivery", "occurrence"), 2, id="cross-owner-occurrence"),
        ],
    )
    def test_root_checker_rejects_each_changed_host_completion_correlation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        path: tuple[str | int, ...],
        replacement: JsonValue,
    ) -> None:
        value = completed_state(tmp_path)
        replace_path_value(value, path, replacement)

        def accept_readiness(checker: ReadinessChecker, observation: Observation) -> CheckResult:
            del checker, observation
            return CheckResult(passed=True, detail={})

        def accept_ingress(checker: IngressChecker, observation: Observation) -> CheckResult:
            del checker, observation
            return CheckResult(
                passed=True,
                detail={
                    "acquisition": True,
                    "manifest": True,
                    "entry_order": True,
                    "key": True,
                    "canonical_bytes": True,
                    "observation": True,
                    "grant": True,
                    "decision": True,
                    "acquisition_bytes": True,
                    "resources": True,
                },
            )

        monkeypatch.setattr(ReadinessChecker, "check", accept_readiness)
        monkeypatch.setattr(IngressChecker, "check", accept_ingress)

        try:
            result = HamsterdanChecker().check(checker_observation(value))
        except ValueError:
            return

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["host_completion"] is False

    def test_ingress_checker_identity_binds_the_resource_contract(self) -> None:
        changed_resources = {
            **INGRESS_RESOURCE_LIMITS,
            "retained.readiness.ingress.database_pages": INGRESS_RESOURCE_LIMITS[
                "retained.readiness.ingress.database_pages"
            ]
            - 1,
        }

        changed_identity = ingress_checker_identity(resource_limits=changed_resources)

        assert changed_identity.digest != IngressChecker.identity.digest

    def test_quarantined_ingress_checker_rejects_changed_reported_ceiling(self, tmp_path: Path) -> None:
        value = collision_staged_state(tmp_path)
        ingress = cast("dict[str, JsonValue]", value["ingress"])
        resources = cast("dict[str, JsonValue]", ingress["resources"])
        resources["maximum_manifests"] = 9_999

        result = IngressChecker().check(checker_observation(ingress))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["resources"] is False

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

    @pytest.mark.parametrize(
        ("path", "replacement", "detail"),
        [
            pytest.param(
                ("ingress", "acquisition", "custody_generation"),
                2,
                "ingress_delivery",
                id="acquisition-generation",
            ),
            pytest.param(
                ("ingress", "acquisition", "webhook", "snapshot", "provider_updated_at"),
                "2026-08-30T12:34:57Z",
                "ingress_delivery",
                id="acquisition-provider-time",
            ),
            pytest.param(
                ("ingress", "posture", "disposition"),
                "exact_duplicate",
                "ingress",
                id="disposition",
            ),
            pytest.param(
                ("ingress", "posture", "manifest", "acquisition", "provider_route_id"),
                "github:mutated",
                "ingress_acquisition",
                id="acquisition",
            ),
            pytest.param(
                ("ingress", "posture", "manifest", "manifest_id"),
                f"manifest:v1:sha256:{'f' * 64}",
                "ingress_manifest",
                id="manifest",
            ),
            pytest.param(
                ("ingress", "posture", "manifest", "entries", 0, "observation_key"),
                f"obs:v1:sha256:{'f' * 64}",
                "ingress_key",
                id="key",
            ),
            pytest.param(
                ("ingress", "posture", "manifest", "entries", 0, "canonical_bytes"),
                "{}",
                "ingress_bytes",
                id="bytes",
            ),
            pytest.param(
                ("ingress", "posture", "grant", "grant_id"),
                f"grant:v1:sha256:{'f' * 64}",
                "ingress_grant",
                id="grant",
            ),
            pytest.param(
                ("ingress", "posture", "decisions", 0),
                {
                    "entry_order": 0,
                    "observation_key": f"obs:v1:sha256:{'f' * 64}",
                    "disposition": "corroborating",
                    "reason": "same_semantics",
                    "fatal": False,
                    "refresh_required": False,
                },
                "ingress_decision",
                id="decision",
            ),
            pytest.param(
                ("ingress", "resources", "acquisition_bytes"),
                0,
                "ingress_acquisition_bytes",
                id="acquisition-bytes",
            ),
        ],
    )
    def test_changed_staging_authority_fails(
        self,
        tmp_path: Path,
        path: tuple[str | int, ...],
        replacement: JsonValue,
        detail: str,
    ) -> None:
        value = staged_state(tmp_path)
        target: object = value
        for part in path[:-1]:
            if isinstance(part, int):
                assert isinstance(target, list)
                target = target[part]
            else:
                assert isinstance(target, dict)
                target = target[part]
        final = path[-1]
        if isinstance(final, int):
            assert isinstance(target, list)
            target[final] = replacement
        else:
            assert isinstance(target, dict)
            target[final] = replacement

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)[detail] is False

    def test_added_ordered_staging_entry_fails(self, tmp_path: Path) -> None:
        value = staged_state(tmp_path)
        ingress = cast("dict[str, JsonValue]", value["ingress"])
        posture = cast("dict[str, JsonValue]", ingress["posture"])
        manifest = cast("dict[str, JsonValue]", posture["manifest"])
        entries = cast("list[JsonValue]", manifest["entries"])
        second = deepcopy(cast("dict[str, JsonValue]", entries[0]))
        second["order"] = 1
        second["observation_key"] = f"obs:v1:sha256:{'f' * 64}"
        entries.append(second)

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["ingress_entry_order"] is False

    def test_changed_quarantined_grant_fails(self, tmp_path: Path) -> None:
        value = collision_staged_state(tmp_path)
        ingress = cast("dict[str, JsonValue]", value["ingress"])
        posture = cast("dict[str, JsonValue]", ingress["posture"])
        grant = cast("dict[str, JsonValue]", posture["grant"])
        grant["manifest_digest"] = "f" * 64

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["ingress"] is False

    def test_quarantined_manifest_cannot_pair_with_eligible_delivery(self, tmp_path: Path) -> None:
        value = collision_staged_state(tmp_path)
        delivery = cast("dict[str, JsonValue]", value["delivery"])
        retained = cast("dict[str, JsonValue]", delivery["retained"])
        retained["quarantined"] = False

        result = HamsterdanChecker().check(checker_observation(value))

        assert not result.passed
        assert cast("dict[str, JsonValue]", result.detail)["ingress_delivery"] is False


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

    def test_staging_resource_samples_stay_within_declared_budgets(self, tmp_path: Path) -> None:
        world = build_hamsterdan_world(root=tmp_path)
        try:
            timeline = world.timeline()
            timeline.command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            timeline.command(
                "hamsterdan.stage_webhook",
                STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            timeline.finish(Disposition.QUIESCENT)
        finally:
            world.close()

        samples = [entry for entry in world.journal if entry.kind == "resource"]
        assert any(
            cast("dict[str, int]", cast("dict[str, JsonValue]", sample.value)["usage"])[
                "retained.readiness.ingress.manifests"
            ]
            == 1
            for sample in samples
        )
        assert all(
            cast("dict[str, int]", cast("dict[str, JsonValue]", sample.value)["usage"])[name]
            <= DEFAULT_BUDGET.profile_resources[name]
            for sample in samples
            for name in (
                "retained.readiness.ingress.manifests",
                "retained.readiness.ingress.entries",
                "retained.readiness.ingress.grants",
                "retained.readiness.ingress.decisions",
                "retained.readiness.ingress.acquisition_bytes",
                "retained.readiness.ingress.canonical_bytes",
                "retained.readiness.ingress.database_pages",
            )
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

    def test_zero_grant_budget_fails_when_staging_creates_the_first_grant(self, tmp_path: Path) -> None:
        resources = {
            **DEFAULT_BUDGET.profile_resources,
            "retained.readiness.ingress.grants": 0,
        }
        budget = DEFAULT_BUDGET.model_copy(update={"profile_resources": resources})
        world = build_hamsterdan_world(root=tmp_path, budget=budget)
        try:
            timeline = world.timeline()
            timeline.command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            with pytest.raises(BudgetExhausted) as raised:
                timeline.command(
                    "hamsterdan.stage_webhook",
                    STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
                )
        finally:
            world.close()

        assert raised.value.bound == "profile_resources:retained.readiness.ingress.grants"
        assert raised.value.limit == 0

    def test_zero_in_flight_budget_rejects_the_unfinished_acceptance(self, tmp_path: Path) -> None:
        resources = {
            **DEFAULT_BUDGET.profile_resources,
            "retained.readiness.in_flight_occurrences": 0,
        }
        budget = DEFAULT_BUDGET.model_copy(update={"profile_resources": resources})
        world = build_hamsterdan_world(root=tmp_path, budget=budget)
        try:
            timeline = world.timeline()
            timeline.command(
                "hamsterdan.open_pull_request",
                OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            )
            timeline.command(
                "hamsterdan.receive_webhook",
                RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            timeline.command(
                "hamsterdan.stage_webhook",
                STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            )
            with pytest.raises(BudgetExhausted) as raised:
                timeline.command(
                    "hamsterdan.accept_staged_observation",
                    ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
                )
        finally:
            world.close()

        assert raised.value.bound == "profile_resources:retained.readiness.in_flight_occurrences"
        assert raised.value.limit == 0

    def test_root_resource_observation_stops_at_the_fixed_file_ceiling(self, tmp_path: Path) -> None:
        for index in range(DEFAULT_BUDGET.profile_resources["retained.state.files"] + 1):
            (tmp_path / f"state-{index}").touch()

        with pytest.raises(RuntimeError) as raised:
            root_resource_usage(tmp_path)

        assert raised.value.args == (
            "state_file_capacity_exceeded",
            DEFAULT_BUDGET.profile_resources["retained.state.files"],
        )

    @pytest.mark.parametrize(
        ("table", "code"),
        [
            pytest.param("subject_roots", "host_subject_capacity_exceeded", id="subjects"),
            pytest.param("host_records", "host_record_capacity_exceeded", id="records"),
        ],
    )
    def test_root_catalog_observation_stops_at_one_row_per_authority(
        self,
        tmp_path: Path,
        table: str,
        code: str,
    ) -> None:
        with sqlite3.connect(tmp_path / "catalog.sqlite3") as connection:
            connection.executescript(
                """
                CREATE TABLE subject_roots (
                    installation_id, repository_id, pull_request_number, instance_id, readiness_root
                );
                CREATE TABLE host_records (
                    action_identity, installation_id, repository_id, pull_request_number,
                    action, posture, cut
                );
                INSERT INTO subject_roots VALUES (44, 31, 7, 'github:44:31:pr:7', 'instances/44/31/7');
                INSERT INTO host_records VALUES (
                    'trace:open:1', 44, 31, 7,
                    'open_pull_request', 'awaiting_observation', 'host_recorded'
                );
                """
            )
            if table == "subject_roots":
                connection.execute(
                    "INSERT INTO subject_roots VALUES (44, 31, 8, 'github:44:31:pr:8', 'instances/44/31/8')"
                )
            else:
                connection.execute(
                    """
                    INSERT INTO host_records VALUES (
                        'trace:open:2', 44, 31, 7,
                        'open_pull_request', 'awaiting_observation', 'host_recorded'
                    )
                    """
                )

        with pytest.raises(RuntimeError) as raised:
            host_state(tmp_path)

        assert raised.value.args == (code, 1)

    @pytest.mark.parametrize(
        ("table", "code"),
        [
            pytest.param("subject_roots", "invalid_host_subject_observation", id="subject"),
            pytest.param("host_records", "invalid_host_record_observation", id="record"),
        ],
    )
    def test_root_catalog_observation_rejects_oversized_singleton_values_without_echo(
        self,
        tmp_path: Path,
        table: str,
        code: str,
    ) -> None:
        sentinel = "stored-secret-must-not-escape-" + "x" * 128
        with sqlite3.connect(tmp_path / "catalog.sqlite3") as connection:
            connection.executescript(
                """
                CREATE TABLE subject_roots (
                    installation_id, repository_id, pull_request_number, instance_id, readiness_root
                );
                CREATE TABLE host_records (
                    action_identity, installation_id, repository_id, pull_request_number,
                    action, posture, cut
                );
                INSERT INTO subject_roots VALUES (44, 31, 7, 'github:44:31:pr:7', 'instances/44/31/7');
                INSERT INTO host_records VALUES (
                    'trace:open:1', 44, 31, 7,
                    'open_pull_request', 'awaiting_observation', 'host_recorded'
                );
                """
            )
            if table == "subject_roots":
                connection.execute("UPDATE subject_roots SET instance_id = ?", (sentinel,))
            else:
                connection.execute("UPDATE host_records SET action_identity = ?", (sentinel,))

        with pytest.raises(RuntimeError) as raised:
            host_state(tmp_path)

        assert raised.value.args == (code,)
        assert sentinel not in str(raised.value)

    def test_readiness_observation_rejects_duplicate_root_authority(self, tmp_path: Path) -> None:
        instance_root = tmp_path / "instance"
        instance_root.mkdir()
        with sqlite3.connect(instance_root / "readiness.sqlite3") as connection:
            connection.executescript(
                """
                CREATE TABLE root_binding (singleton, instance_id, bridge_identity);
                INSERT INTO root_binding VALUES (
                    1, 'github:44:31:pr:7', 'workflow-bridge/head-seen-history-fold@3'
                );
                INSERT INTO root_binding VALUES (
                    2, 'github:44:31:pr:8', 'workflow-bridge/head-seen-history-fold@3'
                );
                """
            )

        with pytest.raises(RuntimeError) as raised:
            readiness_state(instance_root, dispatch_path=tmp_path / "dispatch.sqlite3")

        assert raised.value.args == ("duplicate_root_binding_observation", 1)

    def test_readiness_observation_rejects_oversized_root_value_without_echo(self, tmp_path: Path) -> None:
        instance_root = tmp_path / "instance"
        instance_root.mkdir()
        sentinel = "stored-secret-must-not-escape-" + "x" * 128
        with sqlite3.connect(instance_root / "readiness.sqlite3") as connection:
            connection.executescript("CREATE TABLE root_binding (singleton, instance_id, bridge_identity)")
            connection.execute(
                "INSERT INTO root_binding VALUES (1, ?, 'workflow-bridge/head-seen-history-fold@3')",
                (sentinel,),
            )

        with pytest.raises(RuntimeError) as raised:
            readiness_state(instance_root, dispatch_path=tmp_path / "dispatch.sqlite3")

        assert raised.value.args == ("invalid_root_binding_observation",)
        assert sentinel not in str(raised.value)
