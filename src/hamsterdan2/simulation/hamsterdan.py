# Copyright (c) 2026 Henrique Bastos

"""Root deterministic execution of the first bridged Hamsterdan lifecycle."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
import sqlite3
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
from starlette import status
from starlette.testclient import TestClient

from hamsterdan2.github_app.models import DeliveryId, PositiveIdentifier, ProviderRouteId, RepositoryFullName
from hamsterdan2.github_app.simulation.webhooks import (
    COLLIDING_HEAD_SHA,
    DELIVERY_ID,
    EXPECTED_WEBHOOK,
    ORIGINAL_HEAD_SHA,
    WEBHOOK_SIGNING_MATERIAL,
    signed_webhook_body,
    signed_webhook_headers,
)
from hamsterdan2.host.composition import (
    build_hamsterdan,
    build_observation_acceptance_authority,
    build_staging_authority,
    build_webhook_app,
)
from hamsterdan2.host.delivery import DeliveryCompletionCustody, DeliveryCustody
from hamsterdan2.host.values import (
    ActionIdentity,
    ConfiguredProviderRoute,
    CustodiedDelivery,
    DeliveryReceipt,
    HostDeliveryCompletionReceipt,
    HostRecord,
    OpenPullRequestCommand,
    RegisteredPullRequest,
)
from hamsterdan2.readiness.ingress_values import (
    MAX_ACQUISITION_BYTES,
    MAX_MANIFESTS,
    MAX_SQLITE_PAGES,
    AcquisitionIdentity,
    AdmissionDecision,
    AdmissionGrant,
    AdmissionGrantId,
    CanonicalObservation,
    HistoryAcceptancePosture,
    IngressEntry,
    IngressManifest,
    IngressResources,
    ManifestId,
    ObservationFoldPosture,
    ObservationKey,
    PolicyRevision,
    StagingAcquisition,
    StagingPosture,
)
from hamsterdan2.readiness.simulation.ingress import (
    PROFILE_IDENTITY as INGRESS_PROFILE_IDENTITY,
)
from hamsterdan2.readiness.simulation.ingress import IngressChecker
from hamsterdan2.readiness.simulation.lifecycle import (
    ACCEPTED_HISTORY_RECORDS,
    ACCEPT_STAGED_OBSERVATION_COMMAND,
    EXPECTED_BRIDGE_IDENTITY,
    EXPECTED_HEAD_SEEN_COLOR,
    FOLDED_HISTORY_RECORDS,
    FOLD_ACCEPTED_OBSERVATION_COMMAND,
    INSTANCE_ID,
    OPEN_HISTORY_RECORDS,
    SUBJECT,
    AcceptStagedObservationCommand,
    FoldAcceptedObservationCommand,
    ReadinessChecker,
    ReadinessState,
    SimulationCapacityError,
    bounded_state_storage,
    pending_dispatch_tasks,
    readiness_state,
)
from hamsterdan2.readiness.simulation.lifecycle import (
    PROFILE_IDENTITY as READINESS_PROFILE_IDENTITY,
)
from hamsterdan2.readiness.simulation.lifecycle import (
    RESOURCE_LIMITS as READINESS_RESOURCE_LIMITS,
)
from hamsterdan2.workflow.observations import BranchRef, BranchTip, CommitSha, HeadObservation
from hamsterdan2.workflow.values import AwaitingObservation, PullRequestSubject


if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from petrus.testing.dst import ScenarioProfile
    from pydantic import JsonValue

    from hamsterdan2.host.application import Hamsterdan


OPEN_PULL_REQUEST_COMMAND = OpenPullRequestCommand(
    action_identity=ActionIdentity("trace:open:1"),
    subject=SUBJECT,
)
EXPECTED_REGISTRATION = RegisteredPullRequest(
    subject=SUBJECT,
    instance_id=INSTANCE_ID,
    readiness_root="instances/44/31/7",
)
EXPECTED_RECORD = HostRecord(
    action_identity=OPEN_PULL_REQUEST_COMMAND.action_identity,
    posture=AwaitingObservation(subject=SUBJECT),
)
PROVIDER_ROUTE_ID = ProviderRouteId("github:primary")
PROVIDER_ROUTE = ConfiguredProviderRoute(
    provider_route_id=PROVIDER_ROUTE_ID,
    installation_id=PositiveIdentifier(44),
    repository_id=PositiveIdentifier(31),
    repository_full_name=RepositoryFullName("owner/repo"),
)


class ReceiveWebhookCommand(BaseModel):
    """Choose one exact signed request in the cumulative root tracer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    fixture: Literal["original", "collision"]
    action: Literal["receive_signed_webhook"] = "receive_signed_webhook"


class StageWebhookCommand(BaseModel):
    """Choose one retained acquisition for an authority-side staging turn."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_route_id: ProviderRouteId
    delivery_id: DeliveryId
    action: Literal["stage_retained_webhook"] = "stage_retained_webhook"


class CompleteObservationDeliveryCommand(BaseModel):
    """Choose one folded occurrence for separate host completion."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["complete_observation_delivery"] = "complete_observation_delivery"


