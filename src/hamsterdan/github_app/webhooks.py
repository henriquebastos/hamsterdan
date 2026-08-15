"""Authenticated, sanitized, durable webhook inbox."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from githubkit.webhooks import verify

from hamsterdan.contracts.readiness import AdmittedConversation

from .routing import InstallationRegistry

MAX_BODY_BYTES = 1_048_576
MAX_COMMENT_BYTES = 16_384
MAX_DELIVERY_ATTEMPTS = 20
MAX_RETRY_DELAY_SECONDS = 300
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


def admit_conversation(
    item: Observation,
    *,
    app_slug: str,
    bot_login: str,
) -> AdmittedConversation | None:
    """Admit one provider comment and return only neutral conversation values."""
    if (
        not isinstance(item.delivery_id, str)
        or (item.comment_id is not None and type(item.comment_id) is not int)
        or (item.actor_id is not None and type(item.actor_id) is not int)
        or (item.comment_body is not None and not isinstance(item.comment_body, str))
        or (item.actor_login is not None and not isinstance(item.actor_login, str))
        or (item.actor_type is not None and not isinstance(item.actor_type, str))
        or (item.author_association is not None and not isinstance(item.author_association, str))
    ):
        return None
    text = (item.comment_body or "").strip()
    mention = f"@{app_slug}"
    folded = text.casefold()
    if (
        item.event != "issue_comment"
        or item.action != "created"
        or (item.actor_login or "").strip().casefold() == bot_login.strip().casefold()
        or item.actor_type != "User"
        or (item.author_association or "").upper() not in {"OWNER", "MEMBER", "COLLABORATOR"}
        or not (folded == mention.casefold() or folded.startswith(mention.casefold() + " "))
    ):
        return None
    addressed = "" if folded == mention.casefold() else text[len(mention) + 1 :].lstrip()
    return AdmittedConversation(
        delivery_id=item.delivery_id,
        comment_id=item.comment_id or 0,
        actor_id=item.actor_id or 0,
        actor_login=item.actor_login or "",
        association=item.author_association or "",
        text=addressed,
    )


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
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret, self._registry, self._maximum = webhook_secret, registry, maximum_body_bytes
        self._clock = clock
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self._db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS inbox (
            delivery_id TEXT PRIMARY KEY, event TEXT NOT NULL, observation TEXT NOT NULL,
            status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            reason TEXT, error_class TEXT, next_attempt_at REAL NOT NULL DEFAULT 0);
        """)
        columns = {str(row[1]) for row in self._db.execute("PRAGMA table_info(inbox)")}
        if "next_attempt_at" not in columns:
            with self._db:
                self._db.execute("ALTER TABLE inbox ADD COLUMN next_attempt_at REAL NOT NULL DEFAULT 0")

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

    def pending(
        self,
        limit: int = 100,
        *,
        subject: tuple[int, int, int] | None = None,
    ) -> tuple[Observation, ...]:
        limit = max(1, min(limit, 1000))
        now = self._clock()
        where = "status='pending' AND next_attempt_at<=?"
        parameters: tuple[object, ...] = (now, limit)
        if subject is not None:
            # Per-subject processing is strict row order. An earlier
            # deferred failure fences every later observation for that
            # PR until its exact manifest/History delivery can replay.
            where = (
                "status='pending' AND json_extract(observation,'$.installation_id')=?"
                " AND json_extract(observation,'$.repository_id')=?"
                " AND json_extract(observation,'$.pull_request_number')=?"
            )
            parameters = (*subject, limit)
        with self._lock:
            rows = self._db.execute(
                f"SELECT observation,attempts,next_attempt_at FROM inbox WHERE {where} ORDER BY rowid LIMIT ?",
                parameters,
            ).fetchall()
        if subject is not None:
            due = []
            for row in rows:
                if float(row[2]) > now:
                    break
                due.append(row)
            rows = due
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
            for raw, attempts, _next_attempt_at in rows
        )

    def has_pending(self, *, subject: tuple[int, int, int]) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM inbox WHERE status='pending'"
                " AND json_extract(observation,'$.installation_id')=?"
                " AND json_extract(observation,'$.repository_id')=?"
                " AND json_extract(observation,'$.pull_request_number')=? LIMIT 1",
                subject,
            ).fetchone()
        return row is not None

    def eligible(self, delivery_id: str, *, subject: tuple[int, int, int]) -> bool:
        """Whether a custodied delivery is the due head of its PR row order.

        Uncustodied observations remain eligible for direct test and
        operator activation compatibility. A known terminal or later
        pending delivery can never bypass the earliest pending row.
        """
        now = self._clock()
        with self._lock:
            target = self._db.execute(
                "SELECT status FROM inbox WHERE delivery_id=?",
                (delivery_id,),
            ).fetchone()
            if target is None:
                return True
            if target[0] != "pending":
                return False
            earliest = self._db.execute(
                "SELECT delivery_id,next_attempt_at FROM inbox WHERE status='pending'"
                " AND json_extract(observation,'$.installation_id')=?"
                " AND json_extract(observation,'$.repository_id')=?"
                " AND json_extract(observation,'$.pull_request_number')=?"
                " ORDER BY rowid LIMIT 1",
                subject,
            ).fetchone()
        return earliest is not None and earliest[0] == delivery_id and float(earliest[1]) <= now

    def acknowledge(self, delivery_id: str, reason: str = "processed") -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE inbox SET status='terminal',reason=?,error_class=NULL WHERE delivery_id=?",
                (reason[:256], delivery_id),
            )

    def retry(self, delivery_id: str, error: BaseException) -> None:
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT attempts FROM inbox WHERE delivery_id=? AND status='pending'", (delivery_id,)
            ).fetchone()
            if row is None:
                return
            attempts = int(row[0]) + 1
            if attempts >= MAX_DELIVERY_ATTEMPTS:
                self._db.execute(
                    "UPDATE inbox SET status='failed',attempts=?,reason='attempts exhausted',error_class=? "
                    "WHERE delivery_id=? AND status='pending'",
                    (attempts, type(error).__name__[:128], delivery_id),
                )
                return
            delay = min(2 ** (attempts - 1), MAX_RETRY_DELAY_SECONDS)
            self._db.execute(
                "UPDATE inbox SET attempts=?,next_attempt_at=?,error_class=? WHERE delivery_id=? AND status='pending'",
                (attempts, self._clock() + delay, type(error).__name__[:128], delivery_id),
            )

    def status(self, delivery_id: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT status FROM inbox WHERE delivery_id=?", (delivery_id,)).fetchone()
        return None if row is None else row[0]

    def counts(self) -> dict[str, int]:
        return {
            str(status): int(count)
            for status, count in self._db.execute("SELECT status,count(*) FROM inbox GROUP BY status")
        }

    def failures(self, limit: int = 100) -> tuple[dict[str, object], ...]:
        limit = max(1, min(limit, 1000))
        with self._lock:
            rows = self._db.execute(
                "SELECT delivery_id,event,attempts,error_class,reason FROM inbox "
                "WHERE status='failed' ORDER BY rowid LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            {
                "delivery_id": str(delivery_id),
                "event": str(event),
                "attempts": int(attempts),
                "error_class": None if error_class is None else str(error_class),
                "reason": None if reason is None else str(reason),
            }
            for delivery_id, event, attempts, error_class, reason in rows
        )

    def requeue(self, delivery_id: str) -> bool:
        try:
            canonical = str(uuid.UUID(delivery_id))
        except ValueError:
            return False
        if canonical != delivery_id:
            return False
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE inbox SET status='pending',attempts=0,next_attempt_at=0,reason=NULL,error_class=NULL "
                "WHERE delivery_id=? AND status='failed'",
                (delivery_id,),
            )
        return cursor.rowcount == 1

    def close(self) -> None:
        self._db.close()
