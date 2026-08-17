from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256

import pytest
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.runtime.operation import (
    RuntimeCleanupDisposition,
    RuntimeOperationCleanup,
    RuntimeProtocolError,
)
from petrus.agenticus.runtime.pi_a2_host import PiA2RuntimePolicy, PiA2RuntimeStart
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome

from hamsterdan.agents import (
    AgentCleanupCategory,
    AgentProtocolError,
    AgentResultCategory,
    CodingRequest,
    ConversationRequest,
    PiNativeRunner,
    ReviewRequest,
    encode_prompt,
)
from hamsterdan.agents.pi import PiWorkspaceCleanupError
from hamsterdan.contracts.readiness import ChangeRequest, Intent
from hamsterdan.host.activities import PrReadinessActivities
from hamsterdan.host.git_publish import GitPublishResult

HEAD, BASE = "a" * 40, "b" * 40
URL = "https://example.invalid/owner/repo.git"
WORKSPACE_ARCHIVE = b"\0" * 10240
READ_POLICY = PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ}))


def pi_operation(operation: str, attempt: int = 1) -> str:
    return f"pi:{sha256(f'{operation}\0{attempt}'.encode()).hexdigest()}"


class Workspace:
    archive = WORKSPACE_ARCHIVE
    digest = sha256(archive).hexdigest()
    correlation = "synthetic-workspace"
    policy = READ_POLICY

    def __init__(self, changed: list[str] | None = None) -> None:
        self.changed = changed or []
        self.received: list[bytes] = []

    def reconcile(self, archive: bytes) -> tuple[str, list[str]]:
        self.received.append(archive)
        return ("canonical diff" if self.changed else "", self.changed)


class Workspaces:
    def __init__(self, changed: list[str] | None = None) -> None:
        self.workspace = Workspace(changed)
        self.opens: list[tuple[str, str]] = []

    @contextmanager
    def open(self, kind, repository_url, request, operation_id):
        self.opens.append((kind, operation_id))
        yield self.workspace


def review_request() -> ReviewRequest:
    return ReviewRequest("owner/repo", 7, 2, HEAD, BASE, "diff.patch", review_lenses=["correctness"])


def conversation_request() -> ConversationRequest:
    return ConversationRequest(
        "owner/repo",
        7,
        2,
        HEAD,
        BASE,
        {"text": "status"},
        {"id": 1, "login": "human"},
        {"review": "clear"},
        [{"name": "overall", "ready": True}],
        [],
        [{"type": "status", "arguments": [], "mutation": False}],
    )


def coding_request() -> CodingRequest:
    return CodingRequest("change", "owner/repo", 7, 2, HEAD, BASE, "hamsterdan/change/one")


def activity_coding_result(operation: str, *, status: str = "unchanged", head: str = HEAD) -> dict[str, object]:
    changed = status == "changed"
    return {
        "kind": "change",
        "repository": "owner/repo",
        "pull_request": 7,
        "epoch": 2,
        "head": head,
        "base": BASE,
        "ref": f"hamsterdan/change/{operation[-16:]}",
        "status": status,
        "reproduction_status": "not_attempted",
        "diff": "untrusted" if changed else "",
        "changed_files": ["bounded.txt"] if changed else [],
        "validation_evidence": [{"check": "passed"}] if changed else [],
        "proposed_commit_message": "Apply bounded change" if changed else "",
    }


class ActivityPublisher:
    def __init__(self) -> None:
        self.calls = 0
        self.result = None

    def publish(self, result, **kwargs):
        self.calls += 1
        self.result = result
        return GitPublishResult("c" * 40)


def run_coding_activity(subject: PiNativeRunner, runtime: Runtime, operation: str):
    publisher = ActivityPublisher()
    activities = object.__new__(PrReadinessActivities)
    activities.repository = "owner/repo"
    activities.pr_number = 7
    activities.public_clone_url = URL
    activities.current = None
    activities.current_fence = lambda *args: None
    activities.runner = subject
    activities.git_publisher = publisher
    work = ChangeRequest(2, HEAD, operation, BASE, "policy", Intent(2, HEAD, "change", "digest", True, True))
    return activities.change(work), publisher


