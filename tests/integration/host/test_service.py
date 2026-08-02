from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.webhooks import Observation
from hamsterdan.host.__main__ import inspect_instance
from hamsterdan.host.api import create_app
from hamsterdan.host.service import APP_EVENTS, APP_PERMISSIONS, HostService, QualificationFault


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
    def __init__(self, app: Client | None = None, inventory: Client | None = None):
        self.app = app or Client()
        self.inventory_client = inventory or Client()
        self.operation_calls: list[tuple[int, tuple[int, ...]]] = []
        self.operation_client = Client()
        self.closed = 0

    def inventory(self, installation_id: int) -> Client:
        assert installation_id == 44
        return self.inventory_client

    def installation(self, installation_id: int, repository_ids: list[int] | tuple[int, ...]) -> Client:
        self.operation_calls.append((installation_id, tuple(repository_ids)))
        return self.operation_client

    def close(self) -> None:
        self.closed += 1


class Application:
    def __init__(self, *args: Any, fail: bool = False, **kwargs: Any):
        self.args, self.kwargs, self.fail = args, kwargs, fail
        self.reconciles: list[str] = []
        self.comments: list[dict[str, object]] = []
        self.closed = 0

    def reconcile(self, trigger: str) -> None:
        self.reconciles.append(trigger)
        if self.fail:
            raise RuntimeError("provider secret must not escape")

    def route_comment(self, **kwargs: object) -> None:
        self.comments.append(kwargs)

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


def service(root: Path, *, clients: Clients | None = None, factory: Any = Application) -> HostService:
    result = HostService(config(root), clients=clients or Clients(), runner=object(), application_factory=factory)
    result.registry.reconcile(44, ((31, "owner/one"), (32, "owner/two")))
    return result


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
    assert made[0].kwargs["agent_fault"] is None
    host.close()
    assert all(app.closed == 1 for app in made) and clients.closed == 1


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
    assert made[0].comments[0]["text"] == "@hamsterdan-test help"


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


def test_periodic_sweep_reopens_durable_instances_and_skips_inactive_routes(tmp_path: Path) -> None:
    for repository, pr in ((31, 7), (31, 8), (999, 9)):
        root = tmp_path / "applications" / "44" / str(repository) / str(pr)
        root.mkdir(parents=True)
        (root / "history.jsonl").write_text("", encoding="utf-8")
    made: list[Application] = []
    host = service(tmp_path, factory=lambda *a, **k: made.append(Application(*a, **k)) or made[-1])

    assert host.sweep("startup") == 2
    assert [item.args[1] for item in made] == ["github:44:31:pr:7", "github:44:31:pr:8"]
    assert [item.reconciles for item in made] == [["startup:44:31:7"], ["startup:44:31:8"]]
    assert host.sweep() == 2
    assert [item.reconciles[-1] for item in made] == ["periodic:44:31:7", "periodic:44:31:8"]


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
        root.mkdir(parents=True)
        (root / "history.jsonl").write_text("", encoding="utf-8")
    made: list[Application] = []

    def factory(*args: Any, **kwargs: Any) -> Application:
        app = Application(*args, fail=len(made) == 0, **kwargs)
        made.append(app)
        return app

    host = service(tmp_path, factory=factory)
    assert host.sweep() == 1
    assert len(made) == 2 and made[1].reconciles == ["periodic:44:31:8"]


def registration_clients(
    *,
    app_changes: dict[str, object] | None = None,
    installations: object | None = None,
    repositories: object | None = None,
) -> Clients:
    app: dict[str, object] = {
        "id": 17,
        "client_id": "Iv1.client-secret-looking",
        "slug": "hamsterdan-test",
        "permissions": APP_PERMISSIONS | {"metadata": "read"},
        "events": sorted(APP_EVENTS),
    }
    app.update(app_changes or {})
    installation_value = (
        installations
        if installations is not None
        else [
            {
                "id": 44,
                "account": {"id": 23, "login": "Owner"},
                "suspended_at": None,
                "permissions": APP_PERMISSIONS | {"metadata": "read"},
            }
        ]
    )
    repository_value = (
        repositories
        if repositories is not None
        else {
            "total_count": 2,
            "repositories": [{"id": 31, "full_name": "owner/one"}, {"id": 32, "full_name": "owner/two"}],
        }
    )
    return Clients(
        Client({"/app": app, "/app/installations?per_page=100&page=1": installation_value}),
        Client({"/installation/repositories?per_page=100&page=1": repository_value}),
    )


def test_startup_reconciles_exact_registration_and_removes_former_selection(tmp_path: Path) -> None:
    host = HostService(
        config(tmp_path), clients=registration_clients(), runner=object(), application_factory=Application
    )
    assert host.reconcile_registration()["admitted_repositories"] == 2
    assert host.registry.route(44, 32) is not None
    host.clients = registration_clients(
        repositories={"total_count": 1, "repositories": [{"id": 31, "full_name": "owner/one"}]}
    )
    assert host.reconcile_registration()["admitted_repositories"] == 1
    assert host.registry.route(44, 32) is None


@pytest.mark.parametrize(
    ("changes", "installations", "message"),
    [
        ({"id": 18}, None, "identity"),
        ({"client_id": "wrong"}, None, "identity"),
        ({"slug": "wrong"}, None, "identity"),
        ({}, [], "missing or ambiguous"),
        ({}, [{"id": 44, "account": {"id": 23, "login": "Owner"}, "suspended_at": "now"}], "suspended"),
        (
            {},
            [
                {
                    "id": 44,
                    "account": {"id": 23, "login": "Owner"},
                    "suspended_at": None,
                    "permissions": APP_PERMISSIONS | {"metadata": "read", "pull_requests": "read"},
                }
            ],
            "installation permissions",
        ),
        ({"permissions": APP_PERMISSIONS | {"checks": "write"}}, None, "permissions"),
        ({"events": sorted(APP_EVENTS | {"check_run"})}, None, "events"),
    ],
)
def test_startup_rejects_identity_account_suspension_and_broad_contract_safely(
    tmp_path: Path, changes: dict[str, object], installations: object | None, message: str
) -> None:
    host = HostService(
        config(tmp_path),
        clients=registration_clients(app_changes=changes, installations=installations),
        runner=object(),
        application_factory=Application,
    )
    with pytest.raises(RuntimeError, match=message) as caught:
        host.reconcile_registration()
    assert all(
        secret not in str(caught.value) for secret in ("client-secret-looking", "private-key-secret", "hook-secret")
    )
