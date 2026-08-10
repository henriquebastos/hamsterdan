"""Process-owned composition, startup authority reconciliation, and inbox worker."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from petrus.agenticus.runtime.pi_a2_host import PiA2RuntimeHost
from petrus.motus.activity import ActivityError
from petrus.motus.dispatch import LocalDispatch
from petrus.motus.worker import Worker

from hamsterdan.agents import AgentProtocolError, AgentRunner, OperationRoutedRunner
from hamsterdan.contracts.readiness import (
    DashboardPublicationRequest,
    DashboardPublicationResult,
    ReadinessCommand,
    ReadinessPublicationResult,
)
from hamsterdan.github_app.auth import GitHubAppClients
from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.github_app.models import GitHubBoundaryError
from hamsterdan.github_app.routing import InstallationRegistry
from hamsterdan.github_app.transport import GitHubGraphQL, GitHubKitTransport
from hamsterdan.github_app.webhooks import Observation, WebhookCustody

from .agenticus import AgentComposition, AgentRouteStore
from .application import PrReadinessApplication
from .payloads import PydanticPayloadConverter
from .runnable import RunnableIndex

LOG = logging.getLogger("hamsterdan.host")
ApplicationFactory = Callable[..., PrReadinessApplication]
MAX_INVENTORY_PAGES = 20
APP_PERMISSIONS = {
    "administration": "read",
    "actions": "read",
    "contents": "write",
    "issues": "write",
    "pull_requests": "write",
}
APP_EVENTS = {
    "issue_comment",
    "pull_request",
    "pull_request_review",
    "pull_request_review_comment",
    "workflow_run",
}
_FAULT_BOUNDARIES = frozenset({"agent", "comment"})
_FAULT_PHASES = frozenset({"timed_out", "malformed", "before_call", "after_call"})
_INSTANCE_PATTERN = re.compile(r"github:([1-9][0-9]*):([1-9][0-9]*):pr:([1-9][0-9]*)\Z")
_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_DURABLE_PUBLICATIONS = frozenset({"dashboard_publish", "readiness_publish"})


@dataclass
class QualificationFault:
    """One exact, host-owned, disabled-by-default qualification failure."""

    repository: str
    pull_request: int
    boundary: str
    phase: str
    kind: str
    operation: str
    _spent: bool = field(default=False, init=False, repr=False)
    _spent_operation: str | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> QualificationFault | None:
        raw = (os.environ if environment is None else environment).get("HAMSTERDAN_QUALIFICATION_FAULT")
        if raw is None:
            return None
        if not 0 < len(raw.encode()) <= 4096:
            raise ValueError("qualification fault configuration is malformed")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("qualification fault configuration is malformed") from None
        names = {"repository", "pull_request", "boundary", "phase", "kind", "operation"}
        if not isinstance(value, dict) or set(value) != names:
            raise ValueError("qualification fault configuration is malformed")
        repository, boundary, phase, kind, operation = (
            value["repository"],
            value["boundary"],
            value["phase"],
            value["kind"],
            value["operation"],
        )
        pull_request = value["pull_request"]
        if (
            not isinstance(repository, str)
            or repository.count("/") != 1
            or type(pull_request) is not int
            or pull_request <= 0
            or boundary not in _FAULT_BOUNDARIES
            or phase not in _FAULT_PHASES
            or not isinstance(kind, str)
            or not kind
            or not isinstance(operation, str)
            or not operation
            or (boundary == "agent") != (phase in {"timed_out", "malformed"})
        ):
            raise ValueError("qualification fault configuration is malformed")
        return cls(repository, pull_request, boundary, phase, kind, operation)

    def _matches(
        self, repository: str, pull_request: int, boundary: str, phase: str, kind: str, operation: str
    ) -> bool:
        return (
            not self._spent
            and (repository.casefold(), pull_request, boundary, phase, kind)
            == (
                self.repository.casefold(),
                self.pull_request,
                self.boundary,
                self.phase,
                self.kind,
            )
            and self.operation in {operation, "next"}
        )

    def _consume(self, boundary: str, phase: str, kind: str, operation: str) -> None:
        self._spent = True
        self._spent_operation = operation
        LOG.warning(
            "qualification_fault boundary=%s phase=%s kind=%s operation=%s",
            boundary,
            phase,
            kind,
            operation,
            extra={"boundary": boundary, "phase": phase, "kind": kind, "operation": operation},
        )

    def publication(self, phase: str, repository: str, pull_request: int, kind: str, operation: str) -> None:
        with self._lock:
            if not self._matches(repository, pull_request, "comment", phase, kind, operation):
                return
            self._consume("comment", phase, kind, operation)
        raise GitHubBoundaryError("qualified provider outcome was deliberately withheld")

    def agent(self, repository: str, pull_request: int, kind: str, operation: str) -> None:
        with self._lock:
            if not self._matches(repository, pull_request, "agent", self.phase, kind, operation):
                return
            self._consume("agent", self.phase, kind, operation)
        if self.phase == "timed_out":
            raise AgentProtocolError("qualified agent execution timed out", timed_out=True)
        raise AgentProtocolError("qualified agent result is malformed")


def _json(response: Any) -> Any:
    return response.json()


class HostService:
    def __init__(
        self,
        config: HostConfig,
        *,
        clients: GitHubAppClients | None = None,
        runner: AgentRunner,
        agent_composition: AgentComposition,
        agent_routes: AgentRouteStore,
        agent_runtime: PiA2RuntimeHost | None = None,
        application_factory: ApplicationFactory = PrReadinessApplication,
        workflow_path: str = ".github/workflows/ci.yml",
        reminder_delay: float = 259200,
        poll_interval: float = 0.25,
        sweep_interval: float = 60,
        qualification_fault: QualificationFault | None = None,
    ) -> None:
        self.config = config
        self.root = config.state_path
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.clients = clients or GitHubAppClients(config, metadata_hook=self._request_metadata)
        self.registry = InstallationRegistry(
            self.root / "routes.sqlite3", account_id=config.account_id, allowed_repositories=config.allowed_repositories
        )
        _, secret = config._credentials()
        self.custody = WebhookCustody(self.root / "webhooks.sqlite3", webhook_secret=secret, registry=self.registry)
        self.runner, self.application_factory = runner, application_factory
        self.agent_composition, self.agent_routes, self.agent_runtime = agent_composition, agent_routes, agent_runtime
        self.workflow_path, self.reminder_delay, self.poll_interval = workflow_path, reminder_delay, poll_interval
        self.sweep_interval = sweep_interval
        self.qualification_fault = qualification_fault
        self.installation_id: int | None = None
        self._apps: dict[tuple[int, int, int], PrReadinessApplication] = {}
        self._locks: dict[tuple[int, int, int], threading.Lock] = {}
        self._stop = asyncio.Event()
        self._closed = False
        self._instances: dict[str, tuple[int, int, int]] = {}
        self._application_lock = threading.RLock()
        self._pump_lock = threading.Lock()
        self._scheduler_errors: dict[str, str] = {}
        self.runnable = RunnableIndex(self.root / "runnable.sqlite3")
        dispatch_path = self.root / "activity-dispatch.sqlite3"
        provider = LocalDispatch(dispatch_path, instance="host-worker").worker(("publication",))
        self.activity_worker = Worker(provider, {}, resolver=self._resolve_activity)
        self._dispatch_path = dispatch_path

    def _resolve_activity(self, instance: str, name: str):
        if name not in _DURABLE_PUBLICATIONS:
            return None
        match = _INSTANCE_PATTERN.fullmatch(instance)
        if match is None:
            return self._invalid_publication_scope
        installation_id, repository_id, pull_request_number = (int(value) for value in match.groups())
        key = installation_id, repository_id, pull_request_number
        try:
            application = self._application(*key, allow_inactive_binding=True)
            implementation = application.activity(name)
        except Exception:  # noqa: BLE001 -- recognized publications must fail closed through an implementation
            return self._invalid_publication_scope
        if implementation is None:
            return self._invalid_publication_scope

        def wake(invocation, *, context):
            try:
                with self._locks[key]:
                    try:
                        if self.registry.route(key[0], key[1]) is None:
                            return self._stale_publication_result(name, invocation)
                        return implementation(invocation, context=context)
                    except ActivityError:
                        raise
                    except Exception as error:
                        raise ActivityError(
                            "publication invariant failed",
                            kind=type(error).__name__,
                            retryable=False,
                        ) from error
            finally:
                self.runnable.wake(instance, time.time(), "activity-terminal", name)

        return wake

    @staticmethod
    def _invalid_publication_scope(invocation, *, context):
        raise ActivityError("publication scope is unavailable", kind="PublicationScopeError", retryable=False)

    @staticmethod
    def _stale_publication_result(name: str, invocation: object) -> object:
        converter = PydanticPayloadConverter()
        try:
            payload = cast(Any, invocation).input
            request_name = "work" if name == "dashboard_publish" else "command"
            request_type = DashboardPublicationRequest if name == "dashboard_publish" else ReadinessCommand
            result_type = DashboardPublicationResult if name == "dashboard_publish" else ReadinessPublicationResult
            if not isinstance(payload, dict) or request_name not in payload:
                raise TypeError("publication invocation has no request")
            request = cast(
                DashboardPublicationRequest | ReadinessCommand,
                converter.decode(payload[request_name], request_type),
            )
            result = result_type(request.epoch, request.head, False, request.operation, True)
            return converter.encode(result, result_type)
        except Exception as error:
            raise ActivityError(
                "publication scope is unavailable", kind="PublicationScopeError", retryable=False
            ) from error

    def _request_metadata(self, metadata: Any) -> None:
        LOG.info(
            "github_response method=%s path=%s request_id=%s status=%s rate_limit_remaining=%s rate_limit_reset=%s",
            metadata.method,
            metadata.path,
            metadata.request_id,
            metadata.status,
            metadata.rate_limit_remaining,
            metadata.rate_limit_reset,
            extra={
                "github_method": metadata.method,
                "github_path": metadata.path,
                "github_request_id": metadata.request_id,
                "rate_limit_remaining": metadata.rate_limit_remaining,
                "rate_limit_reset": metadata.rate_limit_reset,
                "status": metadata.status,
            },
        )

    def reconcile_registration(self) -> dict[str, object]:
        app = _json(self.clients.app.request("GET", "/app"))
        if not isinstance(app, dict) or (app.get("id"), app.get("client_id"), str(app.get("slug", "")).casefold()) != (
            self.config.app_id,
            self.config.client_id,
            self.config.app_slug,
        ):
            raise RuntimeError("configured GitHub App identity does not match provider authority")
        permissions = app.get("permissions")
        events = app.get("events")
        if not isinstance(permissions, dict):
            raise RuntimeError("GitHub App permissions are malformed")  # noqa: TRY004
        observed_permissions = {str(key): str(value) for key, value in permissions.items() if key != "metadata"}
        if observed_permissions != APP_PERMISSIONS or permissions.get("metadata", "read") != "read":
            raise RuntimeError(
                "GitHub App permissions do not match the required first-demo contract: "
                f"expected={sorted(APP_PERMISSIONS.items())!r} observed={sorted(observed_permissions.items())!r}"
            )
        if not isinstance(events, list):
            raise RuntimeError("GitHub App events are malformed")  # noqa: TRY004
        observed_events = sorted(str(item) for item in events)
        if set(observed_events) != APP_EVENTS or len(observed_events) != len(APP_EVENTS):
            raise RuntimeError(
                "GitHub App events do not match the required first-demo contract: "
                f"expected={sorted(APP_EVENTS)!r} observed={observed_events!r}"
            )
        installations: list[dict[str, Any]] = []
        for page in range(1, MAX_INVENTORY_PAGES + 1):
            batch = _json(self.clients.app.request("GET", f"/app/installations?per_page=100&page={page}"))
            if not isinstance(batch, list):
                raise RuntimeError("GitHub installation inventory is malformed")  # noqa: TRY004
            installations.extend(cast(list[dict[str, Any]], batch))
            if len(batch) < 100:
                break
        else:
            raise RuntimeError("GitHub installation inventory exceeds the bounded pagination limit")
        matches = [
            item
            for item in installations
            if isinstance(item, dict)
            and isinstance(item.get("account"), dict)
            and item["account"].get("id") == self.config.account_id
            and str(item["account"].get("login", "")).casefold() == self.config.account_login.casefold()
        ]
        if len(matches) != 1:
            raise RuntimeError("configured installation account is missing or ambiguous")
        selected = matches[0]
        if selected.get("suspended_at") is not None:
            raise RuntimeError("configured installation is suspended")
        installation_permissions = selected.get("permissions")
        if not isinstance(installation_permissions, dict):
            raise RuntimeError("configured installation permissions are malformed")  # noqa: TRY004
        observed_installation_permissions = {
            str(key): str(value) for key, value in installation_permissions.items() if key != "metadata"
        }
        if (
            observed_installation_permissions != APP_PERMISSIONS
            or installation_permissions.get("metadata", "read") != "read"
        ):
            raise RuntimeError(
                "configured installation permissions do not match the required first-demo contract: "
                f"expected={sorted(APP_PERMISSIONS.items())!r} "
                f"observed={sorted(observed_installation_permissions.items())!r}"
            )
        installation_id = selected.get("id")
        if type(installation_id) is not int or installation_id <= 0:
            raise RuntimeError("configured installation identity is malformed")
        client = self.clients.inventory(installation_id)
        repositories: list[dict[str, Any]] = []
        total: int | None = None
        for page in range(1, MAX_INVENTORY_PAGES + 1):
            payload = _json(client.request("GET", f"/installation/repositories?per_page=100&page={page}"))
            batch = payload.get("repositories") if isinstance(payload, dict) else None
            current_total = payload.get("total_count") if isinstance(payload, dict) else None
            if not isinstance(batch, list) or type(current_total) is not int or current_total < 0:
                raise RuntimeError("selected repository inventory is malformed")
            total = current_total if total is None else total
            if current_total != total:
                raise RuntimeError("selected repository inventory changed during pagination")
            repositories.extend(cast(list[dict[str, Any]], batch))
            if len(repositories) >= total:
                if len(repositories) != total:
                    raise RuntimeError("selected repository inventory is inconsistent")
                break
        else:
            raise RuntimeError("selected repository inventory exceeds the bounded pagination limit")
        normalized = tuple(
            (item["id"], item["full_name"])
            for item in repositories
            if isinstance(item, dict) and type(item.get("id")) is int and isinstance(item.get("full_name"), str)
        )
        count = self.registry.reconcile(installation_id, normalized)
        self.installation_id = installation_id
        return {
            "app_id": self.config.app_id,
            "app_slug": self.config.app_slug,
            "installation_id": installation_id,
            "admitted_repositories": count,
        }

    def _application(
        self,
        installation_id: int,
        repository_id: int,
        pull_request_number: int,
        *,
        allow_inactive_binding: bool = False,
    ) -> PrReadinessApplication:
        key = installation_id, repository_id, pull_request_number
        with self._application_lock:
            if key in self._apps:
                return self._apps[key]
            route = self.registry.route(installation_id, repository_id)
            if route is None and not allow_inactive_binding:
                raise RuntimeError("route became inactive")
            instance = f"github:{installation_id}:{repository_id}:pr:{pull_request_number}"
            root = self.root / "applications" / str(installation_id) / str(repository_id) / str(pull_request_number)
            if route is None:
                binding = root / "binding.json"
                try:
                    if binding.is_symlink() or not binding.is_file() or binding.stat().st_size > 4096:
                        raise ValueError
                    persisted = json.loads(binding.read_text(encoding="utf-8"))
                except OSError, ValueError, json.JSONDecodeError:
                    raise RuntimeError("inactive route has no strict durable binding") from None
                expected_names = {"instance_id", "repository", "pull_request"}
                repository = persisted.get("repository") if isinstance(persisted, dict) else None
                if (
                    not isinstance(persisted, dict)
                    or set(persisted) != expected_names
                    or persisted.get("instance_id") != instance
                    or type(persisted.get("pull_request")) is not int
                    or persisted.get("pull_request") != pull_request_number
                    or not isinstance(repository, str)
                    or _REPOSITORY_PATTERN.fullmatch(repository) is None
                    or not (root / "history.jsonl").is_file()
                ):
                    raise RuntimeError("inactive route has no strict durable binding")
                repository_full_name = repository
            else:
                assert route is not None
                repository_full_name = route.repository_full_name
            operation_client = self.clients.installation(installation_id, [repository_id])
            transport = GitHubKitTransport(operation_client)
            authority = GitHubAuthority(
                transport,
                repository_full_name,
                pull_request_number,
                graphql=GitHubGraphQL(transport),
            )
            qualification_fault = self.qualification_fault
            routes, composition = self.agent_routes, self.agent_composition

            def agent_dispatch(operation: str, attempt: int) -> None:
                routes.claim(operation, composition)
                if isinstance(self.runner, OperationRoutedRunner):
                    digest = hashlib.sha256(f"{operation}\0{attempt}".encode()).hexdigest()
                    self.runner.route_operation(f"pi:{digest}")

            application = self.application_factory(
                root,
                f"github:{installation_id}:{repository_id}:pr:{pull_request_number}",
                authority,
                self.runner,
                bot_login=self.config.bot_login,
                public_clone_url=f"https://github.com/{repository_full_name}.git",
                workflow_path=self.workflow_path,
                reminder_delay=self.reminder_delay,
                publication_fault=None if qualification_fault is None else qualification_fault.publication,
                agent_fault=(
                    None
                    if qualification_fault is None
                    else lambda kind, operation: qualification_fault.agent(
                        repository_full_name, pull_request_number, kind, operation
                    )
                ),
                agent_dispatch=agent_dispatch,
                agent_settle=routes.settle,
                dispatch_path=self._dispatch_path,
            )
            self._locks[key] = threading.Lock()
            self._apps[key] = application
            self._instances[instance] = key
            return application

    def sweep(self, trigger: str = "periodic") -> int:
        """Reconcile durable PR Instances after restarts or missed provider events."""
        applications = self.root / "applications"
        if not applications.is_dir():
            return 0
        reconciled = 0
        for history in sorted(applications.glob("*/*/*/history.jsonl")):
            try:
                installation_id, repository_id, pull_request_number = (int(part) for part in history.parts[-4:-1])
            except ValueError:
                continue
            if min(installation_id, repository_id, pull_request_number) <= 0:
                continue
            if self.registry.route(installation_id, repository_id) is None:
                continue
            try:
                instance = f"github:{installation_id}:{repository_id}:pr:{pull_request_number}"
                reconciled += self._run_instance(instance, reconcile_trigger=trigger)
            except Exception as error:  # noqa: BLE001 -- one PR must not prevent repair of another
                LOG.warning(
                    "application_sweep_retry installation_id=%s repository_id=%s pull_request_number=%s error_class=%s",
                    installation_id,
                    repository_id,
                    pull_request_number,
                    type(error).__name__,
                    extra={
                        "installation_id": installation_id,
                        "repository_id": repository_id,
                        "pull_request_number": pull_request_number,
                        "error_class": type(error).__name__,
                    },
                )
        return reconciled

    def process(self, item: Observation) -> None:
        self._process(item, lock_owned=False)
        instance = self._instance(item)
        if instance is None:
            return
        match = _INSTANCE_PATTERN.fullmatch(instance)
        assert match is not None
        installation_id, repository_id, pull_request_number = (int(value) for value in match.groups())
        key = installation_id, repository_id, pull_request_number
        application = self._apps.get(key)
        if application is None:
            return
        with self._locks[key]:
            settle = getattr(application, "settle", None)
            self._record_posture(instance, None if settle is None else settle())

    def _process(self, item: Observation, *, lock_owned: bool) -> None:
        fields = {
            "delivery_id": item.delivery_id,
            "event": item.event,
            "installation_id": item.installation_id,
            "repository_id": item.repository_id,
            "pull_request_number": item.pull_request_number,
        }
        if item.event in {"ping", "installation", "installation_repositories"}:
            self.custody.acknowledge(item.delivery_id, "non-workflow event")
            return
        if (
            item.installation_id is None
            or item.repository_id is None
            or self.registry.route(item.installation_id, item.repository_id) is None
        ):
            self.custody.acknowledge(item.delivery_id, "inactive route")
            return
        if item.pull_request_number is None:
            self.custody.acknowledge(item.delivery_id, "no pull request")
            return
        if item.event == "issue_comment":
            addressed = (item.comment_body or "").strip().casefold()
            mention = f"@{self.config.app_slug}"
            if (
                item.action != "created"
                or (item.actor_login or "").casefold() == self.config.bot_login
                or item.actor_type != "User"
                or (item.author_association or "").upper() not in {"OWNER", "MEMBER", "COLLABORATOR"}
                or not (addressed == mention or addressed.startswith(mention + " "))
            ):
                self.custody.acknowledge(item.delivery_id, "comment not addressed")
                return
        try:
            installation_id = item.installation_id
            repository_id = item.repository_id
            pull_request_number = item.pull_request_number
            application = self._application(installation_id, repository_id, pull_request_number)
            key = installation_id, repository_id, pull_request_number
            lock = self._locks[key]

            def perform() -> None:
                if self.registry.route(installation_id, repository_id) is None:
                    self.custody.acknowledge(item.delivery_id, "route inactive before work")
                    return
                if item.event == "issue_comment":
                    application.route_comment(
                        delivery_id=item.delivery_id,
                        comment_id=item.comment_id or 0,
                        actor_id=item.actor_id or 0,
                        actor_login=item.actor_login or "",
                        actor_type=item.actor_type or "",
                        association=item.author_association or "",
                        text=item.comment_body or "",
                    )
                else:
                    application.reconcile(f"github-delivery:{item.delivery_id}")

            if lock_owned:
                perform()
            else:
                with lock:
                    perform()
            self.custody.acknowledge(item.delivery_id)
            LOG.info(
                "webhook_terminal delivery_id=%s event=%s installation_id=%s repository_id=%s "
                "pull_request_number=%s disposition=processed",
                item.delivery_id,
                item.event,
                item.installation_id,
                item.repository_id,
                item.pull_request_number,
                extra=fields | {"disposition": "processed"},
            )
        except Exception as error:  # noqa: BLE001 -- provider/Engine failures must leave every delivery retryable
            self.custody.retry(item.delivery_id, error)
            LOG.warning(
                "webhook_retry delivery_id=%s event=%s installation_id=%s repository_id=%s "
                "pull_request_number=%s disposition=retry error_class=%s",
                item.delivery_id,
                item.event,
                item.installation_id,
                item.repository_id,
                item.pull_request_number,
                type(error).__name__,
                extra=fields | {"disposition": "retry", "error_class": type(error).__name__},
            )

    async def worker(self) -> None:
        loop = asyncio.get_running_loop()
        await asyncio.to_thread(self.sweep, "startup")
        next_sweep = loop.time() + self.sweep_interval
        while not self._stop.is_set():
            await asyncio.to_thread(self.pump)
            if self._stop.is_set():
                break
            await asyncio.to_thread(self.project_pending)
            await asyncio.to_thread(self.run_due)
            if self._stop.is_set():
                break
            if loop.time() >= next_sweep:
                await asyncio.to_thread(self.sweep)
                next_sweep = loop.time() + self.sweep_interval
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    def pump(self, limit: int = 20) -> int:
        """Run one bounded Activity cycle and settle only owning Instances."""
        with self._pump_lock:
            processed = self.activity_worker.run_available(limit=limit)
            # Repair locally generated terminals which did not execute through
            # the resolver. The durable Dispatch/History remain authoritative.
            for instance, key in tuple(self._instances.items()):
                pending = getattr(self._apps[key], "has_unresolved_publication", None)
                if pending is not None and pending():
                    self.runnable.wake(instance, time.time(), "dispatch-repair", "unresolved-publication")
            return processed

    @staticmethod
    def _instance(item: Observation) -> str | None:
        if item.installation_id is None or item.repository_id is None or item.pull_request_number is None:
            return None
        return f"github:{item.installation_id}:{item.repository_id}:pr:{item.pull_request_number}"

    def project_pending(self) -> int:
        """Project canonical due inbox observations into noncanonical wake hints."""
        projected = 0
        for item in self.custody.pending(limit=1000):
            instance = self._instance(item)
            if (
                instance is None
                or self.registry.route(cast(int, item.installation_id), cast(int, item.repository_id)) is None
            ):
                self.process(item)
                continue
            identity = item.delivery_id if item.event == "issue_comment" else "reconcile"
            self.runnable.wake(instance, time.time(), "webhook", identity)
            projected += 1
        return projected

    def _record_posture(self, instance: str, outcome: object | None) -> None:
        self.runnable.replace_timer(instance, getattr(outcome, "next_maturation", None))

    def _run_instance(self, instance: str, *, reconcile_trigger: str | None = None) -> bool:
        match = _INSTANCE_PATTERN.fullmatch(instance)
        if match is None:
            return False
        installation_id, repository_id, pull_request_number = (int(value) for value in match.groups())
        key = installation_id, repository_id, pull_request_number
        route_active = self.registry.route(key[0], key[1]) is not None
        if not route_active and key not in self._apps:
            return False
        application = self._apps[key] if not route_active else self._application(*key)
        with self._locks[key]:
            if route_active:
                for item in self.custody.pending(limit=1000):
                    if self._instance(item) == instance:
                        self._process(item, lock_owned=True)
            settle = getattr(application, "settle", None)
            if route_active and reconcile_trigger is not None and settle is not None:
                # Repair a frozen terminal before provider reconciliation can
                # infer that the same logical publication is still pending.
                self._record_posture(instance, settle())
            if route_active and reconcile_trigger is not None:
                application.reconcile(f"{reconcile_trigger}:{key[0]}:{key[1]}:{key[2]}")
            outcome = None if settle is None else settle()
            self._record_posture(instance, outcome)
        return True

    def run_due(self, limit: int = 100) -> int:
        instances = self.runnable.take_due(limit)
        processed = 0
        for instance in instances:
            try:
                processed += self._run_instance(instance)
                self._scheduler_errors.pop(instance, None)
            except Exception as error:  # noqa: BLE001 -- one damaged Instance must not consume later due wakes
                error_class = type(error).__name__
                self._scheduler_errors[instance] = error_class
                self.runnable.wake(instance, time.time(), "scheduler-repair", "run-due-failure")
                LOG.warning(
                    "scheduler_instance_degraded instance=%s error_class=%s",
                    instance,
                    error_class,
                    extra={"instance": instance, "error_class": error_class},
                )
        return processed

    def stop(self) -> None:
        self._stop.set()
        self.activity_worker.stop()

    def health(self) -> dict[str, object]:
        return {
            "status": "degraded" if self._scheduler_errors else "ok",
            "installation_reconciled": self.installation_id is not None,
            "active_repositories": self.registry.active_count(),
            "applications": len(self._apps),
            "inbox": self.custody.counts(),
            "runnable_hints": self.runnable.count(),
            "scheduler": {
                "degraded_instances": len(self._scheduler_errors),
                "error_classes": sorted(set(self._scheduler_errors.values())),
            },
        }

    def settle_terminals_for_shutdown(self) -> None:
        """Boundedly collect terminals for loaded Instances without driving more Attempts."""
        for instance, key in tuple(self._instances.items()):
            application = self._apps.get(key)
            if application is None:
                continue
            settle = getattr(application, "settle", None)
            if settle is None:
                continue
            try:
                with self._locks[key]:
                    self._record_posture(instance, settle())
            except Exception as error:  # noqa: BLE001 -- shutdown must continue closing all custody
                LOG.warning(
                    "shutdown_terminal_settlement_failed instance=%s error_class=%s",
                    instance,
                    type(error).__name__,
                    extra={"instance": instance, "error_class": type(error).__name__},
                )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        failure: Exception | None = None
        with self._pump_lock:
            try:
                self.settle_terminals_for_shutdown()
            except Exception as error:  # noqa: BLE001 -- remaining resources still require closure
                failure = error
            try:
                self.activity_worker.close()
            except Exception as error:  # noqa: BLE001 -- remaining resources still require closure
                if failure is None:
                    failure = error
        runtime = () if self.agent_runtime is None else (self.agent_runtime,)
        for resource in (
            *self._apps.values(),
            self.runnable,
            self.custody,
            self.registry,
            self.clients,
            *runtime,
            self.agent_routes,
        ):
            try:
                resource.close()
            except Exception as error:  # noqa: BLE001 -- every owned resource must still receive exactly one close
                if failure is None:
                    failure = error
        if failure is not None:
            raise failure