@pytest.mark.parametrize(
    ("kind", "agent_request"),
    [("review", review_request()), ("conversation", conversation_request()), ("coding", coding_request())],
)
def test_prompts_are_exact_canonical_and_bounded(kind: str, agent_request: object) -> None:
    prompt = encode_prompt(kind, URL, agent_request)  # type: ignore[arg-type]
    assert prompt == encode_prompt(kind, URL, agent_request)  # type: ignore[arg-type]
    assert prompt == json.dumps(json.loads(prompt), sort_keys=True, separators=(",", ":"))
    assert json.loads(prompt) == {
        "instructions": json.loads(prompt)["instructions"],
        "kind": kind,
        "repository_url": URL,
        "request": asdict(agent_request),  # type: ignore[arg-type]
        "response": "one JSON object matching the unchanged Hamsterdan result schema; no Markdown or prose",
        "schema_version": 1,
    }
    assert len(prompt.encode()) <= 64 * 1024


class Operation:
    def __init__(self, operation: str, *, outcome: TurnOutcome = TurnOutcome.COMPLETED, clean: bool = True):
        self.operation_id = operation
        self.outcome, self.clean = outcome, clean
        self.waits = 0
        self.cancellations: list[str] = []
        self.closed = 0
        self.episode_id = EpisodeId("unset")
        self.turn_id = TurnId("unset")

    def wait(self, timeout=None):
        self.waits += 1
        return RuntimeTurnSettlement(
            self.episode_id,
            self.turn_id,
            self.outcome,
            1 if self.outcome is TurnOutcome.COMPLETED else 0,
            "turn-completed" if self.outcome is TurnOutcome.COMPLETED else "runtime-failed",
            "output:one" if self.outcome is TurnOutcome.COMPLETED else None,
        )

    def cancel(self, reason):
        self.cancellations.append(reason)
        return CancellationDisposition.REQUESTED

    def close(self):
        self.closed += 1
        return RuntimeOperationCleanup(
            self.operation_id,
            RuntimeCleanupDisposition.CLEAN if self.clean else RuntimeCleanupDisposition.UNVERIFIED,
            "client-closed" if self.clean else "cleanup-uncertain",
        )


class TimeoutThenCompleteOperation(Operation):
    def __init__(self, operation: str, elapsed: list[float]) -> None:
        super().__init__(operation)
        self.elapsed = elapsed
        self.wait_timeouts: list[float | None] = []

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        if len(self.wait_timeouts) == 1:
            self.elapsed[0] = 301
            raise TimeoutError
        return super().wait(timeout)


class BrokenIdentityOperation(Operation):
    def __init__(self, operation: str) -> None:
        self._operation_id = operation
        self.identity_broken = False
        super().__init__(operation)

    @property
    def operation_id(self) -> str:
        if self.identity_broken:
            raise RuntimeError("private runtime identity diagnostic")
        return self._operation_id

    @operation_id.setter
    def operation_id(self, value: str) -> None:
        self._operation_id = value

    def close(self):
        self.closed += 1
        return RuntimeOperationCleanup(
            self._operation_id,
            RuntimeCleanupDisposition.CLEAN,
            "client-closed",
        )


class Runtime:
    def __init__(self, operation: Operation, output: str = "{}", archive: bytes = b"archive"):
        self.operation = operation
        self.output = output
        self.archive = archive
        self.started: list[PiA2RuntimeStart] = []
        self.loaded_outputs: list[str] = []
        self.loaded_archives: list[str] = []
        self.workspaces = Workspaces()

    def start(self, value):
        self.started.append(value)
        self.operation.episode_id = value.episode_id
        self.operation.turn_id = value.turn_id
        return self.operation

    def load_output(self, reference: str) -> str:
        self.loaded_outputs.append(reference)
        return self.output

    def load_workspace_archive(self, operation_id: str) -> bytes:
        self.loaded_archives.append(operation_id)
        return self.archive


