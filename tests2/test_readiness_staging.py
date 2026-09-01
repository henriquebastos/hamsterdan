# Copyright (c) 2026 Henrique Bastos

"""Source-neutral readiness staging starts only on an authority turn."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import sqlite3
from threading import Event
from typing import TYPE_CHECKING, cast

from fastapi.testclient import TestClient
from petrus.engine import Engine
from petrus.impetus.history import ExternalEventDelivered, FiringBegun, FiringCompleted, FiringFailed, TokensProduced
from petrus.impetus.history_store import SqliteHistoryStore
from petrus.impetus.instance import (
    AcceptedDelivery,
    DeliveryDisposition,
    FiringOutcome,
    PriorAcknowledgement,
    ScopedDeliveryAcknowledgement,
)
from petrus.impetus.petrinet import NetPath, Token
from pydantic import ValidationError

from hamsterdan2.github_app.models import (
    CommitSha,
    DeliveryId,
    PositiveIdentifier,
    ProviderRouteId,
    RepositoryFullName,
)
from hamsterdan2.github_app.simulation.webhooks import (
    DELIVERY_ID,
    WEBHOOK_SIGNING_MATERIAL,
    signed_webhook_body,
    signed_webhook_headers,
)
from hamsterdan2.host import delivery as host_delivery
from hamsterdan2.host.application import (
    DeliveryNotFoundError,
    ObservationDeliveryNotFoldedError,
    StagingAuthority,
)
from hamsterdan2.host.catalog import (
    HostCatalogCorruptionError,
    PullRequestNotRegisteredError,
    SubjectRootConflictError,
)
from hamsterdan2.host.composition import (
    build_hamsterdan,
    build_observation_acceptance_authority,
    build_staging_authority,
    build_webhook_app,
)
from hamsterdan2.host.delivery import (
    MAX_NORMALIZED_BYTES,
    DeliveryCompletionCommitError,
    DeliveryCompletionConflictError,
    DeliveryCompletionCorruptionError,
    DeliveryCompletionCustody,
    DeliveryCustody,
    DeliveryCustodyCorruptionError,
)
from hamsterdan2.host.values import (
    ActionIdentity,
    ConfiguredProviderRoute,
    CustodiedDelivery,
    HostDeliveryCompletionReceipt,
    OpenPullRequestCommand,
)
from hamsterdan2.readiness import ingress as readiness_ingress
from hamsterdan2.readiness import projection as readiness_projection
from hamsterdan2.readiness import runtime as readiness_runtime
from hamsterdan2.readiness.ingress import IngressCapacityError, IngressCorruptionError, IngressCustody
from hamsterdan2.readiness.ingress_values import (
    MAX_ACQUISITION_BYTES,
    MAX_CANONICAL_OBSERVATION_BYTES,
    AdmissionDecision,
    CanonicalObservation,
    IngressManifest,
    ObservationFoldPosture,
    ObservationKey,
    PolicyRevision,
    StagingAcquisition,
    StagingPosture,
)
from hamsterdan2.readiness.projection import (
    grant_for,
    observation_entry,
)
from hamsterdan2.readiness.root import ReadinessRootCorruptionError, ReadinessRootMissingError
from hamsterdan2.readiness.runtime import HistoryCapacityError, ObservationFoldCommitError, ObservationNotFoldedError
from hamsterdan2.readiness.workflow_bridge import (
    RetainedSnapshotRejectedError,
    UnsupportedHeadObservationError,
    WorkflowBridgeError,
    bridge_head_delivery,
    history_delivery_identity,
)
from hamsterdan2.workflow.values import PullRequestSubject

import pytest


if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hamsterdan2.host.values import RegisteredPullRequest


PROVIDER_ROUTE_ID = ProviderRouteId("github:primary")
PROVIDER_ROUTE = ConfiguredProviderRoute(
    provider_route_id=PROVIDER_ROUTE_ID,
    installation_id=PositiveIdentifier(44),
    repository_id=PositiveIdentifier(31),
    repository_full_name=RepositoryFullName("owner/repo"),
)
POLICY_REVISION = PolicyRevision("policy:2026-08-30")
DEFAULT_HEAD_SHA = CommitSha("a" * 40)
CANONICAL_HEAD = (
    b'{"base":{"ref":"main","repository_id":31,"sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},'
    b'"draft":false,"family":"head","head":{"ref":"feature/custody","repository_id":32,'
    b'"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"lifecycle_state":"open","local_incarnation":1,'
    b'"mergeable":null,"merged":false,"subject":{"installation_id":44,"pull_request_number":7,'
    b'"repository_id":31},"version":1}'
)
HEAD_KEY = f"obs:v1:sha256:{sha256(CANONICAL_HEAD).hexdigest()}"
SECOND_DELIVERY_ID = DeliveryId("22222222-2222-4222-8222-222222222222")
THIRD_DELIVERY_ID = DeliveryId("33333333-3333-4333-8333-333333333333")
ORPHAN_MANIFEST_ID = f"manifest:v1:sha256:{'f' * 64}"


def colliding_observation_key(content: bytes) -> ObservationKey:
    del content
    return ObservationKey(f"obs:v1:sha256:{'f' * 64}")


class PausingSelectedDeliveryCustody(DeliveryCustody):
    """Pause after the wrapped real custody operation reaches its final read."""

    def __init__(self, custody: DeliveryCustody, selected: Event, continue_staging: Event) -> None:
        self._custody = custody
        self._selected = selected
        self._continue_staging = continue_staging

    def retained_delivery(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> CustodiedDelivery | None:
        delivery = self._custody.retained_delivery(
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
        )
        self._selected.set()
        assert self._continue_staging.wait(timeout=5)
        return delivery


class ManifestAppendingIngressCustody(IngressCustody):
    """Append one manifest after the outer acceptance reconstruction."""

    def __init__(self, custody: IngressCustody, append_manifest: Callable[[], None]) -> None:
        self._custody = custody
        self._append_manifest = append_manifest

    def reconstructed_staging(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> tuple[StagingAcquisition, StagingPosture] | None:
        reconstructed = self._custody.reconstructed_staging(
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
        )
        self._append_manifest()
        return reconstructed


class PausingDeliveryCustody(DeliveryCustody):
    """Pause real custody immediately after reconstructing its first row."""

    def __init__(
        self,
        *,
        path: Path,
        routes: dict[tuple[int, int, str], ProviderRouteId],
        maximum_deliveries: int,
    ) -> None:
        super().__init__(path=path, routes=routes, maximum_deliveries=maximum_deliveries)
        self.reconstruction_started = Event()
        self.continue_reconstruction = Event()

    def reconstruct_delivery_row(
        self,
        row: sqlite3.Row,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> CustodiedDelivery:
        delivery = super().reconstruct_delivery_row(
            row,
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
        )
        self.reconstruction_started.set()
        assert self.continue_reconstruction.wait(timeout=5)
        return delivery


def force_observation_key_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness_projection, "observation_key_for", colliding_observation_key)


def webhook_body(
    *,
    head_sha: CommitSha = DEFAULT_HEAD_SHA,
    action: str = "synchronize",
    draft: bool = False,
    lifecycle_state: str = "open",
    mergeable: bool | None = None,
    merged: bool = False,
    updated_at: str = "2026-08-30T12:34:56Z",
) -> bytes:
    payload = json.loads(signed_webhook_body(head_sha=head_sha))
    payload["action"] = action
    payload["pull_request"]["draft"] = draft
    payload["pull_request"]["state"] = lifecycle_state
    payload["pull_request"]["mergeable"] = mergeable
    payload["pull_request"]["merged"] = merged
    payload["pull_request"]["updated_at"] = updated_at
    return json.dumps(payload, separators=(",", ":")).encode()


def reverse_terminal_records(records: list[dict[str, object]], page: dict[str, object]) -> None:
    del page
    records[-2], records[-1] = records[-1], records[-2]
    records[-2]["position"], records[-1]["position"] = records[-1]["position"], records[-2]["position"]


def change_produced_content(records: list[dict[str, object]], page: dict[str, object]) -> None:
    del page
    payload = cast("dict[str, object]", records[-2]["record"])
    tokens = cast("list[dict[str, object]]", payload["tokens"])
    data = cast("dict[str, object]", tokens[0]["data"])
    data["head"] = "c" * 40


def remove_produced_terminal(records: list[dict[str, object]], page: dict[str, object]) -> None:
    records.pop(-2)
    for position, item in enumerate(records):
        item["position"] = position
    page["frontier"] = page["next"] = len(records)


def replace_completed_with_failure(records: list[dict[str, object]], page: dict[str, object]) -> None:
    del page
    records[-1]["record"] = {
        "record": "FiringFailed",
        "schema": 5,
        "transition": "on_head",
        "error": "fixed failure",
        "occurrence": 1,
        "instant": 0,
    }


def append_unrelated_terminal(records: list[dict[str, object]], page: dict[str, object]) -> None:
    records.append(
        {
            "position": len(records),
            "record": {
                "record": "FiringCompleted",
                "schema": 5,
                "transition": "unrelated",
                "occurrence": 99,
                "instant": 0,
            },
        }
    )
    page["frontier"] = page["next"] = len(records)


def insert_prior_failure(records: list[dict[str, object]], page: dict[str, object]) -> None:
    records.insert(
        len(records) - 4,
        {
            "position": 0,
            "record": {
                "record": "FiringFailed",
                "schema": 5,
                "transition": "on_head",
                "error": "fixed prior failure",
                "occurrence": 99,
                "instant": 0,
            },
        },
    )
    for position, item in enumerate(records):
        item["position"] = position
    page["frontier"] = page["next"] = len(records)


def mutate_history_page(page: dict[str, object], mutation: str) -> dict[str, object]:
    records = cast("list[dict[str, object]]", page["records"])
    mutations = {
        "terminal-order": reverse_terminal_records,
        "produced-content": change_produced_content,
        "partial-terminal": remove_produced_terminal,
        "failed-terminal": replace_completed_with_failure,
        "unrelated-terminal": append_unrelated_terminal,
        "prior-failure": insert_prior_failure,
    }
    mutations[mutation](records, page)
    return page


def replace_accepted_occurrence(page: dict[str, object], occurrence: int) -> dict[str, object]:
    records = cast("list[dict[str, object]]", page["records"])
    for item in records[-2:]:
        record = cast("dict[str, object]", item["record"])
        record["occurrence"] = occurrence
    return page


def change_snapshot_status(current: dict[str, object]) -> None:
    current["status"] = "awaiting"


def change_snapshot_in_flight(current: dict[str, object]) -> None:
    current["in_flight"] = [{"occurrence": 1}]


def change_snapshot_token(current: dict[str, object], *, place: str, field: str, value: str) -> None:
    marking = cast("list[dict[str, object]]", current["marking"])
    selected = next(item for item in marking if item["place"] == place)
    tokens = cast("list[dict[str, object]]", selected["tokens"])
    data = cast("dict[str, object]", tokens[0]["data"])
    data[field] = value


def change_snapshot_life_phase(current: dict[str, object]) -> None:
    change_snapshot_token(current, place="life.state", field="phase", value="quiescent")


def change_snapshot_head_token(current: dict[str, object]) -> None:
    change_snapshot_token(current, place="life.heads", field="head", value="c" * 40)


def mutate_runtime_snapshot(snapshot: dict[str, object], mutation: str) -> dict[str, object]:
    current = cast("dict[str, object]", snapshot["current"])
    mutations = {
        "status": change_snapshot_status,
        "in-flight": change_snapshot_in_flight,
        "life-phase": change_snapshot_life_phase,
        "head-token": change_snapshot_head_token,
    }
    mutations[mutation](current)
    return snapshot


def acquire_signed_delivery(
    root: Path,
    *,
    delivery_id: DeliveryId = DELIVERY_ID,
    body: bytes | None = None,
) -> dict[str, object]:
    request_body = webhook_body() if body is None else body
    headers = {
        name.decode(): (str(delivery_id) if name == b"x-github-delivery" else value.decode())
        for name, value in signed_webhook_headers(request_body)
    }
    app = build_webhook_app(
        state_root=root,
        webhook_secret=WEBHOOK_SIGNING_MATERIAL,
        provider_routes=(PROVIDER_ROUTE,),
    )

    with TestClient(app) as client:
        response = client.post("/github/webhooks", content=request_body, headers=headers)

    assert response.status_code == 202
    return response.json()


@dataclass(frozen=True)
class AcceptanceFixture:
    """One registered, opened, acquired, and staged task-4 authority."""

    root: Path
    registered: RegisteredPullRequest
    staged: StagingPosture
    initial_history_records: int

    @property
    def history_path(self) -> Path:
        return self.root / self.registered.readiness_root / "history.sqlite3"


def history_records(fixture: AcceptanceFixture) -> tuple[object, ...]:
    history = SqliteHistoryStore(fixture.history_path, fixture.registered.instance_id)
    try:
        return history.records
    finally:
        history.close()


def open_registered_readiness(root: Path) -> RegisteredPullRequest:
    subject = PullRequestSubject(installation_id=44, repository_id=31, pull_request_number=7)
    command = OpenPullRequestCommand(action_identity=ActionIdentity("trace:open:1"), subject=subject)
    host = build_hamsterdan(state_root=root)
    registered = host.register(command)
    host.step(command)
    return registered


def prepare_acceptance(
    root: Path,
    *,
    body: bytes | None = None,
    policy_revision: PolicyRevision = POLICY_REVISION,
) -> AcceptanceFixture:
    registered = open_registered_readiness(root)
    acquire_signed_delivery(root, body=body)
    staged = build_staging_authority(
        state_root=root,
        provider_routes=(PROVIDER_ROUTE,),
        policy_revision=policy_revision,
    ).stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
    fixture = AcceptanceFixture(
        root=root,
        registered=registered,
        staged=staged,
        initial_history_records=0,
    )
    return AcceptanceFixture(
        root=root,
        registered=registered,
        staged=staged,
        initial_history_records=len(history_records(fixture)),
    )


def reconstructed_acquisition(fixture: AcceptanceFixture) -> StagingAcquisition:
    reconstructed = IngressCustody.for_reconstruction(
        path=fixture.root / "readiness-ingress.sqlite3",
    ).reconstructed_staging(
        provider_route_id=PROVIDER_ROUTE_ID,
        delivery_id=DELIVERY_ID,
    )
    assert reconstructed is not None
    return reconstructed[0]


def reconstructed_custodied_delivery(fixture: AcceptanceFixture) -> CustodiedDelivery:
    acquisition = reconstructed_acquisition(fixture)
    return CustodiedDelivery(
        provider_route_id=acquisition.identity.provider_route_id,
        custody_generation=acquisition.custody_generation,
        webhook=acquisition.webhook,
        quarantined=acquisition.quarantined,
    )


def duplicate_subject_registration(
    fixture: AcceptanceFixture,
    *,
    instance_id: str,
    readiness_root: str,
) -> None:
    path = fixture.root / "catalog.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            CREATE TABLE malformed_subject_roots (
                installation_id INTEGER NOT NULL,
                repository_id INTEGER NOT NULL,
                pull_request_number INTEGER NOT NULL,
                instance_id TEXT NOT NULL,
                readiness_root TEXT NOT NULL
            )
            """
        )
        connection.execute("INSERT INTO malformed_subject_roots SELECT * FROM subject_roots")
        connection.execute(
            "INSERT INTO malformed_subject_roots VALUES (?, ?, ?, ?, ?)",
            (
                fixture.registered.subject.installation_id,
                fixture.registered.subject.repository_id,
                fixture.registered.subject.pull_request_number,
                instance_id,
                readiness_root,
            ),
        )
        connection.execute("DROP TABLE subject_roots")
        connection.execute("ALTER TABLE malformed_subject_roots RENAME TO subject_roots")


