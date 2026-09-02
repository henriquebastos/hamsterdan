# Copyright (c) 2026 Henrique Bastos

"""Durable raw webhook evidence and Intake-local outcomes."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from typing import TYPE_CHECKING

from pydantic import ValidationError

from hamsterdan2.github_app.models import (
    DeliveryId,
    NormalizedPullRequestWebhook,
    ProviderRouteId,
    VerifiedWebhookDelivery,
    WebhookEvent,
)
from hamsterdan2.host.database import (
    MAX_APPLICATION_PAGES,
    ApplicationDatabase,
    ApplicationStorageCapacityError,
)
from hamsterdan2.host.pr_workflows import PullRequestNotRegisteredError, pr_key, selected_workflow
from hamsterdan2.host.values import (
    ConfiguredProviderRoute,
    InboxAuthorization,
    InboxDelivery,
    InboxReceipt,
    InboxResourceUsage,
)
from hamsterdan2.readiness.intake_values import (
    CanonicalObservation,
    HistoryDeliveryIdentity,
    IntakeResult,
    ObservationKey,
    PolicyRevision,
    PreparedIntake,
)
from hamsterdan2.readiness.projection import project_head
from hamsterdan2.readiness.workflow_bridge import WorkflowBridgeError, bridge_head_delivery, prepare_head_intake
from hamsterdan2.workflow.observations import HeadObservation


if TYPE_CHECKING:
    from collections.abc import Callable
    import sqlite3

    from hamsterdan2.host.values import PullRequestWorkflow
    from hamsterdan2.readiness.runtime import HistoryAcceptance


MAX_NORMALIZED_BYTES = 16_384
MAX_INTAKE_REASON_BYTES = 128


class WebhookInboxError(Exception):
    """The Webhook Inbox cannot safely retain or process one delivery."""


class WebhookInboxCapacityError(WebhookInboxError):
    """The configured finite inbox row limit was reached."""


class WebhookInboxCorruptionError(WebhookInboxError):
    """A durable inbox row cannot be reconstructed exactly."""


class WebhookInboxDeliveryNotFoundError(WebhookInboxError):
    """The selected delivery ID is absent from the inbox."""


class ProviderRouteNotConfiguredError(WebhookInboxError):
    """Normalized provider evidence does not match an active route."""


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


def canonical_normalized(webhook: NormalizedPullRequestWebhook) -> str:
    content = json.dumps(
        webhook.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    if not 1 <= len(content.encode()) <= MAX_NORMALIZED_BYTES:
        raise WebhookInboxError("normalized_content_too_large")
    return content


def row_for(connection: sqlite3.Connection, delivery_id: DeliveryId) -> sqlite3.Row | None:
    rows = connection.execute(
        """
        SELECT CASE WHEN typeof(inbox_sequence) = 'integer' AND inbox_sequence > 0
                    THEN inbox_sequence END AS inbox_sequence,
               CASE WHEN typeof(delivery_id) = 'text' AND length(delivery_id) = 36
                    THEN delivery_id END AS delivery_id,
               CASE WHEN typeof(event) = 'text' AND length(event) BETWEEN 1 AND 64
                    THEN event END AS event,
               CASE WHEN typeof(raw_body) = 'blob' AND length(raw_body) BETWEEN 0 AND 1048576
                    THEN raw_body END AS raw_body,
               body_digest, collision_digest, normalized_content, provider_route_id,
               installation_id, repository_id, pull_request_number,
               observation_key, canonical_observation, policy_revision,
               bridge_identity, history_delivery_identity,
               intake_authorized, intake_outcome, intake_reason, duplicate_of_delivery_id
        FROM webhook_inbox
        WHERE delivery_id = ?
        LIMIT 2
        """,
        (delivery_id,),
    ).fetchall()
    if len(rows) > 1:
        raise WebhookInboxCorruptionError("duplicate_inbox_delivery", delivery_id, "use a fresh state root")
    return rows[0] if rows else None


def prepared_from_row(row: sqlite3.Row) -> PreparedIntake | None:
    values = (
        row["observation_key"],
        row["canonical_observation"],
        row["policy_revision"],
        row["bridge_identity"],
        row["history_delivery_identity"],
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("partial prepared Intake")
    canonical = CanonicalObservation(row["canonical_observation"])
    observation = HeadObservation.model_validate_json(canonical, strict=True)
    prepared = PreparedIntake(
        observation=observation,
        observation_key=ObservationKey(row["observation_key"]),
        canonical_observation=canonical,
        policy_revision=PolicyRevision(row["policy_revision"]),
        bridge_identity=row["bridge_identity"],
        delivery_identity=HistoryDeliveryIdentity(row["history_delivery_identity"]),
    )
    bridge_head_delivery(prepared)
    return prepared


def normalized_from_row(row: sqlite3.Row) -> NormalizedPullRequestWebhook | None:
    content = row["normalized_content"]
    if content is None:
        return None
    if not isinstance(content, str) or not 1 <= len(content.encode()) <= MAX_NORMALIZED_BYTES:
        raise ValueError("normalized content exceeds its bound")
    webhook = NormalizedPullRequestWebhook.model_validate_json(content, strict=True)
    if canonical_normalized(webhook) != content:
        raise ValueError("normalized content is not canonical")
    return webhook


def prepared_matches_normalized(
    prepared: PreparedIntake,
    normalized: NormalizedPullRequestWebhook,
) -> bool:
    expected = prepare_head_intake(
        project_head(normalized.snapshot),
        policy_revision=prepared.policy_revision,
    )
    return prepared == expected


def reconstruct_delivery(row: sqlite3.Row, delivery_id: DeliveryId) -> InboxDelivery:
    try:
        body = row["raw_body"]
        verified = VerifiedWebhookDelivery(
            delivery_id=DeliveryId(row["delivery_id"]),
            event=WebhookEvent(row["event"]),
            body=body,
        )
        normalized = normalized_from_row(row)
        prepared = prepared_from_row(row)
        provider_route_id = None if row["provider_route_id"] is None else ProviderRouteId(row["provider_route_id"])
        reconstructed = InboxDelivery(
            inbox_sequence=row["inbox_sequence"],
            verified=verified,
            body_digest=row["body_digest"],
            collision_digest=row["collision_digest"],
            normalized=normalized,
            provider_route_id=provider_route_id,
            prepared=prepared,
            intake_authorized=bool(row["intake_authorized"]),
            intake_outcome=row["intake_outcome"],
            intake_reason=row["intake_reason"],
            duplicate_of_delivery_id=(
                None if row["duplicate_of_delivery_id"] is None else DeliveryId(row["duplicate_of_delivery_id"])
            ),
        )
        valid = (
            reconstructed.verified.delivery_id == delivery_id
            and isinstance(body, bytes)
            and sha256(body).hexdigest() == reconstructed.body_digest
            and row["intake_authorized"] in (0, 1)
            and (normalized is None or normalized.provenance.delivery_id == delivery_id)
            and (
                prepared is None
                or (
                    normalized is not None
                    and provider_route_id is not None
                    and prepared_matches_normalized(prepared, normalized)
                    and prepared.observation.pr_identity.installation_id == row["installation_id"]
                    and prepared.observation.pr_identity.repository_id == row["repository_id"]
                    and prepared.observation.pr_identity.pull_request_number == row["pull_request_number"]
                )
            )
        )
        require_reconstructible(valid=valid)
    except ValidationError, TypeError, ValueError, WorkflowBridgeError:
        raise WebhookInboxCorruptionError(
            "malformed_inbox_delivery",
            delivery_id,
            "use a fresh state root",
        ) from None
    return reconstructed


def require_reconstructible(*, valid: bool) -> None:
    if not valid:
        raise ValueError("inbox row does not match its durable identity")


def intake_result(delivery: InboxDelivery, *, occurrence: int | None = None) -> IntakeResult:
    if delivery.intake_outcome is None:
        raise WebhookInboxCorruptionError("missing_intake_outcome", delivery.verified.delivery_id)
    delivery_identity = (
        delivery.prepared.delivery_identity if delivery.intake_authorized and delivery.prepared is not None else None
    )
    return IntakeResult(
        delivery_id=delivery.verified.delivery_id,
        outcome=delivery.intake_outcome,
        reason=delivery.intake_reason or "missing_intake_reason",
        pr_identity=None if delivery.prepared is None else delivery.prepared.observation.pr_identity,
        observation_key=None if delivery.prepared is None else delivery.prepared.observation_key,
        delivery_identity=delivery_identity,
        occurrence=occurrence,
    )


def authorization_values(authorization: InboxAuthorization) -> tuple[object, ...]:
    pr_identity = authorization.prepared.observation.pr_identity
    return (
        canonical_normalized(authorization.normalized),
        authorization.provider_route_id,
        *pr_key(pr_identity),
        authorization.prepared.observation_key,
        bytes(authorization.prepared.canonical_observation),
        authorization.prepared.policy_revision,
        authorization.prepared.bridge_identity,
        authorization.prepared.delivery_identity,
    )


def require_delivery(
    connection: sqlite3.Connection,
    delivery_id: DeliveryId,
) -> InboxDelivery:
    row = row_for(connection, delivery_id)
    if row is None:
        raise WebhookInboxDeliveryNotFoundError(delivery_id)
    return reconstruct_delivery(row, delivery_id)


def classify_redelivery(
    connection: sqlite3.Connection,
    recorded: InboxDelivery,
    verified: VerifiedWebhookDelivery,
    digest: str,
) -> InboxReceipt:
    exact = (
        recorded.verified.event == verified.event
        and recorded.verified.body == verified.body
        and recorded.body_digest == digest
    )
    if exact:
        disposition = "duplicate"
    else:
        disposition = "collision"
        retain_collision(connection, recorded, digest)
    return InboxReceipt(
        delivery_id=verified.delivery_id,
        inbox_sequence=recorded.inbox_sequence,
        disposition=disposition,
    )


def retain_collision(
    connection: sqlite3.Connection,
    recorded: InboxDelivery,
    digest: str,
) -> None:
    if recorded.collision_digest is not None:
        return
    if not recorded.intake_authorized and recorded.intake_outcome is None:
        connection.execute(
            """
            UPDATE webhook_inbox
            SET collision_digest = ?, intake_outcome = 'rejected',
                intake_reason = 'delivery_collision'
            WHERE delivery_id = ?
            """,
            (digest, recorded.verified.delivery_id),
        )
        return
    connection.execute(
        "UPDATE webhook_inbox SET collision_digest = ? WHERE delivery_id = ?",
        (digest, recorded.verified.delivery_id),
    )


def retain_first(
    connection: sqlite3.Connection,
    database: ApplicationDatabase,
    verified: VerifiedWebhookDelivery,
    digest: str,
) -> InboxReceipt:
    count = connection.execute("SELECT COUNT(*) FROM webhook_inbox").fetchone()[0]
    if count >= database.maximum_deliveries:
        raise WebhookInboxCapacityError("inbox_capacity_exhausted")
    cursor = connection.execute(
        "INSERT INTO webhook_inbox (delivery_id, event, raw_body, body_digest) VALUES (?, ?, ?, ?)",
        (verified.delivery_id, verified.event, verified.body, digest),
    )
    sequence = cursor.lastrowid
    if sequence is None:
        raise WebhookInboxError("inbox_sequence_not_assigned")
    return InboxReceipt(
        delivery_id=verified.delivery_id,
        inbox_sequence=sequence,
        disposition="received",
    )


def record_rejection(
    connection: sqlite3.Connection,
    delivery: InboxDelivery,
    *,
    reason: str,
    normalized: NormalizedPullRequestWebhook | None,
) -> InboxDelivery:
    if delivery.intake_outcome is not None:
        return delivery
    if delivery.intake_authorized:
        raise WebhookInboxError("authorized_intake_cannot_be_rejected")
    connection.execute(
        """
        UPDATE webhook_inbox
        SET normalized_content = COALESCE(normalized_content, ?),
            intake_outcome = 'rejected', intake_reason = ?
        WHERE delivery_id = ?
        """,
        (
            None if normalized is None else canonical_normalized(normalized),
            reason,
            delivery.verified.delivery_id,
        ),
    )
    return require_delivery(connection, delivery.verified.delivery_id)


def require_authorization_matches(
    delivery: InboxDelivery,
    authorization: InboxAuthorization,
) -> None:
    if delivery.body_digest != authorization.body_digest:
        raise WebhookInboxError("authorization_body_digest_mismatch")
    if authorization.normalized.provenance.delivery_id != authorization.delivery_id:
        raise WebhookInboxError("authorization_delivery_identity_mismatch")


def require_registered_authorization(
    connection: sqlite3.Connection,
    authorization: InboxAuthorization,
) -> PullRequestWorkflow:
    pr_identity = authorization.prepared.observation.pr_identity
    workflow = selected_workflow(connection, pr_identity)
    if workflow is None:
        raise PullRequestNotRegisteredError(
            pr_key(pr_identity),
            "open this PR workflow before retrying Inbox processing",
        )
    return workflow


def require_exact_authorized_replay(
    delivery: InboxDelivery,
    authorization: InboxAuthorization,
) -> None:
    expected = InboxDelivery(
        inbox_sequence=delivery.inbox_sequence,
        verified=delivery.verified,
        body_digest=delivery.body_digest,
        collision_digest=delivery.collision_digest,
        normalized=authorization.normalized,
        provider_route_id=authorization.provider_route_id,
        prepared=authorization.prepared,
        intake_authorized=True,
    )
    if delivery != expected:
        raise WebhookInboxCorruptionError("authorized_intake_mismatch", authorization.delivery_id)


def prior_authorization_result(
    connection: sqlite3.Connection,
    delivery: InboxDelivery,
    authorization: InboxAuthorization,
) -> InboxDelivery | IntakeResult | None:
    if delivery.intake_outcome is not None:
        return intake_result(delivery)
    require_authorization_matches(delivery, authorization)
    require_registered_authorization(connection, authorization)
    if delivery.intake_authorized:
        require_exact_authorized_replay(delivery, authorization)
        return delivery
    if delivery.collision_digest is not None:
        rejected = record_rejection(
            connection,
            delivery,
            reason="delivery_collision",
            normalized=None,
        )
        return intake_result(rejected)
    return None


def observation_owner(
    connection: sqlite3.Connection,
    observation_key: ObservationKey,
) -> sqlite3.Row | None:
    owners = connection.execute(
        """
        SELECT delivery_id, canonical_observation
        FROM webhook_inbox
        WHERE observation_key = ? AND intake_authorized = 1
        LIMIT 2
        """,
        (observation_key,),
    ).fetchall()
    if len(owners) > 1:
        raise WebhookInboxCorruptionError("duplicate_observation_intake_owner")
    return owners[0] if owners else None


def classify_authorization(
    connection: sqlite3.Connection,
    authorization: InboxAuthorization,
) -> None:
    owner = observation_owner(connection, authorization.prepared.observation_key)
    values = authorization_values(authorization)
    if owner is None:
        connection.execute(
            """
            UPDATE webhook_inbox
            SET normalized_content = ?, provider_route_id = ?,
                installation_id = ?, repository_id = ?, pull_request_number = ?,
                observation_key = ?, canonical_observation = ?, policy_revision = ?,
                bridge_identity = ?, history_delivery_identity = ?, intake_authorized = 1
            WHERE delivery_id = ?
            """,
            (*values, authorization.delivery_id),
        )
        return
    same = owner["canonical_observation"] == authorization.prepared.canonical_observation
    outcome = "duplicate" if same else "rejected"
    reason = "same_observation" if same else "observation_key_collision"
    duplicate_of = owner["delivery_id"] if same else None
    connection.execute(
        """
        UPDATE webhook_inbox
        SET normalized_content = ?, provider_route_id = ?,
            installation_id = ?, repository_id = ?, pull_request_number = ?,
            observation_key = ?, canonical_observation = ?, policy_revision = ?,
            bridge_identity = ?, history_delivery_identity = ?,
            intake_outcome = ?, intake_reason = ?, duplicate_of_delivery_id = ?
        WHERE delivery_id = ?
        """,
        (*values, outcome, reason, duplicate_of, authorization.delivery_id),
    )


def require_authorized_delivery(
    connection: sqlite3.Connection,
    delivery_id: DeliveryId,
) -> tuple[PullRequestWorkflow, InboxDelivery, PreparedIntake]:
    delivery = require_delivery(connection, delivery_id)
    prepared = delivery.prepared
    if not delivery.intake_authorized or prepared is None:
        raise WebhookInboxError("delivery_has_no_intake_authority")
    workflow = selected_workflow(connection, prepared.observation.pr_identity)
    if workflow is None:
        raise PullRequestNotRegisteredError(prepared.observation.pr_identity)
    return workflow, delivery, prepared


class WebhookInbox:
    """Own raw evidence until one novel observation is recorded in History."""

    def __init__(
        self,
        database: ApplicationDatabase,
        *,
        routes: dict[tuple[int, int, str], ProviderRouteId] | None = None,
    ) -> None:
        self._database = database
        self._routes = routes

    @classmethod
    def from_database(
        cls,
        database: ApplicationDatabase,
        *,
        provider_routes: tuple[ConfiguredProviderRoute, ...] | None = None,
    ) -> WebhookInbox:
        routes = None if provider_routes is None else configured_routes(provider_routes)
        return cls(database, routes=routes)

    def provider_route_id(self, webhook: NormalizedPullRequestWebhook) -> ProviderRouteId:
        if self._routes is None:
            raise RuntimeError("provider routes are required for Intake processing")
        evidence = (
            webhook.route.installation_id,
            webhook.route.repository_id,
            str(webhook.route.repository_full_name),
        )
        try:
            return self._routes[evidence]
        except KeyError:
            raise ProviderRouteNotConfiguredError("route_not_configured") from None

    def record(self, verified: VerifiedWebhookDelivery) -> InboxReceipt:
        digest = sha256(verified.body).hexdigest()
        with self._database.transaction() as connection:
            row = row_for(connection, verified.delivery_id)
            if row is not None:
                return classify_redelivery(
                    connection,
                    reconstruct_delivery(row, verified.delivery_id),
                    verified,
                    digest,
                )
            return retain_first(connection, self._database, verified, digest)

    def delivery(self, delivery_id: DeliveryId) -> InboxDelivery | None:
        with closing(self._database.connect()) as connection:
            row = row_for(connection, delivery_id)
            return None if row is None else reconstruct_delivery(row, delivery_id)

    def result(self, delivery_id: DeliveryId) -> IntakeResult | None:
        delivery = self.delivery(delivery_id)
        if delivery is None or delivery.intake_outcome is None:
            return None
        return intake_result(delivery)

    def reject(
        self,
        delivery_id: DeliveryId,
        *,
        reason: str,
        normalized: NormalizedPullRequestWebhook | None = None,
    ) -> IntakeResult:
        if not 1 <= len(reason.encode()) <= MAX_INTAKE_REASON_BYTES:
            raise ValueError("Intake rejection reason must contain 1-128 bytes")
        with self._database.transaction() as connection:
            delivery = require_delivery(connection, delivery_id)
            return intake_result(
                record_rejection(
                    connection,
                    delivery,
                    reason=reason,
                    normalized=normalized,
                )
            )

    def authorize(self, authorization: InboxAuthorization) -> InboxDelivery | IntakeResult:
        with self._database.transaction() as connection:
            delivery = require_delivery(connection, authorization.delivery_id)
            prior = prior_authorization_result(connection, delivery, authorization)
            if prior is not None:
                return prior
            classify_authorization(connection, authorization)
            classified = require_delivery(connection, authorization.delivery_id)
            if classified.intake_outcome is not None:
                return intake_result(classified)
            return classified

    def record_in_history(
        self,
        delivery_id: DeliveryId,
        accept: Callable[[PullRequestWorkflow, PreparedIntake], HistoryAcceptance],
    ) -> IntakeResult:
        with self._database.transaction() as connection:
            existing = require_delivery(connection, delivery_id)
            if existing.intake_outcome is not None:
                return intake_result(existing)
            workflow, _, prepared = require_authorized_delivery(connection, delivery_id)
            accepted = accept(workflow, prepared)
            connection.execute(
                """
                UPDATE webhook_inbox
                SET intake_outcome = 'recorded', intake_reason = 'accepted_by_history'
                WHERE delivery_id = ?
                """,
                (delivery_id,),
            )
            return intake_result(
                require_delivery(connection, delivery_id),
                occurrence=accepted.occurrence,
            )

    def resources(self) -> InboxResourceUsage:
        with closing(self._database.connect()) as connection:
            workflows = connection.execute("SELECT COUNT(*) FROM pr_workflows").fetchone()[0]
            deliveries = connection.execute("SELECT COUNT(*) FROM webhook_inbox").fetchone()[0]
            pages = connection.execute("PRAGMA page_count").fetchone()[0]
        if workflows > self._database.maximum_workflows or deliveries > self._database.maximum_deliveries:
            raise ApplicationStorageCapacityError("application_row_ceiling_exceeded")
        return InboxResourceUsage(
            workflows=workflows,
            deliveries=deliveries,
            pages=pages,
            maximum_deliveries=self._database.maximum_deliveries,
            maximum_pages=MAX_APPLICATION_PAGES,
        )
