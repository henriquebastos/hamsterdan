from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import sys
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from petrus.engine import DriveOutcome
from petrus.impetus.history import ExternalEventDelivered
from petrus.motus.activity import ActivityError, ActivityInvocation, activity
from petrus.motus.dispatch import LocalDispatch
from petrus.motus.worker import Worker

from hamsterdan.agents.protocol import ReviewResult
from hamsterdan.contracts.readiness import AdmittedConversation, ConversationPublicationRequest, Intent
from hamsterdan.contracts.readiness_v5 import (
    ABlocked,
    AFault,
    ALanded,
    AMoved,
    AnnounceReq,
    DashBlocked,
    DashFault,
    DashLanded,
    DashReq,
    Replied,
    ReplyBlocked,
    ReplyFault,
    ReplyReq,
)
from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.models import RegistrationInventory, WireResponse
from hamsterdan.github_app.webhooks import Observation
from hamsterdan.host import __main__ as host_main
from hamsterdan.host.__main__ import inspect_instance
from hamsterdan.host.agenticus import AgentRouteStore, compose_agent
from hamsterdan.host.api import create_app
from hamsterdan.host.binding import ensure_instance_binding, read_instance_binding
from hamsterdan.host.service import HostService, QualificationFault
from hamsterdan.host.topology import PRODUCTION, V5, ReadinessComposition
from hamsterdan.host.v5.application import PrReadinessV5Application
from hamsterdan.readiness.net_v5.gating import VariantPayloadConverter


class Response:
    def __init__(self, value: object):
        self.value = value

    def json(self) -> object:
        return self.value


class Client:
    def __init__(self, responses: dict[str, object] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, path: str) -> Response:
        self.calls.append((method, path))
        return Response(self.responses.get(path, {}))


class Clients:
    def __init__(
        self,
        app: Client | None = None,
        inventory: Client | None = None,
        registration: RegistrationInventory | Exception | None = None,
    ):
        self.app = app or Client()
        self.inventory_client = inventory or Client()
        self.registration = registration
        self.operation_calls: list[tuple[int, tuple[int, ...]]] = []
        self.operation_client = Client()
        self.closed = 0

    def inventory(self, installation_id: int) -> Client:
        assert installation_id == 44
        return self.inventory_client

    def registration_inventory(self, config: HostConfig) -> RegistrationInventory:
        if isinstance(self.registration, Exception):
            raise self.registration
        if self.registration is None:
            raise AssertionError("registration inventory was not configured")
        return self.registration

    def installation(self, installation_id: int, repository_ids: list[int] | tuple[int, ...]) -> Client:
        self.operation_calls.append((installation_id, tuple(repository_ids)))
        return self.operation_client

    def close(self) -> None:
        self.closed += 1


class V5Provider:
    def __init__(self) -> None:
        self.head, self.base = "a" * 40, "b" * 40
        self.calls: list[tuple[str, str]] = []
        self.comments: list[dict[str, object]] = []

    def pages(self, path: str):
        self.calls.append(("PAGES", path))
        if path == "/repos/owner/one/issues/7/comments?per_page=100":
            return tuple(self.comments)
        return ()

    def request(self, method: str, path: str, body: object | None = None):
        self.calls.append((method, path))
        if method == "GET" and path == "/repos/owner/one/pulls/7":
            return WireResponse(
                200,
                {
                    "state": "open",
                    "draft": False,
                    "mergeable": True,
                    "mergeable_state": "clean",
                    "merged": False,
                    "html_url": "https://example.test/owner/one/pull/7",
                    "user": {"login": "author"},
                    "head": {"sha": self.head, "ref": "feature", "repo": {"full_name": "owner/one"}},
                    "base": {"sha": self.base, "ref": "main"},
                },
            )
        if method == "GET" and path == "/repos/owner/one/git/ref/heads/main":
            return WireResponse(200, {"object": {"sha": self.base}})
        if method == "GET" and path == "/repos/owner/one/rules/branches/main":
            return WireResponse(404, {})
        if method == "GET" and path == "/repos/owner/one/branches/main/protection":
            return WireResponse(404, {})
        if method == "GET" and path == "/repos/owner/one/pulls/7/requested_reviewers":
            return WireResponse(200, {"users": []})
        if method == "GET" and path.startswith("/repos/owner/one/actions/workflows/.github%2Fworkflows%2Fci.yml/runs?"):
            return WireResponse(200, {"total_count": 0, "workflow_runs": []})
        if method == "POST" and path == "/graphql":
            return WireResponse(
                200,
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                }
                            }
                        }
                    }
                },
            )
        if method == "POST" and path == "/repos/owner/one/issues/7/comments" and isinstance(body, dict):
            comment = {
                "id": len(self.comments) + 1,
                "html_url": f"https://example.test/comments/{len(self.comments) + 1}",
                "body": body.get("body", ""),
                "user": {"login": "hamsterdan-test[bot]"},
            }
            self.comments.append(comment)
            return WireResponse(201, comment)
        raise AssertionError(f"unexpected provider request: {method} {path} {body!r}")


class V5Runner:
    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        assert attempt == 1 and (is_current is None or is_current())
        return ReviewResult(
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            "clear",
            [],
            [],
        )


class Application:
    def __init__(self, *args: Any, fail: bool = False, **kwargs: Any):
        self.args, self.kwargs, self.fail = args, kwargs, fail
        self.reconciles: list[str] = []
        self.observations: list[Observation] = []
        self.durable_runs = 0
        self.comments: list[dict[str, object]] = []
        self.closed = 0

    def process_observation(
        self,
        observation: Observation,
        *,
        conversation: AdmittedConversation | None = None,
    ) -> None:
        self.settle()
        self.observations.append(observation)
        self.reconciles.append(f"github-delivery:{observation.delivery_id}")
        if self.fail:
            raise RuntimeError("provider secret must not escape")
        if conversation is not None:
            self.comments.append(conversation.__dict__)

    def reconcile(self, reason: str) -> None:
        self.reconciles.append(reason)
        if self.fail:
            raise RuntimeError("provider secret must not escape")

    def settle(self) -> None:
        return None

    def has_unresolved_publication(self) -> bool:
        return False

    def run_durable_activities(self, limit: int) -> int:
        self.durable_runs += 1
        return 0

    def stop_durable_activities(self) -> None:
        pass

    def close(self) -> None:
        self.closed += 1


def config(root: Path) -> HostConfig:
    return HostConfig(
        app_id=17,
        app_slug="hamsterdan-test",
        client_id="Iv1.client-secret-looking",
        account_id=23,
        account_login="Owner",
        allowed_repositories=frozenset({(31, "owner/one"), (32, "owner/two")}),
        state_path=root,
        private_key="private-key-secret",
        webhook_secret="hook-secret",
    )


def service(
    root: Path,
    *,
    clients: Clients | None = None,
    factory: Any = Application,
    readiness_composition: ReadinessComposition = PRODUCTION,
) -> HostService:
    agent_composition, routes = agent_custody(root)
    result = HostService(
        config(root),
        clients=clients or Clients(),
        runner=object(),
        agent_composition=agent_composition,
        agent_routes=routes,
        readiness_composition=replace(readiness_composition, application_factory=factory),
    )
    result.registry.reconcile(44, ((31, "owner/one"), (32, "owner/two")))
    return result


def agent_custody(root: Path):
    composition = compose_agent()
    routes = AgentRouteStore(root / "test-agent-routes.sqlite3")
    routes.activate(composition, root / "applications")
    return composition, routes


def bind_application(root: Path, repository: str = "owner/one") -> None:
    installation_id, repository_id, pull_request = (int(part) for part in root.parts[-3:])
    ensure_instance_binding(
        root,
        "production",
        f"github:{installation_id}:{repository_id}:pr:{pull_request}",
        repository,
        pull_request,
    )


def test_host_service_requires_agent_route_custody(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="agent_composition"):
        HostService(config(tmp_path), runner=object())  # type: ignore[call-arg, arg-type]


