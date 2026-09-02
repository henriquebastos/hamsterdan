"""Restart convergence for V5 inline effect Activities.

Canonical Petrus History is the invocation outbox for these gates.  A fresh
Engine must redispatch the exact frozen request after either a pre-effect crash
or a crash after the provider accepted the effect but before ActivityCompleted
was appended.  The provider's stable operation ledger then makes redispatch a
lookup, never a duplicate effect.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from harness import fresh_world, make_activities
from petrus.engine import Engine, choose_throughput
from petrus.impetus.history import ActivityCompleted, ActivityFailed, ActivityRequested, FiringFailed
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import ActivityDefinition, ActivityInvocation, ExecutionPolicy, activity
from petrus.motus.dispatch import Dispatch, InlineDispatch

from hamsterdan.agents.protocol import CodingResult, ReviewResult
from hamsterdan.contracts.readiness_v5 import (
    AgentReview,
    MutWork,
    Publishable,
    RemReq,
    RerunReq,
    RoundOpen,
    RoundUnable,
    WorkflowModel,
)
from hamsterdan.github_app.models import ActionsRunSnapshot, PublicationResult, RerunIssue
from hamsterdan.host.git_publish import GitPublishResult, GitReconciliation
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.gates import V5PublicationGates
from hamsterdan.host.v5.mutation import V5MutationGate
from hamsterdan.host.v5.rerun import V5RerunGate
from hamsterdan.host.v5.review import V5ReviewGate, V5ReviewRequestStore
from hamsterdan.readiness.net_v5 import build_net_v5
from hamsterdan.readiness.net_v5.gating import VariantPayloadConverter, wire_gates
from hamsterdan.readiness.net_v5.topology import DERIVED, GATES

INSTANCE = "test:v5-inline-recovery"
HEAD = "a" * 40
BASE = "b" * 40
NEW_HEAD = "c" * 40
CLAIM = CurrentClaim("running", 3, HEAD, BASE, "policy-1")
REVIEW_MEMORY = {
    "subject": "github:12:34:pr:7",
    "head": HEAD,
    "incarnation": 3,
    "status": "pending",
    "reviewed": [],
    "provisional": [],
    "findings": [],
    "lineage": [],
    "dismissed": [],
    "pub": {"phase": "idle"},
}
ROUND = RoundOpen(
    operation=f"review:github:12:34:pr:7:{HEAD}:i3",
    head=HEAD,
    base=BASE,
    policy="policy-1",
    incarnation=3,
    prior_findings=[],
    prior_lineage=[],
    mem=REVIEW_MEMORY,
)
FINDINGS = [{"id": "f1", "note": "review finding", "blocking": True}]
PUBLICATION = Publishable(
    head=HEAD,
    base=BASE,
    policy="policy-1",
    incarnation=3,
    findings=FINDINGS,
    effect=f"findings:{HEAD}:i3",
    op=f"findings:{HEAD}:i3",
    mem={**REVIEW_MEMORY, "pub": {"phase": "pending"}},
)
RERUN = RerunReq(
    fingerprint="lineage:fingerprint",
    fp="fingerprint",
    op="rerun:lineage:fingerprint",
    head=HEAD,
    base=BASE,
    policy="policy-1",
    incarnation=3,
    run_id=41,
    attempt=2,
    mem={"reruns": {}, "repairs": {}, "rerun_faults": {}, "closing": None},
)
REMINDER = RemReq(timer_id="timer:github:12:34:pr:7:i3:s0")
MUTATION = MutWork(
    op="change",
    op_key=f"push:comment:9:{HEAD}:i3",
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


class SimulatedProcessDeath(BaseException):
    """Test-only cut that cannot be classified as an Activity terminal."""


class CrashCutDispatch:
    """Execute or retain an invocation, optionally losing its terminal."""

    def __init__(self, activities: Mapping[str, ActivityDefinition], mode: str) -> None:
        self.activities, self.mode = activities, mode
        self.invocations: list[tuple[int, ActivityInvocation]] = []
        self.completed: list[tuple[int, object]] = []
        self.crashes = 0

    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None:
        self.invocations.append((occurrence, invocation))
        if self.mode == "hold":
            return
        try:
            result = self.activities[invocation.activity](invocation, context=None)  # type: ignore[arg-type]
        except SimulatedProcessDeath:
            self.crashes += 1
            return
        if self.mode == "complete":
            self.completed.append((occurrence, result))

    def collect(self) -> tuple[tuple[int, object], ...]:
        values = tuple(self.completed)
        self.completed.clear()
        return values


class ClaimPort:
    def __init__(self) -> None:
        self.readable = True
        self.reads = 0

    def __call__(self) -> CurrentClaim:
        self.reads += 1
        if not self.readable:
            raise AssertionError("lookup-first recovery read moved authority")
        return CLAIM


class ReviewAuthority:
    def __init__(self) -> None:
        self.readable = True
        self.reads = 0

    def comments(self):
        self.reads += 1
        if not self.readable:
            raise AssertionError("review replay read current provider comments")
        return ()

    def select_run(self, workflow: str, head: str):
        self.reads += 1
        if not self.readable:
            raise AssertionError("review replay read current provider checks")
        assert (workflow, head) == ("ci.yml", HEAD)


class ReviewLedgerRunner:
    def __init__(self) -> None:
        self.held: dict[str, tuple[object, ReviewResult]] = {}
        self.calls = 0
        self.executions = 0

    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        assert repository_url == "https://example.test/owner/repo.git" and attempt == 1
        assert is_current is not None and is_current()
        self.calls += 1
        prior = self.held.get(operation)
        if prior is not None:
            assert prior[0] == request
            return prior[1]
        self.executions += 1
        result = ReviewResult("owner/repo", 7, 3, HEAD, BASE, "clear", [], [])
        self.held[operation] = request, result
        return result


class FindingsLedger:
    def __init__(self) -> None:
        self.held: dict[str, tuple[str, str]] = {}
        self.posts = 0

    def finding_find(self, operation, head):
        prior = self.held.get(operation)
        if prior is None:
            return None
        assert prior[0] == head
        return PublicationResult("existing", inline=True)

    def finding(self, operation, epoch, head, text, **kwargs):
        del kwargs
        assert epoch == 3
        prior = self.held.get(operation)
        if prior is not None:
            assert prior == (head, text)
            return PublicationResult("existing", inline=True)
        self.posts += 1
        self.held[operation] = head, text
        return PublicationResult("created", inline=True)


class RerunLedger:
    def __init__(self) -> None:
        self.held_operations: set[str] = set()
        self.posts = 0

    def held(self, run_id: int, head: str, operation: str):
        assert (run_id, head) == (RERUN.run_id, HEAD)
        return PublicationResult("existing") if operation in self.held_operations else None

    def issue(self, run: ActionsRunSnapshot, *, epoch: int, operation: str):
        assert (run.id, run.head, epoch) == (RERUN.run_id, HEAD, 3)
        if operation in self.held_operations:
            return RerunIssue(PublicationResult("existing"), run.id, run.attempt)
        self.posts += 1
        self.held_operations.add(operation)
        return RerunIssue(PublicationResult("requested"), run.id, run.attempt)


class ReminderLedger:
    def __init__(self) -> None:
        self.held_operations: set[str] = set()
        self.posts = 0

    def reminder_operation(self, operation: str, *, context):
        if operation in self.held_operations:
            return PublicationResult("existing")
        assert context() == (3, HEAD, None, "author")
        self.posts += 1
        self.held_operations.add(operation)
        return PublicationResult("created")


class RunsPort:
    def __init__(self) -> None:
        self.readable = True

    def __call__(self, head: str) -> tuple[ActionsRunSnapshot, ...]:
        if not self.readable:
            raise AssertionError("lookup-first recovery read workflow runs")
        return (ActionsRunSnapshot(RERUN.run_id, head, "ci.yml", RERUN.attempt, "completed", "failure"),)


class MutationLedgerRunner:
    def __init__(self) -> None:
        self.held: dict[str, tuple[object, CodingResult]] = {}
        self.calls = 0
        self.executions = 0

    def code(self, repository_url, request, *, operation, attempt, is_current=None):
        assert repository_url == "https://example.test/owner/repo.git" and attempt == 1
        assert is_current is not None and is_current()
        self.calls += 1
        prior = self.held.get(operation)
        if prior is not None:
            assert prior[0] == request
            return prior[1]
        self.executions += 1
        result = CodingResult(
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
        self.held[operation] = request, result
        return result


class MutationLedgerPublisher:
    def __init__(self) -> None:
        self.held: dict[str, tuple[str, str]] = {}
        self.advances = 0
        self.crash_before_publish = False

    def reconcile(self, *, operation, payload_digest, expected_head, **kwargs):
        del kwargs
        prior = self.held.get(operation)
        if prior is None:
            return GitReconciliation("absent", expected_head)
        assert prior[0] == payload_digest
        return GitReconciliation("existing", prior[1], prior[1], (expected_head,))

    def publish(self, result, *, operation, payload_digest, expected_head, **kwargs):
        del result, kwargs
        if self.crash_before_publish:
            self.crash_before_publish = False
            raise SimulatedProcessDeath
        self.advances += 1
        self.held[operation] = payload_digest, NEW_HEAD
        assert expected_head == HEAD
        return GitPublishResult(NEW_HEAD)


def _definitions(activity_name: str, implementation: Callable[..., object]) -> dict[str, ActivityDefinition]:
    definitions = {definition.declaration.name: definition for definition in make_activities(fresh_world())}
    definitions[activity_name] = activity(
        implementation,
        name=activity_name,
        converter=VariantPayloadConverter(),
    )
    return definitions


def _open(
    root: Path,
    definitions: Mapping[str, ActivityDefinition],
    dispatch: Dispatch,
    *,
    create: bool,
    place: str = "",
    work: WorkflowModel | None = None,
) -> Engine:
    built = build_net_v5()
    options = {
        "history": JsonlHistoryStore(root / "history.jsonl"),
        "dispatch": dispatch,
        "handlers": wire_gates(built, GATES, definitions, DERIVED),
        "guards": dict(built.guards),
        "activities": tuple(definition.declaration for definition in definitions.values()),
        "policy": choose_throughput,
    }
    if create:
        assert work is not None
        marking = Marking().deposit(NetPath(place), Token(type(work).__name__, work.dump()))
        return Engine.create(built.net, INSTANCE, marking=marking, **options)
    return Engine.load(built.net, INSTANCE, **options)


def _drain(engine: Engine, limit: int = 100) -> None:
    for _ in range(limit):
        if not engine.advance().ready:
            return
    raise AssertionError("V5 inline recovery fixture did not quiesce")


def _request(
    root: Path,
    definitions: Mapping[str, ActivityDefinition],
    activity_name: str,
    place: str,
    work: WorkflowModel,
) -> ActivityRequested:
    dispatch = CrashCutDispatch(definitions, "hold")
    engine = _open(root, definitions, dispatch, create=True, place=place, work=work)
    _drain(engine)
    [requested] = [
        record
        for record in engine.records
        if isinstance(record, ActivityRequested) and record.activity == activity_name
    ]
    [(occurrence, invocation)] = dispatch.invocations
    assert occurrence == requested.occurrence
    assert invocation == ActivityInvocation(
        activity_name,
        input={"work": work.dump()},
        policy=ExecutionPolicy(attempts=1),
        correlation=requested.correlation,
        idempotency=requested.idempotency,
    )
    engine.close()
    return requested


def _restart(
    root: Path,
    definitions: Mapping[str, ActivityDefinition],
    mode: str,
    requested: ActivityRequested,
) -> tuple[Engine, CrashCutDispatch]:
    dispatch = CrashCutDispatch(definitions, mode)
    engine = _open(root, definitions, dispatch, create=False)
    engine.advance()
    [(occurrence, invocation)] = dispatch.invocations
    assert occurrence == requested.occurrence
    assert invocation.input == requested.input
    assert invocation.policy == requested.policy
    assert invocation.correlation == requested.correlation
    assert invocation.idempotency == requested.idempotency
    return engine, dispatch


def _finish_and_prove_stable(
    root: Path,
    definitions: Mapping[str, ActivityDefinition],
    requested: ActivityRequested,
) -> None:
    engine, _ = _restart(root, definitions, "complete", requested)
    _drain(engine)
    completed = [
        record
        for record in engine.records
        if isinstance(record, ActivityCompleted) and record.occurrence == requested.occurrence
    ]
    assert len(completed) == 1
    terminal_records = engine.records
    engine.close()

    dispatch = CrashCutDispatch(definitions, "complete")
    stable = _open(root, definitions, dispatch, create=False)
    stable.advance()
    assert stable.records == terminal_records
    assert dispatch.invocations == []
    stable.close()


def test_review_agent_redispatches_one_frozen_global_operation_without_a_second_agent_execution(tmp_path: Path) -> None:
    runner = ReviewLedgerRunner()
    authority = ReviewAuthority()
    requests = V5ReviewRequestStore(tmp_path / "review-requests.sqlite3")
    gate = V5ReviewGate(
        "owner/repo",
        7,
        authority,
        runner,
        "https://example.test/owner/repo.git",
        "ci.yml",
        ClaimPort(),
        requests,
    )
    definitions = _definitions("review_agent", gate.review_agent)
    requested = _request(tmp_path, definitions, "review_agent", "review.round", ROUND)
    assert requested.correlation == requested.idempotency == ROUND.operation

    first, _ = _restart(tmp_path, definitions, "discard", requested)
    assert runner.executions == 1 and list(runner.held) == [ROUND.operation]
    assert authority.reads == 2
    first.close()
    requests.close()

    authority.readable = False
    requests = V5ReviewRequestStore(tmp_path / "review-requests.sqlite3")
    replay_gate = replace(gate, requests=requests)
    replay_definitions = _definitions("review_agent", replay_gate.review_agent)
    second, _ = _restart(tmp_path, replay_definitions, "discard", requested)
    assert runner.executions == 1 and runner.calls == 2
    assert authority.reads == 2
    second.close()

    _finish_and_prove_stable(tmp_path, replay_definitions, requested)
    assert runner.executions == 1 and runner.calls == 3
    requests.close()


def test_findings_publication_reconciles_before_moved_authority_after_two_lost_terminals(tmp_path: Path) -> None:
    claim = ClaimPort()
    ledger = FindingsLedger()
    gate = V5PublicationGates(ledger, claim, lambda: (None, "author"))
    definitions = _definitions("publish_gate", gate.publish_gate)
    requested = _request(tmp_path, definitions, "publish_gate", "review.publishable", PUBLICATION)
    assert requested.correlation == requested.idempotency == PUBLICATION.op

    first, _ = _restart(tmp_path, definitions, "discard", requested)
    assert ledger.posts == 1 and list(ledger.held) == [f"{PUBLICATION.op}:f1"]
    first.close()
    claim.readable = False
    second, _ = _restart(tmp_path, definitions, "discard", requested)
    assert ledger.posts == 1
    second.close()

    _finish_and_prove_stable(tmp_path, definitions, requested)
    assert ledger.posts == 1


def test_rerun_reconciles_before_claim_and_runs_reads_after_two_lost_terminals(tmp_path: Path) -> None:
    claim, runs, ledger = ClaimPort(), RunsPort(), RerunLedger()
    gate = V5RerunGate(ledger, runs, claim)
    definitions = _definitions("rerun_gate", gate.rerun_gate)
    requested = _request(tmp_path, definitions, "rerun_gate", "esc.rerun_req", RERUN)
    assert requested.correlation == requested.idempotency == RERUN.op

    first, _ = _restart(tmp_path, definitions, "discard", requested)
    assert ledger.posts == 1 and ledger.held_operations == {RERUN.op}
    first.close()
    claim.readable = runs.readable = False
    second, _ = _restart(tmp_path, definitions, "discard", requested)
    assert ledger.posts == 1
    second.close()

    _finish_and_prove_stable(tmp_path, definitions, requested)
    assert ledger.posts == 1


def test_reminder_reconciles_before_claim_and_recipient_reads_after_two_lost_terminals(tmp_path: Path) -> None:
    claim, ledger = ClaimPort(), ReminderLedger()
    gate = V5PublicationGates(ledger, claim, lambda: (None, "author"))
    definitions = _definitions("reminder_gate", gate.reminder_gate)
    requested = _request(tmp_path, definitions, "reminder_gate", "rem.pub_req", REMINDER)
    operation = f"reminder:{REMINDER.timer_id}"
    assert requested.correlation == requested.idempotency == operation
    assert requested.policy == ExecutionPolicy(attempts=1)

    first, _ = _restart(tmp_path, definitions, "discard", requested)
    assert ledger.posts == 1 and ledger.held_operations == {operation}
    first.close()
    claim.readable = False
    second, _ = _restart(tmp_path, definitions, "discard", requested)
    assert ledger.posts == 1
    second.close()

    _finish_and_prove_stable(tmp_path, definitions, requested)
    assert ledger.posts == 1


def test_mutation_replays_one_agent_result_then_reconciles_one_ref_advance(tmp_path: Path) -> None:
    claim, runner, publisher = ClaimPort(), MutationLedgerRunner(), MutationLedgerPublisher()
    gate = V5MutationGate(
        "owner/repo",
        7,
        runner,
        publisher,
        "https://example.test/owner/repo.git",
        claim,
    )
    definitions = _definitions("git_gate", gate.git_gate)
    requested = _request(tmp_path, definitions, "git_gate", "mut.work", MUTATION)
    assert requested.correlation == requested.idempotency == MUTATION.op_key

    publisher.crash_before_publish = True
    first, dispatch = _restart(tmp_path, definitions, "discard", requested)
    assert dispatch.crashes == 1 and runner.executions == 1 and publisher.advances == 0
    first.close()

    second, _ = _restart(tmp_path, definitions, "discard", requested)
    assert runner.executions == 1 and runner.calls == 2 and publisher.advances == 1
    second.close()
    claim.readable = False

    _finish_and_prove_stable(tmp_path, definitions, requested)
    assert runner.executions == 1 and runner.calls == 2 and publisher.advances == 1
    [(agent_operation, (agent_request, _))] = list(runner.held.items())
    assert agent_operation == f"mutation:owner/repo:pr:7:{MUTATION.op_key}"
    assert asdict(agent_request)["head"] == HEAD


def test_unexpected_inline_failure_stays_a_loud_activity_failure(tmp_path: Path) -> None:
    def explode(work: RoundOpen) -> AgentReview | RoundUnable:
        del work
        raise RuntimeError("unexpected provider bug")

    definitions = _definitions("review_agent", explode)
    engine = _open(
        tmp_path,
        definitions,
        InlineDispatch(definitions),
        create=True,
        place="review.round",
        work=ROUND,
    )

    with pytest.raises(RuntimeError, match="failed terminally.*unexpected provider bug"):
        _drain(engine)

    engine.close()
    records = JsonlHistoryStore(tmp_path / "history.jsonl").records
    [requested] = [record for record in records if isinstance(record, ActivityRequested)]
    [failed] = [record for record in records if isinstance(record, ActivityFailed)]
    assert failed.occurrence == requested.occurrence and failed.kind == "RuntimeError"
    assert any(isinstance(record, FiringFailed) and record.occurrence == requested.occurrence for record in records)


@pytest.mark.parametrize(
    ("activity_name", "place", "work"),
    [
        ("review_agent", "review.round", replace(ROUND, operation="")),
        ("publish_gate", "review.publishable", replace(PUBLICATION, op="")),
        ("rerun_gate", "esc.rerun_req", replace(RERUN, op="")),
        ("reminder_gate", "rem.pub_req", replace(REMINDER, timer_id="")),
        ("git_gate", "mut.work", replace(MUTATION, op_key="")),
        ("publish_gate", "review.publishable", replace(PUBLICATION, effect="findings:different:i3")),
    ],
)
def test_inline_recovery_identity_contract_rejects_malformed_work_before_dispatch(
    tmp_path: Path,
    activity_name: str,
    place: str,
    work: WorkflowModel,
) -> None:
    definitions = {definition.declaration.name: definition for definition in make_activities(fresh_world())}
    dispatch = CrashCutDispatch(definitions, "hold")
    engine = _open(tmp_path, definitions, dispatch, create=True, place=place, work=work)

    with pytest.raises(ValueError, match="identity|effect"):
        _drain(engine)

    assert dispatch.invocations == []
    engine.close()


@pytest.mark.parametrize("identity", ["has space", "line\nbreak", "réview", "x" * 1025])
@pytest.mark.parametrize(
    ("activity_name", "place", "work"),
    [
        ("review_agent", "review.round", ROUND),
        ("publish_gate", "review.publishable", PUBLICATION),
        ("rerun_gate", "esc.rerun_req", RERUN),
        ("reminder_gate", "rem.pub_req", REMINDER),
        ("git_gate", "mut.work", MUTATION),
    ],
)
def test_inline_recovery_identity_contract_rejects_noncanonical_provider_identities(
    tmp_path: Path,
    identity: str,
    activity_name: str,
    place: str,
    work: WorkflowModel,
) -> None:
    if isinstance(work, RoundOpen):
        malformed = replace(work, operation=identity)
    elif isinstance(work, Publishable):
        malformed = replace(work, effect=identity, op=identity)
    elif isinstance(work, RerunReq):
        malformed = replace(work, op=identity)
    elif isinstance(work, RemReq):
        malformed = replace(work, timer_id=identity)
    elif isinstance(work, MutWork):
        malformed = replace(work, op_key=identity)
    else:
        raise TypeError(f"unsupported test work {type(work).__name__}")
    definitions = {definition.declaration.name: definition for definition in make_activities(fresh_world())}
    dispatch = CrashCutDispatch(definitions, "hold")
    engine = _open(tmp_path, definitions, dispatch, create=True, place=place, work=malformed)

    with pytest.raises(ValueError, match="identity"):
        _drain(engine)

    assert dispatch.invocations == []
    engine.close()


@pytest.mark.parametrize(
    ("activity_name", "place", "work"),
    [
        ("publish_gate", "review.publishable", replace(PUBLICATION, effect="x" * 129, op="x" * 129)),
        ("rerun_gate", "esc.rerun_req", replace(RERUN, op="x" * 129)),
        ("reminder_gate", "rem.pub_req", replace(REMINDER, timer_id="x" * 129)),
    ],
)
def test_comment_backed_inline_identity_honors_the_provider_marker_bound(
    tmp_path: Path,
    activity_name: str,
    place: str,
    work: WorkflowModel,
) -> None:
    definitions = {definition.declaration.name: definition for definition in make_activities(fresh_world())}
    dispatch = CrashCutDispatch(definitions, "hold")
    engine = _open(tmp_path, definitions, dispatch, create=True, place=place, work=work)

    with pytest.raises(ValueError, match="identity"):
        _drain(engine)

    assert dispatch.invocations == []
    engine.close()
