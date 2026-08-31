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
    canonical_content TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    disposition TEXT NOT NULL CHECK (disposition IN ('retained', 'quarantined')),
    collision_digest TEXT,
    UNIQUE (provider_route_id, delivery_id)
);
"""


class DeliveryRefusalError(Exception):
    """Host custody could not safely retain one normalized delivery."""

    def __init__(self, reason: RefusalReason) -> None:
        self.reason = reason
        super().__init__(reason)


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA max_page_count = {MAX_SQLITE_PAGES}")
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
        with closing(connect(path)) as connection, connection:
            connection.executescript(SCHEMA)
        return cls(path=path, routes=routes, maximum_deliveries=maximum_deliveries)

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

    def ensure_capacity(self, connection: sqlite3.Connection) -> None:
        count = connection.execute("SELECT COUNT(*) FROM delivery_custody").fetchone()[0]
        if count >= self._maximum_deliveries:
            raise DeliveryRefusalError("custody_capacity_exhausted")

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
                row = connection.execute(
                    """
                    SELECT custody_generation, canonical_content, content_digest, disposition
                    FROM delivery_custody
                    WHERE provider_route_id = ? AND delivery_id = ?
                    """,
                    (provider_route_id, delivery_id),
                ).fetchone()
                if row is not None:
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

    def retained_delivery(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> CustodiedDelivery | None:
        with closing(connect(self._path)) as connection:
            row = connection.execute(
                """
                SELECT custody_generation, canonical_content, disposition
                FROM delivery_custody
                WHERE provider_route_id = ? AND delivery_id = ?
                """,
                (provider_route_id, delivery_id),
            ).fetchone()
        if row is None:
            return None
        return CustodiedDelivery(
            provider_route_id=provider_route_id,
            custody_generation=row["custody_generation"],
            webhook=NormalizedPullRequestWebhook.model_validate_json(row["canonical_content"], strict=True),
            quarantined=row["disposition"] == "quarantined",
        )

    def retained_count(self) -> int:
        with closing(connect(self._path)) as connection:
            row = connection.execute("SELECT COUNT(*) FROM delivery_custody").fetchone()
        return int(row[0])
