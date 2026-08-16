"""Provider-backed review-agent gate for the V5 topology (CV17.DS2.1c).

The review loop owns prior-finding selection and the globally scoped
logical operation. This host adapter only gathers credential-free
context, invokes the existing routed AgentRunner, and classifies clean
agent inability separately from genuine activity failures.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from pydantic import TypeAdapter, ValidationError

from hamsterdan.agents.protocol import (
    AgentProtocolError,
    AgentResultCategory,
    AgentRunner,
    ReviewRequest,
)
from hamsterdan.contracts.readiness_v5 import (
    AgentReview,
    ReviewUnableCategory,
    RoundMoved,
    RoundOpen,
    RoundUnable,
)
from hamsterdan.host.v5.claim import ClaimReader, CurrentClaim

LOG = logging.getLogger(__name__)
_REQUEST_ADAPTER = TypeAdapter(ReviewRequest)
_REVIEW_LENSES = ["correctness", "security", "tests", "maintainability", "developer experience"]

_RESULT_CATEGORIES: dict[AgentResultCategory, ReviewUnableCategory] = {
    AgentResultCategory.RUNTIME_LIFECYCLE: "runtime_lifecycle",
    AgentResultCategory.OUTPUT_SCHEMA: "output_schema",
    AgentResultCategory.CORRELATION: "correlation",
    AgentResultCategory.UNCHANGED: "unchanged",
    AgentResultCategory.UNABLE: "unable",
    AgentResultCategory.WORKSPACE_RECONCILIATION: "workspace_reconciliation",
}


class ReviewAuthority(Protocol):
    """Read-only provider context gathered before agent execution."""

    def comments(self) -> tuple[dict[str, Any], ...] | list[dict[str, Any]]: ...

    def select_run(self, workflow: str, head: str) -> Any | None: ...


class ReviewRequestCustody(Protocol):
    """Freeze the exact credential-free request before Agenticus submission."""

    def lookup(self, operation: str) -> ReviewRequest | None: ...

    def claim(self, operation: str, request: ReviewRequest) -> ReviewRequest: ...


def _encode_request(request: ReviewRequest) -> str:
    return json.dumps(asdict(request), sort_keys=True, separators=(",", ":"))


def _load_request(raw: object, digest: object) -> ReviewRequest:
    if not isinstance(raw, str) or not isinstance(digest, str) or sha256(raw.encode()).hexdigest() != digest:
        raise RuntimeError("stored V5 review request digest is invalid")
    try:
        request = _REQUEST_ADAPTER.validate_json(raw, strict=True)
    except ValidationError:
        raise RuntimeError("stored V5 review request is malformed") from None
    if _encode_request(request) != raw:
        raise RuntimeError("stored V5 review request is not canonical")
    return request


class V5ReviewRequestStore:
    """Durable, operation-keyed custody for exact Agenticus review inputs."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._database = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        try:
            self._database.execute("PRAGMA journal_mode=WAL")
            self._database.execute("PRAGMA synchronous=FULL")
            self._database.execute(
                """CREATE TABLE IF NOT EXISTS v5_review_requests (
                    operation TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    digest TEXT NOT NULL
                )"""
            )
        except BaseException:
            self._database.close()
            raise

    def lookup(self, operation: str) -> ReviewRequest | None:
        with self._lock:
            row = self._database.execute(
                "SELECT request_json,digest FROM v5_review_requests WHERE operation=?",
                (operation,),
            ).fetchone()
        return None if row is None else _load_request(*row)

    def claim(self, operation: str, request: ReviewRequest) -> ReviewRequest:
        raw = _encode_request(request)
        digest = sha256(raw.encode()).hexdigest()
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                self._database.execute(
                    "INSERT OR IGNORE INTO v5_review_requests VALUES(?,?,?)",
                    (operation, raw, digest),
                )
                row = self._database.execute(
                    "SELECT request_json,digest FROM v5_review_requests WHERE operation=?",
                    (operation,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("V5 review request custody did not retain its claim")
                claimed = _load_request(*row)
                self._database.commit()
                return claimed
            except BaseException:
                self._database.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._database.close()


def _category(error: AgentProtocolError) -> ReviewUnableCategory:
    if error.timed_out:
        return "timed_out"
    if error.canceled:
        return "canceled"
    if error.result_category is not None:
        return _RESULT_CATEGORIES[error.result_category]
    if error.cleanup_category is not None:
        return "cleanup_unverified"
    return "protocol"


@dataclass(frozen=True)
class V5ReviewGate:
    """Translate one V5 round to the existing credential-free runner."""

    repository: str
    pull_request: int
    authority: ReviewAuthority
    runner: AgentRunner
    public_clone_url: str
    workflow_path: str
    claim: ClaimReader
    requests: ReviewRequestCustody

    def review_agent(self, work: RoundOpen) -> AgentReview | RoundMoved | RoundUnable:
        expected = CurrentClaim(
            phase="running",
            incarnation=work.incarnation,
            head=work.head,
            base=work.base,
            policy=work.policy,
        )
        request = self.requests.lookup(work.operation)
        if request is not None:
            self._validate_request(work, request)
        observed = self.claim()
        if observed != expected:
            return RoundMoved(
                head=work.head,
                incarnation=work.incarnation,
                observed=observed.head,
                observed_base=observed.base,
                observed_policy=observed.policy,
                observed_incarnation=observed.incarnation,
                observed_phase=observed.phase,
                mem=work.mem,
            )
        if request is None:
            request = self.requests.claim(work.operation, self._compose_request(work))
            self._validate_request(work, request)
        try:
            result = self.runner.review(
                self.public_clone_url,
                request,
                operation=work.operation,
                attempt=1,
                is_current=self._current(expected),
            )
        except AgentProtocolError as error:
            category = _category(error)
            LOG.warning(
                "V5 review agent unavailable category=%s incarnation=%s head=%s operation=%s",
                category,
                work.incarnation,
                work.head,
                work.operation,
            )
            return RoundUnable(
                head=work.head,
                incarnation=work.incarnation,
                category=category,
                mem=work.mem,
            )
        if result.status == "unable":
            return RoundUnable(
                head=work.head,
                incarnation=work.incarnation,
                category="unable",
                mem=work.mem,
            )
        if result.status not in ("clear", "blocking"):
            raise ValueError("agent returned an unrecognized review status")
        return AgentReview(
            head=work.head,
            base=work.base,
            policy=work.policy,
            incarnation=work.incarnation,
            findings=result.findings,
            lineage=result.lineage,
            mem=work.mem,
        )

    def _compose_request(self, work: RoundOpen) -> ReviewRequest:
        comments = [
            {
                "id": item.get("id"),
                "url": item.get("html_url", ""),
                "body": str(item.get("body", ""))[:20_000],
                "author": item.get("user", {}).get("login", "") if isinstance(item.get("user"), dict) else "",
            }
            for item in self.authority.comments()[-100:]
        ]
        run = self.authority.select_run(self.workflow_path, work.head)
        return ReviewRequest(
            repository=self.repository,
            pull_request=self.pull_request,
            epoch=work.incarnation,
            head=work.head,
            base=work.base,
            diff_path="diff.patch",
            policy={"digest": work.policy},
            review_lenses=_REVIEW_LENSES,
            actions_evidence=[] if run is None else [asdict(run)],
            prior_findings=work.prior_findings,
            prior_comments=comments,
            prior_replies=[],
            applied_changes=work.prior_lineage,
        )

    def _validate_request(self, work: RoundOpen, request: ReviewRequest) -> None:
        frozen = (
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            request.diff_path,
            request.policy,
            request.review_lenses,
            request.context_paths,
            request.prior_findings,
            request.prior_replies,
            request.applied_changes,
        )
        expected = (
            self.repository,
            self.pull_request,
            work.incarnation,
            work.head,
            work.base,
            "diff.patch",
            {"digest": work.policy},
            _REVIEW_LENSES,
            [],
            work.prior_findings,
            [],
            work.prior_lineage,
        )
        if frozen != expected:
            raise RuntimeError("V5 review operation selected a different review request")

    def _current(self, expected: CurrentClaim) -> Callable[[], bool]:
        return lambda: self.claim() == expected


__all__ = ["V5ReviewGate", "V5ReviewRequestStore"]
