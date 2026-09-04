# Copyright (c) 2026 Henrique Bastos

"""Real process loss at each durable CV21 Intake handoff."""

from __future__ import annotations

import asyncio
from functools import partial
import hashlib
import hmac
import json
import multiprocessing
import os
import signal
import sqlite3
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from petrus.impetus.history_store import SqliteHistoryStore

from hamsterdan2.github_app.models import DeliveryId, PositiveIdentifier, ProviderRouteId, RepositoryFullName
from hamsterdan2.host.composition import (
    application_database,
    build_hamsterdan,
    build_pull_request_authority,
    build_webhook_app,
    build_webhook_inbox_worker,
)
from hamsterdan2.host.pr_workflows import PullRequestWorkflows
from hamsterdan2.host.values import (
    ActionIdentity,
    ConfiguredProviderRoute,
    InboxAuthorization,
    OpenPullRequestCommand,
    PullRequestWorkflow,
)
from hamsterdan2.host.webhook_inbox import WebhookInbox
from hamsterdan2.readiness.intake_values import PolicyRevision, PreparedIntake
from hamsterdan2.readiness.runtime import HistoryAcceptance, build_readiness_runtime
from hamsterdan2.workflow.values import AwaitingObservation, PullRequestIdentity


if TYPE_CHECKING:
    from collections.abc import Callable
    from multiprocessing.process import BaseProcess
    from pathlib import Path

    from starlette.types import ASGIApp, Message, Scope


WEBHOOK_SECRET = "process-recovery-inbox-secret"
DELIVERY_ID = DeliveryId("11111111-1111-4111-8111-111111111111")
PR_IDENTITY = PullRequestIdentity(installation_id=44, repository_id=31, pull_request_number=7)
PROVIDER_ROUTE = ConfiguredProviderRoute(
    provider_route_id=ProviderRouteId("github:primary"),
    installation_id=PositiveIdentifier(44),
    repository_id=PositiveIdentifier(31),
    repository_full_name=RepositoryFullName("owner/repo"),
)


def pull_request_body() -> bytes:
    return json.dumps(
        {
            "action": "synchronize",
            "number": 7,
            "installation": {"id": 44},
            "repository": {"id": 31, "full_name": "owner/repo"},
            "pull_request": {
                "number": 7,
                "state": "open",
                "draft": False,
                "merged": False,
                "mergeable": None,
                "updated_at": "2026-08-30T12:34:56Z",
                "head": {"repo": {"id": 32}, "ref": "feature/inbox", "sha": "a" * 40},
                "base": {"repo": {"id": 31}, "ref": "main", "sha": "b" * 40},
            },
        },
        separators=(",", ":"),
    ).encode()


def signed_asgi_headers(body: bytes) -> list[tuple[bytes, bytes]]:
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"x-github-delivery", str(DELIVERY_ID).encode()),
        (b"x-github-event", b"pull_request"),
        (b"x-hub-signature-256", f"sha256={digest}".encode()),
    ]


def signed_http_headers(body: bytes) -> dict[str, str]:
    return {name.decode(): value.decode() for name, value in signed_asgi_headers(body) if name != b"content-length"}


def open_pr(state_root: Path) -> None:
    build_hamsterdan(state_root=state_root).open_pull_request(
        OpenPullRequestCommand(
            action_identity=ActionIdentity("process:open:1"),
            pr_identity=PR_IDENTITY,
        )
    )


def open_history_then_crash(workflow: PullRequestWorkflow, *, state_root: Path) -> AwaitingObservation:
    opened = build_readiness_runtime(
        history_path=state_root / "history.sqlite3",
        dispatch_path=state_root / "dispatch.sqlite3",
        workflow_id=workflow.workflow_id,
    ).open(workflow.pr_identity)
    os.kill(os.getpid(), signal.SIGKILL)
    return opened


def workflow_open_child(state_root: Path) -> None:
    PullRequestWorkflows(application_database(state_root)).open(
        OpenPullRequestCommand(
            action_identity=ActionIdentity("process:open:1"),
            pr_identity=PR_IDENTITY,
        ),
        partial(open_history_then_crash, state_root=state_root),
    )


def receive_body(state_root: Path, body: bytes) -> None:
    app = build_webhook_app(state_root=state_root, webhook_secret=WEBHOOK_SECRET)
    with TestClient(app) as client:
        response = client.post("/github/webhooks", content=body, headers=signed_http_headers(body))
    assert response.status_code == 200


def history_length(state_root: Path) -> int:
    history = SqliteHistoryStore(state_root / "history.sqlite3", "github:44:31:pr:7")
    try:
        return len(history)
    finally:
        history.close()


async def crash_after_response_start(app: ASGIApp, body: bytes) -> None:
    messages: list[Message] = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive() -> Message:
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            os.kill(os.getpid(), signal.SIGKILL)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/github/webhooks",
        "raw_path": b"/github/webhooks",
        "query_string": b"",
        "root_path": "",
        "headers": signed_asgi_headers(body),
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }
    await app(scope, receive, send)


def http_child(state_root: Path, body: bytes) -> None:
    app = build_webhook_app(state_root=state_root, webhook_secret=WEBHOOK_SECRET)
    asyncio.run(crash_after_response_start(app, body))