def runner(result: dict[str, object], operation: Operation | None = None) -> tuple[PiNativeRunner, Runtime]:
    selected = operation or Operation("review:one")
    selected.operation_id = pi_operation(selected.operation_id)
    runtime = Runtime(selected, json.dumps(result))
    changed = result.get("changed_files")
    workspaces = Workspaces(changed if isinstance(changed, list) else None)  # type: ignore[arg-type]
    runtime.workspaces = workspaces
    value = PiNativeRunner(runtime, workspaces)  # type: ignore[arg-type]
    return value, runtime


def test_review_waits_reads_strict_result_and_closes_verified_operation() -> None:
    request = review_request()
    result = {
        **{name: getattr(request, name) for name in ("repository", "pull_request", "epoch", "head", "base")},
        "status": "clear",
        "findings": [],
        "lineage": [],
    }
    subject, runtime = runner(result)

    assert subject.review(URL, request, operation="review:one", attempt=1).status == "clear"
    assert len(runtime.started) == 1
    assert runtime.started[0].prompt == encode_prompt("review", URL, request)
    assert runtime.started[0].workspace_archive == WORKSPACE_ARCHIVE
    assert runtime.started[0].operation_id == pi_operation("review:one")
    assert runtime.started[0].workspace_digest == sha256(WORKSPACE_ARCHIVE).hexdigest()
    assert runtime.started[0].workspace_correlation == "synthetic-workspace"
    assert runtime.started[0].policy is READ_POLICY
    assert runtime.operation.waits == 1 and runtime.operation.closed == 1


def test_logical_operation_and_attempt_derive_stable_distinct_pi_execution_identities() -> None:
    request = review_request()
    output = json.dumps(
        {
            **{name: getattr(request, name) for name in ("repository", "pull_request", "epoch", "head", "base")},
            "status": "clear",
            "findings": [],
            "lineage": [],
        }
    )
    started: list[str] = []

    for attempt in (1, 2):
        operation = Operation(pi_operation("review:attempts", attempt))
        runtime = Runtime(operation, output)
        workspaces = Workspaces()
        runtime.workspaces = workspaces
        subject = PiNativeRunner(runtime, workspaces)  # type: ignore[arg-type]

        assert subject.review(URL, request, operation="review:attempts", attempt=attempt).status == "clear"
        started.append(runtime.started[0].operation_id)

    assert started == [pi_operation("review:attempts", 1), pi_operation("review:attempts", 2)]


def test_conversation_and_code_preserve_strict_output_correlation() -> None:
    conversation = conversation_request()
    intent = {
        "type": "status",
        "arguments": {},
        "mutation": False,
        "explicit": True,
        "confidence": 1,
    }
    conversation_result = {
        **{name: getattr(conversation, name) for name in ("repository", "pull_request", "epoch", "head", "base")},
        "intents": [intent],
    }
    subject, _ = runner(conversation_result, Operation("conversation:one"))
    assert subject.converse(URL, conversation, operation="conversation:one", attempt=1).intents == [intent]

    coding = coding_request()
    coding_result = {
        **{
            name: getattr(coding, name)
            for name in ("kind", "repository", "pull_request", "epoch", "head", "base", "ref")
        },
        "status": "unchanged",
        "reproduction_status": "not_attempted",
        "diff": "",
        "changed_files": [],
        "validation_evidence": [],
        "proposed_commit_message": "",
    }
    subject, _ = runner(coding_result, Operation("code:one"))
    assert subject.code(URL, coding, operation="code:one", attempt=1).status == "unchanged"
    mismatched = dict(coding_result, head="c" * 40)
    subject, _ = runner(mismatched, Operation("code:two"))
    with pytest.raises(AgentProtocolError, match="correlation"):
        subject.code(URL, coding, operation="code:two", attempt=1)


