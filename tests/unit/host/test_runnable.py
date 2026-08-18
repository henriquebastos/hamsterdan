from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from hamsterdan.host.runnable import RunnableIndex


def test_wakes_coalesce_and_due_instances_are_taken_deterministically(tmp_path: Path) -> None:
    index = RunnableIndex(tmp_path / "runnable.sqlite3", clock=lambda: 10)
    index.wake("instance-b", 3, "webhook", "delivery")
    index.wake("instance-a", 2, "webhook", "delivery")
    index.wake("instance-a", 1, "webhook", "delivery")
    index.wake("instance-c", 11, "webhook", "delivery")

    assert index.count() == 3
    assert index.next_due() == 1
    assert index.take_due() == ("instance-a", "instance-b")
    assert index.next_due() == 11
    assert index.take_due() == ()
    assert index.take_due(now=11) == ("instance-c",)
    assert index.next_due() is None


def test_wake_added_after_take_is_not_lost_and_reopen_is_durable(tmp_path: Path) -> None:
    path = tmp_path / "runnable.sqlite3"
    first = RunnableIndex(path)
    first.wake("instance", 0, "webhook", "one")
    assert first.take_due(now=0) == ("instance",)
    first.wake("instance", 0, "webhook", "two")
    first.close()

    second = RunnableIndex(path)
    assert second.take_due(now=0) == ("instance",)
    second.close()


@pytest.mark.parametrize("damage", ["bytes", "schema"])
def test_disposable_index_recovers_from_corruption_or_incompatible_schema(tmp_path: Path, damage: str) -> None:
    path = tmp_path / "runnable.sqlite3"
    if damage == "bytes":
        path.write_bytes(b"not a sqlite database")
    else:
        with sqlite3.connect(path) as database:
            database.execute("CREATE TABLE wakes (wrong TEXT)")

    index = RunnableIndex(path)
    index.wake("instance", 0, "repair", "recovered")

    assert index.take_due(now=0) == ("instance",)
    assert path.with_name("runnable.sqlite3.corrupt").exists()
    index.close()


def test_repeated_recovery_keeps_only_one_bounded_quarantine(tmp_path: Path) -> None:
    path = tmp_path / "runnable.sqlite3"
    path.write_bytes(b"first")
    RunnableIndex(path).close()
    path.write_bytes(b"second")
    RunnableIndex(path).close()

    assert [item.name for item in tmp_path.glob("*.corrupt")] == ["runnable.sqlite3.corrupt"]


def test_timer_is_replaced_and_cancelled_without_disturbing_other_wakes(tmp_path: Path) -> None:
    index = RunnableIndex(tmp_path / "runnable.sqlite3")
    index.wake("instance", 5, "activity-terminal", "publish")
    index.replace_timer("instance", 20)
    index.replace_timer("instance", 30)

    assert index.take_due(now=5) == ("instance",)
    assert index.take_due(now=20) == ()
    index.cancel_timer("instance")
    assert index.take_due(now=100) == ()


@pytest.mark.parametrize("value", ["", "x" * 257])
def test_identifiers_are_nonempty_and_bounded(tmp_path: Path, value: str) -> None:
    index = RunnableIndex(tmp_path / "runnable.sqlite3")
    with pytest.raises(ValueError, match="bounded identifier"):
        index.wake(value, 0, "kind", "identity")


@pytest.mark.parametrize("due_at", [math.inf, -math.inf, math.nan])
def test_due_time_must_be_finite(tmp_path: Path, due_at: float) -> None:
    index = RunnableIndex(tmp_path / "runnable.sqlite3")
    with pytest.raises(ValueError, match="finite"):
        index.wake("instance", due_at, "kind", "identity")
