from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import uuid
from contextvars import Context
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from hamsterdan.github_app.auth import GitHubAppClients, RequestMetadata
from hamsterdan.github_app.config import ConfigurationError, HostConfig
from hamsterdan.github_app.routing import InstallationRegistry
from hamsterdan.github_app.transport import GitHubKitTransport
from hamsterdan.github_app.webhooks import MAX_DELIVERY_ATTEMPTS, SUPPORTED_EVENTS, WebhookCustody, WebhookRejected


def secret(path: Path, value: bytes) -> Path:
    path.write_bytes(value)
    path.chmod(0o600)
    return path


def environment(tmp_path: Path) -> dict[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return {
        "HAMSTERDAN_GITHUB_APP_ID": "17",
        "HAMSTERDAN_GITHUB_APP_SLUG": "hamsterdan-test",
        "HAMSTERDAN_GITHUB_CLIENT_ID": "Iv1.explicit",
        "HAMSTERDAN_GITHUB_ACCOUNT_ID": "23",
        "HAMSTERDAN_GITHUB_ACCOUNT_LOGIN": "Owner",
        "HAMSTERDAN_ALLOWED_REPOSITORIES": "31:Owner/One,32:Owner/Two",
        "HAMSTERDAN_STATE_PATH": str(tmp_path / "state.db"),
        "HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE": str(secret(tmp_path / "key", key)),
        "HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE": str(secret(tmp_path / "hook", b"hook-secret")),
    }


def test_config_accepts_only_explicit_secure_secret_files_and_is_redacted(tmp_path: Path) -> None:
    env = environment(tmp_path)
    config = HostConfig.from_environment(env)
    assert config.app_id == 17 and config.bot_login == "hamsterdan-test[bot]"
    assert config.allowed_repositories == frozenset({(31, "owner/one"), (32, "owner/two")})
    assert "hook-secret" not in repr(config) and "PRIVATE KEY" not in repr(config)
    with pytest.raises(AttributeError):
        config.app_id = 18
    env["GITHUB_APP_ID"] = "999"
    assert HostConfig.from_environment(env).app_id == 17


@pytest.mark.parametrize("failure", ["symlink", "directory", "permissions", "empty", "oversized", "invalid"])
def test_config_rejects_unsafe_secret_files_without_disclosure(tmp_path: Path, failure: str) -> None:
    env = environment(tmp_path)
    path = Path(env["HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE"])
    if failure == "symlink":
        target = secret(tmp_path / "target", b"do-not-disclose")
        path.unlink()
        path.symlink_to(target)
    elif failure == "directory":
        path.unlink()
        path.mkdir()
    elif failure == "permissions":
        path.chmod(0o640)
    elif failure == "empty":
        path.write_bytes(b"")
    elif failure == "oversized":
        path.write_bytes(b"x" * 65_537)
    else:
        path.write_bytes(b"\xff")
    with pytest.raises(ConfigurationError) as caught:
        HostConfig.from_environment(env)
    assert "do-not-disclose" not in str(caught.value)


def test_app_and_installation_auth_use_jwt_then_scoped_token_and_safe_metadata(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    metadata: list[RequestMetadata] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "installation-secret", "expires_at": "2099-01-01T00:00:00Z"})
        return httpx.Response(
            200,
            headers={"x-github-request-id": "request", "x-ratelimit-remaining": "9", "x-ratelimit-reset": "10"},
            json={},
        )

    clients = GitHubAppClients(
        HostConfig.from_environment(environment(tmp_path)),
        transport=httpx.MockTransport(handler),
        metadata_hook=metadata.append,
    )
    clients.app.request("GET", "/app")
    first = clients.installation(44, [32, 31, 31])
    assert first is clients.installation(44, (31, 32))
    assert first is not clients.installation(44, (31,))
    first.request("GET", "/installation/repositories")
    assert calls[0].headers["authorization"].startswith("Bearer ey")
    assert calls[-1].headers["authorization"] == "token installation-secret"
    assert metadata[-1] == RequestMetadata("GET", "/installation/repositories", "request", 9, 10, 200)
    assert "installation-secret" not in repr(metadata) and not hasattr(metadata[-1], "headers")
    clients.close()
    clients.close()