RECEIVE_WEBHOOK_COMMAND = ReceiveWebhookCommand(fixture="original")
COLLIDE_WEBHOOK_COMMAND = ReceiveWebhookCommand(fixture="collision")
STAGE_WEBHOOK_COMMAND = StageWebhookCommand(
    provider_route_id=PROVIDER_ROUTE_ID,
    delivery_id=DELIVERY_ID,
)
COMPLETE_OBSERVATION_DELIVERY_COMMAND = CompleteObservationDeliveryCommand()
STAGING_POLICY_REVISION = PolicyRevision("policy:cv21-ds2-v1")
ROOT_OBSERVATION_REQUEST = ObservationRequest(name="hamsterdan.state", payload={})
ORIGINAL_WEBHOOK_FIXTURE_DIGEST = f"sha256:{sha256(signed_webhook_body(head_sha=ORIGINAL_HEAD_SHA)).hexdigest()}"
COLLISION_WEBHOOK_FIXTURE_DIGEST = f"sha256:{sha256(signed_webhook_body(head_sha=COLLIDING_HEAD_SHA)).hexdigest()}"
EXPECTED_DELIVERY = CustodiedDelivery(
    provider_route_id=PROVIDER_ROUTE_ID,
    custody_generation=1,
    webhook=EXPECTED_WEBHOOK,
    quarantined=False,
)
EXPECTED_QUARANTINED_DELIVERY = EXPECTED_DELIVERY.model_copy(update={"quarantined": True})
EXPECTED_STAGING_ACQUISITION = StagingAcquisition(
    identity=AcquisitionIdentity(
        provider_route_id=PROVIDER_ROUTE_ID,
        delivery_id=DELIVERY_ID,
    ),
    custody_generation=EXPECTED_DELIVERY.custody_generation,
    webhook=EXPECTED_DELIVERY.webhook,
    quarantined=False,
)
EXPECTED_COLLISION_ACQUISITION = EXPECTED_STAGING_ACQUISITION.model_copy(update={"quarantined": True})
EXPECTED_CANONICAL_HEAD = CanonicalObservation(
    b'{"base":{"ref":"main","repository_id":31,"sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},'
    b'"draft":false,"family":"head","head":{"ref":"feature/custody","repository_id":32,'
    b'"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"lifecycle_state":"open","local_incarnation":1,'
    b'"mergeable":null,"merged":false,"subject":{"installation_id":44,"pull_request_number":7,'
    b'"repository_id":31},"version":1}'
)
EXPECTED_OBSERVATION_KEY = ObservationKey(
    "obs:v1:sha256:c0eb3728c5881baea0e4fa015ba1b64879720e7f8c55a8e92497b9957808aa6f"
)
EXPECTED_MANIFEST_ID = ManifestId("manifest:v1:sha256:bc946a67c48abe9f572da277dc85b22d900f4cb3a271b4c2b2c25629e23c9ea2")
EXPECTED_GRANT_DIGEST = "d5bdc4c1ddff288b16de9383c4783c992b8f75cb8176f31615d41d7b3ed1b735"
EXPECTED_STAGING = StagingPosture(
    disposition="novel",
    manifest=IngressManifest(
        manifest_id=EXPECTED_MANIFEST_ID,
        acquisition=AcquisitionIdentity(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        ),
        policy_revision=STAGING_POLICY_REVISION,
        entries=(
            IngressEntry(
                order=0,
                observation_key=EXPECTED_OBSERVATION_KEY,
                canonical_bytes=EXPECTED_CANONICAL_HEAD,
                observation=HeadObservation(
                    subject=SUBJECT,
                    head=BranchTip(
                        repository_id=32,
                        ref=BranchRef("feature/custody"),
                        sha=CommitSha("a" * 40),
                    ),
                    base=BranchTip(
                        repository_id=31,
                        ref=BranchRef("main"),
                        sha=CommitSha("b" * 40),
                    ),
                    lifecycle_state="open",
                    draft=False,
                    merged=False,
                    mergeable=None,
                ),
            ),
        ),
    ),
    grant=AdmissionGrant(
        grant_id=AdmissionGrantId(f"grant:v1:sha256:{EXPECTED_GRANT_DIGEST}"),
        manifest_id=EXPECTED_MANIFEST_ID,
        manifest_digest=EXPECTED_GRANT_DIGEST,
    ),
    decisions=(
        AdmissionDecision(
            entry_order=0,
            observation_key=EXPECTED_OBSERVATION_KEY,
            disposition="novel",
            reason="first_observation",
            fatal=False,
            refresh_required=False,
        ),
    ),
)


class HostState(BaseModel):
    """Detached host-catalog observation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    subjects: list[RegisteredPullRequest]
    records: list[HostRecord]


class DeliveryState(BaseModel):
    """Detached durable webhook custody observation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    rows: int
    retained: CustodiedDelivery | None
    completion_rows: int = 0
    completion: HostDeliveryCompletionReceipt | None = None


class IngressState(BaseModel):
    """Detached source-neutral staging authority and finite retained usage."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    acquisition: StagingAcquisition | None
    posture: StagingPosture | None
    resources: IngressResources


class HamsterdanState(BaseModel):
    """Detached cross-owner observation for the cumulative root tracer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    host: HostState
    readiness: ReadinessState
    delivery: DeliveryState
    ingress: IngressState