def test_unknown_startup_selector_stops_before_agent_or_provider_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    composed: list[str] = []
    monkeypatch.setattr(HostConfig, "from_environment", classmethod(lambda cls: config(tmp_path)))
    monkeypatch.setattr(host_main, "compose_agent", lambda environment: composed.append("agent"))
    monkeypatch.setattr(sys, "argv", ["hamsterdan.host", "serve"])
    monkeypatch.setenv("HAMSTERDAN_READINESS_TOPOLOGY", "V5")

    with pytest.raises(SystemExit) as raised:
        host_main.main()

    assert raised.value.code == 2
    assert composed == []


def test_agent_route_is_claimed_from_explicit_execution_identity_before_start(tmp_path: Path) -> None:
    events: list[str] = []

    class RoutedRunner:
        def review(self, *args: object, **kwargs: object) -> None:
            events.append(f"start:{kwargs['operation']}:{kwargs['attempt']}")

    class RecordingRoutes(AgentRouteStore):
        def claim(self, operation, composition):
            events.append(f"claim:{operation}")
            return super().claim(operation, composition)

    composition = compose_agent()
    routes = RecordingRoutes(tmp_path / "test-agent-routes.sqlite3")
    routes.activate(composition, tmp_path / "applications")
    runner = RoutedRunner()
    host = HostService(
        config(tmp_path),
        clients=Clients(),
        runner=runner,  # type: ignore[arg-type]
        agent_composition=composition,
        agent_routes=routes,
        readiness_composition=replace(PRODUCTION, application_factory=Application),
    )
    host.registry.reconcile(44, ((31, "owner/one"),))
    app = host._application(44, 31, 7)
    routed = app.args[3]

    routed.review("repository", object(), operation="review:one", attempt=1)
    routed.review("repository", object(), operation="review:one", attempt=2)

    assert events == [
        "claim:review:one",
        "start:review:one:1",
        "claim:review:one",
        "start:review:one:2",
    ]


def observation(delivery: str, repository: int = 31, pr: int = 7, **values: object) -> Observation:
    data: dict[str, object] = {
        "delivery_id": delivery,
        "event": "pull_request",
        "action": "synchronize",
        "installation_id": 44,
        "account_id": 23,
        "repository_id": repository,
        "repository_full_name": "owner/one" if repository == 31 else "owner/two",
        "pull_request_number": pr,
    }
    data.update(values)
    return Observation(**data)  # type: ignore[arg-type]


def signed(body: bytes, delivery: str, event: str = "pull_request") -> dict[str, str]:
    digest = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    return {
        "content-type": "application/json",
        "x-hub-signature-256": f"sha256={digest}",
        "x-github-delivery": delivery,
        "x-github-event": event,
    }


def envelope(repository: int = 31, pr: int = 7) -> bytes:
    return json.dumps(
        {
            "action": "synchronize",
            "installation": {"id": 44, "account": {"id": 23}},
            "repository": {"id": repository, "full_name": "owner/one"},
            "pull_request": {"number": pr},
        }
    ).encode()


def test_fastapi_accepts_durably_before_work_deduplicates_and_has_sanitized_health(tmp_path: Path) -> None:
    made: list[Application] = []

    def factory(*args: Any, **kwargs: Any) -> Application:
        made.append(Application(*args, **kwargs))
        return made[-1]

    host = service(tmp_path, factory=factory)
    delivery, body = str(uuid.uuid4()), envelope()
    with TestClient(create_app(host, reconcile_startup=False)) as client:
        # Let the initially empty worker reach its wait so the response witnesses custody, not application work.
        time.sleep(0.02)
        response = client.post("/github/webhooks", content=body, headers=signed(body, delivery))
        assert response.status_code == 202
        assert response.json() == {"custody": "durable", "delivery_id": delivery, "disposition": "accepted"}
        assert host.custody.status(delivery) == "pending" and made == []
        duplicate = client.post("/github/webhooks", content=body, headers=signed(body, delivery))
        assert duplicate.status_code == 202 and duplicate.json()["disposition"] == "duplicate"
        health = client.get("/healthz")
        assert health.status_code == 200
        encoded = health.text
        assert all(
            secret not in encoded for secret in ("hook-secret", "private-key-secret", "client-secret", "comment")
        )
        host.process(host.custody.pending()[0])
        assert len(made) == 1 and made[0].reconciles == [f"github-delivery:{delivery}"]


def test_fastapi_startup_reconciliation_failure_still_closes_owned_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clients = Clients()
    host = service(tmp_path, clients=clients)
    monkeypatch.setattr(
        host,
        "reconcile_registration",
        lambda: (_ for _ in ()).throw(RuntimeError("synthetic startup failure")),
    )

    with pytest.raises(RuntimeError, match="synthetic startup failure"), TestClient(create_app(host)):
        raise AssertionError("failed startup must not enter the application lifespan")
    assert clients.closed == 1


@pytest.mark.parametrize(
    ("body", "headers"),
    [
        (b"{}", {"content-type": "application/json"}),
        (b"not-json", None),
        (envelope(), {"content-type": "text/plain"}),
    ],
)
def test_fastapi_rejects_malformed_signature_body_or_header(
    tmp_path: Path, body: bytes, headers: dict[str, str] | None
) -> None:
    host = service(tmp_path)
    delivery = str(uuid.uuid4())
    actual = signed(body, delivery) if headers is None else signed(body, delivery) | headers
    if body == b"{}":
        actual.pop("x-hub-signature-256")
    with TestClient(create_app(host, reconcile_startup=False)) as client:
        assert client.post("/github/webhooks", content=body, headers=actual).status_code == 400


def test_application_identity_roots_and_operation_clients_are_exact(tmp_path: Path) -> None:
    made: list[Application] = []
    clients = Clients()

    def factory(*args: Any, **kwargs: Any) -> Application:
        made.append(Application(*args, **kwargs))
        return made[-1]

    host = service(tmp_path, clients=clients, factory=factory)
    for item in (observation("a"), observation("b"), observation("c", 32), observation("d", 31, 8)):
        host.process(item)
    assert len(made) == 3
    assert made[0].args[0] == tmp_path / "applications/44/31/7"
    assert made[0].args[1] == "github:44:31:pr:7"
    assert [call[1] for call in clients.operation_calls] == [(31,), (32,), (31,)]
    assert made[0].args[2].graphql is not None
    assert made[0].kwargs["publication_fault"] is None
    assert "agent_fault" not in made[0].kwargs
    host.close()
    assert all(app.closed == 1 for app in made) and clients.closed == 1


def test_application_protocol_receives_the_full_custodied_observation(tmp_path: Path) -> None:
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)) or made[-1])
    item = observation("full-observation", event="check_run", action="completed")

    host.process(item)

    assert made[0].observations == [item]
    assert made[0].reconciles == ["github-delivery:full-observation"]
    assert made[0].kwargs["custody_path"] == tmp_path / "webhooks.sqlite3"
    host.close()


def test_pump_prioritizes_pending_authority_custody_before_durable_activities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = service(tmp_path)
    events: list[str] = []
    monkeypatch.setattr(host, "project_pending", lambda: events.append("project") or 1)
    monkeypatch.setattr(host, "run_due", lambda: events.append("apply") or 1)
    monkeypatch.setattr(
        host.activity_worker,
        "run_available",
        lambda *, limit: events.append(f"activities:{limit}") or 0,
    )

    host.pump(limit=7)

    assert events == ["project", "apply", "activities:7"]
    host.close()


def test_pump_does_not_claim_application_queue_while_that_pr_has_pending_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = service(tmp_path)
    application = host._application(44, 31, 7)
    unrelated = host._application(44, 31, 8)
    identity, body = str(uuid.uuid4()), envelope()
    host.custody.receive(signed(body, identity).items() | {("content-length", str(len(body)))}, body)
    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        database.execute("UPDATE inbox SET next_attempt_at=9999999999 WHERE delivery_id=?", (identity,))
    monkeypatch.setattr(host.activity_worker, "run_available", lambda *, limit: 0)

    host.pump()
    assert application.durable_runs == 0
    assert unrelated.durable_runs == 1

    host.custody.acknowledge(identity)
    host.pump()
    assert application.durable_runs == 1
    assert unrelated.durable_runs == 2
    host.close()