def test_new_client_lifecycle_remints_without_a_host_token_cache(tmp_path: Path) -> None:
    minted = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal minted
        if request.url.path.endswith("/access_tokens"):
            minted += 1
            return httpx.Response(201, json={"token": f"token-{minted}", "expires_at": "2099-01-01T00:00:00Z"})
        return httpx.Response(200, json={})

    config = HostConfig.from_environment(environment(tmp_path))
    for _ in range(2):
        with GitHubAppClients(config, transport=httpx.MockTransport(handler)) as clients:
            clients.installation(44, [31]).request("GET", "/installation/repositories")
    assert minted == 2


def test_expired_installation_token_is_reminted_by_the_sdk(tmp_path: Path) -> None:
    minted = 0
    authorization: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal minted
        if request.url.path.endswith("/access_tokens"):
            minted += 1
            expires = "2000-01-01T00:00:00Z" if minted == 1 else "2099-01-01T00:00:00Z"
            return httpx.Response(201, json={"token": f"token-{minted}", "expires_at": expires})
        authorization.append(request.headers["authorization"])
        return httpx.Response(200, json={})

    with GitHubAppClients(
        HostConfig.from_environment(environment(tmp_path)), transport=httpx.MockTransport(handler)
    ) as clients:
        installation = clients.installation(44, [31])
        installation.request("GET", "/installation/repositories")
        installation.request("GET", "/installation/repositories")
    assert minted == 2
    assert authorization == ["token token-1", "token token-2"]


def test_installation_client_drives_bounded_gateway_without_exposing_token(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "installation-secret", "expires_at": "2099-01-01T00:00:00Z"})
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, content=b"bounded log")
        return httpx.Response(404, headers={"x-github-request-id": "request-404"}, json={"message": "missing"})

    with GitHubAppClients(
        HostConfig.from_environment(environment(tmp_path)),
        transport=httpx.MockTransport(handler),
    ) as clients:
        transport = GitHubKitTransport(clients.installation(44, [31]))
        response = transport.request("GET", "/repos/owner/one/missing")
        assert (response.status, response.body) == (404, {"message": "missing"})
        assert transport.download("/repos/owner/one/actions/runs/1/logs") == b"bounded log"
        assert "installation-secret" not in repr(transport)


def test_streamed_gateway_reads_body_before_context_local_client_closes(tmp_path: Path) -> None:
    class CloseSensitiveStream(httpx.SyncByteStream):
        def __init__(self, transport: CloseSensitiveTransport, body: bytes) -> None:
            self.transport, self.body = transport, body

        def __iter__(self):
            if self.transport.closed:
                raise httpx.ReadError("body read after client close")
            yield self.body

    class CloseSensitiveTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.closed = False

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            self.closed = False
            if request.url.path.endswith("/access_tokens"):
                body = b'{"token":"installation-secret","expires_at":"2099-01-01T00:00:00Z"}'
            else:
                body = b'{"ok":true}'
            return httpx.Response(200, request=request, stream=CloseSensitiveStream(self, body))

        def close(self) -> None:
            self.closed = True

    provider = CloseSensitiveTransport()
    clients = GitHubAppClients(HostConfig.from_environment(environment(tmp_path)), transport=provider)
    transport = GitHubKitTransport(clients.installation(44, [31]))
    for _ in range(2):
        response = Context().run(transport.request, "GET", "/repos/owner/one")
        assert (response.status, response.body) == (200, {"ok": True})
    clients.close()


def registry(tmp_path: Path) -> InstallationRegistry:
    return InstallationRegistry(
        tmp_path / "routing.db", account_id=23, allowed_repositories=frozenset({(31, "owner/one"), (32, "owner/two")})
    )


