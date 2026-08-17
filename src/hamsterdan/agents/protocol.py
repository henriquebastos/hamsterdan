"""Frozen agent contracts and strict credential-free protocol validation."""

# Keeping request-kind validation in separate branches mirrors the canonical protocol.
# ruff: noqa: SIM102

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Never, Protocol, cast

JSONDict = dict[str, object]
CURRENT = Callable[[], bool]
_SHA = re.compile(r"[0-9a-f]{40,64}")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,254}")
_FINDING_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,47}"
_FINDING_ID = re.compile(_FINDING_ID_PATTERN)
_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_MAX_ITEMS, _MAX_TEXT, _MAX_PATH, _MAX_FILE = 100, 20_000, 1024, 2_000_000
_SECRET_WORDS = ("TOKEN", "PASSWORD", "PASSWD", "SECRET", "CREDENTIAL", "PRIVATE_KEY", "API_KEY")
_COMMON_RESULT_FIELDS = ("repository", "pull_request", "epoch", "head", "base")
_REVIEW_RESULT_FIELDS = frozenset((*_COMMON_RESULT_FIELDS, "status", "findings", "lineage"))
_CONVERSATION_RESULT_FIELDS = frozenset((*_COMMON_RESULT_FIELDS, "intents"))
_CODING_RESULT_FIELDS = frozenset(
    (
        *_COMMON_RESULT_FIELDS,
        "kind",
        "ref",
        "status",
        "reproduction_status",
        "diff",
        "changed_files",
        "validation_evidence",
        "proposed_commit_message",
    )
)
_FINDING_FIELDS = frozenset(
    {
        "id",
        "path",
        "line",
        "related_locations",
        "title",
        "body",
        "severity",
        "confidence",
        "evidence",
        "blocking",
        "suggestion",
    }
)
_RELATED_LOCATION_FIELDS = frozenset({"path", "line"})
_LINEAGE_FIELDS = frozenset({"finding_id", "state", "supersedes"})
_INTENT_FIELDS = frozenset({"type", "arguments", "mutation", "explicit", "confidence"})
_REVIEW_STATUSES = frozenset({"clear", "blocking", "unable"})
_FINDING_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
_LINEAGE_STATES = frozenset({"new", "still_open", "resolved", "superseded", "withdrawn"})
_CODING_STATUSES = frozenset({"changed", "unchanged", "unable"})
_REPRODUCTION_STATUSES = frozenset({"unknown", "confirmed", "not_reproduced", "not_attempted"})


class AgentResultCategory(StrEnum):
    """Closed, provider-neutral coding-result admission outcomes."""

    RUNTIME_LIFECYCLE = "runtime_lifecycle"
    OUTPUT_SCHEMA = "output_schema"
    CORRELATION = "correlation"
    UNCHANGED = "unchanged"
    UNABLE = "unable"
    WORKSPACE_RECONCILIATION = "workspace_reconciliation"


class AgentCleanupCategory(StrEnum):
    """Closed cleanup uncertainty retained separately from result admission."""

    UNVERIFIED = "cleanup_unverified"


class AgentProtocolError(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        canceled: bool = False,
        timed_out: bool = False,
        result_category: AgentResultCategory | None = None,
        cleanup_category: AgentCleanupCategory | None = None,
    ):
        if result_category is not None and not isinstance(result_category, AgentResultCategory):
            raise TypeError("agent result category must use the closed vocabulary")
        if cleanup_category is not None and not isinstance(cleanup_category, AgentCleanupCategory):
            raise TypeError("agent cleanup category must use the closed vocabulary")
        super().__init__(reason)
        self.canceled, self.timed_out = canceled, timed_out
        self.result_category, self.cleanup_category = result_category, cleanup_category

    def retain_result_category(self, category: AgentResultCategory) -> AgentProtocolError:
        if not isinstance(category, AgentResultCategory):
            raise TypeError("agent result category must use the closed vocabulary")
        if self.result_category is None:
            self.result_category = category
        return self

    def retain_cleanup_category(self, category: AgentCleanupCategory) -> AgentProtocolError:
        if not isinstance(category, AgentCleanupCategory):
            raise TypeError("agent cleanup category must use the closed vocabulary")
        if self.cleanup_category is None:
            self.cleanup_category = category
        return self