def test_qualification_fault_is_exact_one_shot_and_disabled_by_default() -> None:
    assert QualificationFault.from_environment({}) is None
    raw = json.dumps(
        {
            "repository": "owner/one",
            "pull_request": 7,
            "boundary": "agent",
            "phase": "timed_out",
            "kind": "review",
            "operation": "next",
        }
    )
    fault = QualificationFault.from_environment({"HAMSTERDAN_QUALIFICATION_FAULT": raw})
    assert fault is not None

    with pytest.raises(Exception) as raised:
        fault.agent("OWNER/ONE", 7, "review", "review:one")
    assert getattr(raised.value, "timed_out", False)
    assert fault._spent_operation == "review:one"
    fault.agent("owner/one", 7, "review", "review:two")


@pytest.mark.parametrize(
    "change",
    [
        {"phase": "after_call"},
        {"boundary": "comment"},
        {"operation": ""},
        {"extra": True},
    ],
)
def test_qualification_fault_configuration_rejects_mismatched_shapes(change: dict[str, object]) -> None:
    value: dict[str, object] = {
        "repository": "owner/one",
        "pull_request": 7,
        "boundary": "agent",
        "phase": "timed_out",
        "kind": "review",
        "operation": "review:one",
    }
    value.update(change)
    with pytest.raises(ValueError, match="qualification fault configuration is malformed"):
        QualificationFault.from_environment({"HAMSTERDAN_QUALIFICATION_FAULT": json.dumps(value)})


def test_inactive_routes_and_non_actionable_comments_are_terminal_without_application(tmp_path: Path) -> None:
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)))
    cases = [
        observation("missing", repository=999),
        observation(
            "bot",
            event="issue_comment",
            action="created",
            comment_body="@hamsterdan-test explain the blockers",
            actor_login=host.config.bot_login,
        ),
        observation(
            "untrusted",
            event="issue_comment",
            action="created",
            comment_body="@hamsterdan-test explain the blockers",
            actor_login="x",
            actor_type="User",
            author_association="NONE",
        ),
        observation(
            "retired-slash-command",
            event="issue_comment",
            action="created",
            comment_body="/hamsterdan status",
            actor_login="x",
            actor_type="User",
            author_association="OWNER",
        ),
        observation(
            "mention-lookalike",
            event="issue_comment",
            action="created",
            comment_body="@hamsterdan explain the blockers",
            actor_login="x",
            actor_type="User",
            author_association="OWNER",
        ),
        observation(
            "unaddressed",
            event="issue_comment",
            action="created",
            comment_body="hello",
            actor_login="x",
            actor_type="User",
            author_association="OWNER",
        ),
    ]
    for item in cases:
        host.process(item)
    host.registry.installation("suspend", 44, 23)
    host.process(observation("suspended"))
    host.registry.installation("deleted", 44, 23)
    host.process(observation("removed"))
    assert made == []


def test_malformed_authenticated_comment_is_terminal_without_retry_loop_or_application(tmp_path: Path) -> None:
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)) or made[-1])
    delivery = str(uuid.uuid4())
    body = json.dumps(
        {
            "action": "created",
            "installation": {"id": 44, "account": {"id": 23}},
            "repository": {"id": 31, "full_name": "owner/one"},
            "issue": {"number": 7, "pull_request": {"url": "https://api.github.test/pulls/7"}},
            "comment": {
                "id": "9",
                "body": "@hamsterdan-test help",
                "author_association": "MEMBER",
                "user": {"id": 5, "login": "human", "type": "User"},
            },
        }
    ).encode()
    host.custody.receive(signed(body, delivery, "issue_comment").items() | {("content-length", str(len(body)))}, body)

    host.process(host.custody.pending()[0])

    assert host.custody.status(delivery) == "terminal"
    assert made == []
    host.close()


def test_addressed_trusted_human_comment_is_routed(tmp_path: Path) -> None:
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)) or made[-1])
    host.process(
        observation(
            "comment",
            event="issue_comment",
            action="created",
            comment_id=9,
            comment_body="@hamsterdan-test help",
            actor_id=5,
            actor_login="human",
            actor_type="User",
            author_association="MEMBER",
        )
    )
    assert len(made) == 1
    assert made[0].comments[0]["comment_id"] == 9
    assert made[0].comments[0]["text"] == "help"
    assert made[0].reconciles == ["github-delivery:comment"]


def test_delivery_remains_pending_when_post_activation_settlement_fails(tmp_path: Path) -> None:
    class SettlementFailure(Application):
        settlements = 0

        def settle(self) -> None:
            self.settlements += 1
            if self.settlements == 2:
                raise RuntimeError("settlement failed")

    host = service(tmp_path, factory=SettlementFailure)
    delivery, body = str(uuid.uuid4()), envelope()
    host.custody.receive(signed(body, delivery).items() | {("content-length", str(len(body)))}, body)

    host.process(host.custody.pending()[0])

    application = host._apps[(44, 31, 7)]
    assert application.reconciles == [f"github-delivery:{delivery}"]
    assert host.custody.status(delivery) == "pending"
    host.close()


def test_delivery_factory_failure_is_recorded_for_durable_retry(tmp_path: Path) -> None:
    def fail_factory(*args: object, **kwargs: object) -> Application:
        raise RuntimeError("application open failed")

    host = service(tmp_path, factory=fail_factory)
    delivery, body = str(uuid.uuid4()), envelope()
    host.custody.receive(signed(body, delivery).items() | {("content-length", str(len(body)))}, body)

    host.process(host.custody.pending()[0])

    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        attempts, next_attempt_at = database.execute(
            "SELECT attempts,next_attempt_at FROM inbox WHERE delivery_id=?", (delivery,)
        ).fetchone()
    assert attempts == 1
    assert next_attempt_at > 0
    assert host.custody.status(delivery) == "pending"
    host.close()


def test_delivery_is_acknowledged_only_after_runnable_posture_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = service(tmp_path)
    delivery, body = str(uuid.uuid4()), envelope()
    host.custody.receive(signed(body, delivery).items() | {("content-length", str(len(body)))}, body)
    observed_statuses: list[str | None] = []
    record = host._record_posture

    def observe_posture(instance: str, outcome: object | None) -> None:
        observed_statuses.append(host.custody.status(delivery))
        record(instance, outcome)

    monkeypatch.setattr(host, "_record_posture", observe_posture)

    host.process(host.custody.pending()[0])

    assert observed_statuses == ["pending"]
    assert host.custody.status(delivery) == "terminal"
    host.close()


def test_delivery_remains_pending_when_runnable_posture_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = service(tmp_path)
    delivery, body = str(uuid.uuid4()), envelope()
    host.custody.receive(signed(body, delivery).items() | {("content-length", str(len(body)))}, body)

    def fail_posture(instance: str, outcome: object | None) -> None:
        raise RuntimeError("posture failed")

    monkeypatch.setattr(host, "_record_posture", fail_posture)

    host.process(host.custody.pending()[0])

    assert host.custody.status(delivery) == "pending"
    host.close()


def test_retry_does_not_block_later_delivery_and_new_process_resumes_same_custody(tmp_path: Path) -> None:
    first_apps: list[Application] = []
    first = service(
        tmp_path, factory=lambda *a, **k: first_apps.append(Application(*a, fail=True, **k)) or first_apps[-1]
    )
    for delivery in (str(uuid.uuid4()), str(uuid.uuid4())):
        body = envelope(pr=7 if not first.custody.pending() else 8)
        first.custody.receive(signed(body, delivery).items() | {("content-length", str(len(body)))}, body)
    pending = first.custody.pending()
    first.process(pending[0])
    # A separate PR is still attempted despite the first delivery remaining pending.
    first.process(pending[1])
    assert first.custody.pending() == ()
    first.close()
    resumed_apps: list[Application] = []
    second = service(tmp_path, factory=lambda *a, **k: resumed_apps.append(Application(*a, **k)) or resumed_apps[-1])
    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        database.execute("UPDATE inbox SET next_attempt_at=0")
    for item in second.custody.pending():
        second.process(item)
    assert second.custody.pending() == () and len(resumed_apps) == 2
    second.close()