def test_malformed_output_and_operation_identity_mismatch_fail_closed() -> None:
    request = review_request()
    malformed_operation = Operation(pi_operation("review:malformed"))
    runtime = Runtime(malformed_operation)
    runtime.output = "not-json"
    malformed = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    with pytest.raises(AgentProtocolError, match="malformed JSON"):
        malformed.review(URL, request, operation="review:malformed", attempt=1)
    assert malformed_operation.closed == 1

    mismatched_operation = Operation("review:other")
    runtime = Runtime(mismatched_operation)
    mismatched = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    with pytest.raises(AgentProtocolError, match="identity mismatched"):
        mismatched.review(URL, request, operation="review:expected", attempt=1)
    assert mismatched_operation.cancellations == ["operation-mismatch"]
    assert mismatched_operation.closed == 1


def test_runtime_never_starts_without_valid_explicit_operation_identity() -> None:
    runtime = Runtime(Operation("review:unclaimed"))
    subject = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]

    with pytest.raises(AgentProtocolError, match="invalid operation"):
        subject.review(URL, review_request(), operation="", attempt=1)

    assert runtime.started == []


def test_authority_is_rechecked_after_workspace_preparation_before_start() -> None:
    runtime = Runtime(Operation(pi_operation("review:stale-preparation")))
    subject = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    current = iter((True, False))

    with pytest.raises(AgentProtocolError) as caught:
        subject.review(
            URL, review_request(), operation="review:stale-preparation", attempt=1, is_current=lambda: next(current)
        )

    assert caught.value.canceled
    assert runtime.started == []


def test_stable_start_identity_and_failed_preflight_cannot_start_or_reuse_route() -> None:
    runtime = Runtime(Operation(pi_operation("review:expected")))
    subject = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    with pytest.raises(AgentProtocolError):
        subject.review(URL, review_request(), operation="review:expected", attempt=1)
    first = runtime.started[0]
    replay_runtime = Runtime(Operation(pi_operation("review:expected")))
    replay = PiNativeRunner(replay_runtime, replay_runtime.workspaces)  # type: ignore[arg-type]
    with pytest.raises(AgentProtocolError):
        replay.review(URL, review_request(), operation="review:expected", attempt=1)
    second = replay_runtime.started[0]
    assert (first.operation_id, first.episode_id, first.turn_id) == (
        second.operation_id,
        second.episode_id,
        second.turn_id,
    )

    subject = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    with pytest.raises(AgentProtocolError, match="repository URL"):
        subject.review("https://user@example.invalid/repo", review_request(), operation="review:preflight", attempt=1)
    with pytest.raises(AgentProtocolError, match="identity mismatched"):
        subject.review(URL, review_request(), operation="review:preflight", attempt=1)
    assert len(runtime.started) == 2


def test_stale_timeout_failure_and_unverified_cleanup_fail_safe() -> None:
    request = review_request()
    result = {
        **{name: getattr(request, name) for name in ("repository", "pull_request", "epoch", "head", "base")},
        "status": "clear",
        "findings": [],
        "lineage": [],
    }
    stale = Operation("review:stale")
    subject, _ = runner(result, stale)
    current = iter((True, True, False))
    stale.wait = lambda timeout=None: (_ for _ in ()).throw(TimeoutError())  # type: ignore[method-assign]
    with pytest.raises(AgentProtocolError) as caught:
        subject.review(URL, request, operation="review:stale", attempt=1, is_current=lambda: next(current))
    assert caught.value.canceled and stale.cancellations == ["stale-authority"] and stale.closed == 1

    failed = Operation("review:failed", outcome=TurnOutcome.FAILED)
    subject, _ = runner(result, failed)
    with pytest.raises(AgentProtocolError, match="completed result"):
        subject.review(URL, request, operation="review:failed", attempt=1)
    assert failed.closed == 1

    unverified = Operation("review:unclean", clean=False)
    subject, _ = runner(result, unverified)
    with pytest.raises(AgentProtocolError, match="cleanup is unverified"):
        subject.review(URL, request, operation="review:unclean", attempt=1)


def test_default_runner_admits_completion_after_the_retired_outer_timeout() -> None:
    request = review_request()
    result = {
        **{name: getattr(request, name) for name in ("repository", "pull_request", "epoch", "head", "base")},
        "status": "clear",
        "findings": [],
        "lineage": [],
    }
    elapsed = [0.0]
    operation = TimeoutThenCompleteOperation(pi_operation("review:long-running"), elapsed)
    runtime = Runtime(operation, json.dumps(result))
    subject = PiNativeRunner(runtime, runtime.workspaces, clock=lambda: elapsed[0])  # type: ignore[arg-type]

    assert subject.review(URL, request, operation="review:long-running", attempt=1).status == "clear"
    assert operation.wait_timeouts == [0.1, 0.1]
    assert operation.cancellations == []
    assert operation.closed == 1


