# Copyright (c) 2026 Henrique Bastos

"""The glossary-aligned webhook inbox hands novel observations to History."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import sqlite3
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from petrus.impetus.history_store import SqliteHistoryStore

from hamsterdan2.github_app.models import (
    MAX_PROVIDER_IDENTIFIER,
    DeliveryId,
    PositiveIdentifier,
    ProviderRouteId,
    RepositoryFullName,
)
from hamsterdan2.github_app.webhooks import MAX_SECURITY_HEADER_BYTES, GitHubWebhook, WebhookRefusalError
from hamsterdan2.host.composition import (
    application_database,
    build_hamsterdan,
    build_pull_request_authority,
    build_webhook_app,
    build_webhook_inbox_worker,
)
from hamsterdan2.host.database import ApplicationStorageCorruptionError
from hamsterdan2.host.pr_workflows import PullRequestNotRegisteredError
from hamsterdan2.host.values import (
    ActionIdentity,
    ConfiguredProviderRoute,
    InboxAuthorization,
    InboxDelivery,
    OpenPullRequestCommand,
)
from hamsterdan2.host.webhook_inbox import WebhookInbox, WebhookInboxCorruptionError
from hamsterdan2.readiness.intake_values import PolicyRevision
from hamsterdan2.readiness.runtime import HistoryCorruptionError
from hamsterdan2.workflow.values import PullRequestIdentity


if TYPE_CHECKING:
    from pathlib import Path
    from typing import Protocol

    class HttpResponse(Protocol):
        status_code: int

        def json(self) -> dict[str, object]: ...

    from hamsterdan2.host.application import WebhookInboxWorker

import pytest


WEBHOOK_SECRET = "glossary-aligned-inbox-secret"
FIRST_DELIVERY = DeliveryId("11111111-1111-4111-8111-111111111111")
SECOND_DELIVERY = DeliveryId("22222222-2222-4222-8222-222222222222")
THIRD_DELIVERY = DeliveryId("33333333-3333-4333-8333-333333333333")
PR_IDENTITY = PullRequestIdentity(installation_id=44, repository_id=31, pull_request_number=7)
PROVIDER_ROUTE = ConfiguredProviderRoute(
    provider_route_id=ProviderRouteId("github:primary"),
    installation_id=PositiveIdentifier(44),
    repository_id=PositiveIdentifier(31),
    repository_full_name=RepositoryFullName("owner/repo"),
)


def pull_request_body(
    *,
    updated_at: str = "2026-08-30T12:34:56Z",
    installation_id: int = 44,
    pull_request_number: int = 7,
    head_sha: str = "a" * 40,
    state: str = "open",
    draft: bool = False,
    merged: bool = False,
) -> bytes:
    return json.dumps(
        {
            "action": "synchronize",
            "number": pull_request_number,
            "installation": {"id": installation_id},
            "repository": {"id": 31, "full_name": "owner/repo"},
            "pull_request": {
                "number": pull_request_number,
                "state": state,
                "draft": draft,
                "merged": merged,
                "mergeable": None,
                "updated_at": updated_at,
                "head": {"repo": {"id": 32}, "ref": "feature/inbox", "sha": head_sha},
                "base": {"repo": {"id": 31}, "ref": "main", "sha": "b" * 40},
            },
        },
        separators=(",", ":"),
    ).encode()


def signed_headers(
    body: bytes,
    delivery_id: DeliveryId,
    *,
    event: str = "pull_request",
) -> dict[str, str]:
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "content-type": "application/json",
        "x-github-delivery": str(delivery_id),
        "x-github-event": event,
        "x-hub-signature-256": f"sha256={digest}",
    }


def history_records(path: Path) -> tuple[object, ...]:
    history = SqliteHistoryStore(path, "github:44:31:pr:7")
    try:
        return history.records
    finally:
        history.close()


def open_pull_request(state_root: Path, pr_identity: PullRequestIdentity = PR_IDENTITY) -> None:
    build_hamsterdan(state_root=state_root).open_pull_request(
        OpenPullRequestCommand(
            action_identity=ActionIdentity(
                f"trace:open:{pr_identity.installation_id}:{pr_identity.repository_id}:"
                f"{pr_identity.pull_request_number}"
            ),
            pr_identity=pr_identity,
        )
    )


def receive(
    state_root: Path,
    body: bytes,
    delivery_id: DeliveryId,
    *,
    event: str = "pull_request",
) -> HttpResponse:
    app = build_webhook_app(state_root=state_root, webhook_secret=WEBHOOK_SECRET)
    with TestClient(app) as client:
        return client.post(
            "/github/webhooks",
            content=body,
            headers=signed_headers(body, delivery_id, event=event),
        )


def inbox_worker(state_root: Path, *, policy_revision: str = "policy:2026-09-01") -> WebhookInboxWorker:
    return build_webhook_inbox_worker(
        state_root=state_root,
        provider_routes=(PROVIDER_ROUTE,),
        policy_revision=PolicyRevision(policy_revision),
    )


class TestWebhookInboxHandoff:
    """Raw intake, semantic dedupe, and History completion have distinct owners."""

    def test_signed_malformed_body_is_saved_before_later_rejection(self, tmp_path: Path) -> None:
        body = b"{"
        app = build_webhook_app(state_root=tmp_path, webhook_secret=WEBHOOK_SECRET)

        with TestClient(app) as client:
            response = client.post(
                "/github/webhooks",
                content=body,
                headers=signed_headers(body, FIRST_DELIVERY),
            )

        worker = build_webhook_inbox_worker(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=PolicyRevision("policy:2026-09-01"),
        )
        result = worker.process_delivery(FIRST_DELIVERY)

        assert response.status_code == 200
        assert response.json() == {
            "inbox": "durable",
            "delivery_id": str(FIRST_DELIVERY),
            "inbox_sequence": 1,
            "disposition": "received",
        }
        assert result.outcome == "rejected"
        assert result.reason == "malformed_envelope"
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute(
                "SELECT raw_body, intake_outcome FROM webhook_inbox WHERE delivery_id = ?",
                (FIRST_DELIVERY,),
            ).fetchone() == (body, "rejected")

    def test_only_a_novel_observation_reaches_shared_history_and_history_owns_completion(
        self,
        tmp_path: Path,
    ) -> None:
        build_hamsterdan(state_root=tmp_path).open_pull_request(
            OpenPullRequestCommand(
                action_identity=ActionIdentity("trace:open:1"),
                pr_identity=PR_IDENTITY,
            )
        )
        app = build_webhook_app(state_root=tmp_path, webhook_secret=WEBHOOK_SECRET)
        worker = build_webhook_inbox_worker(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=PolicyRevision("policy:2026-09-01"),
        )

        first_body = pull_request_body()
        with TestClient(app) as client:
            first_response = client.post(
                "/github/webhooks",
                content=first_body,
                headers=signed_headers(first_body, FIRST_DELIVERY),
            )
        first = worker.process_delivery(FIRST_DELIVERY)
        accepted_history = history_records(tmp_path / "history.sqlite3")

        second_body = pull_request_body(updated_at="2026-08-30T12:35:56Z")
        with TestClient(app) as client:
            second_response = client.post(
                "/github/webhooks",
                content=second_body,
                headers=signed_headers(second_body, SECOND_DELIVERY),
            )
        second = worker.process_delivery(SECOND_DELIVERY)

        completion = build_pull_request_authority(state_root=tmp_path).complete_next_observation(PR_IDENTITY)

        assert first_response.status_code == second_response.status_code == 200
        assert first.outcome == "recorded"
        assert second.outcome == "duplicate"
        assert len(accepted_history) == 23
        assert history_records(tmp_path / "history.sqlite3")[:23] == accepted_history
        assert len(history_records(tmp_path / "history.sqlite3")) == 25
        assert completion.disposition == "completed"
        assert completion.checkpoint == "observation_folded"
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            outcomes = connection.execute(
                "SELECT delivery_id, intake_outcome FROM webhook_inbox ORDER BY inbox_sequence"
            ).fetchall()
        assert tables == {"pr_workflows", "webhook_inbox"}
        assert outcomes == [(str(FIRST_DELIVERY), "recorded"), (str(SECOND_DELIVERY), "duplicate")]
        assert sorted(path.name for path in tmp_path.glob("*.sqlite3")) == [
            "dispatch.sqlite3",
            "hamsterdan.sqlite3",
            "history.sqlite3",
        ]


class TestRawWebhookInbox:
    """HTTP authenticates bounded transport evidence and stops after durable storage."""

    def test_body_limit_accepts_the_boundary_and_refuses_the_next_byte(self, tmp_path: Path) -> None:
        maximum_body_bytes = 64
        accepted_body = b"x" * maximum_body_bytes
        refused_body = b"x" * (maximum_body_bytes + 1)
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            maximum_body_bytes=maximum_body_bytes,
        )

        with TestClient(app) as client:
            accepted = client.post(
                "/github/webhooks",
                content=accepted_body,
                headers=signed_headers(accepted_body, FIRST_DELIVERY),
            )
            refused = client.post(
                "/github/webhooks",
                content=refused_body,
                headers=signed_headers(refused_body, SECOND_DELIVERY),
            )

        assert accepted.status_code == 200
        assert refused.status_code == 400
        assert refused.json() == {"refusal": "body_too_large"}
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute("SELECT delivery_id, raw_body FROM webhook_inbox").fetchall() == [
                (str(FIRST_DELIVERY), accepted_body)
            ]

    def test_protected_header_bound_is_measured_before_whitespace_is_removed(self) -> None:
        body = b"{}"
        webhook = GitHubWebhook(webhook_secret=WEBHOOK_SECRET)
        headers = [
            (b"content-length", str(len(body)).encode()),
            (b"content-type", b"application/json"),
            (b"x-github-delivery", str(FIRST_DELIVERY).encode()),
            (b"x-github-event", b"pull_request"),
            (b"x-hub-signature-256", b" " * (MAX_SECURITY_HEADER_BYTES + 1)),
        ]

        with pytest.raises(WebhookRefusalError) as error:
            webhook.verify(headers, body)

        assert error.value.args == ("security_header_too_large",)
        assert error.value.__cause__ is None

    def test_invalid_signature_never_enters_the_inbox(self, tmp_path: Path) -> None:
        body = pull_request_body()
        headers = signed_headers(body, FIRST_DELIVERY)
        headers["x-hub-signature-256"] = f"sha256={'0' * 64}"
        app = build_webhook_app(state_root=tmp_path, webhook_secret=WEBHOOK_SECRET)

        with TestClient(app) as client:
            response = client.post("/github/webhooks", content=body, headers=headers)

        assert response.status_code == 400
        assert response.json() == {"refusal": "invalid_signature"}
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM webhook_inbox").fetchone()[0] == 0

    def test_delivery_id_deduplicates_transport_and_preserves_the_original_body_on_collision(
        self,
        tmp_path: Path,
    ) -> None:
        original = pull_request_body()
        changed = pull_request_body(head_sha="c" * 40)

        first = receive(tmp_path, original, FIRST_DELIVERY)
        duplicate = receive(tmp_path, original, FIRST_DELIVERY)
        collision = receive(tmp_path, changed, FIRST_DELIVERY)

        assert first.json()["disposition"] == "received"
        assert duplicate.json()["disposition"] == "duplicate"
        assert collision.json()["disposition"] == "collision"
        assert {
            first.json()["inbox_sequence"],
            duplicate.json()["inbox_sequence"],
            collision.json()["inbox_sequence"],
        } == {1}
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            row = connection.execute(
                "SELECT raw_body, collision_digest, intake_outcome, intake_reason FROM webhook_inbox"
            ).fetchone()
        assert row == (original, hashlib.sha256(changed).hexdigest(), "rejected", "delivery_collision")

    def test_concurrent_exact_redelivery_retains_one_raw_row(self, tmp_path: Path) -> None:
        body = pull_request_body()

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = tuple(executor.map(lambda _: receive(tmp_path, body, FIRST_DELIVERY), range(2)))

        dispositions = tuple(response.json()["disposition"] for response in responses)
        assert dispositions in (("received", "duplicate"), ("duplicate", "received"))
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute("SELECT delivery_id, raw_body FROM webhook_inbox").fetchall() == [
                (str(FIRST_DELIVERY), body)
            ]

    def test_signed_unsupported_event_is_stored_then_rejected_by_the_later_worker(self, tmp_path: Path) -> None:
        body = b'{"zen":"keep it logically awesome"}'

        response = receive(tmp_path, body, FIRST_DELIVERY, event="ping")
        result = inbox_worker(tmp_path).process_delivery(FIRST_DELIVERY)

        assert response.status_code == 200
        assert result.outcome == "rejected"
        assert result.reason == "unsupported_event"
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute(
                "SELECT event, raw_body FROM webhook_inbox WHERE delivery_id = ?",
                (FIRST_DELIVERY,),
            ).fetchone() == ("ping", body)

    @pytest.mark.parametrize(
        "body",
        [
            pull_request_body(installation_id=MAX_PROVIDER_IDENTIFIER + 1),
            pull_request_body(updated_at="9999-12-31T23:59:59-23:59"),
        ],
        ids=("provider-id-overflow", "provider-timestamp-utc-overflow"),
    )
    def test_unrepresentable_provider_evidence_is_retained_then_rejected(self, tmp_path: Path, body: bytes) -> None:
        response = receive(tmp_path, body, FIRST_DELIVERY)

        result = inbox_worker(tmp_path).process_delivery(FIRST_DELIVERY)

        assert response.status_code == 200
        assert result.outcome == "rejected"
        assert result.reason == "malformed_envelope"
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute("SELECT raw_body FROM webhook_inbox").fetchone()[0] == body

    def test_inbox_capacity_refuses_before_retaining_an_unbounded_row(self, tmp_path: Path) -> None:
        first_body = pull_request_body()
        second_body = pull_request_body(head_sha="c" * 40)
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            maximum_deliveries=1,
        )

        with TestClient(app) as client:
            first = client.post(
                "/github/webhooks",
                content=first_body,
                headers=signed_headers(first_body, FIRST_DELIVERY),
            )
            second = client.post(
                "/github/webhooks",
                content=second_body,
                headers=signed_headers(second_body, SECOND_DELIVERY),
            )

        assert first.status_code == 200
        assert second.status_code == 503
        assert second.json() == {"refusal": "inbox_capacity_exhausted"}
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM webhook_inbox").fetchone()[0] == 1


class TestIntakeClassification:
    """The host decides semantic novelty before offering an observation to History."""

    def test_unknown_pr_remains_pending_until_its_workflow_is_registered(self, tmp_path: Path) -> None:
        body = pull_request_body()
        receive(tmp_path, body, FIRST_DELIVERY)
        worker = inbox_worker(tmp_path)

        with pytest.raises(PullRequestNotRegisteredError):
            worker.process_delivery(FIRST_DELIVERY)

        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute(
                "SELECT normalized_content, intake_authorized, intake_outcome FROM webhook_inbox"
            ).fetchone() == (None, 0, None)
        open_pull_request(tmp_path)
        assert worker.process_delivery(FIRST_DELIVERY).outcome == "recorded"

    def test_unsupported_lifecycle_is_a_rejected_intake_without_history_acceptance(self, tmp_path: Path) -> None:
        open_pull_request(tmp_path)
        body = pull_request_body(state="closed", merged=True)
        receive(tmp_path, body, FIRST_DELIVERY)

        result = inbox_worker(tmp_path).process_delivery(FIRST_DELIVERY)

        assert result.outcome == "rejected"
        assert result.reason == "unsupported_head_lifecycle"
        assert len(history_records(tmp_path / "history.sqlite3")) == 21

    def test_durable_authorization_survives_policy_change_and_late_transport_collision(self, tmp_path: Path) -> None:
        open_pull_request(tmp_path)
        body = pull_request_body()
        receive(tmp_path, body, FIRST_DELIVERY)
        original_worker = inbox_worker(tmp_path, policy_revision="policy:original")
        authorization = original_worker.authorization_for(original_worker.selected_delivery(FIRST_DELIVERY))
        assert isinstance(authorization, InboxAuthorization)
        inbox = WebhookInbox.from_database(
            application_database(tmp_path),
            provider_routes=(PROVIDER_ROUTE,),
        )
        authorized = inbox.authorize(authorization)
        assert isinstance(authorized, InboxDelivery)
        assert authorized.intake_authorized

        changed = pull_request_body(head_sha="c" * 40)
        assert receive(tmp_path, changed, FIRST_DELIVERY).json()["disposition"] == "collision"
        result = inbox_worker(tmp_path, policy_revision="policy:changed").process_delivery(FIRST_DELIVERY)

        assert result.outcome == "recorded"
        assert result.delivery_identity == authorization.prepared.delivery_identity
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute(
                "SELECT policy_revision, collision_digest, intake_outcome FROM webhook_inbox"
            ).fetchone() == ("policy:original", hashlib.sha256(changed).hexdigest(), "recorded")

    def test_first_pending_semantic_authority_blocks_a_second_delivery_before_history(self, tmp_path: Path) -> None:
        open_pull_request(tmp_path)
        first_body = pull_request_body()
        second_body = pull_request_body(updated_at="2026-08-30T12:35:56Z")
        receive(tmp_path, first_body, FIRST_DELIVERY)
        receive(tmp_path, second_body, SECOND_DELIVERY)
        worker = inbox_worker(tmp_path)
        authorization = worker.authorization_for(worker.selected_delivery(FIRST_DELIVERY))
        assert isinstance(authorization, InboxAuthorization)
        inbox = WebhookInbox.from_database(
            application_database(tmp_path),
            provider_routes=(PROVIDER_ROUTE,),
        )
        inbox.authorize(authorization)

        duplicate = worker.process_delivery(SECOND_DELIVERY)

        assert duplicate.outcome == "duplicate"
        assert duplicate.reason == "same_observation"
        assert duplicate.delivery_identity is None
        assert len(history_records(tmp_path / "history.sqlite3")) == 21
        assert worker.process_delivery(FIRST_DELIVERY).outcome == "recorded"
        assert len(history_records(tmp_path / "history.sqlite3")) == 23

    def test_concurrent_semantic_offers_converge_on_one_history_acceptance(self, tmp_path: Path) -> None:
        open_pull_request(tmp_path)
        first_body = pull_request_body()
        second_body = pull_request_body(updated_at="2026-08-30T12:35:56Z")
        receive(tmp_path, first_body, FIRST_DELIVERY)
        receive(tmp_path, second_body, SECOND_DELIVERY)
        worker = inbox_worker(tmp_path)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(worker.process_delivery, (FIRST_DELIVERY, SECOND_DELIVERY)))

        assert sorted(result.outcome for result in results) == ["duplicate", "recorded"]
        assert len(history_records(tmp_path / "history.sqlite3")) == 23


class TestHistoryOwnership:
    """History owns accepted occurrences and their completion without a host completion ledger."""

    def test_one_pr_accepts_distinct_observations_and_completes_oldest_unfinished_first(self, tmp_path: Path) -> None:
        open_pull_request(tmp_path)
        first_body = pull_request_body(head_sha="a" * 40)
        second_body = pull_request_body(head_sha="c" * 40)
        receive(tmp_path, first_body, FIRST_DELIVERY)
        receive(tmp_path, second_body, SECOND_DELIVERY)
        worker = inbox_worker(tmp_path)

        first = worker.process_delivery(FIRST_DELIVERY)
        second = worker.process_delivery(SECOND_DELIVERY)
        authority = build_pull_request_authority(state_root=tmp_path)
        first_completion = authority.complete_next_observation(PR_IDENTITY)
        second_completion = authority.complete_next_observation(PR_IDENTITY)
        replay = authority.complete_next_observation(PR_IDENTITY)

        assert (first.outcome, first.occurrence) == ("recorded", 1)
        assert (second.outcome, second.occurrence) == ("recorded", 2)
        assert (first_completion.disposition, first_completion.occurrence) == ("completed", 1)
        assert (second_completion.disposition, second_completion.occurrence) == ("completed", 2)
        assert (replay.disposition, replay.occurrence) == ("already_completed", 2)
        assert len(history_records(tmp_path / "history.sqlite3")) == 29

    def test_shared_history_is_partitioned_by_pr_identity_not_by_database_file(self, tmp_path: Path) -> None:
        second_pr = PullRequestIdentity(installation_id=44, repository_id=31, pull_request_number=8)
        open_pull_request(tmp_path)
        open_pull_request(tmp_path, second_pr)
        first_body = pull_request_body(pull_request_number=7)
        second_body = pull_request_body(pull_request_number=8)
        receive(tmp_path, first_body, FIRST_DELIVERY)
        receive(tmp_path, second_body, SECOND_DELIVERY)
        worker = inbox_worker(tmp_path)

        first = worker.process_delivery(FIRST_DELIVERY)
        second = worker.process_delivery(SECOND_DELIVERY)

        assert first.observation_key != second.observation_key
        assert len(history_records(tmp_path / "history.sqlite3")) == 23
        other_history = SqliteHistoryStore(tmp_path / "history.sqlite3", "github:44:31:pr:8")
        try:
            assert len(other_history.records) == 23
        finally:
            other_history.close()
        assert sorted(path.name for path in tmp_path.glob("*.sqlite3")) == [
            "dispatch.sqlite3",
            "hamsterdan.sqlite3",
            "history.sqlite3",
        ]


class TestDurableIntegrity:
    """Fresh owners reject cross-boundary mutations rather than trusting SQLite rows."""

    def test_pr_identity_refuses_values_above_the_shared_sqlite_range(self) -> None:
        with pytest.raises(ValueError, match="less than or equal to"):
            PullRequestIdentity(
                installation_id=MAX_PROVIDER_IDENTIFIER + 1,
                repository_id=31,
                pull_request_number=7,
            )

    def test_authorized_observation_must_still_match_its_normalized_inbox_evidence(self, tmp_path: Path) -> None:
        open_pull_request(tmp_path)
        body = pull_request_body()
        receive(tmp_path, body, FIRST_DELIVERY)
        worker = inbox_worker(tmp_path)
        authorization = worker.authorization_for(worker.selected_delivery(FIRST_DELIVERY))
        assert isinstance(authorization, InboxAuthorization)
        inbox = WebhookInbox.from_database(
            application_database(tmp_path),
            provider_routes=(PROVIDER_ROUTE,),
        )
        inbox.authorize(authorization)
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            content = connection.execute("SELECT normalized_content FROM webhook_inbox").fetchone()[0]
            mutated = json.loads(content)
            mutated["snapshot"]["head"]["sha"] = "d" * 40
            connection.execute(
                "UPDATE webhook_inbox SET normalized_content = ?",
                (json.dumps(mutated, ensure_ascii=True, separators=(",", ":"), sort_keys=True),),
            )

        with pytest.raises(WebhookInboxCorruptionError):
            inbox_worker(tmp_path).process_delivery(FIRST_DELIVERY)

    def test_completed_history_terminal_must_match_the_exact_accepted_observation(self, tmp_path: Path) -> None:
        open_pull_request(tmp_path)
        body = pull_request_body()
        receive(tmp_path, body, FIRST_DELIVERY)
        assert inbox_worker(tmp_path).process_delivery(FIRST_DELIVERY).outcome == "recorded"
        authority = build_pull_request_authority(state_root=tmp_path)
        assert authority.complete_next_observation(PR_IDENTITY).disposition == "completed"
        with sqlite3.connect(tmp_path / "history.sqlite3") as connection:
            raw = connection.execute(
                """
                SELECT payload FROM impetus_history_events
                WHERE instance = ? AND position = 23
                """,
                ("github:44:31:pr:7",),
            ).fetchone()[0]
            mutated = json.loads(raw)
            mutated["tokens"][0]["data"]["head"] = "d" * 40
            connection.execute(
                """
                UPDATE impetus_history_events SET payload = ?
                WHERE instance = ? AND position = 23
                """,
                (json.dumps(mutated, separators=(",", ":"), sort_keys=True), "github:44:31:pr:7"),
            )

        with pytest.raises(HistoryCorruptionError):
            build_pull_request_authority(state_root=tmp_path).complete_next_observation(PR_IDENTITY)

    def test_completed_history_terminal_pair_must_keep_its_exact_order(self, tmp_path: Path) -> None:
        open_pull_request(tmp_path)
        body = pull_request_body()
        receive(tmp_path, body, FIRST_DELIVERY)
        assert inbox_worker(tmp_path).process_delivery(FIRST_DELIVERY).outcome == "recorded"
        authority = build_pull_request_authority(state_root=tmp_path)
        assert authority.complete_next_observation(PR_IDENTITY).disposition == "completed"
        with sqlite3.connect(tmp_path / "history.sqlite3") as connection:
            rows = connection.execute(
                """
                SELECT position, payload FROM impetus_history_events
                WHERE instance = ? AND position IN (23, 24)
                ORDER BY position
                """,
                ("github:44:31:pr:7",),
            ).fetchall()
            connection.executemany(
                """
                UPDATE impetus_history_events SET payload = ?
                WHERE instance = ? AND position = ?
                """,
                (
                    (rows[1][1], "github:44:31:pr:7", rows[0][0]),
                    (rows[0][1], "github:44:31:pr:7", rows[1][0]),
                ),
            )

        with pytest.raises(HistoryCorruptionError):
            build_pull_request_authority(state_root=tmp_path).complete_next_observation(PR_IDENTITY)

    def test_application_database_rejects_any_third_application_table(self, tmp_path: Path) -> None:
        database = application_database(tmp_path)
        with database.connect() as connection:
            connection.execute("CREATE TABLE accidental_completion (identity TEXT PRIMARY KEY)")
            connection.commit()

        with pytest.raises(ApplicationStorageCorruptionError):
            application_database(tmp_path)