def test_same_subject_delivery_waits_behind_an_earlier_deferred_failure(tmp_path: Path) -> None:
    seen: list[str] = []

    class FailFirst(Application):
        def process_observation(self, observation, *, conversation=None):
            seen.append(observation.delivery_id)
            if len(seen) == 1:
                raise RuntimeError("first delivery failed")
            return super().process_observation(observation, conversation=conversation)

    host = service(tmp_path, factory=FailFirst)
    deliveries = [str(uuid.uuid4()), str(uuid.uuid4())]
    for identity in deliveries:
        body = envelope(pr=7)
        host.custody.receive(signed(body, identity).items() | {("content-length", str(len(body)))}, body)

    with pytest.raises(RuntimeError, match="first delivery failed"):
        host._activate_instance("github:44:31:pr:7")

    # Even an explicitly supplied later observation must respect the
    # custodied row-order fence rather than bypassing subject loading.
    host.process(host.custody.pending()[0])

    assert seen == [deliveries[0]]
    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        rows = database.execute(
            "SELECT delivery_id,attempts FROM inbox WHERE delivery_id IN (?,?) ORDER BY rowid",
            deliveries,
        ).fetchall()
    assert rows == [(deliveries[0], 1), (deliveries[1], 0)]
    assert host.custody.pending(subject=(44, 31, 7)) == ()
    host.close()


def test_periodic_sweep_reopens_active_and_inactive_bound_instances(tmp_path: Path) -> None:
    for repository, pr in ((31, 7), (31, 8), (999, 9)):
        root = tmp_path / "applications" / "44" / str(repository) / str(pr)
        bind_application(root, "owner/inactive" if repository == 999 else "owner/one")
        (root / "history.jsonl").write_text("", encoding="utf-8")
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)) or made[-1])

    assert host.sweep("startup") == 3
    assert [item.args[1] for item in made] == [
        "github:44:31:pr:7",
        "github:44:31:pr:8",
        "github:44:999:pr:9",
    ]
    assert [item.reconciles for item in made] == [["startup:44:31:7"], ["startup:44:31:8"], []]
    assert host.sweep() == 3
    assert [item.reconciles for item in made] == [
        ["startup:44:31:7", "periodic:44:31:7"],
        ["startup:44:31:8", "periodic:44:31:8"],
        [],
    ]


def test_startup_sweep_applies_pending_comment_without_duplicate_provider_reconciliation(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    bind_application(root)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)) or made[-1])
    delivery = str(uuid.uuid4())
    body = json.dumps(
        {
            "action": "created",
            "installation": {"id": 44, "account": {"id": 23}},
            "repository": {"id": 31, "full_name": "owner/one"},
            "issue": {"number": 7, "pull_request": {"url": "https://api.github.test/pulls/7"}},
            "comment": {
                "id": 9,
                "body": "@hamsterdan-test help",
                "author_association": "MEMBER",
                "user": {"id": 5, "login": "human", "type": "User"},
            },
        }
    ).encode()
    host.custody.receive(signed(body, delivery, "issue_comment").items() | {("content-length", str(len(body)))}, body)

    assert host.sweep("startup") == 1
    assert len(made) == 1
    assert made[0].reconciles == [f"github-delivery:{delivery}"]
    assert len(made[0].comments) == 1
    assert host.custody.status(delivery) == "terminal"
    host.close()


def test_startup_sweep_finds_instance_comment_beyond_global_pending_batch(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    bind_application(root)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)) or made[-1])
    unrelated = [
        (
            str(uuid.uuid4()),
            "pull_request",
            json.dumps(observation(str(uuid.uuid4()), repository=32, pr=8).__dict__, separators=(",", ":")),
        )
        for _ in range(1000)
    ]
    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        database.executemany(
            "INSERT INTO inbox(delivery_id,event,observation,status) VALUES(?,?,?,'pending')", unrelated
        )
    delivery = str(uuid.uuid4())
    body = json.dumps(
        {
            "action": "created",
            "installation": {"id": 44, "account": {"id": 23}},
            "repository": {"id": 31, "full_name": "owner/one"},
            "issue": {"number": 7, "pull_request": {"url": "https://api.github.test/pulls/7"}},
            "comment": {
                "id": 9,
                "body": "@hamsterdan-test help",
                "author_association": "MEMBER",
                "user": {"id": 5, "login": "human", "type": "User"},
            },
        }
    ).encode()
    host.custody.receive(signed(body, delivery, "issue_comment").items() | {("content-length", str(len(body)))}, body)

    assert host.sweep("startup") == 1
    assert made[0].reconciles == [f"github-delivery:{delivery}"]
    assert len(made[0].comments) == 1
    assert host.custody.status(delivery) == "terminal"
    host.close()


def test_sweep_does_not_reconcile_while_addressed_comment_retry_is_deferred(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    bind_application(root)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)) or made[-1])
    delivery = str(uuid.uuid4())
    item = observation(
        delivery,
        event="issue_comment",
        action="created",
        comment_body="@hamsterdan-test help",
        actor_login="human",
        actor_type="User",
        author_association="MEMBER",
    )
    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        database.execute(
            "INSERT INTO inbox(delivery_id,event,observation,status) VALUES(?,?,?,'pending')",
            (delivery, item.event, json.dumps(item.__dict__, separators=(",", ":"))),
        )
    host.custody.retry(delivery, RuntimeError("deferred"))

    assert host.sweep("startup") == 1
    assert len(made) == 1
    assert made[0].reconciles == []
    assert made[0].comments == []
    assert host.custody.status(delivery) == "pending"
    host.close()


def test_sweep_waits_for_actionable_comment_beyond_same_instance_batch(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    bind_application(root)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)) or made[-1])
    items = []
    for _ in range(1000):
        delivery = str(uuid.uuid4())
        item = observation(
            delivery,
            event="issue_comment",
            action="created",
            comment_body="not addressed",
            actor_login="human",
            actor_type="User",
            author_association="MEMBER",
        )
        items.append((delivery, item.event, json.dumps(item.__dict__, separators=(",", ":"))))
    target_delivery = str(uuid.uuid4())
    target = observation(
        target_delivery,
        event="issue_comment",
        action="created",
        comment_body="@hamsterdan-test help",
        actor_login="human",
        actor_type="User",
        author_association="MEMBER",
    )
    items.append((target_delivery, target.event, json.dumps(target.__dict__, separators=(",", ":"))))
    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        database.executemany("INSERT INTO inbox(delivery_id,event,observation,status) VALUES(?,?,?,'pending')", items)

    assert host.sweep("startup") == 1
    assert made[0].reconciles == []
    assert host.custody.status(target_delivery) == "pending"
    assert host.sweep("periodic") == 1
    assert made[0].reconciles == [f"github-delivery:{target_delivery}"]
    assert len(made[0].comments) == 1
    assert host.custody.status(target_delivery) == "terminal"
    host.close()


