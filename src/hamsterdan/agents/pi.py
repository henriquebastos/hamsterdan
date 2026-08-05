"""Hamsterdan protocol adapter over an injected Pi native A2 runtime lifecycle."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import asdict
from typing import Protocol, cast, runtime_checkable
from urllib.parse import urlsplit, urlunsplit

from petrus.agenticus.runtime.operation import RuntimeOperation, RuntimeProtocolError
from petrus.agenticus.runtime.pi import PiRuntimeInvocation
from petrus.agenticus.thread.lifecycle import TurnOutcome

from .protocol import (
    CURRENT,
    AgentProtocolError,
    AgentRequest,
    AgentResult,
    CodingRequest,
    CodingResult,
    ConversationRequest,
    ConversationResult,
    JSONDict,
    ReviewRequest,
    ReviewResult,
    _fail,
    _text,
    _validate_request,
    _validate_result,
)

MAX_RESULT_BYTES = 1_000_000
InvocationFactory = Callable[[str, str], PiRuntimeInvocation]
OutputLoader = Callable[[str], str]


class PiRuntimeLifecycle(Protocol):
    def start(self, invocation: PiRuntimeInvocation) -> RuntimeOperation: ...


@runtime_checkable
class OperationRoutedRunner(Protocol):
    def route_operation(self, operation: str) -> None: ...


_OPERATION: ContextVar[str | None] = ContextVar("hamsterdan_pi_operation", default=None)
_SEMANTICS = {
    "review": (
        "Review the exact supplied PR generation using the supplied policy, evidence, prior findings, and lenses. "
        "Return only evidenced actionable findings with consistent lineage."
    ),
    "conversation": (
        "Interpret the supplied comment against the current dashboard, gates, findings, and allowed intents. "
        "Select exactly one declared intent and never invent workflow state or authorization."
    ),
    "coding": (
        "Propose the smallest conservative change for the supplied work and report bounded validation evidence. "
        "Never claim a changed repair without confirmed reproduction."
    ),
}


def encode_prompt(kind: str, repository_url: str, request: AgentRequest) -> str:
    """Encode one canonical bounded Pi prompt without execution authority."""

    _validate_request(request)
    if kind not in _SEMANTICS:
        raise ValueError("Pi prompt kind is unsupported")
    parsed = urlsplit(_text(repository_url, "repository URL", limit=4096))
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        _fail("repository URL contains credentials or noncanonical data")
    payload = {
        "instructions": _SEMANTICS[kind],
        "kind": kind,
        "repository_url": urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")),
        "request": asdict(request),
        "response": "one JSON object matching the unchanged Hamsterdan result schema; no Markdown or prose",
        "schema_version": 1,
    }
    prompt = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(prompt.encode()) > 64 * 1024:
        _fail("Pi prompt exceeded limit")
    return prompt


class PiNativeRunner:
    """Translate unchanged Hamsterdan contracts through public Pi operation lifecycle."""

    def __init__(
        self,
        runtime: PiRuntimeLifecycle,
        invocation_factory: InvocationFactory,
        output_loader: OutputLoader,
        *,
        timeout: float = 300,
        poll_interval: float = 0.1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout <= 0 or poll_interval <= 0 or poll_interval > timeout:
            raise ValueError("Pi runner timeout and poll interval must be positive and ordered")
        self._runtime, self._invocation_factory, self._output_loader = runtime, invocation_factory, output_loader
        self._timeout, self._poll_interval, self._clock = timeout, poll_interval, clock

    def route_operation(self, operation: str) -> None:
        _OPERATION.set(_text(operation, "operation", limit=256))

    def review(self, repository_url: str, request: ReviewRequest, *, is_current: CURRENT | None = None) -> ReviewResult:
        return cast(ReviewResult, self._run("review", repository_url, request, is_current))

    def converse(
        self, repository_url: str, request: ConversationRequest, *, is_current: CURRENT | None = None
    ) -> ConversationResult:
        return cast(ConversationResult, self._run("conversation", repository_url, request, is_current))

    def code(self, repository_url: str, request: CodingRequest, *, is_current: CURRENT | None = None) -> CodingResult:
        return cast(CodingResult, self._run("coding", repository_url, request, is_current))

    def _run(
        self,
        kind: str,
        repository_url: str,
        request: AgentRequest,
        is_current: CURRENT | None,
    ) -> AgentResult:
        operation_id = _OPERATION.get()
        _OPERATION.set(None)
        if operation_id is None:
            raise AgentProtocolError("Pi operation route was not selected")
        prompt = encode_prompt(kind, repository_url, request)
        if is_current is not None and not is_current():
            raise AgentProtocolError("agent attempt superseded", canceled=True)
        try:
            invocation = self._invocation_factory(operation_id, prompt)
            if invocation.operation_id != operation_id or invocation.prompt != prompt:
                raise AgentProtocolError("Pi invocation correlation mismatched its route")
            operation = self._runtime.start(invocation)
        except AgentProtocolError:
            raise
        except Exception:  # noqa: BLE001 - sanitize injected lifecycle/factory failures at the protocol boundary
            raise AgentProtocolError("Pi operation could not start") from None
        started_operation_id = operation.operation_id
        try:
            if started_operation_id != operation_id:
                operation.cancel("operation-mismatch")
                raise AgentProtocolError("Pi operation identity mismatched its route")
            settlement = self._wait(operation, is_current)
            if (
                settlement.episode_id != invocation.episode_id
                or settlement.turn_id != invocation.turn_id
                or settlement.outcome is not TurnOutcome.COMPLETED
                or settlement.accepted_appends != 1
                or settlement.output_reference is None
            ):
                if settlement.outcome is TurnOutcome.CANCELLED:
                    raise AgentProtocolError("agent attempt canceled", canceled=True)
                raise AgentProtocolError("Pi operation did not produce a completed result")
            raw = self._output_loader(settlement.output_reference)
            data = _parse_result(raw)
            changed = data.get("changed_files") if kind == "coding" else None
            return _validate_result(
                kind,
                data,
                request,
                cast(list[str], changed) if isinstance(changed, list) else None,
            )
        except AgentProtocolError:
            raise
        except RuntimeProtocolError:
            raise AgentProtocolError("Pi operation lifecycle failed") from None
        except Exception:  # noqa: BLE001 - sanitize output collaborator failures at the protocol boundary
            raise AgentProtocolError("Pi operation result is unavailable") from None
        finally:
            try:
                cleanup = operation.close()
            except Exception:  # noqa: BLE001 - cleanup uncertainty must fail closed without leaking internals
                raise AgentProtocolError("Pi operation cleanup is unverified") from None
            if not cleanup.verified or cleanup.operation_id != started_operation_id:
                raise AgentProtocolError("Pi operation cleanup is unverified")

    def _wait(self, operation: RuntimeOperation, is_current: CURRENT | None):
        deadline = self._clock() + self._timeout
        while True:
            if is_current is not None and not is_current():
                operation.cancel("stale-authority")
                raise AgentProtocolError("agent attempt superseded", canceled=True)
            remaining = deadline - self._clock()
            if remaining <= 0:
                operation.cancel("host-timeout")
                raise AgentProtocolError("agent execution timed out", timed_out=True)
            try:
                return operation.wait(min(self._poll_interval, remaining))
            except TimeoutError:
                continue


class UnavailablePiRunner:
    """Fail closed when the exact Pi installation or collaborators are unavailable."""

    def route_operation(self, operation: str) -> None:
        _text(operation, "operation", limit=256)

    def review(self, repository_url: str, request: ReviewRequest, *, is_current: CURRENT | None = None) -> ReviewResult:
        raise AgentProtocolError("Pi native A2 runtime is not ready")

    def converse(
        self, repository_url: str, request: ConversationRequest, *, is_current: CURRENT | None = None
    ) -> ConversationResult:
        raise AgentProtocolError("Pi native A2 runtime is not ready")

    def code(self, repository_url: str, request: CodingRequest, *, is_current: CURRENT | None = None) -> CodingResult:
        raise AgentProtocolError("Pi native A2 runtime is not ready")


def _parse_result(raw: str) -> JSONDict:
    if not isinstance(raw, str) or len(raw.encode()) > MAX_RESULT_BYTES:
        _fail("Pi result exceeded limit")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise AgentProtocolError("result is malformed JSON") from None
    if not isinstance(value, dict):
        _fail("result must be a JSON object")
    return value