def test_stale_authority_is_polled_between_bounded_waits() -> None:
    operation = Operation(pi_operation("review:stale-wait"))
    wait_timeouts: list[float | None] = []

    def wait(timeout=None):
        wait_timeouts.append(timeout)
        raise TimeoutError

    operation.wait = wait  # type: ignore[method-assign]
    runtime = Runtime(operation)
    subject = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    current = iter((True, True, True, False))

    with pytest.raises(AgentProtocolError) as caught:
        subject.review(
            URL, review_request(), operation="review:stale-wait", attempt=1, is_current=lambda: next(current)
        )

    assert caught.value.canceled
    assert wait_timeouts == [0.1]
    assert operation.cancellations == ["stale-authority"]
    assert runtime.loaded_outputs == []
    assert operation.closed == 1


def test_authority_lost_during_settlement_is_not_admitted() -> None:
    request = review_request()
    operation = Operation(pi_operation("review:stale-settlement"))
    runtime = Runtime(
        operation,
        json.dumps(
            {
                **{name: getattr(request, name) for name in ("repository", "pull_request", "epoch", "head", "base")},
                "status": "clear",
                "findings": [],
                "lineage": [],
            }
        ),
    )
    subject = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    current = iter((True, True, True, False))

    with pytest.raises(AgentProtocolError) as caught:
        subject.review(
            URL,
            request,
            operation="review:stale-settlement",
            attempt=1,
            is_current=lambda: next(current),
        )

    assert caught.value.canceled
    assert operation.cancellations == ["stale-authority"]
    assert runtime.loaded_outputs == []
    assert operation.closed == 1


def test_timeout_cancels_before_verified_close() -> None:
    operation = Operation(pi_operation("review:timeout"))
    operation.wait = lambda timeout=None: (_ for _ in ()).throw(TimeoutError())  # type: ignore[method-assign]
    runtime = Runtime(operation)
    clock = iter((0.0, 2.0))
    subject = PiNativeRunner(runtime, runtime.workspaces, timeout=1, clock=lambda: next(clock))  # type: ignore[arg-type]
    with pytest.raises(AgentProtocolError) as caught:
        subject.review(URL, review_request(), operation="review:timeout", attempt=1)

    assert caught.value.timed_out
    assert operation.cancellations == ["host-timeout"]
    assert operation.closed == 1


@pytest.mark.parametrize(
    ("timeout", "poll_interval"),
    [
        (0, 0.1),
        (-1, 0.1),
        (float("nan"), 0.1),
        (float("inf"), 0.1),
        (True, 0.1),
        ("1", 0.1),
        (0.05, 0.1),
        (None, 0),
        (None, -1),
        (None, float("nan")),
        (None, float("inf")),
        (None, True),
        (None, "0.1"),
    ],
)
def test_runner_rejects_nonfinite_or_unordered_wait_policy(timeout: object, poll_interval: object) -> None:
    runtime = Runtime(Operation("unused"))

    with pytest.raises(ValueError, match="timeout and poll interval"):
        PiNativeRunner(runtime, runtime.workspaces, timeout=timeout, poll_interval=poll_interval)  # type: ignore[arg-type]