def expected_history_delivery_identity(posture: StagingPosture) -> str | None:
    if len(posture.manifest.entries) != 1:
        return None
    entry = posture.manifest.entries[0]
    material = json.dumps(
        {
            "bridge_identity": EXPECTED_BRIDGE_IDENTITY,
            "entry_order": entry.order,
            "grant_id": str(posture.grant.grant_id),
            "manifest_digest": posture.grant.manifest_digest,
            "manifest_id": str(posture.manifest.manifest_id),
            "observation_key": str(entry.observation_key),
            "version": 1,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"history-delivery:v1:sha256:{sha256(material).hexdigest()}"


def history_acceptance_corresponds(state: HamsterdanState) -> bool:
    readiness = state.readiness
    delivery = readiness.delivery
    if readiness.staging != state.ingress.posture:
        return False
    if not readiness.accepted:
        return (
            delivery is None
            and readiness.history_records in (0, OPEN_HISTORY_RECORDS)
            and readiness.in_flight_occurrences == 0
            and not readiness.folded
        )
    posture = state.ingress.posture
    binding = readiness.binding
    if (
        posture is None
        or binding is None
        or delivery is None
        or len(posture.manifest.entries) != 1
        or len(posture.decisions) != 1
    ):
        return False
    entry = posture.manifest.entries[0]
    observation = entry.observation
    expected_payload = {
        "head": str(observation.head.sha),
        "base": str(observation.base.sha),
        "mergeable": observation.mergeable is True,
        "policy": str(posture.manifest.policy_revision),
        "strict_base": True,
        "base_current": False,
    }
    common = (
        posture == EXPECTED_STAGING
        and observation.subject == SUBJECT
        and binding.instance_id == INSTANCE_ID
        and binding.bridge_identity == EXPECTED_BRIDGE_IDENTITY
        and delivery.source == "on_head"
        and delivery.token_color == EXPECTED_HEAD_SEEN_COLOR
        and delivery.token_payload == expected_payload
        and delivery.delivery_identity == expected_history_delivery_identity(posture)
        and delivery.occurrence == 1
    )
    accepted = (
        readiness.history_records == ACCEPTED_HISTORY_RECORDS
        and readiness.in_flight_occurrences == 1
        and delivery.record_order == ("ExternalEventDelivered", "FiringBegun")
        and not delivery.folded
        and not readiness.folded
        and readiness.fold_posture is None
    )
    fold = readiness.fold_posture
    folded = (
        readiness.history_records == FOLDED_HISTORY_RECORDS
        and readiness.in_flight_occurrences == 0
        and delivery.record_order == ("ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted")
        and delivery.produced_place == "life.heads"
        and delivery.produced_entries == ()
        and delivery.produced_tokens is not None
        and len(delivery.produced_tokens) == 1
        and delivery.produced_tokens[0].color == delivery.token_color
        and delivery.produced_tokens[0].data == delivery.token_payload
        and delivery.completed_transition == delivery.source
        and delivery.folded
        and readiness.folded
        and fold is not None
        and fold.subject == observation.subject
        and fold.instance_id == binding.instance_id
        and fold.bridge_identity == binding.bridge_identity
        and fold.manifest_id == posture.manifest.manifest_id
        and fold.grant_id == posture.grant.grant_id
        and fold.manifest_digest == posture.grant.manifest_digest
        and fold.entry_order == entry.order
        and fold.observation_key == entry.observation_key
        and fold.delivery_identity == delivery.delivery_identity
        and fold.occurrence == delivery.occurrence
        and fold.phase == "running"
        and fold.local_incarnation == observation.local_incarnation
        and fold.head == observation.head
        and fold.base == observation.base
        and fold.mergeable == (observation.mergeable is True)
        and fold.policy_revision == posture.manifest.policy_revision
        and fold.strict_base
        and not fold.base_current
        and fold.finished
        and fold.folded
        and fold.cut == "observation_folded"
    )
    return common and (accepted or folded)


def hamsterdan_checker_identity(
    *,
    ingress_checker_identity: CheckerIdentity,
    readiness_checker_identity: CheckerIdentity,
) -> CheckerIdentity:
    return CheckerIdentity(
        name="hamsterdan2.cv21.root-checker",
        version=6,
        digest=digest_json(
            {
                "subject": SUBJECT.model_dump(mode="json"),
                "action_identity": str(OPEN_PULL_REQUEST_COMMAND.action_identity),
                "instance_identity": INSTANCE_ID,
                "bridge_identity": EXPECTED_BRIDGE_IDENTITY,
                "provider_route_identity": str(PROVIDER_ROUTE_ID),
                "delivery_identity": str(DELIVERY_ID),
                "delivery_content": EXPECTED_WEBHOOK.model_dump(mode="json"),
                "staging": EXPECTED_STAGING.model_dump(mode="json"),
                "staging_acquisitions": {
                    "eligible": EXPECTED_STAGING_ACQUISITION.model_dump(mode="json"),
                    "collision": EXPECTED_COLLISION_ACQUISITION.model_dump(mode="json"),
                },
                "history_acceptance": {
                    "bridge_identity": EXPECTED_BRIDGE_IDENTITY,
                    "source": "on_head",
                    "token": {
                        "color": EXPECTED_HEAD_SEEN_COLOR,
                        "payload": {
                            "head": "a" * 40,
                            "base": "b" * 40,
                            "mergeable": False,
                            "policy": str(STAGING_POLICY_REVISION),
                            "strict_base": True,
                            "base_current": False,
                        },
                    },
                    "delivery_identity": expected_history_delivery_identity(EXPECTED_STAGING),
                    "occurrence": 1,
                    "record_order": ["ExternalEventDelivered", "FiringBegun"],
                    "in_flight_occurrences": 1,
                    "finished": False,
                    "folded": False,
                },
                "history_fold": {
                    "record_order": [
                        "ExternalEventDelivered",
                        "FiringBegun",
                        "TokensProduced",
                        "FiringCompleted",
                    ],
                    "produced_place": "life.heads",
                    "history_records": FOLDED_HISTORY_RECORDS,
                    "in_flight_occurrences": 0,
                    "cut": "observation_folded",
                },
                "host_completion": {
                    "custody_generation": 1,
                    "history_delivery_identity": expected_history_delivery_identity(EXPECTED_STAGING),
                    "occurrence": 1,
                    "workflow_cut": "observation_folded",
                    "cut": "host_delivery_completed",
                },
                "ingress_checker": ingress_checker_identity.model_dump(mode="json"),
                "readiness_checker": readiness_checker_identity.model_dump(mode="json"),
                "phases": [
                    "empty",
                    "delivery_custodied",
                    "readiness_staged",
                    "history_accepted",
                    "observation_folded",
                    "host_delivery_completed",
                    "host_recorded",
                ],
                "relationships": "every retained phase identifies one PR",
            }
        ),
    )


CHECKER_IDENTITY = hamsterdan_checker_identity(
    ingress_checker_identity=IngressChecker.identity,
    readiness_checker_identity=ReadinessChecker.identity,
)
RESOURCE_LIMITS = {
    "pending.motus.tasks": 0,
    "retained.host.records": 1,
    "retained.host.subjects": 1,
    "retained.host.deliveries": 1,
    "retained.host.delivery_completions": 1,
    "retained.readiness.ingress.manifests": 1,
    "retained.readiness.ingress.entries": 1,
    "retained.readiness.ingress.grants": 1,
    "retained.readiness.ingress.decisions": 1,
    "retained.readiness.ingress.acquisition_bytes": MAX_ACQUISITION_BYTES,
    "retained.readiness.ingress.canonical_bytes": len(EXPECTED_CANONICAL_HEAD),
    "retained.readiness.ingress.database_pages": MAX_SQLITE_PAGES,
    "retained.readiness.history_records": READINESS_RESOURCE_LIMITS["retained.readiness.history_records"],
    "retained.readiness.in_flight_occurrences": READINESS_RESOURCE_LIMITS["retained.readiness.in_flight_occurrences"],
    "retained.state.bytes": 524_288,
    "retained.state.files": 7,
}


def hamsterdan_profile_identity(
    *,
    original_webhook_fixture_digest: str,
    collision_webhook_fixture_digest: str,
    staging_policy_revision: PolicyRevision,
    ingress_profile_identity: ProfileIdentity,
    readiness_profile_identity: ProfileIdentity,
    resource_limits: Mapping[str, int],
) -> ProfileIdentity:
    return ProfileIdentity(
        name="hamsterdan2.cv21",
        version=5,
        digest=digest_json(
            {
                "commands": [
                    OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
                    RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
                    COLLIDE_WEBHOOK_COMMAND.model_dump(mode="json"),
                    STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
                    ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
                    FOLD_ACCEPTED_OBSERVATION_COMMAND.model_dump(mode="json"),
                    COMPLETE_OBSERVATION_DELIVERY_COMMAND.model_dump(mode="json"),
                ],
                "webhook_fixtures": {
                    "original": original_webhook_fixture_digest,
                    "collision": collision_webhook_fixture_digest,
                },
                "staging_policy_revision": str(staging_policy_revision),
                "observation": ROOT_OBSERVATION_REQUEST.model_dump(mode="json"),
                "fault_policy": "reject_all",
                "owner_profiles": {
                    "ingress": ingress_profile_identity.model_dump(mode="json"),
                    "readiness": readiness_profile_identity.model_dump(mode="json"),
                },
                "cuts": [
                    "delivery_custodied",
                    "readiness_staged",
                    "history_accepted_unfinished",
                    "observation_folded",
                    "host_delivery_completed",
                    "host_recorded",
                ],
                "owners": ["github_app", "host", "readiness", "workflow_bridge"],
                "resources": dict(resource_limits),
            }
        ),
    )


PROFILE_IDENTITY = hamsterdan_profile_identity(
    original_webhook_fixture_digest=ORIGINAL_WEBHOOK_FIXTURE_DIGEST,
    collision_webhook_fixture_digest=COLLISION_WEBHOOK_FIXTURE_DIGEST,
    staging_policy_revision=STAGING_POLICY_REVISION,
    ingress_profile_identity=INGRESS_PROFILE_IDENTITY,
    readiness_profile_identity=READINESS_PROFILE_IDENTITY,
    resource_limits=RESOURCE_LIMITS,
)
DEFAULT_BUDGET = BudgetV4(
    actions=16,
    queued_commands=1,
    timer_advances=0,
    logical_instant=0,
    reloads=2,
    predicate_polls=1,
    artifact_bytes=262_144,
    profile_resources=RESOURCE_LIMITS,
)


def start_hamsterdan(root: Path) -> GenerationStart[Hamsterdan]:
    return GenerationStart(build_hamsterdan(state_root=root))


def observed_host_subjects(connection: sqlite3.Connection) -> list[RegisteredPullRequest]:
    rows = connection.execute(
        """
            SELECT CASE WHEN typeof(installation_id) = 'integer' AND installation_id > 0
                        THEN installation_id END AS installation_id,
                   CASE WHEN typeof(repository_id) = 'integer' AND repository_id > 0
                        THEN repository_id END AS repository_id,
                   CASE WHEN typeof(pull_request_number) = 'integer' AND pull_request_number > 0
                        THEN pull_request_number END AS pull_request_number,
                   CASE WHEN typeof(instance_id) = 'text'
                              AND length(CAST(instance_id AS BLOB)) BETWEEN 1 AND 128
                              AND instance_id = printf(
                                  'github:%d:%d:pr:%d', installation_id, repository_id, pull_request_number
                              )
                        THEN instance_id END AS instance_id,
                   CASE WHEN typeof(readiness_root) = 'text'
                              AND length(CAST(readiness_root AS BLOB)) BETWEEN 1 AND 128
                              AND readiness_root = printf(
                                  'instances/%d/%d/%d', installation_id, repository_id, pull_request_number
                              )
                        THEN readiness_root END AS readiness_root
            FROM subject_roots
            ORDER BY installation_id, repository_id, pull_request_number
            LIMIT ?
            """,
        (RESOURCE_LIMITS["retained.host.subjects"] + 1,),
    ).fetchall()
    if len(rows) > RESOURCE_LIMITS["retained.host.subjects"]:
        raise SimulationCapacityError(
            "host_subject_capacity_exceeded",
            RESOURCE_LIMITS["retained.host.subjects"],
        )
    if any(value is None for row in rows for value in row):
        raise SimulationCapacityError("invalid_host_subject_observation")
    return [
        RegisteredPullRequest(
            subject=PullRequestSubject(
                installation_id=row["installation_id"],
                repository_id=row["repository_id"],
                pull_request_number=row["pull_request_number"],
            ),
            instance_id=row["instance_id"],
            readiness_root=row["readiness_root"],
        )
        for row in rows
    ]


def observed_host_records(connection: sqlite3.Connection) -> list[HostRecord]:
    rows = connection.execute(
        """
            SELECT CASE WHEN typeof(action_identity) = 'text'
                              AND length(CAST(action_identity AS BLOB)) BETWEEN 1 AND 128
                              AND action_identity = ?
                        THEN action_identity END AS action_identity,
                   CASE WHEN typeof(installation_id) = 'integer' AND installation_id > 0
                        THEN installation_id END AS installation_id,
                   CASE WHEN typeof(repository_id) = 'integer' AND repository_id > 0
                        THEN repository_id END AS repository_id,
                   CASE WHEN typeof(pull_request_number) = 'integer' AND pull_request_number > 0
                        THEN pull_request_number END AS pull_request_number,
                   CASE WHEN typeof(action) = 'text' AND action = 'open_pull_request'
                        THEN action END AS action,
                   CASE WHEN typeof(posture) = 'text' AND posture = 'awaiting_observation'
                        THEN posture END AS posture,
                   CASE WHEN typeof(cut) = 'text' AND cut = 'host_recorded'
                        THEN cut END AS cut
            FROM host_records
            ORDER BY action_identity
            LIMIT ?
            """,
        (
            str(OPEN_PULL_REQUEST_COMMAND.action_identity),
            RESOURCE_LIMITS["retained.host.records"] + 1,
        ),
    ).fetchall()
    if len(rows) > RESOURCE_LIMITS["retained.host.records"]:
        raise SimulationCapacityError(
            "host_record_capacity_exceeded",
            RESOURCE_LIMITS["retained.host.records"],
        )
    if any(value is None for row in rows for value in row):
        raise SimulationCapacityError("invalid_host_record_observation")
    return [
        HostRecord(
            action_identity=ActionIdentity(row["action_identity"]),
            action=row["action"],
            posture=AwaitingObservation(
                subject=PullRequestSubject(
                    installation_id=row["installation_id"],
                    repository_id=row["repository_id"],
                    pull_request_number=row["pull_request_number"],
                ),
                posture=row["posture"],
            ),
            cut=row["cut"],
        )
        for row in rows
    ]


def host_state(root: Path) -> HostState:
    path = root / "catalog.sqlite3"
    if not path.is_file():
        return HostState(subjects=[], records=[])
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        return HostState(
            subjects=observed_host_subjects(connection),
            records=observed_host_records(connection),
        )


def delivery_state(root: Path) -> DeliveryState:
    path = root / "deliveries.sqlite3"
    if not path.is_file():
        return DeliveryState(rows=0, retained=None)
    custody = DeliveryCustody.from_path(path=path, provider_routes=(PROVIDER_ROUTE,))
    completions = DeliveryCompletionCustody.from_path(path=path)
    staged = ingress_state(root).acquisition
    expected_delivery = None
    if staged is not None:
        expected_delivery = CustodiedDelivery(
            provider_route_id=staged.identity.provider_route_id,
            custody_generation=staged.custody_generation,
            webhook=staged.webhook,
            quarantined=staged.quarantined,
        )
    return DeliveryState(
        rows=custody.retained_count(),
        retained=custody.retained_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        ),
        completion_rows=completions.completion_count(),
        completion=completions.completion_receipt(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
            expected_delivery=expected_delivery,
        ),
    )


def empty_ingress_resources() -> IngressResources:
    return IngressResources(
        manifests=0,
        entries=0,
        grants=0,
        decisions=0,
        acquisition_bytes=0,
        canonical_bytes=0,
        database_pages=0,
        maximum_manifests=MAX_MANIFESTS,
        maximum_acquisition_bytes=MAX_MANIFESTS * MAX_ACQUISITION_BYTES,
        maximum_database_pages=MAX_SQLITE_PAGES,
    )


def ingress_state(root: Path) -> IngressState:
    if not (root / "readiness-ingress.sqlite3").is_file():
        return IngressState(acquisition=None, posture=None, resources=empty_ingress_resources())
    authority = build_staging_authority(
        state_root=root,
        provider_routes=(PROVIDER_ROUTE,),
        policy_revision=STAGING_POLICY_REVISION,
    )
    return IngressState(
        acquisition=authority.staging_acquisition(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        ),
        posture=authority.staging_posture(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        ),
        resources=authority.ingress_resources(),
    )


def observe_hamsterdan(root: Path) -> HamsterdanState:
    return HamsterdanState(
        host=host_state(root),
        readiness=readiness_state(
            root / EXPECTED_REGISTRATION.readiness_root,
            dispatch_path=root / "dispatch.sqlite3",
            ingress_path=root / "readiness-ingress.sqlite3",
        ),
        delivery=delivery_state(root),
        ingress=ingress_state(root),
    )


def action_was_recorded(root: Path, action_identity: ActionIdentity) -> bool:
    path = root / "catalog.sqlite3"
    if not path.is_file():
        return False
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            "SELECT 1 FROM host_records WHERE action_identity = ?",
            (action_identity,),
        ).fetchone()
    return row is not None