def test_scoped_resolver_reconstructs_persisted_application_and_rejects_non_publication_names(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    bind_application(root)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    calls: list[str] = []

    class ResolvableApplication(Application):
        def activity(self, name: str):
            calls.append(name)
            return lambda invocation, *, context: {"activity": name}

    host = service(tmp_path, factory=ResolvableApplication)

    resolved = host._resolve_activity("github:44:31:pr:7", "dashboard_publish")

    assert resolved is not None
    assert (44, 31, 7) in host._apps
    assert calls == ["dashboard_publish"]
    assert host._resolve_activity("github:44:31:pr:7", "review") is None
    assert host._resolve_activity("not-a-pr-instance", "dashboard_publish") is not None
    host.close()


def test_v5_revoked_route_settles_instance_queue_as_typed_blocked_without_provider_calls(tmp_path: Path) -> None:
    provider_calls: list[str] = []

    @activity(name="reply_gate", converter=VariantPayloadConverter())
    def reply(work: ReplyReq) -> Replied | ReplyBlocked | ReplyFault:
        provider_calls.append(f"reply:{work.id}")
        raise AssertionError("revoked reply reached provider")

    @activity(name="dash_gate", converter=VariantPayloadConverter())
    def dash(work: DashReq) -> DashLanded | DashBlocked | DashFault:
        provider_calls.append(f"dash:{work.digest}")
        raise AssertionError("revoked dashboard reached provider")

    @activity(name="announce_gate", converter=VariantPayloadConverter())
    def announce(work: AnnounceReq) -> ALanded | AMoved | ABlocked | AFault:
        provider_calls.append(f"announce:{work.op}")
        raise AssertionError("revoked announcement reached provider")

    definitions = {item.declaration.name: item for item in (reply, dash, announce)}
    works = {
        "reply_gate": ReplyReq(id="comment-7", text="safe reply"),
        "dash_gate": DashReq(entries=["one"], digest="d1", desired_entries=["one", "two"], desired_digest="d2"),
        "announce_gate": AnnounceReq(op="ready:h1:i3", incarnation=3, head="h1", base="b1", policy="p1"),
    }
    blocked = {
        "reply_gate": ReplyBlocked(id="comment-7", text="safe reply"),
        "dash_gate": DashBlocked(entries=["one"], digest="d1", desired_entries=["one", "two"], desired_digest="d2"),
        "announce_gate": ABlocked(incarnation=3, head="h1", base="b1", policy="p1"),
    }
    host = service(tmp_path, readiness_composition=V5)
    application = host._application(44, 31, 7)
    assert host.readiness_composition.topology == "v5"
    assert host.activity_worker is None
    assert application.kwargs["durable_activity_resolver"].__self__ is host

    instance = "github:44:31:pr:7"
    queue = f"v5-publication:{instance}"
    dispatch_path = tmp_path / "activity-dispatch.sqlite3"
    sender = LocalDispatch(
        dispatch_path,
        instance=instance,
        activity_queues={name: queue for name in definitions},
    )
    for occurrence, (name, work) in enumerate(works.items(), start=1):
        sender.dispatch(occurrence, ActivityInvocation(name, input={"work": work.dump()}))
    production = LocalDispatch(dispatch_path, instance="production-inspector").worker(("publication",))
    assert production.claim() is None
    production.close()
    host.registry.installation("suspend", 44, 23)
    worker = Worker(
        LocalDispatch(dispatch_path, instance="v5-worker").worker((queue,)),
        definitions,
        resolver=lambda attempt_instance, name: host._guard_durable_activity(attempt_instance, name, definitions[name]),
    )

    assert worker.run_available(limit=10) == 3
    results = dict(sender.collect())

    assert provider_calls == []
    for occurrence, name in enumerate(works, start=1):
        definition = definitions[name]
        assert results[occurrence] == definition.converter.encode(blocked[name], definition.result)
        assert results[occurrence]["$variant"].endswith("Blocked")
    worker.close()
    host.close()


def test_v5_shutdown_during_first_attempt_prevents_a_second_instance_queue_claim(tmp_path: Path) -> None:
    started, release = threading.Event(), threading.Event()

    class StoppableApplication(Application):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)
            self.claims = 0
            self.stopped = False

        def run_durable_activities(self, limit: int) -> int:
            assert limit >= 2
            self.claims += 1
            started.set()
            assert release.wait(1)
            if not self.stopped:
                self.claims += 1
            return self.claims

        def stop_durable_activities(self) -> None:
            self.stopped = True

    host = service(tmp_path, factory=StoppableApplication, readiness_composition=V5)
    application = host._application(44, 31, 7)
    pumping = threading.Thread(target=host.pump)
    pumping.start()
    assert started.wait(1)

    host.stop()
    release.set()
    pumping.join(1)

    assert not pumping.is_alive()
    assert application.claims == 1
    host.close()


def test_explicit_v5_composition_opens_the_real_v5_application_and_labeled_history(tmp_path: Path) -> None:
    host = service(tmp_path, factory=PrReadinessV5Application, readiness_composition=V5)

    application = host._application(44, 31, 7)

    assert isinstance(application, PrReadinessV5Application)
    assert host.activity_worker is None
    binding = read_instance_binding(tmp_path / "applications/44/31/7/binding.json")
    assert binding.topology == "v5" and not binding.legacy
    assert (tmp_path / "applications/44/31/7/history.jsonl").is_file()
    host.close()


def test_selected_v5_routes_custodied_webhook_into_identified_history_before_acknowledgement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = V5Provider()
    monkeypatch.setattr("hamsterdan.host.service.GitHubKitTransport", lambda client: provider)
    composition, routes = agent_custody(tmp_path)
    host = HostService(
        config(tmp_path),
        clients=Clients(),
        runner=V5Runner(),  # type: ignore[arg-type]
        agent_composition=composition,
        agent_routes=routes,
        readiness_composition=V5,
    )
    host.registry.reconcile(44, ((31, "owner/one"),))
    delivery, body = str(uuid.uuid4()), envelope()
    receipt = host.custody.receive(
        signed(body, delivery).items() | {("content-length", str(len(body)))},
        body,
    )
    assert receipt.disposition == "accepted" and host.custody.status(delivery) == "pending"
    acknowledged_after: list[tuple[str, ...]] = []
    acknowledge = host.custody.acknowledge

    def observe_acknowledgement(identity: str, reason: str | None = None) -> None:
        application = host._apps[(44, 31, 7)]
        accepted = tuple(
            record.identity
            for record in application._runtime().engine.records
            if isinstance(record, ExternalEventDelivered)
        )
        acknowledged_after.append(accepted)
        acknowledge(identity, reason)

    monkeypatch.setattr(host.custody, "acknowledge", observe_acknowledgement)

    host.process(host.custody.pending()[0])

    application = host._apps[(44, 31, 7)]
    assert isinstance(application, PrReadinessV5Application)
    expected = tuple(f"github-delivery:{delivery}:{door}" for door in ("on_head", "on_ready", "on_human"))
    assert len(acknowledged_after) == 1 and acknowledged_after[0][:3] == expected
    assert any(identity.startswith("v5-timer-command-applied:") for identity in acknowledged_after[0])
    assert host.custody.status(delivery) == "terminal"
    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        assert database.execute(
            "SELECT revision,source_kind,source_id FROM v5_authority_grants WHERE subject='github:44:31:pr:7'"
        ).fetchone() == (1, "github-delivery", delivery)
    host.close()


def test_selected_v5_sweep_reconciliation_reuses_unchanged_identity_and_advances_changed_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = V5Provider()
    monkeypatch.setattr("hamsterdan.host.service.GitHubKitTransport", lambda client: provider)
    composition, routes = agent_custody(tmp_path)
    host = HostService(
        config(tmp_path),
        clients=Clients(),
        runner=V5Runner(),  # type: ignore[arg-type]
        agent_composition=composition,
        agent_routes=routes,
        readiness_composition=V5,
    )
    host.registry.reconcile(44, ((31, "owner/one"),))
    application = host._application(44, 31, 7)

    assert host.sweep("startup") == 1
    startup = tuple(
        record.identity
        for record in application._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and record.identity.startswith("host-reconcile:")
    )
    assert len(startup) == 3 and all(":github:44:31:pr:7:1:" in identity for identity in startup)

    assert host.sweep("periodic") == 1
    unchanged = tuple(
        record.identity
        for record in application._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and record.identity.startswith("host-reconcile:")
    )
    assert unchanged == startup

    provider.head = "c" * 40
    assert host.sweep("periodic") == 1
    changed = tuple(
        record.identity
        for record in application._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and record.identity.startswith("host-reconcile:")
    )
    assert changed[:3] == startup
    assert len(changed) == 6 and all(":github:44:31:pr:7:2:" in identity for identity in changed[3:])
    host.close()

    composition, routes = agent_custody(tmp_path)
    restarted = HostService(
        config(tmp_path),
        clients=Clients(),
        runner=V5Runner(),  # type: ignore[arg-type]
        agent_composition=composition,
        agent_routes=routes,
        readiness_composition=V5,
    )
    restarted.registry.reconcile(44, ((31, "owner/one"),))
    assert restarted.sweep("startup") == 1
    reopened = restarted._apps[(44, 31, 7)]
    after_restart = tuple(
        record.identity
        for record in reopened._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and record.identity.startswith("host-reconcile:")
    )
    assert after_restart == changed
    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        assert database.execute(
            "SELECT revision,source_kind FROM v5_authority_grants WHERE subject='github:44:31:pr:7'"
        ).fetchone() == (2, "host-reconcile")
    restarted.close()


