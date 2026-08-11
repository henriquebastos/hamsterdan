from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from petrus.impetus.history import ActivityFailed, ActivityRequested, FiringFailed
from petrus.impetus.petrinet import NetPath, Token
from petrus.motus.activity import ExecutionPolicy

from hamsterdan.contracts.readiness import (
    ActionsState,
    Authority,
    ConversationPublicationState,
    DashboardPublicationState,
    FindingPublicationState,
    HumanState,
    MutationState,
    ReadinessPublicationState,
    ReadinessSnapshot,
    ReviewRequest,
    ReviewState,
)
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
    def __init__(self, snapshot: ReadinessSnapshot, *, missing: str = "", duplicate: str = "") -> None:
        values = snapshot.dump()
        concerns = tuple(
            value_type(**{name: values[name] for name in value_type.__dataclass_fields__ if name in values})
            for value_type in (
                Authority,
                ActionsState,
                ReviewState,
                HumanState,
                MutationState,
                FindingPublicationState,
                ConversationPublicationState,
                DashboardPublicationState,
                ReadinessPublicationState,
            )
        )
        self.tokens = {
            path: (Token(type(value).__name__, value.dump()),)
            for path, value in zip(
                (
                    "authority",
                    "actions_state",
                    "review_state",
                    "human_state",
                    "mutation_state",
                    "finding_publication_state",
                    "conversation_publication_state",
                    "dashboard_publication_state",
                    "readiness_publication_state",
                ),
                concerns,
                strict=True,
            )
        }
        if missing:
            self.tokens[missing] = ()
        if duplicate:
            self.tokens[duplicate] *= 2

    def place(self, path: NetPath):
        return self.tokens.get(str(path), ())


def readiness_snapshot(**changes: object) -> ReadinessSnapshot:
    return ReadinessSnapshot("repo", 7, 2, "head", "base", True, True, **changes)


def test_fast_current_check_uses_only_durable_local_authority() -> None:
    authority = ProviderAuthority()
    lease = AuthorityLease(cast(Any, authority))
    lease.engine = cast(Any, SimpleNamespace(marking=Marking(readiness_snapshot(policy_digest="policy"))))

    assert all(lease.is_current(2, "head") for _ in range(1_000))
    assert not lease.is_current(1, "head")
    assert not lease.is_current(2, "stale")
    assert authority.calls == 0


def test_provisional_mutation_blocks_fast_currentness() -> None:
    lease = AuthorityLease(cast(Any, ProviderAuthority()))
    lease.engine = cast(Any, SimpleNamespace(marking=Marking(readiness_snapshot(provisional=True))))

    assert not lease.is_current(2, "head")


def test_snapshot_strictly_joins_the_six_concern_tokens() -> None:
    lease = AuthorityLease(cast(Any, ProviderAuthority()))
    lease.engine = cast(Any, SimpleNamespace(marking=Marking(readiness_snapshot(actions="green", review="clear"))))

    snapshot = lease.snapshot()

    assert snapshot is not None
    assert (snapshot.repository_id, snapshot.epoch, snapshot.actions, snapshot.review) == ("repo", 2, "green", "clear")


@pytest.mark.parametrize(
    "marking",
    [
        Marking(readiness_snapshot(), missing="review_state"),
        Marking(readiness_snapshot(), duplicate="authority"),
    ],
)
def test_snapshot_rejects_partial_or_duplicate_active_cohort(marking: Marking) -> None:
    lease = AuthorityLease(cast(Any, ProviderAuthority()))
    lease.engine = cast(Any, SimpleNamespace(marking=marking))

    with pytest.raises(RuntimeError, match="exactly one|incomplete"):
        lease.snapshot()


def test_snapshot_is_none_when_the_active_cohort_is_inactive() -> None:
    lease = AuthorityLease(cast(Any, ProviderAuthority()))
    lease.engine = cast(Any, SimpleNamespace(marking=SimpleNamespace(place=lambda path: ())))

    assert lease.snapshot() is None


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
