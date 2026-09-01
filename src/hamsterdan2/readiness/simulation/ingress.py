# Copyright (c) 2026 Henrique Bastos

"""Owner-local deterministic staging and replay of one retained acquisition."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal, cast

from petrus.testing.dst import (
    ApplyResult,
    BudgetV4,
    CheckResult,
    CheckerIdentity,
    Command,
    Fault,
    GenerationStart,
    Observation,
    ObservationRequest,
    ProfileIdentity,
    ReplayResult,
    ResourceUsage,
    ScenarioArtifact,
    ScenarioArtifactV3,
    ScenarioContext,
    ScenarioRegistry,
    World,
    digest_json,
    replay,
)
from pydantic import BaseModel, ConfigDict

from hamsterdan2.github_app.models import ProviderRouteId
from hamsterdan2.github_app.simulation.webhooks import DELIVERY_ID, EXPECTED_WEBHOOK
from hamsterdan2.readiness.ingress import IngressCustody
from hamsterdan2.readiness.ingress_values import (
    MAX_ACQUISITION_BYTES,
    MAX_MANIFESTS,
    MAX_SQLITE_PAGES,
    AcquisitionIdentity,
    IngressResources,
    PolicyRevision,
    StagingAcquisition,
    StagingPosture,
)


if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from petrus.testing.dst import ScenarioProfile
    from pydantic import JsonValue


PROVIDER_ROUTE_ID = ProviderRouteId("github:primary")
POLICY_REVISION = PolicyRevision("policy:cv21-ds2-v1")
EXPECTED_KEY = "obs:v1:sha256:c0eb3728c5881baea0e4fa015ba1b64879720e7f8c55a8e92497b9957808aa6f"
EXPECTED_MANIFEST_ID = "manifest:v1:sha256:bc946a67c48abe9f572da277dc85b22d900f4cb3a271b4c2b2c25629e23c9ea2"
EXPECTED_GRANT_ID = "grant:v1:sha256:d5bdc4c1ddff288b16de9383c4783c992b8f75cb8176f31615d41d7b3ed1b735"
EXPECTED_GRANT_DIGEST = "d5bdc4c1ddff288b16de9383c4783c992b8f75cb8176f31615d41d7b3ed1b735"
EXPECTED_ACQUISITION_BYTES = 745
EXPECTED_COLLISION_GRANT_ID = "grant:v1:sha256:f097e649e61dab91f17a998789c72e7857482fc7c416384615669b807da4c820"
EXPECTED_COLLISION_GRANT_DIGEST = "f097e649e61dab91f17a998789c72e7857482fc7c416384615669b807da4c820"
EXPECTED_COLLISION_ACQUISITION_BYTES = 744
EXPECTED_CANONICAL_BYTES = (
    b'{"base":{"ref":"main","repository_id":31,"sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},'
    b'"draft":false,"family":"head","head":{"ref":"feature/custody","repository_id":32,'
    b'"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"lifecycle_state":"open","local_incarnation":1,'
    b'"mergeable":null,"merged":false,"subject":{"installation_id":44,"pull_request_number":7,'
    b'"repository_id":31},"version":1}'
)
EXPECTED_ACQUISITION = StagingAcquisition(
    identity=AcquisitionIdentity(
        provider_route_id=PROVIDER_ROUTE_ID,
        delivery_id=DELIVERY_ID,
    ),
    custody_generation=1,
    webhook=EXPECTED_WEBHOOK,
    quarantined=False,
)
EXPECTED_COLLISION_ACQUISITION = EXPECTED_ACQUISITION.model_copy(update={"quarantined": True})


class StageAcquisitionCommand(BaseModel):
    """Strict owner-local command for one exact retained acquisition."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["stage_acquisition"] = "stage_acquisition"