def root_resource_usage(root: Path) -> ResourceUsage:
    file_count, retained_bytes = bounded_state_storage(
        root,
        maximum_files=RESOURCE_LIMITS["retained.state.files"],
        maximum_bytes=RESOURCE_LIMITS["retained.state.bytes"],
    )
    readiness_root = root / EXPECTED_REGISTRATION.readiness_root
    state = readiness_state(
        readiness_root,
        dispatch_path=root / "dispatch.sqlite3",
        ingress_path=root / "readiness-ingress.sqlite3",
    )
    host = host_state(root)
    delivery = delivery_state(root)
    ingress = ingress_state(root)
    return ResourceUsage(
        values={
            "pending.motus.tasks": pending_dispatch_tasks(root / "dispatch.sqlite3"),
            "retained.host.records": len(host.records),
            "retained.host.subjects": len(host.subjects),
            "retained.host.deliveries": delivery.rows,
            "retained.host.delivery_completions": delivery.completion_rows,
            "retained.readiness.ingress.manifests": ingress.resources.manifests,
            "retained.readiness.ingress.entries": ingress.resources.entries,
            "retained.readiness.ingress.grants": ingress.resources.grants,
            "retained.readiness.ingress.decisions": ingress.resources.decisions,
            "retained.readiness.ingress.acquisition_bytes": ingress.resources.acquisition_bytes,
            "retained.readiness.ingress.canonical_bytes": ingress.resources.canonical_bytes,
            "retained.readiness.ingress.database_pages": ingress.resources.database_pages,
            "retained.readiness.history_records": state.history_records,
            "retained.readiness.in_flight_occurrences": state.in_flight_occurrences,
            "retained.state.bytes": retained_bytes,
            "retained.state.files": file_count,
        }
    )


