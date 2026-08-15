"""Provider-backed review-agent gate for the V5 topology (CV17.DS2.1c).

The review loop owns prior-finding selection and the globally scoped
logical operation. This host adapter only gathers credential-free
context, invokes the existing routed AgentRunner, and classifies clean
agent inability separately from genuine activity failures.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from hamsterdan.agents.protocol import (
    AgentProtocolError,
    AgentResultCategory,
    AgentRunner,
    ReviewRequest,
)
from hamsterdan.contracts.readiness_v5 import (
    AgentReview,
    ReviewUnableCategory,
    RoundOpen,
    RoundUnable,
)
from hamsterdan.host.v5.claim import ClaimReader, CurrentClaim

LOG = logging.getLogger(__name__)

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

    def review_agent(self, work: RoundOpen) -> AgentReview | RoundUnable:
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
        expected = CurrentClaim(
            phase="running",
            incarnation=work.incarnation,
            head=work.head,
            base=work.base,
            policy=work.policy,
        )
        request = ReviewRequest(
            repository=self.repository,
            pull_request=self.pull_request,
            epoch=work.incarnation,
            head=work.head,
            base=work.base,
            diff_path="diff.patch",
            policy={"digest": work.policy},
            review_lenses=["correctness", "security", "tests", "maintainability", "developer experience"],
            actions_evidence=[] if run is None else [asdict(run)],
            prior_findings=work.prior_findings,
            prior_comments=comments,
            prior_replies=[],
            applied_changes=work.prior_lineage,
        )
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

    def _current(self, expected: CurrentClaim) -> Callable[[], bool]:
        return lambda: self.claim() == expected