def test_routing_lifecycle_multiple_repositories_and_malformed_or_unknown_are_inert(tmp_path: Path) -> None:
    routes = registry(tmp_path)
    assert routes.installation("created", 44, 23)
    assert routes.repositories("added", 44, 23, ((31, "Owner/One"), (32, "owner/two")))
    assert routes.route(44, 31) is not None and routes.route(44, 32) is not None
    assert routes.repositories("removed", 44, 23, ((31, "owner/one"),)) and routes.route(44, 31) is None
    assert routes.installation("suspend", 44, 23) and routes.route(44, 32) is None
    assert routes.installation("unsuspend", 44, 23) and routes.route(44, 32) is not None
    assert routes.installation("new_permissions_accepted", 44, 23)
    assert not routes.installation("created", 0, 23)
    assert not routes.installation("created", 45, 999)
    assert not routes.repositories("added", 999, 23, ((31, "owner/one"),))
    assert not routes.repositories("added", 44, 23, ((-1, "bad"),))
    assert routes.installation("deleted", 44, 23) and routes.route(44, 32) is None


def signed_headers(body: bytes, event: str, delivery: str | None = None) -> list[tuple[str, str]]:
    signature = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    return [
        ("content-length", str(len(body))),
        ("content-type", "application/json"),
        ("x-hub-signature-256", f"sha256={signature}"),
        ("x-github-delivery", delivery or str(uuid.uuid4())),
        ("x-github-event", event),
    ]


def test_webhook_verifies_before_parse_or_persistence_and_records_rejection(tmp_path: Path) -> None:
    custody = WebhookCustody(tmp_path / "webhooks.db", webhook_secret="hook-secret")
    body = b"not json"
    headers = signed_headers(body, "ping")
    headers[2] = (headers[2][0], "sha256=" + "0" * 64)
    with pytest.raises(WebhookRejected, match="verification"):
        custody.receive(headers, body)
    assert custody.status(headers[3][1]) is None
    delivery = str(uuid.uuid4())
    with pytest.raises(WebhookRejected, match="envelope"):
        custody.receive(signed_headers(body, "ping", delivery), body)
    assert custody.status(delivery) is None


@pytest.mark.parametrize("mutation", ["content-type", "length", "sha1", "duplicate", "oversized"])
def test_webhook_enforces_exact_transport_envelope(tmp_path: Path, mutation: str) -> None:
    custody = WebhookCustody(tmp_path / "w.db", webhook_secret="hook-secret", maximum_body_bytes=20)
    body = b"{}"
    headers = signed_headers(body, "ping")
    if mutation == "content-type":
        headers[1] = ("content-type", "application/json; charset=utf-8")
    elif mutation == "length":
        headers[0] = ("content-length", "3")
    elif mutation == "sha1":
        headers[2] = ("x-hub-signature-256", "sha1=" + "0" * 40)
    elif mutation == "duplicate":
        headers.append(("Content-Length", "2"))
    else:
        body = b"{" + b" " * 20 + b"}"
    with pytest.raises(WebhookRejected):
        custody.receive(headers, body)


def test_webhook_dedupes_observes_issue_comment_and_never_stores_payload(tmp_path: Path) -> None:
    custody = WebhookCustody(tmp_path / "w.db", webhook_secret="hook-secret")
    payload = {
        "action": "created",
        "installation": {"id": 44, "account": {"id": 23}},
        "repository": {"id": 31, "full_name": "owner/one"},
        "issue": {"number": 7, "pull_request": {}},
        "comment": {
            "id": 8,
            "body": "secret payload text",
            "author_association": "MEMBER",
            "user": {"id": 9, "login": "alice", "type": "User"},
        },
    }
    body = json.dumps(payload).encode()
    delivery = str(uuid.uuid4())
    headers = signed_headers(body, "issue_comment", delivery)
    receipt = custody.receive(headers, body)
    duplicate = custody.receive(headers, body)
    assert receipt.observation is not None
    assert (
        receipt.observation.pull_request_number,
        receipt.observation.comment_id,
        receipt.observation.actor_login,
    ) == (7, 8, "alice")
    assert duplicate.disposition == "duplicate"
    db = sqlite3.connect(tmp_path / "w.db")
    rows = db.execute("select observation from inbox").fetchall()
    assert "secret payload text" in str(rows)
    assert "x-hub-signature" not in str(rows)