def replace_subject_registration(
    fixture: AcceptanceFixture,
    *,
    instance_id: object,
    readiness_root: object,
) -> None:
    path = fixture.root / "catalog.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            CREATE TABLE malformed_subject_roots (
                installation_id,
                repository_id,
                pull_request_number,
                instance_id,
                readiness_root
            )
            """
        )
        connection.execute(
            "INSERT INTO malformed_subject_roots VALUES (?, ?, ?, ?, ?)",
            (
                fixture.registered.subject.installation_id,
                fixture.registered.subject.repository_id,
                fixture.registered.subject.pull_request_number,
                instance_id,
                readiness_root,
            ),
        )
        connection.execute("DROP TABLE subject_roots")
        connection.execute("ALTER TABLE malformed_subject_roots RENAME TO subject_roots")


def duplicate_readiness_root_binding(
    fixture: AcceptanceFixture,
    *,
    singleton: int,
    instance_id: str,
    bridge_identity: str,
) -> None:
    path = fixture.root / fixture.registered.readiness_root / "readiness.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE malformed_root_binding (
                singleton INTEGER NOT NULL,
                instance_id TEXT NOT NULL,
                bridge_identity TEXT NOT NULL
            )
            """
        )
        connection.execute("INSERT INTO malformed_root_binding SELECT * FROM root_binding")
        connection.execute(
            "INSERT INTO malformed_root_binding VALUES (?, ?, ?)",
            (singleton, instance_id, bridge_identity),
        )
        connection.execute("DROP TABLE root_binding")
        connection.execute("ALTER TABLE malformed_root_binding RENAME TO root_binding")


