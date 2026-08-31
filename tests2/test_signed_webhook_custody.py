# Copyright (c) 2026 Henrique Bastos

"""A signed GitHub webhook ends at durable replacement-host custody."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
import hashlib
import hmac
import json
from threading import Barrier
from typing import TYPE_CHECKING, cast

from fastapi.testclient import TestClient
from pydantic import ValidationError

from hamsterdan2.github_app.models import (
    DeliveryId,
    PositiveIdentifier,
    ProviderRouteId,
    PullRequestSnapshot,
    RepositoryFullName,
)
from hamsterdan2.github_app.webhooks import MAX_SECURITY_HEADER_BYTES, GitHubWebhook, WebhookRefusalError
from hamsterdan2.host.api import bounded_body, refusal_response
from hamsterdan2.host.composition import build_webhook_app
from hamsterdan2.host.delivery import MAX_SQLITE_PAGES, DeliveryCustody, connect
from hamsterdan2.host.values import ConfiguredProviderRoute

import pytest


if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI
    from starlette.requests import Request

    from hamsterdan2.host.api import HttpRefusalReason


WEBHOOK_SECRET = "task-2-webhook-secret"
DELIVERY_ID = DeliveryId("11111111-1111-4111-8111-111111111111")
PROVIDER_ROUTE_ID = ProviderRouteId("github:primary")
PROVIDER_ROUTE = ConfiguredProviderRoute(
    provider_route_id=PROVIDER_ROUTE_ID,
    installation_id=PositiveIdentifier(44),
    repository_id=PositiveIdentifier(31),
    repository_full_name=RepositoryFullName("owner/repo"),
)


def pull_request_body(
    *,
    action="synchronize",
    number=7,
    pull_request_number=7,
    state="open",
    draft=False,
    merged=False,
    mergeable=None,
    updated_at="2026-08-30T12:34:56Z",
    head_repository_id=32,
    head_ref="feature/custody",
    head_sha="a" * 40,
    base_repository_id=None,
    base_ref="main",
    base_sha="b" * 40,
    installation_id=44,
    repository_id=31,
    repository_full_name="owner/repo",
    padding="",
) -> bytes:
    return json.dumps(
        {
            "action": action,
            "number": number,
            "installation": {"id": installation_id},
            "repository": {"id": repository_id, "full_name": repository_full_name},
            "pull_request": {
                "number": pull_request_number,
                "state": state,
                "draft": draft,
                "merged": merged,
                "mergeable": mergeable,
                "updated_at": updated_at,
                "head": {"repo": {"id": head_repository_id}, "ref": head_ref, "sha": head_sha},
                "base": {
                    "repo": {"id": repository_id if base_repository_id is None else base_repository_id},
                    "ref": base_ref,
                    "sha": base_sha,
                },
            },
            "unretained_provider_field": "raw-only-marker",
            "padding": padding,
        },
        separators=(",", ":"),
    ).encode()


def signed_headers(
    body: bytes,
    *,
    delivery_id: str = str(DELIVERY_ID),
    event: str = "pull_request",
    secret: str = WEBHOOK_SECRET,
) -> dict[str, str]:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "content-type": "application/json",
        "x-github-delivery": delivery_id,
        "x-github-event": event,
        "x-hub-signature-256": f"sha256={digest}",
    }


def raw_signed_headers(body: bytes) -> list[tuple[bytes, bytes]]:
    return [
        (b"content-length", str(len(body)).encode()),
        (b"content-type", b"application/json"),
        (b"x-github-delivery", str(DELIVERY_ID).encode()),
        (b"x-github-event", b"pull_request"),
        (
            b"x-hub-signature-256",
            f"sha256={hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()}".encode(),
        ),
    ]


def replace_raw_header(
    headers: list[tuple[bytes, bytes]],
    name: bytes,
    value: bytes,
) -> list[tuple[bytes, bytes]]:
    return [(header_name, value if header_name == name else header_value) for header_name, header_value in headers]


def pull_request_body_with_size(size: int) -> bytes:
    minimum = pull_request_body()
    if len(minimum) > size:
        raise ValueError("requested body size is below the valid envelope minimum")
    return pull_request_body(padding="x" * (size - len(minimum)))


def post_after_barrier(
    app: FastAPI,
    barrier: Barrier,
    body: bytes,
    *,
    delivery_id: str = str(DELIVERY_ID),
) -> tuple[int, dict[str, object]]:
    with TestClient(app) as client:
        barrier.wait()
        response = client.post(
            "/github/webhooks",
            content=body,
            headers=signed_headers(body, delivery_id=delivery_id),
        )
    return response.status_code, response.json()


class TestSignedWebhookCustody:
    """A real ASGI request proves durable custody without opening readiness."""

    def test_valid_request_reconstructs_the_normalized_delivery_after_http_202(self, tmp_path: Path) -> None:
        body = pull_request_body()
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            response = client.post("/github/webhooks", content=body, headers=signed_headers(body))

        reconstructed = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        ).retained_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )

        assert response.status_code == 202
        assert response.json() == {
            "custody": "durable",
            "provider_route_id": "github:primary",
            "delivery_id": "11111111-1111-4111-8111-111111111111",
            "custody_generation": 1,
            "disposition": "retained",
        }
        assert reconstructed is not None
        assert reconstructed.model_dump(mode="json") == {
            "provider_route_id": "github:primary",
            "custody_generation": 1,
            "webhook": {
                "route": {
                    "installation_id": 44,
                    "repository_id": 31,
                    "repository_full_name": "owner/repo",
                },
                "snapshot": {
                    "subject": {
                        "installation_id": 44,
                        "repository_id": 31,
                        "pull_request_number": 7,
                    },
                    "head": {
                        "repository_id": 32,
                        "ref": "feature/custody",
                        "sha": "a" * 40,
                    },
                    "base": {"repository_id": 31, "ref": "main", "sha": "b" * 40},
                    "state": "open",
                    "draft": False,
                    "merged": False,
                    "mergeable": None,
                    "provider_updated_at": "2026-08-30T12:34:56Z",
                },
                "provenance": {
                    "delivery_id": "11111111-1111-4111-8111-111111111111",
                    "event": "pull_request",
                    "action": "synchronize",
                },
            },
            "quarantined": False,
        }
        assert reconstructed.is_readiness_eligible()
        assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file()) == [
            "deliveries.sqlite3"
        ]


class TestWebhookVerification:
    """Only a valid HMAC permits the GitHub boundary to parse an envelope."""

    def test_invalid_hmac_precedes_malformed_json_and_retains_nothing(self, tmp_path: Path) -> None:
        body = b"not-json"
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            invalid_hmac = client.post(
                "/github/webhooks",
                content=body,
                headers=signed_headers(body, secret="wrong-secret"),
            )
            valid_hmac = client.post("/github/webhooks", content=body, headers=signed_headers(body))

        custody = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        )
        assert invalid_hmac.status_code == 400
        assert invalid_hmac.json() == {"refusal": "invalid_signature"}
        assert valid_hmac.status_code == 400
        assert valid_hmac.json() == {"refusal": "malformed_envelope"}
        assert custody.retained_count() == 0


class TestWebhookTransportBounds:
    """The ASGI rim accepts the exact body limit and refuses the next byte."""

    def test_body_size_minus_one_limit_and_plus_one_have_exact_outcomes(self, tmp_path: Path) -> None:
        limit = 1_024
        below = pull_request_body_with_size(limit - 1)
        exact = pull_request_body_with_size(limit)
        above = pull_request_body_with_size(limit + 1)
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
            maximum_body_bytes=limit,
        )

        with TestClient(app) as client:
            below_response = client.post(
                "/github/webhooks",
                content=below,
                headers=signed_headers(below, delivery_id="22222222-2222-4222-8222-222222222222"),
            )
            exact_response = client.post(
                "/github/webhooks",
                content=exact,
                headers=signed_headers(exact, delivery_id="33333333-3333-4333-8333-333333333333"),
            )
            above_response = client.post(
                "/github/webhooks",
                content=above,
                headers=signed_headers(above, delivery_id="44444444-4444-4444-8444-444444444444"),
            )

        assert below_response.status_code == 202
        assert below_response.json()["custody_generation"] == 1
        assert exact_response.status_code == 202
        assert exact_response.json()["custody_generation"] == 2
        assert above_response.status_code == 400
        assert above_response.json() == {"refusal": "body_too_large"}
        assert (
            DeliveryCustody.from_path(
                path=tmp_path / "deliveries.sqlite3",
                provider_routes=(PROVIDER_ROUTE,),
            ).retained_count()
            == 2
        )

    def test_oversized_chunk_is_refused_before_copying_it(self) -> None:
        class CopyGuardChunk:
            def __len__(self) -> int:
                return 1

            def __iter__(self):
                raise AssertionError("oversized chunk must not be copied")

        class ChunkedRequest:
            async def stream(self):
                yield b"x" * 8
                yield CopyGuardChunk()

        with pytest.raises(WebhookRefusalError) as raised:
            asyncio.run(bounded_body(cast("Request", ChunkedRequest()), 8))

        assert raised.value.reason == "body_too_large"

    def test_duplicate_protected_header_is_refused_without_custody(self, tmp_path: Path) -> None:
        body = pull_request_body()
        headers = [*signed_headers(body).items(), ("x-github-event", "pull_request")]
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            response = client.post("/github/webhooks", content=body, headers=headers)

        assert response.status_code == 400
        assert response.json() == {"refusal": "duplicate_security_header"}
        assert (
            DeliveryCustody.from_path(
                path=tmp_path / "deliveries.sqlite3",
                provider_routes=(PROVIDER_ROUTE,),
            ).retained_count()
            == 0
        )

    @pytest.mark.parametrize(
        ("header_name", "header_value", "reason"),
        [
            (b"content-length", b"not-a-number", "invalid_content_length"),
            (b"content-length", b"1", "invalid_content_length"),
            (b"content-type", b"application/x-www-form-urlencoded", "unsupported_content_type"),
            (b"x-github-event", b"issues", "unsupported_event"),
            (b"x-github-delivery", b"not-a-uuid", "invalid_delivery_id"),
            (b"x-hub-signature-256", b"sha256=not-hex", "invalid_signature_header"),
        ],
    )
    def test_malformed_protected_transport_value_is_refused(
        self,
        header_name: bytes,
        header_value: bytes,
        reason: str,
    ) -> None:
        body = pull_request_body()
        webhook = GitHubWebhook(webhook_secret=WEBHOOK_SECRET)
        headers = replace_raw_header(raw_signed_headers(body), header_name, header_value)

        with pytest.raises(WebhookRefusalError) as raised:
            webhook.normalize(headers, body)

        assert raised.value.reason == reason

    def test_missing_content_length_and_present_transfer_encoding_are_refused(self) -> None:
        body = pull_request_body()
        webhook = GitHubWebhook(webhook_secret=WEBHOOK_SECRET)
        headers = raw_signed_headers(body)

        with pytest.raises(WebhookRefusalError) as missing_length:
            webhook.normalize(
                [(name, value) for name, value in headers if name != b"content-length"],
                body,
            )
        with pytest.raises(WebhookRefusalError) as transfer_encoding:
            webhook.normalize([*headers, (b"transfer-encoding", b"chunked")], body)

        assert missing_length.value.reason == "invalid_content_length"
        assert transfer_encoding.value.reason == "unsupported_transfer_encoding"

    @pytest.mark.parametrize(
        ("size", "reason"),
        [
            (MAX_SECURITY_HEADER_BYTES - 1, "unsupported_event"),
            (MAX_SECURITY_HEADER_BYTES, "unsupported_event"),
            (MAX_SECURITY_HEADER_BYTES + 1, "security_header_too_large"),
        ],
    )
    def test_protected_header_size_minus_one_limit_and_plus_one_are_closed(self, size: int, reason: str) -> None:
        body = pull_request_body()
        webhook = GitHubWebhook(webhook_secret=WEBHOOK_SECRET)
        headers = replace_raw_header(raw_signed_headers(body), b"x-github-event", b"x" * size)

        with pytest.raises(WebhookRefusalError) as raised:
            webhook.normalize(headers, body)

        assert raised.value.reason == reason

    def test_protected_header_limit_measures_raw_whitespace_before_normalization(self) -> None:
        body = pull_request_body()
        webhook = GitHubWebhook(webhook_secret=WEBHOOK_SECRET)
        headers = replace_raw_header(
            raw_signed_headers(body),
            b"x-github-event",
            b" " * (MAX_SECURITY_HEADER_BYTES + 1),
        )

        with pytest.raises(WebhookRefusalError) as raised:
            webhook.normalize(headers, body)

        assert raised.value.reason == "security_header_too_large"

    @pytest.mark.parametrize(
        ("target_bytes", "reason"),
        [
            (32_767, None),
            (32_768, None),
            (32_769, "headers_too_large"),
        ],
    )
    def test_complete_header_bytes_minus_one_limit_and_plus_one_are_bounded(
        self,
        target_bytes: int,
        reason: str | None,
    ) -> None:
        body = pull_request_body()
        webhook = GitHubWebhook(webhook_secret=WEBHOOK_SECRET)
        headers = raw_signed_headers(body)
        current_bytes = sum(len(name) + len(value) for name, value in headers)
        padding_name = b"x-untrusted-padding"
        headers.append((padding_name, b"x" * (target_bytes - current_bytes - len(padding_name))))

        if reason is None:
            assert webhook.normalize(headers, body).snapshot.head.sha == "a" * 40
        else:
            with pytest.raises(WebhookRefusalError) as raised:
                webhook.normalize(headers, body)
            assert raised.value.reason == reason

    @pytest.mark.parametrize(
        ("target_entries", "reason"),
        [
            (99, None),
            (100, None),
            (101, "headers_too_large"),
        ],
    )
    def test_header_count_minus_one_limit_and_plus_one_are_bounded(
        self,
        target_entries: int,
        reason: str | None,
    ) -> None:
        body = pull_request_body()
        webhook = GitHubWebhook(webhook_secret=WEBHOOK_SECRET)
        headers = raw_signed_headers(body)
        headers.extend((f"x-untrusted-{index}".encode(), b"") for index in range(target_entries - len(headers)))

        if reason is None:
            assert webhook.normalize(headers, body).snapshot.head.sha == "a" * 40
        else:
            with pytest.raises(WebhookRefusalError) as raised:
                webhook.normalize(headers, body)
            assert raised.value.reason == reason


class TestPullRequestNormalization:
    """GitHub evidence crosses the boundary with exact tri-state mergeability."""

    @pytest.mark.parametrize(
        ("mergeable", "delivery_id"),
        [
            (True, DeliveryId("55555555-5555-4555-8555-555555555555")),
            (False, DeliveryId("66666666-6666-4666-8666-666666666666")),
            (None, DeliveryId("77777777-7777-4777-8777-777777777777")),
        ],
    )
    def test_mergeability_remains_true_false_or_unknown(
        self,
        tmp_path: Path,
        *,
        mergeable: bool | None,
        delivery_id: DeliveryId,
    ) -> None:
        body = pull_request_body(mergeable=mergeable)
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            response = client.post(
                "/github/webhooks",
                content=body,
                headers=signed_headers(body, delivery_id=str(delivery_id)),
            )

        retained = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        ).retained_delivery(provider_route_id=PROVIDER_ROUTE_ID, delivery_id=delivery_id)
        assert response.status_code == 202
        assert retained is not None
        assert retained.webhook.snapshot.mergeable is mergeable

    @pytest.mark.parametrize("mergeable", [0, 1, "true", {}, []])
    def test_non_boolean_mergeability_is_refused(self, tmp_path: Path, mergeable: object) -> None:
        body = pull_request_body(mergeable=mergeable)
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            response = client.post("/github/webhooks", content=body, headers=signed_headers(body))

        assert response.status_code == 400
        assert response.json() == {"refusal": "malformed_envelope"}
        assert (
            DeliveryCustody.from_path(
                path=tmp_path / "deliveries.sqlite3",
                provider_routes=(PROVIDER_ROUTE,),
            ).retained_count()
            == 0
        )

    @pytest.mark.parametrize(
        "body",
        [
            pull_request_body(action="invented"),
            pull_request_body(number=8),
            pull_request_body(base_repository_id=99),
            pull_request_body(merged=True),
            pull_request_body(state="merged"),
            pull_request_body(updated_at="not-a-time"),
            pull_request_body(head_sha="A" * 40),
            pull_request_body(base_sha="short"),
            pull_request_body(head_ref="bad\nref"),
        ],
    )
    def test_inconsistent_or_invalid_provider_evidence_is_refused(self, tmp_path: Path, body: bytes) -> None:
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            response = client.post("/github/webhooks", content=body, headers=signed_headers(body))

        assert response.status_code == 400
        assert response.json() == {"refusal": "malformed_envelope"}
        assert (
            DeliveryCustody.from_path(
                path=tmp_path / "deliveries.sqlite3",
                provider_routes=(PROVIDER_ROUTE,),
            ).retained_count()
            == 0
        )

    def test_provider_identifier_accepts_signed_64_bit_limit_and_refuses_the_next_value(self) -> None:
        maximum_identifier = 9_223_372_036_854_775_807
        at_limit = pull_request_body(installation_id=maximum_identifier)
        above_limit = pull_request_body(installation_id=maximum_identifier + 1)
        webhook = GitHubWebhook(webhook_secret=WEBHOOK_SECRET)

        normalized = webhook.normalize(raw_signed_headers(at_limit), at_limit)
        with pytest.raises(WebhookRefusalError) as raised:
            webhook.normalize(raw_signed_headers(above_limit), above_limit)

        assert normalized.snapshot.subject.installation_id == maximum_identifier
        assert raised.value.reason == "malformed_envelope"

    @pytest.mark.parametrize(
        "provider_updated_at",
        [
            "0001-01-01T00:00:00+14:00",
            "9999-12-31T23:59:59-12:00",
        ],
    )
    def test_timestamp_outside_the_utc_range_is_a_closed_refusal(
        self,
        tmp_path: Path,
        provider_updated_at: str,
    ) -> None:
        body = pull_request_body(updated_at=provider_updated_at)
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            response = client.post("/github/webhooks", content=body, headers=signed_headers(body))

        assert response.status_code == 400
        assert response.json() == {"refusal": "malformed_envelope"}

    def test_snapshot_canonicalizes_an_aware_provider_timestamp_to_utc(self) -> None:
        body = pull_request_body()
        normalized = GitHubWebhook(webhook_secret=WEBHOOK_SECRET).normalize(raw_signed_headers(body), body)
        snapshot_payload = normalized.snapshot.model_dump()
        snapshot_payload["provider_updated_at"] = datetime(
            2026,
            8,
            30,
            14,
            34,
            56,
            tzinfo=timezone(timedelta(hours=2)),
        )

        snapshot = PullRequestSnapshot.model_validate(snapshot_payload, strict=True)

        assert snapshot.provider_updated_at == datetime(2026, 8, 30, 12, 34, 56, tzinfo=UTC)
        assert snapshot.provider_updated_at.tzinfo is UTC


class TestConfiguredRouteFence:
    """Only one exact configured provider route can acquire host custody."""

    @pytest.mark.parametrize(
        ("installation_id", "repository_id", "repository_full_name"),
        [
            (45, 31, "owner/repo"),
            (44, 33, "owner/repo"),
            (44, 31, "owner/other"),
        ],
    )
    def test_unconfigured_or_mismatched_route_is_refused_without_a_row(
        self,
        tmp_path: Path,
        installation_id: int,
        repository_id: int,
        repository_full_name: str,
    ) -> None:
        body = pull_request_body(
            installation_id=installation_id,
            repository_id=repository_id,
            repository_full_name=repository_full_name,
        )
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            response = client.post("/github/webhooks", content=body, headers=signed_headers(body))

        assert response.status_code == 400
        assert response.json() == {"refusal": "route_not_configured"}
        assert (
            DeliveryCustody.from_path(
                path=tmp_path / "deliveries.sqlite3",
                provider_routes=(PROVIDER_ROUTE,),
            ).retained_count()
            == 0
        )


class TestDurableAcquisitionIdentity:
    """Route and delivery identity classify duplicate and colliding content durably."""

    def test_exact_duplicate_keeps_one_row_and_the_first_generation(self, tmp_path: Path) -> None:
        body = pull_request_body()
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            first = client.post("/github/webhooks", content=body, headers=signed_headers(body))
            duplicate = client.post("/github/webhooks", content=body, headers=signed_headers(body))

        custody = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        )
        assert first.json()["disposition"] == "retained"
        assert duplicate.status_code == 202
        assert duplicate.json() == {
            "custody": "durable",
            "provider_route_id": "github:primary",
            "delivery_id": str(DELIVERY_ID),
            "custody_generation": 1,
            "disposition": "exact_duplicate",
        }
        assert custody.retained_count() == 1

    def test_concurrent_exact_acquisition_retains_one_row_and_returns_one_duplicate(self, tmp_path: Path) -> None:
        body = pull_request_body()
        apps = tuple(
            build_webhook_app(
                state_root=tmp_path,
                webhook_secret=WEBHOOK_SECRET,
                provider_routes=(PROVIDER_ROUTE,),
            )
            for _ in range(2)
        )
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = [
                worker.result() for worker in [workers.submit(post_after_barrier, app, barrier, body) for app in apps]
            ]

        custody = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        )
        assert [status_code for status_code, _payload in outcomes] == [202, 202]
        assert sorted(str(payload["disposition"]) for _status_code, payload in outcomes) == [
            "exact_duplicate",
            "retained",
        ]
        assert {payload["custody_generation"] for _status_code, payload in outcomes} == {1}
        assert custody.retained_count() == 1

    def test_concurrent_changed_content_quarantines_whichever_original_won(self, tmp_path: Path) -> None:
        bodies = (pull_request_body(), pull_request_body(head_sha="c" * 40))
        apps = tuple(
            build_webhook_app(
                state_root=tmp_path,
                webhook_secret=WEBHOOK_SECRET,
                provider_routes=(PROVIDER_ROUTE,),
            )
            for _ in range(2)
        )
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = [
                worker.result()
                for worker in [
                    workers.submit(post_after_barrier, app, barrier, body)
                    for app, body in zip(apps, bodies, strict=True)
                ]
            ]

        custody = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        )
        retained = custody.retained_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        retained_index = next(
            index for index, (_status_code, payload) in enumerate(outcomes) if payload["disposition"] == "retained"
        )
        expected_sha = "a" * 40 if retained_index == 0 else "c" * 40
        assert [status_code for status_code, _payload in outcomes] == [202, 202]
        assert sorted(str(payload["disposition"]) for _status_code, payload in outcomes) == [
            "quarantined",
            "retained",
        ]
        assert {payload["custody_generation"] for _status_code, payload in outcomes} == {1}
        assert custody.retained_count() == 1
        assert retained is not None
        assert retained.webhook.snapshot.head.sha == expected_sha
        assert retained.quarantined

    def test_fresh_app_redelivery_reconstructs_as_an_exact_duplicate(self, tmp_path: Path) -> None:
        body = pull_request_body()
        first_app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )
        with TestClient(first_app) as client:
            assert client.post("/github/webhooks", content=body, headers=signed_headers(body)).status_code == 202

        reconstructed_app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )
        with TestClient(reconstructed_app) as client:
            redelivery = client.post("/github/webhooks", content=body, headers=signed_headers(body))

        assert redelivery.status_code == 202
        assert redelivery.json()["custody_generation"] == 1
        assert redelivery.json()["disposition"] == "exact_duplicate"

    def test_equivalent_timestamp_offset_is_the_same_normalized_content(self, tmp_path: Path) -> None:
        utc_body = pull_request_body(updated_at="2026-08-30T12:34:56Z")
        offset_body = pull_request_body(updated_at="2026-08-30T14:34:56+02:00")
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            first = client.post("/github/webhooks", content=utc_body, headers=signed_headers(utc_body))
            redelivery = client.post("/github/webhooks", content=offset_body, headers=signed_headers(offset_body))

        assert first.status_code == 202
        assert first.json()["disposition"] == "retained"
        assert redelivery.status_code == 202
        assert redelivery.json()["disposition"] == "exact_duplicate"

    def test_changed_content_quarantines_without_overwriting_original_evidence(self, tmp_path: Path) -> None:
        original_body = pull_request_body()
        changed_body = pull_request_body(head_sha="c" * 40)
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            first = client.post(
                "/github/webhooks",
                content=original_body,
                headers=signed_headers(original_body),
            )
            collision = client.post(
                "/github/webhooks",
                content=changed_body,
                headers=signed_headers(changed_body),
            )
            quarantined_redelivery = client.post(
                "/github/webhooks",
                content=original_body,
                headers=signed_headers(original_body),
            )

        custody = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
        )
        retained = custody.retained_delivery(
            provider_route_id=PROVIDER_ROUTE_ID,
            delivery_id=DELIVERY_ID,
        )
        assert first.json()["disposition"] == "retained"
        assert collision.status_code == 202
        assert collision.json() == {
            "custody": "durable",
            "provider_route_id": "github:primary",
            "delivery_id": str(DELIVERY_ID),
            "custody_generation": 1,
            "disposition": "quarantined",
        }
        assert quarantined_redelivery.status_code == 202
        assert quarantined_redelivery.json()["disposition"] == "quarantined"
        assert custody.retained_count() == 1
        assert retained is not None
        assert retained.webhook.snapshot.head.sha == "a" * 40
        assert retained.quarantined
        assert not retained.is_readiness_eligible()


class TestCustodySecurityAndResources:
    """Custody retains only bounded normalized evidence and one row per acquisition."""

    def test_raw_input_secret_signature_and_arbitrary_header_never_enter_storage_or_response(
        self, tmp_path: Path
    ) -> None:
        body = pull_request_body()
        headers = {**signed_headers(body), "x-untrusted-diagnostic": "arbitrary-header-marker"}
        signature = headers["x-hub-signature-256"]
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
        )

        with TestClient(app) as client:
            response = client.post("/github/webhooks", content=body, headers=headers)

        database = (tmp_path / "deliveries.sqlite3").read_bytes()
        response_body = response.content
        assert response.status_code == 202
        for forbidden in (
            b"raw-only-marker",
            WEBHOOK_SECRET.encode(),
            signature.encode(),
            b"arbitrary-header-marker",
        ):
            assert forbidden not in database
            assert forbidden not in response_body

    def test_unknown_refusal_reason_cannot_be_emitted(self) -> None:
        with pytest.raises(ValidationError):
            refusal_response(cast("HttpRefusalReason", "invented_reason"))

    def test_capacity_accepts_existing_identity_but_refuses_a_second_row(self, tmp_path: Path) -> None:
        first_body = pull_request_body()
        second_body = pull_request_body(head_sha="d" * 40)
        app = build_webhook_app(
            state_root=tmp_path,
            webhook_secret=WEBHOOK_SECRET,
            provider_routes=(PROVIDER_ROUTE,),
            maximum_deliveries=1,
        )

        with TestClient(app) as client:
            first = client.post("/github/webhooks", content=first_body, headers=signed_headers(first_body))
            duplicate = client.post("/github/webhooks", content=first_body, headers=signed_headers(first_body))
            second = client.post(
                "/github/webhooks",
                content=second_body,
                headers=signed_headers(
                    second_body,
                    delivery_id="99999999-9999-4999-8999-999999999999",
                ),
            )

        path = tmp_path / "deliveries.sqlite3"
        with closing(connect(path)) as connection:
            row_count = connection.execute("SELECT COUNT(*) FROM delivery_custody").fetchone()[0]
            page_limit = connection.execute("PRAGMA max_page_count").fetchone()[0]
        assert first.status_code == 202
        assert first.json()["disposition"] == "retained"
        assert duplicate.status_code == 202
        assert duplicate.json()["disposition"] == "exact_duplicate"
        assert second.status_code == 503
        assert second.json() == {"refusal": "custody_capacity_exhausted"}
        assert row_count == 1
        assert page_limit == MAX_SQLITE_PAGES
        assert [file.name for file in tmp_path.iterdir() if file.is_file()] == ["deliveries.sqlite3"]

    def test_concurrent_distinct_identities_cannot_exceed_capacity(self, tmp_path: Path) -> None:
        body = pull_request_body()
        delivery_ids = (
            str(DELIVERY_ID),
            "99999999-9999-4999-8999-999999999999",
        )
        apps = tuple(
            build_webhook_app(
                state_root=tmp_path,
                webhook_secret=WEBHOOK_SECRET,
                provider_routes=(PROVIDER_ROUTE,),
                maximum_deliveries=1,
            )
            for _ in range(2)
        )
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = [
                worker.result()
                for worker in [
                    workers.submit(
                        post_after_barrier,
                        app,
                        barrier,
                        body,
                        delivery_id=delivery_id,
                    )
                    for app, delivery_id in zip(apps, delivery_ids, strict=True)
                ]
            ]

        custody = DeliveryCustody.from_path(
            path=tmp_path / "deliveries.sqlite3",
            provider_routes=(PROVIDER_ROUTE,),
            maximum_deliveries=1,
        )
        assert sorted(status_code for status_code, _payload in outcomes) == [202, 503]
        assert sorted(
            str(payload.get("disposition", payload.get("refusal"))) for _status_code, payload in outcomes
        ) == [
            "custody_capacity_exhausted",
            "retained",
        ]
        assert custody.retained_count() == 1
