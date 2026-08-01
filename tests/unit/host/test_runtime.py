from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace
from typing import Any, cast

from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness import Control, Work
from hamsterdan.host.activities import PrReadinessActivities
from hamsterdan.host.runtime import AuthorityLease


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
        self.token = Token("control", asdict(control))

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
    work = Work("review", 2, "head", "review:operation")

    assert all(activities._is_current(work) for _ in range(1_000))