def replace_readiness_root_binding(
    fixture: AcceptanceFixture,
    *,
    singleton: object,
    instance_id: object,
    bridge_identity: object,
) -> None:
    path = fixture.root / fixture.registered.readiness_root / "readiness.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE malformed_root_binding (
                singleton,
                instance_id,
                bridge_identity
            )
            """
        )
        connection.execute(
            "INSERT INTO malformed_root_binding VALUES (?, ?, ?)",
            (singleton, instance_id, bridge_identity),
        )
        connection.execute("DROP TABLE root_binding")
        connection.execute("ALTER TABLE malformed_root_binding RENAME TO root_binding")


def replace_staged_entry_with_valid_unrelated_head(root: Path, staged: StagingPosture) -> None:
    changed_observation = staged.manifest.entries[0].observation.model_copy(update={"draft": True})
    changed_entry = observation_entry(changed_observation)
    changed_manifest = staged.manifest.model_copy(update={"entries": (changed_entry,)})
    changed_grant = grant_for(changed_manifest)
    with closing(sqlite3.connect(root / "readiness-ingress.sqlite3")) as connection, connection:
        connection.execute(
            "UPDATE ingress_entries SET observation_key = ?, canonical_bytes = ?",
            (changed_entry.observation_key, changed_entry.canonical_bytes),
        )
        connection.execute(
            "UPDATE admission_grants SET grant_id = ?, manifest_digest = ?",
            (changed_grant.grant_id, changed_grant.manifest_digest),
        )
        connection.execute(
            "UPDATE admission_decisions SET observation_key = ?",
            (changed_entry.observation_key,),
        )


def replace_acquisition_quarantine(root: Path, *, quarantined: bool) -> None:
    with closing(sqlite3.connect(root / "readiness-ingress.sqlite3")) as connection, connection:
        row = connection.execute("SELECT acquisition_bytes FROM ingress_manifests").fetchone()
        acquisition = json.loads(row[0])
        acquisition["quarantined"] = quarantined
        acquisition_bytes = json.dumps(
            acquisition,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        connection.execute(
            "UPDATE ingress_manifests SET acquisition_bytes = ?, acquisition_digest = ?",
            (acquisition_bytes, sha256(acquisition_bytes).hexdigest()),
        )


def replace_decision_with_valid_incomparable(root: Path) -> None:
    with closing(sqlite3.connect(root / "readiness-ingress.sqlite3")) as connection, connection:
        connection.execute("UPDATE ingress_manifests SET original_disposition = 'incomparable'")
        connection.execute(
            """
            UPDATE admission_decisions
            SET disposition = 'incomparable', reason = 'unordered_head',
                fatal = 0, refresh_required = 1
            """
        )


def insert_orphan_ingress_row(root: Path, table: str) -> None:
    statements = {
        "entry": (
            """
            INSERT INTO ingress_entries (
                manifest_id, entry_order, observation_key, canonical_bytes
            ) VALUES (?, 0, ?, ?)
            """,
            (ORPHAN_MANIFEST_ID, HEAD_KEY, CANONICAL_HEAD),
        ),
        "grant": (
            """
            INSERT INTO admission_grants (grant_id, manifest_id, manifest_digest)
            VALUES (?, ?, ?)
            """,
            (f"grant:v1:sha256:{'f' * 64}", ORPHAN_MANIFEST_ID, "f" * 64),
        ),
        "decision": (
            """
            INSERT INTO admission_decisions (
                manifest_id, decision_order, entry_order, observation_key,
                disposition, reason, fatal, refresh_required
            ) VALUES (?, 0, NULL, NULL, 'acquisition_collision',
                      'quarantined_acquisition', 1, 0)
            """,
            (ORPHAN_MANIFEST_ID,),
        ),
    }
    statement, parameters = statements[table]
    with closing(sqlite3.connect(root / "readiness-ingress.sqlite3")) as connection, connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(statement, parameters)


class TestFirstReadinessStagingTurn:
    """One signed acquisition becomes one durable Head manifest outside HTTP."""

    def test_authority_turn_stages_novel_head_without_history_or_fold(self, tmp_path: Path) -> None:
        receipt = acquire_signed_delivery(tmp_path)
        custody = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        )
        delivery = custody.retained_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )

        staged = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        reconstructed = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        ).staging_posture(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert receipt["disposition"] == "retained"
        assert delivery is not None
        assert delivery.is_readiness_eligible()
        assert staged == reconstructed
        assert staged is not None
        assert staged.disposition == "novel"
        assert staged.manifest.policy_revision == POLICY_REVISION
        assert len(staged.manifest.entries) == 1
        entry = staged.manifest.entries[0]
        assert entry.order == 0
        assert str(entry.observation_key) == HEAD_KEY
        assert bytes(entry.canonical_bytes) == CANONICAL_HEAD
        assert entry.observation.model_dump(mode="json") == {
            "version": 1,
            "family": "head",
            "subject": {
                "installation_id": 44,
                "repository_id": 31,
                "pull_request_number": 7,
            },
            "local_incarnation": 1,
            "head": {
                "repository_id": 32,
                "ref": "feature/custody",
                "sha": "a" * 40,
            },
            "base": {"repository_id": 31, "ref": "main", "sha": "b" * 40},
            "lifecycle_state": "open",
            "draft": False,
            "merged": False,
            "mergeable": None,
        }
        assert staged.grant.manifest_id == staged.manifest.manifest_id
        assert [decision.model_dump(mode="json") for decision in staged.decisions] == [
            {
                "entry_order": 0,
                "observation_key": HEAD_KEY,
                "disposition": "novel",
                "reason": "first_observation",
                "fatal": False,
                "refresh_required": False,
            }
        ]
        assert not (tmp_path / "dispatch.sqlite3").exists()
        assert not list(tmp_path.rglob("history.sqlite3"))

    def test_registered_staged_head_is_accepted_in_history_without_being_folded(self, tmp_path: Path) -> None:
        subject = PullRequestSubject(installation_id=44, repository_id=31, pull_request_number=7)
        command = OpenPullRequestCommand(action_identity=ActionIdentity("trace:open:1"), subject=subject)
        host = build_hamsterdan(state_root=tmp_path)
        registered = host.register(command)
        opened = host.step(command)
        receipt = acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        staged = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        history_path = tmp_path / registered.readiness_root / "history.sqlite3"
        history = SqliteHistoryStore(history_path, registered.instance_id)
        before = history.records
        history.close()

        accepted = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        history = SqliteHistoryStore(history_path, registered.instance_id)
        records = history.records
        history.close()
        assert receipt["disposition"] == "retained"
        assert staged.disposition == "novel"
        assert opened.posture.posture == "awaiting_observation"
        assert accepted.subject == subject
        assert accepted.disposition == "accepted"
        assert accepted.reason == "accepted_unfinished"
        assert accepted.bridge_identity == "workflow-bridge/head-seen-history-fold@3"
        assert accepted.manifest_id == staged.manifest.manifest_id
        assert accepted.grant_id == staged.grant.grant_id
        assert accepted.entry_order == 0
        assert accepted.observation_key == staged.manifest.entries[0].observation_key
        assert accepted.delivery_identity is not None
        assert accepted.delivery_identity.startswith("history-delivery:v1:sha256:")
        assert accepted.occurrence is not None
        assert accepted.occurrence > 0
        assert accepted.folded is False
        assert records[: len(before)] == before
        accepted_records = records[len(before) :]
        assert len(accepted_records) == 2
        delivered, begun = accepted_records
        assert isinstance(delivered, ExternalEventDelivered)
        assert isinstance(begun, FiringBegun)
        assert str(delivered.source) == str(begun.transition) == "on_head"
        assert delivered.identity == str(accepted.delivery_identity)
        assert delivered.occurrence == begun.occurrence == accepted.occurrence
        assert delivered.scope is begun.scope is None
        assert delivered.instant == begun.instant == 0
        assert len(delivered.tokens) == 1
        token = delivered.tokens[0]
        assert token.color == "HeadSeen"
        assert token.data == {
            "head": "a" * 40,
            "base": "b" * 40,
            "mergeable": False,
            "policy": str(POLICY_REVISION),
            "strict_base": True,
            "base_current": False,
        }
        assert not any(isinstance(record, FiringCompleted | TokensProduced) for record in accepted_records)
        with closing(sqlite3.connect(tmp_path / "catalog.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM host_records").fetchone()[0] == 1
        with closing(sqlite3.connect(tmp_path / "dispatch.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM impetus_local_dispatch_tasks").fetchone()[0] == 0

    def test_accepted_head_folds_before_separate_host_delivery_completion(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)

        accepted = authority.accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        accepted_records = history_records(fixture)
        folded = authority.fold_accepted_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        folded_records = history_records(fixture)

        assert not accepted.finished
        assert not accepted.folded
        assert len(accepted_records) == fixture.initial_history_records + 2
        assert isinstance(folded, ObservationFoldPosture)
        assert folded.model_dump(mode="json") == {
            "subject": fixture.registered.subject.model_dump(mode="json"),
            "instance_id": fixture.registered.instance_id,
            "bridge_identity": "workflow-bridge/head-seen-history-fold@3",
            "manifest_id": str(fixture.staged.manifest.manifest_id),
            "grant_id": str(fixture.staged.grant.grant_id),
            "manifest_digest": fixture.staged.grant.manifest_digest,
            "entry_order": 0,
            "observation_key": str(fixture.staged.manifest.entries[0].observation_key),
            "delivery_identity": str(accepted.delivery_identity),
            "occurrence": accepted.occurrence,
            "phase": "running",
            "local_incarnation": 1,
            "head": {
                "repository_id": 32,
                "ref": "feature/custody",
                "sha": "a" * 40,
            },
            "base": {"repository_id": 31, "ref": "main", "sha": "b" * 40},
            "mergeable": False,
            "policy_revision": str(POLICY_REVISION),
            "strict_base": True,
            "base_current": False,
            "finished": True,
            "folded": True,
            "cut": "observation_folded",
        }
        assert folded_records[: len(accepted_records)] == accepted_records
        produced, completed = folded_records[-2:]
        assert isinstance(produced, TokensProduced)
        assert isinstance(completed, FiringCompleted)
        assert produced.occurrence == completed.occurrence == accepted.occurrence
        assert str(produced.place) == "life.heads"
        assert len(produced.tokens) == 1
        assert produced.tokens[0].color == "HeadSeen"
        assert produced.tokens[0].data == {
            "head": "a" * 40,
            "base": "b" * 40,
            "mergeable": False,
            "policy": str(POLICY_REVISION),
            "strict_base": True,
            "base_current": False,
        }
        assert produced.entries == ()
        assert produced.scope is None
        assert produced.instant == 0
        assert str(completed.transition) == "on_head"
        assert completed.instant == 0
        assert not any(isinstance(record, FiringFailed) for record in folded_records)

        completed_delivery = authority.complete_observation_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert completed_delivery.model_dump(mode="json") == {
            "provider_route_id": str(PROVIDER_ROUTE_ID),
            "delivery_id": str(DELIVERY_ID),
            "custody_generation": 1,
            "subject": fixture.registered.subject.model_dump(mode="json"),
            "instance_id": fixture.registered.instance_id,
            "bridge_identity": folded.bridge_identity,
            "manifest_id": folded.manifest_id,
            "grant_id": folded.grant_id,
            "manifest_digest": folded.manifest_digest,
            "entry_order": folded.entry_order,
            "observation_key": folded.observation_key,
            "history_delivery_identity": folded.delivery_identity,
            "occurrence": folded.occurrence,
            "workflow_cut": "observation_folded",
            "cut": "host_delivery_completed",
        }
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM delivery_custody").fetchone()[0] == 1
        with closing(sqlite3.connect(tmp_path / "dispatch.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM impetus_local_dispatch_tasks").fetchone()[0] == 0
        assert history_records(fixture) == folded_records


class TestFirstHistoryAcceptance:
    """The first bridge accepts only one exact unfinished Head occurrence."""

    @pytest.mark.parametrize(
        ("mergeable", "expected"),
        [
            pytest.param(None, False, id="unknown-is-false"),
            pytest.param(False, False, id="false-is-false"),
            pytest.param(True, True, id="true-is-true"),
        ],
    )
    def test_bridge_maps_each_mergeability_state_exactly(
        self,
        tmp_path: Path,
        *,
        mergeable: bool | None,
        expected: bool,
    ) -> None:
        fixture = prepare_acceptance(tmp_path, body=webhook_body(mergeable=mergeable))

        accepted = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        delivered, begun = history_records(fixture)[-2:]
        assert isinstance(delivered, ExternalEventDelivered)
        assert isinstance(begun, FiringBegun)
        assert delivered.source == begun.transition
        assert str(delivered.source) == "on_head"
        assert delivered.tokens[0].color == "HeadSeen"
        assert delivered.tokens[0].data == {
            "head": "a" * 40,
            "base": "b" * 40,
            "mergeable": expected,
            "policy": str(POLICY_REVISION),
            "strict_base": True,
            "base_current": False,
        }
        assert accepted.occurrence == delivered.occurrence == begun.occurrence
        assert not accepted.finished
        assert not accepted.folded

    def test_policy_comes_from_the_reconstructed_manifest(self, tmp_path: Path) -> None:
        retained_policy = PolicyRevision("policy:retained-authority")
        fixture = prepare_acceptance(tmp_path, policy_revision=retained_policy)

        accepted = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        delivered = history_records(fixture)[-2]
        assert isinstance(delivered, ExternalEventDelivered)
        assert fixture.staged.manifest.policy_revision == retained_policy
        assert delivered.tokens[0].data["policy"] == str(retained_policy)
        assert accepted.manifest_id == fixture.staged.manifest.manifest_id

    @pytest.mark.parametrize(
        ("manifest_update", "grant_update", "entry_update"),
        [
            pytest.param({"manifest_id": f"manifest:v1:sha256:{'f' * 64}"}, {}, {}, id="manifest"),
            pytest.param({}, {"grant_id": f"grant:v1:sha256:{'f' * 64}"}, {}, id="grant"),
            pytest.param({}, {"manifest_digest": "f" * 64}, {}, id="digest"),
            pytest.param({}, {}, {"order": 1}, id="entry-order"),
            pytest.param({}, {}, {"observation_key": f"obs:v1:sha256:{'f' * 64}"}, id="entry-key"),
        ],
    )
    def test_delivery_identity_is_sensitive_to_each_manifest_scoped_authority_field(
        self,
        tmp_path: Path,
        manifest_update: dict[str, object],
        grant_update: dict[str, object],
        entry_update: dict[str, object],
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        original_manifest = fixture.staged.manifest
        original_grant = fixture.staged.grant
        original_entry = original_manifest.entries[0]
        baseline = history_delivery_identity(
            manifest=original_manifest,
            grant=original_grant,
            entry=original_entry,
        )

        changed = history_delivery_identity(
            manifest=original_manifest.model_copy(update=manifest_update),
            grant=original_grant.model_copy(update=grant_update),
            entry=original_entry.model_copy(update=entry_update),
        )

        assert changed != baseline
        assert len(changed) == len(baseline) == 91

    def test_fresh_exact_reoffer_returns_the_same_occurrence_without_append(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        first = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        after_first = history_records(fixture)

        replayed = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert replayed == first
        assert history_records(fixture) == after_first
        assert len(after_first) == fixture.initial_history_records + 2

    def test_exact_reoffer_at_the_record_ceiling_needs_no_fresh_reservation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        monkeypatch.setattr(
            readiness_runtime,
            "MAX_HISTORY_RECORDS",
            fixture.initial_history_records + 2,
        )
        first = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        after_first = history_records(fixture)

        replayed = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert replayed == first
        assert history_records(fixture) == after_first
        assert len(after_first) == readiness_runtime.MAX_HISTORY_RECORDS

    def test_acceptance_calls_the_public_door_once_without_scope(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        entry = fixture.staged.manifest.entries[0]
        expected_identity = history_delivery_identity(
            manifest=fixture.staged.manifest,
            grant=fixture.staged.grant,
            entry=entry,
        )
        real_accept_delivery = Engine.accept_delivery
        calls: list[tuple[object, Token, dict[str, object]]] = []

        def record_acceptance(
            engine: Engine,
            source: object,
            token: Token,
            **arguments: object,
        ) -> object:
            calls.append((source, token, arguments))
            return real_accept_delivery(engine, source, token, **arguments)  # ty: ignore[invalid-argument-type]

        monkeypatch.setattr(Engine, "accept_delivery", record_acceptance)

        accepted = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert len(calls) == 1
        source, token, arguments = calls[0]
        assert source == "on_head"
        assert token.color == "HeadSeen"
        assert arguments == {"identity": str(expected_identity)}
        assert accepted.delivery_identity == expected_identity

    def test_prior_acknowledgement_becomes_a_bounded_ended_refusal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        entry = fixture.staged.manifest.entries[0]
        identity = history_delivery_identity(
            manifest=fixture.staged.manifest,
            grant=fixture.staged.grant,
            entry=entry,
        )

        def acknowledge_prior(*args: object, **kwargs: object) -> PriorAcknowledgement:
            del args, kwargs
            return PriorAcknowledgement(identity=str(identity), occurrence=7)

        monkeypatch.setattr(Engine, "accept_delivery", acknowledge_prior)

        posture = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert posture.reason == "occurrence_already_ended"
        assert posture.disposition == "refused"
        assert posture.delivery_identity == identity
        assert posture.occurrence == 7
        assert posture.finished
        assert not posture.folded
        assert len(history_records(fixture)) == fixture.initial_history_records

    def test_unexpected_scoped_acknowledgement_becomes_a_bounded_refusal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        entry = fixture.staged.manifest.entries[0]
        identity = history_delivery_identity(
            manifest=fixture.staged.manifest,
            grant=fixture.staged.grant,
            entry=entry,
        )

        def acknowledge_scoped(*args: object, **kwargs: object) -> ScopedDeliveryAcknowledgement:
            del args, kwargs
            return ScopedDeliveryAcknowledgement(
                identity=str(identity),
                disposition=DeliveryDisposition.DROPPED,
                scope="unexpected-scope",
            )

        monkeypatch.setattr(Engine, "accept_delivery", acknowledge_scoped)

        posture = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert posture.reason == "unexpected_scoped_acknowledgement"
        assert posture.disposition == "refused"
        assert posture.delivery_identity == identity
        assert posture.occurrence is None
        assert not posture.finished
        assert not posture.folded
        assert len(history_records(fixture)) == fixture.initial_history_records

    @pytest.mark.parametrize("acknowledgement", ["prior", "scoped"])
    def test_acknowledgement_for_another_identity_fails_closed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        acknowledgement: str,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)

        def acknowledge_other(*args: object, **kwargs: object) -> object:
            del args, kwargs
            if acknowledgement == "prior":
                return PriorAcknowledgement(identity="history-delivery:v1:sha256:" + "f" * 64, occurrence=7)
            return ScopedDeliveryAcknowledgement(
                identity="history-delivery:v1:sha256:" + "f" * 64,
                disposition=DeliveryDisposition.DROPPED,
                scope="unexpected-scope",
            )

        monkeypatch.setattr(Engine, "accept_delivery", acknowledge_other)

        with pytest.raises(readiness_runtime.HistoryAcceptanceError, match="acknowledgement_correlation_mismatch"):
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert len(history_records(fixture)) == fixture.initial_history_records

    def test_exact_same_acquisition_restaging_keeps_the_original_novel_authority_eligible(
        self,
        tmp_path: Path,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)

        duplicate = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=PolicyRevision("policy:changed-after-staging"),
        ).stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        accepted = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert duplicate.disposition == "exact_duplicate"
        assert duplicate.manifest == fixture.staged.manifest
        assert accepted.staging_disposition == "novel"
        assert accepted.disposition == "accepted"

    def test_concurrent_exact_acceptors_converge_on_one_occurrence(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)

        def accept() -> object:
            return build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (executor.submit(accept), executor.submit(accept))
            results = [future.result() for future in futures]

        assert results[0] == results[1]
        assert len(history_records(fixture)) == fixture.initial_history_records + 2

    def test_inner_reconstruction_preserves_the_configured_manifest_ceiling(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)
        ingress_path = tmp_path / "readiness-ingress.sqlite3"
        outer = IngressCustody.for_reconstruction(path=ingress_path, maximum_manifests=1)

        def append_manifest() -> None:
            build_staging_authority(
                state_root=tmp_path,
                provider_routes=(PROVIDER_ROUTE,),
                policy_revision=POLICY_REVISION,
            ).stage_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=SECOND_DELIVERY_ID,
            )

        wrapped = ManifestAppendingIngressCustody(outer, append_manifest)
        real_reconstruction = IngressCustody.for_reconstruction
        openings = 0

        def open_reconstruction(
            custody_type: type[IngressCustody],
            *,
            path: Path,
            maximum_manifests: int = readiness_ingress.MAX_MANIFESTS,
        ) -> IngressCustody:
            del custody_type
            nonlocal openings
            openings += 1
            if openings == 1:
                return wrapped
            return real_reconstruction(path=path, maximum_manifests=maximum_manifests)

        monkeypatch.setattr(IngressCustody, "for_reconstruction", classmethod(open_reconstruction))
        authority = build_observation_acceptance_authority(state_root=tmp_path, maximum_manifests=1)

        with pytest.raises(IngressCorruptionError):
            authority.accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert len(history_records(fixture)) == fixture.initial_history_records

    def test_history_byte_ceiling_refuses_before_engine_load_or_append(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = history_records(fixture)
        engine_loads = 0

        def reject_engine_load(*args: object, **kwargs: object) -> object:
            del args, kwargs
            nonlocal engine_loads
            engine_loads += 1
            raise AssertionError("over-ceiling History must fail before Engine load")

        monkeypatch.setattr(readiness_runtime, "MAX_HISTORY_BYTES", 1)
        monkeypatch.setattr(readiness_runtime, "load_engine", reject_engine_load)

        with pytest.raises(HistoryCapacityError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args[:2] == ("history_capacity_exceeded", "bytes")
        assert engine_loads == 0
        assert history_records(fixture) == before

    def test_history_acceptance_reserves_wal_growth_before_the_public_call(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = history_records(fixture)
        measurements = iter(
            (
                readiness_runtime.MAX_HISTORY_BYTES - readiness_runtime.MAX_HISTORY_ENGINE_LOAD_HEADROOM,
                readiness_runtime.MAX_HISTORY_BYTES - readiness_runtime.MAX_HISTORY_ACCEPTANCE_HEADROOM + 1,
            )
        )
        acceptance_calls = 0

        def measured_storage_bytes(path: Path) -> int:
            del path
            return next(measurements)

        def reject_acceptance(engine: Engine, *args: object, **kwargs: object) -> object:
            del engine, args, kwargs
            nonlocal acceptance_calls
            acceptance_calls += 1
            raise AssertionError("insufficient WAL headroom must fail before acceptance")

        monkeypatch.setattr(readiness_runtime, "history_storage_bytes", measured_storage_bytes)
        monkeypatch.setattr(Engine, "accept_delivery", reject_acceptance)

        with pytest.raises(HistoryCapacityError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "history_capacity_exceeded",
            "bytes",
            readiness_runtime.MAX_HISTORY_BYTES - readiness_runtime.MAX_HISTORY_ACCEPTANCE_HEADROOM + 1,
            readiness_runtime.MAX_HISTORY_BYTES,
        )
        assert acceptance_calls == 0
        assert history_records(fixture) == before

    def test_first_acceptance_growth_fits_its_reserved_storage_headroom(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = readiness_runtime.history_storage_bytes(fixture.history_path)

        build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        after = readiness_runtime.history_storage_bytes(fixture.history_path)
        assert after - before <= readiness_runtime.MAX_HISTORY_ACCEPTANCE_HEADROOM

    def test_malformed_acquisition_content_cannot_escape_through_acceptance_diagnostics(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = history_records(fixture)
        secret = "stored-acquisition-sentinel"
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection, connection:
            acquisition = json.loads(
                connection.execute("SELECT acquisition_bytes FROM ingress_manifests").fetchone()[0]
            )
            acquisition["webhook"]["snapshot"]["state"] = secret
            connection.execute(
                "UPDATE ingress_manifests SET acquisition_bytes = ?",
                (json.dumps(acquisition, separators=(",", ":"), sort_keys=True).encode(),),
            )

        with pytest.raises(IngressCorruptionError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable ingress rows failed strict reconstruction",
        )
        assert secret not in repr(raised.value)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        assert history_records(fixture) == before

    def test_malformed_observation_content_cannot_escape_through_acceptance_diagnostics(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = history_records(fixture)
        secret = "stored-observation-sentinel"
        observation = json.loads(CANONICAL_HEAD)
        observation["lifecycle_state"] = secret
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection, connection:
            connection.execute(
                "UPDATE ingress_entries SET canonical_bytes = ?",
                (json.dumps(observation, separators=(",", ":"), sort_keys=True).encode(),),
            )

        with pytest.raises(IngressCorruptionError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable ingress rows failed strict reconstruction",
        )
        assert secret not in repr(raised.value)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        assert history_records(fixture) == before

    def test_history_record_ceiling_refuses_before_acceptance_or_append(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = history_records(fixture)
        acceptance_calls = 0

        def reject_acceptance(engine: Engine, *args: object, **kwargs: object) -> object:
            del engine, args, kwargs
            nonlocal acceptance_calls
            acceptance_calls += 1
            raise AssertionError("over-ceiling History must fail before acceptance")

        monkeypatch.setattr(readiness_runtime, "MAX_HISTORY_RECORDS", fixture.initial_history_records - 1)
        monkeypatch.setattr(Engine, "accept_delivery", reject_acceptance)

        with pytest.raises(HistoryCapacityError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "history_capacity_exceeded",
            "records",
            fixture.initial_history_records,
            fixture.initial_history_records - 1,
        )
        assert acceptance_calls == 0
        assert history_records(fixture) == before

    @pytest.mark.parametrize(
        ("body", "shape"),
        [
            pytest.param(webhook_body(lifecycle_state="closed"), (1, "closed", False, False), id="closed"),
            pytest.param(webhook_body(draft=True), (1, "open", True, False), id="draft"),
            pytest.param(
                webhook_body(lifecycle_state="closed", merged=True),
                (1, "closed", False, True),
                id="merged",
            ),
        ],
    )
    def test_unsupported_head_lifecycle_fails_before_history_mutation(
        self,
        tmp_path: Path,
        body: bytes,
        shape: tuple[int, str, bool, bool],
    ) -> None:
        fixture = prepare_acceptance(tmp_path, body=body)

        with pytest.raises(UnsupportedHeadObservationError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == ("unsupported_head_lifecycle", shape)
        assert len(history_records(fixture)) == fixture.initial_history_records

    def test_bridge_rejects_a_later_local_incarnation_before_history_mutation(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        original_entry = fixture.staged.manifest.entries[0]
        changed_entry = observation_entry(original_entry.observation.model_copy(update={"local_incarnation": 2}))
        changed_manifest = fixture.staged.manifest.model_copy(update={"entries": (changed_entry,)})

        with pytest.raises(UnsupportedHeadObservationError) as raised:
            bridge_head_delivery(
                manifest=changed_manifest,
                grant=grant_for(changed_manifest),
                entry=changed_entry,
            )

        assert raised.value.args == ("unsupported_head_lifecycle", (2, "open", False, False))
        assert len(history_records(fixture)) == fixture.initial_history_records

    @pytest.mark.parametrize(
        "disposition",
        ["corroborating", "acquisition_collision", "semantic_collision", "conflicting", "incomparable"],
    )
    def test_non_novel_staging_never_enters_history(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        disposition: str,
    ) -> None:
        registered = open_registered_readiness(tmp_path)
        acquire_signed_delivery(tmp_path)
        selected_delivery_id = SECOND_DELIVERY_ID
        if disposition == "acquisition_collision":
            acquire_signed_delivery(tmp_path, body=webhook_body(head_sha=CommitSha("c" * 40)))
            selected_delivery_id = DELIVERY_ID
        else:
            if disposition == "semantic_collision":
                force_observation_key_collision(monkeypatch)
            bodies = {
                "corroborating": webhook_body(),
                "semantic_collision": webhook_body(head_sha=CommitSha("c" * 40)),
                "conflicting": webhook_body(draft=True),
                "incomparable": webhook_body(head_sha=CommitSha("c" * 40)),
            }
            acquire_signed_delivery(
                tmp_path,
                delivery_id=SECOND_DELIVERY_ID,
                body=bodies[disposition],
            )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        if disposition != "acquisition_collision":
            authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        staged = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=selected_delivery_id,
        )
        fixture = AcceptanceFixture(
            root=tmp_path,
            registered=registered,
            staged=staged,
            initial_history_records=0,
        )
        before = history_records(fixture)

        refused = build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=selected_delivery_id,
        )

        assert staged.disposition == disposition
        assert refused.disposition == "refused"
        assert refused.reason == "staging_not_novel"
        assert refused.staging_disposition == disposition
        assert refused.delivery_identity is None
        assert refused.occurrence is None
        assert history_records(fixture) == before

    def test_unearned_stale_staging_fails_strict_reconstruction_without_history_mutation(
        self,
        tmp_path: Path,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection, connection:
            connection.execute("UPDATE ingress_manifests SET original_disposition = 'stale'")
            connection.execute(
                """
                UPDATE admission_decisions
                SET disposition = 'stale', reason = 'ordered_before',
                    fatal = 0, refresh_required = 0
                """
            )

        with pytest.raises(IngressCorruptionError):
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert len(history_records(fixture)) == fixture.initial_history_records

    @pytest.mark.parametrize(
        ("statement", "parameters"),
        [
            pytest.param(
                "UPDATE ingress_manifests SET manifest_id = ?",
                (f"manifest:v1:sha256:{'f' * 64}",),
                id="manifest",
            ),
            pytest.param(
                "UPDATE ingress_manifests SET policy_revision = 'policy:changed'",
                (),
                id="policy",
            ),
            pytest.param(
                "UPDATE ingress_entries SET entry_order = 1",
                (),
                id="entry-order",
            ),
            pytest.param(
                "UPDATE ingress_entries SET observation_key = ?",
                (f"obs:v1:sha256:{'f' * 64}",),
                id="entry-key",
            ),
            pytest.param(
                "UPDATE admission_grants SET manifest_digest = ?",
                ("f" * 64,),
                id="grant",
            ),
            pytest.param(
                "UPDATE admission_decisions SET reason = 'same_semantics'",
                (),
                id="decision",
            ),
        ],
    )
    def test_mutated_staging_authority_fails_before_history_mutation(
        self,
        tmp_path: Path,
        statement: str,
        parameters: tuple[object, ...],
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection, connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(statement, parameters)

        with pytest.raises(IngressCorruptionError):
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert len(history_records(fixture)) == fixture.initial_history_records

    def test_unknown_subject_is_not_auto_registered_for_history_acceptance(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        ).stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        with pytest.raises(PullRequestNotRegisteredError):
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "catalog.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM subject_roots").fetchone()[0] == 0
        assert not list(tmp_path.rglob("history.sqlite3"))

    def test_registered_but_unopened_root_fails_before_history_creation(self, tmp_path: Path) -> None:
        subject = PullRequestSubject(installation_id=44, repository_id=31, pull_request_number=7)
        command = OpenPullRequestCommand(action_identity=ActionIdentity("trace:open:1"), subject=subject)
        build_hamsterdan(state_root=tmp_path).register(command)
        acquire_signed_delivery(tmp_path)
        build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        ).stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        with pytest.raises(ReadinessRootMissingError):
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert not list(tmp_path.rglob("history.sqlite3"))

    def test_mismatched_catalog_root_cannot_redirect_history_acceptance(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        with closing(sqlite3.connect(tmp_path / "catalog.sqlite3")) as connection, connection:
            connection.execute("UPDATE subject_roots SET readiness_root = 'instances/44/31/8'")

        with pytest.raises(SubjectRootConflictError):
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert len(history_records(fixture)) == fixture.initial_history_records
        assert not (tmp_path / "instances/44/31/8/history.sqlite3").exists()

    def test_catalog_binding_cannot_redirect_acceptance_to_another_valid_open_root(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        other_subject = PullRequestSubject(installation_id=44, repository_id=31, pull_request_number=8)
        other_command = OpenPullRequestCommand(
            action_identity=ActionIdentity("trace:open:2"),
            subject=other_subject,
        )
        host = build_hamsterdan(state_root=tmp_path)
        other = host.register(other_command)
        host.step(other_command)
        other_history_path = tmp_path / other.readiness_root / "history.sqlite3"
        other_history = SqliteHistoryStore(other_history_path, other.instance_id)
        try:
            other_before = other_history.records
        finally:
            other_history.close()
        with closing(sqlite3.connect(tmp_path / "catalog.sqlite3")) as connection, connection:
            connection.execute(
                """
                UPDATE subject_roots
                SET instance_id = 'temporary', readiness_root = 'instances/99/99/99'
                WHERE pull_request_number = 7
                """
            )
            connection.execute(
                """
                UPDATE subject_roots SET instance_id = ?, readiness_root = ?
                WHERE pull_request_number = 8
                """,
                (fixture.registered.instance_id, fixture.registered.readiness_root),
            )
            connection.execute(
                """
                UPDATE subject_roots SET instance_id = ?, readiness_root = ?
                WHERE pull_request_number = 7
                """,
                (other.instance_id, other.readiness_root),
            )

        with pytest.raises(SubjectRootConflictError):
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert len(history_records(fixture)) == fixture.initial_history_records
        other_history = SqliteHistoryStore(other_history_path, other.instance_id)
        try:
            assert other_history.records == other_before
        finally:
            other_history.close()

    @pytest.mark.parametrize(
        ("instance_id", "readiness_root"),
        [
            pytest.param(
                "github:44:31:pr:7",
                "instances/44/31/7",
                id="duplicate",
            ),
            pytest.param(
                "github:44:31:pr:8",
                "instances/44/31/8",
                id="conflicting",
            ),
        ],
    )
    def test_duplicate_catalog_authority_fails_before_history_mutation(
        self,
        tmp_path: Path,
        instance_id: str,
        readiness_root: str,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = history_records(fixture)
        duplicate_subject_registration(
            fixture,
            instance_id=instance_id,
            readiness_root=readiness_root,
        )

        with pytest.raises(HostCatalogCorruptionError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "duplicate_subject_registration",
            (44, 31, 7),
            2,
            "replace the malformed host catalog before requesting readiness authority",
        )
        assert history_records(fixture) == before

    @pytest.mark.parametrize(
        ("instance_id", "readiness_root"),
        [
            pytest.param(7, "instances/44/31/7", id="wrong-type-instance"),
            pytest.param("github:44:31:pr:7", "r" * 129, id="oversized-root"),
        ],
    )
    def test_invalid_exact_catalog_authority_fails_with_bounded_diagnostic_before_history_mutation(
        self,
        tmp_path: Path,
        instance_id: object,
        readiness_root: object,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = history_records(fixture)
        replace_subject_registration(
            fixture,
            instance_id=instance_id,
            readiness_root=readiness_root,
        )

        with pytest.raises(HostCatalogCorruptionError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "invalid_subject_registration",
            (44, 31, 7),
            "replace the malformed host catalog before requesting readiness authority",
        )
        assert history_records(fixture) == before

    @pytest.mark.parametrize(
        ("singleton", "instance_id", "bridge_identity"),
        [
            pytest.param(
                1,
                "github:44:31:pr:7",
                "workflow-bridge/head-seen-history-fold@3",
                id="duplicate",
            ),
            pytest.param(
                1,
                "github:44:31:pr:8",
                "workflow-bridge/mutated@1",
                id="conflicting",
            ),
        ],
    )
    def test_duplicate_readiness_root_authority_fails_before_history_mutation(
        self,
        tmp_path: Path,
        singleton: int,
        instance_id: str,
        bridge_identity: str,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = history_records(fixture)
        duplicate_readiness_root_binding(
            fixture,
            singleton=singleton,
            instance_id=instance_id,
            bridge_identity=bridge_identity,
        )

        with pytest.raises(ReadinessRootCorruptionError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "duplicate_root_binding",
            "github:44:31:pr:7",
            2,
            "replace the malformed readiness root before requesting authority",
        )
        assert history_records(fixture) == before

    @pytest.mark.parametrize(
        ("singleton", "instance_id", "bridge_identity"),
        [
            pytest.param(
                2,
                "github:44:31:pr:7",
                "workflow-bridge/head-seen-history-fold@3",
                id="invalid-singleton",
            ),
            pytest.param(
                1,
                7,
                "workflow-bridge/head-seen-history-fold@3",
                id="wrong-type-instance",
            ),
            pytest.param(
                1,
                "github:44:31:pr:7",
                "b" * 129,
                id="oversized-bridge",
            ),
        ],
    )
    def test_invalid_exact_readiness_root_authority_fails_with_bounded_diagnostic_before_history_mutation(
        self,
        tmp_path: Path,
        singleton: object,
        instance_id: object,
        bridge_identity: object,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        before = history_records(fixture)
        replace_readiness_root_binding(
            fixture,
            singleton=singleton,
            instance_id=instance_id,
            bridge_identity=bridge_identity,
        )

        with pytest.raises(ReadinessRootCorruptionError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "invalid_root_binding",
            "github:44:31:pr:7",
            "replace the malformed readiness root before requesting authority",
        )
        assert history_records(fixture) == before

    def test_malformed_history_fails_loud_without_manufacturing_acceptance(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        with closing(sqlite3.connect(fixture.history_path)) as connection, connection:
            connection.execute("DELETE FROM impetus_history_events WHERE position = 22")
            before = connection.execute("SELECT COUNT(*) FROM impetus_history_events").fetchone()[0]

        with pytest.raises(readiness_runtime.HistoryCorruptionError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "malformed_canonical_history",
            fixture.registered.instance_id,
            "replace the malformed History before requesting readiness authority",
        )
        with closing(sqlite3.connect(fixture.history_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM impetus_history_events").fetchone()[0] == before

    def test_malformed_history_never_exposes_stored_content_in_its_exception_chain(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        sentinel = "stored-secret-must-not-escape"
        with closing(sqlite3.connect(fixture.history_path)) as connection, connection:
            connection.execute(
                "UPDATE impetus_history_events SET payload = ? WHERE position = 0",
                (json.dumps({"record": sentinel, "schema": 5}),),
            )

        with pytest.raises(readiness_runtime.HistoryCorruptionError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "malformed_canonical_history",
            fixture.registered.instance_id,
            "replace the malformed History before requesting readiness authority",
        )
        assert sentinel not in str(raised.value)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None

    def test_deeply_nested_history_payload_has_the_same_bounded_corruption_error(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        nested_payload = "[" * 100_000 + "0" + "]" * 100_000
        with closing(sqlite3.connect(fixture.history_path)) as connection, connection:
            connection.execute(
                "UPDATE impetus_history_events SET payload = ? WHERE position = 0",
                (nested_payload,),
            )

        with pytest.raises(readiness_runtime.HistoryCorruptionError) as raised:
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "malformed_canonical_history",
            fixture.registered.instance_id,
            "replace the malformed History before requesting readiness authority",
        )
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None

    def test_changed_history_content_under_one_identity_is_a_collision(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        with closing(sqlite3.connect(fixture.history_path)) as connection, connection:
            row = connection.execute(
                "SELECT payload FROM impetus_history_events WHERE record_type = 'ExternalEventDelivered'"
            ).fetchone()
            assert row is not None
            payload = json.loads(row[0])
            payload["tokens"][0]["data"]["mergeable"] = True
            connection.execute(
                """
                UPDATE impetus_history_events SET payload = ?
                WHERE record_type = 'ExternalEventDelivered'
                """,
                (json.dumps(payload, separators=(",", ":")),),
            )
            before = connection.execute("SELECT COUNT(*) FROM impetus_history_events").fetchone()[0]

        with pytest.raises(ValueError, match="canonical token content differs"):
            build_observation_acceptance_authority(state_root=tmp_path).accept_staged_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        with closing(sqlite3.connect(fixture.history_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM impetus_history_events").fetchone()[0] == before


class TestExactObservationFoldAndHostCompletion:
    """The accepted occurrence folds once before a separate host receipt exists."""

    def test_fold_reoffers_and_completes_the_exact_public_carrier_once(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        accepted = authority.accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        real_accept = Engine.accept_delivery
        real_complete = Engine.complete_delivery
        recovered: list[AcceptedDelivery] = []
        completed: list[AcceptedDelivery] = []
        offers: list[tuple[object, object, dict[str, object]]] = []

        def record_offer(engine: Engine, source: object, token: object, **arguments: object) -> object:
            result = real_accept(engine, source, token, **arguments)  # ty: ignore[invalid-argument-type]
            offers.append((source, token, arguments))
            assert isinstance(result, AcceptedDelivery)
            recovered.append(result)
            return result

        def record_completion(engine: Engine, carrier: AcceptedDelivery) -> object:
            completed.append(carrier)
            return real_complete(engine, carrier)

        monkeypatch.setattr(Engine, "accept_delivery", record_offer)
        monkeypatch.setattr(Engine, "complete_delivery", record_completion)

        folded = authority.fold_accepted_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert isinstance(folded, ObservationFoldPosture)
        assert len(offers) == len(recovered) == len(completed) == 1
        source, token, arguments = offers[0]
        assert source == "on_head"
        assert (
            token
            == bridge_head_delivery(
                manifest=fixture.staged.manifest,
                grant=fixture.staged.grant,
                entry=fixture.staged.manifest.entries[0],
            ).token
        )
        assert arguments == {"identity": str(accepted.delivery_identity)}
        assert completed[0] is recovered[0]
        assert recovered[0].instance == fixture.registered.instance_id
        assert recovered[0].identity == accepted.delivery_identity
        assert recovered[0].occurrence == accepted.occurrence

    def test_fresh_fold_retry_validates_prior_success_without_completing_or_appending(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        first = authority.fold_accepted_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        before = history_records(fixture)
        real_history_page = Engine.history_page
        history_pages = 0

        def count_history_page(engine: Engine, after: int, limit: int) -> dict[str, object]:
            nonlocal history_pages
            history_pages += 1
            return real_history_page(engine, after, limit)

        def reject_completion(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise AssertionError("an ended exact reoffer must not call completion")

        monkeypatch.setattr(Engine, "history_page", count_history_page)
        monkeypatch.setattr(Engine, "complete_delivery", reject_completion)

        replayed = build_observation_acceptance_authority(state_root=tmp_path).fold_accepted_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert replayed == first
        assert history_pages == 1
        assert history_records(fixture) == before

    def test_host_completion_before_fold_refuses_without_writing(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        before = history_records(fixture)

        with pytest.raises(ObservationNotFoldedError) as raised:
            authority.complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args[0] == "observation_not_folded"
        assert history_records(fixture) == before
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 0

    def test_changed_canonical_custody_after_fold_cannot_authorize_host_completion(self, tmp_path: Path) -> None:
        prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            stored = json.loads(connection.execute("SELECT canonical_content FROM delivery_custody").fetchone()[0])
            stored["snapshot"]["head"]["sha"] = "c" * 40
            changed = json.dumps(stored, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
            connection.execute(
                "UPDATE delivery_custody SET canonical_content = ?, content_digest = ?",
                (changed, sha256(changed.encode()).hexdigest()),
            )

        with pytest.raises(DeliveryCompletionCorruptionError):
            authority.complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 0

    def test_changed_custody_digest_after_fold_cannot_authorize_host_completion(self, tmp_path: Path) -> None:
        prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("UPDATE delivery_custody SET content_digest = ?", ("f" * 64,))

        with pytest.raises(DeliveryCompletionCorruptionError):
            authority.complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 0

    def test_malformed_custody_collision_after_fold_cannot_authorize_host_completion(self, tmp_path: Path) -> None:
        prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE delivery_custody SET disposition = 'quarantined', collision_digest = NULL")

        with pytest.raises(DeliveryCompletionCorruptionError):
            authority.complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 0

    def test_orphaned_host_completion_cannot_be_reconstructed(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        expected_delivery = reconstructed_custodied_delivery(fixture)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.complete_observation_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DELETE FROM delivery_custody")

        with pytest.raises(DeliveryCompletionCorruptionError):
            DeliveryCompletionCustody.from_path(path=tmp_path / "deliveries.sqlite3").completion_receipt(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
                expected_delivery=expected_delivery,
            )

    def test_fresh_exact_host_completion_retry_returns_receipt_without_insert_or_history_append(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        first = authority.complete_observation_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        before = history_records(fixture)

        def reject_append(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise AssertionError("an exact host completion retry must not insert")

        monkeypatch.setattr(DeliveryCompletionCustody, "append_completion", reject_append)

        replayed = build_observation_acceptance_authority(state_root=tmp_path).complete_observation_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert replayed == first
        assert history_records(fixture) == before
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 1

    def test_host_completion_backend_refusal_exposes_only_fixed_cause_and_fresh_load_decides(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        sentinel = "backend-secret-sentinel"

        def refuse_append(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise sqlite3.OperationalError(sentinel)

        monkeypatch.setattr(DeliveryCompletionCustody, "append_completion", refuse_append)

        with pytest.raises(DeliveryCompletionCommitError) as raised:
            authority.complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == (
            "host_completion_commit_unknown",
            "reload host delivery custody before deciding whether completion committed",
        )
        assert sentinel not in repr(raised.value)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 0
        monkeypatch.undo()
        recovered = build_observation_acceptance_authority(state_root=tmp_path).complete_observation_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        assert recovered.cut == "host_delivery_completed"
        assert len(history_records(fixture)) == fixture.initial_history_records + 4

    def test_non_novel_staging_cannot_fold_or_complete_host_delivery(self, tmp_path: Path) -> None:
        registered = open_registered_readiness(tmp_path)
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, body=webhook_body(head_sha=CommitSha("c" * 40)))
        staged = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        ).stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        fixture = AcceptanceFixture(
            root=tmp_path,
            registered=registered,
            staged=staged,
            initial_history_records=0,
        )
        before = history_records(fixture)
        authority = build_observation_acceptance_authority(state_root=tmp_path)

        folded = authority.fold_accepted_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        with pytest.raises(ObservationDeliveryNotFoldedError):
            authority.complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert staged.disposition == "acquisition_collision"
        assert not isinstance(folded, ObservationFoldPosture)
        assert folded.reason == "staging_not_novel"
        assert not folded.folded
        assert history_records(fixture) == before
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 0

    def test_late_custody_collision_preserves_original_fold_and_host_completion(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        accepted = authority.accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        collision = acquire_signed_delivery(
            tmp_path,
            body=webhook_body(head_sha=CommitSha("c" * 40)),
        )
        folded = authority.fold_accepted_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        completed = authority.complete_observation_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        retained = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        ).retained_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert collision["disposition"] == "quarantined"
        assert retained is not None
        assert retained.quarantined
        assert retained.webhook.snapshot.head.sha == DEFAULT_HEAD_SHA
        assert isinstance(folded, ObservationFoldPosture)
        assert folded.delivery_identity == accepted.delivery_identity
        assert folded.head.sha == DEFAULT_HEAD_SHA
        assert completed.history_delivery_identity == accepted.delivery_identity
        assert completed.custody_generation == retained.custody_generation == 1
        assert fixture.staged == build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=PolicyRevision("policy:later"),
        ).staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

    def test_changed_accepted_occurrence_is_rejected_before_completion(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        accepted = authority.accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        real_accept = Engine.accept_delivery
        completion_calls = 0

        def changed_occurrence(engine: Engine, *args: object, **kwargs: object) -> AcceptedDelivery:
            result = real_accept(engine, *args, **kwargs)  # ty: ignore[invalid-argument-type]
            assert isinstance(result, AcceptedDelivery)
            return AcceptedDelivery(result.instance, result.source, result.identity, result.occurrence + 1)

        def reject_completion(*args: object, **kwargs: object) -> object:
            del args, kwargs
            nonlocal completion_calls
            completion_calls += 1
            raise AssertionError("mismatched recovered occurrence must fail before completion")

        monkeypatch.setattr(Engine, "accept_delivery", changed_occurrence)
        monkeypatch.setattr(Engine, "complete_delivery", reject_completion)

        with pytest.raises(readiness_runtime.HistoryAcceptanceError, match="accepted_delivery_correlation_mismatch"):
            authority.fold_accepted_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert completion_calls == 0
        assert len(history_records(fixture)) == fixture.initial_history_records + 2
        assert accepted.occurrence is not None

    def test_recorded_occurrence_two_is_rejected_before_completion(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        accepted = authority.accept_staged_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        real_history_page = Engine.history_page
        completion_calls = 0

        def changed_history_page(engine: Engine, after: int, limit: int) -> dict[str, object]:
            page = deepcopy(real_history_page(engine, after, limit))
            return replace_accepted_occurrence(page, 2)

        def changed_acceptance(*args: object, **kwargs: object) -> AcceptedDelivery:
            del args, kwargs
            assert accepted.delivery_identity is not None
            return AcceptedDelivery(
                fixture.registered.instance_id,
                "on_head",
                str(accepted.delivery_identity),
                2,
            )

        def reject_completion(*args: object, **kwargs: object) -> object:
            del args, kwargs
            nonlocal completion_calls
            completion_calls += 1
            raise AssertionError("occurrence 2 must fail before completion")

        monkeypatch.setattr(Engine, "history_page", changed_history_page)
        monkeypatch.setattr(Engine, "accept_delivery", changed_acceptance)
        monkeypatch.setattr(Engine, "complete_delivery", reject_completion)

        with pytest.raises(readiness_runtime.HistoryAcceptanceError, match="accepted_delivery_occurrence_mismatch"):
            authority.fold_accepted_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert completion_calls == 0
        assert len(history_records(fixture)) == fixture.initial_history_records + 2

    def test_prior_acknowledgement_for_another_occurrence_fails_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        accepted = authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        before = history_records(fixture)

        def wrong_occurrence(*args: object, **kwargs: object) -> PriorAcknowledgement:
            del args, kwargs
            assert accepted.delivery_identity is not None
            assert accepted.occurrence is not None
            return PriorAcknowledgement(str(accepted.delivery_identity), accepted.occurrence + 1)

        monkeypatch.setattr(Engine, "accept_delivery", wrong_occurrence)

        with pytest.raises(
            readiness_runtime.HistoryAcceptanceError, match="prior_acknowledgement_correlation_mismatch"
        ):
            build_observation_acceptance_authority(state_root=tmp_path).fold_accepted_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert history_records(fixture) == before

    def test_changed_host_completion_correlation_never_overwrites(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        original = authority.complete_observation_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("UPDATE delivery_completions SET occurrence = occurrence + 1")

        with pytest.raises(DeliveryCompletionCorruptionError):
            build_observation_acceptance_authority(state_root=tmp_path).complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            row = connection.execute("SELECT occurrence FROM delivery_completions").fetchone()
        assert row == (original.occurrence + 1,)
        assert len(history_records(fixture)) == fixture.initial_history_records + 4

    def test_duplicate_host_completion_rows_fail_bounded_reconstruction(self, tmp_path: Path) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.complete_observation_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("ALTER TABLE delivery_completions RENAME TO original_delivery_completions")
            connection.execute("CREATE TABLE delivery_completions AS SELECT * FROM original_delivery_completions")
            connection.execute("INSERT INTO delivery_completions SELECT * FROM original_delivery_completions")
            connection.execute("DROP TABLE original_delivery_completions")

        with pytest.raises(DeliveryCompletionCorruptionError) as raised:
            authority.complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert raised.value.args == ("duplicate_host_completion", PROVIDER_ROUTE_ID, DELIVERY_ID)
        assert len(history_records(fixture)) == fixture.initial_history_records + 4

    @pytest.mark.parametrize(
        "statement",
        [
            "UPDATE delivery_completions SET custody_generation = 'bad'",
            "UPDATE delivery_completions SET installation_id = 'bad'",
            "UPDATE delivery_completions SET repository_id = 'bad'",
            "UPDATE delivery_completions SET pull_request_number = 'bad'",
            "UPDATE delivery_completions SET instance_id = zeroblob(129)",
            "UPDATE delivery_completions SET bridge_identity = 'wrong'",
            "UPDATE delivery_completions SET manifest_id = zeroblob(1000000)",
            "UPDATE delivery_completions SET grant_id = zeroblob(1000000)",
            "UPDATE delivery_completions SET manifest_digest = zeroblob(1000000)",
            "UPDATE delivery_completions SET entry_order = 'bad'",
            "UPDATE delivery_completions SET observation_key = zeroblob(1000000)",
            "UPDATE delivery_completions SET history_delivery_identity = zeroblob(1000000)",
            "UPDATE delivery_completions SET occurrence = 'bad'",
            "UPDATE delivery_completions SET workflow_cut = 'wrong'",
            "UPDATE delivery_completions SET cut = 'wrong'",
        ],
    )
    def test_each_malformed_host_completion_field_fails_bounded_reconstruction(
        self,
        tmp_path: Path,
        statement: str,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.complete_observation_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(statement)

        with pytest.raises(DeliveryCompletionCorruptionError):
            authority.complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 1
        assert len(history_records(fixture)) == fixture.initial_history_records + 4

    @pytest.mark.parametrize(
        ("statement", "parameters"),
        [
            ("UPDATE delivery_completions SET custody_generation = custody_generation + 1", ()),
            (
                "UPDATE delivery_completions SET installation_id = ?, instance_id = ?",
                (45, "github:45:31:pr:7"),
            ),
            ("UPDATE delivery_completions SET manifest_id = ?", (f"manifest:v1:sha256:{'f' * 64}",)),
            ("UPDATE delivery_completions SET grant_id = ?", (f"grant:v1:sha256:{'f' * 64}",)),
            ("UPDATE delivery_completions SET manifest_digest = ?", ("f" * 64,)),
            ("UPDATE delivery_completions SET entry_order = ?", (1,)),
            ("UPDATE delivery_completions SET observation_key = ?", (f"obs:v1:sha256:{'f' * 64}",)),
            (
                "UPDATE delivery_completions SET history_delivery_identity = ?",
                (f"history-delivery:v1:sha256:{'f' * 64}",),
            ),
        ],
    )
    def test_each_changed_host_completion_correlation_fails_without_overwrite(
        self,
        tmp_path: Path,
        statement: str,
        parameters: tuple[object, ...],
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.complete_observation_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute(statement, parameters)
            changed = connection.execute("SELECT * FROM delivery_completions").fetchone()

        with pytest.raises(DeliveryCompletionConflictError):
            authority.complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT * FROM delivery_completions").fetchone() == changed
        assert len(history_records(fixture)) == fixture.initial_history_records + 4

    @pytest.mark.parametrize("field", ["transition", "occurrence", "consumed", "produced", "records"])
    def test_each_firing_outcome_correlation_field_is_validated(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        field: str,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        real_complete = Engine.complete_delivery

        def changed_outcome(engine: Engine, carrier: AcceptedDelivery) -> FiringOutcome:
            outcome = real_complete(engine, carrier)
            changes = {
                "transition": {"transition": NetPath("on_runs")},
                "occurrence": {"occurrence": outcome.occurrence + 1},
                "consumed": {"consumed": (Token.black(),)},
                "produced": {"produced": ()},
                "records": {"records": outcome.records[:-1]},
            }
            return replace(outcome, **changes[field])

        monkeypatch.setattr(Engine, "complete_delivery", changed_outcome)

        with pytest.raises(WorkflowBridgeError, match="firing_outcome_correlation_mismatch"):
            authority.fold_accepted_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert len(history_records(fixture)) == fixture.initial_history_records + 4
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 0
        recovered = build_observation_acceptance_authority(state_root=tmp_path).fold_accepted_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        assert isinstance(recovered, ObservationFoldPosture)

    @pytest.mark.parametrize(
        "mutation",
        [
            "terminal-order",
            "produced-content",
            "partial-terminal",
            "failed-terminal",
            "unrelated-terminal",
            "prior-failure",
        ],
    )
    def test_prior_success_requires_exact_complete_terminal_history(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mutation: str,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        before = history_records(fixture)
        real_history_page = Engine.history_page

        def changed_history_page(engine: Engine, after: int, limit: int) -> dict[str, object]:
            page = deepcopy(real_history_page(engine, after, limit))
            return mutate_history_page(page, mutation)

        monkeypatch.setattr(Engine, "history_page", changed_history_page)

        with pytest.raises(RetainedSnapshotRejectedError):
            build_observation_acceptance_authority(state_root=tmp_path).fold_accepted_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert history_records(fixture) == before

    def test_fold_record_capacity_refuses_before_completion_write(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        before = history_records(fixture)
        monkeypatch.setattr(readiness_runtime, "MAX_HISTORY_RECORDS", len(before) + 1)
        completion_calls = 0

        def reject_completion(*args: object, **kwargs: object) -> object:
            del args, kwargs
            nonlocal completion_calls
            completion_calls += 1
            raise AssertionError("record capacity must fail before completion")

        monkeypatch.setattr(Engine, "complete_delivery", reject_completion)

        with pytest.raises(HistoryCapacityError) as raised:
            authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            "history_capacity_exceeded",
            "records",
            len(before),
            len(before) + 1,
        )
        assert completion_calls == 0
        assert history_records(fixture) == before

    def test_fold_remeasures_wal_headroom_before_completion_write(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        before = history_records(fixture)
        measurements = iter(
            (
                readiness_runtime.MAX_HISTORY_BYTES - readiness_runtime.MAX_HISTORY_ENGINE_LOAD_HEADROOM,
                readiness_runtime.MAX_HISTORY_BYTES - readiness_runtime.MAX_HISTORY_COMPLETION_HEADROOM + 1,
            )
        )
        completion_calls = 0

        def measured_storage(path: Path) -> int:
            del path
            return next(measurements)

        def reject_completion(*args: object, **kwargs: object) -> object:
            del args, kwargs
            nonlocal completion_calls
            completion_calls += 1
            raise AssertionError("byte capacity must fail before completion")

        monkeypatch.setattr(readiness_runtime, "history_storage_bytes", measured_storage)
        monkeypatch.setattr(Engine, "complete_delivery", reject_completion)

        with pytest.raises(HistoryCapacityError) as raised:
            authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args[0:2] == ("history_capacity_exceeded", "bytes")
        assert completion_calls == 0
        assert history_records(fixture) == before

    def test_ended_fold_retry_reserves_no_completion_append_headroom(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        first = authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        before = history_records(fixture)
        monkeypatch.setattr(readiness_runtime, "MAX_HISTORY_RECORDS", len(before))
        monkeypatch.setattr(readiness_runtime, "MAX_HISTORY_COMPLETION_HEADROOM", readiness_runtime.MAX_HISTORY_BYTES)

        replayed = build_observation_acceptance_authority(state_root=tmp_path).fold_accepted_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert replayed == first
        assert history_records(fixture) == before

    def test_concurrent_exact_fold_and_host_completion_serialize_and_converge(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        entered_completion = Event()
        allow_completion = Event()
        completion_started = Event()
        real_complete = Engine.complete_delivery

        def paused_completion(engine: Engine, carrier: AcceptedDelivery) -> FiringOutcome:
            entered_completion.set()
            assert allow_completion.wait(timeout=5)
            return real_complete(engine, carrier)

        def complete_host() -> HostDeliveryCompletionReceipt:
            completion_started.set()
            return build_observation_acceptance_authority(state_root=tmp_path).complete_observation_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        monkeypatch.setattr(Engine, "complete_delivery", paused_completion)
        with ThreadPoolExecutor(max_workers=2) as executor:
            folded_future = executor.submit(
                authority.fold_accepted_observation,
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )
            assert entered_completion.wait(timeout=5)
            completed_future = executor.submit(complete_host)
            assert completion_started.wait(timeout=5)
            allow_completion.set()
            folded = folded_future.result(timeout=5)
            completed = completed_future.result(timeout=5)

        assert isinstance(folded, ObservationFoldPosture)
        assert completed.history_delivery_identity == folded.delivery_identity
        assert len(history_records(fixture)) == fixture.initial_history_records + 4
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 1

    def test_ambiguous_completion_error_exposes_no_backend_content_and_fresh_load_decides(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        real_complete = Engine.complete_delivery
        sentinel = "backend-secret-sentinel"

        def commit_then_lose_ack(engine: Engine, carrier: AcceptedDelivery) -> object:
            real_complete(engine, carrier)
            raise RuntimeError(sentinel)

        monkeypatch.setattr(Engine, "complete_delivery", commit_then_lose_ack)

        with pytest.raises(ObservationFoldCommitError) as raised:
            authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            "observation_fold_commit_unknown",
            fixture.registered.instance_id,
            "reload canonical History before deciding whether the observation folded",
        )
        assert sentinel not in repr(raised.value)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None
        assert len(history_records(fixture)) == fixture.initial_history_records + 4
        monkeypatch.setattr(Engine, "complete_delivery", real_complete)
        recovered = build_observation_acceptance_authority(state_root=tmp_path).fold_accepted_observation(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        assert isinstance(recovered, ObservationFoldPosture)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            assert connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0] == 0

    @pytest.mark.parametrize("mutation", ["status", "in-flight", "life-phase", "head-token"])
    def test_each_retained_projection_field_is_proven_from_actual_runtime_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mutation: str,
    ) -> None:
        fixture = prepare_acceptance(tmp_path)
        authority = build_observation_acceptance_authority(state_root=tmp_path)
        authority.accept_staged_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.fold_accepted_observation(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        before = history_records(fixture)
        real_snapshot = Engine.snapshot

        def changed_snapshot(engine: Engine) -> dict[str, object]:
            snapshot = deepcopy(real_snapshot(engine))
            return mutate_runtime_snapshot(snapshot, mutation)

        monkeypatch.setattr(Engine, "snapshot", changed_snapshot)

        with pytest.raises(RetainedSnapshotRejectedError):
            build_observation_acceptance_authority(state_root=tmp_path).fold_accepted_observation(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        assert history_records(fixture) == before


class TestStagingClassification:
    """Durable acquisition and Head relationships have closed finite outcomes."""

    def test_exact_reoffer_reconstructs_original_authority_without_a_second_entry(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        first_authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        first = first_authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        duplicate = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=PolicyRevision("policy:changed-after-retention"),
        ).stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert duplicate.disposition == "exact_duplicate"
        assert duplicate.manifest == first.manifest
        assert duplicate.grant == first.grant
        assert duplicate.decisions == first.decisions
        assert duplicate.manifest.policy_revision == POLICY_REVISION
        assert len(duplicate.manifest.entries) == 1

    def test_distinct_acquisition_with_identical_semantics_is_corroborating(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        first = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        corroborating = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=SECOND_DELIVERY_ID,
        )

        assert first.disposition == "novel"
        assert corroborating.disposition == "corroborating"
        assert corroborating.manifest.entries[0].observation_key == first.manifest.entries[0].observation_key
        assert corroborating.manifest.entries[0].canonical_bytes == first.manifest.entries[0].canonical_bytes
        assert corroborating.decisions[0].reason == "same_semantics"

    def test_quarantined_acquisition_gets_one_empty_collision_manifest(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        collision_receipt = acquire_signed_delivery(
            tmp_path,
            body=webhook_body(head_sha=CommitSha("c" * 40)),
        )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )

        collision = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert collision_receipt["disposition"] == "quarantined"
        assert collision.disposition == "acquisition_collision"
        assert collision.manifest.entries == ()
        assert [decision.model_dump(mode="json") for decision in collision.decisions] == [
            {
                "entry_order": None,
                "observation_key": None,
                "disposition": "acquisition_collision",
                "reason": "quarantined_acquisition",
                "fatal": True,
                "refresh_required": False,
            }
        ]
        assert (
            authority.stage_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            ).disposition
            == "exact_duplicate"
        )

    def test_changed_head_is_incomparable_without_timestamp_ordering(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(
            tmp_path,
            delivery_id=SECOND_DELIVERY_ID,
            body=webhook_body(
                head_sha=CommitSha("c" * 40),
                updated_at="2026-08-31T12:34:56Z",
            ),
        )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        changed = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=SECOND_DELIVERY_ID,
        )

        assert changed.disposition == "incomparable"
        assert changed.decisions[0].reason == "unordered_head"
        assert not changed.decisions[0].fatal
        assert changed.decisions[0].refresh_required

    def test_same_tips_with_contradictory_head_semantics_are_failure_data(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(
            tmp_path,
            delivery_id=SECOND_DELIVERY_ID,
            body=webhook_body(draft=True),
        )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        contradictory = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=SECOND_DELIVERY_ID,
        )

        assert contradictory.disposition == "conflicting"
        assert contradictory.decisions[0].reason == "contradictory_head"
        assert contradictory.decisions[0].fatal
        assert not contradictory.decisions[0].refresh_required

    def test_provider_time_action_and_delivery_identity_do_not_change_head_equality(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(
            tmp_path,
            delivery_id=THIRD_DELIVERY_ID,
            body=webhook_body(
                action="opened",
                updated_at="2026-08-31T12:34:56Z",
            ),
        )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        first = authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        diagnostic_change = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=THIRD_DELIVERY_ID,
        )

        assert diagnostic_change.disposition == "corroborating"
        assert diagnostic_change.manifest.entries[0].observation_key == first.manifest.entries[0].observation_key
        assert diagnostic_change.manifest.entries[0].canonical_bytes == first.manifest.entries[0].canonical_bytes

    def test_same_key_with_different_bytes_is_a_fatal_semantic_collision(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        force_observation_key_collision(monkeypatch)
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(
            tmp_path,
            delivery_id=SECOND_DELIVERY_ID,
            body=webhook_body(head_sha=CommitSha("c" * 40)),
        )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        first = authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        collision = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=SECOND_DELIVERY_ID,
        )
        preserved = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        ).staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert collision.disposition == "semantic_collision"
        assert collision.decisions[0].reason == "key_bytes_mismatch"
        assert collision.decisions[0].fatal
        assert collision.manifest.entries[0].observation_key == first.manifest.entries[0].observation_key
        assert collision.manifest.entries[0].canonical_bytes != first.manifest.entries[0].canonical_bytes
        assert preserved == first

    def test_later_custody_collision_never_overwrites_the_original_staging_authority(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        original = authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        collision_receipt = acquire_signed_delivery(
            tmp_path,
            body=webhook_body(head_sha=CommitSha("c" * 40)),
        )

        collision = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=PolicyRevision("policy:changed-after-retention"),
        ).stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        preserved = authority.staging_posture(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert collision_receipt["disposition"] == "quarantined"
        assert collision.disposition == "acquisition_collision"
        assert collision.manifest == original.manifest
        assert collision.grant == original.grant
        assert collision.decisions == original.decisions
        assert preserved == original


class TestDetachedStagingAuthority:
    """Reconstruction rejects every mutation to retained staging authority."""

    def test_changed_host_canonical_content_fails_before_staging(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            row = connection.execute("SELECT canonical_content FROM delivery_custody").fetchone()
            changed = json.loads(row[0])
            changed["provenance"]["delivery_id"] = str(SECOND_DELIVERY_ID)
            connection.execute(
                "UPDATE delivery_custody SET canonical_content = ?",
                (json.dumps(changed, ensure_ascii=True, separators=(",", ":"), sort_keys=True),),
            )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )

        with pytest.raises(DeliveryCustodyCorruptionError) as raised:
            authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable delivery custody failed strict reconstruction",
        )
        assert authority.ingress_resources().manifests == 0

    def test_retained_host_delivery_cannot_claim_quarantine_without_collision_evidence(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE delivery_custody SET disposition = 'quarantined'")
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )

        with pytest.raises(DeliveryCustodyCorruptionError) as raised:
            authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable delivery custody failed strict reconstruction",
        )
        assert authority.ingress_resources().manifests == 0

    def test_collided_host_delivery_cannot_claim_eligibility(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, body=webhook_body(head_sha=CommitSha("c" * 40)))
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE delivery_custody SET disposition = 'retained'")
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )

        with pytest.raises(DeliveryCustodyCorruptionError) as raised:
            authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable delivery custody failed strict reconstruction",
        )
        assert authority.ingress_resources().manifests == 0

    def test_valid_but_unrelated_entry_cannot_replace_the_acquisition_projection(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        staged = authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        replace_staged_entry_with_valid_unrelated_head(tmp_path, staged)

        with pytest.raises(IngressCorruptionError) as raised:
            authority.staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable ingress rows failed strict reconstruction",
        )

    def test_classification_rejects_corrupt_prior_authority_before_mutation(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        staged = authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        replace_staged_entry_with_valid_unrelated_head(tmp_path, staged)

        with pytest.raises(IngressCorruptionError):
            authority.stage_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=SECOND_DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection:
            manifests = connection.execute("SELECT COUNT(*) FROM ingress_manifests").fetchone()[0]
        assert manifests == 1

    def test_eligible_acquisition_cannot_reconstruct_as_an_empty_quarantine_projection(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        replace_acquisition_quarantine(tmp_path, quarantined=True)

        with pytest.raises(IngressCorruptionError):
            authority.staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

    def test_quarantined_acquisition_cannot_reconstruct_as_an_eligible_projection(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, body=webhook_body(head_sha=CommitSha("c" * 40)))
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        replace_acquisition_quarantine(tmp_path, quarantined=False)

        with pytest.raises(IngressCorruptionError):
            authority.staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

    def test_valid_but_unearned_classification_fails_strict_reconstruction(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        replace_decision_with_valid_incomparable(tmp_path)

        with pytest.raises(IngressCorruptionError) as raised:
            authority.staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable ingress rows failed strict reconstruction",
        )

    def test_classification_rejects_unearned_prior_decision_before_mutation(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        replace_decision_with_valid_incomparable(tmp_path)

        with pytest.raises(IngressCorruptionError):
            authority.stage_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=SECOND_DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection:
            manifests = connection.execute("SELECT COUNT(*) FROM ingress_manifests").fetchone()[0]
        assert manifests == 1

    def test_quarantined_classification_rejects_corrupt_prior_authority_before_mutation(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)
        acquire_signed_delivery(
            tmp_path,
            delivery_id=SECOND_DELIVERY_ID,
            body=webhook_body(head_sha=CommitSha("c" * 40)),
        )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        replace_decision_with_valid_incomparable(tmp_path)

        with pytest.raises(IngressCorruptionError):
            authority.stage_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=SECOND_DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection:
            manifests = connection.execute("SELECT COUNT(*) FROM ingress_manifests").fetchone()[0]
        assert manifests == 1

    @pytest.mark.parametrize("table", ["entry", "grant", "decision"])
    def test_classification_rejects_orphan_authority_before_mutation(self, tmp_path: Path, table: str) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        insert_orphan_ingress_row(tmp_path, table)

        with pytest.raises(IngressCorruptionError):
            authority.stage_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=SECOND_DELIVERY_ID,
            )

        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection:
            manifests = connection.execute("SELECT COUNT(*) FROM ingress_manifests").fetchone()[0]
        assert manifests == 1

    def test_duplicate_host_identity_in_a_malformed_schema_cannot_feed_staging(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE malformed_delivery_custody AS SELECT * FROM delivery_custody;
                INSERT INTO malformed_delivery_custody SELECT * FROM delivery_custody;
                DROP TABLE delivery_custody;
                ALTER TABLE malformed_delivery_custody RENAME TO delivery_custody;
                """
            )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )

        with pytest.raises(DeliveryCustodyCorruptionError):
            authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert authority.ingress_resources().manifests == 0

    def test_duplicate_acquisition_in_a_malformed_schema_fails_closed(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE malformed_ingress_manifests AS SELECT * FROM ingress_manifests;
                    INSERT INTO malformed_ingress_manifests SELECT * FROM ingress_manifests;
                    DROP TABLE ingress_manifests;
                    ALTER TABLE malformed_ingress_manifests RENAME TO ingress_manifests;
                    """
                )

        with pytest.raises(IngressCorruptionError):
            authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

    def test_duplicate_grant_in_a_malformed_schema_fails_closed(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE malformed_admission_grants AS SELECT * FROM admission_grants;
                    INSERT INTO malformed_admission_grants SELECT * FROM admission_grants;
                    DROP TABLE admission_grants;
                    ALTER TABLE malformed_admission_grants RENAME TO admission_grants;
                    """
                )

        with pytest.raises(IngressCorruptionError):
            authority.staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

    def test_exact_http_redelivery_rejects_corrupt_retained_collision_state(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE delivery_custody SET collision_digest = ?", ("f" * 64,))

        with pytest.raises(DeliveryCustodyCorruptionError):
            acquire_signed_delivery(tmp_path)

        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            row = connection.execute("SELECT disposition, collision_digest FROM delivery_custody").fetchone()
        assert row == ("retained", "f" * 64)

    def test_exact_http_redelivery_rejects_oversized_collision_evidence(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE delivery_custody SET collision_digest = zeroblob(1000000)")

        with pytest.raises(DeliveryCustodyCorruptionError):
            acquire_signed_delivery(tmp_path)

    def test_changed_http_redelivery_rejects_corrupt_row_without_mutation(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection, connection:
            connection.execute("UPDATE delivery_custody SET content_digest = ?", ("f" * 64,))

        with pytest.raises(DeliveryCustodyCorruptionError):
            acquire_signed_delivery(tmp_path, body=webhook_body(head_sha=CommitSha("c" * 40)))

        with closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection:
            row = connection.execute(
                "SELECT content_digest, disposition, collision_digest FROM delivery_custody"
            ).fetchone()
        assert row == ("f" * 64, "retained", None)

    def test_manifest_rejects_noncontiguous_entry_order(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        staged = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        ).stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        entry = staged.manifest.entries[0].model_copy(update={"order": 1})

        with pytest.raises(ValidationError, match="manifest entry order must be contiguous from zero"):
            IngressManifest(
                manifest_id=staged.manifest.manifest_id,
                acquisition=staged.manifest.acquisition,
                policy_revision=staged.manifest.policy_revision,
                entries=(entry,),
            )

    def test_manifest_rejects_duplicate_observation_keys(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        staged = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        ).stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        first = staged.manifest.entries[0]
        duplicate = first.model_copy(update={"order": 1})

        with pytest.raises(ValidationError, match="manifest observation keys must be unique"):
            IngressManifest(
                manifest_id=staged.manifest.manifest_id,
                acquisition=staged.manifest.acquisition,
                policy_revision=staged.manifest.policy_revision,
                entries=(first, duplicate),
            )

    @pytest.mark.parametrize(
        ("statement", "parameters"),
        [
            pytest.param(
                "UPDATE ingress_manifests SET acquisition_bytes = ?",
                (b"{}",),
                id="acquisition",
            ),
            pytest.param(
                "UPDATE ingress_manifests SET manifest_id = ?",
                (f"manifest:v1:sha256:{'f' * 64}",),
                id="manifest-identity",
            ),
            pytest.param(
                "UPDATE ingress_manifests SET policy_revision = ?",
                ("policy:mutated",),
                id="manifest-policy",
            ),
            pytest.param(
                "UPDATE ingress_manifests SET staging_sequence = 2",
                (),
                id="staging-sequence",
            ),
            pytest.param(
                "UPDATE ingress_entries SET entry_order = 1",
                (),
                id="entry-order",
            ),
            pytest.param(
                "UPDATE ingress_entries SET observation_key = ?",
                (f"obs:v1:sha256:{'f' * 64}",),
                id="observation-key",
            ),
            pytest.param(
                "UPDATE ingress_entries SET canonical_bytes = ?",
                (b"{}",),
                id="canonical-bytes",
            ),
            pytest.param(
                "UPDATE admission_grants SET manifest_digest = ?",
                ("f" * 64,),
                id="grant",
            ),
            pytest.param(
                "UPDATE admission_decisions SET reason = 'same_semantics'",
                (),
                id="decision",
            ),
        ],
    )
    def test_mutated_authority_fails_strict_reconstruction(
        self,
        tmp_path: Path,
        statement: str,
        parameters: tuple[object, ...],
    ) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection, connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(statement, parameters)

        with pytest.raises(IngressCorruptionError) as raised:
            build_staging_authority(
                state_root=tmp_path,
                provider_routes=(PROVIDER_ROUTE,),
                policy_revision=POLICY_REVISION,
            ).staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable ingress rows failed strict reconstruction",
        )

    def test_closed_disposition_family_accepts_stale_but_rejects_invented_labels(self) -> None:
        stale = AdmissionDecision(
            entry_order=0,
            observation_key=ObservationKey(HEAD_KEY),
            disposition="stale",
            reason="ordered_before",
            fatal=False,
            refresh_required=False,
        )

        with pytest.raises(ValidationError):
            AdmissionDecision.model_validate(
                {**stale.model_dump(), "disposition": "older_by_timestamp"},
                strict=True,
            )

        assert stale.disposition == "stale"

    def test_non_boolean_decision_storage_fails_strict_reconstruction(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        force_observation_key_collision(monkeypatch)
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(
            tmp_path,
            delivery_id=SECOND_DELIVERY_ID,
            body=webhook_body(head_sha=CommitSha("c" * 40)),
        )
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        collision = authority.stage_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=SECOND_DELIVERY_ID,
        )
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                "UPDATE admission_decisions SET fatal = 2 WHERE manifest_id = ?",
                (collision.manifest.manifest_id,),
            )

        with pytest.raises(IngressCorruptionError) as raised:
            authority.staging_posture(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=SECOND_DELIVERY_ID,
            )

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            SECOND_DELIVERY_ID,
            "use a fresh state root; durable ingress rows failed strict reconstruction",
        )

    def test_non_blob_acquisition_storage_fails_before_byte_conversion(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE ingress_manifests SET acquisition_bytes = 16769")

        with pytest.raises(IngressCorruptionError) as raised:
            authority.staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable ingress rows failed strict reconstruction",
        )

    def test_non_blob_observation_storage_fails_before_byte_conversion(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE ingress_entries SET canonical_bytes = 8193")

        with pytest.raises(IngressCorruptionError) as raised:
            authority.staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "use a fresh state root; durable ingress rows failed strict reconstruction",
        )

    def test_invalid_optional_decision_key_cannot_reconstruct_as_absent(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, body=webhook_body(head_sha=CommitSha("c" * 40)))
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        with closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE admission_decisions SET observation_key = zeroblob(1000000)")

        with pytest.raises(IngressCorruptionError):
            authority.staging_posture(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

    def test_new_ingress_schema_rejects_oversized_acquisition_storage(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        with (
            closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection,
            pytest.raises(sqlite3.IntegrityError),
            connection,
        ):
            connection.execute(
                "UPDATE ingress_manifests SET acquisition_bytes = ?",
                (b"x" * (MAX_ACQUISITION_BYTES + 1),),
            )

    def test_new_ingress_schema_rejects_non_blob_observation_storage(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        with (
            closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection,
            pytest.raises(sqlite3.IntegrityError),
            connection,
        ):
            connection.execute("UPDATE ingress_entries SET canonical_bytes = 8193")

    def test_new_ingress_schema_rejects_non_integer_decision_entry_order(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        with (
            closing(sqlite3.connect(tmp_path / "readiness-ingress.sqlite3")) as connection,
            pytest.raises(sqlite3.IntegrityError),
            connection,
        ):
            connection.execute("UPDATE admission_decisions SET entry_order = zeroblob(1000000)")

    def test_new_host_schema_rejects_oversized_canonical_content(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)

        with (
            closing(sqlite3.connect(tmp_path / "deliveries.sqlite3")) as connection,
            pytest.raises(sqlite3.IntegrityError),
            connection,
        ):
            connection.execute(
                "UPDATE delivery_custody SET canonical_content = ?",
                ("x" * (MAX_NORMALIZED_BYTES + 1),),
            )

    def test_missing_host_delivery_fails_before_creating_a_manifest(self, tmp_path: Path) -> None:
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )

        with pytest.raises(DeliveryNotFoundError) as raised:
            authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        assert raised.value.args == (
            PROVIDER_ROUTE_ID,
            DELIVERY_ID,
            "acquire this delivery before requesting readiness staging",
        )
        assert authority.ingress_resources().manifests == 0


class TestIngressResourcesAndConcurrency:
    """Finite SQLite custody preserves one deterministic authority under races."""

    def test_canonical_observation_rejects_oversized_bytes_before_custody(self) -> None:
        oversized = b"x" * (MAX_CANONICAL_OBSERVATION_BYTES + 1)

        with pytest.raises(
            ValueError,
            match=rf"^canonical observation must contain 1-{MAX_CANONICAL_OBSERVATION_BYTES} bytes$",
        ) as raised:
            CanonicalObservation(oversized)

        assert raised.value.args == (f"canonical observation must contain 1-{MAX_CANONICAL_OBSERVATION_BYTES} bytes",)

    def test_capacity_refuses_a_new_identity_without_disturbing_retained_authority(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
            maximum_manifests=1,
        )
        retained = authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)

        with pytest.raises(IngressCapacityError) as raised:
            authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=SECOND_DELIVERY_ID)

        assert raised.value.args == (
            1,
            "align ingress capacity with host delivery custody before accepting more acquisitions",
        )
        assert (
            authority.staging_posture(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )
            == retained
        )
        assert (
            authority.staging_posture(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=SECOND_DELIVERY_ID,
            )
            is None
        )

    def test_reconstruction_rejects_rows_above_the_configured_manifest_ceiling(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=SECOND_DELIVERY_ID)
        constrained = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
            maximum_manifests=1,
        )

        with pytest.raises(IngressCorruptionError):
            constrained.staging_posture(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

    def test_existing_database_above_the_sqlite_page_ceiling_fails_closed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        acquire_signed_delivery(tmp_path)
        build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        ).stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        monkeypatch.setattr(readiness_ingress, "MAX_SQLITE_PAGES", 1)

        with pytest.raises(IngressCapacityError) as raised:
            build_staging_authority(
                state_root=tmp_path,
                provider_routes=(PROVIDER_ROUTE,),
                policy_revision=POLICY_REVISION,
            )

        assert raised.value.args == (
            1,
            "use a fresh state root; durable ingress exceeds the SQLite page ceiling",
        )

    def test_host_custody_above_its_sqlite_page_ceiling_cannot_feed_staging(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        acquire_signed_delivery(tmp_path)
        monkeypatch.setattr(host_delivery, "MAX_SQLITE_PAGES", 1)

        with pytest.raises(DeliveryCustodyCorruptionError) as raised:
            build_staging_authority(
                state_root=tmp_path,
                provider_routes=(PROVIDER_ROUTE,),
                policy_revision=POLICY_REVISION,
            )

        assert raised.value.args == (
            1,
            "use a fresh state root; durable delivery custody exceeds the SQLite page ceiling",
        )
        assert not (tmp_path / "readiness-ingress.sqlite3").exists()

    def test_host_custody_above_configured_row_capacity_cannot_feed_staging(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)

        with pytest.raises(DeliveryCustodyCorruptionError) as raised:
            build_staging_authority(
                state_root=tmp_path,
                provider_routes=(PROVIDER_ROUTE,),
                policy_revision=POLICY_REVISION,
                maximum_deliveries=1,
            )

        assert raised.value.args == (
            1,
            "use a fresh state root; durable delivery custody exceeds the configured row ceiling",
        )
        assert not (tmp_path / "readiness-ingress.sqlite3").exists()

    def test_resource_observation_counts_bounded_retained_evidence(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)
        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=DELIVERY_ID)
        authority.stage_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=SECOND_DELIVERY_ID)

        resources = authority.ingress_resources()

        assert resources.manifests == 2
        assert resources.entries == 2
        assert resources.grants == 2
        assert resources.decisions == 2
        assert resources.canonical_bytes == 2 * len(CANONICAL_HEAD)
        assert 0 < resources.acquisition_bytes <= resources.maximum_acquisition_bytes
        assert 0 < resources.database_pages <= resources.maximum_database_pages
        assert resources.maximum_manifests == 10_000

    def test_concurrent_exact_reoffers_create_one_manifest_grant_and_entry(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)

        def stage() -> str:
            return (
                build_staging_authority(
                    state_root=tmp_path,
                    provider_routes=(PROVIDER_ROUTE,),
                    policy_revision=POLICY_REVISION,
                )
                .stage_delivery(
                    provider_route_id=PROVIDER_ROUTE_ID,
                    delivery_id=DELIVERY_ID,
                )
                .disposition
            )

        with ThreadPoolExecutor(max_workers=8) as workers:
            dispositions = [future.result() for future in [workers.submit(stage) for _ in range(8)]]

        authority = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        )
        assert sorted(dispositions) == ["exact_duplicate"] * 7 + ["novel"]
        assert authority.ingress_resources().model_dump() == {
            "manifests": 1,
            "entries": 1,
            "grants": 1,
            "decisions": 1,
            "acquisition_bytes": authority.ingress_resources().acquisition_bytes,
            "canonical_bytes": len(CANONICAL_HEAD),
            "database_pages": authority.ingress_resources().database_pages,
            "maximum_manifests": 10_000,
            "maximum_acquisition_bytes": 167_680_000,
            "maximum_database_pages": 131_072,
        }

    def test_concurrent_distinct_acquisitions_classify_once_in_serial_authority_order(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        acquire_signed_delivery(tmp_path, delivery_id=SECOND_DELIVERY_ID)

        def stage(delivery_id: DeliveryId) -> str:
            return (
                build_staging_authority(
                    state_root=tmp_path,
                    provider_routes=(PROVIDER_ROUTE,),
                    policy_revision=POLICY_REVISION,
                )
                .stage_delivery(
                    provider_route_id=PROVIDER_ROUTE_ID,
                    delivery_id=delivery_id,
                )
                .disposition
            )

        with ThreadPoolExecutor(max_workers=2) as workers:
            dispositions = [
                future.result()
                for future in [
                    workers.submit(stage, DELIVERY_ID),
                    workers.submit(stage, SECOND_DELIVERY_ID),
                ]
            ]

        resources = build_staging_authority(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=POLICY_REVISION,
        ).ingress_resources()
        assert sorted(dispositions) == ["corroborating", "novel"]
        assert (resources.manifests, resources.entries, resources.grants, resources.decisions) == (2, 2, 2, 2)

    def test_collision_during_reconstruction_is_visible_at_the_final_custody_read(self, tmp_path: Path) -> None:
        acquire_signed_delivery(tmp_path)
        delivery_custody = PausingDeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        )
        assert isinstance(delivery_custody, PausingDeliveryCustody)
        authority = StagingAuthority(
            delivery_custody=delivery_custody,
            ingress_custody=IngressCustody.from_path(
                path=tmp_path / "readiness-ingress.sqlite3",
                policy_revision=POLICY_REVISION,
            ),
        )
        try:
            with ThreadPoolExecutor(max_workers=1) as worker:
                staged_future = worker.submit(
                    authority.stage_delivery,
                    provider_route_id=PROVIDER_ROUTE_ID,
                    delivery_id=DELIVERY_ID,
                )
                assert delivery_custody.reconstruction_started.wait(timeout=5)
                collision = acquire_signed_delivery(
                    tmp_path,
                    body=webhook_body(head_sha=CommitSha("c" * 40)),
                )
                delivery_custody.continue_reconstruction.set()
                staged = staged_future.result()
        finally:
            delivery_custody.continue_reconstruction.set()

        assert collision["disposition"] == "quarantined"
        assert staged.disposition == "acquisition_collision"
        assert staged.manifest.entries == ()

    def test_earlier_selected_staging_turn_retains_authority_before_later_quarantine(
        self,
        tmp_path: Path,
    ) -> None:
        acquire_signed_delivery(tmp_path)
        selected_first = Event()
        continue_first = Event()
        selected_second = Event()
        continue_second = Event()
        continue_second.set()
        second_started = Event()
        first_custody = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        )
        second_custody = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        )
        first_authority = StagingAuthority(
            delivery_custody=PausingSelectedDeliveryCustody(
                first_custody,
                selected_first,
                continue_first,
            ),
            ingress_custody=IngressCustody.from_path(
                path=tmp_path / "readiness-ingress.sqlite3",
                policy_revision=POLICY_REVISION,
            ),
        )
        second_authority = StagingAuthority(
            delivery_custody=PausingSelectedDeliveryCustody(
                second_custody,
                selected_second,
                continue_second,
            ),
            ingress_custody=IngressCustody.from_path(
                path=tmp_path / "readiness-ingress.sqlite3",
                policy_revision=POLICY_REVISION,
            ),
        )

        def stage_second() -> StagingPosture:
            second_started.set()
            return second_authority.stage_delivery(
                provider_route_id=PROVIDER_ROUTE_ID,
                delivery_id=DELIVERY_ID,
            )

        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                first_future = workers.submit(
                    first_authority.stage_delivery,
                    provider_route_id=PROVIDER_ROUTE_ID,
                    delivery_id=DELIVERY_ID,
                )
                assert selected_first.wait(timeout=5)
                second_future = workers.submit(stage_second)
                assert second_started.wait(timeout=5)
                assert not selected_second.wait(timeout=0.5)
                collision = acquire_signed_delivery(
                    tmp_path,
                    body=webhook_body(head_sha=CommitSha("c" * 40)),
                )
                continue_first.set()
                first = first_future.result()
                second = second_future.result()
        finally:
            continue_first.set()

        assert collision["disposition"] == "quarantined"
        assert first.disposition == "novel"
        assert second.disposition == "acquisition_collision"
        assert second.manifest == first.manifest
        assert second.grant == first.grant
        assert second.decisions == first.decisions
