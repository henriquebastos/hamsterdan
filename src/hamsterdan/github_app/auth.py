"""Narrow ownership wrapper around GitHubKit App authentication."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, Self, cast

import httpx
from githubkit import GitHub
from githubkit.auth import AppAuthStrategy
from githubkit.cache import MemCacheStrategy

from .config import AccountConfig, HostConfig
from .models import GitHubBoundaryError, InstallationInventory, RegistrationInventory
from .transport import GitHubKitTransport

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
    "pull_request_review_thread",
    "workflow_run",
}


@dataclass(frozen=True)
class RequestMetadata:
    method: str
    path: str
    request_id: str | None
    rate_limit_remaining: int | None
    rate_limit_reset: int | None
    status: int


class ClientFactory(Protocol):
    def __call__(self, auth: Any = None, **kwargs: Any) -> GitHub: ...


def _integer_header(response: httpx.Response, name: str) -> int | None:
    value = response.headers.get(name)
    return int(value) if value is not None and value.isascii() and value.isdecimal() else None


class GitHubAppClients:
    """Own App and installation clients for one process and registration."""

    def __init__(
        self,
        config: HostConfig,
        *,
        client_factory: ClientFactory | None = None,
        metadata_hook: Callable[[RequestMetadata], None] | None = None,
        cache_strategy: object | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        private_key, _ = config._credentials()
        self._auth = AppAuthStrategy(config.app_id, private_key, client_id=config.client_id)
        self._factory = cast(ClientFactory, GitHub) if client_factory is None else client_factory
        self._metadata_hook = metadata_hook
        # GitHubKit owns token expiry and refresh. A process-owner-local strategy
        # prevents its module-level default cache leaking tokens across restarts.
        self._cache = MemCacheStrategy() if cache_strategy is None else cache_strategy
        self._transport = transport
        self._clients: dict[tuple[int, tuple[int, ...] | None], GitHub] = {}
        self._closed = False
        self._app = self._make(self._auth)

    def _make(self, auth: object) -> GitHub:
        hooks = {"response": [self._observe]} if self._metadata_hook else None
        kwargs: dict[str, object] = {
            "auto_retry": False,
            "follow_redirects": False,
            "trust_env": False,
            "event_hooks": hooks,
            "transport": self._transport,
        }
        kwargs["cache_strategy"] = self._cache
        return self._factory(auth, **kwargs)

    def _observe(self, response: httpx.Response) -> None:
        assert self._metadata_hook is not None
        self._metadata_hook(
            RequestMetadata(
                response.request.method,
                response.request.url.path,
                response.headers.get("x-github-request-id"),
                _integer_header(response, "x-ratelimit-remaining"),
                _integer_header(response, "x-ratelimit-reset"),
                response.status_code,
            )
        )

    @property
    def app(self) -> GitHub:
        return self._app

    def installation(self, installation_id: int, repository_ids: list[int] | tuple[int, ...]) -> GitHub:
        if type(installation_id) is not int or installation_id <= 0:
            raise ValueError("installation id is malformed")
        canonical = tuple(sorted(set(repository_ids)))
        if not canonical or any(type(item) is not int or item <= 0 for item in canonical):
            raise ValueError("repository ids are malformed")
        key = installation_id, canonical
        if key not in self._clients:
            self._clients[key] = self._make(self._auth.as_installation(installation_id, repository_ids=canonical))
        return self._clients[key]

    def inventory(self, installation_id: int) -> GitHub:
        """Return an installation client unrestricted by a repository token allow-list.

        This is only for discovering the provider's selected-repository inventory;
        operation clients must use :meth:`installation` with one exact repository.
        """
        if type(installation_id) is not int or installation_id <= 0:
            raise ValueError("installation id is malformed")
        key = installation_id, None
        if key not in self._clients:
            self._clients[key] = self._make(self._auth.as_installation(installation_id))
        return self._clients[key]

    def registration_inventory(self, config: HostConfig) -> RegistrationInventory:
        """Validate one App registration and every configured installation account."""
        app_transport = GitHubKitTransport(self.app)
        app_response = app_transport.request("GET", "/app")
        if app_response.status != 200:
            raise GitHubBoundaryError("GitHub App registration evidence is unavailable")
        app = app_response.body
        if not isinstance(app, dict):
            raise RuntimeError("configured GitHub App identity does not match provider authority")  # noqa: TRY004
        app_id, client_id, slug = app.get("id"), app.get("client_id"), app.get("slug")
        if (
            type(app_id) is not int
            or app_id != config.app_id
            or type(client_id) is not str
            or client_id != config.client_id
            or type(slug) is not str
            or slug.casefold() != config.app_slug
        ):
            raise RuntimeError("configured GitHub App identity does not match provider authority")
        _validate_permissions(app.get("permissions"), "GitHub App")
        events = app.get("events")
        if not isinstance(events, list):
            raise RuntimeError("GitHub App events are malformed")  # noqa: TRY004
        observed_events = sorted(str(item) for item in events)
        if set(observed_events) != APP_EVENTS or len(observed_events) != len(APP_EVENTS):
            raise RuntimeError(
                "GitHub App events do not match the required first-demo contract: "
                f"expected={sorted(APP_EVENTS)!r} observed={observed_events!r}"
            )
        installations: list[dict[str, Any]] = []
        current: str | None = "/app/installations?per_page=100"
        for _ in range(MAX_INVENTORY_PAGES):
            response = app_transport.request("GET", current)
            if response.status != 200:
                raise GitHubBoundaryError("GitHub installation inventory is unavailable")
            batch = response.body
            if not isinstance(batch, list):
                raise RuntimeError("GitHub installation inventory is malformed")  # noqa: TRY004
            installations.extend(cast(list[dict[str, Any]], batch))
            current = response.next_path
            if current is None:
                break
        else:
            raise RuntimeError("GitHub installation inventory exceeds the bounded pagination limit")
        inventory = tuple(self._account_inventory(account, installations) for account in config.accounts)
        installation_ids = {item.installation_id for item in inventory}
        if len(installation_ids) != len(inventory):
            raise RuntimeError("configured installation identity is ambiguous")
        return RegistrationInventory(inventory)

    def _account_inventory(self, account: AccountConfig, installations: list[dict[str, Any]]) -> InstallationInventory:
        matches = [
            item
            for item in installations
            if isinstance(item, dict)
            and isinstance(item.get("account"), dict)
            and type(item["account"].get("id")) is int
            and item["account"]["id"] == account.account_id
            and type(item["account"].get("login")) is str
            and item["account"]["login"].casefold() == account.account_login.casefold()
        ]
        if len(matches) != 1:
            raise RuntimeError("configured installation account is missing or ambiguous")
        selected = matches[0]
        if "suspended_at" not in selected:
            raise RuntimeError("configured installation suspension evidence is malformed")
        if selected.get("suspended_at") is not None:
            raise RuntimeError("configured installation is suspended")
        _validate_permissions(selected.get("permissions"), "configured installation")
        installation_id = selected.get("id")
        if type(installation_id) is not int or installation_id <= 0:
            raise RuntimeError("configured installation identity is malformed")
        transport = GitHubKitTransport(self.inventory(installation_id))
        repositories: list[dict[str, Any]] = []
        total: int | None = None
        current = "/installation/repositories?per_page=100"
        for _ in range(MAX_INVENTORY_PAGES):
            response = transport.request("GET", current)
            if response.status != 200:
                raise GitHubBoundaryError("GitHub repository inventory is unavailable")
            payload = response.body
            batch = payload.get("repositories") if isinstance(payload, dict) else None
            current_total = payload.get("total_count") if isinstance(payload, dict) else None
            if not isinstance(batch, list) or type(current_total) is not int or current_total < 0:
                raise RuntimeError("selected repository inventory is malformed")
            total = current_total if total is None else total
            if current_total != total:
                raise RuntimeError("selected repository inventory changed during pagination")
            repositories.extend(cast(list[dict[str, Any]], batch))
            if len(repositories) > total or (len(repositories) == total and response.next_path is not None):
                raise RuntimeError("selected repository inventory is inconsistent")
            current = response.next_path
            if current is None:
                break
        else:
            raise RuntimeError("selected repository inventory exceeds the bounded pagination limit")
        if len(repositories) != total:
            raise RuntimeError("selected repository inventory is inconsistent")
        if any(not _valid_repository(item) for item in repositories):
            raise RuntimeError("selected repository inventory is malformed")
        normalized = tuple((cast(int, item["id"]), cast(str, item["full_name"])) for item in repositories)
        if len({item[0] for item in normalized}) != len(normalized) or len(
            {item[1].casefold() for item in normalized}
        ) != len(normalized):
            raise RuntimeError("selected repository inventory is inconsistent")
        observed = {(item[0], item[1].casefold()) for item in normalized}
        if not set(account.repositories).issubset(observed):
            raise RuntimeError("configured repositories are unavailable from the installation")
        return InstallationInventory(installation_id, account.account_id, normalized)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _validate_permissions(value: object, owner: str) -> None:
    if not isinstance(value, dict):
        raise RuntimeError(f"{owner} permissions are malformed")  # noqa: TRY004
    observed = {str(key): str(permission) for key, permission in value.items() if key != "metadata"}
    if observed != APP_PERMISSIONS or value.get("metadata", "read") != "read":
        raise RuntimeError(
            f"{owner} permissions do not match the required first-demo contract: "
            f"expected={sorted(APP_PERMISSIONS.items())!r} observed={sorted(observed.items())!r}"
        )


def _valid_repository(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    repository_id, full_name = value.get("id"), value.get("full_name")
    return (
        type(repository_id) is int
        and repository_id > 0
        and type(full_name) is str
        and 1 <= len(full_name) <= 201
        and full_name.isascii()
        and full_name.isprintable()
        and full_name.count("/") == 1
        and all(part and part.strip() == part for part in full_name.split("/"))
    )