def validate_open_pull_request(command: Command) -> Command:
    if command.name != "hamsterdan.open_pull_request":
        raise ValueError("DS1 root accepts only 'hamsterdan.open_pull_request'")
    parsed = OpenPullRequestCommand.model_validate(command.payload, strict=True)
    if parsed != OPEN_PULL_REQUEST_COMMAND or parsed.model_dump(mode="json") != command.payload:
        raise ValueError("DS1 root command must name the exact admitted action, subject, and fields")
    return command


def validate_receive_webhook(command: Command) -> Command:
    if command.name != "hamsterdan.receive_webhook":
        raise ValueError("CV21 root accepts only admitted host and webhook commands")
    parsed = ReceiveWebhookCommand.model_validate(command.payload, strict=True)
    if parsed not in (RECEIVE_WEBHOOK_COMMAND, COLLIDE_WEBHOOK_COMMAND):
        raise ValueError("DS2 root command must choose one exact admitted signed fixture")
    if parsed.model_dump(mode="json") != command.payload:
        raise ValueError("DS2 root webhook command must contain exactly the admitted fields")
    return command


def validate_stage_webhook(command: Command) -> Command:
    if command.name != "hamsterdan.stage_webhook":
        raise ValueError("CV21 root accepts only admitted host, webhook, and staging commands")
    parsed = StageWebhookCommand.model_validate(command.payload, strict=True)
    if parsed != STAGE_WEBHOOK_COMMAND or parsed.model_dump(mode="json") != command.payload:
        raise ValueError("DS2 root staging command must name the exact acquired identity and fields")
    return command