def test_webhook_retry_is_delayed_and_eventually_parked(tmp_path: Path) -> None:
    now = [100.0]
    custody = WebhookCustody(tmp_path / "w.db", webhook_secret="hook-secret", clock=lambda: now[0])
    body = b"{}"
    delivery = str(uuid.uuid4())
    custody.receive(signed_headers(body, "ping", delivery), body)

    for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
        pending = custody.pending()
        assert len(pending) == 1 and pending[0].attempts == attempt - 1
        custody.retry(delivery, RuntimeError("secret provider response"))
        assert custody.pending() == ()
        if attempt < MAX_DELIVERY_ATTEMPTS:
            now[0] += min(2 ** (attempt - 1), 300)

    assert custody.status(delivery) == "failed"
    assert custody.counts() == {"failed": 1}
    assert custody.failures() == (
        {
            "delivery_id": delivery,
            "event": "ping",
            "attempts": MAX_DELIVERY_ATTEMPTS,
            "error_class": "RuntimeError",
            "reason": "attempts exhausted",
        },
    )
    assert custody.requeue("not-a-uuid") is False
    assert custody.requeue(delivery) is True
    assert custody.requeue(delivery) is False
    pending = custody.pending()
    assert len(pending) == 1 and pending[0].attempts == 0


def test_webhook_custody_migrates_existing_inbox_for_retry_schedule(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    database = sqlite3.connect(path)
    database.execute(
        "CREATE TABLE inbox (delivery_id TEXT PRIMARY KEY,event TEXT NOT NULL,observation TEXT NOT NULL,"
        "status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,reason TEXT,error_class TEXT)"
    )
    database.close()
    custody = WebhookCustody(path, webhook_secret="hook-secret")
    with sqlite3.connect(path) as migrated:
        columns = {row[1] for row in migrated.execute("PRAGMA table_info(inbox)")}
    assert "next_attempt_at" in columns
    custody.close()


def test_installation_webhook_admits_initial_repositories_and_reconciliation_portfolio(tmp_path: Path) -> None:
    routes = registry(tmp_path)
    custody = WebhookCustody(tmp_path / "w.db", webhook_secret="hook-secret", registry=routes)
    payload = {
        "action": "created",
        "installation": {"id": 44, "account": {"id": 23}},
        "repositories": [{"id": 31, "full_name": "owner/one"}, {"id": 99, "full_name": "owner/no"}],
    }
    body = json.dumps(payload).encode()
    custody.receive(signed_headers(body, "installation"), body)
    assert routes.route(44, 31) is not None and routes.route(44, 99) is None
    assert {"pull_request_review_comment", "check_run", "check_suite"} <= SUPPORTED_EVENTS


@pytest.mark.parametrize(
    "event,container",
    [
        ("pull_request", "pull_request"),
        ("pull_request_review", "pull_request"),
        ("pull_request_review_comment", "pull_request"),
        ("workflow_run", "workflow_run"),
        ("check_run", "check_run"),
        ("check_suite", "check_suite"),
    ],
)
def test_reconciliation_events_extract_exact_pull_number(tmp_path: Path, event: str, container: str) -> None:
    value: dict[str, Any] = {
        "action": "completed",
        "installation": {"id": 44, "account": {"id": 23}},
        "repository": {"id": 31, "full_name": "owner/one"},
    }
    value[container] = {"number": 7} if container == "pull_request" else {"pull_requests": [{"number": 7}]}
    body = json.dumps(value).encode()
    receipt = WebhookCustody(tmp_path / f"{event}.db", webhook_secret="hook-secret").receive(
        signed_headers(body, event), body
    )
    assert receipt.observation is not None and receipt.observation.pull_request_number == 7