def test_coding_archive_policy_derives_unchanged_and_changed_or_rejects_missing_archive() -> None:
    request = coding_request()
    base = {
        **{
            name: getattr(request, name)
            for name in ("kind", "repository", "pull_request", "epoch", "head", "base", "ref")
        },
        "reproduction_status": "not_attempted",
        "diff": "",
        "changed_files": [],
        "validation_evidence": [],
        "proposed_commit_message": "",
    }
    subject, runtime = runner(dict(base, status="unchanged"), Operation("code:archive"))
    assert subject.code(URL, request, operation="code:archive", attempt=1).status == "unchanged"
    assert runtime.loaded_archives == [pi_operation("code:archive")]

    subject, runtime = runner(
        dict(
            base,
            status="changed",
            diff="synthetic",
            changed_files=["x.py"],
            validation_evidence=[{"command": "synthetic", "result": "passed"}],
            proposed_commit_message="Apply synthetic change",
        ),
        Operation("code:changed"),
    )
    changed = subject.code(URL, request, operation="code:changed", attempt=1)
    assert changed.diff == "canonical diff" and changed.changed_files == ["x.py"]
    assert runtime.loaded_archives == [pi_operation("code:changed")]

    subject, runtime = runner(dict(base, status="unchanged"), Operation("code:missing"))
    runtime.archive = b""
    with pytest.raises(AgentProtocolError, match="archive is unavailable") as caught:
        subject.code(URL, request, operation="code:missing", attempt=1)
    assert caught.value.result_category is AgentResultCategory.WORKSPACE_RECONCILIATION

    subject, runtime = runner(dict(base, status="unchanged"), Operation("code:invalid-archive"))
    runtime.load_workspace_archive = lambda operation_id: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeProtocolError("workspace-archive-corrupt")
    )
    with pytest.raises(AgentProtocolError, match="archive is unavailable") as caught:
        subject.code(URL, request, operation="code:invalid-archive", attempt=1)
    assert caught.value.result_category is AgentResultCategory.WORKSPACE_RECONCILIATION


@pytest.mark.parametrize(
    ("case", "category"),
    [
        ("runtime", AgentResultCategory.RUNTIME_LIFECYCLE),
        ("schema", AgentResultCategory.OUTPUT_SCHEMA),
        ("correlation", AgentResultCategory.CORRELATION),
        ("workspace", AgentResultCategory.WORKSPACE_RECONCILIATION),
    ],
)
def test_coding_activity_retains_each_adapter_admission_failure_without_retry_or_publication(
    case: str, category: AgentResultCategory
) -> None:
    operation_id = f"change:admission-{case}"
    output = activity_coding_result(
        operation_id,
        head="c" * 40 if case == "correlation" else HEAD,
    )
    operation = Operation(
        operation_id,
        outcome=TurnOutcome.FAILED if case == "runtime" else TurnOutcome.COMPLETED,
    )
    subject, runtime = runner(output, operation)
    if case == "schema":
        runtime.output = "not-json private model prose"
    if case == "workspace":
        runtime.archive = b""

    effect, publisher = run_coding_activity(subject, runtime, operation_id)

    assert not effect.ok
    assert effect.agent_result_category == category
    assert effect.agent_cleanup_category == ""
    assert effect.publication_category == ""
    assert len(runtime.started) == 1
    assert publisher.calls == 0


@pytest.mark.parametrize(
    ("status", "category"),
    [
        ("unchanged", AgentResultCategory.UNCHANGED),
        ("unable", AgentResultCategory.UNABLE),
    ],
)
def test_coding_activity_retains_valid_nonmutation_outcome_without_retry_or_publication(
    status: str, category: AgentResultCategory
) -> None:
    operation_id = f"change:admission-{status}"
    subject, runtime = runner(activity_coding_result(operation_id, status=status), Operation(operation_id))

    effect, publisher = run_coding_activity(subject, runtime, operation_id)

    assert not effect.ok
    assert effect.agent_result_category == category
    assert effect.agent_cleanup_category == ""
    assert len(runtime.started) == 1
    assert publisher.calls == 0


def test_coding_activity_passes_accepted_changed_result_to_existing_publisher() -> None:
    operation_id = "change:admission-changed"
    subject, runtime = runner(activity_coding_result(operation_id, status="changed"), Operation(operation_id))

    effect, publisher = run_coding_activity(subject, runtime, operation_id)

    assert effect.ok
    assert effect.agent_result_category == "" and effect.agent_cleanup_category == ""
    assert publisher.calls == 1
    assert publisher.result is not None
    assert publisher.result.diff == "canonical diff"
    assert publisher.result.changed_files == ["bounded.txt"]
    assert len(runtime.started) == 1


