"""Executable contracts for the provider-backed V5 review-agent gate.

The gate translates one globally identified V5 round into the existing
credential-free AgentRunner protocol. Agent-declared inability and
classified AgentProtocolError outcomes return RoundUnable; composition,
programming, and durability failures remain genuine Motus failures.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from hamsterdan.agents.protocol import (
    AgentCleanupCategory,
    AgentProtocolError,
    AgentResultCategory,
    ReviewResult,
)
from hamsterdan.contracts.readiness_v5 import AgentReview, RoundDeferred, RoundMoved, RoundOpen, RoundUnable
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.review import V5ReviewGate, V5ReviewRequestStore

HEAD = "a" * 40
BASE = "b" * 40
OPERATION = f"review:github:12:34:pr:7:{HEAD}:i3"
MEM = {
    "subject": "github:12:34:pr:7",
    "head": HEAD,
    "incarnation": 3,
    "status": "pending",
    "reviewed": [],
    "provisional": [{"id": "old", "note": "old", "blocking": True}],
    "findings": [{"id": "landed", "note": "landed", "blocking": True}],
    "lineage": [{"finding_id": "old", "state": "still_open", "supersedes": None}],
    "dismissed": [],
    "pub": {"phase": "idle"},
}
WORK = RoundOpen(
    operation=OPERATION,
    head=HEAD,
    base=BASE,
    policy="policy-1",
    incarnation=3,
    prior_findings=MEM["provisional"],
    prior_lineage=MEM["lineage"],
    mem=MEM,
)
CLAIM = CurrentClaim(phase="running", incarnation=3, head=HEAD, base=BASE, policy="policy-1")


class FakeAuthority:
    def __init__(self) -> None:
        self.readable = True
        self.reads = 0
        self.comment_body = "context"

    def comments(self):
        self.reads += 1
        if not self.readable:
            raise AssertionError("recovered V5 review read current provider comments")
        return (
            {
                "id": 9,
                "html_url": "https://example.test/comments/9",
                "body": self.comment_body,
                "user": {"login": "reviewer"},
            },
        )

    def select_run(self, workflow: str, head: str):
        self.reads += 1
        if not self.readable:
            raise AssertionError("recovered V5 review read current provider checks")
        assert (workflow, head) == ("ci.yml", HEAD)


class Runner:
    def __init__(self, result: ReviewResult | Exception):
        self.result = result
        self.calls: list[tuple] = []

    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        self.calls.append((repository_url, request, operation, attempt, is_current))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def result(*, status: str = "clear", findings=None, lineage=None) -> ReviewResult:
    return ReviewResult(
        repository="owner/repo",
        pull_request=7,
        epoch=3,
        head=HEAD,
        base=BASE,
        status=status,
        findings=[] if findings is None else findings,
        lineage=[] if lineage is None else lineage,
    )


class PassthroughRequests:
    def __init__(self) -> None:
        self.claims = 0

    def lookup(self, operation, attempt=1):
        del operation, attempt

    def claim(self, operation, request, attempt=1):
        del operation, attempt
        self.claims += 1
        return request


def gate(runner: Runner, claim=CLAIM, *, authority=None, requests=None, unstaged=lambda: None) -> V5ReviewGate:
    return V5ReviewGate(
        repository="owner/repo",
        pull_request=7,
        authority=FakeAuthority() if authority is None else authority,
        runner=runner,
        public_clone_url="https://example.test/owner/repo.git",
        workflow_path="ci.yml",
        claim=lambda: claim,
        requests=PassthroughRequests() if requests is None else requests,
        unstaged_custody=unstaged,
    )


class TestReviewAgentGate:
    def test_forwards_global_operation_and_net_selected_lineage_without_credentials(self) -> None:
        fresh = {"id": "fresh", "note": "fresh", "blocking": False}
        lineage = [
            {"finding_id": "old", "state": "resolved", "supersedes": None},
            {"finding_id": "fresh", "state": "new", "supersedes": None},
        ]
        runner = Runner(result(findings=[fresh], lineage=lineage))

        out = gate(runner).review_agent(WORK)

        assert isinstance(out, AgentReview)
        assert out.findings == [fresh]  # no host-side provisional concatenation
        assert out.lineage == lineage
        [(repository_url, request, operation, attempt, is_current)] = runner.calls
        assert repository_url == "https://example.test/owner/repo.git"
        assert operation == OPERATION and attempt == 1
        assert request.prior_findings == WORK.prior_findings
        assert request.applied_changes == WORK.prior_lineage
        assert request.repository == "owner/repo" and request.pull_request == 7
        assert request.policy == {"digest": "policy-1"}
        assert request.prior_comments == [
            {
                "id": 9,
                "url": "https://example.test/comments/9",
                "body": "context",
                "author": "reviewer",
            }
        ]
        assert is_current is not None and is_current() is True

    def test_unstaged_custody_defers_before_claim_request_or_agent_entry(self) -> None:
        blocker = "9adff0dc-4784-4eed-9c78-047d6952efed"
        runner = Runner(result())
        authority = FakeAuthority()
        requests = PassthroughRequests()

        out = gate(runner, authority=authority, requests=requests, unstaged=lambda: blocker).review_agent(WORK)

        assert out == RoundDeferred(
            operation=OPERATION,
            head=HEAD,
            base=BASE,
            policy="policy-1",
            incarnation=3,
            prior_findings=WORK.prior_findings,
            prior_lineage=WORK.prior_lineage,
            mem=MEM,
            attempt=1,
            blocker=blocker,
        )
        assert runner.calls == []
        assert authority.reads == 0
        assert requests.claims == 0

    def test_cleanup_verified_cancellation_defers_when_custody_arrives_in_flight(self) -> None:
        blocker = [None]

        class CancelingRunner(Runner):
            def review(self, repository_url, request, *, operation, attempt, is_current=None):
                blocker[0] = "9adff0dc-4784-4eed-9c78-047d6952efed"
                raise AgentProtocolError("superseded", canceled=True)

        out = gate(CancelingRunner(result()), unstaged=lambda: blocker[0]).review_agent(WORK)

        assert isinstance(out, RoundDeferred)
        assert out.attempt == 1 and out.blocker == blocker[0]

    def test_cleanup_uncertainty_remains_unable_even_when_custody_arrives(self) -> None:
        blocker = [None]

        class CancelingRunner(Runner):
            def review(self, repository_url, request, *, operation, attempt, is_current=None):
                blocker[0] = "9adff0dc-4784-4eed-9c78-047d6952efed"
                raise AgentProtocolError(
                    "superseded",
                    canceled=True,
                    cleanup_category=AgentCleanupCategory.UNVERIFIED,
                )

        out = gate(CancelingRunner(result()), unstaged=lambda: blocker[0]).review_agent(WORK)

        assert isinstance(out, RoundUnable) and out.category == "canceled"

    def test_moved_claim_cancels_before_request_custody_provider_reads_or_agent_entry(self) -> None:
        runner = Runner(result())
        moved = replace(CLAIM, incarnation=4)
        authority = FakeAuthority()
        requests = PassthroughRequests()

        out = gate(runner, moved, authority=authority, requests=requests).review_agent(WORK)

        assert out == RoundMoved(
            head=HEAD,
            incarnation=3,
            observed=moved.head,
            observed_base=moved.base,
            observed_policy=moved.policy,
            observed_incarnation=moved.incarnation,
            observed_phase=moved.phase,
            mem=MEM,
        )
        assert runner.calls == []
        assert authority.reads == 0
        assert requests.claims == 0

    def test_validated_unable_result_is_a_clean_round_outcome(self) -> None:
        out = gate(Runner(result(status="unable", findings=[{"ignored": True}]))).review_agent(WORK)
        assert out == RoundUnable(head=HEAD, incarnation=3, category="unable", mem=MEM)

    @pytest.mark.parametrize(
        ("category", "expected"),
        [(category, category.value) for category in AgentResultCategory],
    )
    def test_closed_agent_result_categories_map_exhaustively(
        self, category: AgentResultCategory, expected: str
    ) -> None:
        error = AgentProtocolError("classified", result_category=category)
        out = gate(Runner(error)).review_agent(WORK)
        assert isinstance(out, RoundUnable) and out.category == expected

    @pytest.mark.parametrize(
        ("error", "category"),
        [
            (AgentProtocolError("timeout", timed_out=True), "timed_out"),
            (AgentProtocolError("cancel", canceled=True), "canceled"),
            (
                AgentProtocolError("cleanup", cleanup_category=AgentCleanupCategory.UNVERIFIED),
                "cleanup_unverified",
            ),
            (AgentProtocolError("protocol"), "protocol"),
        ],
    )
    def test_other_protocol_outcomes_use_the_closed_unable_vocabulary(
        self, error: AgentProtocolError, category: str
    ) -> None:
        out = gate(Runner(error)).review_agent(WORK)
        assert isinstance(out, RoundUnable) and out.category == category

    def test_unexpected_runner_failure_remains_a_genuine_activity_failure(self) -> None:
        with pytest.raises(RuntimeError, match="bug"):
            gate(Runner(RuntimeError("bug"))).review_agent(WORK)


class TestReviewRequestRecovery:
    def test_restart_reuses_the_exact_frozen_request_before_any_provider_read(self, tmp_path: Path) -> None:
        path = tmp_path / "review-requests.sqlite3"
        authority = FakeAuthority()
        first_runner = Runner(result())
        first_store = V5ReviewRequestStore(path)
        gate(first_runner, authority=authority, requests=first_store).review_agent(WORK)
        frozen = first_runner.calls[0][1]
        assert authority.reads == 2
        first_store.close()

        authority.comment_body = "changed after the lost Activity terminal"
        authority.readable = False
        second_runner = Runner(result())
        second_store = V5ReviewRequestStore(path)
        gate(second_runner, authority=authority, requests=second_store).review_agent(WORK)

        assert second_runner.calls[0][1] == frozen
        assert authority.reads == 2
        second_store.close()

    def test_same_operation_cannot_select_a_different_round(self, tmp_path: Path) -> None:
        path = tmp_path / "review-requests.sqlite3"
        store = V5ReviewRequestStore(path)
        gate(Runner(result()), requests=store).review_agent(WORK)

        conflicting = replace(WORK, head="c" * 40)
        with pytest.raises(RuntimeError, match="operation.*different review request"):
            gate(Runner(result()), requests=store).review_agent(conflicting)
        store.close()

    def test_fresh_attempt_gets_fresh_request_custody_under_the_same_operation(self, tmp_path: Path) -> None:
        path = tmp_path / "review-requests.sqlite3"
        authority = FakeAuthority()
        store = V5ReviewRequestStore(path)
        first = Runner(result())
        gate(first, authority=authority, requests=store).review_agent(WORK)

        authority.comment_body = "context after deferred custody cleared"
        second = Runner(result())
        gate(second, authority=authority, requests=store).review_agent(replace(WORK, attempt=2))

        assert first.calls[0][1].prior_comments[0]["body"] == "context"
        assert second.calls[0][1].prior_comments[0]["body"] == "context after deferred custody cleared"
        assert [first.calls[0][3], second.calls[0][3]] == [1, 2]
        with sqlite3.connect(path) as database:
            assert database.execute(
                "SELECT attempt FROM v5_review_requests WHERE operation=? ORDER BY attempt", (OPERATION,)
            ).fetchall() == [(1,), (2,)]
        store.close()

    def test_legacy_operation_keyed_request_migrates_as_attempt_one(self, tmp_path: Path) -> None:
        path = tmp_path / "review-requests.sqlite3"
        store = V5ReviewRequestStore(path)
        gate(Runner(result()), requests=store).review_agent(WORK)
        store.close()
        with sqlite3.connect(path) as database:
            database.execute("ALTER TABLE v5_review_requests RENAME TO v5_review_requests_v2")
            database.execute(
                "CREATE TABLE v5_review_requests ("
                "operation TEXT PRIMARY KEY,request_json TEXT NOT NULL,digest TEXT NOT NULL)"
            )
            database.execute(
                "INSERT INTO v5_review_requests SELECT operation,request_json,digest FROM v5_review_requests_v2"
            )
            database.execute("DROP TABLE v5_review_requests_v2")

        reopened = V5ReviewRequestStore(path)

        assert reopened.lookup(OPERATION, 1) is not None
        with sqlite3.connect(path) as database:
            assert {row[1] for row in database.execute("PRAGMA table_info(v5_review_requests)")} == {
                "operation",
                "attempt",
                "request_json",
                "digest",
            }
        reopened.close()

    def test_stored_request_digest_is_verified_before_replay(self, tmp_path: Path) -> None:
        path = tmp_path / "review-requests.sqlite3"
        store = V5ReviewRequestStore(path)
        gate(Runner(result()), requests=store).review_agent(WORK)
        store.close()

        with sqlite3.connect(path) as database:
            [raw] = database.execute(
                "SELECT request_json FROM v5_review_requests WHERE operation = ?", (OPERATION,)
            ).fetchone()
            corrupted = raw.replace('"diff_path":"diff.patch"', '"diff_path":"other.patch"')
            assert sha256(corrupted.encode()).hexdigest() != sha256(raw.encode()).hexdigest()
            database.execute(
                "UPDATE v5_review_requests SET request_json = ? WHERE operation = ?",
                (corrupted, OPERATION),
            )

        reopened = V5ReviewRequestStore(path)
        with pytest.raises(RuntimeError, match="digest"):
            reopened.lookup(OPERATION)
        reopened.close()