def test_selected_v5_restart_rebuilds_timer_after_crash_before_runnable_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SimulatedProcessDeath(BaseException):
        pass

    provider = V5Provider()
    monkeypatch.setattr("hamsterdan.host.service.GitHubKitTransport", lambda client: provider)
    clock_us = [1_000_000]
    monkeypatch.setattr("hamsterdan.host.v5.timers.time.time_ns", lambda: clock_us[0] * 1_000)
    composition, routes = agent_custody(tmp_path)
    first = HostService(
        config(tmp_path),
        clients=Clients(),
        runner=V5Runner(),  # type: ignore[arg-type]
        agent_composition=composition,
        agent_routes=routes,
        readiness_composition=V5,
        reminder_delay=10,
    )
    first.runnable._clock = lambda: clock_us[0] / 1_000_000
    first.registry.reconcile(44, ((31, "owner/one"),))
    first._application(44, 31, 7)
    assert first.sweep("startup") == 1
    assert first.runnable.count() == 1

    def die_before_runnable_hint(instance: str, settled: DriveOutcome) -> None:
        assert instance == "github:44:31:pr:7"
        assert settled.next_maturation == 21.0
        raise SimulatedProcessDeath

    clock_us[0] = 11_000_000
    record_posture = first._record_posture
    monkeypatch.setattr(first, "_record_posture", die_before_runnable_hint)
    with pytest.raises(SimulatedProcessDeath):
        first.run_due()

    history = tmp_path / "applications" / "44" / "31" / "7" / "history.jsonl"
    assert len(provider.comments) == 1
    assert (
        sum(
            value.get("record") == "ExternalEventDelivered" and value.get("source") == "on_timer"
            for value in map(json.loads, history.read_text().splitlines())
        )
        == 1
    )
    monkeypatch.setattr(first, "_record_posture", record_posture)
    first.close()

    application_root = tmp_path / "applications" / "44" / "31" / "7"
    for path in (application_root / "timers.sqlite3", tmp_path / "runnable.sqlite3"):
        path.unlink()
        path.with_name(path.name + "-wal").unlink(missing_ok=True)
        path.with_name(path.name + "-shm").unlink(missing_ok=True)

    composition, routes = agent_custody(tmp_path)
    second = HostService(
        config(tmp_path),
        clients=Clients(),
        runner=V5Runner(),  # type: ignore[arg-type]
        agent_composition=composition,
        agent_routes=routes,
        readiness_composition=V5,
        reminder_delay=10,
    )
    second.runnable._clock = lambda: clock_us[0] / 1_000_000
    second.registry.reconcile(44, ((31, "owner/one"),))
    try:
        assert second.sweep("startup") == 1
        assert second.runnable.count() == 1
        assert second.run_due() == 0
        assert len(provider.comments) == 1

        clock_us[0] = 21_000_000
        assert second.run_due() == 1
        assert len(provider.comments) == 2
        assert (
            sum(
                value.get("record") == "ExternalEventDelivered" and value.get("source") == "on_timer"
                for value in map(json.loads, history.read_text().splitlines())
            )
            == 2
        )
    finally:
        second.close()


def test_host_skips_post_reconciliation_settlement_when_application_reports_a_custody_fence(tmp_path: Path) -> None:
    class FencedApplication(Application):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)
            self.settlements = 0

        def settle(self) -> None:
            self.settlements += 1

        def reconcile(self, reason: str) -> bool:
            self.reconciles.append(reason)
            return False

    host = service(tmp_path, factory=FencedApplication, readiness_composition=V5)

    assert host._activate_instance("github:44:31:pr:7", reconcile_trigger="startup")

    application = host._apps[(44, 31, 7)]
    assert application.reconciles == ["startup:44:31:7"]
    assert application.settlements == 1
    host.close()


def test_host_rechecks_custody_and_route_before_post_reconciliation_settlement(tmp_path: Path) -> None:
    host: HostService

    class CustodyRaceApplication(Application):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)
            self.settlements = 0

        def settle(self) -> None:
            self.settlements += 1

        def reconcile(self, reason: str) -> bool:
            self.reconciles.append(reason)
            pending = observation(str(uuid.uuid4()))
            with sqlite3.connect(self.kwargs["custody_path"]) as database:
                database.execute(
                    "INSERT INTO inbox(delivery_id,event,observation,status) VALUES(?,?,?,'pending')",
                    (pending.delivery_id, pending.event, json.dumps(pending.__dict__, separators=(",", ":"))),
                )
            return True

    host = service(tmp_path, factory=CustodyRaceApplication, readiness_composition=V5)
    assert host._activate_instance("github:44:31:pr:7", reconcile_trigger="startup")
    application = host._apps[(44, 31, 7)]
    assert application.settlements == 1
    host.close()

    class RouteRaceApplication(CustodyRaceApplication):
        def reconcile(self, reason: str) -> None:
            self.reconciles.append(reason)
            host.registry.installation("suspend", 44, 23)

    host = service(tmp_path / "route", factory=RouteRaceApplication, readiness_composition=V5)
    assert host._activate_instance("github:44:31:pr:7", reconcile_trigger="startup")
    application = host._apps[(44, 31, 7)]
    assert application.settlements == 1
    host.close()


def test_scoped_resolver_wraps_unexpected_publication_error_as_nonretryable(tmp_path: Path) -> None:
    class BrokenApplication(Application):
        def activity(self, name: str):
            def fail(invocation, *, context):
                raise ValueError("provider detail must not escape")

            return fail

    host = service(tmp_path, factory=BrokenApplication)
    host._application(44, 31, 7)
    resolved = host._resolve_activity("github:44:31:pr:7", "readiness_publish")

    assert resolved is not None
    with pytest.raises(ActivityError) as raised:
        resolved(object(), context=object())
    assert raised.value.failure.kind == "ValueError"
    assert not raised.value.failure.retryable
    assert "provider detail" not in str(raised.value)
    host.close()


def test_publication_resolver_fails_closed_for_malformed_scope_and_request(tmp_path: Path) -> None:
    class ApplicationWithoutActivity(Application):
        pass

    host = service(tmp_path, factory=ApplicationWithoutActivity)
    malformed_scope = host._resolve_activity("not-a-pr-instance", "dashboard_publish")
    assert malformed_scope is not None
    with pytest.raises(ActivityError) as scope_error:
        malformed_scope(ActivityInvocation("dashboard_publish", input={}), context=object())
    assert scope_error.value.failure.kind == "PublicationScopeError"
    assert not scope_error.value.failure.retryable
    assert host._resolve_activity("not-a-pr-instance", "review") is None

    host._application(44, 31, 7)
    host.registry.installation("suspend", 44, 23)
    resolved = host._resolve_activity("github:44:31:pr:7", "dashboard_publish")
    assert resolved is not None
    with pytest.raises(ActivityError) as request_error:
        resolved(ActivityInvocation("dashboard_publish", input={}), context=object())
    assert request_error.value.failure.kind == "PublicationScopeError"
    assert not request_error.value.failure.retryable
    host.close()


def test_revoked_production_publication_preserves_malformed_scope_classification(tmp_path: Path) -> None:
    class ResolvableApplication(Application):
        def activity(self, name: str):
            return lambda invocation, *, context: {"ok": True}

    host = service(tmp_path, factory=ResolvableApplication)
    host._application(44, 31, 7)
    resolved = host._resolve_activity("github:44:31:pr:7", "dashboard_publish")
    assert resolved is not None
    host.registry.installation("suspend", 44, 23)

    with pytest.raises(ActivityError) as raised:
        resolved(ActivityInvocation("dashboard_publish", input={}), context=object())

    assert raised.value.failure.kind == "PublicationScopeError"
    assert not raised.value.failure.retryable
    host.close()


def test_cached_application_revalidates_route_and_returns_typed_stale_publication(tmp_path: Path) -> None:
    provider_calls: list[str] = []

    class ResolvableApplication(Application):
        def activity(self, name: str):
            def publish(invocation, *, context):
                provider_calls.append(name)
                return {"ok": True}

            return publish

    host = service(tmp_path, factory=ResolvableApplication)
    host._application(44, 31, 7)
    resolved = host._resolve_activity("github:44:31:pr:7", "dashboard_publish")
    assert resolved is not None
    host.registry.installation("suspend", 44, 23)
    request = {
        "epoch": 1,
        "head": "a" * 40,
        "operation": "dashboard:one",
        "base_head": "b" * 40,
        "policy_digest": "policy",
        "control": {
            "repository_id": "owner/one",
            "pr_number": 7,
            "epoch": 1,
            "head": "a" * 40,
            "base_head": "b" * 40,
            "strict_base": True,
            "base_current": True,
            "policy_digest": "policy",
        },
    }

    result = resolved(ActivityInvocation("dashboard_publish", input={"work": request}), context=object())

    assert result == {
        "epoch": 1,
        "head": "a" * 40,
        "ok": False,
        "operation": "dashboard:one",
        "capability_available": True,
        "faulted": False,
    }
    assert provider_calls == []
    host.close()


