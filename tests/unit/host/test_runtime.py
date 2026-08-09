from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from petrus.impetus.history import ActivityFailed, ActivityRequested, FiringFailed
from petrus.impetus.petrinet import NetPath, Token
from petrus.motus.activity import ExecutionPolicy

from hamsterdan.contracts.readiness import Control, ReviewRequest
from hamsterdan.host.activities import PrReadinessActivities
from hamsterdan.host.runtime import AuthorityLease, PrReadinessHost


class ProviderAuthority:
    def __init__(self) -> None:
        self.calls = 0

    def pull_request(self):
        self.calls += 1
        raise AssertionError("fast cancellation must not read GitHub")

    def policy(self, base_ref: str):
        self.calls += 1
        raise AssertionError("fast cancellation must not read GitHub")


class Marking:
    def __init__(self, control: Control) -> None:
        self.token = Token("control", control.dump())

    def place(self, path: NetPath):
        assert path == NetPath("current")
        return (self.token,)


def test_fast_current_check_uses_only_durable_local_authority() -> None:
    authority = ProviderAuthority()
    lease = AuthorityLease(cast(Any, authority))
    control = Control("repo", 7, 2, "head", "base", True, True, policy_digest="policy")
    lease.engine = cast(Any, SimpleNamespace(marking=Marking(control)))

    assert all(lease.is_current(2, "head") for _ in range(1_000))
    assert not lease.is_current(1, "head")
    assert not lease.is_current(2, "stale")
    assert authority.calls == 0


def test_agent_polling_predicate_does_not_invoke_provider_fence() -> None:
    activities = object.__new__(PrReadinessActivities)
    activities.current = lambda epoch, head: (epoch, head) == (2, "head")
    activities.current_fence = lambda *args: (_ for _ in ()).throw(AssertionError("provider fence used while polling"))
    work = ReviewRequest(2, "head", "review:operation", "base", "policy", True, True, {}, [], [])

    assert all(activities._is_current(work) for _ in range(1_000))


def test_drain_does_not_replace_engine_without_a_new_exact_failure_pair(tmp_path) -> None:
    class BrokenEngine:
        records = ()

        def advance(self):
            raise RuntimeError("unproven engine failure")

    class Replacement:
        records = ()
        closed = False

        def close(self):
            self.closed = True

    broken, replacement = BrokenEngine(), Replacement()
    lease = AuthorityLease(cast(Any, ProviderAuthority()))
    lease.engine = cast(Any, broken)
    subject = PrReadinessHost(
        tmp_path,
        cast(Any, broken),
        lease,
        cast(Any, object()),
        lambda: cast(Any, replacement),
    )

    with pytest.raises(RuntimeError, match="unproven engine failure"):
        subject.drain()

    assert subject.engine is broken
    assert lease.engine is broken
    assert replacement.closed


def test_drain_rejects_a_divergent_history_prefix(tmp_path) -> None:
    requested = ActivityRequested(
        NetPath("execute.review"),
        activity="review",
        input={},
        policy=ExecutionPolicy(),
        correlation="correlation",
        idempotency="idempotency",
        occurrence=1,
    )
    divergent = ActivityRequested(
        NetPath("execute.dashboard_publish"),
        activity="dashboard_publish",
        input={},
        policy=ExecutionPolicy(),
        correlation="other",
        idempotency="other",
        occurrence=1,
    )

    class BrokenEngine:
        records = (requested,)

        def advance(self):
            raise RuntimeError("terminal failure")

    class Replacement:
        records = (
            divergent,
            ActivityFailed(NetPath("execute.review"), "failed", occurrence=1),
            FiringFailed(NetPath("execute.review"), "failed", occurrence=1),
        )
        closed = False

        def close(self):
            self.closed = True

    broken, replacement = BrokenEngine(), Replacement()
    lease = AuthorityLease(cast(Any, ProviderAuthority()))
    lease.engine = cast(Any, broken)
    subject = PrReadinessHost(tmp_path, cast(Any, broken), lease, cast(Any, object()), lambda: cast(Any, replacement))

    with pytest.raises(RuntimeError, match="terminal failure"):
        subject.drain()

    assert subject.engine is broken and lease.engine is broken
    assert replacement.closed


def test_drain_rejects_a_failure_pair_for_the_wrong_transition(tmp_path) -> None:
    requested = ActivityRequested(
        NetPath("execute.review"),
        activity="review",
        input={},
        policy=ExecutionPolicy(),
        correlation="correlation",
        idempotency="idempotency",
        occurrence=1,
    )

    class BrokenEngine:
        records = (requested,)

        def advance(self):
            raise RuntimeError("terminal failure")

    class Replacement:
        records = (
            requested,
            ActivityFailed(NetPath("execute.dashboard_publish"), "failed", occurrence=1),
            FiringFailed(NetPath("execute.dashboard_publish"), "failed", occurrence=1),
        )
        closed = False

        def close(self):
            self.closed = True

    broken, replacement = BrokenEngine(), Replacement()
    lease = AuthorityLease(cast(Any, ProviderAuthority()))
    lease.engine = cast(Any, broken)
    subject = PrReadinessHost(tmp_path, cast(Any, broken), lease, cast(Any, object()), lambda: cast(Any, replacement))

    with pytest.raises(RuntimeError, match="terminal failure"):
        subject.drain()

    assert subject.engine is broken and lease.engine is broken
    assert replacement.closed
