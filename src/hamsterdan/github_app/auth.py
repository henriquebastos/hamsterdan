"""Narrow ownership wrapper around GitHubKit App authentication."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, Self, cast

import httpx
from githubkit import GitHub
from githubkit.auth import AppAuthStrategy
from githubkit.cache import MemCacheStrategy

from .config import HostConfig


@dataclass(frozen=True)
class RequestMetadata:
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
        client = self._factory(auth, **kwargs)
        client.__enter__()
        return client

    def _observe(self, response: httpx.Response) -> None:
        assert self._metadata_hook is not None
        self._metadata_hook(
            RequestMetadata(
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

    def close(self) -> None:
        if self._closed:
            return
        for client in {self._app, *self._clients.values()}:
            client.__exit__(None, None, None)
        self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
