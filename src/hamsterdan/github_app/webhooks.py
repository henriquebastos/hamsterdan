"""Authenticated, sanitized, durable webhook inbox."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from githubkit.webhooks import verify

from .routing import InstallationRegistry

MAX_BODY_BYTES = 1_048_576
MAX_COMMENT_BYTES = 16_384
SUPPORTED_EVENTS = frozenset(
    {
        "installation",
        "installation_repositories",
        "pull_request",
        "issues",
        "issue_comment",
        "pull_request_review",
        "pull_request_review_comment",
        "workflow_run",
        "check_run",
        "check_suite",
        "ping",
    }
)
_SIGNATURE = re.compile(r"sha256=[0-9a-f]{64}\Z")


class WebhookRejected(ValueError):
    pass


@dataclass(frozen=True)
class Observation:
    delivery_id: str
    event: str
    action: str | None
    installation_id: int | None
    account_id: int | None
    repository_id: int | None
    repository_full_name: str | None
    pull_request_number: int | None = None
    comment_id: int | None = None
    comment_body: str | None = None
    actor_id: int | None = None
    actor_login: str | None = None
    actor_type: str | None = None
    author_association: str | None = None
    repositories: tuple[tuple[int, str], ...] = ()
    attempts: int = 0


@dataclass(frozen=True)
class Receipt:
    delivery_id: str
    disposition: str
    observation: Observation | None = None


def _headers(entries: Iterable[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    protected = {
        "content-length",
        "content-type",
        "transfer-encoding",
        "x-hub-signature-256",
        "x-github-delivery",
        "x-github-event",
    }
    for name, value in entries:
        key = name.lower()
        if key in protected and key in result:
            raise WebhookRejected("duplicate security header")
        result[key] = value.strip()
    if "transfer-encoding" in result:
        raise WebhookRejected("transfer encoding is not accepted")
    return result


class WebhookCustody:
    def __init__(
        self,
        path: Path,
        *,
        webhook_secret: str,
        registry: InstallationRegistry | None = None,
        maximum_body_bytes: int = MAX_BODY_BYTES,
    ) -> None:
        self._secret, self._registry, self._maximum = webhook_secret, registry, maximum_body_bytes
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self._db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS inbox (
            delivery_id TEXT PRIMARY KEY, event TEXT NOT NULL, observation TEXT NOT NULL,
            status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            reason TEXT, error_class TEXT);
        """)

    def receive(self, headers: Iterable[tuple[str, str]], body: bytes) -> Receipt:
        projected = _headers(headers)
        length, signature = projected.get("content-length"), projected.get("x-hub-signature-256")
        if length is None or not length.isascii() or not length.isdecimal() or int(length) != len(body):
            raise WebhookRejected("content length is missing or invalid")
        if len(body) > self._maximum:
            raise WebhookRejected("request body is too large")
        if projected.get("content-type") != "application/json":
            raise WebhookRejected("content type is missing or unsupported")
        if signature is None or _SIGNATURE.fullmatch(signature) is None:
            raise WebhookRejected("sha256 signature is missing or malformed")
        delivery, event = projected.get("x-github-delivery"), projected.get("x-github-event")
        if any(len(projected.get(name, "")) > 256 for name in ("x-github-delivery", "x-github-event", "content-type")):
            raise WebhookRejected("security header is too large")
        try:
            delivery = str(uuid.UUID(delivery)) if delivery else ""
        except ValueError:
            raise WebhookRejected("delivery id is malformed") from None
        if not delivery or event not in SUPPORTED_EVENTS:
            raise WebhookRejected("delivery or event is missing or unsupported")
        if not verify(self._secret, body, signature):
            raise WebhookRejected("signature verification failed")
        try:
            observation = self._parse(delivery, event, body)
        except json.JSONDecodeError, KeyError, TypeError, ValueError:
            raise WebhookRejected("webhook envelope is malformed") from None
        encoded = json.dumps(asdict(observation), separators=(",", ":"), sort_keys=True)
        with self._lock, self._db:
            try:
                self._db.execute(
                    "INSERT INTO inbox(delivery_id,event,observation,status) VALUES(?,?,?,'pending')",
                    (delivery, event, encoded),
                )
            except sqlite3.IntegrityError:
                return Receipt(delivery, "duplicate")
            if event in {"installation", "installation_repositories"}:
                self._apply_lifecycle(observation)
                self._db.execute(
                    "UPDATE inbox SET status='terminal',reason='routing lifecycle applied' WHERE delivery_id=?",
                    (delivery,),
                )
                return Receipt(delivery, "accepted_terminal", observation)
        return Receipt(delivery, "accepted", observation)

    def _parse(self, delivery: str, event: str, body: bytes) -> Observation:
        value: Any = json.loads(body)
        if type(value) is not dict:
            raise ValueError
        installation, repository = value.get("installation") or {}, value.get("repository") or {}
        account, pull, issue, comment = (
            installation.get("account") or {},
            value.get("pull_request") or {},
            value.get("issue") or {},
            value.get("comment") or {},
        )
        actor = comment.get("user") or value.get("sender") or {}
        number = pull.get("number")
        if event == "issue_comment" and issue.get("pull_request") is not None:
            number = issue.get("number")
        elif event in {"workflow_run", "check_run", "check_suite"}:
            pulls = (value.get(event) or {}).get("pull_requests") or []
            number = pulls[0].get("number") if pulls else None
        source = value.get("repositories", [])
        if event == "installation_repositories":
            source = value.get("repositories_added" if value.get("action") == "added" else "repositories_removed", [])
        repositories = tuple((item["id"], item["full_name"]) for item in source)
        text = comment.get("body") if event == "issue_comment" else None
        if text is not None and (not isinstance(text, str) or len(text.encode()) > MAX_COMMENT_BYTES):
            raise ValueError
        return Observation(
            delivery,
            event,
            value.get("action"),
            installation.get("id"),
            account.get("id"),
            repository.get("id"),
            repository.get("full_name"),
            number,
            comment.get("id") if event == "issue_comment" else None,
            text,
            actor.get("id") if event == "issue_comment" else None,
            actor.get("login") if event == "issue_comment" else None,
            actor.get("type") if event == "issue_comment" else None,
            comment.get("author_association") if event == "issue_comment" else None,
            repositories,
        )

    def _apply_lifecycle(self, item: Observation) -> None:
        if self._registry is None or item.installation_id is None or item.account_id is None or item.action is None:
            return
        if item.event == "installation":
            applied = self._registry.installation(item.action, item.installation_id, item.account_id)
            if applied and item.action == "created":
                self._registry.repositories("added", item.installation_id, item.account_id, item.repositories)
        else:
            self._registry.repositories(item.action, item.installation_id, item.account_id, item.repositories)

    def pending(self, limit: int = 100) -> tuple[Observation, ...]:
        limit = max(1, min(limit, 1000))
        with self._lock:
            rows = self._db.execute(
                "SELECT observation,attempts FROM inbox WHERE status='pending' ORDER BY rowid LIMIT ?", (limit,)
            ).fetchall()
        return tuple(
            Observation(
                **(
                    json.loads(raw)
                    | {
                        "repositories": tuple(tuple(x) for x in json.loads(raw).get("repositories", ())),
                        "attempts": attempts,
                    }
                )
            )
            for raw, attempts in rows
        )

    def acknowledge(self, delivery_id: str, reason: str = "processed") -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE inbox SET status='terminal',reason=?,error_class=NULL WHERE delivery_id=?",
                (reason[:256], delivery_id),
            )

    def retry(self, delivery_id: str, error: BaseException) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE inbox SET attempts=attempts+1,error_class=? WHERE delivery_id=?",
                (type(error).__name__[:128], delivery_id),
            )

    def status(self, delivery_id: str) -> str | None:
        row = self._db.execute("SELECT status FROM inbox WHERE delivery_id=?", (delivery_id,)).fetchone()
        return None if row is None else row[0]

    def counts(self) -> dict[str, int]:
        return {
            str(status): int(count)
            for status, count in self._db.execute("SELECT status,count(*) FROM inbox GROUP BY status")
        }

    def close(self) -> None:
        self._db.close()
