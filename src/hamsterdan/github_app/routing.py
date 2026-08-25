"""Durable admission routing for configured installation accounts."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from .config import AccountConfig
from .models import InstallationInventory


@dataclass(frozen=True)
class Route:
    installation_id: int
    account_id: int
    repository_id: int
    repository_full_name: str


class InstallationRegistry:
    def __init__(self, path: Path, *, accounts: tuple[AccountConfig, ...]) -> None:
        self._allowed = {account.account_id: dict(account.repositories) for account in accounts}
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self._db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS installations (
              installation_id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, active INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS repositories (
              installation_id INTEGER NOT NULL, repository_id INTEGER NOT NULL, full_name TEXT NOT NULL,
              active INTEGER NOT NULL, PRIMARY KEY (installation_id, repository_id));
        """)

    def installation(self, action: str, installation_id: int, account_id: int) -> bool:
        if not self._valid_id(installation_id) or not self._valid_id(account_id) or account_id not in self._allowed:
            return False
        with self._lock, self._db:
            existing = self._db.execute(
                "SELECT account_id FROM installations WHERE installation_id=?", (installation_id,)
            ).fetchone()
            if existing is not None and existing[0] != account_id:
                return False
            if action in {"created", "unsuspend", "new_permissions_accepted"}:
                self._db.execute(
                    "DELETE FROM repositories WHERE installation_id IN "
                    "(SELECT installation_id FROM installations WHERE account_id=? AND installation_id<>?)",
                    (account_id, installation_id),
                )
                self._db.execute(
                    "DELETE FROM installations WHERE account_id=? AND installation_id<>?",
                    (account_id, installation_id),
                )
                self._db.execute(
                    "INSERT INTO installations VALUES (?, ?, 1) ON CONFLICT(installation_id) DO UPDATE SET account_id=excluded.account_id, active=1",
                    (installation_id, account_id),
                )
            elif action == "suspend":
                self._db.execute(
                    "UPDATE installations SET active=0 WHERE installation_id=? AND account_id=?",
                    (installation_id, account_id),
                )
            elif action == "deleted":
                self._db.execute(
                    "DELETE FROM repositories WHERE installation_id IN "
                    "(SELECT installation_id FROM installations WHERE installation_id=? AND account_id=?)",
                    (installation_id, account_id),
                )
                self._db.execute(
                    "DELETE FROM installations WHERE installation_id=? AND account_id=?", (installation_id, account_id)
                )
            else:
                return False
        return True

    def repositories(
        self, action: str, installation_id: int, account_id: int, repositories: tuple[tuple[int, str], ...]
    ) -> bool:
        if (
            action not in {"added", "removed"}
            or not self._valid_id(installation_id)
            or not self._valid_id(account_id)
            or account_id not in self._allowed
            or any(not self._valid_repository(item) for item in repositories)
        ):
            return False
        with self._lock, self._db:
            if not self._installation_exists(installation_id, account_id):
                return False
            for repository_id, full_name in repositories:
                admitted_name = self._allowed[account_id].get(repository_id)
                if action == "added" and admitted_name == full_name.lower():
                    self._db.execute(
                        "INSERT INTO repositories VALUES (?, ?, ?, 1) ON CONFLICT(installation_id, repository_id) DO UPDATE SET full_name=excluded.full_name, active=1",
                        (installation_id, repository_id, full_name.lower()),
                    )
                elif action == "removed":
                    self._db.execute(
                        "DELETE FROM repositories WHERE installation_id=? AND repository_id=?",
                        (installation_id, repository_id),
                    )
        return True

    @staticmethod
    def _valid_id(value: object) -> bool:
        return type(value) is int and value > 0

    @classmethod
    def _valid_repository(cls, value: tuple[int, str]) -> bool:
        repository_id, full_name = value
        return (
            cls._valid_id(repository_id)
            and type(full_name) is str
            and 1 <= len(full_name) <= 201
            and full_name.isascii()
            and full_name.isprintable()
            and full_name.count("/") == 1
            and all(part and part.strip() == part for part in full_name.split("/"))
        )

    def _installation_exists(self, installation_id: int, account_id: int) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM installations WHERE installation_id=? AND account_id=?", (installation_id, account_id)
        ).fetchone()
        return row is not None

    def route(self, installation_id: int, repository_id: int) -> Route | None:
        with self._lock:
            row = self._db.execute(
                "SELECT i.account_id, r.full_name FROM installations i JOIN repositories r USING (installation_id) "
                "WHERE i.installation_id=? AND r.repository_id=? AND i.active=1 AND r.active=1",
                (installation_id, repository_id),
            ).fetchone()
        return None if row is None else Route(installation_id, row[0], repository_id, row[1])

    def reconcile(self, installations: tuple[InstallationInventory, ...]) -> int:
        """Atomically replace every configured installation and repository route."""
        if (
            len({item.installation_id for item in installations}) != len(installations)
            or len({item.account_id for item in installations}) != len(installations)
            or {item.account_id for item in installations} != self._allowed.keys()
        ):
            raise ValueError("registration inventory does not match configured accounts")
        admitted: list[tuple[int, int, int, str]] = []
        for installation in installations:
            if not self._valid_id(installation.installation_id):
                raise ValueError("registration inventory is malformed")
            observed = {
                repository_id: full_name.lower()
                for repository_id, full_name in installation.repositories
                if self._valid_repository((repository_id, full_name))
            }
            allowed = self._allowed[installation.account_id]
            if any(observed.get(repository_id) != full_name for repository_id, full_name in allowed.items()):
                raise ValueError("registration inventory does not contain every configured repository")
            admitted.extend(
                (installation.installation_id, installation.account_id, repository_id, full_name)
                for repository_id, full_name in allowed.items()
            )
        with self._lock, self._db:
            self._db.execute("DELETE FROM repositories")
            self._db.execute("DELETE FROM installations")
            self._db.executemany(
                "INSERT INTO installations VALUES (?, ?, 1)",
                ((item.installation_id, item.account_id) for item in installations),
            )
            self._db.executemany(
                "INSERT INTO repositories VALUES (?, ?, ?, 1)",
                (
                    (installation_id, repository_id, full_name)
                    for installation_id, _, repository_id, full_name in admitted
                ),
            )
        return len(admitted)

    def active_count(self) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT count(*) FROM repositories r JOIN installations i USING(installation_id) "
                "WHERE r.active=1 AND i.active=1"
            ).fetchone()
        return int(row[0])

    def active_installation_count(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT count(*) FROM installations WHERE active=1").fetchone()
        return int(row[0])

    def close(self) -> None:
        with self._lock:
            self._db.close()