def test_inactive_route_returns_exact_typed_stale_conversation_publication(tmp_path: Path) -> None:
    provider_calls: list[str] = []

    class ResolvableApplication(Application):
        def activity(self, name: str):
            def publish(invocation, *, context):
                provider_calls.append(name)
                return {"ok": True}

            return publish

    host = service(tmp_path, factory=ResolvableApplication)
    host._application(44, 31, 7)
    resolved = host._resolve_activity("github:44:31:pr:7", "conversation_publish")
    assert resolved is not None
    host.registry.installation("suspend", 44, 23)
    request = ConversationPublicationRequest(
        2,
        "a" * 40,
        "conversation:stale",
        "b" * 40,
        "policy",
        Intent(
            2,
            "a" * 40,
            "reply",
            "reply-digest",
            True,
            False,
            {"message": "Safe reply"},
            "b" * 40,
            "policy",
        ),
    )

    result = resolved(ActivityInvocation("conversation_publish", input={"work": request.dump()}), context=object())

    assert result == {
        "epoch": 2,
        "head": "a" * 40,
        "ok": False,
        "operation": "conversation:stale",
        "capability_available": True,
        "faulted": False,
    }
    assert provider_calls == []
    host.close()


def test_restart_reconstructs_revoked_route_and_settles_exact_stale_publication(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    root.mkdir(parents=True)
    (root / "binding.json").write_text(
        json.dumps({"instance_id": "github:44:31:pr:7", "repository": "owner/one", "pull_request": 7})
    )
    (root / "history.jsonl").write_text("", encoding="utf-8")
    provider_calls: list[str] = []
    settlements: list[str] = []

    class RestartedApplication(Application):
        def activity(self, name: str):
            def publish(invocation, *, context):
                provider_calls.append(name)
                return {"ok": True}

            return publish

        def settle(self) -> None:
            settlements.append("settled")

    host = service(tmp_path, factory=RestartedApplication)
    host.registry.installation("suspend", 44, 23)
    resolved = host._resolve_activity("github:44:31:pr:7", "dashboard_publish")
    assert resolved is not None
    request = {
        "epoch": 3,
        "head": "a" * 40,
        "operation": "dashboard:restart",
        "base_head": "b" * 40,
        "policy_digest": "policy",
        "control": {
            "repository_id": "owner/one",
            "pr_number": 7,
            "epoch": 3,
            "head": "a" * 40,
            "base_head": "b" * 40,
            "strict_base": True,
            "base_current": True,
            "policy_digest": "policy",
        },
    }

    result = resolved(ActivityInvocation("dashboard_publish", input={"work": request}), context=object())

    assert result == {
        "epoch": 3,
        "head": "a" * 40,
        "ok": False,
        "operation": "dashboard:restart",
        "capability_available": True,
        "faulted": False,
    }
    assert provider_calls == []
    assert host.run_due() == 1
    assert settlements == ["settled"]
    host.close()


@pytest.mark.parametrize("pull_request", [True, 7.0])
def test_startup_preflight_rejects_noninteger_pull_request_binding(tmp_path: Path, pull_request: object) -> None:
    root = tmp_path / "applications/44/31/7"
    root.mkdir(parents=True)
    (root / "binding.json").write_text(
        json.dumps({"instance_id": "github:44:31:pr:7", "repository": "owner/one", "pull_request": pull_request})
    )
    (root / "history.jsonl").write_text("", encoding="utf-8")
    clients = Clients()
    composition, routes = agent_custody(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="binding is unreadable or malformed"):
            HostService(
                config(tmp_path),
                clients=clients,
                runner=object(),
                agent_composition=composition,
                agent_routes=routes,
            )
    finally:
        routes.close()
    assert clients.operation_calls == []


def test_run_due_contains_instance_failure_rewakes_and_recovers_scheduler_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = service(tmp_path)
    first = "github:44:31:pr:7"
    second = "github:44:32:pr:8"
    attempts: dict[str, int] = {}

    def run(instance: str, *, reconcile_trigger=None) -> bool:
        attempts[instance] = attempts.get(instance, 0) + 1
        if instance == first and attempts[instance] == 1:
            raise RuntimeError("sensitive scheduler failure")
        return True

    monkeypatch.setattr(host, "_activate_instance", run)
    host.runnable.wake(first, 0, "petri-timer", "next-maturation")
    host.runnable.wake(second, 0, "webhook", "delivery")

    assert host.run_due() == 1
    assert attempts == {first: 1, second: 1}
    assert host.runnable.take_due(now=time.time()) == (first,)
    health = host.health()
    assert health["status"] == "degraded"
    assert health["scheduler"] == {"degraded_instances": 1, "error_classes": ["RuntimeError"]}
    assert "sensitive scheduler failure" not in json.dumps(health)

    host.runnable.wake(first, 0, "scheduler-repair", "run-due-failure")
    assert host.run_due() == 1
    assert attempts[first] == 2
    assert host.health()["status"] == "ok"
    host.close()


def test_worker_failure_remains_primary_and_lifespan_closes_resources_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clients = Clients()
    host = service(tmp_path, clients=clients)
    app = host._application(44, 31, 7)

    async def fail_worker() -> None:
        raise RuntimeError("worker failed")

    monkeypatch.setattr(host, "worker", fail_worker)
    with pytest.raises(RuntimeError, match="worker failed"), TestClient(create_app(host, reconcile_startup=False)):
        time.sleep(0.02)

    assert clients.closed == 1
    assert app.closed == 1


def test_startup_sweep_settles_frozen_terminal_before_provider_reconciliation(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    bind_application(root)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    events: list[str] = []

    class FrozenApplication(Application):
        published = False

        def settle(self) -> None:
            events.append("settle")
            self.published = True

        def reconcile(self, reason: str) -> None:
            events.append(f"reconcile:{self.published}")
            if not self.published:
                events.append("duplicate-publication")

    host = service(tmp_path, factory=FrozenApplication)

    assert host.sweep("startup") == 1
    assert events == ["settle", "reconcile:True", "settle"]
    assert "duplicate-publication" not in events
    host.close()


def test_sweep_route_deactivation_during_pre_settlement_skips_reconciliation_and_second_settle(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    bind_application(root)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    host = service(tmp_path)
    application = host._application(44, 31, 7)
    settlements: list[str] = []

    def deactivate() -> None:
        settlements.append("settle")
        host.registry.installation("suspend", 44, 23)

    application.settle = deactivate  # type: ignore[method-assign]

    assert host.sweep("periodic") == 1
    assert settlements == ["settle"]
    host.close()


def test_activity_terminal_wake_only_settles_once_without_provider_reconciliation(tmp_path: Path) -> None:
    events: list[str] = []

    class TerminalApplication(Application):
        def settle(self) -> None:
            events.append("settle")

    host = service(tmp_path, factory=TerminalApplication)
    host._application(44, 31, 7)
    instance = "github:44:31:pr:7"
    host.runnable.wake(instance, 0, "activity-terminal", "dashboard_publish")

    assert host.run_due() == 1
    assert events == ["settle"]
    assert host._apps[(44, 31, 7)].reconciles == []
    host.close()


def test_due_wake_reconstructs_uncached_persisted_instance_and_settles_once(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    bind_application(root)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    events: list[str] = []

    class TerminalApplication(Application):
        def settle(self) -> None:
            events.append("settle")

    host = service(tmp_path, factory=TerminalApplication)
    instance = "github:44:31:pr:7"
    host.runnable.wake(instance, 0, "petri-timer", "next-maturation")

    assert host.run_due() == 1
    assert (44, 31, 7) in host._apps
    assert events == ["settle"]
    host.close()


def test_due_wake_reconstructs_inactive_bound_instance_to_settle_terminal(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    root.mkdir(parents=True)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    (root / "binding.json").write_text(
        json.dumps(
            {"instance_id": "github:44:31:pr:7", "repository": "owner/one", "pull_request": 7},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    events: list[str] = []

    class TerminalApplication(Application):
        def settle(self) -> None:
            events.append("settle")

    host = service(tmp_path, factory=TerminalApplication)
    host.registry.installation("suspend", 44, 23)
    instance = "github:44:31:pr:7"
    host.runnable.wake(instance, 0, "activity-terminal", "dashboard_publish")

    assert host.run_due() == 1
    assert (44, 31, 7) in host._apps
    assert events == ["settle"]
    assert host._apps[(44, 31, 7)].reconciles == []
    host.close()


def test_startup_sweep_repairs_inactive_bound_instance_without_runnable_hint(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    root.mkdir(parents=True)
    (root / "history.jsonl").write_text("", encoding="utf-8")
    (root / "binding.json").write_text(
        json.dumps(
            {"instance_id": "github:44:31:pr:7", "repository": "owner/one", "pull_request": 7},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    events: list[str] = []

    class TerminalApplication(Application):
        def settle(self) -> None:
            events.append("settle")

    host = service(tmp_path, factory=TerminalApplication)
    host.registry.installation("suspend", 44, 23)

    assert host.runnable.count() == 0
    assert host.sweep("startup") == 1
    assert events == ["settle"]
    assert host._apps[(44, 31, 7)].reconciles == []
    host.close()


def test_close_waits_for_admitted_pump_then_closes_worker_before_application_and_is_idempotent(
    tmp_path: Path,
) -> None:
    host = service(tmp_path)
    entered, release, close_started, close_finished = (threading.Event() for _ in range(4))
    events: list[str] = []

    class BlockingWorker:
        def run_available(self, *, limit: int) -> int:
            entered.set()
            assert release.wait(1)
            events.append("pump-finished")
            return 0

        def close(self) -> None:
            events.append("worker-close")

        def stop(self) -> None:
            pass

    class ClosingApplication(Application):
        def close(self) -> None:
            events.append("application-close")

    host.activity_worker = BlockingWorker()  # type: ignore[assignment]
    host._apps[(44, 31, 7)] = ClosingApplication()
    pump = threading.Thread(target=host.pump)
    pump.start()
    assert entered.wait(1)

    def close() -> None:
        close_started.set()
        host.close()
        close_finished.set()

    closing = threading.Thread(target=close)
    closing.start()
    assert close_started.wait(1)
    assert not close_finished.wait(0.05)
    release.set()
    pump.join(1)
    closing.join(1)

    assert not pump.is_alive() and not closing.is_alive()
    assert events[:3] == ["pump-finished", "worker-close", "application-close"]
    host.close()
    assert events.count("worker-close") == events.count("application-close") == 1


def test_instance_inspection_is_bounded_and_excludes_payloads_and_errors(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    root.mkdir(parents=True)
    (root / "binding.json").write_text(
        json.dumps({"instance_id": "github:44:31:pr:7", "repository": "owner/one", "pull_request": 7})
    )
    records = [
        {"record": "InstanceCreated", "instant": 0},
        {
            "record": "ActivityRequested",
            "occurrence": 3,
            "instant": 1,
            "transition": "execute.dashboard_publish",
            "activity": "dashboard_publish",
            "input": {"work": {"operation": "dashboard:three", "payload": {"secret": "must-not-escape"}}},
        },
        {
            "record": "ActivityFailed",
            "occurrence": 3,
            "instant": 2,
            "error": "credential-bearing failure must not escape",
        },
        {"record": "FiringFailed", "occurrence": 3, "instant": 2},
        {
            "record": "ActivityRequested",
            "occurrence": 4,
            "instant": 3,
            "transition": "execute.review",
            "activity": "review",
            "input": {"work": {"operation": "review:four"}},
        },
    ]
    (root / "history.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records))

    result = inspect_instance(tmp_path, 44, 31, 7)
    encoded = json.dumps(result)

    assert result["record_count"] == 5
    assert result["activities"] == {
        "requested": 2,
        "completed": 0,
        "failed": 1,
        "firing_failed": 1,
        "unresolved": [
            {
                "occurrence": 4,
                "transition": "execute.review",
                "activity": "review",
                "operation": "review:four",
            }
        ],
    }
    assert "must-not-escape" not in encoded and "credential-bearing" not in encoded


def test_instance_inspection_rejects_unsafe_binding_and_emitted_fields(tmp_path: Path) -> None:
    root = tmp_path / "applications/44/31/7"
    root.mkdir(parents=True)
    target = tmp_path / "binding-target.json"
    target.write_text(json.dumps({"instance_id": "github:44:31:pr:7", "repository": "owner/one", "pull_request": 7}))
    (root / "binding.json").symlink_to(target)
    (root / "history.jsonl").write_text(json.dumps({"record": "InstanceCreated", "instant": 0}) + "\n")
    with pytest.raises(ValueError, match="bounded regular file"):
        inspect_instance(tmp_path, 44, 31, 7)

    (root / "binding.json").unlink()
    (root / "binding.json").write_text(
        json.dumps({"instance_id": "github:44:31:pr:7", "repository": "owner/one", "pull_request": 7})
    )
    (root / "history.jsonl").write_text(
        json.dumps(
            {
                "record": "ActivityRequested",
                "occurrence": 1,
                "instant": 1,
                "transition": {"secret": "must-not-escape"},
                "activity": "review",
                "input": {"work": {"operation": "review:one"}},
            }
        )
        + "\n"
    )
    with pytest.raises(ValueError, match="Activity identifiers are malformed") as raised:
        inspect_instance(tmp_path, 44, 31, 7)
    assert "must-not-escape" not in str(raised.value)


def test_instance_inspection_rejects_a_symlinked_instance_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    applications = tmp_path / "applications/44/31"
    applications.mkdir(parents=True)
    (applications / "7").symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="not a real directory"):
        inspect_instance(tmp_path, 44, 31, 7)


def test_sweep_failure_on_one_pr_does_not_block_another(tmp_path: Path) -> None:
    for pr in (7, 8):
        root = tmp_path / "applications" / "44" / "31" / str(pr)
        bind_application(root)
        (root / "history.jsonl").write_text("", encoding="utf-8")
    made: list[Application] = []

    def factory(*args: Any, **kwargs: Any) -> Application:
        app = Application(*args, fail=len(made) == 0, **kwargs)
        made.append(app)
        return app

    host = service(tmp_path, factory=factory)
    assert host.sweep() == 1
    assert len(made) == 2 and made[1].reconciles == ["periodic:44:31:8"]


def registration_clients(repositories: tuple[tuple[int, str], ...] = ((31, "owner/one"), (32, "owner/two"))) -> Clients:
    return Clients(registration=RegistrationInventory(44, repositories))


def test_startup_reconciles_exact_registration_and_removes_former_selection(tmp_path: Path) -> None:
    composition, routes = agent_custody(tmp_path)
    host = HostService(
        config(tmp_path),
        clients=registration_clients(),
        runner=object(),
        agent_composition=composition,
        agent_routes=routes,
        readiness_composition=replace(PRODUCTION, application_factory=Application),
    )
    assert host.reconcile_registration()["admitted_repositories"] == 2
    assert host.registry.route(44, 32) is not None
    host.clients = registration_clients(((31, "owner/one"),))
    assert host.reconcile_registration()["admitted_repositories"] == 1
    assert host.registry.route(44, 32) is None


def test_registration_failure_preserves_the_current_registry_and_host_identity(tmp_path: Path) -> None:
    composition, routes = agent_custody(tmp_path)
    host = HostService(
        config(tmp_path),
        clients=registration_clients(),
        runner=object(),
        agent_composition=composition,
        agent_routes=routes,
        readiness_composition=replace(PRODUCTION, application_factory=Application),
    )
    host.reconcile_registration()
    host.clients = Clients(registration=RuntimeError("selected repository inventory is malformed"))

    with pytest.raises(RuntimeError, match="inventory is malformed"):
        host.reconcile_registration()
    assert host.installation_id == 44
    assert host.registry.route(44, 31) is not None
    assert host.registry.route(44, 32) is not None
