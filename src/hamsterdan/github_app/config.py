"""Strict, single-registration GitHub App host configuration."""

from __future__ import annotations

import os
import re
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

MAX_SECRET_BYTES = 64 * 1024
_ACCOUNT_LOGIN = re.compile(r"[A-Za-z0-9-]{1,39}")
_REPOSITORY_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_RETIRED_INSTALLATION_ENVIRONMENT = {
    "HAMSTERDAN_ALLOWED_REPOSITORIES",
    "HAMSTERDAN_GITHUB_ACCOUNT_ID",
    "HAMSTERDAN_GITHUB_ACCOUNT_LOGIN",
}


class ConfigurationError(ValueError):
    """A configuration failure that never includes a secret value."""


def _positive_decimal(value: str | None, label: str) -> int:
    if value is None or not value.isascii() or not value.isdecimal() or value.startswith("0"):
        raise ConfigurationError(f"{label} is missing or malformed")
    result = int(value)
    if result <= 0:
        raise ConfigurationError(f"{label} is missing or malformed")
    return result


def _identifier(value: str | None, label: str) -> str:
    if value is None or not 1 <= len(value) <= 128 or not value.isascii() or not value.isprintable():
        raise ConfigurationError(f"{label} is missing or malformed")
    return value


def _slug(value: str | None) -> str:
    slug = "" if value is None else value.casefold()
    if (
        not 1 <= len(slug) <= 100
        or not slug.isascii()
        or any(not (character.isalnum() or character == "-") for character in slug)
        or slug.startswith("-")
        or slug.endswith("-")
    ):
        raise ConfigurationError("App slug is missing or malformed")
    return slug


def _watched_authors(value: str | None) -> frozenset[str]:
    if value is None or not value.strip():
        return frozenset()
    logins = frozenset(part.strip().casefold() for part in value.split(","))
    if any(_ACCOUNT_LOGIN.fullmatch(login) is None for login in logins):
        raise ConfigurationError("watched authors are malformed")
    return logins


def _bounded_file(value: str | None, label: str, *, forbidden_mode: int) -> bytes:
    if not value:
        raise ConfigurationError(f"{label} file is missing")
    path = Path(value)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ConfigurationError(f"{label} file is not a regular file")
        if info.st_mode & forbidden_mode:
            raise ConfigurationError(f"{label} file permissions are too broad")
        if not 0 < info.st_size <= MAX_SECRET_BYTES:
            raise ConfigurationError(f"{label} file size is not admitted")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            current = os.fstat(descriptor)
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino) or not stat.S_ISREG(current.st_mode):
                raise ConfigurationError(f"{label} file changed while opening")
            raw = os.read(descriptor, MAX_SECRET_BYTES + 1)
        finally:
            os.close(descriptor)
    except ConfigurationError:
        raise
    except OSError:
        raise ConfigurationError(f"{label} file cannot be read safely") from None
    if not raw or len(raw) > MAX_SECRET_BYTES:
        raise ConfigurationError(f"{label} file size is not admitted")
    return raw


def _secret_file(value: str | None, label: str) -> str:
    raw = _bounded_file(value, label, forbidden_mode=0o077)
    try:
        secret = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise ConfigurationError(f"{label} file is not valid text") from None
    if not secret:
        raise ConfigurationError(f"{label} file is empty")
    return secret


@dataclass(frozen=True)
class AccountConfig:
    account_id: int
    account_login: str
    repositories: tuple[tuple[int, str], ...]


def _repository(value: object, *, account_login: str) -> tuple[int, str]:
    if not isinstance(value, str):
        raise ConfigurationError("installation repositories are malformed")
    try:
        identifier_text, full_name = value.split(":", 1)
    except ValueError:
        raise ConfigurationError("installation repositories are malformed") from None
    identifier = _positive_decimal(identifier_text, "repository id")
    if (
        _REPOSITORY_NAME.fullmatch(full_name) is None
        or full_name.split("/", 1)[0].casefold() != account_login.casefold()
    ):
        raise ConfigurationError("installation repositories are malformed")
    return identifier, full_name.casefold()