def validate_accept_staged_observation(command: Command) -> Command:
    if command.name != "hamsterdan.accept_staged_observation":
        raise ValueError("CV21 root accepts only admitted host, webhook, staging, and acceptance commands")
    parsed = AcceptStagedObservationCommand.model_validate(command.payload, strict=True)
    if parsed != ACCEPT_STAGED_OBSERVATION_COMMAND or parsed.model_dump(mode="json") != command.payload:
        raise ValueError("DS2 root acceptance command must contain exactly the admitted fields")
    return command


def validate_fold_accepted_observation(command: Command) -> Command:
    if command.name != "hamsterdan.fold_accepted_observation":
        raise ValueError("CV21 root accepts only admitted host, webhook, staging, acceptance, and fold commands")
    parsed = FoldAcceptedObservationCommand.model_validate(command.payload, strict=True)
    if parsed != FOLD_ACCEPTED_OBSERVATION_COMMAND or parsed.model_dump(mode="json") != command.payload:
        raise ValueError("DS2 root fold command must contain exactly the admitted fields")
    return command


def validate_complete_observation_delivery(command: Command) -> Command:
    if command.name != "hamsterdan.complete_observation_delivery":
        raise ValueError("CV21 root accepts only the six admitted cumulative tracer commands")
    parsed = CompleteObservationDeliveryCommand.model_validate(command.payload, strict=True)
    if parsed != COMPLETE_OBSERVATION_DELIVERY_COMMAND or parsed.model_dump(mode="json") != command.payload:
        raise ValueError("DS2 root host-completion command must contain exactly the admitted fields")
    return command


def stage_retained_webhook(root: Path) -> StagingPosture:
    return build_staging_authority(
        state_root=root,
        provider_routes=(PROVIDER_ROUTE,),
        policy_revision=STAGING_POLICY_REVISION,
    ).stage_delivery(
        provider_route_id=PROVIDER_ROUTE_ID,
        delivery_id=DELIVERY_ID,
    )


def accept_staged_observation(root: Path) -> HistoryAcceptancePosture:
    return build_observation_acceptance_authority(state_root=root).accept_staged_observation(
        provider_route_id=PROVIDER_ROUTE_ID,
        delivery_id=DELIVERY_ID,
    )


def fold_accepted_observation(root: Path) -> ObservationFoldPosture | HistoryAcceptancePosture:
    return build_observation_acceptance_authority(state_root=root).fold_accepted_observation(
        provider_route_id=PROVIDER_ROUTE_ID,
        delivery_id=DELIVERY_ID,
    )


def complete_observation_delivery(root: Path) -> HostDeliveryCompletionReceipt:
    return build_observation_acceptance_authority(state_root=root).complete_observation_delivery(
        provider_route_id=PROVIDER_ROUTE_ID,
        delivery_id=DELIVERY_ID,
    )


def receive_signed_webhook(root: Path, fixture: Literal["original", "collision"]) -> DeliveryReceipt:
    head_sha = ORIGINAL_HEAD_SHA if fixture == "original" else COLLIDING_HEAD_SHA
    body = signed_webhook_body(head_sha=head_sha)
    headers = {name.decode(): value.decode() for name, value in signed_webhook_headers(body)}
    app = build_webhook_app(
        state_root=root,
        webhook_secret=WEBHOOK_SIGNING_MATERIAL,
        provider_routes=(PROVIDER_ROUTE,),
    )
    with TestClient(app) as client:
        response = client.post("/github/webhooks", content=body, headers=headers)
    if response.status_code != status.HTTP_202_ACCEPTED:
        raise RuntimeError(f"admitted DS2 fixture was refused with HTTP {response.status_code}")
    return DeliveryReceipt.model_validate(response.json(), strict=True)


