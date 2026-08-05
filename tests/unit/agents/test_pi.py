from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from petrus.agenticus.runtime.operation import (
    RuntimeCleanupDisposition,
    RuntimeOperationCleanup,
    RuntimeProtocolError,
)
from petrus.agenticus.runtime.pi_a2_host import PiA2RuntimeStart
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome

from hamsterdan.agents import (
    AgentProtocolError,
    CodingRequest,
    ConversationRequest,
    PiNativeRunner,
    ReviewRequest,
    encode_prompt,
)

HEAD, BASE = "a" * 40, "b" * 40
URL = "https://example.invalid/owner/repo.git"


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


class Runtime:
    def __init__(self, operation: Operation, output: str = "{}", archive: bytes = b"archive"):
        self.operation = operation
        self.output = output
        self.archive = archive
        self.started: list[PiA2RuntimeStart] = []
        self.loaded_outputs: list[str] = []
        self.loaded_archives: list[str] = []

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
    runtime = Runtime(selected, json.dumps(result))
    value = PiNativeRunner(runtime)  # type: ignore[arg-type]
    value.route_operation(selected.operation_id)
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

    assert subject.review(URL, request).status == "clear"
    assert len(runtime.started) == 1
    assert runtime.started[0].prompt == encode_prompt("review", URL, request)
    assert runtime.operation.waits == 1 and runtime.operation.closed == 1


def test_conversation_and_code_preserve_strict_output_correlation() -> None:
    conversation = conversation_request()
    intent = {
        "type": "status",
        "arguments": {},
        "mutation": False,
        "explicit": True,
        "confidence": 1,
        "confirmation": False,
    }
    conversation_result = {
        **{name: getattr(conversation, name) for name in ("repository", "pull_request", "epoch", "head", "base")},
        "intents": [intent],
    }
    subject, _ = runner(conversation_result, Operation("conversation:one"))
    assert subject.converse(URL, conversation).intents == [intent]

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
    assert subject.code(URL, coding).status == "unchanged"
    mismatched = dict(coding_result, head="c" * 40)
    subject, _ = runner(mismatched, Operation("code:two"))
    with pytest.raises(AgentProtocolError, match="correlation"):
        subject.code(URL, coding)


def test_malformed_output_and_operation_identity_mismatch_fail_closed() -> None:
    request = review_request()
    malformed_operation = Operation("review:malformed")
    runtime = Runtime(malformed_operation)
    runtime.output = "not-json"
    malformed = PiNativeRunner(runtime)  # type: ignore[arg-type]
    malformed.route_operation(malformed_operation.operation_id)
    with pytest.raises(AgentProtocolError, match="malformed JSON"):
        malformed.review(URL, request)
    assert malformed_operation.closed == 1

    mismatched_operation = Operation("review:other")
    runtime = Runtime(mismatched_operation)
    mismatched = PiNativeRunner(runtime)  # type: ignore[arg-type]
    mismatched.route_operation("review:expected")
    with pytest.raises(AgentProtocolError, match="identity mismatched"):
        mismatched.review(URL, request)
    assert mismatched_operation.cancellations == ["operation-mismatch"]
    assert mismatched_operation.closed == 1


def test_runtime_never_starts_without_a_claimed_route() -> None:
    runtime = Runtime(Operation("review:unclaimed"))
    subject = PiNativeRunner(runtime)  # type: ignore[arg-type]

    with pytest.raises(AgentProtocolError, match="route was not selected"):
        subject.review(URL, review_request())

    assert runtime.started == []


def test_stable_start_identity_and_failed_preflight_cannot_start_or_reuse_route() -> None:
    runtime = Runtime(Operation("review:expected"))
    subject = PiNativeRunner(runtime)  # type: ignore[arg-type]
    subject.route_operation("review:expected")
    with pytest.raises(AgentProtocolError):
        subject.review(URL, review_request())
    first = runtime.started[0]
    replay_runtime = Runtime(Operation("review:expected"))
    replay = PiNativeRunner(replay_runtime)  # type: ignore[arg-type]
    replay.route_operation("review:expected")
    with pytest.raises(AgentProtocolError):
        replay.review(URL, review_request())
    second = replay_runtime.started[0]
    assert (first.operation_id, first.episode_id, first.turn_id) == (
        second.operation_id,
        second.episode_id,
        second.turn_id,
    )

    subject = PiNativeRunner(runtime)  # type: ignore[arg-type]
    subject.route_operation("review:preflight")
    with pytest.raises(AgentProtocolError, match="repository URL"):
        subject.review("https://user@example.invalid/repo", review_request())
    with pytest.raises(AgentProtocolError, match="route was not selected"):
        subject.review(URL, review_request())
    assert len(runtime.started) == 1


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
    current = iter((True, False))
    stale.wait = lambda timeout=None: (_ for _ in ()).throw(TimeoutError())  # type: ignore[method-assign]
    with pytest.raises(AgentProtocolError) as caught:
        subject.review(URL, request, is_current=lambda: next(current))
    assert caught.value.canceled and stale.cancellations == ["stale-authority"] and stale.closed == 1

    failed = Operation("review:failed", outcome=TurnOutcome.FAILED)
    subject, _ = runner(result, failed)
    with pytest.raises(AgentProtocolError, match="completed result"):
        subject.review(URL, request)
    assert failed.closed == 1

    unverified = Operation("review:unclean", clean=False)
    subject, _ = runner(result, unverified)
    with pytest.raises(AgentProtocolError, match="cleanup is unverified"):
        subject.review(URL, request)


def test_timeout_cancels_before_verified_close() -> None:
    operation = Operation("review:timeout")
    operation.wait = lambda timeout=None: (_ for _ in ()).throw(TimeoutError())  # type: ignore[method-assign]
    runtime = Runtime(operation)
    clock = iter((0.0, 2.0))
    subject = PiNativeRunner(runtime, timeout=1, clock=lambda: next(clock))  # type: ignore[arg-type]
    subject.route_operation(operation.operation_id)

    with pytest.raises(AgentProtocolError) as caught:
        subject.review(URL, review_request())

    assert caught.value.timed_out
    assert operation.cancellations == ["host-timeout"]
    assert operation.closed == 1


def test_coding_archive_policy_passes_unchanged_and_rejects_changed_or_missing_archive() -> None:
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
    assert subject.code(URL, request).status == "unchanged"
    assert runtime.loaded_archives == ["code:archive"]

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
    with pytest.raises(AgentProtocolError, match="cannot be safely applied") as caught:
        subject.code(URL, request)
    assert caught.value.canceled
    assert runtime.loaded_archives == ["code:changed"]

    subject, runtime = runner(dict(base, status="unchanged"), Operation("code:missing"))
    runtime.archive = b""
    with pytest.raises(AgentProtocolError, match="archive is unavailable") as caught:
        subject.code(URL, request)
    assert caught.value.canceled

    subject, runtime = runner(dict(base, status="unchanged"), Operation("code:invalid-archive"))
    runtime.load_workspace_archive = lambda operation_id: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeProtocolError("workspace-archive-corrupt")
    )
    with pytest.raises(AgentProtocolError, match="archive is unavailable") as caught:
        subject.code(URL, request)
    assert caught.value.canceled
