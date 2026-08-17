"""Hamsterdan protocol adapter over an injected Pi native A2 runtime lifecycle."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict
from hashlib import sha256
from math import isfinite
from typing import Protocol, cast
from urllib.parse import urlsplit, urlunsplit

from petrus.agenticus.runtime.operation import RuntimeOperation, RuntimeProtocolError
from petrus.agenticus.runtime.pi_a2_host import PiA2RuntimeHost, PiA2RuntimePolicy, PiA2RuntimeStart
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import TurnOutcome

from .protocol import (
    _CODING_RESULT_FIELDS,
    _CODING_STATUSES,
    _CONVERSATION_RESULT_FIELDS,
    _FINDING_FIELDS,
    _FINDING_ID_PATTERN,
    _FINDING_SEVERITIES,
    _INTENT_FIELDS,
    _LINEAGE_FIELDS,
    _LINEAGE_STATES,
    _RELATED_LOCATION_FIELDS,
    _REPRODUCTION_STATUSES,
    _REVIEW_RESULT_FIELDS,
    _REVIEW_STATUSES,
    CURRENT,
    AgentCleanupCategory,
    AgentProtocolError,
    AgentRequest,
    AgentResult,
    AgentResultCategory,
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


class PiWorkspaceError(RuntimeError):
    """A secret-safe deterministic failure at the receiving-host workspace boundary."""


class PiWorkspaceCleanupError(PiWorkspaceError):
    """Workspace cleanup uncertainty kept separate from result admission."""

    def __init__(self, *, preparation_failed: bool = False) -> None:
        self.preparation_failed = preparation_failed
        super().__init__("Pi workspace cleanup is unverified")


class PreparedPiWorkspace(Protocol):
    archive: bytes
    digest: str
    correlation: str
    policy: PiA2RuntimePolicy

    def reconcile(self, archive: bytes) -> tuple[str, list[str]]: ...


class PiWorkspaceProvider(Protocol):
    def open(
        self,
        kind: str,
        repository_url: str,
        request: AgentRequest,
        operation_id: str,
    ) -> AbstractContextManager[PreparedPiWorkspace]: ...


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
_PROMPT_FIELDS = frozenset({"instructions", "kind", "prompt_version", "repository_url", "request", "response_contract"})


def _contract_fields(names: frozenset[str] | tuple[str, ...], descriptions: dict[str, str]) -> JSONDict:
    if set(names) != set(descriptions):
        raise RuntimeError("Pi response contract differs from the result validator")
    return {name: descriptions[name] for name in sorted(names)}


def _response_contract(kind: str) -> JSONDict:
    exact = {
        "repository": "string; copy request.repository exactly",
        "pull_request": "integer; copy request.pull_request exactly",
        "epoch": "integer; copy request.epoch exactly",
        "head": "string; copy request.head exactly",
        "base": "string; copy request.base exactly",
    }
    nested: JSONDict = {}
    invariants: list[str]
    if kind == "review":
        exact.update(
            {
                "status": f"one of {sorted(_REVIEW_STATUSES)}",
                "findings": "array of finding objects; use [] when none",
                "lineage": "array of lineage objects; use [] when none",
            }
        )
        nested = {
            "finding_exact_fields": _contract_fields(
                _FINDING_FIELDS,
                {
                    "id": (
                        f"unique 1-48 ASCII-character identifier matching {_FINDING_ID_PATTERN}; "
                        "colon and whitespace are forbidden"
                    ),
                    "path": "repository-relative path",
                    "line": "positive integer line number",
                    "related_locations": "array of related-location objects; primary location must not repeat",
                    "title": "non-empty string",
                    "body": "non-empty actionable explanation",
                    "severity": f"one of {sorted(_FINDING_SEVERITIES)}",
                    "confidence": "number from 0 through 1",
                    "evidence": "non-empty evidenced observation",
                    "blocking": "boolean",
                    "suggestion": "string; empty when absent; no Markdown code fence",
                },
            ),
            "related_location_exact_fields": _contract_fields(
                _RELATED_LOCATION_FIELDS,
                {"path": "repository-relative path", "line": "positive integer line number"},
            ),
            "lineage_exact_fields": _contract_fields(
                _LINEAGE_FIELDS,
                {
                    "finding_id": (
                        "unique within lineage; for new and still_open copy an exact "
                        f"returned finding.id matching {_FINDING_ID_PATTERN}"
                    ),
                    "state": f"one of {sorted(_LINEAGE_STATES)}",
                    "supersedes": "prior finding identifier or null",
                },
            ),
        }
        invariants = [
            "status clear has no blocking finding; status blocking has at least one blocking finding",
            "new and still_open lineage references a returned finding",
            "new lineage has null supersedes; superseded lineage has a non-null predecessor",
        ]
        result_fields = _REVIEW_RESULT_FIELDS
    elif kind == "conversation":
        exact["intents"] = "array containing exactly one intent object"
        nested = {
            "intent_exact_fields": _contract_fields(
                _INTENT_FIELDS,
                {
                    "type": "copy one type declared in request.allowed_intents",
                    "arguments": "object with exactly the argument keys declared for that type",
                    "mutation": "boolean equal to that declaration's mutation value",
                    "explicit": "boolean; true for mutations and declarations requiring explicit intent",
                    "confidence": "number from 0 through 1",
                },
            )
        }
        invariants = [
            "return exactly one declared intent and never invent an intent or argument key",
            "mutation intents require concrete non-empty arguments",
        ]
        result_fields = _CONVERSATION_RESULT_FIELDS
    else:
        exact.update(
            {
                "kind": "string; copy request.kind exactly",
                "ref": "string; copy request.ref exactly",
                "status": f"one of {sorted(_CODING_STATUSES)}",
                "reproduction_status": f"one of {sorted(_REPRODUCTION_STATUSES)}",
                "diff": "string; empty unless status is changed",
                "changed_files": "sorted unique array of repository-relative paths changed in the workspace",
                "validation_evidence": "array of non-empty bounded JSON objects; non-empty when status is changed",
                "proposed_commit_message": "string; non-empty when changed, with a first line of at most 72 characters",
            }
        )
        invariants = [
            "status changed only when the workspace changed; otherwise use unchanged or unable",
            "a changed repair requires reproduction_status confirmed",
            "report only validation actually performed",
        ]
        result_fields = _CODING_RESULT_FIELDS
    return {
        "return_format": "Return exactly one JSON object and nothing else; no Markdown or prose.",
        "exact_fields": _contract_fields(result_fields, exact),
        "nested": nested,
        "invariants": invariants,
        "forbidden_envelope_fields": sorted(_PROMPT_FIELDS - result_fields),
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
        "prompt_version": 3 if kind == "review" else 2,
        "repository_url": urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")),
        "request": asdict(request),
        "response_contract": _response_contract(kind),
    }
    prompt = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(prompt.encode()) > 64 * 1024:
        _fail("Pi prompt exceeded limit")
    return prompt


class PiNativeRunner:
    """Translate unchanged Hamsterdan contracts through public Pi operation lifecycle."""

    def __init__(
        self,
        runtime: PiA2RuntimeHost,
        workspaces: PiWorkspaceProvider,
        *,
        timeout: float | None = None,
        poll_interval: float = 0.1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            isinstance(poll_interval, bool)
            or not isinstance(poll_interval, int | float)
            or not isfinite(poll_interval)
            or poll_interval <= 0
            or timeout is not None
            and (
                isinstance(timeout, bool)
                or not isinstance(timeout, int | float)
                or not isfinite(timeout)
                or timeout <= 0
                or poll_interval > timeout
            )
        ):
            raise ValueError("Pi runner timeout and poll interval must be positive and ordered")
        self._runtime, self._workspaces = runtime, workspaces
        self._timeout, self._poll_interval, self._clock = timeout, poll_interval, clock

    def review(
        self,
        repository_url: str,
        request: ReviewRequest,
        *,
        operation: str,
        attempt: int,
        is_current: CURRENT | None = None,
    ) -> ReviewResult:
        return cast(ReviewResult, self._run("review", repository_url, request, operation, attempt, is_current))

    def converse(
        self,
        repository_url: str,
        request: ConversationRequest,
        *,
        operation: str,
        attempt: int,
        is_current: CURRENT | None = None,
    ) -> ConversationResult:
        return cast(
            ConversationResult, self._run("conversation", repository_url, request, operation, attempt, is_current)
        )

    def code(
        self,
        repository_url: str,
        request: CodingRequest,
        *,
        operation: str,
        attempt: int,
        is_current: CURRENT | None = None,
    ) -> CodingResult:
        return cast(CodingResult, self._run("coding", repository_url, request, operation, attempt, is_current))

    def _run(
        self,
        kind: str,
        repository_url: str,
        request: AgentRequest,
        operation: str,
        attempt: int,
        is_current: CURRENT | None,
    ) -> AgentResult:
        logical_operation = _text(operation, "operation", limit=1024)
        if type(attempt) is not int or attempt < 1:
            raise AgentProtocolError("invalid agent attempt", result_category=AgentResultCategory.CORRELATION)
        operation_id = f"pi:{sha256(f'{logical_operation}\0{attempt}'.encode()).hexdigest()}"
        try:
            prompt = encode_prompt(kind, repository_url, request)
        except AgentProtocolError as error:
            raise error.retain_result_category(AgentResultCategory.CORRELATION)
        if is_current is not None and not is_current():
            raise AgentProtocolError("agent attempt superseded", canceled=True)
        result: AgentResult | None = None
        failure: AgentProtocolError | None = None
        try:
            with self._workspaces.open(kind, repository_url, request, operation_id) as workspace:
                try:
                    if is_current is not None and not is_current():
                        raise AgentProtocolError("agent attempt superseded", canceled=True)
                    result = self._run_workspace(kind, prompt, request, operation_id, is_current, workspace)
                except AgentProtocolError as error:
                    failure = error
        except PiWorkspaceCleanupError as error:
            if failure is None:
                failure = AgentProtocolError(
                    "Pi workspace cleanup is unverified",
                    result_category=(
                        AgentResultCategory.WORKSPACE_RECONCILIATION if error.preparation_failed else None
                    ),
                    cleanup_category=AgentCleanupCategory.UNVERIFIED,
                )
            else:
                failure.retain_cleanup_category(AgentCleanupCategory.UNVERIFIED)
        except PiWorkspaceError:
            if failure is None:
                failure = AgentProtocolError(
                    "Pi workspace proof failed",
                    result_category=AgentResultCategory.WORKSPACE_RECONCILIATION,
                )
        if failure is not None:
            raise failure
        if result is None:
            raise AgentProtocolError(
                "Pi operation result is unavailable", result_category=AgentResultCategory.RUNTIME_LIFECYCLE
            )
        return result

    def _run_workspace(
        self,
        kind: str,
        prompt: str,
        request: AgentRequest,
        operation_id: str,
        is_current: CURRENT | None,
        workspace: PreparedPiWorkspace,
    ) -> AgentResult:
        try:
            identity = sha256(operation_id.encode()).hexdigest()
            start = PiA2RuntimeStart(
                operation_id,
                EpisodeId(f"episode-{identity}"),
                TurnId(f"turn-{identity}"),
                prompt,
                workspace.archive,
                workspace.digest,
                workspace.correlation,
                workspace.policy,
            )
            operation = self._runtime.start(start)
        except AgentProtocolError:
            raise
        except Exception:  # noqa: BLE001 - sanitize injected lifecycle/factory failures at the protocol boundary
            raise AgentProtocolError(
                "Pi operation could not start", result_category=AgentResultCategory.RUNTIME_LIFECYCLE
            ) from None
        started_operation_id: str | None = None
        result: AgentResult | None = None
        failure: AgentProtocolError | None = None
        try:
            started_operation_id = operation.operation_id
            if started_operation_id != operation_id:
                self._cancel(operation, "operation-mismatch")
                raise AgentProtocolError(
                    "Pi operation identity mismatched its route",
                    result_category=AgentResultCategory.CORRELATION,
                )
            settlement = self._wait(operation, is_current)
            if settlement.episode_id != start.episode_id or settlement.turn_id != start.turn_id:
                raise AgentProtocolError(
                    "Pi settlement identity mismatched its route",
                    result_category=AgentResultCategory.CORRELATION,
                )
            if (
                settlement.outcome is not TurnOutcome.COMPLETED
                or settlement.accepted_appends != 1
                or settlement.output_reference is None
            ):
                if settlement.outcome is TurnOutcome.CANCELLED:
                    raise AgentProtocolError(
                        "agent attempt canceled",
                        canceled=True,
                        result_category=AgentResultCategory.RUNTIME_LIFECYCLE,
                    )
                raise AgentProtocolError(
                    "Pi operation did not produce a completed result",
                    result_category=AgentResultCategory.RUNTIME_LIFECYCLE,
                )
            raw = self._runtime.load_output(settlement.output_reference)
            try:
                data = _parse_result(raw)
            except AgentProtocolError as error:
                raise error.retain_result_category(AgentResultCategory.OUTPUT_SCHEMA)
            changed: list[str] | None = None
            if kind == "coding":
                try:
                    archive = self._runtime.load_workspace_archive(operation_id)
                except RuntimeProtocolError:
                    raise AgentProtocolError(
                        "Pi coding workspace archive is unavailable",
                        result_category=AgentResultCategory.WORKSPACE_RECONCILIATION,
                    ) from None
                if not archive:
                    raise AgentProtocolError(
                        "Pi coding workspace archive is unavailable",
                        result_category=AgentResultCategory.WORKSPACE_RECONCILIATION,
                    )
                try:
                    diff, changed = workspace.reconcile(archive)
                except PiWorkspaceError:
                    raise AgentProtocolError(
                        "Pi workspace proof failed",
                        result_category=AgentResultCategory.WORKSPACE_RECONCILIATION,
                    ) from None
                data = dict(data)
                data["diff"], data["changed_files"] = diff, changed
            try:
                result = _validate_result(
                    kind,
                    data,
                    request,
                    changed,
                )
            except AgentProtocolError as error:
                raise error.retain_result_category(AgentResultCategory.OUTPUT_SCHEMA)
        except AgentProtocolError as error:
            failure = error
        except PiWorkspaceError:
            failure = AgentProtocolError(
                "Pi workspace proof failed",
                result_category=AgentResultCategory.WORKSPACE_RECONCILIATION,
            )
        except RuntimeProtocolError:
            failure = AgentProtocolError(
                "Pi operation lifecycle failed", result_category=AgentResultCategory.RUNTIME_LIFECYCLE
            )
        except Exception:  # noqa: BLE001 - sanitize output collaborator failures at the protocol boundary
            failure = AgentProtocolError(
                "Pi operation result is unavailable", result_category=AgentResultCategory.RUNTIME_LIFECYCLE
            )
        try:
            cleanup = operation.close()
            cleanup_verified = (
                started_operation_id is not None and cleanup.verified and cleanup.operation_id == started_operation_id
            )
        except Exception:  # noqa: BLE001 - cleanup uncertainty must fail closed without leaking internals
            cleanup_verified = False
        if not cleanup_verified:
            if failure is None:
                failure = AgentProtocolError(
                    "Pi operation cleanup is unverified",
                    cleanup_category=AgentCleanupCategory.UNVERIFIED,
                )
            else:
                failure.retain_cleanup_category(AgentCleanupCategory.UNVERIFIED)
        if failure is not None:
            raise failure
        if result is None:
            raise AgentProtocolError(
                "Pi operation result is unavailable", result_category=AgentResultCategory.RUNTIME_LIFECYCLE
            )
        return result

    def _wait(self, operation: RuntimeOperation, is_current: CURRENT | None):
        deadline = None if self._timeout is None else self._clock() + self._timeout
        while True:
            if is_current is not None and not is_current():
                self._cancel(operation, "stale-authority")
                raise AgentProtocolError("agent attempt superseded", canceled=True)
            wait_timeout = self._poll_interval
            if deadline is not None:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    self._cancel(operation, "host-timeout")
                    raise AgentProtocolError(
                        "agent execution timed out",
                        timed_out=True,
                        result_category=AgentResultCategory.RUNTIME_LIFECYCLE,
                    )
                wait_timeout = min(wait_timeout, remaining)
            try:
                settlement = operation.wait(wait_timeout)
            except TimeoutError:
                continue
            if is_current is not None and not is_current():
                self._cancel(operation, "stale-authority")
                raise AgentProtocolError("agent attempt superseded", canceled=True)
            return settlement

    @staticmethod
    def _cancel(operation: RuntimeOperation, reason: str) -> None:
        try:
            operation.cancel(reason)
        except Exception:  # noqa: BLE001 - close remains the authoritative cleanup proof
            return


class UnavailablePiRunner:
    """Fail closed when the exact Pi installation or collaborators are unavailable."""

    def review(
        self,
        repository_url: str,
        request: ReviewRequest,
        *,
        operation: str,
        attempt: int,
        is_current: CURRENT | None = None,
    ) -> ReviewResult:
        raise AgentProtocolError("Pi native A2 runtime is not ready")

    def converse(
        self,
        repository_url: str,
        request: ConversationRequest,
        *,
        operation: str,
        attempt: int,
        is_current: CURRENT | None = None,
    ) -> ConversationResult:
        raise AgentProtocolError("Pi native A2 runtime is not ready")

    def code(
        self,
        repository_url: str,
        request: CodingRequest,
        *,
        operation: str,
        attempt: int,
        is_current: CURRENT | None = None,
    ) -> CodingResult:
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
