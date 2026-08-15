"""Executable contracts for the provider-backed V5 review-agent gate.

The gate translates one globally identified V5 round into the existing
credential-free AgentRunner protocol. Agent-declared inability and
classified AgentProtocolError outcomes return RoundUnable; composition,
programming, and durability failures remain genuine Motus failures.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from hamsterdan.agents.protocol import (
    AgentCleanupCategory,
    AgentProtocolError,
    AgentResultCategory,
    ReviewResult,
)
from hamsterdan.contracts.readiness_v5 import AgentReview, RoundOpen, RoundUnable
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.review import V5ReviewGate

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
    def comments(self):
        return (
            {
                "id": 9,
                "html_url": "https://example.test/comments/9",
                "body": "context",
                "user": {"login": "reviewer"},
            },
        )

    def select_run(self, workflow: str, head: str):
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


def gate(runner: Runner, claim=CLAIM) -> V5ReviewGate:
    return V5ReviewGate(
        repository="owner/repo",
        pull_request=7,
        authority=FakeAuthority(),
        runner=runner,
        public_clone_url="https://example.test/owner/repo.git",
        workflow_path="ci.yml",
        claim=lambda: claim,
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

    def test_currentness_callback_detects_any_claim_movement(self) -> None:
        runner = Runner(result())
        moved = replace(CLAIM, incarnation=4)
        gate(runner, moved).review_agent(WORK)
        is_current = runner.calls[0][-1]
        assert is_current is not None and is_current() is False

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
