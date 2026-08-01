"""Process-owned composition, startup authority reconciliation, and inbox worker."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any, cast

from hamsterdan.agents.amp import AmpExecuteRunner
from hamsterdan.github_app.auth import GitHubAppClients
from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.github_app.routing import InstallationRegistry
from hamsterdan.github_app.transport import GitHubGraphQL, GitHubKitTransport
from hamsterdan.github_app.webhooks import Observation, WebhookCustody

from .application import PrReadinessApplication

LOG = logging.getLogger("hamsterdan.host")
ApplicationFactory = Callable[..., PrReadinessApplication]
MAX_INVENTORY_PAGES = 20
APP_PERMISSIONS = {
    "administration": "read",
    "actions": "read",
    "contents": "write",
    "issues": "write",
    "pull_requests": "read",
}
APP_EVENTS = {
    "issue_comment",
    "pull_request",
    "pull_request_review",
    "pull_request_review_comment",
    "workflow_run",
}


def _json(response: Any) -> Any:
    return response.json()


class HostService:
    def __init__(
        self,
        config: HostConfig,
        *,
        clients: GitHubAppClients | None = None,
        runner: AmpExecuteRunner | None = None,
        application_factory: ApplicationFactory = PrReadinessApplication,
        workflow_path: str = ".github/workflows/ci.yml",
        reminder_delay: float = 259200,
        poll_interval: float = 0.25,
        sweep_interval: float = 60,
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
        self.runner, self.application_factory = runner or AmpExecuteRunner(), application_factory
        self.workflow_path, self.reminder_delay, self.poll_interval = workflow_path, reminder_delay, poll_interval
        self.sweep_interval = sweep_interval
        self.installation_id: int | None = None
        self._apps: dict[tuple[int, int, int], PrReadinessApplication] = {}
        self._locks: dict[tuple[int, int, int], threading.Lock] = {}
        self._stop = asyncio.Event()
        self._closed = False

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
        if (
            not isinstance(permissions, dict)
            or {str(key): str(value) for key, value in permissions.items() if key != "metadata"} != APP_PERMISSIONS
            or permissions.get("metadata", "read") != "read"
        ):
            raise RuntimeError("GitHub App permissions do not match the required first-demo contract")
        if not isinstance(events, list) or set(events) != APP_EVENTS or len(events) != len(APP_EVENTS):
            raise RuntimeError("GitHub App events do not match the required first-demo contract")
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
        self, installation_id: int, repository_id: int, pull_request_number: int
    ) -> PrReadinessApplication:
        key = installation_id, repository_id, pull_request_number
        if key not in self._apps:
            route = self.registry.route(installation_id, repository_id)
            if route is None:
                raise RuntimeError("route became inactive")
            operation_client = self.clients.installation(installation_id, [repository_id])
            transport = GitHubKitTransport(operation_client)
            authority = GitHubAuthority(
                transport,
                route.repository_full_name,
                pull_request_number,
                graphql=GitHubGraphQL(transport),
            )
            root = self.root / "applications" / str(installation_id) / str(repository_id) / str(pull_request_number)
            self._apps[key] = self.application_factory(
                root,
                f"github:{installation_id}:{repository_id}:pr:{pull_request_number}",
                authority,
                self.runner,
                bot_login=self.config.bot_login,
                public_clone_url=f"https://github.com/{route.repository_full_name}.git",
                workflow_path=self.workflow_path,
                reminder_delay=self.reminder_delay,
            )
            self._locks[key] = threading.Lock()
        return self._apps[key]

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
            key = installation_id, repository_id, pull_request_number
            try:
                application = self._application(*key)
                with self._locks[key]:
                    application.reconcile(f"{trigger}:{installation_id}:{repository_id}:{pull_request_number}")
                reconciled += 1
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
            aliases = ("/hamsterdan", f"@{self.config.app_slug}")
            if (
                item.action != "created"
                or (item.actor_login or "").casefold() == self.config.bot_login
                or item.actor_type != "User"
                or (item.author_association or "").upper() not in {"OWNER", "MEMBER", "COLLABORATOR"}
                or not any(addressed == alias or addressed.startswith(alias + " ") for alias in aliases)
            ):
                self.custody.acknowledge(item.delivery_id, "comment not addressed")
                return
        try:
            application = self._application(item.installation_id, item.repository_id, item.pull_request_number)
            key = item.installation_id, item.repository_id, item.pull_request_number
            with self._locks[key]:
                if self.registry.route(item.installation_id, item.repository_id) is None:
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
        next_sweep = loop.time()
        while not self._stop.is_set():
            for item in self.custody.pending():
                await asyncio.to_thread(self.process, item)
            if loop.time() >= next_sweep:
                await asyncio.to_thread(self.sweep)
                next_sweep = loop.time() + self.sweep_interval
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "installation_reconciled": self.installation_id is not None,
            "active_repositories": self.registry.active_count(),
            "applications": len(self._apps),
            "inbox": self.custody.counts(),
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        failure: Exception | None = None
        for resource in (*self._apps.values(), self.custody, self.registry, self.clients):
            try:
                resource.close()
            except Exception as error:  # noqa: BLE001 -- every owned resource must still receive exactly one close
                if failure is None:
                    failure = error
        if failure is not None:
            raise failure
