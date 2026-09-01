# Copyright (c) 2026 Henrique Bastos

"""Configured route fencing and durable webhook delivery custody."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
import sqlite3
from typing import TYPE_CHECKING, Literal

from hamsterdan2.github_app.models import DeliveryId, NormalizedPullRequestWebhook, ProviderRouteId
from hamsterdan2.host.values import (
    ConfiguredProviderRoute,
    CustodiedDelivery,
    DeliveryReceipt,
    HostDeliveryCompletionReceipt,
)
from hamsterdan2.workflow.values import PullRequestSubject


if TYPE_CHECKING:
    from pathlib import Path


MAX_NORMALIZED_BYTES = 16_384
MAX_RETAINED_DELIVERIES = 10_000
MAX_SQLITE_PAGES = 65_536
SHA256_HEX_LENGTH = 64
RefusalReason = Literal[
    "custody_capacity_exhausted",
    "normalized_content_too_large",
    "route_not_configured",
]
SCHEMA = """
CREATE TABLE IF NOT EXISTS delivery_custody (
    custody_generation INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_route_id TEXT NOT NULL,
    delivery_id TEXT NOT NULL,
    canonical_content TEXT NOT NULL CHECK (
        typeof(canonical_content) = 'text'
        AND length(CAST(canonical_content AS BLOB)) BETWEEN 1 AND 16384
    ),
    content_digest TEXT NOT NULL CHECK (
        typeof(content_digest) = 'text'
        AND length(content_digest) = 64
        AND content_digest NOT GLOB '*[^0-9a-f]*'
    ),
    disposition TEXT NOT NULL CHECK (disposition IN ('retained', 'quarantined')),
    collision_digest TEXT,
    CHECK (
        (disposition = 'retained' AND collision_digest IS NULL)
        OR (
            disposition = 'quarantined'
            AND typeof(collision_digest) = 'text'
            AND length(collision_digest) = 64
            AND collision_digest NOT GLOB '*[^0-9a-f]*'
        )
    ),
    UNIQUE (provider_route_id, delivery_id)
);
CREATE TABLE IF NOT EXISTS delivery_completions (
    provider_route_id TEXT NOT NULL,
    delivery_id TEXT NOT NULL,
    custody_generation INTEGER NOT NULL,
    installation_id INTEGER NOT NULL,
    repository_id INTEGER NOT NULL,
    pull_request_number INTEGER NOT NULL,
    instance_id TEXT NOT NULL,
    bridge_identity TEXT NOT NULL CHECK (bridge_identity = 'workflow-bridge/head-seen-history-fold@3'),
    manifest_id TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    manifest_digest TEXT NOT NULL,
    entry_order INTEGER NOT NULL,
    observation_key TEXT NOT NULL,
    history_delivery_identity TEXT NOT NULL,
    occurrence INTEGER NOT NULL,
    workflow_cut TEXT NOT NULL CHECK (workflow_cut = 'observation_folded'),
    cut TEXT NOT NULL CHECK (cut = 'host_delivery_completed'),
    PRIMARY KEY (provider_route_id, delivery_id),
    FOREIGN KEY (provider_route_id, delivery_id)
        REFERENCES delivery_custody (provider_route_id, delivery_id)
);
"""


class DeliveryRefusalError(Exception):
    """Host custody could not safely retain one normalized delivery."""

    def __init__(self, reason: RefusalReason) -> None:
        self.reason = reason
        super().__init__(reason)


class DeliveryCustodyCorruptionError(Exception):
    """Durable host delivery custody failed strict reconstruction."""


class DeliveryCompletionError(Exception):
    """Host completion could not safely retain one History-proven fold."""


class DeliveryCompletionConflictError(DeliveryCompletionError):
    """The task-2 identity already names a different host completion."""


class DeliveryCompletionCapacityError(DeliveryCompletionError):
    """Host completion crossed its configured finite row boundary."""


class DeliveryCompletionCorruptionError(DeliveryCompletionError):
    """Durable host completion failed strict reconstruction."""


class DeliveryCompletionCommitError(DeliveryCompletionError):
    """SQLite did not authoritatively acknowledge the completion write."""


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    effective_maximum = connection.execute(f"PRAGMA max_page_count = {MAX_SQLITE_PAGES}").fetchone()[0]
    pages = connection.execute("PRAGMA page_count").fetchone()[0]
    if effective_maximum > MAX_SQLITE_PAGES or pages > MAX_SQLITE_PAGES:
        connection.close()
        raise DeliveryCustodyCorruptionError(
            MAX_SQLITE_PAGES,
            "use a fresh state root; durable delivery custody exceeds the SQLite page ceiling",
        )
    return connection


def canonical_content(webhook: NormalizedPullRequestWebhook) -> tuple[str, str]:
    content = json.dumps(
        webhook.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    encoded = content.encode()
    if len(encoded) > MAX_NORMALIZED_BYTES:
        raise DeliveryRefusalError("normalized_content_too_large")
    return content, sha256(encoded).hexdigest()


def require_reconstructible(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def configured_routes(
    routes: tuple[ConfiguredProviderRoute, ...],
) -> dict[tuple[int, int, str], ProviderRouteId]:
    by_evidence: dict[tuple[int, int, str], ProviderRouteId] = {}
    identities: set[ProviderRouteId] = set()
    for route in routes:
        evidence = (route.installation_id, route.repository_id, str(route.repository_full_name))
        if route.provider_route_id in identities or evidence in by_evidence:
            raise ValueError("configured provider routes must have unique identities and route evidence")
        identities.add(route.provider_route_id)
        by_evidence[evidence] = route.provider_route_id
    if not by_evidence:
        raise ValueError("configure at least one active provider route")
    return by_evidence


class DeliveryCustody:
    """Acquire each configured provider delivery once without raw input."""

    def __init__(
        self,
        *,
        path: Path,
        routes: dict[tuple[int, int, str], ProviderRouteId],
        maximum_deliveries: int,
    ) -> None:
        self._path = path
        self._routes = routes
        self._maximum_deliveries = maximum_deliveries

    @classmethod
    def from_path(
        cls,
        *,
        path: Path,
        provider_routes: tuple[ConfiguredProviderRoute, ...],
        maximum_deliveries: int = MAX_RETAINED_DELIVERIES,
    ) -> DeliveryCustody:
        if not 1 <= maximum_deliveries <= MAX_RETAINED_DELIVERIES:
            raise ValueError(f"maximum deliveries must be between 1 and {MAX_RETAINED_DELIVERIES}")
        routes = configured_routes(provider_routes)
        path.parent.mkdir(parents=True, exist_ok=True)
        custody = cls(path=path, routes=routes, maximum_deliveries=maximum_deliveries)
        with closing(connect(path)) as connection, connection:
            connection.executescript(SCHEMA)
            custody.verify_retained_capacity(connection)
        return custody

    def provider_route_id(self, webhook: NormalizedPullRequestWebhook) -> ProviderRouteId:
        evidence = (
            webhook.route.installation_id,
            webhook.route.repository_id,
            str(webhook.route.repository_full_name),
        )
        try:
            return self._routes[evidence]
        except KeyError:
            raise DeliveryRefusalError("route_not_configured") from None

    @staticmethod
    def delivery_row(
        connection: sqlite3.Connection,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> sqlite3.Row | None:
        rows = connection.execute(
            """
            SELECT CASE WHEN typeof(custody_generation) = 'integer' AND custody_generation > 0
                        THEN custody_generation END AS custody_generation,
                   CASE WHEN typeof(provider_route_id) = 'text'
                             AND length(provider_route_id) BETWEEN 1 AND 128
                        THEN provider_route_id END AS provider_route_id,
                   CASE WHEN typeof(delivery_id) = 'text' AND length(delivery_id) = 36
                        THEN delivery_id END AS delivery_id,
                   CASE WHEN typeof(canonical_content) = 'text'
                             AND length(CAST(canonical_content AS BLOB)) BETWEEN 1 AND ?
                        THEN canonical_content END AS canonical_content,
                   CASE WHEN typeof(content_digest) = 'text'
                             AND length(content_digest) = 64
                             AND content_digest NOT GLOB '*[^0-9a-f]*'
                        THEN content_digest END AS content_digest,
                   CASE WHEN disposition IN ('retained', 'quarantined')
                        THEN disposition END AS disposition,
                   CASE WHEN collision_digest IS NULL
                             OR (typeof(collision_digest) = 'text'
                                 AND length(collision_digest) = 64
                                 AND collision_digest NOT GLOB '*[^0-9a-f]*')
                        THEN 1 ELSE 0 END AS collision_digest_valid,
                   CASE WHEN collision_digest IS NULL
                             OR (typeof(collision_digest) = 'text'
                                 AND length(collision_digest) = 64
                                 AND collision_digest NOT GLOB '*[^0-9a-f]*')
                        THEN collision_digest END AS collision_digest
            FROM delivery_custody
            WHERE provider_route_id = ? AND delivery_id = ?
            LIMIT 2
            """,
            (MAX_NORMALIZED_BYTES, provider_route_id, delivery_id),
        ).fetchall()
        if len(rows) > 1:
            raise DeliveryCustodyCorruptionError(
                provider_route_id,
                delivery_id,
                "use a fresh state root; durable delivery custody failed strict reconstruction",
            )
        return rows[0] if rows else None

    def ensure_capacity(self, connection: sqlite3.Connection) -> None:
        count = connection.execute("SELECT COUNT(*) FROM delivery_custody").fetchone()[0]
        if count >= self._maximum_deliveries:
            raise DeliveryRefusalError("custody_capacity_exhausted")

    def verify_retained_capacity(self, connection: sqlite3.Connection) -> None:
        count = connection.execute("SELECT COUNT(*) FROM delivery_custody").fetchone()[0]
        if count > self._maximum_deliveries:
            raise DeliveryCustodyCorruptionError(
                self._maximum_deliveries,
                "use a fresh state root; durable delivery custody exceeds the configured row ceiling",
            )

    @staticmethod
    def retain_first(
        connection: sqlite3.Connection,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
        content: str,
        digest: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO delivery_custody (
                provider_route_id, delivery_id, canonical_content, content_digest, disposition
            ) VALUES (?, ?, ?, ?, 'retained')
            """,
            (provider_route_id, delivery_id, content, digest),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not assign a custody generation")
        return cursor.lastrowid

    def acquire(self, webhook: NormalizedPullRequestWebhook) -> DeliveryReceipt:
        provider_route_id = self.provider_route_id(webhook)
        delivery_id = webhook.provenance.delivery_id
        content, digest = canonical_content(webhook)
        with closing(connect(self._path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = self.delivery_row(
                    connection,
                    provider_route_id=provider_route_id,
                    delivery_id=delivery_id,
                )
                if row is not None:
                    self.reconstruct_delivery_row(
                        row,
                        provider_route_id=provider_route_id,
                        delivery_id=delivery_id,
                    )
                    receipt = self.classify_redelivery(
                        connection=connection,
                        row=row,
                        provider_route_id=provider_route_id,
                        delivery_id=delivery_id,
                        content=content,
                        digest=digest,
                    )
                    connection.commit()
                    return receipt
                self.ensure_capacity(connection)
                generation = self.retain_first(
                    connection,
                    provider_route_id=provider_route_id,
                    delivery_id=delivery_id,
                    content=content,
                    digest=digest,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return DeliveryReceipt(
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
            custody_generation=generation,
            disposition="retained",
        )

    def classify_redelivery(
        self,
        *,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
        content: str,
        digest: str,
    ) -> DeliveryReceipt:
        generation = int(row["custody_generation"])
        disposition = str(row["disposition"])
        exact = row["content_digest"] == digest and row["canonical_content"] == content
        if disposition == "retained" and exact:
            receipt_disposition = "exact_duplicate"
        else:
            receipt_disposition = "quarantined"
            if disposition != "quarantined":
                connection.execute(
                    """
                    UPDATE delivery_custody
                    SET disposition = 'quarantined', collision_digest = ?
                    WHERE provider_route_id = ? AND delivery_id = ?
                    """,
                    (digest, provider_route_id, delivery_id),
                )
        return DeliveryReceipt(
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
            custody_generation=generation,
            disposition=receipt_disposition,
        )

    def reconstruct_delivery_row(
        self,
        row: sqlite3.Row,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> CustodiedDelivery:
        try:
            stored_content = row["canonical_content"]
            require_reconstructible(
                isinstance(stored_content, str) and 1 <= len(stored_content) <= MAX_NORMALIZED_BYTES,
                "canonical delivery content exceeds its storage bound",
            )
            webhook = NormalizedPullRequestWebhook.model_validate_json(stored_content, strict=True)
            content, digest = canonical_content(webhook)
            reconstructed_route_id = self.provider_route_id(webhook)
            disposition = row["disposition"]
            collision_digest = row["collision_digest"]
            valid_collision_state = (disposition == "retained" and collision_digest is None) or (
                disposition == "quarantined"
                and isinstance(collision_digest, str)
                and len(collision_digest) == SHA256_HEX_LENGTH
                and all(character in "0123456789abcdef" for character in collision_digest)
            )
            custody_generation = row["custody_generation"]
            valid = (
                type(custody_generation) is int
                and custody_generation > 0
                and row["provider_route_id"] == provider_route_id
                and row["delivery_id"] == delivery_id
                and content == stored_content
                and digest == row["content_digest"]
                and webhook.provenance.delivery_id == delivery_id
                and reconstructed_route_id == provider_route_id
                and row["collision_digest_valid"] == 1
                and valid_collision_state
            )
            require_reconstructible(valid, "delivery row does not match its canonical authority")
            return CustodiedDelivery(
                provider_route_id=provider_route_id,
                custody_generation=custody_generation,
                webhook=webhook,
                quarantined=disposition == "quarantined",
            )
        except DeliveryRefusalError, TypeError, ValueError:
            raise DeliveryCustodyCorruptionError(
                provider_route_id,
                delivery_id,
                "use a fresh state root; durable delivery custody failed strict reconstruction",
            ) from None

    def retained_delivery(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> CustodiedDelivery | None:
        with closing(connect(self._path)) as connection:
            self.verify_retained_capacity(connection)
            row = self.delivery_row(
                connection,
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )
            if row is None:
                return None
            delivery = self.reconstruct_delivery_row(
                row,
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )
            current_row = self.delivery_row(
                connection,
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )
            if current_row is None:
                raise DeliveryCustodyCorruptionError(
                    provider_route_id,
                    delivery_id,
                    "use a fresh state root; durable delivery custody failed strict reconstruction",
                )
            if tuple(current_row) == tuple(row):
                return delivery
            return self.reconstruct_delivery_row(
                current_row,
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )

    def retained_count(self) -> int:
        with closing(connect(self._path)) as connection:
            row = connection.execute("SELECT COUNT(*) FROM delivery_custody").fetchone()
        return int(row[0])


class DeliveryCompletionCustody:
    """Retain one exact host receipt after History proves the source fold."""

    def __init__(self, *, path: Path, maximum_completions: int) -> None:
        self._path = path
        self._maximum_completions = maximum_completions

    @classmethod
    def from_path(
        cls,
        *,
        path: Path,
        maximum_completions: int = MAX_RETAINED_DELIVERIES,
    ) -> DeliveryCompletionCustody:
        if not 1 <= maximum_completions <= MAX_RETAINED_DELIVERIES:
            raise ValueError(f"maximum completions must be between 1 and {MAX_RETAINED_DELIVERIES}")
        path.parent.mkdir(parents=True, exist_ok=True)
        custody = cls(path=path, maximum_completions=maximum_completions)
        with closing(connect(path)) as connection, connection:
            connection.executescript(SCHEMA)
            custody.verify_completion_capacity(connection)
        return custody

    def verify_completion_capacity(self, connection: sqlite3.Connection) -> int:
        count = connection.execute("SELECT COUNT(*) FROM delivery_completions").fetchone()[0]
        if type(count) is not int or count < 0 or count > self._maximum_completions:
            raise DeliveryCompletionCorruptionError(
                "host_completion_capacity_exceeded",
                self._maximum_completions,
            )
        return count

    @staticmethod
    def completion_row(
        connection: sqlite3.Connection,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> sqlite3.Row | None:
        rows = connection.execute(
            """
            SELECT CASE WHEN typeof(provider_route_id) = 'text'
                              AND length(CAST(provider_route_id AS BLOB)) BETWEEN 1 AND 128
                        THEN provider_route_id END AS provider_route_id,
                   CASE WHEN typeof(delivery_id) = 'text' AND length(CAST(delivery_id AS BLOB)) = 36
                        THEN delivery_id END AS delivery_id,
                   CASE WHEN typeof(custody_generation) = 'integer' AND custody_generation > 0
                        THEN custody_generation END AS custody_generation,
                   CASE WHEN typeof(installation_id) = 'integer' AND installation_id > 0
                        THEN installation_id END AS installation_id,
                   CASE WHEN typeof(repository_id) = 'integer' AND repository_id > 0
                        THEN repository_id END AS repository_id,
                   CASE WHEN typeof(pull_request_number) = 'integer' AND pull_request_number > 0
                        THEN pull_request_number END AS pull_request_number,
                   CASE WHEN typeof(instance_id) = 'text'
                              AND length(CAST(instance_id AS BLOB)) BETWEEN 1 AND 128
                        THEN instance_id END AS instance_id,
                   CASE WHEN typeof(bridge_identity) = 'text'
                              AND bridge_identity = 'workflow-bridge/head-seen-history-fold@3'
                        THEN bridge_identity END AS bridge_identity,
                   CASE WHEN typeof(manifest_id) = 'text'
                              AND length(CAST(manifest_id AS BLOB)) = 83
                        THEN manifest_id END AS manifest_id,
                   CASE WHEN typeof(grant_id) = 'text'
                              AND length(CAST(grant_id AS BLOB)) = 80
                        THEN grant_id END AS grant_id,
                   CASE WHEN typeof(manifest_digest) = 'text'
                              AND length(CAST(manifest_digest AS BLOB)) = 64
                        THEN manifest_digest END AS manifest_digest,
                   CASE WHEN typeof(entry_order) = 'integer' AND entry_order BETWEEN 0 AND 7
                        THEN entry_order END AS entry_order,
                   CASE WHEN typeof(observation_key) = 'text'
                              AND length(CAST(observation_key AS BLOB)) = 78
                        THEN observation_key END AS observation_key,
                   CASE WHEN typeof(history_delivery_identity) = 'text'
                              AND length(CAST(history_delivery_identity AS BLOB)) = 91
                        THEN history_delivery_identity END AS history_delivery_identity,
                   CASE WHEN typeof(occurrence) = 'integer' AND occurrence > 0
                        THEN occurrence END AS occurrence,
                   CASE WHEN workflow_cut = 'observation_folded' THEN workflow_cut END AS workflow_cut,
                   CASE WHEN cut = 'host_delivery_completed' THEN cut END AS cut
            FROM delivery_completions
            WHERE CAST(provider_route_id AS TEXT) = ? AND CAST(delivery_id AS TEXT) = ?
            LIMIT 2
            """,
            (provider_route_id, delivery_id),
        ).fetchall()
        if len(rows) > 1:
            raise DeliveryCompletionCorruptionError(
                "duplicate_host_completion",
                provider_route_id,
                delivery_id,
            )
        return rows[0] if rows else None

    @staticmethod
    def reconstruct_completion(
        row: sqlite3.Row,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> HostDeliveryCompletionReceipt:
        if any(value is None for value in row):
            raise DeliveryCompletionCorruptionError(
                "malformed_host_completion",
                provider_route_id,
                delivery_id,
            )
        try:
            return HostDeliveryCompletionReceipt(
                provider_route_id=row["provider_route_id"],
                delivery_id=row["delivery_id"],
                custody_generation=row["custody_generation"],
                subject=PullRequestSubject(
                    installation_id=row["installation_id"],
                    repository_id=row["repository_id"],
                    pull_request_number=row["pull_request_number"],
                ),
                instance_id=row["instance_id"],
                bridge_identity=row["bridge_identity"],
                manifest_id=row["manifest_id"],
                grant_id=row["grant_id"],
                manifest_digest=row["manifest_digest"],
                entry_order=row["entry_order"],
                observation_key=row["observation_key"],
                history_delivery_identity=row["history_delivery_identity"],
                occurrence=row["occurrence"],
                workflow_cut=row["workflow_cut"],
                cut=row["cut"],
            )
        except TypeError, ValueError:
            raise DeliveryCompletionCorruptionError(
                "malformed_host_completion",
                provider_route_id,
                delivery_id,
            ) from None

    @staticmethod
    def append_completion(
        connection: sqlite3.Connection,
        receipt: HostDeliveryCompletionReceipt,
    ) -> None:
        connection.execute(
            """
            INSERT INTO delivery_completions (
                provider_route_id, delivery_id, custody_generation,
                installation_id, repository_id, pull_request_number, instance_id,
                bridge_identity, manifest_id, grant_id, manifest_digest,
                entry_order, observation_key, history_delivery_identity, occurrence,
                workflow_cut, cut
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt.provider_route_id,
                receipt.delivery_id,
                receipt.custody_generation,
                receipt.subject.installation_id,
                receipt.subject.repository_id,
                receipt.subject.pull_request_number,
                receipt.instance_id,
                receipt.bridge_identity,
                receipt.manifest_id,
                receipt.grant_id,
                receipt.manifest_digest,
                receipt.entry_order,
                receipt.observation_key,
                receipt.history_delivery_identity,
                receipt.occurrence,
                receipt.workflow_cut,
                receipt.cut,
            ),
        )

    def record_completion(
        self,
        receipt: HostDeliveryCompletionReceipt,
        *,
        expected_delivery: CustodiedDelivery,
    ) -> HostDeliveryCompletionReceipt:
        backend_refused = False
        try:
            return self.record_completion_once(receipt, expected_delivery=expected_delivery)
        except sqlite3.Error:
            backend_refused = True
        if backend_refused:
            raise DeliveryCompletionCommitError(
                "host_completion_commit_unknown",
                "reload host delivery custody before deciding whether completion committed",
            )
        raise AssertionError("host completion backend refusal was not classified")

    def record_completion_once(
        self,
        receipt: HostDeliveryCompletionReceipt,
        *,
        expected_delivery: CustodiedDelivery,
    ) -> HostDeliveryCompletionReceipt:
        with closing(connect(self._path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                recorded, inserted = self.record_completion_turn(
                    connection,
                    receipt,
                    expected_delivery=expected_delivery,
                )
            except BaseException:
                connection.rollback()
                raise
            if inserted:
                connection.commit()
            else:
                connection.rollback()
            return recorded

    def record_completion_turn(
        self,
        connection: sqlite3.Connection,
        receipt: HostDeliveryCompletionReceipt,
        *,
        expected_delivery: CustodiedDelivery,
    ) -> tuple[HostDeliveryCompletionReceipt, bool]:
        count = self.verify_completion_capacity(connection)
        self.require_matching_delivery(
            connection,
            receipt,
            expected_delivery=expected_delivery,
        )
        recorded = self.existing_completion(connection, receipt)
        if recorded is not None:
            return recorded, False
        if count >= self._maximum_completions:
            raise DeliveryCompletionCapacityError(
                "host_completion_capacity_exhausted",
                self._maximum_completions,
            )
        self.append_completion(connection, receipt)
        return receipt, True

    @staticmethod
    def require_matching_delivery(
        connection: sqlite3.Connection,
        receipt: HostDeliveryCompletionReceipt,
        *,
        expected_delivery: CustodiedDelivery,
    ) -> None:
        row = DeliveryCustody.delivery_row(
            connection,
            provider_route_id=receipt.provider_route_id,
            delivery_id=receipt.delivery_id,
        )
        expected_content, expected_digest = canonical_content(expected_delivery.webhook)
        subject = expected_delivery.webhook.snapshot.subject
        valid_disposition = row is not None and (
            (row["disposition"] == "retained" and row["collision_digest"] is None)
            or (
                row["disposition"] == "quarantined"
                and isinstance(row["collision_digest"], str)
                and len(row["collision_digest"]) == SHA256_HEX_LENGTH
                and all(character in "0123456789abcdef" for character in row["collision_digest"])
            )
        )
        valid = (
            row is not None
            and expected_delivery.provider_route_id == receipt.provider_route_id
            and expected_delivery.webhook.provenance.delivery_id == receipt.delivery_id
            and expected_delivery.custody_generation == receipt.custody_generation
            and subject.installation_id == receipt.subject.installation_id
            and subject.repository_id == receipt.subject.repository_id
            and subject.pull_request_number == receipt.subject.pull_request_number
            and row["custody_generation"] == receipt.custody_generation
            and row["provider_route_id"] == receipt.provider_route_id
            and row["delivery_id"] == receipt.delivery_id
            and row["canonical_content"] == expected_content
            and row["content_digest"] == expected_digest
            and row["collision_digest_valid"] == 1
            and valid_disposition
        )
        if not valid:
            raise DeliveryCompletionCorruptionError(
                "completion_delivery_custody_mismatch",
                receipt.provider_route_id,
                receipt.delivery_id,
            )

    def existing_completion(
        self,
        connection: sqlite3.Connection,
        receipt: HostDeliveryCompletionReceipt,
    ) -> HostDeliveryCompletionReceipt | None:
        row = self.completion_row(
            connection,
            provider_route_id=receipt.provider_route_id,
            delivery_id=receipt.delivery_id,
        )
        if row is None:
            return None
        recorded = self.reconstruct_completion(
            row,
            provider_route_id=receipt.provider_route_id,
            delivery_id=receipt.delivery_id,
        )
        if recorded != receipt:
            raise DeliveryCompletionConflictError(
                "host_completion_correlation_conflict",
                receipt.provider_route_id,
                receipt.delivery_id,
            )
        return recorded

    def completion_receipt(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
        expected_delivery: CustodiedDelivery | None = None,
    ) -> HostDeliveryCompletionReceipt | None:
        with closing(connect(self._path)) as connection:
            self.verify_completion_capacity(connection)
            row = self.completion_row(
                connection,
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )
            if row is None:
                return None
            receipt = self.reconstruct_completion(
                row,
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )
            if expected_delivery is None:
                raise DeliveryCompletionCorruptionError(
                    "completion_delivery_authority_missing",
                    provider_route_id,
                    delivery_id,
                )
            self.require_matching_delivery(
                connection,
                receipt,
                expected_delivery=expected_delivery,
            )
            return receipt

    def completion_count(self) -> int:
        with closing(connect(self._path)) as connection:
            return self.verify_completion_capacity(connection)
