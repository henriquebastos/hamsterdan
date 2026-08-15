"""Canonical, restart-safe host custody for V5 reminder timers."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from pydantic import TypeAdapter, ValidationError

from hamsterdan.contracts.readiness_v5 import (
    ArmReminder,
    CancelReminder,
    ReminderTimer,
    TimerArmed,
    TimerCancelled,
    TimerCommand,
    TimerCommandApplied,
    TimerDue,
)

_SCHEMA_VERSION = 1
_MAX_DELAY = 2_147_483_647
_MAX_I64 = 2**63 - 1
_MIN_I64 = -(2**63)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SCHEMA_COLUMNS = {
    "v5_timer_meta": (
        (0, "singleton", "INTEGER", 0, None, 1),
        (1, "schema_version", "INTEGER", 1, None, 0),
        (2, "topology", "TEXT", 1, None, 0),
        (3, "subject", "TEXT", 1, None, 0),
        (4, "last_generation", "INTEGER", 1, None, 0),
    ),
    "v5_timer_operations": (
        (0, "operation", "TEXT", 0, None, 1),
        (1, "subject", "TEXT", 1, None, 0),
        (2, "generation", "INTEGER", 1, None, 0),
        (3, "command_json", "TEXT", 1, None, 0),
        (4, "result_json", "TEXT", 1, None, 0),
        (5, "ack_identity", "TEXT", 1, None, 0),
        (6, "applied_at_us", "INTEGER", 1, None, 0),
        (7, "ack_delivered", "INTEGER", 1, "0", 0),
    ),
    "v5_timers": (
        (0, "timer_id", "TEXT", 0, None, 1),
        (1, "subject", "TEXT", 1, None, 0),
        (2, "incarnation", "INTEGER", 1, None, 0),
        (3, "sequence", "INTEGER", 1, None, 0),
        (4, "head", "TEXT", 1, None, 0),
        (5, "due_at_us", "INTEGER", 1, None, 0),
        (6, "arm_operation", "TEXT", 1, None, 0),
        (7, "state", "TEXT", 1, None, 0),
        (8, "terminal_operation", "TEXT", 0, None, 0),
        (9, "matured_at_us", "INTEGER", 0, None, 0),
        (10, "maturity_identity", "TEXT", 0, None, 0),
        (11, "maturity_delivered", "INTEGER", 1, "0", 0),
    ),
}
_SCHEMA_INDEXES = {
    "v5_timers_one_armed": ((0, 1, "subject"),),
    "v5_timers_due": ((0, 1, "subject"), (1, 5, "due_at_us"), (2, 0, "timer_id")),
    "v5_timer_pending_acks": ((0, 1, "subject"), (1, 7, "ack_delivered"), (2, 2, "generation")),
}


@dataclass(frozen=True)
class TimerMaturity:
    value: TimerDue
    identity: str


@dataclass
class _ProjectedTimer:
    timer: ReminderTimer
    due_at_us: int
    arm_operation: str
    state: str = "armed"
    terminal_operation: str | None = None
    matured_at_us: int | None = None
    maturity_identity: str | None = None
    maturity_delivered: int = 0

    def row(self, subject: str) -> tuple[object, ...]:
        return (
            self.timer.id,
            subject,
            self.timer.incarnation,
            self.timer.sequence,
            self.timer.head,
            self.due_at_us,
            self.arm_operation,
            self.state,
            self.terminal_operation,
            self.matured_at_us,
            self.maturity_identity,
            self.maturity_delivered,
        )


def _canonical(value: object) -> str:
    payload = value.dump() if isinstance(value, (TimerCommand, TimerCommandApplied, TimerDue)) else value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _load[T](raw: object, model: type[T], label: str) -> T:
    if not isinstance(raw, str):
        raise TypeError(f"stored V5 timer {label} is malformed")
    try:
        value = TypeAdapter(model).validate_json(raw)
    except ValidationError:
        raise RuntimeError(f"stored V5 timer {label} is malformed") from None
    if _canonical(value) != raw:
        raise RuntimeError(f"stored V5 timer {label} is not canonical")
    return value


def _format_us(value: int) -> str:
    if type(value) is not int or not _MIN_I64 <= value <= _MAX_I64:
        raise ValueError("V5 timer instant is outside signed 64-bit microseconds")
    try:
        instant = _EPOCH + timedelta(microseconds=value)
    except OverflowError:
        raise ValueError("V5 timer instant is outside datetime range") from None
    return instant.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_us(value: str) -> int:
    if not isinstance(value, str):
        raise TypeError("V5 timer instant must be canonical UTC")
    try:
        instant = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError("V5 timer instant must be canonical UTC") from None
    if instant.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise ValueError("V5 timer instant must be canonical UTC")
    delta = instant - _EPOCH
    result = delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
    if not _MIN_I64 <= result <= _MAX_I64:
        raise ValueError("V5 timer instant is outside signed 64-bit microseconds")
    return result


class V5TimerStore:
    """One subject's canonical timer operation and maturation ledger."""

    def __init__(
        self,
        path: Path,
        subject: str,
        database: sqlite3.Connection,
        clock_us: Callable[[], int],
    ) -> None:
        self.path = path
        self.subject = subject
        self._db = database
        self._clock_us = clock_us
        self._lock = threading.RLock()
        self._closed = False

    @classmethod
    def open(
        cls,
        path: Path,
        subject: str,
        *,
        history: Iterable[TimerCommandApplied | TimerDue] = (),
        outstanding: TimerCommand | None = None,
        clock_us: Callable[[], int] = lambda: time.time_ns() // 1_000,
    ) -> V5TimerStore:
        cls._subject(subject)
        facts = tuple(history)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        existed = path.exists()
        unrecoverable_arm = False
        if outstanding is not None and isinstance(outstanding.command, ArmReminder):
            unrecoverable_arm = not any(
                isinstance(fact, TimerCommandApplied)
                and fact.operation == outstanding.operation
                and isinstance(fact.result, TimerArmed)
                and fact.result.timer == outstanding.command.timer
                for fact in facts
            )
        if not existed and unrecoverable_arm:
            raise RuntimeError("V5 timer store cannot recover an unacknowledged arm")
        database: sqlite3.Connection | None = None
        rebuilt = not existed
        try:
            database = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            cls._configure(database)
            if existed:
                cls._validate_schema(database, subject)
            else:
                cls._create_schema(database, subject)
        except sqlite3.DatabaseError, RuntimeError:
            if database is not None:
                database.close()
            if unrecoverable_arm:
                raise RuntimeError("V5 timer store cannot recover an unacknowledged arm") from None
            cls._quarantine(path)
            rebuilt = True
            database = None
        if database is None:
            database = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            cls._configure(database)
            cls._create_schema(database, subject)

        store = cls(path, subject, database, clock_us)
        try:
            if rebuilt:
                store._rebuild(facts)
            else:
                store._validate_contents(facts, outstanding, tolerate_pending_markers=True)
                store._reconcile_history(facts)
            store._validate_contents(facts, outstanding)
            return store
        except sqlite3.DatabaseError, RuntimeError, TypeError, ValueError:
            store.close()
            if rebuilt:
                cls._discard(path)
                raise
            if unrecoverable_arm:
                raise RuntimeError("V5 timer store cannot recover an unacknowledged arm") from None
            cls._quarantine(path)
            replacement_db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            cls._configure(replacement_db)
            cls._create_schema(replacement_db, subject)
            replacement = cls(path, subject, replacement_db, clock_us)
            try:
                replacement._rebuild(facts)
                replacement._validate_contents(facts, outstanding)
                return replacement
            except BaseException:
                replacement.close()
                cls._discard(path)
                raise

    @staticmethod
    def _subject(subject: str) -> None:
        if (
            not isinstance(subject, str)
            or not subject
            or len(subject.encode()) > 900
            or not subject.isascii()
            or not subject.isprintable()
        ):
            raise ValueError("V5 timer subject is malformed")

    @staticmethod
    def _configure(database: sqlite3.Connection) -> None:
        journal = database.execute("PRAGMA journal_mode=WAL").fetchone()
        database.execute("PRAGMA foreign_keys=ON")
        foreign_keys = database.execute("PRAGMA foreign_keys").fetchone()
        if journal != ("wal",) or foreign_keys != (1,):
            raise RuntimeError("V5 timer store could not enforce SQLite safety settings")

    @staticmethod
    def _create_schema(database: sqlite3.Connection, subject: str) -> None:
        database.executescript(
            """
            CREATE TABLE v5_timer_meta (
              singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
              schema_version INTEGER NOT NULL CHECK (schema_version = 1),
              topology TEXT NOT NULL CHECK (topology = 'v5'),
              subject TEXT NOT NULL UNIQUE,
              last_generation INTEGER NOT NULL CHECK (last_generation >= 0)
            );
            CREATE TABLE v5_timer_operations (
              operation TEXT PRIMARY KEY,
              subject TEXT NOT NULL,
              generation INTEGER NOT NULL CHECK (generation > 0),
              command_json TEXT NOT NULL,
              result_json TEXT NOT NULL,
              ack_identity TEXT NOT NULL UNIQUE,
              applied_at_us INTEGER NOT NULL,
              ack_delivered INTEGER NOT NULL DEFAULT 0 CHECK (ack_delivered IN (0, 1)),
              UNIQUE(subject, generation)
            );
            CREATE TABLE v5_timers (
              timer_id TEXT PRIMARY KEY,
              subject TEXT NOT NULL,
              incarnation INTEGER NOT NULL CHECK (incarnation >= 0),
              sequence INTEGER NOT NULL CHECK (sequence >= 0),
              head TEXT NOT NULL,
              due_at_us INTEGER NOT NULL,
              arm_operation TEXT NOT NULL,
              state TEXT NOT NULL CHECK (state IN ('armed','superseded','cancelled','matured','retired')),
              terminal_operation TEXT,
              matured_at_us INTEGER,
              maturity_identity TEXT UNIQUE,
              maturity_delivered INTEGER NOT NULL DEFAULT 0 CHECK (maturity_delivered IN (0, 1)),
              CHECK (
                (state = 'armed' AND terminal_operation IS NULL AND matured_at_us IS NULL
                  AND maturity_identity IS NULL AND maturity_delivered = 0)
                OR (state IN ('superseded','cancelled') AND terminal_operation IS NOT NULL
                  AND matured_at_us IS NULL AND maturity_identity IS NULL AND maturity_delivered = 0)
                OR (state = 'retired' AND terminal_operation IS NULL AND matured_at_us IS NULL
                  AND maturity_identity IS NULL AND maturity_delivered = 0)
                OR (state = 'matured' AND terminal_operation IS NULL AND matured_at_us IS NOT NULL
                  AND maturity_identity IS NOT NULL)
              )
            );
            CREATE UNIQUE INDEX v5_timers_one_armed ON v5_timers(subject) WHERE state='armed';
            CREATE INDEX v5_timers_due ON v5_timers(subject,due_at_us,timer_id) WHERE state='armed';
            CREATE INDEX v5_timer_pending_acks
              ON v5_timer_operations(subject,ack_delivered,generation);
            """
        )
        database.execute(
            "INSERT INTO v5_timer_meta(singleton,schema_version,topology,subject,last_generation) VALUES(1,1,'v5',?,0)",
            (subject,),
        )

    @staticmethod
    def _validate_schema(database: sqlite3.Connection, subject: str) -> None:
        if database.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise RuntimeError("V5 timer store is corrupt")
        names = {
            (kind, name)
            for kind, name in database.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        }
        expected = {
            ("table", "v5_timer_meta"),
            ("table", "v5_timer_operations"),
            ("table", "v5_timers"),
            ("index", "v5_timers_one_armed"),
            ("index", "v5_timers_due"),
            ("index", "v5_timer_pending_acks"),
        }
        if names != expected:
            raise RuntimeError("V5 timer store schema is incompatible")
        if any(
            tuple(database.execute(f"PRAGMA table_info({table})")) != columns
            for table, columns in _SCHEMA_COLUMNS.items()
        ):
            raise RuntimeError("V5 timer store schema is incompatible")
        if any(
            tuple(database.execute(f"PRAGMA index_info({index})")) != columns
            for index, columns in _SCHEMA_INDEXES.items()
        ):
            raise RuntimeError("V5 timer store schema is incompatible")
        row = database.execute(
            "SELECT schema_version,topology,subject,last_generation FROM v5_timer_meta WHERE singleton=1"
        ).fetchone()
        if (
            row is None
            or type(row[0]) is not int
            or row[0] != _SCHEMA_VERSION
            or row[1] != "v5"
            or row[2] != subject
            or type(row[3]) is not int
            or row[3] < 0
        ):
            raise RuntimeError("V5 timer store metadata is incompatible")

    @staticmethod
    def _quarantine(path: Path) -> None:
        suffixes = ("", "-wal", "-shm")
        quarantine = path.with_name(f"{path.name}.corrupt")
        sequence = 0
        while any(quarantine.with_name(quarantine.name + suffix).exists() for suffix in suffixes):
            sequence += 1
            quarantine = path.with_name(f"{path.name}.corrupt.{sequence}")
        for suffix in suffixes:
            source = path.with_name(path.name + suffix)
            if source.exists():
                os.replace(source, quarantine.with_name(quarantine.name + suffix))

    @staticmethod
    def _discard(path: Path) -> None:
        for candidate in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
            candidate.unlink(missing_ok=True)

    def _operation_generation(self, operation: str) -> int:
        match = re.fullmatch(rf"timer-command:{re.escape(self.subject)}:g([1-9][0-9]*)", operation)
        if match is None:
            raise ValueError("V5 timer operation identity is malformed")
        result = int(match.group(1))
        if result > _MAX_I64:
            raise ValueError("V5 timer operation generation is out of range")
        return result

    def _validate_timer(self, timer: ReminderTimer) -> None:
        if (
            type(timer.incarnation) is not int
            or timer.incarnation < 0
            or type(timer.sequence) is not int
            or timer.sequence < 0
            or not timer.head
            or timer.id != f"timer:{self.subject}:i{timer.incarnation}:s{timer.sequence}"
        ):
            raise ValueError("V5 timer identity is malformed")

    def apply(self, issued: TimerCommand) -> TimerCommandApplied:
        generation = self._operation_generation(issued.operation)
        self._validate_timer(issued.command.timer)
        encoded = _canonical(issued)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                existing = self._db.execute(
                    "SELECT command_json,result_json FROM v5_timer_operations WHERE operation=?",
                    (issued.operation,),
                ).fetchone()
                if existing is not None:
                    if existing[0] != encoded:
                        raise RuntimeError("timer operation has a different timer command")
                    result = _load(existing[1], TimerCommandApplied, "operation result")
                    if (
                        result.operation != issued.operation
                        or result.result.timer != issued.command.timer
                        or (isinstance(issued.command, ArmReminder) and not isinstance(result.result, TimerArmed))
                        or (
                            isinstance(issued.command, CancelReminder) and not isinstance(result.result, TimerCancelled)
                        )
                    ):
                        raise RuntimeError("stored V5 timer operation result contradicts its command")
                    self._db.execute("COMMIT")
                    return result

                (last_generation,) = self._db.execute(
                    "SELECT last_generation FROM v5_timer_meta WHERE singleton=1"
                ).fetchone()
                if generation != last_generation + 1:
                    raise RuntimeError("V5 timer operation generation is not contiguous")
                now = self._now_us()
                if isinstance(issued.command, ArmReminder):
                    delay = issued.command.delay_s
                    if type(delay) is not int or not 1 <= delay <= _MAX_DELAY:
                        raise ValueError("V5 timer arm delay must be a positive bounded integer")
                    due = now + delay * 1_000_000
                    _format_us(due)
                    result = TimerCommandApplied(
                        operation=issued.operation,
                        result=TimerArmed(
                            kind="armed",
                            timer=issued.command.timer,
                            due_at=_format_us(due),
                        ),
                    )
                    self._db.execute(
                        "UPDATE v5_timers SET state='superseded',terminal_operation=?"
                        " WHERE subject=? AND state='armed'",
                        (issued.operation, self.subject),
                    )
                    timer = issued.command.timer
                    self._db.execute(
                        "INSERT INTO v5_timers(timer_id,subject,incarnation,sequence,head,due_at_us,"
                        "arm_operation,state) VALUES(?,?,?,?,?,?,?,'armed')",
                        (timer.id, self.subject, timer.incarnation, timer.sequence, timer.head, due, issued.operation),
                    )
                elif isinstance(issued.command, CancelReminder):
                    result = TimerCommandApplied(
                        operation=issued.operation,
                        result=TimerCancelled(kind="cancelled", timer=issued.command.timer),
                    )
                    timer = issued.command.timer
                    self._db.execute(
                        "UPDATE v5_timers SET state='cancelled',terminal_operation=?"
                        " WHERE timer_id=? AND subject=? AND incarnation=? AND sequence=?"
                        " AND head=? AND state='armed'",
                        (
                            issued.operation,
                            timer.id,
                            self.subject,
                            timer.incarnation,
                            timer.sequence,
                            timer.head,
                        ),
                    )
                else:  # pragma: no cover - strict union hydration owns this
                    raise TypeError("V5 timer command variant is malformed")
                ack_identity = f"v5-timer-command-applied:{issued.operation}"
                self._db.execute(
                    "INSERT INTO v5_timer_operations(operation,subject,generation,command_json,result_json,"
                    "ack_identity,applied_at_us,ack_delivered) VALUES(?,?,?,?,?,?,?,0)",
                    (
                        issued.operation,
                        self.subject,
                        generation,
                        encoded,
                        _canonical(result),
                        ack_identity,
                        now,
                    ),
                )
                self._db.execute(
                    "UPDATE v5_timer_meta SET last_generation=? WHERE singleton=1",
                    (generation,),
                )
                self._db.execute("COMMIT")
                return result
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def _now_us(self) -> int:
        value = self._clock_us()
        if type(value) is not int or not _MIN_I64 <= value <= _MAX_I64:
            raise ValueError("V5 timer clock returned an invalid instant")
        return value

    def pending_ack(self) -> TimerCommandApplied | None:
        with self._lock:
            row = self._db.execute(
                "SELECT operation,command_json,result_json,ack_identity FROM v5_timer_operations"
                " WHERE subject=? AND ack_delivered=0 ORDER BY generation LIMIT 1",
                (self.subject,),
            ).fetchone()
        if row is None:
            return None
        command = _load(row[1], TimerCommand, "operation command")
        result = _load(row[2], TimerCommandApplied, "operation result")
        if (
            row[0] != command.operation
            or row[0] != result.operation
            or command.command.timer != result.result.timer
            or (isinstance(command.command, ArmReminder) and not isinstance(result.result, TimerArmed))
            or (isinstance(command.command, CancelReminder) and not isinstance(result.result, TimerCancelled))
            or row[3] != self.ack_identity(result.operation)
        ):
            raise RuntimeError("stored V5 timer acknowledgement is malformed")
        return result

    @staticmethod
    def ack_identity(operation: str) -> str:
        return f"v5-timer-command-applied:{operation}"

    def mark_ack_delivered(self, operation: str) -> None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._db.execute(
                    "UPDATE v5_timer_operations SET ack_delivered=1 WHERE operation=? AND subject=?",
                    (operation, self.subject),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("V5 timer acknowledgement has no operation")
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def pending_maturity(self) -> TimerMaturity | None:
        with self._lock:
            row = self._db.execute(
                "SELECT timer_id,incarnation,sequence,head,due_at_us,matured_at_us,maturity_identity"
                " FROM v5_timers WHERE subject=? AND state='matured' AND maturity_delivered=0"
                " ORDER BY matured_at_us,timer_id LIMIT 1",
                (self.subject,),
            ).fetchone()
        return None if row is None else self._maturity(row)

    def claim_due(self, now_us: int | None = None) -> TimerMaturity | None:
        now = self._now_us() if now_us is None else now_us
        if type(now) is not int or not _MIN_I64 <= now <= _MAX_I64:
            raise ValueError("V5 timer claim instant is invalid")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT timer_id,incarnation,sequence,head,due_at_us FROM v5_timers"
                    " WHERE subject=? AND state='armed' AND due_at_us<=?"
                    " ORDER BY due_at_us,timer_id LIMIT 1",
                    (self.subject, now),
                ).fetchone()
                if row is None:
                    self._db.execute("COMMIT")
                    return None
                identity = self.maturity_identity(cast(str, row[0]), cast(int, row[4]))
                self._db.execute(
                    "UPDATE v5_timers SET state='matured',matured_at_us=?,maturity_identity=?"
                    " WHERE timer_id=? AND subject=? AND state='armed'",
                    (now, identity, row[0], self.subject),
                )
                self._db.execute("COMMIT")
                return self._maturity((*row, now, identity))
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    @staticmethod
    def maturity_identity(timer_id: str, due_at_us: int) -> str:
        return f"v5-timer-due:{timer_id}:{due_at_us}"

    @classmethod
    def due_identity(cls, value: TimerDue) -> str:
        return cls.maturity_identity(value.timer.id, _parse_us(value.due_at))

    def _maturity(self, row: tuple[object, ...]) -> TimerMaturity:
        timer_id, incarnation, sequence, head, due, matured, identity = row
        if (
            not isinstance(timer_id, str)
            or type(incarnation) is not int
            or type(sequence) is not int
            or not isinstance(head, str)
            or type(due) is not int
            or type(matured) is not int
            or not isinstance(identity, str)
            or identity != self.maturity_identity(timer_id, due)
            or matured < due
        ):
            raise RuntimeError("stored V5 timer maturity is malformed")
        timer = ReminderTimer(id=timer_id, incarnation=incarnation, sequence=sequence, head=head)
        self._validate_timer(timer)
        return TimerMaturity(
            TimerDue(timer=timer, due_at=_format_us(due), matured_at=_format_us(matured)),
            identity,
        )

    def mark_maturity_delivered(self, timer_id: str) -> None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._db.execute(
                    "UPDATE v5_timers SET maturity_delivered=1 WHERE timer_id=? AND subject=? AND state='matured'",
                    (timer_id, self.subject),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("V5 timer maturity has no claimed timer")
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def next_due(self) -> float | None:
        with self._lock:
            row = self._db.execute(
                "SELECT MIN(due_at_us) FROM v5_timers WHERE subject=? AND state='armed'",
                (self.subject,),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        if type(row[0]) is not int:
            raise RuntimeError("stored V5 timer deadline is malformed")
        return row[0] / 1_000_000

    def _project_applied(
        self,
        timers: dict[str, _ProjectedTimer],
        fact: TimerCommandApplied,
    ) -> None:
        self._validate_timer(fact.result.timer)
        if isinstance(fact.result, TimerArmed):
            due = _parse_us(fact.result.due_at)
            for projected in timers.values():
                if projected.state == "armed":
                    projected.state = "superseded"
                    projected.terminal_operation = fact.operation
            if fact.result.timer.id in timers:
                raise RuntimeError("accepted V5 timer arm reuses a timer identity")
            timers[fact.result.timer.id] = _ProjectedTimer(fact.result.timer, due, fact.operation)
        elif isinstance(fact.result, TimerCancelled):
            projected = timers.get(fact.result.timer.id)
            if projected is not None and projected.state == "armed" and projected.timer == fact.result.timer:
                projected.state = "cancelled"
                projected.terminal_operation = fact.operation
        else:  # pragma: no cover - strict union hydration owns this
            raise TypeError("V5 timer result variant is malformed")

    def _project_due(
        self,
        timers: dict[str, _ProjectedTimer],
        fact: TimerDue,
        *,
        delivered: int,
    ) -> None:
        self._validate_timer(fact.timer)
        due, matured = _parse_us(fact.due_at), _parse_us(fact.matured_at)
        if matured < due:
            raise RuntimeError("accepted V5 timer maturity predates its deadline")
        projected = timers.get(fact.timer.id)
        if (
            projected is not None
            and projected.state == "armed"
            and projected.timer == fact.timer
            and projected.due_at_us == due
        ):
            projected.state = "matured"
            projected.matured_at_us = matured
            projected.maturity_identity = self.maturity_identity(fact.timer.id, due)
            projected.maturity_delivered = delivered

    def _validate_contents(
        self,
        facts: tuple[TimerCommandApplied | TimerDue, ...],
        outstanding: TimerCommand | None,
        *,
        tolerate_pending_markers: bool = False,
    ) -> None:
        timers: dict[str, _ProjectedTimer] = {}
        accepted: dict[str, TimerCommandApplied] = {}
        history_generation = 0
        for fact in facts:
            if isinstance(fact, TimerCommandApplied):
                generation = self._operation_generation(fact.operation)
                if generation != history_generation + 1:
                    raise RuntimeError("accepted V5 timer operations are not contiguous")
                history_generation = generation
                accepted[fact.operation] = fact
                self._project_applied(timers, fact)
            elif isinstance(fact, TimerDue):
                self._project_due(timers, fact, delivered=1)
            else:
                raise TypeError("V5 timer History contains an unknown fact")

        (last_generation,) = self._db.execute("SELECT last_generation FROM v5_timer_meta WHERE singleton=1").fetchone()
        rows = self._db.execute(
            "SELECT operation,subject,generation,command_json,result_json,ack_identity,"
            "applied_at_us,ack_delivered FROM v5_timer_operations ORDER BY generation"
        ).fetchall()
        pending: list[tuple[int, TimerCommand, TimerCommandApplied]] = []
        observed_generations: set[int] = set()
        for row in rows:
            operation, subject, generation, command_json, result_json, ack_identity, applied_at, delivered = row
            if (
                not isinstance(operation, str)
                or subject != self.subject
                or type(generation) is not int
                or generation in observed_generations
                or type(applied_at) is not int
                or type(delivered) is not int
                or delivered not in (0, 1)
                or ack_identity != self.ack_identity(operation)
                or generation != self._operation_generation(operation)
            ):
                raise RuntimeError("stored V5 timer operation is malformed")
            observed_generations.add(generation)
            command = _load(command_json, TimerCommand, "operation command")
            result = _load(result_json, TimerCommandApplied, "operation result")
            self._validate_timer(command.command.timer)
            if (
                command.operation != operation
                or result.operation != operation
                or command.command.timer != result.result.timer
                or (isinstance(command.command, ArmReminder) and not isinstance(result.result, TimerArmed))
                or (isinstance(command.command, CancelReminder) and not isinstance(result.result, TimerCancelled))
            ):
                raise RuntimeError("stored V5 timer operation contradicts its command")
            if isinstance(command.command, ArmReminder):
                armed = cast(TimerArmed, result.result)
                due = applied_at + command.command.delay_s * 1_000_000
                if _parse_us(armed.due_at) != due or _format_us(due) != armed.due_at:
                    raise RuntimeError("stored V5 timer arm deadline contradicts its command")
            accepted_result = accepted.get(operation)
            if accepted_result is not None:
                if result != accepted_result or (delivered != 1 and not tolerate_pending_markers):
                    raise RuntimeError("stored V5 timer operation contradicts canonical History")
            else:
                if delivered != 0 or generation <= history_generation:
                    raise RuntimeError("stored V5 timer operation has no canonical acknowledgement")
                pending.append((generation, command, result))

        if type(last_generation) is not int:
            raise RuntimeError("stored V5 timer generation is malformed")
        expected_last = max((history_generation, *observed_generations))
        pending_generations = [generation for generation, _, _ in pending]
        if (
            last_generation != expected_last
            or pending_generations != list(range(history_generation + 1, last_generation + 1))
            or len(pending) > 1
            or (pending and pending[0][1] != outstanding)
        ):
            raise RuntimeError("stored V5 timer generations contradict canonical History")
        for _, _, result in pending:
            self._project_applied(timers, result)

        timer_rows = self._db.execute(
            "SELECT timer_id,subject,incarnation,sequence,head,due_at_us,arm_operation,state,"
            "terminal_operation,matured_at_us,maturity_identity,maturity_delivered"
            " FROM v5_timers ORDER BY timer_id"
        ).fetchall()
        for row in timer_rows:
            if row[7] != "matured" or row[11] != 0:
                continue
            maturity = self._maturity((row[0], row[2], row[3], row[4], row[5], row[9], row[10]))
            projected = timers.get(maturity.value.timer.id)
            if (
                projected is not None
                and projected.state == "armed"
                and projected.timer == maturity.value.timer
                and projected.due_at_us == _parse_us(maturity.value.due_at)
            ):
                self._project_due(timers, maturity.value, delivered=0)
        expected_rows = [projected.row(self.subject) for _, projected in sorted(timers.items())]
        compared_rows = timer_rows
        if tolerate_pending_markers:
            expected_by_id = {row[0]: row for row in expected_rows}
            compared_rows = [
                (*row[:-1], 1)
                if row[-1] == 0
                and (expected := expected_by_id.get(row[0])) is not None
                and expected[-1] == 1
                and row[:-1] == expected[:-1]
                else row
                for row in timer_rows
            ]
        if compared_rows != expected_rows:
            raise RuntimeError("stored V5 timers contradict canonical History and pending operations")

    def _rebuild(self, facts: tuple[TimerCommandApplied | TimerDue, ...]) -> None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                last_generation = 0
                for fact in facts:
                    if isinstance(fact, TimerCommandApplied):
                        generation = self._operation_generation(fact.operation)
                        if generation != last_generation + 1:
                            raise RuntimeError("accepted V5 timer operations are not contiguous")
                        last_generation = generation
                        self._validate_timer(fact.result.timer)
                        if isinstance(fact.result, TimerArmed):
                            due = _parse_us(fact.result.due_at)
                            self._db.execute(
                                "UPDATE v5_timers SET state='superseded',terminal_operation=?"
                                " WHERE subject=? AND state='armed'",
                                (fact.operation, self.subject),
                            )
                            timer = fact.result.timer
                            self._db.execute(
                                "INSERT INTO v5_timers(timer_id,subject,incarnation,sequence,head,due_at_us,"
                                "arm_operation,state) VALUES(?,?,?,?,?,?,?,'armed')",
                                (
                                    timer.id,
                                    self.subject,
                                    timer.incarnation,
                                    timer.sequence,
                                    timer.head,
                                    due,
                                    fact.operation,
                                ),
                            )
                        elif isinstance(fact.result, TimerCancelled):
                            timer = fact.result.timer
                            self._db.execute(
                                "UPDATE v5_timers SET state='cancelled',terminal_operation=?"
                                " WHERE timer_id=? AND subject=? AND incarnation=? AND sequence=?"
                                " AND head=? AND state='armed'",
                                (
                                    fact.operation,
                                    timer.id,
                                    self.subject,
                                    timer.incarnation,
                                    timer.sequence,
                                    timer.head,
                                ),
                            )
                    elif isinstance(fact, TimerDue):
                        self._validate_timer(fact.timer)
                        due, matured = _parse_us(fact.due_at), _parse_us(fact.matured_at)
                        if matured < due:
                            raise RuntimeError("accepted V5 timer maturity predates its deadline")
                        identity = self.maturity_identity(fact.timer.id, due)
                        self._db.execute(
                            "UPDATE v5_timers SET state='matured',matured_at_us=?,maturity_identity=?,"
                            "maturity_delivered=1 WHERE timer_id=? AND subject=? AND incarnation=? AND sequence=?"
                            " AND head=? AND state='armed' AND due_at_us=?",
                            (
                                matured,
                                identity,
                                fact.timer.id,
                                self.subject,
                                fact.timer.incarnation,
                                fact.timer.sequence,
                                fact.timer.head,
                                due,
                            ),
                        )
                    else:
                        raise TypeError("V5 timer History contains an unknown fact")
                self._db.execute(
                    "UPDATE v5_timer_meta SET last_generation=? WHERE singleton=1",
                    (last_generation,),
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def _reconcile_history(self, facts: tuple[TimerCommandApplied | TimerDue, ...]) -> None:
        acknowledged = {fact.operation for fact in facts if isinstance(fact, TimerCommandApplied)}
        maturities = tuple(fact for fact in facts if isinstance(fact, TimerDue))
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for operation in acknowledged:
                    self._db.execute(
                        "UPDATE v5_timer_operations SET ack_delivered=1 WHERE operation=? AND subject=?",
                        (operation, self.subject),
                    )
                for fact in maturities:
                    self._db.execute(
                        "UPDATE v5_timers SET maturity_delivered=1"
                        " WHERE timer_id=? AND subject=? AND incarnation=? AND sequence=? AND head=?"
                        " AND state='matured' AND due_at_us=?",
                        (
                            fact.timer.id,
                            self.subject,
                            fact.timer.incarnation,
                            fact.timer.sequence,
                            fact.timer.head,
                            _parse_us(fact.due_at),
                        ),
                    )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._db.close()


__all__ = ["TimerMaturity", "V5TimerStore"]