@dataclass(frozen=True)
class ReviewRequest:
    repository: str
    pull_request: int
    epoch: int
    head: str
    base: str
    diff_path: str
    policy: JSONDict = field(default_factory=dict)
    review_lenses: list[str] = field(default_factory=list)
    context_paths: list[str] = field(default_factory=list)
    actions_evidence: list[JSONDict] = field(default_factory=list)
    prior_findings: list[JSONDict] = field(default_factory=list)
    prior_comments: list[JSONDict] = field(default_factory=list)
    prior_replies: list[JSONDict] = field(default_factory=list)
    applied_changes: list[JSONDict] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewResult:
    repository: str
    pull_request: int
    epoch: int
    head: str
    base: str
    status: str
    findings: list[JSONDict]
    lineage: list[JSONDict]


@dataclass(frozen=True)
class ConversationRequest:
    repository: str
    pull_request: int
    epoch: int
    head: str
    base: str
    comment_context: JSONDict
    actor: JSONDict
    dashboard: JSONDict
    gates: list[JSONDict]
    findings: list[JSONDict]
    allowed_intents: list[JSONDict]


@dataclass(frozen=True)
class ConversationResult:
    repository: str
    pull_request: int
    epoch: int
    head: str
    base: str
    intents: list[JSONDict]


@dataclass(frozen=True)
class CodingRequest:
    kind: str
    repository: str
    pull_request: int
    epoch: int
    head: str
    base: str
    ref: str
    selected_work: list[JSONDict] = field(default_factory=list)
    failure_evidence: list[JSONDict] = field(default_factory=list)
    fingerprint: str = ""
    lineage: list[JSONDict] = field(default_factory=list)
    reproduction_status: str = "unknown"
    merge_base: bool = False


ChangeRequest = RepairRequest = CodingRequest


@dataclass(frozen=True)
class CodingResult:
    kind: str
    repository: str
    pull_request: int
    epoch: int
    head: str
    base: str
    ref: str
    status: str
    reproduction_status: str
    diff: str
    changed_files: list[str]
    validation_evidence: list[JSONDict]
    proposed_commit_message: str


ChangeResult = RepairResult = CodingResult


class AgentRunner(Protocol):
    def review(
        self,
        repository_url: str,
        request: ReviewRequest,
        *,
        operation: str,
        attempt: int,
        is_current: CURRENT | None = None,
    ) -> ReviewResult: ...
    def converse(
        self,
        repository_url: str,
        request: ConversationRequest,
        *,
        operation: str,
        attempt: int,
        is_current: CURRENT | None = None,
    ) -> ConversationResult: ...
    def code(
        self,
        repository_url: str,
        request: CodingRequest,
        *,
        operation: str,
        attempt: int,
        is_current: CURRENT | None = None,
    ) -> CodingResult: ...


def _fail(message: str) -> Never:
    raise AgentProtocolError(message)


def _text(value: object, name: str, *, empty: bool = False, limit: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or (not empty and not value) or len(value.encode()) > limit or "\x00" in value:
        _fail(f"invalid {name}")
    return value


def _safe_path(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value.encode()) > _MAX_PATH or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.parts[0] not in {".git", ".impetus"}


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list) or len(value) > _MAX_ITEMS:
        _fail(f"invalid {name}")
    return cast(list[object], value)


def _exact(data: JSONDict, names: set[str] | frozenset[str]) -> None:
    if set(data) != names:
        _fail(f"result fields differ: expected {sorted(names)}, got {sorted(data)}")