class IngressSimulationState(BaseModel):
    """Detached owner-local staging observation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    acquisition: StagingAcquisition | None
    posture: StagingPosture | None
    resources: IngressResources


STAGE_ACQUISITION_COMMAND = StageAcquisitionCommand()
INGRESS_OBSERVATION_REQUEST = ObservationRequest(name="readiness.ingress.state", payload={})
RESOURCE_LIMITS = {
    "retained.readiness.ingress.manifests": 1,
    "retained.readiness.ingress.entries": 1,
    "retained.readiness.ingress.grants": 1,
    "retained.readiness.ingress.decisions": 1,
    "retained.readiness.ingress.acquisition_bytes": 16_768,
    "retained.readiness.ingress.canonical_bytes": len(EXPECTED_CANONICAL_BYTES),
    "retained.readiness.ingress.database_pages": MAX_SQLITE_PAGES,
}


def ingress_profile_identity(
    *,
    acquisition: StagingAcquisition,
    policy_revision: PolicyRevision,
    observation_request: ObservationRequest,
    resource_limits: Mapping[str, int],
) -> ProfileIdentity:
    return ProfileIdentity(
        name="hamsterdan2.readiness.ds2.ingress",
        version=1,
        digest=digest_json(
            {
                "command": STAGE_ACQUISITION_COMMAND.model_dump(mode="json"),
                "acquisition": acquisition.model_dump(mode="json"),
                "policy_revision": str(policy_revision),
                "observation": observation_request.model_dump(mode="json"),
                "fault_policy": "reject_all",
                "dispositions": [
                    "exact_duplicate",
                    "acquisition_collision",
                    "novel",
                    "corroborating",
                    "stale",
                    "semantic_collision",
                    "conflicting",
                    "incomparable",
                ],
                "resources": dict(resource_limits),
            }
        ),
    )


PROFILE_IDENTITY = ingress_profile_identity(
    acquisition=EXPECTED_ACQUISITION,
    policy_revision=POLICY_REVISION,
    observation_request=INGRESS_OBSERVATION_REQUEST,
    resource_limits=RESOURCE_LIMITS,
)


def ingress_checker_identity(*, resource_limits: Mapping[str, int]) -> CheckerIdentity:
    return CheckerIdentity(
        name="hamsterdan2.readiness.ds2.ingress-checker",
        version=1,
        digest=digest_json(
            {
                "manifest": EXPECTED_MANIFEST_ID,
                "disposition": "novel",
                "key": EXPECTED_KEY,
                "canonical_bytes": EXPECTED_CANONICAL_BYTES.decode(),
                "acquisition_bytes": EXPECTED_ACQUISITION_BYTES,
                "acquisitions": {
                    "eligible": EXPECTED_ACQUISITION.model_dump(mode="json"),
                    "collision": EXPECTED_COLLISION_ACQUISITION.model_dump(mode="json"),
                },
                "policy_revision": str(POLICY_REVISION),
                "observation_request": INGRESS_OBSERVATION_REQUEST.model_dump(mode="json"),
                "grant": {
                    "grant_id": EXPECTED_GRANT_ID,
                    "manifest_id": EXPECTED_MANIFEST_ID,
                    "manifest_digest": EXPECTED_GRANT_DIGEST,
                },
                "decision": {
                    "entry_order": 0,
                    "observation_key": EXPECTED_KEY,
                    "disposition": "novel",
                    "reason": "first_observation",
                    "fatal": False,
                    "refresh_required": False,
                },
                "acquisition_collision": {
                    "manifest": EXPECTED_MANIFEST_ID,
                    "entries": 0,
                    "acquisition_bytes": EXPECTED_COLLISION_ACQUISITION_BYTES,
                    "grant": {
                        "grant_id": EXPECTED_COLLISION_GRANT_ID,
                        "manifest_id": EXPECTED_MANIFEST_ID,
                        "manifest_digest": EXPECTED_COLLISION_GRANT_DIGEST,
                    },
                    "decision": {
                        "entry_order": None,
                        "observation_key": None,
                        "disposition": "acquisition_collision",
                        "reason": "quarantined_acquisition",
                        "fatal": True,
                        "refresh_required": False,
                    },
                },
                "resources": {
                    "profile_limits": dict(resource_limits),
                    "reported_ceilings": {
                        "manifests": MAX_MANIFESTS,
                        "acquisition_bytes": MAX_MANIFESTS * MAX_ACQUISITION_BYTES,
                        "database_pages": MAX_SQLITE_PAGES,
                    },
                    "staged": {
                        "rows": {"manifests": 1, "entries": 1, "grants": 1, "decisions": 1},
                        "acquisition_bytes": EXPECTED_ACQUISITION_BYTES,
                        "canonical_bytes": len(EXPECTED_CANONICAL_BYTES),
                        "database_pages": "1..maximum",
                    },
                    "acquisition_collision": {
                        "rows": {"manifests": 1, "entries": 0, "grants": 1, "decisions": 1},
                        "acquisition_bytes": EXPECTED_COLLISION_ACQUISITION_BYTES,
                        "canonical_bytes": 0,
                        "database_pages": "1..maximum",
                    },
                    "empty": {
                        "rows_and_bytes": 0,
                        "database_pages": "0..maximum",
                    },
                },
            }
        ),
    )


CHECKER_IDENTITY = ingress_checker_identity(resource_limits=RESOURCE_LIMITS)
DEFAULT_BUDGET = BudgetV4(
    actions=4,
    queued_commands=1,
    timer_advances=0,
    logical_instant=0,
    reloads=1,
    predicate_polls=1,
    artifact_bytes=65_536,
    profile_resources=RESOURCE_LIMITS,
)


def start_ingress(root: Path) -> GenerationStart[IngressCustody]:
    root.mkdir(parents=True, exist_ok=True)
    return GenerationStart(
        IngressCustody.from_path(
            path=root / "ingress.sqlite3",
            policy_revision=POLICY_REVISION,
        )
    )


def observe_ingress(root: Path) -> IngressSimulationState:
    custody = start_ingress(root).generation
    return IngressSimulationState(
        acquisition=custody.staging_acquisition(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        ),
        posture=custody.staging_posture(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        ),
        resources=custody.resources(),
    )


def ingress_resource_usage(root: Path) -> ResourceUsage:
    resources = observe_ingress(root).resources
    return ResourceUsage(
        values={
            "retained.readiness.ingress.manifests": resources.manifests,
            "retained.readiness.ingress.entries": resources.entries,
            "retained.readiness.ingress.grants": resources.grants,
            "retained.readiness.ingress.decisions": resources.decisions,
            "retained.readiness.ingress.acquisition_bytes": resources.acquisition_bytes,
            "retained.readiness.ingress.canonical_bytes": resources.canonical_bytes,
            "retained.readiness.ingress.database_pages": resources.database_pages,
        }
    )


class IngressScenarioProfile:
    """Petrus profile over real readiness-owned ingress custody."""

    identity = PROFILE_IDENTITY

    def __init__(self, root: Path) -> None:
        self._root = root

    def validate(self, command: Command) -> Command:
        if command.name != "readiness.stage_acquisition":
            raise ValueError("DS2 ingress accepts only 'readiness.stage_acquisition'")
        parsed = StageAcquisitionCommand.model_validate(command.payload, strict=True)
        if parsed != STAGE_ACQUISITION_COMMAND or parsed.model_dump(mode="json") != command.payload:
            raise ValueError("DS2 ingress command must contain exactly the admitted fields")
        return command

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"DS2 ingress admits no faults; remove {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[IngressCustody]:
        del context
        return start_ingress(self._root)

    def load(self, context: ScenarioContext) -> GenerationStart[IngressCustody]:
        return self.create(context)

    def apply(
        self,
        generation: IngressCustody,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del command, context
        posture = generation.stage(
            provider_route_id=EXPECTED_ACQUISITION.identity.provider_route_id,
            custody_generation=EXPECTED_ACQUISITION.custody_generation,
            webhook=EXPECTED_ACQUISITION.webhook,
            quarantined=EXPECTED_ACQUISITION.quarantined,
        )
        return ApplyResult(
            disposition="idempotent" if posture.disposition == "exact_duplicate" else "applied",
            value=posture.model_dump(mode="json"),
            scheduled=[],
        )

    def observe(
        self,
        generation: IngressCustody,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del generation, context
        if request != INGRESS_OBSERVATION_REQUEST:
            raise ValueError("DS2 ingress exposes only parameterless 'readiness.ingress.state'")
        return cast("JsonValue", observe_ingress(self._root).model_dump(mode="json"))

    def resource_usage(self, generation: IngressCustody | None) -> ResourceUsage:
        del generation
        return ingress_resource_usage(self._root)

    def drop(self, generation: IngressCustody) -> None:
        del generation

    def close(self, generation: IngressCustody) -> None:
        del generation


class IngressChecker:
    """Check fixed staging authority independently of projection and key code."""

    identity = CHECKER_IDENTITY
    request = INGRESS_OBSERVATION_REQUEST

    def check(self, observation: Observation) -> CheckResult:
        state = IngressSimulationState.model_validate_json(json.dumps(observation.value), strict=True)
        posture = state.posture
        entry = None if posture is None or len(posture.manifest.entries) != 1 else posture.manifest.entries[0]
        acquisition_evidence = state.acquisition == EXPECTED_ACQUISITION
        collision_acquisition_evidence = state.acquisition == EXPECTED_COLLISION_ACQUISITION
        disposition = posture is not None and posture.disposition == "novel"
        collision_disposition = posture is not None and posture.disposition == "acquisition_collision"
        manifest = posture is not None and str(posture.manifest.manifest_id) == EXPECTED_MANIFEST_ID
        acquisition = posture is not None and (
            posture.manifest.acquisition.provider_route_id == PROVIDER_ROUTE_ID
            and posture.manifest.acquisition.delivery_id == DELIVERY_ID
        )
        manifest = manifest and posture.manifest.policy_revision == POLICY_REVISION
        key = entry is not None and str(entry.observation_key) == EXPECTED_KEY
        canonical_bytes = entry is not None and bytes(entry.canonical_bytes) == EXPECTED_CANONICAL_BYTES
        entry_order = entry is not None and entry.order == 0
        observation_value = json.loads(EXPECTED_CANONICAL_BYTES)
        observation_matches = entry is not None and entry.observation.model_dump(mode="json") == observation_value
        grant = posture is not None and posture.grant.model_dump(mode="json") == {
            "grant_id": EXPECTED_GRANT_ID,
            "manifest_id": EXPECTED_MANIFEST_ID,
            "manifest_digest": EXPECTED_GRANT_DIGEST,
        }
        collision_grant = posture is not None and posture.grant.model_dump(mode="json") == {
            "grant_id": EXPECTED_COLLISION_GRANT_ID,
            "manifest_id": EXPECTED_MANIFEST_ID,
            "manifest_digest": EXPECTED_COLLISION_GRANT_DIGEST,
        }
        decision = (
            posture is not None
            and len(posture.decisions) == 1
            and posture.decisions[0].model_dump(mode="json")
            == {
                "entry_order": 0,
                "observation_key": EXPECTED_KEY,
                "disposition": "novel",
                "reason": "first_observation",
                "fatal": False,
                "refresh_required": False,
            }
        )
        collision_decision = (
            posture is not None
            and len(posture.decisions) == 1
            and posture.decisions[0].model_dump(mode="json")
            == {
                "entry_order": None,
                "observation_key": None,
                "disposition": "acquisition_collision",
                "reason": "quarantined_acquisition",
                "fatal": True,
                "refresh_required": False,
            }
        )
        resource_limits = (
            state.resources.maximum_manifests == MAX_MANIFESTS
            and state.resources.maximum_acquisition_bytes == MAX_MANIFESTS * MAX_ACQUISITION_BYTES
            and state.resources.maximum_database_pages == MAX_SQLITE_PAGES
            and state.resources.database_pages <= MAX_SQLITE_PAGES
        )
        acquisition_bytes = state.resources.acquisition_bytes == EXPECTED_ACQUISITION_BYTES
        collision_acquisition_bytes = state.resources.acquisition_bytes == EXPECTED_COLLISION_ACQUISITION_BYTES
        staged_resources = (
            state.resources.manifests
            == state.resources.entries
            == state.resources.grants
            == state.resources.decisions
            == 1
            and acquisition_bytes
            and state.resources.canonical_bytes == RESOURCE_LIMITS["retained.readiness.ingress.canonical_bytes"]
            and state.resources.database_pages > 0
        )
        collision_resources = (
            state.resources.manifests == state.resources.grants == state.resources.decisions == 1
            and state.resources.entries == 0
            and collision_acquisition_bytes
            and state.resources.canonical_bytes == 0
            and state.resources.database_pages > 0
        )
        empty_resources = (
            state.resources.manifests
            == state.resources.entries
            == state.resources.grants
            == state.resources.decisions
            == state.resources.acquisition_bytes
            == state.resources.canonical_bytes
            == 0
        )
        resources = resource_limits and (staged_resources or collision_resources or empty_resources)
        empty = posture is None and empty_resources and resource_limits
        collision = all(
            (
                collision_disposition,
                collision_acquisition_evidence,
                manifest,
                acquisition,
                posture is not None and posture.manifest.entries == (),
                collision_grant,
                collision_decision,
                collision_resources,
                resource_limits,
            )
        )
        empty = empty and state.acquisition is None
        return CheckResult(
            passed=empty
            or collision
            or all(
                (
                    disposition,
                    acquisition_evidence,
                    manifest,
                    acquisition,
                    key,
                    canonical_bytes,
                    entry_order,
                    observation_matches,
                    grant,
                    decision,
                    resources,
                )
            ),
            detail={
                "empty": empty,
                "disposition": disposition or collision_disposition,
                "acquisition_evidence": acquisition_evidence or collision_acquisition_evidence,
                "manifest": manifest,
                "acquisition": acquisition,
                "key": key,
                "canonical_bytes": canonical_bytes,
                "entry_order": entry_order,
                "observation": observation_matches,
                "grant": grant or collision_grant,
                "decision": decision or collision_decision,
                "acquisition_bytes": acquisition_bytes or collision_acquisition_bytes,
                "resources": resources,
            },
        )


def build_ingress_world(*, root: Path, budget: BudgetV4 = DEFAULT_BUDGET) -> World:
    profile = cast("ScenarioProfile[object]", IngressScenarioProfile(root))
    return World(profile, budget, checkers=(IngressChecker(),))


def replay_ingress(artifact: ScenarioArtifactV3 | ScenarioArtifact, *, root: Path) -> ReplayResult:
    if not isinstance(artifact, ScenarioArtifact):
        raise TypeError("DS2 ingress replay requires a version-4 resource artifact")
    registry = ScenarioRegistry()
    registry.register_profile(IngressScenarioProfile(root))
    registry.register_checker(IngressChecker())
    return cast("ReplayResult", replay(artifact, registry))
