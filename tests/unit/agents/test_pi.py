from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from petrus.agenticus.runtime.operation import (
    RuntimeCleanupDisposition,
    RuntimeOperationCleanup,
)
from petrus.agenticus.runtime.pi import PiRuntimeInvocation
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


def invocation(operation: str, prompt: str) -> PiRuntimeInvocation:
    value = object.__new__(PiRuntimeInvocation)
    object.__setattr__(value, "operation_id", operation)
    object.__setattr__(value, "episode_id", EpisodeId(f"episode:{operation}"))
    object.__setattr__(value, "turn_id", TurnId(f"turn:{operation}"))
    object.__setattr__(value, "prompt", prompt)
    return value


class Operation:
    def __init__(self, operation: str, *, outcome: TurnOutcome = TurnOutcome.COMPLETED, clean: bool = True):
        self.operation_id = operation
        self.outcome, self.clean = outcome, clean
        self.waits = 0
        self.cancellations: list[str] = []
        self.closed = 0

    def wait(self, timeout=None):
        self.waits += 1
        return RuntimeTurnSettlement(
            EpisodeId(f"episode:{self.operation_id}"),
            TurnId(f"turn:{self.operation_id}"),
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
    def __init__(self, operation: Operation):
        self.operation = operation
        self.started: list[PiRuntimeInvocation] = []

    def start(self, value):
        self.started.append(value)
        return self.operation


def runner(result: dict[str, object], operation: Operation | None = None) -> tuple[PiNativeRunner, Runtime]:
    selected = operation or Operation("review:one")
    runtime = Runtime(selected)
    value = PiNativeRunner(runtime, invocation, lambda reference: json.dumps(result))
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
    malformed = PiNativeRunner(runtime, invocation, lambda reference: "not-json")
    malformed.route_operation(malformed_operation.operation_id)
    with pytest.raises(AgentProtocolError, match="malformed JSON"):
        malformed.review(URL, request)
    assert malformed_operation.closed == 1

    mismatched_operation = Operation("review:other")
    runtime = Runtime(mismatched_operation)
    mismatched = PiNativeRunner(runtime, invocation, lambda reference: "{}")
    mismatched.route_operation("review:expected")
    with pytest.raises(AgentProtocolError, match="identity mismatched"):
        mismatched.review(URL, request)
    assert mismatched_operation.cancellations == ["operation-mismatch"]
    assert mismatched_operation.closed == 1


def test_runtime_never_starts_without_a_claimed_route() -> None:
    runtime = Runtime(Operation("review:unclaimed"))
    subject = PiNativeRunner(runtime, invocation, lambda reference: "{}")

    with pytest.raises(AgentProtocolError, match="route was not selected"):
        subject.review(URL, review_request())

    assert runtime.started == []


def test_invocation_mismatch_and_failed_preflight_cannot_start_or_reuse_route() -> None:
    runtime = Runtime(Operation("review:expected"))
    mismatched = PiNativeRunner(runtime, lambda operation, prompt: invocation("review:other", prompt), lambda ref: "{}")
    mismatched.route_operation("review:expected")
    with pytest.raises(AgentProtocolError, match="invocation correlation"):
        mismatched.review(URL, review_request())
    assert runtime.started == []

    subject = PiNativeRunner(runtime, invocation, lambda ref: "{}")
    subject.route_operation("review:preflight")
    with pytest.raises(AgentProtocolError, match="repository URL"):
        subject.review("https://user@example.invalid/repo", review_request())
    with pytest.raises(AgentProtocolError, match="route was not selected"):
        subject.review(URL, review_request())
    assert runtime.started == []


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
    subject = PiNativeRunner(
        runtime,
        invocation,
        lambda reference: "{}",
        timeout=1,
        clock=lambda: next(clock),
    )
    subject.route_operation(operation.operation_id)

    with pytest.raises(AgentProtocolError) as caught:
        subject.review(URL, review_request())

    assert caught.value.timed_out
    assert operation.cancellations == ["host-timeout"]
    assert operation.closed == 1
