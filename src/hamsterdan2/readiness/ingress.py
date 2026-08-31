# Copyright (c) 2026 Henrique Bastos

"""Atomic SQLite custody for source-neutral readiness ingress authority."""

from __future__ import annotations

from contextlib import closing
import sqlite3
from typing import TYPE_CHECKING

from hamsterdan2.readiness.ingress_values import (
    MAX_ACQUISITION_BYTES,
    MAX_CANONICAL_OBSERVATION_BYTES,
    MAX_ENTRIES_PER_MANIFEST,
    MAX_MANIFESTS,
    MAX_SQLITE_PAGES,
    AcquisitionIdentity,
    AdmissionDecision,
    AdmissionGrant,
    CanonicalObservation,
    IngressEntry,
    IngressManifest,
    IngressResources,
    ManifestId,
    ObservationKey,
    PolicyRevision,
    StagingAcquisition,
    StagingPosture,
)
from hamsterdan2.readiness.projection import (
    canonical_json,
    classify_head,
    decision,
    grant_for,
    manifest_id_for,
    observation_entry,
    project_head,
    sha256_digest,
)
from hamsterdan2.workflow.observations import HeadObservation


if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from typing import Protocol

    from hamsterdan2.github_app.models import DeliveryId, NormalizedPullRequestWebhook, ProviderRouteId

    class StagingDelivery(Protocol):
        @property
        def provider_route_id(self) -> ProviderRouteId: ...

        @property
        def custody_generation(self) -> int: ...

        @property
        def webhook(self) -> NormalizedPullRequestWebhook: ...

        @property
        def quarantined(self) -> bool: ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS ingress_manifests (
    staging_sequence INTEGER NOT NULL UNIQUE CHECK (
        typeof(staging_sequence) = 'integer' AND staging_sequence BETWEEN 1 AND 10000
    ),
    provider_route_id TEXT NOT NULL CHECK (
        typeof(provider_route_id) = 'text' AND length(provider_route_id) BETWEEN 1 AND 128
    ),
    delivery_id TEXT NOT NULL CHECK (
        typeof(delivery_id) = 'text' AND length(delivery_id) = 36
    ),
    manifest_id TEXT NOT NULL UNIQUE CHECK (
        typeof(manifest_id) = 'text' AND length(manifest_id) = 83
    ),
    policy_revision TEXT NOT NULL CHECK (
        typeof(policy_revision) = 'text' AND length(policy_revision) BETWEEN 1 AND 128
    ),
    acquisition_bytes BLOB NOT NULL CHECK (
        typeof(acquisition_bytes) = 'blob' AND length(acquisition_bytes) BETWEEN 1 AND 16768
    ),
    acquisition_digest TEXT NOT NULL CHECK (
        typeof(acquisition_digest) = 'text'
        AND length(acquisition_digest) = 64
        AND acquisition_digest NOT GLOB '*[^0-9a-f]*'
    ),
    entry_count INTEGER NOT NULL CHECK (
        typeof(entry_count) = 'integer' AND entry_count BETWEEN 0 AND 8
    ),
    original_disposition TEXT NOT NULL CHECK (
        original_disposition IN (
            'acquisition_collision', 'novel', 'corroborating', 'stale',
            'semantic_collision', 'conflicting', 'incomparable'
        )
    ),
    PRIMARY KEY (provider_route_id, delivery_id)
);
CREATE TABLE IF NOT EXISTS ingress_entries (
    manifest_id TEXT NOT NULL CHECK (
        typeof(manifest_id) = 'text' AND length(manifest_id) = 83
    ),
    entry_order INTEGER NOT NULL CHECK (
        typeof(entry_order) = 'integer' AND entry_order BETWEEN 0 AND 7
    ),
    observation_key TEXT NOT NULL CHECK (
        typeof(observation_key) = 'text' AND length(observation_key) = 78
    ),
    canonical_bytes BLOB NOT NULL CHECK (
        typeof(canonical_bytes) = 'blob' AND length(canonical_bytes) BETWEEN 1 AND 8192
    ),
    PRIMARY KEY (manifest_id, entry_order),
    UNIQUE (manifest_id, observation_key),
    FOREIGN KEY (manifest_id) REFERENCES ingress_manifests (manifest_id)
);
CREATE TABLE IF NOT EXISTS admission_grants (
    grant_id TEXT PRIMARY KEY CHECK (
        typeof(grant_id) = 'text' AND length(grant_id) = 80
    ),
    manifest_id TEXT NOT NULL UNIQUE CHECK (
        typeof(manifest_id) = 'text' AND length(manifest_id) = 83
    ),
    manifest_digest TEXT NOT NULL CHECK (
        typeof(manifest_digest) = 'text'
        AND length(manifest_digest) = 64
        AND manifest_digest NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (manifest_id) REFERENCES ingress_manifests (manifest_id)
);
CREATE TABLE IF NOT EXISTS admission_decisions (
    manifest_id TEXT NOT NULL CHECK (
        typeof(manifest_id) = 'text' AND length(manifest_id) = 83
    ),
    decision_order INTEGER NOT NULL CHECK (
        typeof(decision_order) = 'integer' AND decision_order BETWEEN 0 AND 7
    ),
    entry_order INTEGER CHECK (
        entry_order IS NULL
        OR (typeof(entry_order) = 'integer' AND entry_order BETWEEN 0 AND 7)
    ),
    observation_key TEXT CHECK (
        observation_key IS NULL
        OR (typeof(observation_key) = 'text' AND length(observation_key) = 78)
    ),
    disposition TEXT NOT NULL CHECK (
        disposition IN (
            'acquisition_collision', 'novel', 'corroborating', 'stale',
            'semantic_collision', 'conflicting', 'incomparable'
        )
    ),
    reason TEXT NOT NULL CHECK (
        reason IN (
            'first_observation', 'quarantined_acquisition', 'same_semantics',
            'key_bytes_mismatch', 'ordered_before', 'contradictory_head', 'unordered_head'
        )
    ),
    fatal INTEGER NOT NULL CHECK (
        typeof(fatal) = 'integer' AND fatal IN (0, 1)
    ),
    refresh_required INTEGER NOT NULL CHECK (
        typeof(refresh_required) = 'integer' AND refresh_required IN (0, 1)
    ),
    PRIMARY KEY (manifest_id, decision_order),
    FOREIGN KEY (manifest_id) REFERENCES ingress_manifests (manifest_id)
);
"""


class IngressError(Exception):
    """Readiness ingress could not safely preserve or reconstruct its durable contract."""


class IngressCapacityError(IngressError):
    """Configured ingress custody cannot retain another acquired identity."""


class IngressCorruptionError(IngressError):
    """Durable ingress rows do not reconstruct to their strict canonical values."""


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    effective_maximum = connection.execute(f"PRAGMA max_page_count = {MAX_SQLITE_PAGES}").fetchone()[0]
    pages = connection.execute("PRAGMA page_count").fetchone()[0]
    if effective_maximum > MAX_SQLITE_PAGES or pages > MAX_SQLITE_PAGES:
        connection.close()
        raise IngressCapacityError(
            MAX_SQLITE_PAGES,
            "use a fresh state root; durable ingress exceeds the SQLite page ceiling",
        )
    return connection


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def bounded_blob(value: object, *, maximum_bytes: int, field: str) -> bytes:
    if type(value) is not bytes:
        raise ValueError(f"{field} must be stored as bounded bytes")
    if not 1 <= len(value) <= maximum_bytes:
        raise ValueError(f"{field} exceeds its byte bound")
    return value


class IngressCustody:
    """Retain and reconstruct one immutable source-neutral manifest per acquisition."""

    def __init__(
        self,
        *,
        path: Path,
        policy_revision: PolicyRevision,
        maximum_manifests: int,
    ) -> None:
        self._path = path
        self._policy_revision = policy_revision
        self._maximum_manifests = maximum_manifests

    @classmethod
    def from_path(
        cls,
        *,
        path: Path,
        policy_revision: PolicyRevision,
        maximum_manifests: int = MAX_MANIFESTS,
    ) -> IngressCustody:
        if not 1 <= maximum_manifests <= MAX_MANIFESTS:
            raise ValueError(f"maximum manifests must be between 1 and {MAX_MANIFESTS}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(connect(path)) as connection, connection:
            connection.executescript(SCHEMA)
        return cls(
            path=path,
            policy_revision=policy_revision,
            maximum_manifests=maximum_manifests,
        )

    def stage(
        self,
        *,
        provider_route_id: ProviderRouteId,
        custody_generation: int,
        webhook: NormalizedPullRequestWebhook,
        quarantined: bool,
    ) -> StagingPosture:
        acquisition = self.new_acquisition(
            provider_route_id=provider_route_id,
            custody_generation=custody_generation,
            webhook=webhook,
            quarantined=quarantined,
        )
        acquisition_bytes = canonical_json(acquisition, maximum_bytes=MAX_ACQUISITION_BYTES)
        disposition = self.retain(acquisition, acquisition_bytes)
        return self.detached_posture(acquisition, disposition)

    def stage_selected(
        self,
        select_delivery: Callable[[], StagingDelivery],
    ) -> StagingPosture:
        with closing(connect(self._path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                delivery = select_delivery()
                acquisition = self.new_acquisition(
                    provider_route_id=delivery.provider_route_id,
                    custody_generation=delivery.custody_generation,
                    webhook=delivery.webhook,
                    quarantined=delivery.quarantined,
                )
                acquisition_bytes = canonical_json(acquisition, maximum_bytes=MAX_ACQUISITION_BYTES)
                disposition = self.retain_in_transaction(connection, acquisition, acquisition_bytes)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return self.detached_posture(acquisition, disposition)

    @staticmethod
    def new_acquisition(
        *,
        provider_route_id: ProviderRouteId,
        custody_generation: int,
        webhook: NormalizedPullRequestWebhook,
        quarantined: bool,
    ) -> StagingAcquisition:
        return StagingAcquisition(
            identity=AcquisitionIdentity(
                provider_route_id=provider_route_id,
                delivery_id=webhook.provenance.delivery_id,
            ),
            custody_generation=custody_generation,
            webhook=webhook,
            quarantined=quarantined,
        )

    def detached_posture(
        self,
        acquisition: StagingAcquisition,
        disposition: str | None,
    ) -> StagingPosture:
        posture = self.staging_posture(
            provider_route_id=acquisition.identity.provider_route_id,
            delivery_id=acquisition.identity.delivery_id,
        )
        if posture is None:
            raise IngressCorruptionError(
                acquisition.identity.provider_route_id,
                acquisition.identity.delivery_id,
                "committed staging posture could not be reconstructed",
            )
        return posture if disposition is None else posture.model_copy(update={"disposition": disposition})

    def retain(self, acquisition: StagingAcquisition, acquisition_bytes: bytes) -> str | None:
        with closing(connect(self._path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                disposition = self.retain_in_transaction(connection, acquisition, acquisition_bytes)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return disposition

    def retain_in_transaction(
        self,
        connection: sqlite3.Connection,
        acquisition: StagingAcquisition,
        acquisition_bytes: bytes,
    ) -> str | None:
        digest = sha256_digest(acquisition_bytes)
        existing = self.acquisition_row(connection, acquisition.identity)
        if existing is not None:
            return (
                "exact_duplicate"
                if existing["acquisition_digest"] == digest and existing["acquisition_bytes"] == acquisition_bytes
                else "acquisition_collision"
            )
        self.ensure_capacity(connection)
        self.retain_first(connection, acquisition, acquisition_bytes, digest)
        return None

    @staticmethod
    def acquisition_row(
        connection: sqlite3.Connection,
        identity: AcquisitionIdentity,
    ) -> sqlite3.Row | None:
        rows = connection.execute(
            """
            SELECT CASE WHEN typeof(acquisition_bytes) = 'blob'
                              AND length(acquisition_bytes) BETWEEN 1 AND ?
                         THEN acquisition_bytes END AS acquisition_bytes,
                   CASE WHEN typeof(acquisition_digest) = 'text'
                              AND length(acquisition_digest) = 64
                              AND acquisition_digest NOT GLOB '*[^0-9a-f]*'
                         THEN acquisition_digest END AS acquisition_digest
            FROM ingress_manifests
            WHERE provider_route_id = ? AND delivery_id = ?
            LIMIT 2
            """,
            (MAX_ACQUISITION_BYTES, identity.provider_route_id, identity.delivery_id),
        ).fetchall()
        if len(rows) > 1:
            raise IngressCorruptionError(
                identity.provider_route_id,
                identity.delivery_id,
                "use a fresh state root; durable ingress rows failed strict reconstruction",
            )
        return rows[0] if rows else None

    def ensure_capacity(self, connection: sqlite3.Connection) -> None:
        retained = connection.execute("SELECT COUNT(*) FROM ingress_manifests").fetchone()[0]
        if retained >= self._maximum_manifests:
            raise IngressCapacityError(
                self._maximum_manifests,
                "align ingress capacity with host delivery custody before accepting more acquisitions",
            )

    def retain_first(
        self,
        connection: sqlite3.Connection,
        acquisition: StagingAcquisition,
        acquisition_bytes: bytes,
        acquisition_digest: str,
    ) -> None:
        prior_entries = self.prior_entries(connection)
        entry = None if acquisition.quarantined else observation_entry(project_head(acquisition.webhook.snapshot))
        admission_decision = self.classify(entry, prior_entries)
        manifest = IngressManifest(
            manifest_id=manifest_id_for(acquisition.identity),
            acquisition=acquisition.identity,
            policy_revision=self._policy_revision,
            entries=() if entry is None else (entry,),
        )
        grant = grant_for(manifest)
        self.insert_manifest(connection, acquisition_bytes, acquisition_digest, manifest, admission_decision)
        self.insert_entry(connection, manifest, entry)
        self.insert_grant(connection, grant)
        self.insert_decision(connection, manifest, admission_decision)

    @staticmethod
    def classify(
        entry: IngressEntry | None,
        prior_entries: tuple[IngressEntry, ...],
    ) -> AdmissionDecision:
        if entry is None:
            return decision(
                None,
                disposition="acquisition_collision",
                reason="quarantined_acquisition",
                fatal=True,
                refresh_required=False,
            )
        return classify_head(entry, prior_entries)

    @staticmethod
    def insert_manifest(
        connection: sqlite3.Connection,
        acquisition_bytes: bytes,
        acquisition_digest: str,
        manifest: IngressManifest,
        admission_decision: AdmissionDecision,
    ) -> None:
        sequence_row = connection.execute(
            "SELECT COALESCE(MAX(staging_sequence), 0) + 1 FROM ingress_manifests"
        ).fetchone()
        staging_sequence = sequence_row[0]
        connection.execute(
            """
            INSERT INTO ingress_manifests (
                staging_sequence, provider_route_id, delivery_id, manifest_id, policy_revision,
                acquisition_bytes, acquisition_digest, entry_count, original_disposition
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                staging_sequence,
                manifest.acquisition.provider_route_id,
                manifest.acquisition.delivery_id,
                manifest.manifest_id,
                manifest.policy_revision,
                acquisition_bytes,
                acquisition_digest,
                len(manifest.entries),
                admission_decision.disposition,
            ),
        )

    @staticmethod
    def insert_entry(
        connection: sqlite3.Connection,
        manifest: IngressManifest,
        entry: IngressEntry | None,
    ) -> None:
        if entry is None:
            return
        connection.execute(
            """
            INSERT INTO ingress_entries (
                manifest_id, entry_order, observation_key, canonical_bytes
            ) VALUES (?, ?, ?, ?)
            """,
            (manifest.manifest_id, entry.order, entry.observation_key, entry.canonical_bytes),
        )

    @staticmethod
    def insert_grant(connection: sqlite3.Connection, grant: AdmissionGrant) -> None:
        connection.execute(
            """
            INSERT INTO admission_grants (grant_id, manifest_id, manifest_digest)
            VALUES (?, ?, ?)
            """,
            (grant.grant_id, grant.manifest_id, grant.manifest_digest),
        )

    @staticmethod
    def insert_decision(
        connection: sqlite3.Connection,
        manifest: IngressManifest,
        admission_decision: AdmissionDecision,
    ) -> None:
        connection.execute(
            """
            INSERT INTO admission_decisions (
                manifest_id, decision_order, entry_order, observation_key,
                disposition, reason, fatal, refresh_required
            ) VALUES (?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                manifest.manifest_id,
                admission_decision.entry_order,
                admission_decision.observation_key,
                admission_decision.disposition,
                admission_decision.reason,
                admission_decision.fatal,
                admission_decision.refresh_required,
            ),
        )

    def prior_entries(self, connection: sqlite3.Connection) -> tuple[IngressEntry, ...]:
        try:
            authorities = self.reconstruct_authorities(connection)
        except (TypeError, ValueError) as error:
            raise IngressCorruptionError(
                "use a fresh state root; prior durable ingress rows failed strict reconstruction",
            ) from error
        return tuple(entry for _, posture in authorities for entry in posture.manifest.entries)

    def reconstructed_staging(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> tuple[StagingAcquisition, StagingPosture] | None:
        with closing(connect(self._path)) as connection:
            try:
                authorities = self.reconstruct_authorities(connection)
            except (TypeError, ValueError) as error:
                raise IngressCorruptionError(
                    provider_route_id,
                    delivery_id,
                    "use a fresh state root; durable ingress rows failed strict reconstruction",
                ) from error
        identity = AcquisitionIdentity(provider_route_id=provider_route_id, delivery_id=delivery_id)
        return next(
            ((acquisition, posture) for acquisition, posture in authorities if acquisition.identity == identity),
            None,
        )

    def staging_posture(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> StagingPosture | None:
        reconstructed = self.reconstructed_staging(
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
        )
        return None if reconstructed is None else reconstructed[1]

    def staging_acquisition(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> StagingAcquisition | None:
        reconstructed = self.reconstructed_staging(
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
        )
        return None if reconstructed is None else reconstructed[0]

    def reconstruct_authorities(
        self,
        connection: sqlite3.Connection,
    ) -> tuple[tuple[StagingAcquisition, StagingPosture], ...]:
        orphaned = connection.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1 FROM ingress_entries AS child
                    LEFT JOIN ingress_manifests AS parent USING (manifest_id)
                    WHERE parent.manifest_id IS NULL LIMIT 1
                ),
                EXISTS (
                    SELECT 1 FROM admission_grants AS child
                    LEFT JOIN ingress_manifests AS parent USING (manifest_id)
                    WHERE parent.manifest_id IS NULL LIMIT 1
                ),
                EXISTS (
                    SELECT 1 FROM admission_decisions AS child
                    LEFT JOIN ingress_manifests AS parent USING (manifest_id)
                    WHERE parent.manifest_id IS NULL LIMIT 1
                )
            """
        ).fetchone()
        require(not any(orphaned), "staging authority contains orphan child rows")
        rows = connection.execute(
            """
            SELECT CASE WHEN typeof(staging_sequence) = 'integer'
                                  AND staging_sequence BETWEEN 1 AND 10000
                         THEN staging_sequence END AS staging_sequence,
                   CASE WHEN typeof(provider_route_id) = 'text'
                              AND length(provider_route_id) BETWEEN 1 AND 128
                         THEN provider_route_id END AS provider_route_id,
                   CASE WHEN typeof(delivery_id) = 'text' AND length(delivery_id) = 36
                         THEN delivery_id END AS delivery_id,
                   CASE WHEN typeof(manifest_id) = 'text' AND length(manifest_id) = 83
                         THEN manifest_id END AS manifest_id,
                   CASE WHEN typeof(policy_revision) = 'text'
                              AND length(policy_revision) BETWEEN 1 AND 128
                         THEN policy_revision END AS policy_revision,
                   CASE WHEN typeof(acquisition_bytes) = 'blob'
                              AND length(acquisition_bytes) BETWEEN 1 AND ?
                         THEN acquisition_bytes END AS acquisition_bytes,
                   CASE WHEN typeof(acquisition_digest) = 'text'
                              AND length(acquisition_digest) = 64
                              AND acquisition_digest NOT GLOB '*[^0-9a-f]*'
                         THEN acquisition_digest END AS acquisition_digest,
                   CASE WHEN typeof(entry_count) = 'integer' AND entry_count BETWEEN 0 AND 8
                         THEN entry_count END AS entry_count,
                   CASE WHEN original_disposition IN (
                                  'acquisition_collision', 'novel', 'corroborating', 'stale',
                                  'semantic_collision', 'conflicting', 'incomparable'
                              )
                         THEN original_disposition END AS original_disposition
            FROM ingress_manifests
            ORDER BY staging_sequence
            LIMIT ?
            """,
            (MAX_ACQUISITION_BYTES, self._maximum_manifests + 1),
        ).fetchall()
        require(
            len(rows) <= self._maximum_manifests,
            "retained manifests exceed the configured reconstruction ceiling",
        )
        authorities: list[tuple[StagingAcquisition, StagingPosture]] = []
        prior_entries: tuple[IngressEntry, ...] = ()
        for expected_sequence, row in enumerate(rows, start=1):
            require(
                row["staging_sequence"] == expected_sequence,
                "staging sequence must be contiguous from one",
            )
            authority = self.reconstruct_authority(
                connection,
                row,
                provider_route_id=row["provider_route_id"],
                delivery_id=row["delivery_id"],
                prior_entries=prior_entries,
            )
            authorities.append(authority)
            prior_entries += authority[1].manifest.entries
        return tuple(authorities)

    def reconstruct_authority(
        self,
        connection: sqlite3.Connection,
        manifest_row: sqlite3.Row,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
        prior_entries: tuple[IngressEntry, ...],
    ) -> tuple[StagingAcquisition, StagingPosture]:
        acquisition = self.reconstruct_acquisition(manifest_row, provider_route_id, delivery_id)
        entries = self.reconstruct_entries(connection, manifest_row)
        manifest = self.reconstruct_manifest(manifest_row, acquisition, entries)
        grant = self.reconstruct_grant(connection, manifest)
        decisions = self.reconstruct_decisions(connection, manifest_row, entries)
        expected_entries = (
            () if acquisition.quarantined else (observation_entry(project_head(acquisition.webhook.snapshot)),)
        )
        require(entries == expected_entries, "manifest entries do not match their retained acquisition")
        expected_decision = (
            decision(
                None,
                disposition="acquisition_collision",
                reason="quarantined_acquisition",
                fatal=True,
                refresh_required=False,
            )
            if acquisition.quarantined
            else classify_head(entries[0], prior_entries)
        )
        require(
            decisions == (expected_decision,),
            "manifest does not retain its exact transaction-sequenced decision",
        )
        return (
            acquisition,
            StagingPosture(
                disposition=manifest_row["original_disposition"],
                manifest=manifest,
                grant=grant,
                decisions=decisions,
            ),
        )

    @staticmethod
    def reconstruct_acquisition(
        manifest_row: sqlite3.Row,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> StagingAcquisition:
        acquisition_bytes = bounded_blob(
            manifest_row["acquisition_bytes"],
            maximum_bytes=MAX_ACQUISITION_BYTES,
            field="acquisition",
        )
        acquisition = StagingAcquisition.model_validate_json(acquisition_bytes, strict=True)
        require(
            canonical_json(acquisition, maximum_bytes=MAX_ACQUISITION_BYTES) == acquisition_bytes,
            "acquisition bytes are not canonical",
        )
        require(
            sha256_digest(acquisition_bytes) == manifest_row["acquisition_digest"],
            "acquisition digest does not match canonical bytes",
        )
        require(
            acquisition.identity == AcquisitionIdentity(provider_route_id=provider_route_id, delivery_id=delivery_id),
            "acquisition identity does not match its lookup key",
        )
        return acquisition

    def reconstruct_entries(
        self,
        connection: sqlite3.Connection,
        manifest_row: sqlite3.Row,
    ) -> tuple[IngressEntry, ...]:
        rows = connection.execute(
            """
            SELECT CASE WHEN typeof(entry_order) = 'integer' AND entry_order BETWEEN 0 AND 7
                         THEN entry_order END AS entry_order,
                   CASE WHEN typeof(observation_key) = 'text' AND length(observation_key) = 78
                         THEN observation_key END AS observation_key,
                   CASE WHEN typeof(canonical_bytes) = 'blob'
                              AND length(canonical_bytes) BETWEEN 1 AND ?
                         THEN canonical_bytes END AS canonical_bytes
            FROM ingress_entries WHERE manifest_id = ? ORDER BY entry_order
            LIMIT ?
            """,
            (
                MAX_CANONICAL_OBSERVATION_BYTES,
                manifest_row["manifest_id"],
                MAX_ENTRIES_PER_MANIFEST + 1,
            ),
        ).fetchall()
        require(
            len(rows) <= MAX_ENTRIES_PER_MANIFEST,
            "manifest entries exceed the reconstruction ceiling",
        )
        entries = tuple(self.reconstruct_entry(row, expected_order=index) for index, row in enumerate(rows))
        require(len(entries) == manifest_row["entry_count"], "manifest entry count does not match retained entries")
        return entries

    @staticmethod
    def reconstruct_manifest(
        manifest_row: sqlite3.Row,
        acquisition: StagingAcquisition,
        entries: tuple[IngressEntry, ...],
    ) -> IngressManifest:
        manifest = IngressManifest(
            manifest_id=ManifestId(manifest_row["manifest_id"]),
            acquisition=acquisition.identity,
            policy_revision=PolicyRevision(manifest_row["policy_revision"]),
            entries=entries,
        )
        require(
            manifest.manifest_id == manifest_id_for(acquisition.identity),
            "manifest identity does not match acquisition identity",
        )
        return manifest

    @staticmethod
    def reconstruct_grant(
        connection: sqlite3.Connection,
        manifest: IngressManifest,
    ) -> AdmissionGrant:
        rows = connection.execute(
            """
            SELECT CASE WHEN typeof(grant_id) = 'text' AND length(grant_id) = 80
                         THEN grant_id END AS grant_id,
                   CASE WHEN typeof(manifest_id) = 'text' AND length(manifest_id) = 83
                         THEN manifest_id END AS manifest_id,
                   CASE WHEN typeof(manifest_digest) = 'text'
                              AND length(manifest_digest) = 64
                              AND manifest_digest NOT GLOB '*[^0-9a-f]*'
                         THEN manifest_digest END AS manifest_digest
            FROM admission_grants WHERE manifest_id = ?
            LIMIT 2
            """,
            (manifest.manifest_id,),
        ).fetchall()
        require(len(rows) == 1, "manifest must retain exactly one admission grant")
        grant = AdmissionGrant.model_validate(dict(rows[0]), strict=True)
        require(grant == grant_for(manifest), "grant does not authorize the exact reconstructed manifest")
        return grant

    @staticmethod
    def reconstruct_decisions(
        connection: sqlite3.Connection,
        manifest_row: sqlite3.Row,
        entries: tuple[IngressEntry, ...],
    ) -> tuple[AdmissionDecision, ...]:
        rows = connection.execute(
            """
            SELECT CASE WHEN typeof(decision_order) = 'integer'
                                  AND decision_order BETWEEN 0 AND 7
                         THEN decision_order END AS decision_order,
                   CASE WHEN entry_order IS NULL
                                   OR (typeof(entry_order) = 'integer' AND entry_order BETWEEN 0 AND 7)
                         THEN 1 ELSE 0 END AS entry_order_valid,
                   CASE WHEN entry_order IS NULL
                                   OR (typeof(entry_order) = 'integer' AND entry_order BETWEEN 0 AND 7)
                         THEN entry_order END AS entry_order,
                   CASE WHEN observation_key IS NULL
                                   OR (typeof(observation_key) = 'text' AND length(observation_key) = 78)
                         THEN 1 ELSE 0 END AS observation_key_valid,
                   CASE WHEN observation_key IS NULL
                                   OR (typeof(observation_key) = 'text' AND length(observation_key) = 78)
                         THEN observation_key END AS observation_key,
                   CASE WHEN disposition IN (
                                  'acquisition_collision', 'novel', 'corroborating', 'stale',
                                  'semantic_collision', 'conflicting', 'incomparable'
                              )
                         THEN disposition END AS disposition,
                   CASE WHEN reason IN (
                                  'first_observation', 'quarantined_acquisition', 'same_semantics',
                                  'key_bytes_mismatch', 'ordered_before', 'contradictory_head',
                                  'unordered_head'
                              )
                         THEN reason END AS reason,
                   CASE WHEN typeof(fatal) = 'integer' AND fatal IN (0, 1)
                         THEN fatal END AS fatal,
                   CASE WHEN typeof(refresh_required) = 'integer' AND refresh_required IN (0, 1)
                         THEN refresh_required END AS refresh_required
            FROM admission_decisions WHERE manifest_id = ? ORDER BY decision_order
            LIMIT 2
            """,
            (manifest_row["manifest_id"],),
        ).fetchall()
        require(len(rows) == 1, "manifest must retain exactly one bounded decision")
        decisions = tuple(IngressCustody.reconstruct_decision(row, index) for index, row in enumerate(rows))
        require(
            decisions[0].disposition == manifest_row["original_disposition"],
            "manifest decisions do not match the original durable disposition",
        )
        entry_order = decisions[0].entry_order
        require(entry_order is None or entry_order < len(entries), "manifest decision entry order is out of range")
        decision_entry = None if entry_order is None else entries[entry_order]
        require(
            (decision_entry is None and not entries)
            or (decision_entry is not None and decision_entry.observation_key == decisions[0].observation_key),
            "manifest decision does not identify its exact retained entry",
        )
        return decisions

    @staticmethod
    def reconstruct_decision(row: sqlite3.Row, expected_order: int) -> AdmissionDecision:
        require(row["decision_order"] == expected_order, "manifest decision order must be contiguous from zero")
        require(
            row["entry_order_valid"] == 1 and row["observation_key_valid"] == 1,
            "manifest decision optional fields exceed their storage bounds",
        )
        require(
            row["fatal"] in (0, 1) and row["refresh_required"] in (0, 1),
            "manifest decision booleans must be stored as zero or one",
        )
        return AdmissionDecision(
            entry_order=row["entry_order"],
            observation_key=row["observation_key"],
            disposition=row["disposition"],
            reason=row["reason"],
            fatal=bool(row["fatal"]),
            refresh_required=bool(row["refresh_required"]),
        )

    def reconstruct_entry(self, row: sqlite3.Row, *, expected_order: int) -> IngressEntry:
        canonical = CanonicalObservation(
            bounded_blob(
                row["canonical_bytes"],
                maximum_bytes=MAX_CANONICAL_OBSERVATION_BYTES,
                field="focused observation",
            )
        )
        observation = HeadObservation.model_validate_json(canonical, strict=True)
        require(
            canonical_json(observation, maximum_bytes=MAX_CANONICAL_OBSERVATION_BYTES) == canonical,
            "focused observation bytes are not canonical",
        )
        entry = IngressEntry(
            order=row["entry_order"],
            observation_key=ObservationKey(row["observation_key"]),
            canonical_bytes=canonical,
            observation=observation,
        )
        require(entry.order == expected_order, "manifest entry order must be contiguous from zero")
        require(
            entry.observation_key == observation_entry(observation).observation_key,
            "observation key does not match canonical bytes",
        )
        return entry

    def resources(self) -> IngressResources:
        with closing(connect(self._path)) as connection:
            manifest_row = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(length(acquisition_bytes)), 0) FROM ingress_manifests"
            ).fetchone()
            entry_row = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(length(canonical_bytes)), 0) FROM ingress_entries"
            ).fetchone()
            grants = connection.execute("SELECT COUNT(*) FROM admission_grants").fetchone()[0]
            decisions = connection.execute("SELECT COUNT(*) FROM admission_decisions").fetchone()[0]
            pages = connection.execute("PRAGMA page_count").fetchone()[0]
        return IngressResources(
            manifests=manifest_row[0],
            entries=entry_row[0],
            grants=grants,
            decisions=decisions,
            acquisition_bytes=manifest_row[1],
            canonical_bytes=entry_row[1],
            database_pages=pages,
            maximum_manifests=self._maximum_manifests,
            maximum_acquisition_bytes=self._maximum_manifests * MAX_ACQUISITION_BYTES,
            maximum_database_pages=MAX_SQLITE_PAGES,
        )