def installation_accounts(path: str | Path) -> tuple[AccountConfig, ...]:
    """Read one strict, complete installation configuration snapshot."""
    raw = _bounded_file(str(path), "GitHub installations", forbidden_mode=0o022)
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, tomllib.TOMLDecodeError:
        raise ConfigurationError("GitHub installations file is malformed") from None
    if set(document) != {"accounts"} or not isinstance(document["accounts"], list) or not document["accounts"]:
        raise ConfigurationError("GitHub installations file is malformed")

    accounts: list[AccountConfig] = []
    account_ids: set[int] = set()
    account_logins: set[str] = set()
    repository_ids: set[int] = set()
    repository_names: set[str] = set()
    for value in document["accounts"]:
        if not isinstance(value, dict) or set(value) != {"id", "login", "repositories"}:
            raise ConfigurationError("GitHub installations file is malformed")
        account_id, account_login, raw_repositories = value["id"], value["login"], value["repositories"]
        if (
            type(account_id) is not int
            or account_id <= 0
            or not isinstance(account_login, str)
            or _ACCOUNT_LOGIN.fullmatch(account_login) is None
            or not isinstance(raw_repositories, list)
            or not raw_repositories
        ):
            raise ConfigurationError("GitHub installations file is malformed")
        canonical_login = account_login.casefold()
        if account_id in account_ids or canonical_login in account_logins:
            raise ConfigurationError("GitHub installation accounts are duplicated")
        repositories = tuple(sorted(_repository(item, account_login=account_login) for item in raw_repositories))
        current_ids = {item[0] for item in repositories}
        current_names = {item[1] for item in repositories}
        if (
            len(current_ids) != len(repositories)
            or len(current_names) != len(repositories)
            or current_ids & repository_ids
            or current_names & repository_names
        ):
            raise ConfigurationError("GitHub installation repositories are duplicated")
        account_ids.add(account_id)
        account_logins.add(canonical_login)
        repository_ids.update(current_ids)
        repository_names.update(current_names)
        accounts.append(AccountConfig(account_id, account_login, repositories))
    return tuple(sorted(accounts, key=lambda item: item.account_id))


class HostConfig:
    """Immutable host-owned configuration; credential repr is always redacted."""

    app_id: int
    app_slug: str
    client_id: str
    accounts: tuple[AccountConfig, ...]
    state_path: Path
    watched_authors: frozenset[str]
    _private_key: str
    _webhook_secret: str
    _locked: bool

    __slots__ = (
        "_locked",
        "_private_key",
        "_webhook_secret",
        "accounts",
        "app_id",
        "app_slug",
        "client_id",
        "state_path",
        "watched_authors",
    )

    def __init__(
        self,
        *,
        app_id: int,
        app_slug: str,
        client_id: str,
        accounts: tuple[AccountConfig, ...],
        state_path: Path,
        private_key: str,
        webhook_secret: str,
        watched_authors: frozenset[str] = frozenset(),
    ) -> None:
        object.__setattr__(self, "app_id", app_id)
        object.__setattr__(self, "app_slug", app_slug.casefold())
        object.__setattr__(self, "client_id", client_id)
        object.__setattr__(self, "accounts", accounts)
        object.__setattr__(self, "state_path", state_path)
        object.__setattr__(self, "watched_authors", watched_authors)
        object.__setattr__(self, "_private_key", private_key)
        object.__setattr__(self, "_webhook_secret", webhook_secret)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("HostConfig is immutable")
        object.__setattr__(self, name, value)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> HostConfig:
        env = os.environ if environment is None else environment
        if _RETIRED_INSTALLATION_ENVIRONMENT & env.keys():
            raise ConfigurationError("retired single-account configuration is present")
        state_path = Path(env.get("HAMSTERDAN_STATE_PATH", ""))
        if not str(state_path) or state_path == Path("."):
            raise ConfigurationError("state path is missing")
        return cls(
            app_id=_positive_decimal(env.get("HAMSTERDAN_GITHUB_APP_ID"), "App id"),
            app_slug=_slug(env.get("HAMSTERDAN_GITHUB_APP_SLUG")),
            client_id=_identifier(env.get("HAMSTERDAN_GITHUB_CLIENT_ID"), "client id"),
            accounts=installation_accounts(env.get("HAMSTERDAN_GITHUB_INSTALLATIONS_FILE", "")),
            state_path=state_path,
            private_key=_secret_file(env.get("HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE"), "private key"),
            webhook_secret=_secret_file(env.get("HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE"), "webhook secret"),
            watched_authors=_watched_authors(env.get("HAMSTERDAN_WATCH_AUTHORS")),
        )

    def _credentials(self) -> tuple[str, str]:
        return self._private_key, self._webhook_secret

    @property
    def bot_login(self) -> str:
        return f"{self.app_slug}[bot]"

    def __repr__(self) -> str:
        return (
            f"HostConfig(app_id={self.app_id!r}, app_slug={self.app_slug!r}, client_id=<redacted>, "
            f"accounts={self.accounts!r}, watched_authors={self.watched_authors!r}, "
            f"state_path={self.state_path!r}, credentials=<redacted>)"
        )
