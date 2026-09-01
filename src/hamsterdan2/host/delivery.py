# Copyright (c) 2026 Henrique Bastos

"""Configured route fencing and durable webhook delivery custody."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
import sqlite3
from typing import TYPE_CHECKING, Literal

from hamsterdan2.github_app.models import DeliveryId, NormalizedPullRequestWebhook, ProviderRouteId
from hamsterdan2.host.values import ConfiguredProviderRoute, CustodiedDelivery, DeliveryReceipt


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
"""


class DeliveryRefusalError(Exception):
    """Host custody could not safely retain one normalized delivery."""

    def __init__(self, reason: RefusalReason) -> None:
        self.reason = reason
        super().__init__(reason)


class DeliveryCustodyCorruptionError(Exception):
    """Durable host delivery custody failed strict reconstruction."""


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
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