def accept_then_crash(
    workflow: PullRequestWorkflow,
    prepared: PreparedIntake,
    *,
    state_root: Path,
) -> HistoryAcceptance:
    build_readiness_runtime(
        history_path=state_root / "history.sqlite3",
        dispatch_path=state_root / "dispatch.sqlite3",
        workflow_id=workflow.workflow_id,
    ).accept(workflow, prepared)
    os.kill(os.getpid(), signal.SIGKILL)
    raise AssertionError("SIGKILL did not stop the process")


def history_acceptance_child(state_root: Path) -> None:
    worker = build_webhook_inbox_worker(
        state_root=state_root,
        provider_routes=(PROVIDER_ROUTE,),
        policy_revision=PolicyRevision("policy:process"),
    )
    inbox = WebhookInbox.from_database(
        application_database(state_root),
        provider_routes=(PROVIDER_ROUTE,),
    )
    authorization = worker.authorization_for(worker.selected_delivery(DELIVERY_ID))
    assert isinstance(authorization, InboxAuthorization)
    inbox.authorize(authorization)
    inbox.record_in_history(
        DELIVERY_ID,
        partial(accept_then_crash, state_root=state_root),
    )


def complete_then_crash(workflow: PullRequestWorkflow, *, state_root: Path) -> None:
    build_readiness_runtime(
        history_path=state_root / "history.sqlite3",
        dispatch_path=state_root / "dispatch.sqlite3",
        workflow_id=workflow.workflow_id,
    ).complete_next(workflow)
    os.kill(os.getpid(), signal.SIGKILL)


def history_completion_child(state_root: Path) -> None:
    workflows = PullRequestWorkflows(application_database(state_root))
    workflows.run_authority(
        PR_IDENTITY,
        partial(complete_then_crash, state_root=state_root),
    )


def run_until_sigkill(target: Callable[..., object], *arguments: object) -> None:
    context = multiprocessing.get_context("fork")
    process = context.Process(target=target, args=arguments)
    process.start()
    process.join(15)
    require_sigkill(process)


def require_sigkill(process: BaseProcess) -> None:
    if process.is_alive():
        process.kill()
        process.join(5)
        raise AssertionError("child did not reach the expected process-loss boundary")
    assert process.exitcode == -signal.SIGKILL


class TestProcessRecovery:
    """Each owner recovers from the adjacent durable boundary without a second ledger."""

    def test_history_open_survives_loss_before_pr_workflow_registration(self, tmp_path: Path) -> None:
        run_until_sigkill(workflow_open_child, tmp_path)

        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM pr_workflows").fetchone()[0] == 0
        assert history_length(tmp_path) == 22

        open_pr(tmp_path)

        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM pr_workflows").fetchone()[0] == 1
        assert history_length(tmp_path) == 22

    def test_inbox_commit_survives_loss_before_http_acknowledgement(self, tmp_path: Path) -> None:
        body = pull_request_body()

        run_until_sigkill(http_child, tmp_path, body)

        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute("SELECT raw_body, intake_outcome FROM webhook_inbox").fetchone() == (body, None)
        app = build_webhook_app(state_root=tmp_path, webhook_secret=WEBHOOK_SECRET)
        with TestClient(app) as client:
            recovered = client.post("/github/webhooks", content=body, headers=signed_http_headers(body))
        assert recovered.status_code == 200
        assert recovered.json()["disposition"] == "duplicate"
        assert recovered.json()["inbox_sequence"] == 1

    def test_history_acceptance_survives_loss_before_inbox_recorded(self, tmp_path: Path) -> None:
        open_pr(tmp_path)
        receive_body(tmp_path, pull_request_body())

        run_until_sigkill(history_acceptance_child, tmp_path)

        assert history_length(tmp_path) == 24
        with sqlite3.connect(tmp_path / "hamsterdan.sqlite3") as connection:
            assert connection.execute("SELECT intake_authorized, intake_outcome FROM webhook_inbox").fetchone() == (
                1,
                None,
            )
        recovered = build_webhook_inbox_worker(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=PolicyRevision("policy:changed-after-crash"),
        ).process_delivery(DELIVERY_ID)
        assert recovered.outcome == "recorded"
        assert recovered.occurrence == 1
        assert history_length(tmp_path) == 24

    def test_history_completion_survives_loss_before_caller_acknowledgement(self, tmp_path: Path) -> None:
        open_pr(tmp_path)
        receive_body(tmp_path, pull_request_body())
        worker = build_webhook_inbox_worker(
            state_root=tmp_path,
            provider_routes=(PROVIDER_ROUTE,),
            policy_revision=PolicyRevision("policy:process"),
        )
        assert worker.process_delivery(DELIVERY_ID).outcome == "recorded"

        run_until_sigkill(history_completion_child, tmp_path)

        assert history_length(tmp_path) == 26
        recovered = build_pull_request_authority(state_root=tmp_path).complete_next_observation(PR_IDENTITY)
        assert recovered.disposition == "already_completed"
        assert recovered.occurrence == 1
        assert history_length(tmp_path) == 26
