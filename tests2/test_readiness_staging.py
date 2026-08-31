# Copyright (c) 2026 Henrique Bastos

"""Source-neutral readiness staging starts only on an authority turn."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
import json
import sqlite3
from threading import Event
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
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
from hamsterdan2.host.application import DeliveryNotFoundError, StagingAuthority
from hamsterdan2.host.composition import build_staging_authority, build_webhook_app
from hamsterdan2.host.delivery import MAX_NORMALIZED_BYTES, DeliveryCustody, DeliveryCustodyCorruptionError
from hamsterdan2.host.values import ConfiguredProviderRoute
from hamsterdan2.readiness import ingress as readiness_ingress
from hamsterdan2.readiness import projection as readiness_projection
from hamsterdan2.readiness.ingress import IngressCapacityError, IngressCorruptionError, IngressCustody
from hamsterdan2.readiness.ingress_values import (
    MAX_ACQUISITION_BYTES,
    MAX_CANONICAL_OBSERVATION_BYTES,
    AdmissionDecision,
    CanonicalObservation,
    IngressManifest,
    ObservationKey,
    PolicyRevision,
    StagingPosture,
)
from hamsterdan2.readiness.projection import (
    grant_for,
    observation_entry,
)

import pytest


if TYPE_CHECKING:
    from pathlib import Path

    from hamsterdan2.host.values import CustodiedDelivery


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
    updated_at: str = "2026-08-30T12:34:56Z",
) -> bytes:
    payload = json.loads(signed_webhook_body(head_sha=head_sha))
    payload["action"] = action
    payload["pull_request"]["draft"] = draft
    payload["pull_request"]["updated_at"] = updated_at
    return json.dumps(payload, separators=(",", ":")).encode()


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