def _correlate(data: JSONDict, request: object, fields: tuple[str, ...]) -> None:
    for name in fields:
        expected = getattr(request, name)
        if name not in data or type(data[name]) is not type(expected):
            _fail(f"result correlation mismatch: {name}")
        if data[name] != expected:
            raise AgentProtocolError(
                f"result correlation mismatch: {name}", result_category=AgentResultCategory.CORRELATION
            )


def _confidence(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= 1


AgentRequest = ReviewRequest | ConversationRequest | CodingRequest
AgentResult = ReviewResult | ConversationResult | CodingResult


def _validate_request(request: AgentRequest) -> None:
    if not _REPOSITORY.fullmatch(request.repository):
        _fail("invalid repository")
    if type(request.pull_request) is not int or request.pull_request < 1:
        _fail("invalid pull request")
    if type(request.epoch) is not int or request.epoch < 0:
        _fail("invalid epoch")
    for name in ("head", "base"):
        if not _SHA.fullmatch(getattr(request, name)):
            _fail(f"invalid {name} SHA")
    if isinstance(request, ReviewRequest):
        if not _safe_path(request.diff_path) or any(
            not _safe_path(path) for path in _list(request.context_paths, "context paths")
        ):
            _fail("invalid review path")
        if not isinstance(request.policy, dict) or len(request.policy) > _MAX_ITEMS:
            _fail("invalid review policy")
        json.dumps(request.policy)
        if any(not isinstance(lens, str) or not lens or len(lens) > 100 for lens in request.review_lenses):
            _fail("invalid review lenses")
    if isinstance(request, CodingRequest):
        if (
            request.kind not in {"change", "repair"}
            or not _REF.fullmatch(request.ref)
            or ".." in request.ref
            or "@{" in request.ref
            or type(request.merge_base) is not bool
        ):
            _fail("invalid coding kind/ref")


def _validate_review(data: JSONDict) -> ReviewResult:
    if data["status"] not in _REVIEW_STATUSES:
        _fail("invalid review status")
    findings = cast(list[JSONDict], _list(data["findings"], "findings"))
    lineage = cast(list[JSONDict], _list(data["lineage"], "lineage"))
    ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            _fail("finding must be an object")
        _exact(finding, _FINDING_FIELDS)
        finding_id = _text(finding["id"], "finding id", limit=200)
        if not _FINDING_ID.fullmatch(finding_id) or finding_id in ids:
            _fail("invalid or duplicate finding id")
        ids.add(finding_id)
        severity = finding["severity"]
        if (
            not _safe_path(finding["path"])
            or type(finding["line"]) is not int
            or finding["line"] < 1
            or severity not in _FINDING_SEVERITIES
            or not _confidence(finding["confidence"])
            or type(finding["blocking"]) is not bool
        ):
            _fail("invalid or inconsistent finding")
        primary = (finding["path"], finding["line"])
        locations = cast(list[JSONDict], _list(finding["related_locations"], "related locations"))
        seen_locations = {primary}
        for location in locations:
            if not isinstance(location, dict):
                _fail("related location must be an object")
            _exact(location, _RELATED_LOCATION_FIELDS)
            key = (location["path"], location["line"])
            if (
                not _safe_path(location["path"])
                or type(location["line"]) is not int
                or location["line"] < 1
                or key in seen_locations
            ):
                _fail("invalid or duplicate related location")
            seen_locations.add(key)
        for name in ("title", "body", "evidence", "suggestion"):
            _text(finding[name], name, empty=name == "suggestion")
        if "```" in cast(str, finding["suggestion"]):
            _fail("invalid suggestion")
    seen_lineage: set[str] = set()
    for item in lineage:
        if not isinstance(item, dict):
            _fail("lineage must be an object")
        _exact(item, _LINEAGE_FIELDS)
        finding_id = _text(item["finding_id"], "lineage finding id", limit=200)
        supersedes = item["supersedes"]
        if finding_id in seen_lineage or item["state"] not in _LINEAGE_STATES:
            _fail("invalid lineage")
        seen_lineage.add(finding_id)
        if supersedes is not None:
            _text(supersedes, "supersedes", limit=200)
        if item["state"] in {"new", "still_open"} and finding_id not in ids:
            _fail("open lineage has no finding")
        if item["state"] == "new" and supersedes is not None:
            _fail("new lineage cannot supersede")
        if item["state"] == "superseded" and supersedes is None:
            _fail("superseded lineage lacks predecessor")
    if (
        data["status"] == "clear"
        and any(x["blocking"] for x in findings)
        or data["status"] == "blocking"
        and not any(x["blocking"] for x in findings)
    ):
        _fail("review status inconsistent with findings")
    return ReviewResult(
        repository=cast(str, data["repository"]),
        pull_request=cast(int, data["pull_request"]),
        epoch=cast(int, data["epoch"]),
        head=cast(str, data["head"]),
        base=cast(str, data["base"]),
        status=cast(str, data["status"]),
        findings=findings,
        lineage=lineage,
    )


def _allowed_intents(request: ConversationRequest) -> dict[str, JSONDict]:
    allowed: dict[str, JSONDict] = {}
    for declaration in _list(request.allowed_intents, "allowed intents"):
        if not isinstance(declaration, dict) or not isinstance(declaration.get("type"), str):
            _fail("invalid allowed intent declaration")
        declaration = cast(JSONDict, declaration)
        name = cast(str, declaration["type"])
        if name in allowed:
            _fail("duplicate allowed intent")
        allowed[name] = declaration
    return allowed


def _validate_intent_arguments(arguments: JSONDict, mutation: bool) -> None:
    for name, value in arguments.items():
        if name in {"request", "message"}:
            if not _text(value, f"intent {name}").strip():
                _fail(f"invalid intent {name}")
        elif name == "assignee":
            assignee = _text(value, "intent assignee", limit=39)
            if _LOGIN.fullmatch(assignee) is None:
                _fail("invalid intent assignee")
        elif name in {"id", "finding_id"}:
            finding_id = _text(value, f"intent {name}", limit=48)
            if _FINDING_ID.fullmatch(finding_id) is None:
                _fail(f"invalid intent {name}")
        elif name == "findings":
            findings = _list(value, "intent findings")
            if not findings or any(
                not isinstance(item, str) or _FINDING_ID.fullmatch(item) is None for item in findings
            ):
                _fail("invalid intent findings")
        elif name == "target":
            if value not in {"conversation", "dashboard", "readiness"}:
                _fail("invalid publication recovery target")
        elif name == "operation":
            if not _text(value, "intent operation", limit=256).strip():
                _fail("invalid publication recovery operation")
    if mutation and not arguments:
        _fail("mutation intent lacks concrete scope")


def _validate_conversation(data: JSONDict, request: ConversationRequest) -> ConversationResult:
    allowed = _allowed_intents(request)
    intents = _list(data["intents"], "intents")
    if len(intents) != 1:
        _fail("conversation must select exactly one intent")
    for intent in intents:
        if not isinstance(intent, dict):
            _fail("intent must be an object")
        intent = cast(JSONDict, intent)
        _exact(intent, _INTENT_FIELDS)
        declared = allowed.get(intent["type"])
        if declared is None or not isinstance(intent["arguments"], dict) or len(intent["arguments"]) > _MAX_ITEMS:
            _fail("unauthorized intent or arguments")
        mutation = declared.get("mutation", False)
        if type(mutation) is not bool or intent["mutation"] is not mutation or not _confidence(intent["confidence"]):
            _fail("intent metadata differs from declaration")
        expected_arguments = declared.get("arguments")
        if isinstance(expected_arguments, list) and set(intent["arguments"]) != set(expected_arguments):
            _fail("intent arguments differ from declaration")
        if isinstance(expected_arguments, dict) and set(intent["arguments"]) != set(expected_arguments):
            _fail("intent arguments differ from declaration")
        if type(intent["explicit"]) is not bool:
            _fail("invalid intent authorization flags")
        if mutation and not intent["explicit"]:
            _fail("mutation intent was not explicit")
        if declared.get("requires_explicit", False) and not intent["explicit"]:
            _fail("intent requires explicit request")
        _validate_intent_arguments(cast(JSONDict, intent["arguments"]), mutation)
        json.dumps(intent["arguments"])
    return ConversationResult(
        repository=cast(str, data["repository"]),
        pull_request=cast(int, data["pull_request"]),
        epoch=cast(int, data["epoch"]),
        head=cast(str, data["head"]),
        base=cast(str, data["base"]),
        intents=cast(list[JSONDict], intents),
    )


def _validate_coding(data: JSONDict, request: CodingRequest, changed: list[str]) -> CodingResult:
    if data["status"] not in _CODING_STATUSES or data["reproduction_status"] not in _REPRODUCTION_STATUSES:
        _fail("invalid coding status/reproduction status")
    if (data["status"] == "changed") != bool(changed) or data["status"] == "unchanged" and changed:
        raise AgentProtocolError(
            "coding status differs from host worktree",
            result_category=AgentResultCategory.WORKSPACE_RECONCILIATION,
        )
    if request.kind == "repair" and changed and data["reproduction_status"] != "confirmed":
        _fail("repair changed result requires confirmed reproduction")
    _text(data["diff"], "diff", empty=True, limit=4_000_000)
    files = cast(list[str], _list(data["changed_files"], "changed files"))
    if files != sorted(set(files)) or files != changed or not all(_safe_path(x) for x in files):
        _fail("invalid changed files")
    message = _text(
        data["proposed_commit_message"], "proposed commit message", empty=data["status"] != "changed", limit=1000
    )
    if data["status"] == "changed" and ("\n\n\n" in message or len(message.splitlines()[0]) > 72):
        _fail("invalid proposed commit message")
    evidence = _list(data["validation_evidence"], "validation evidence")
    if data["status"] == "changed" and not evidence:
        _fail("changed result lacks validation evidence")
    for item in evidence:
        if not isinstance(item, dict) or not item or len(item) > 20:
            _fail("invalid validation evidence")
        if len(json.dumps(item).encode()) > _MAX_TEXT:
            _fail("validation evidence too large")
    return CodingResult(
        kind=cast(str, data["kind"]),
        repository=cast(str, data["repository"]),
        pull_request=cast(int, data["pull_request"]),
        epoch=cast(int, data["epoch"]),
        head=cast(str, data["head"]),
        base=cast(str, data["base"]),
        ref=cast(str, data["ref"]),
        status=cast(str, data["status"]),
        reproduction_status=cast(str, data["reproduction_status"]),
        diff=cast(str, data["diff"]),
        changed_files=files,
        validation_evidence=cast(list[JSONDict], evidence),
        proposed_commit_message=message,
    )


def _validate_result(kind: str, data: object, request: AgentRequest, changed: list[str] | None = None) -> AgentResult:
    if not isinstance(data, dict):
        _fail("result must be a JSON object")
    data = cast(JSONDict, data)
    _correlate(data, request, _COMMON_RESULT_FIELDS)
    if kind == "review":
        _exact(data, _REVIEW_RESULT_FIELDS)
        return _validate_review(data)
    if kind == "conversation":
        _exact(data, _CONVERSATION_RESULT_FIELDS)
        if not isinstance(request, ConversationRequest):
            raise AgentProtocolError(
                "request kind differs from result kind", result_category=AgentResultCategory.CORRELATION
            )
        return _validate_conversation(data, request)
    _exact(data, _CODING_RESULT_FIELDS)
    _correlate(data, request, ("kind", "ref"))
    if not isinstance(request, CodingRequest):
        raise AgentProtocolError(
            "request kind differs from result kind", result_category=AgentResultCategory.CORRELATION
        )
    return _validate_coding(data, request, changed or [])
