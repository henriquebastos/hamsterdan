"""Executable contracts for the provider-backed V5 mutation/git gate."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hamsterdan.agents.protocol import (
    AgentCleanupCategory,
    AgentProtocolError,
    AgentResultCategory,
    CodingResult,
)
from hamsterdan.contracts.readiness_v5 import DeclinedM, FaultM, MovedM, MutWork, Pushed
from hamsterdan.github_app.models import GitHubBoundaryError
from hamsterdan.host.git_publish import (
    GitPublishError,
    GitPublishResult,
    GitReconciliation,
    PublicationCategory,
)
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.mutation import V5MutationGate

HEAD = "a" * 40
BASE = "b" * 40
NEW_HEAD = "c" * 40
CLAIM = CurrentClaim("running", 3, HEAD, BASE, "policy-1")
WORK = MutWork(
    op="change",
    op_key="push:comment:9:" + HEAD + ":i3",
    head=HEAD,
    base=BASE,
    policy="policy-1",
    incarnation=3,
    lineage="",
    kind="change",
    instruction="rename the config key",
    run_id=0,
    attempt=0,
)


def changed(request) -> CodingResult:
    return CodingResult(
        request.kind,
        request.repository,
        request.pull_request,
        request.epoch,
        request.head,
        request.base,
        request.ref,
        "changed",
        "not_attempted",
        "diff --git a/a b/a\n",
        ["a"],
        [],
        "Apply requested change",
    )


class Runner:
    def __init__(self, outcome=None, *, consult_current: bool = False):
        self.outcome = outcome
        self.consult_current = consult_current
        self.calls: list[tuple] = []

    def code(self, repository_url, request, *, operation, attempt, is_current=None):
        current = None if not self.consult_current else is_current()
        self.calls.append((repository_url, request, operation, attempt, current))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return changed(request) if self.outcome is None else self.outcome


class Publisher:
    def __init__(self, *, reconciliation=None, publication=None):
        self.reconciliation = GitReconciliation("absent", HEAD) if reconciliation is None else reconciliation
        self.publication = GitPublishResult(NEW_HEAD) if publication is None else publication
        self.calls: list[tuple] = []

    def reconcile(self, **kwargs):
        self.calls.append(("reconcile", kwargs))
        outcome = self.reconciliation
        if isinstance(outcome, list):
            outcome = outcome.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def publish(self, result, **kwargs):
        self.calls.append(("publish", result, kwargs))
        if isinstance(self.publication, Exception):
            raise self.publication
        return self.publication


def gate(runner=None, publisher=None, claims=(CLAIM, CLAIM)) -> V5MutationGate:
    observed = iter(claims)

    def read_claim():
        value = next(observed)
        return value() if callable(value) else value

    return V5MutationGate(
        repository="owner/repo",
        pull_request=7,
        runner=Runner() if runner is None else runner,
        publisher=Publisher() if publisher is None else publisher,
        public_clone_url="https://example.test/owner/repo.git",
        claim=read_claim,
    )


def assert_fault(out: object) -> None:
    assert isinstance(out, FaultM)
    assert (out.op, out.op_key, out.head, out.base, out.policy) == (
        WORK.op,
        WORK.op_key,
        WORK.head,
        WORK.base,
        WORK.policy,
    )
    assert (out.kind, out.instruction, out.run_id, out.attempt) == (
        WORK.kind,
        WORK.instruction,
        WORK.run_id,
        WORK.attempt,
    )


class TestMutationGate:
    def test_existing_commit_reconciles_before_claim_or_agent(self) -> None:
        runner = Runner()
        publisher = Publisher(reconciliation=GitReconciliation("existing", NEW_HEAD, NEW_HEAD, (HEAD,)))

        out = gate(runner, publisher, claims=()).git_gate(WORK)

        assert out == Pushed(WORK.op, WORK.op_key, HEAD, NEW_HEAD, 3, "")
        assert runner.calls == []
        assert [call[0] for call in publisher.calls] == ["reconcile"]

    @pytest.mark.parametrize(
        "drift",
        [
            {"phase": "quiescent"},
            {"incarnation": 4},
            {"head": NEW_HEAD},
            {"base": "d" * 40},
            {"policy": "policy-2"},
        ],
    )
    def test_any_pre_agent_claim_movement_returns_the_full_observation(self, drift: dict) -> None:
        observed = replace(CLAIM, **drift)
        runner = Runner()

        out = gate(runner, claims=(observed,)).git_gate(WORK)

        assert out == MovedM(
            WORK.op,
            WORK.op_key,
            HEAD,
            3,
            observed.head,
            observed.base,
            observed.policy,
            observed.incarnation,
            observed.phase,
        )
        assert runner.calls == []

    def test_claim_movement_during_agent_wins_over_a_clean_decline(self) -> None:
        request = V5MutationGate.request("owner/repo", 7, WORK)
        unable = replace(changed(request), status="unable", diff="", changed_files=[])
        observed = replace(CLAIM, policy="policy-2")

        out = gate(Runner(unable), claims=(CLAIM, observed)).git_gate(WORK)

        assert isinstance(out, MovedM) and out.observed_policy == "policy-2"

    @pytest.mark.parametrize("status", ["unchanged", "unable", "banana"])
    def test_agent_no_change_is_a_clean_decline_after_the_second_fence(self, status: str) -> None:
        request = V5MutationGate.request("owner/repo", 7, WORK)
        result = replace(changed(request), status=status, diff="", changed_files=[])

        out = gate(Runner(result)).git_gate(WORK)

        expected = status if status in {"unchanged", "unable"} else "output_schema"
        assert isinstance(out, DeclinedM) and out.category == expected

    @pytest.mark.parametrize("category", list(AgentResultCategory))
    def test_classified_agent_protocol_outcomes_decline(self, category: AgentResultCategory) -> None:
        out = gate(Runner(AgentProtocolError("classified", result_category=category))).git_gate(WORK)
        assert isinstance(out, DeclinedM) and out.category == category.value

    @pytest.mark.parametrize(
        ("error", "category"),
        [
            (AgentProtocolError("timeout", timed_out=True), "timed_out"),
            (AgentProtocolError("canceled", canceled=True), "canceled"),
            (
                AgentProtocolError("cleanup", cleanup_category=AgentCleanupCategory.UNVERIFIED),
                "cleanup_unverified",
            ),
            (AgentProtocolError("protocol"), "protocol"),
        ],
    )
    def test_other_agent_protocol_outcomes_decline(self, error: AgentProtocolError, category: str) -> None:
        out = gate(Runner(error)).git_gate(WORK)
        assert isinstance(out, DeclinedM) and out.category == category

    def test_unreadable_claim_before_or_after_agent_fails_closed(self) -> None:
        def unreadable():
            raise GitHubBoundaryError("claim unavailable")

        before = V5MutationGate(
            "owner/repo", 7, Runner(), Publisher(), "https://example.test/repo.git", unreadable
        ).git_gate(WORK)
        assert_fault(before)
        after = gate(claims=(CLAIM, unreadable)).git_gate(WORK)
        assert_fault(after)

    def test_success_uses_distinct_global_agent_and_provider_identities(self) -> None:
        runner = Runner(consult_current=True)
        publisher = Publisher()

        out = gate(runner, publisher, claims=(CLAIM, CLAIM, CLAIM)).git_gate(WORK)

        assert out == Pushed(WORK.op, WORK.op_key, HEAD, NEW_HEAD, 3, "")
        [(_, request, operation, attempt, current)] = runner.calls
        assert operation == f"mutation:owner/repo:pr:7:{WORK.op_key}"
        assert attempt == 1 and current is True
        assert request.kind == "change"
        assert request.selected_work == [{"kind": "change", "request": "rename the config key"}]
        [(_, _, publication)] = [call for call in publisher.calls if call[0] == "publish"]
        assert publication["operation"] == WORK.op_key
        assert publication["payload_digest"] == publisher.calls[0][1]["payload_digest"]

    @pytest.mark.parametrize(
        ("category", "terminal"),
        [
            (PublicationCategory.CORRELATION, "declined"),
            (PublicationCategory.PATCH_ADMISSION, "declined"),
            (PublicationCategory.CURRENT_AUTHORITY, "moved"),
            (PublicationCategory.IDEMPOTENCY, "fault"),
            (PublicationCategory.REPOSITORY_REF, "fault"),
            (PublicationCategory.GIT_OPERATION, "fault"),
            (PublicationCategory.OBJECT_WRITE, "fault"),
            (PublicationCategory.BOUNDARY_UNAVAILABLE, "fault"),
        ],
    )
    def test_publication_categories_have_closed_terminals(self, category: PublicationCategory, terminal: str) -> None:
        publisher = Publisher(publication=GitPublishError(category, "classified"))
        out = gate(publisher=publisher, claims=(CLAIM, CLAIM, CLAIM)).git_gate(WORK)
        assert {"declined": DeclinedM, "moved": MovedM, "fault": FaultM}[terminal] is type(out)

    def test_ambiguous_ref_cas_reconciles_before_failing_closed(self) -> None:
        publisher = Publisher(
            reconciliation=[
                GitReconciliation("absent", HEAD),
                GitReconciliation("existing", NEW_HEAD, NEW_HEAD, (HEAD,)),
            ],
            publication=GitPublishError(PublicationCategory.REF_CAS, "unproven"),
        )
        out = gate(publisher=publisher).git_gate(WORK)
        assert isinstance(out, Pushed) and out.new_head == NEW_HEAD

        publisher = Publisher(
            reconciliation=[GitReconciliation("absent", HEAD), GitReconciliation("absent", NEW_HEAD)],
            publication=GitPublishError(PublicationCategory.REF_CAS, "unproven"),
        )
        assert_fault(gate(publisher=publisher).git_gate(WORK))

    def test_raw_publication_boundary_failure_remains_recoverable(self) -> None:
        publisher = Publisher(publication=GitHubBoundaryError("PR projection unavailable"))

        out = gate(publisher=publisher).git_gate(WORK)

        assert_fault(out)

    def test_unexpected_runner_failure_remains_an_activity_failure(self) -> None:
        with pytest.raises(RuntimeError, match="bug"):
            gate(Runner(RuntimeError("bug"))).git_gate(WORK)


class TestCodingProjection:
    @pytest.mark.parametrize("kind", ["change", "update_base", "resolve_conflict"])
    def test_human_work_preserves_its_kind_and_instruction(self, kind: str) -> None:
        work = replace(WORK, op=kind, kind=kind)
        request = V5MutationGate.request("owner/repo", 7, work)
        assert request.kind == "change"
        assert request.selected_work == [{"kind": kind, "request": WORK.instruction}]
        assert request.failure_evidence == [] and request.fingerprint == "" and request.lineage == []
        assert request.merge_base is (kind != "change")

    def test_repair_projects_exact_failure_evidence_and_budget_lineage(self) -> None:
        work = replace(
            WORK,
            op="repair:L1:fp1",
            kind="repair",
            instruction="",
            lineage="L1",
            run_id=42,
            attempt=2,
        )
        request = V5MutationGate.request("owner/repo", 7, work)
        assert request.kind == "repair" and request.selected_work == []
        assert request.failure_evidence == [
            {"head": HEAD, "run_id": 42, "attempt": 2, "conclusion": "failure", "fingerprint": "fp1"}
        ]
        assert request.fingerprint == "fp1"
        assert request.lineage == [{"kind": "repair_budget", "lineage": "L1", "operation": "repair:L1:fp1"}]

    @pytest.mark.parametrize(
        "work",
        [
            replace(WORK, op="repair:wrong:fp1", kind="repair", instruction="", lineage="L1", run_id=1, attempt=1),
            replace(WORK, op="repair:L1:", kind="repair", instruction="", lineage="L1", run_id=1, attempt=1),
            replace(WORK, op="repair:L1:fp1", kind="repair", lineage="L1", run_id=1, attempt=1),
            replace(WORK, op="repair:L1:fp1", kind="repair", instruction="", lineage="L1", run_id=0, attempt=1),
        ],
    )
    def test_malformed_repair_payload_is_an_internal_contract_failure(self, work: MutWork) -> None:
        with pytest.raises(ValueError, match="repair"):
            V5MutationGate.request("owner/repo", 7, work)
