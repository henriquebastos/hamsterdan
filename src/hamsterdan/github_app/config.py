"""Strict, single-registration GitHub App host configuration."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path

MAX_SECRET_BYTES = 64 * 1024


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


def _secret_file(value: str | None, label: str) -> str:
    if not value:
        raise ConfigurationError(f"{label} file is missing")
    path = Path(value)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ConfigurationError(f"{label} file is not a regular file")
        if info.st_mode & 0o077:
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
    try:
        secret = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise ConfigurationError(f"{label} file is not valid text") from None
    if not secret:
        raise ConfigurationError(f"{label} file is empty")
    return secret


class HostConfig:
    """Immutable host-owned configuration; credential repr is always redacted."""

    app_id: int
    app_slug: str
    client_id: str
    account_id: int
    account_login: str
    allowed_repositories: frozenset[tuple[int, str]]
    state_path: Path
    _private_key: str
    _webhook_secret: str
    _locked: bool

    __slots__ = (
        "_locked",
        "_private_key",
        "_webhook_secret",
        "account_id",
        "account_login",
        "allowed_repositories",
        "app_id",
        "app_slug",
        "client_id",
        "state_path",
    )

    def __init__(
        self,
        *,
        app_id: int,
        app_slug: str,
        client_id: str,
        account_id: int,
        account_login: str,
        allowed_repositories: frozenset[tuple[int, str]],
        state_path: Path,
        private_key: str,
        webhook_secret: str,
    ) -> None:
        object.__setattr__(self, "app_id", app_id)
        object.__setattr__(self, "app_slug", app_slug.casefold())
        object.__setattr__(self, "client_id", client_id)
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "account_login", account_login)
        object.__setattr__(self, "allowed_repositories", allowed_repositories)
        object.__setattr__(self, "state_path", state_path)
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
        repositories: set[tuple[int, str]] = set()
        raw = env.get("HAMSTERDAN_ALLOWED_REPOSITORIES", "")
        for entry in raw.split(","):
            try:
                repository_id, full_name = entry.strip().split(":", 1)
            except ValueError:
                raise ConfigurationError("allowed repositories are malformed") from None
            identifier = _positive_decimal(repository_id, "repository id")
            if full_name.count("/") != 1 or not full_name.isascii() or not full_name.isprintable():
                raise ConfigurationError("repository name is malformed")
            repositories.add((identifier, full_name.lower()))
        if not repositories:
            raise ConfigurationError("allowed repositories are missing")
        state_path = Path(env.get("HAMSTERDAN_STATE_PATH", ""))
        if not str(state_path) or state_path == Path("."):
            raise ConfigurationError("state path is missing")
        return cls(
            app_id=_positive_decimal(env.get("HAMSTERDAN_GITHUB_APP_ID"), "App id"),
            app_slug=_slug(env.get("HAMSTERDAN_GITHUB_APP_SLUG")),
            client_id=_identifier(env.get("HAMSTERDAN_GITHUB_CLIENT_ID"), "client id"),
            account_id=_positive_decimal(env.get("HAMSTERDAN_GITHUB_ACCOUNT_ID"), "account id"),
            account_login=_identifier(env.get("HAMSTERDAN_GITHUB_ACCOUNT_LOGIN"), "account login"),
            allowed_repositories=frozenset(repositories),
            state_path=state_path,
            private_key=_secret_file(env.get("HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE"), "private key"),
            webhook_secret=_secret_file(env.get("HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE"), "webhook secret"),
        )

    def _credentials(self) -> tuple[str, str]:
        return self._private_key, self._webhook_secret

    @property
    def bot_login(self) -> str:
        return f"{self.app_slug}[bot]"

    def __repr__(self) -> str:
        return (
            f"HostConfig(app_id={self.app_id!r}, app_slug={self.app_slug!r}, client_id=<redacted>, account_id={self.account_id!r}, "
            f"account_login={self.account_login!r}, allowed_repositories={self.allowed_repositories!r}, "
            f"state_path={self.state_path!r}, credentials=<redacted>)"
        )