def test_operation_cleanup_failure_cannot_overwrite_first_output_admission_cause() -> None:
    operation_id = "change:admission-cleanup"
    subject, runtime = runner(activity_coding_result(operation_id), Operation(operation_id, clean=False))
    runtime.output = "not-json private model prose"

    effect, publisher = run_coding_activity(subject, runtime, operation_id)

    assert not effect.ok
    assert effect.agent_result_category == AgentResultCategory.OUTPUT_SCHEMA
    assert effect.agent_cleanup_category == AgentCleanupCategory.UNVERIFIED
    assert publisher.calls == 0
    assert len(runtime.started) == 1


def test_agent_failure_categories_are_closed_and_first_cause_is_one_shot() -> None:
    with pytest.raises(TypeError, match="closed vocabulary"):
        AgentProtocolError("private diagnostic", result_category="owner/private")  # type: ignore[arg-type]
    error = AgentProtocolError("private diagnostic", result_category=AgentResultCategory.OUTPUT_SCHEMA)

    error.retain_result_category(AgentResultCategory.CORRELATION)
    error.retain_cleanup_category(AgentCleanupCategory.UNVERIFIED)

    assert error.result_category is AgentResultCategory.OUTPUT_SCHEMA
    assert error.cleanup_category is AgentCleanupCategory.UNVERIFIED


def test_workspace_preparation_and_cleanup_failure_retains_both_closed_causes() -> None:
    operation_id = "change:admission-preparation"
    runtime = Runtime(Operation(operation_id), json.dumps(activity_coding_result(operation_id)))

    class FailedWorkspaces:
        @contextmanager
        def open(self, kind, repository_url, request, operation):
            if False:
                yield
            raise PiWorkspaceCleanupError(preparation_failed=True)

    subject = PiNativeRunner(runtime, FailedWorkspaces())  # type: ignore[arg-type]

    effect, publisher = run_coding_activity(subject, runtime, operation_id)

    assert effect.agent_result_category == AgentResultCategory.WORKSPACE_RECONCILIATION
    assert effect.agent_cleanup_category == AgentCleanupCategory.UNVERIFIED
    assert runtime.started == []
    assert publisher.calls == 0


def test_throwing_runtime_identity_is_sanitized_and_still_closes() -> None:
    operation_id = "code:broken-identity"
    operation = BrokenIdentityOperation(pi_operation(operation_id))
    runtime = Runtime(operation)
    subject = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    operation.identity_broken = True

    with pytest.raises(AgentProtocolError) as caught:
        subject.code(URL, coding_request(), operation=operation_id, attempt=1)

    assert caught.value.result_category is AgentResultCategory.RUNTIME_LIFECYCLE
    assert caught.value.cleanup_category is AgentCleanupCategory.UNVERIFIED
    assert operation.closed == 1


def test_throwing_cancel_cannot_replace_correlation_or_stale_authority() -> None:
    request = coding_request()
    mismatch = Operation("code:actual")
    mismatch.cancel = lambda reason: (_ for _ in ()).throw(RuntimeError("private cancel diagnostic"))  # type: ignore[method-assign]
    runtime = Runtime(mismatch)
    subject = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    with pytest.raises(AgentProtocolError) as caught:
        subject.code(URL, request, operation="code:expected", attempt=1)

    assert caught.value.result_category is AgentResultCategory.CORRELATION
    assert mismatch.closed == 1

    stale = Operation(pi_operation("code:stale"))
    stale.cancel = lambda reason: (_ for _ in ()).throw(RuntimeError("private cancel diagnostic"))  # type: ignore[method-assign]
    runtime = Runtime(stale)
    subject = PiNativeRunner(runtime, runtime.workspaces)  # type: ignore[arg-type]
    current = iter((True, True, False))

    with pytest.raises(AgentProtocolError) as caught:
        subject.code(URL, request, operation="code:stale", attempt=1, is_current=lambda: next(current))

    assert caught.value.canceled and caught.value.result_category is None
    assert stale.closed == 1