class HamsterdanScenarioProfile:
    """Petrus profile over the real replacement host composition."""

    identity = PROFILE_IDENTITY

    def __init__(self, root: Path) -> None:
        self._root = root

    def validate(self, command: Command) -> Command:
        validator = {
            "hamsterdan.open_pull_request": validate_open_pull_request,
            "hamsterdan.receive_webhook": validate_receive_webhook,
            "hamsterdan.stage_webhook": validate_stage_webhook,
            "hamsterdan.accept_staged_observation": validate_accept_staged_observation,
            "hamsterdan.fold_accepted_observation": validate_fold_accepted_observation,
            "hamsterdan.complete_observation_delivery": validate_complete_observation_delivery,
        }.get(command.name)
        if validator is None:
            raise ValueError("CV21 root accepts only the six admitted cumulative tracer commands")
        return validator(command)

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"CV21 root admits no faults; remove {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[Hamsterdan]:
        del context
        return start_hamsterdan(self._root)

    def load(self, context: ScenarioContext) -> GenerationStart[Hamsterdan]:
        del context
        return start_hamsterdan(self._root)

    def apply(
        self,
        generation: Hamsterdan,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del context
        operation = {
            "hamsterdan.receive_webhook": self.apply_receive,
            "hamsterdan.stage_webhook": self.apply_staging,
            "hamsterdan.accept_staged_observation": self.apply_acceptance,
            "hamsterdan.fold_accepted_observation": self.apply_fold,
            "hamsterdan.complete_observation_delivery": self.apply_completion,
            "hamsterdan.open_pull_request": self.apply_open,
        }[command.name]
        return operation(generation, command)

    def apply_receive(self, generation: Hamsterdan, command: Command) -> ApplyResult:
        del generation
        parsed = ReceiveWebhookCommand.model_validate(command.payload, strict=True)
        receipt = receive_signed_webhook(self._root, parsed.fixture)
        return ApplyResult(
            disposition="idempotent" if receipt.disposition == "exact_duplicate" else "applied",
            value=receipt.model_dump(mode="json"),
            scheduled=[],
        )

    def apply_staging(self, generation: Hamsterdan, command: Command) -> ApplyResult:
        del generation, command
        posture = stage_retained_webhook(self._root)
        return ApplyResult(
            disposition="idempotent" if posture.disposition == "exact_duplicate" else "applied",
            value=posture.model_dump(mode="json"),
            scheduled=[],
        )

    def apply_acceptance(self, generation: Hamsterdan, command: Command) -> ApplyResult:
        del generation, command
        before = readiness_state(
            self._root / EXPECTED_REGISTRATION.readiness_root,
            dispatch_path=self._root / "dispatch.sqlite3",
        ).history_records
        posture = accept_staged_observation(self._root)
        after = readiness_state(
            self._root / EXPECTED_REGISTRATION.readiness_root,
            dispatch_path=self._root / "dispatch.sqlite3",
        ).history_records
        return ApplyResult(
            disposition="idempotent" if after == before else "applied",
            value=posture.model_dump(mode="json"),
            scheduled=[],
        )

    def apply_fold(self, generation: Hamsterdan, command: Command) -> ApplyResult:
        del generation, command
        before = readiness_state(
            self._root / EXPECTED_REGISTRATION.readiness_root,
            dispatch_path=self._root / "dispatch.sqlite3",
            ingress_path=self._root / "readiness-ingress.sqlite3",
        ).history_records
        posture = fold_accepted_observation(self._root)
        after = readiness_state(
            self._root / EXPECTED_REGISTRATION.readiness_root,
            dispatch_path=self._root / "dispatch.sqlite3",
            ingress_path=self._root / "readiness-ingress.sqlite3",
        ).history_records
        return ApplyResult(
            disposition="idempotent" if after == before else "applied",
            value=posture.model_dump(mode="json"),
            scheduled=[],
        )

    def apply_completion(self, generation: Hamsterdan, command: Command) -> ApplyResult:
        del generation, command
        before = delivery_state(self._root).completion_rows
        receipt = complete_observation_delivery(self._root)
        after = delivery_state(self._root).completion_rows
        return ApplyResult(
            disposition="idempotent" if after == before else "applied",
            value=receipt.model_dump(mode="json"),
            scheduled=[],
        )

    def apply_open(self, generation: Hamsterdan, command: Command) -> ApplyResult:
        del command
        replayed = action_was_recorded(self._root, OPEN_PULL_REQUEST_COMMAND.action_identity)
        record = generation.open_pull_request(OPEN_PULL_REQUEST_COMMAND)
        return ApplyResult(
            disposition="idempotent" if replayed else "applied",
            value=record.model_dump(mode="json"),
            scheduled=[],
        )

    def observe(
        self,
        generation: Hamsterdan,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del generation, context
        if request != ROOT_OBSERVATION_REQUEST:
            raise ValueError("CV21 root exposes only the parameterless 'hamsterdan.state' observation")
        return cast("JsonValue", observe_hamsterdan(self._root).model_dump(mode="json"))

    def resource_usage(self, generation: Hamsterdan | None) -> ResourceUsage:
        del generation
        return root_resource_usage(self._root)

    def drop(self, generation: Hamsterdan) -> None:
        del generation

    def close(self, generation: Hamsterdan) -> None:
        del generation


class HamsterdanChecker:
    """Check cross-owner identity without decoding Petrus runtime state."""

    identity = CHECKER_IDENTITY
    request = ROOT_OBSERVATION_REQUEST

    def check(self, observation: Observation) -> CheckResult:
        state = HamsterdanState.model_validate_json(json.dumps(observation.value), strict=True)
        empty_host = state.host == HostState(subjects=[], records=[]) and state.readiness == ReadinessState(
            binding=None,
            history_records=0,
            in_flight_occurrences=0,
        )
        subject_binding = state.host.subjects in ([], [EXPECTED_REGISTRATION])
        action_identity = state.host.records in ([], [EXPECTED_RECORD])
        readiness_result = ReadinessChecker().check(
            Observation(
                name="readiness.state",
                value=state.readiness.model_dump(mode="json"),
                instant=observation.instant,
                generation=observation.generation,
                sequence=observation.sequence,
            )
        )
        registered = state.host == HostState(
            subjects=[EXPECTED_REGISTRATION], records=[]
        ) and state.readiness == ReadinessState(
            binding=None,
            history_records=0,
            in_flight_occurrences=0,
        )
        readiness_durable = (
            state.host == HostState(subjects=[EXPECTED_REGISTRATION], records=[])
            and state.readiness.binding is not None
            and state.readiness.history_records > 0
        )
        opened = (
            state.host == HostState(subjects=[EXPECTED_REGISTRATION], records=[EXPECTED_RECORD])
            and state.readiness.binding is not None
            and state.readiness.history_records > 0
        )
        delivery = state.delivery.retained
        delivery_empty = state.delivery == DeliveryState(rows=0, retained=None)
        delivery_custody = delivery_empty or (
            state.delivery.rows == 1 and state.delivery.retained in (EXPECTED_DELIVERY, EXPECTED_QUARANTINED_DELIVERY)
        )
        delivery_route = delivery is None or (
            delivery.provider_route_id == PROVIDER_ROUTE_ID and delivery.webhook.route == EXPECTED_WEBHOOK.route
        )
        delivery_identity = delivery is None or delivery.webhook.provenance.delivery_id == DELIVERY_ID
        delivery_content = delivery is None or (
            delivery.webhook.snapshot == EXPECTED_WEBHOOK.snapshot
            and delivery.webhook.provenance.event == EXPECTED_WEBHOOK.provenance.event
            and delivery.webhook.provenance.action == EXPECTED_WEBHOOK.provenance.action
        )
        completion = state.delivery.completion
        expected_completion = (
            completion is not None
            and completion.provider_route_id == PROVIDER_ROUTE_ID
            and completion.delivery_id == DELIVERY_ID
            and completion.custody_generation == 1
            and completion.subject == SUBJECT
            and completion.instance_id == INSTANCE_ID
            and completion.bridge_identity == EXPECTED_BRIDGE_IDENTITY
            and str(completion.manifest_id) == str(EXPECTED_STAGING.manifest.manifest_id)
            and str(completion.grant_id) == str(EXPECTED_STAGING.grant.grant_id)
            and completion.manifest_digest == EXPECTED_STAGING.grant.manifest_digest
            and completion.entry_order == 0
            and str(completion.observation_key) == str(EXPECTED_STAGING.manifest.entries[0].observation_key)
            and str(completion.history_delivery_identity) == expected_history_delivery_identity(EXPECTED_STAGING)
            and completion.occurrence == 1
            and completion.workflow_cut == "observation_folded"
            and completion.cut == "host_delivery_completed"
        )
        completion_correspondence = (state.delivery.completion_rows == 0 and completion is None) or (
            state.delivery.completion_rows == 1
            and expected_completion
            and state.readiness.folded
            and state.readiness.delivery is not None
            and state.readiness.fold_posture is not None
            and state.readiness.delivery.delivery_identity == completion.history_delivery_identity
            and state.readiness.delivery.occurrence == completion.occurrence
            and state.readiness.fold_posture.delivery_identity == completion.history_delivery_identity
            and state.readiness.fold_posture.occurrence == completion.occurrence
        )
        posture = state.ingress.posture
        ingress_result = IngressChecker().check(
            Observation(
                name="readiness.ingress.state",
                value=state.ingress.model_dump(mode="json"),
                instant=observation.instant,
                generation=observation.generation,
                sequence=observation.sequence,
            )
        )
        ingress_detail = cast("dict[str, JsonValue]", ingress_result.detail)
        entries = () if posture is None else posture.manifest.entries
        staged_acquisition = state.ingress.acquisition
        ingress_delivery = (posture is None and state.ingress.acquisition is None) or (
            posture is not None
            and delivery is not None
            and staged_acquisition is not None
            and staged_acquisition.identity == posture.manifest.acquisition
            and staged_acquisition.custody_generation == delivery.custody_generation
            and staged_acquisition.webhook == delivery.webhook
            and posture.manifest.acquisition.provider_route_id == delivery.provider_route_id
            and posture.manifest.acquisition.delivery_id == delivery.webhook.provenance.delivery_id
            and (
                (not entries and staged_acquisition.quarantined and delivery.quarantined)
                or (
                    len(entries) == 1
                    and not staged_acquisition.quarantined
                    and entries[0].observation.subject.model_dump(mode="json")
                    == staged_acquisition.webhook.snapshot.subject.model_dump(mode="json")
                )
            )
        )
        ingress_empty = (
            posture is None
            and state.ingress.resources.manifests
            == state.ingress.resources.entries
            == state.ingress.resources.grants
            == state.ingress.resources.decisions
            == state.ingress.resources.acquisition_bytes
            == state.ingress.resources.canonical_bytes
            == 0
        )
        ingress_staged = posture is not None and state.ingress.resources.manifests == 1
        staged_without_host = (
            state.host == HostState(subjects=[], records=[])
            and posture is not None
            and state.readiness
            == ReadinessState(
                binding=None,
                history_records=0,
                in_flight_occurrences=0,
                staging=posture,
            )
        )
        history_acceptance = history_acceptance_corresponds(state)
        empty = empty_host and delivery_empty
        return CheckResult(
            passed=(empty_host or staged_without_host or registered or readiness_durable or opened)
            and subject_binding
            and action_identity
            and readiness_result.passed
            and delivery_custody
            and delivery_route
            and delivery_identity
            and delivery_content
            and (ingress_empty or ingress_staged)
            and ingress_result.passed
            and ingress_delivery
            and history_acceptance
            and completion_correspondence,
            detail={
                "empty": empty,
                "staged_without_host": staged_without_host,
                "registered": registered,
                "readiness_durable": readiness_durable,
                "opened": opened,
                "subject_binding": subject_binding,
                "action_identity": action_identity,
                "readiness": readiness_result.passed,
                "delivery_custody": delivery_custody,
                "delivery_route": delivery_route,
                "delivery_identity": delivery_identity,
                "delivery_content": delivery_content,
                "ingress_empty": ingress_empty,
                "ingress_staged": ingress_staged,
                "ingress": ingress_result.passed,
                "ingress_delivery": ingress_delivery,
                "history_acceptance": history_acceptance,
                "host_completion": completion_correspondence,
                "ingress_acquisition": ingress_detail["acquisition"],
                "ingress_manifest": ingress_detail["manifest"],
                "ingress_entry_order": ingress_detail["entry_order"],
                "ingress_key": ingress_detail["key"],
                "ingress_bytes": ingress_detail["canonical_bytes"],
                "ingress_observation": ingress_detail["observation"],
                "ingress_grant": ingress_detail["grant"],
                "ingress_decision": ingress_detail["decision"],
                "ingress_acquisition_bytes": ingress_detail["acquisition_bytes"],
                "ingress_resources": ingress_detail["resources"],
            },
        )


def build_hamsterdan_world(*, root: Path, budget: BudgetV4 = DEFAULT_BUDGET) -> World:
    profile = cast("ScenarioProfile[object]", HamsterdanScenarioProfile(root))
    return World(profile, budget, checkers=(HamsterdanChecker(),))


def replay_hamsterdan(artifact: ScenarioArtifactV3 | ScenarioArtifact, *, root: Path) -> ReplayResult:
    if not isinstance(artifact, ScenarioArtifact):
        raise TypeError("CV21 root replay requires a version-4 resource artifact")
    registry = ScenarioRegistry()
    registry.register_profile(HamsterdanScenarioProfile(root))
    registry.register_checker(HamsterdanChecker())
    return cast("ReplayResult", replay(artifact, registry))
