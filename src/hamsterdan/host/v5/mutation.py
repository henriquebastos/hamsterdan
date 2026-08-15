"""Provider-backed coding-agent and exact-CAS gate for V5 mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Protocol

from hamsterdan.agents.protocol import AgentProtocolError, AgentRunner, CodingRequest, CodingResult
from hamsterdan.contracts.readiness_v5 import DeclinedM, FaultM, MovedM, MutWork, Pushed
from hamsterdan.github_app.models import GitHubBoundaryError
from hamsterdan.host.git_publish import (
    GitPublishError,
    GitPublishResult,
    GitReconciliation,
    PublicationCategory,
    payload_digest,
)
from hamsterdan.host.v5.claim import ClaimReader, CurrentClaim


class MutationPublisher(Protocol):
    def reconcile(
        self,
        *,
        operation: str,
        payload_digest: str,
        expected_head: str,
        base_head: str,
        merge_base: bool = False,
    ) -> GitReconciliation: ...

    def publish(
        self,
        result: CodingResult,
        *,
        operation: str,
        payload_digest: str,
        expected_head: str,
        base_head: str,
        merge_base: bool = False,
    ) -> GitPublishResult: ...


def _reason(error: Exception) -> str:
    return str(error) or repr(error)


def _agent_category(error: AgentProtocolError) -> str:
    if error.timed_out:
        return "timed_out"
    if error.canceled:
        return "canceled"
    if error.result_category is not None:
        return error.result_category.value
    if error.cleanup_category is not None:
        return error.cleanup_category.value
    return "protocol"


@dataclass(frozen=True)
class V5MutationGate:
    """Run one globally identified coding attempt and publish it once.

    Provider reconciliation precedes every authority read and agent call.
    The full host/provider claim is then checked both before and after the
    agent; the exact ref CAS remains the final atomic head fence.
    """

    repository: str
    pull_request: int
    runner: AgentRunner
    publisher: MutationPublisher
    public_clone_url: str
    claim: ClaimReader

    @staticmethod
    def request(repository: str, pull_request: int, work: MutWork) -> CodingRequest:
        operation = f"mutation:{repository}:pr:{pull_request}:{work.op_key}"
        ref = f"hamsterdan/mutation/{sha256(operation.encode()).hexdigest()[:32]}"
        selected_work: list[dict[str, object]]
        failure_evidence: list[dict[str, object]]
        lineage: list[dict[str, object]]
        if work.kind == "repair":
            prefix = f"repair:{work.lineage}:"
            if (
                not work.lineage
                or not work.op.startswith(prefix)
                or not work.op.removeprefix(prefix)
                or work.instruction
                or work.run_id <= 0
                or work.attempt <= 0
            ):
                raise ValueError("repair mutation payload is malformed")
            fingerprint = work.op.removeprefix(prefix)
            selected_work = []
            failure_evidence = [
                {
                    "head": work.head,
                    "run_id": work.run_id,
                    "attempt": work.attempt,
                    "conclusion": "failure",
                    "fingerprint": fingerprint,
                }
            ]
            lineage = [{"kind": "repair_budget", "lineage": work.lineage, "operation": work.op}]
        else:
            if work.kind not in {"change", "update_base", "resolve_conflict"}:
                raise ValueError("mutation kind is malformed")
            fingerprint = ""
            selected_work = [{"kind": work.kind, "request": work.instruction}]
            failure_evidence = []
            lineage = []
        return CodingRequest(
            kind="repair" if work.kind == "repair" else "change",
            repository=repository,
            pull_request=pull_request,
            epoch=work.incarnation,
            head=work.head,
            base=work.base,
            ref=ref,
            selected_work=selected_work,
            failure_evidence=failure_evidence,
            fingerprint=fingerprint,
            lineage=lineage,
            reproduction_status="unknown",
            merge_base=work.kind in {"update_base", "resolve_conflict"},
        )

    def git_gate(self, work: MutWork) -> Pushed | MovedM | FaultM | DeclinedM:
        request = self.request(self.repository, self.pull_request, work)
        agent_operation = f"mutation:{self.repository}:pr:{self.pull_request}:{work.op_key}"
        digest = payload_digest(
            {
                "schema_version": 1,
                "semantic_operation": work.op,
                "policy": work.policy,
                "coding_request": asdict(request),
            }
        )
        reconciliation = self._reconcile(work, request, digest)
        if isinstance(reconciliation, FaultM):
            return reconciliation
        if reconciliation.disposition == "existing":
            return self._pushed(work, reconciliation.commit)

        expected = CurrentClaim("running", work.incarnation, work.head, work.base, work.policy)
        current = self._read_claim(work)
        if isinstance(current, FaultM):
            return current
        if current != expected:
            return self._moved(work, current)

        result: CodingResult | None = None
        agent_error: AgentProtocolError | None = None
        try:
            result = self.runner.code(
                self.public_clone_url,
                request,
                operation=agent_operation,
                attempt=1,
                is_current=self._current(expected),
            )
        except AgentProtocolError as error:
            agent_error = error

        current = self._read_claim(work)
        if isinstance(current, FaultM):
            return current
        if current != expected:
            return self._moved(work, current)
        if agent_error is not None:
            return self._declined(work, _agent_category(agent_error), _reason(agent_error))
        assert result is not None
        correlation = (
            result.kind,
            result.repository,
            result.pull_request,
            result.epoch,
            result.head,
            result.base,
            result.ref,
        )
        expected_correlation = (
            request.kind,
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            request.ref,
        )
        if correlation != expected_correlation:
            return self._declined(work, "correlation", "agent result did not match its request")
        if result.status != "changed":
            category = result.status if result.status in {"unchanged", "unable"} else "output_schema"
            return self._declined(work, category, "agent produced no publishable change")

        try:
            published = self.publisher.publish(
                result,
                operation=work.op_key,
                payload_digest=digest,
                expected_head=work.head,
                base_head=work.base,
                merge_base=request.merge_base,
            )
        except GitPublishError as error:
            if error.category in {PublicationCategory.CORRELATION, PublicationCategory.PATCH_ADMISSION}:
                return self._declined(work, error.category.value, _reason(error))
            if error.category is PublicationCategory.CURRENT_AUTHORITY:
                current = self._read_claim(work)
                return current if isinstance(current, FaultM) else self._moved(work, current)
            if error.category is PublicationCategory.REF_CAS:
                reconciliation = self._reconcile(work, request, digest)
                if isinstance(reconciliation, FaultM):
                    return reconciliation
                if reconciliation.disposition == "existing":
                    return self._pushed(work, reconciliation.commit)
            return self._fault(work, _reason(error))
        except GitHubBoundaryError as error:
            return self._fault(work, _reason(error))
        return self._pushed(work, published.head)

    def _reconcile(self, work: MutWork, request: CodingRequest, digest: str) -> GitReconciliation | FaultM:
        try:
            return self.publisher.reconcile(
                operation=work.op_key,
                payload_digest=digest,
                expected_head=work.head,
                base_head=work.base,
                merge_base=request.merge_base,
            )
        except (GitPublishError, GitHubBoundaryError) as error:
            return self._fault(work, _reason(error))

    def _read_claim(self, work: MutWork) -> CurrentClaim | FaultM:
        try:
            return self.claim()
        except (GitHubBoundaryError, RuntimeError, ValueError) as error:
            return self._fault(work, _reason(error))

    def _current(self, expected: CurrentClaim) -> Callable[[], bool]:
        return lambda: self.claim() == expected

    @staticmethod
    def _pushed(work: MutWork, head: str) -> Pushed:
        return Pushed(work.op, work.op_key, work.head, head, work.incarnation, work.lineage)

    @staticmethod
    def _moved(work: MutWork, current: CurrentClaim) -> MovedM:
        return MovedM(
            work.op,
            work.op_key,
            work.head,
            work.incarnation,
            current.head,
            current.base,
            current.policy,
            current.incarnation,
            current.phase,
        )

    @staticmethod
    def _declined(work: MutWork, category: str, reason: str) -> DeclinedM:
        return DeclinedM(work.op, work.op_key, work.head, work.incarnation, category, reason)

    @staticmethod
    def _fault(work: MutWork, reason: str) -> FaultM:
        return FaultM(
            work.op,
            work.op_key,
            work.head,
            work.base,
            work.policy,
            reason,
            work.incarnation,
            work.kind,
            work.instruction,
            work.run_id,
            work.attempt,
        )
