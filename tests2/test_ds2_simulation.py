# Copyright (c) 2026 Henrique Bastos

"""Deterministic owner-local and root evidence for signed webhook custody."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING, cast

from petrus.testing.dst import (
    BudgetExhausted,
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
    PROFILE_IDENTITY as READINESS_PROFILE_IDENTITY,
)
from hamsterdan2.readiness.simulation.lifecycle import ReadinessChecker, ReadinessState
from hamsterdan2.simulation.hamsterdan import (
    COLLIDE_WEBHOOK_COMMAND,
    COLLISION_WEBHOOK_FIXTURE_DIGEST,
    DEFAULT_BUDGET,
    EXPECTED_DELIVERY,
    EXPECTED_QUARANTINED_DELIVERY,
    ORIGINAL_WEBHOOK_FIXTURE_DIGEST,
    RECEIVE_WEBHOOK_COMMAND,
    STAGE_WEBHOOK_COMMAND,
    STAGING_POLICY_REVISION,
    HamsterdanChecker,
    build_hamsterdan_world,
    hamsterdan_checker_identity,
    hamsterdan_profile_identity,
    observe_hamsterdan,
    replay_hamsterdan,
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
        assert state.readiness == ReadinessState(binding=None, history_records=0)
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
        assert custody_only.readiness == ReadinessState(binding=None, history_records=0)
        assert staged.disposition == "applied"
        assert staged_value["disposition"] == "novel"
        assert state.ingress.posture is not None
        assert state.ingress.posture.disposition == "novel"
        assert state.ingress.resources.manifests == 1
        assert state.ingress.resources.entries == 1
        assert state.ingress.resources.grants == 1
        assert state.ingress.resources.decisions == 1
        assert state.readiness == ReadinessState(binding=None, history_records=0)
        assert not (record_root / "dispatch.sqlite3").exists()
        assert not list(record_root.rglob("history.sqlite3"))
        assert replayed.outcome == "pass"
        assert replayed.operations == len(artifact.operations)
        assert replayed.journal_digest == artifact.expected.journal_digest

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
