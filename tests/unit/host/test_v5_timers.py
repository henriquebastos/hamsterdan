"""Durable host custody for V5 reminder timers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from petrus.impetus.history import ExternalEventDelivered
from petrus.impetus.petrinet import NetPath, Token
from pydantic import ValidationError

from hamsterdan.contracts.readiness_v5 import (
    ArmReminder,
    CancelReminder,
    ReminderTimer,
    TimerArmed,
    TimerCommand,
    TimerCommandApplied,
    TimerDue,
)
from hamsterdan.host.v5.runtime import V5Runtime
from hamsterdan.host.v5.timers import V5TimerStore

SUBJECT = "github:44:31:pr:7"


def timer(incarnation: int, sequence: int, head: str = "h1") -> ReminderTimer:
    return ReminderTimer(
        id=f"timer:{SUBJECT}:i{incarnation}:s{sequence}",
        incarnation=incarnation,
        sequence=sequence,
        head=head,
    )


def arm(generation: int, value: ReminderTimer, delay_s: int = 10) -> TimerCommand:
    return TimerCommand(
        operation=f"timer-command:{SUBJECT}:g{generation}",
        command=ArmReminder(kind="arm", timer=value, delay_s=delay_s),
    )


def cancel(generation: int, value: ReminderTimer) -> TimerCommand:
    return TimerCommand(
        operation=f"timer-command:{SUBJECT}:g{generation}",
        command=CancelReminder(kind="cancel", timer=value, reason="draft"),
    )


def test_exact_arm_replay_preserves_deadline_and_conflicting_payload_fails(tmp_path: Path) -> None:
    now = [1_000_000]
    store = V5TimerStore.open(tmp_path / "timers.sqlite3", SUBJECT, clock_us=lambda: now[0])
    command = arm(1, timer(1, 0))

    first = store.apply(command)
    now[0] = 9_000_000
    replayed = store.apply(command)

    assert replayed == first
    assert isinstance(first.result, TimerArmed)
    assert first.result.due_at == "1970-01-01T00:00:11.000000Z"
    conflicting = TimerCommand(
        operation=command.operation,
        command=ArmReminder(kind="arm", timer=timer(1, 1), delay_s=10),
    )
    with pytest.raises(RuntimeError, match="different timer command"):
        store.apply(conflicting)
    store.close()


def test_new_arm_atomically_supersedes_and_stale_cancel_cannot_touch_it(tmp_path: Path) -> None:
    now = [1_000_000]
    path = tmp_path / "timers.sqlite3"
    store = V5TimerStore.open(path, SUBJECT, clock_us=lambda: now[0])
    old, current = timer(1, 0), timer(2, 0, "h2")
    store.apply(arm(1, old))
    store.mark_ack_delivered(f"timer-command:{SUBJECT}:g1")
    now[0] = 2_000_000
    store.apply(arm(2, current))
    now[0] = 3_000_000
    store.apply(cancel(3, old))

    with sqlite3.connect(path) as database:
        states = dict(database.execute("SELECT timer_id,state FROM v5_timers"))
    assert states == {old.id: "superseded", current.id: "armed"}
    assert store.next_due() == 12.0
    store.close()


def test_ack_and_maturity_crash_markers_replay_exact_frozen_values(tmp_path: Path) -> None:
    now = [1_000_000]
    path = tmp_path / "timers.sqlite3"
    store = V5TimerStore.open(path, SUBJECT, clock_us=lambda: now[0])
    command = arm(1, timer(1, 0), delay_s=1)
    applied = store.apply(command)
    assert store.pending_ack() == applied
    store.close()  # crash before History delivery

    reopened = V5TimerStore.open(path, SUBJECT, outstanding=command, clock_us=lambda: now[0])
    assert reopened.pending_ack() == applied
    reopened.mark_ack_delivered(applied.operation)
    assert reopened.pending_ack() is None
    now[0] = 2_000_000
    claimed = reopened.claim_due()
    assert claimed is not None
    assert claimed.value.matured_at == "1970-01-01T00:00:02.000000Z"
    reopened.close()  # crash before History delivery

    replayed = V5TimerStore.open(path, SUBJECT, history=(applied,), clock_us=lambda: now[0])
    assert replayed.pending_maturity() == claimed
    replayed.mark_maturity_delivered(claimed.value.timer.id)
    assert replayed.pending_maturity() is None
    assert replayed.next_due() is None
    replayed.close()


def test_history_rebuild_recovers_acknowledged_deadline_and_maturity(tmp_path: Path) -> None:
    value = timer(1, 0)
    armed = TimerCommandApplied(
        operation=f"timer-command:{SUBJECT}:g1",
        result=TimerArmed(kind="armed", timer=value, due_at="2026-08-16T00:00:00.000000Z"),
    )
    due = TimerDue(
        timer=value,
        due_at="2026-08-16T00:00:00.000000Z",
        matured_at="2026-08-16T00:00:01.000000Z",
    )

    armed_store = V5TimerStore.open(tmp_path / "armed.sqlite3", SUBJECT, history=(armed,))
    assert armed_store.next_due() == 1_786_838_400.0
    armed_store.close()

    matured_store = V5TimerStore.open(tmp_path / "matured.sqlite3", SUBJECT, history=(armed, due))
    assert matured_store.next_due() is None
    assert matured_store.pending_maturity() is None  # History already accepted it
    matured_store.close()


def test_history_rebuild_recovers_outstanding_arm_when_its_ack_is_canonical(tmp_path: Path) -> None:
    command = arm(1, timer(1, 0))
    acknowledged = TimerCommandApplied(
        operation=command.operation,
        result=TimerArmed(
            kind="armed",
            timer=command.command.timer,
            due_at="2026-08-16T00:00:00.000000Z",
        ),
    )

    store = V5TimerStore.open(
        tmp_path / "timers.sqlite3",
        SUBJECT,
        history=(acknowledged,),
        outstanding=command,
    )

    assert store.next_due() == 1_786_838_400.0
    store.close()


def test_semantically_corrupt_deadline_rebuilds_from_canonical_history(tmp_path: Path) -> None:
    path = tmp_path / "timers.sqlite3"
    store = V5TimerStore.open(path, SUBJECT, clock_us=lambda: 1_000_000)
    acknowledged = store.apply(arm(1, timer(1, 0)))
    store.mark_ack_delivered(acknowledged.operation)
    store.close()
    with sqlite3.connect(path) as database:
        database.execute("UPDATE v5_timers SET due_at_us=1000000")

    rebuilt = V5TimerStore.open(path, SUBJECT, history=(acknowledged,))

    assert rebuilt.next_due() == 11.0
    assert path.with_name("timers.sqlite3.corrupt").exists()
    rebuilt.close()


def test_store_missing_new_history_generation_rebuilds_canonical_timer(tmp_path: Path) -> None:
    path = tmp_path / "timers.sqlite3"
    old, current = timer(1, 0), timer(2, 0, "h2")
    first = TimerCommandApplied(
        operation=f"timer-command:{SUBJECT}:g1",
        result=TimerArmed(kind="armed", timer=old, due_at="2026-08-16T00:00:00.000000Z"),
    )
    second = TimerCommandApplied(
        operation=f"timer-command:{SUBJECT}:g2",
        result=TimerArmed(kind="armed", timer=current, due_at="2026-08-17T00:00:00.000000Z"),
    )
    V5TimerStore.open(path, SUBJECT, history=(first,)).close()

    rebuilt = V5TimerStore.open(path, SUBJECT, history=(first, second))

    assert rebuilt.next_due() == 1_786_924_800.0
    rebuilt.close()


def test_missing_or_corrupt_store_with_unacknowledged_arm_fails_closed(tmp_path: Path) -> None:
    command = arm(1, timer(1, 0))
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(RuntimeError, match="unacknowledged arm"):
        V5TimerStore.open(missing, SUBJECT, outstanding=command)

    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not sqlite")
    with pytest.raises(RuntimeError, match="unacknowledged arm"):
        V5TimerStore.open(corrupt, SUBJECT, outstanding=command)


def test_unacknowledged_arm_failure_preserves_the_database_triplet(tmp_path: Path) -> None:
    path = tmp_path / "timers.sqlite3"
    command = arm(1, timer(1, 0))
    store = V5TimerStore.open(path, SUBJECT, clock_us=lambda: 1_000_000)
    store.apply(command)
    store.close()
    with sqlite3.connect(path) as database:
        database.execute("CREATE TABLE incompatible(value TEXT)")

    with pytest.raises(RuntimeError, match="unacknowledged arm"):
        V5TimerStore.open(path, SUBJECT, outstanding=command)

    assert path.exists()
    assert not path.with_name("timers.sqlite3.corrupt").exists()
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT due_at_us FROM v5_timers").fetchone() == (11_000_000,)


def test_pending_arm_must_equal_the_net_command_and_preserves_its_deadline_on_failure(tmp_path: Path) -> None:
    path = tmp_path / "timers.sqlite3"
    value = timer(1, 0)
    stored = arm(1, value, delay_s=1)
    store = V5TimerStore.open(path, SUBJECT, clock_us=lambda: 1_000_000)
    store.apply(stored)
    store.close()

    with pytest.raises(RuntimeError, match="unacknowledged arm"):
        V5TimerStore.open(path, SUBJECT, outstanding=arm(1, value, delay_s=2))

    preserved = V5TimerStore.open(path, SUBJECT, outstanding=stored)
    assert preserved.next_due() == 2.0
    assert preserved.pending_ack() is not None
    preserved.close()


def test_pending_cancel_mismatch_rebuilds_before_the_net_command_applies(tmp_path: Path) -> None:
    path = tmp_path / "timers.sqlite3"
    value = timer(1, 0)
    armed = TimerCommandApplied(
        operation=f"timer-command:{SUBJECT}:g1",
        result=TimerArmed(kind="armed", timer=value, due_at="1970-01-01T00:00:11.000000Z"),
    )
    stored = cancel(2, value)
    store = V5TimerStore.open(path, SUBJECT, history=(armed,))
    store.apply(stored)
    store.close()
    outstanding = TimerCommand(
        operation=stored.operation,
        command=CancelReminder(kind="cancel", timer=value, reason="closed"),
    )

    rebuilt = V5TimerStore.open(path, SUBJECT, history=(armed,), outstanding=outstanding)

    assert rebuilt.pending_ack() is None
    assert rebuilt.next_due() == 11.0
    rebuilt.apply(outstanding)
    assert rebuilt.next_due() is None
    rebuilt.close()


def test_failed_history_rebuild_does_not_leave_false_empty_custody(tmp_path: Path) -> None:
    path = tmp_path / "timers.sqlite3"
    value = timer(1, 0)
    invalid = TimerCommandApplied(
        operation=f"timer-command:{SUBJECT}:g2",
        result=TimerArmed(kind="armed", timer=value, due_at="2026-08-16T00:00:00.000000Z"),
    )
    valid = TimerCommandApplied(
        operation=f"timer-command:{SUBJECT}:g1",
        result=invalid.result,
    )

    with pytest.raises(RuntimeError, match="not contiguous"):
        V5TimerStore.open(path, SUBJECT, history=(invalid,))

    rebuilt = V5TimerStore.open(path, SUBJECT, history=(valid,))
    assert rebuilt.next_due() == 1_786_838_400.0
    rebuilt.close()


def test_reopened_store_enforces_wal_and_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "timers.sqlite3"
    V5TimerStore.open(path, SUBJECT).close()

    reopened = V5TimerStore.open(path, SUBJECT)

    assert reopened._db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    assert reopened._db.execute("PRAGMA foreign_keys").fetchone() == (1,)
    reopened.close()


def test_intact_armed_row_without_history_or_pending_ack_is_rebuilt_as_absent(tmp_path: Path) -> None:
    path = tmp_path / "timers.sqlite3"
    store = V5TimerStore.open(path, SUBJECT, clock_us=lambda: 1_000_000)
    applied = store.apply(arm(1, timer(1, 0)))
    store.mark_ack_delivered(applied.operation)
    store.close()

    reopened = V5TimerStore.open(path, SUBJECT, history=())
    assert reopened.next_due() is None
    reopened.close()


def test_repeated_corruption_preserves_each_quarantined_database(tmp_path: Path) -> None:
    path = tmp_path / "timers.sqlite3"
    path.write_bytes(b"first corrupt database")
    V5TimerStore.open(path, SUBJECT).close()
    first = path.with_name("timers.sqlite3.corrupt")
    assert first.read_bytes() == b"first corrupt database"

    path.write_bytes(b"second corrupt database")
    V5TimerStore.open(path, SUBJECT).close()

    assert first.read_bytes() == b"first corrupt database"
    assert path.with_name("timers.sqlite3.corrupt.1").read_bytes() == b"second corrupt database"


@pytest.mark.parametrize("delay", [0, -1, 2_147_483_648])
def test_arm_delay_is_a_positive_bounded_integer(tmp_path: Path, delay: object) -> None:
    store = V5TimerStore.open(tmp_path / f"timers-{delay}.sqlite3", SUBJECT)
    command = TimerCommand(
        operation=f"timer-command:{SUBJECT}:g1",
        command=ArmReminder(kind="arm", timer=timer(1, 0), delay_s=delay),  # type: ignore[arg-type]
    )
    with pytest.raises((ValueError, RuntimeError), match="delay"):
        store.apply(command)
    store.close()


def test_arm_delay_contract_rejects_boolean() -> None:
    with pytest.raises(ValidationError, match="valid integer"):
        ArmReminder(kind="arm", timer=timer(1, 0), delay_s=True)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("source", "color", "fact"),
    [
        (
            "on_timer_command_applied",
            "TimerCommandApplied",
            TimerCommandApplied(
                operation=f"timer-command:{SUBJECT}:g1",
                result=TimerArmed(
                    kind="armed",
                    timer=timer(1, 0),
                    due_at="1970-01-01T00:00:11.000000Z",
                ),
            ),
        ),
        (
            "on_timer",
            "TimerDue",
            TimerDue(
                timer=timer(1, 0),
                due_at="1970-01-01T00:00:11.000000Z",
                matured_at="1970-01-01T00:00:12.000000Z",
            ),
        ),
    ],
)
def test_timer_history_rejects_typed_fact_under_wrong_identity(
    source: str,
    color: str,
    fact: TimerCommandApplied | TimerDue,
) -> None:
    record = ExternalEventDelivered(
        NetPath(source),
        (Token(color, fact.dump()),),
        identity="wrong-identity",
        occurrence=1,
    )
    runtime = cast(
        V5Runtime,
        SimpleNamespace(
            engine=SimpleNamespace(records=(record,)),
            _timer_value=V5Runtime._timer_value,
        ),
    )

    with pytest.raises(RuntimeError, match="identity"):
        V5Runtime.timer_history(runtime)
