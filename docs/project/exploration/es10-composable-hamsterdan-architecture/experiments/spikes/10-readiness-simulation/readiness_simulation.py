"""Standalone readiness simulation module for ES-010 experiment 10.

The module mounts unchanged beneath experiment 9's ``Timeline``. It executes
the production mutation gate and its production Git publication port shape;
only provider truth, agent execution, and the not-yet-production readiness
step are experimental.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from typing import Any, Protocol, cast

from runtime import ActionRef, Budget, Timeline

from hamsterdan.agents.protocol import AgentProtocolError, AgentRunner, CodingRequest, CodingResult
from hamsterdan.contracts.readiness_v5 import DeclinedM, FaultM, MovedM, MutWork, Pushed
from hamsterdan.github_app.models import GitHubBoundaryError
from hamsterdan.host.git_publish import (
    GitPublishError,
    GitPublishResult,
    GitReconciliation,
    PublicationCategory,
)
from hamsterdan.host.git_publish import (
    payload_digest as digest_payload,
)
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.mutation import V5MutationGate

AUTHORITY_FIELDS = {"phase", "incarnation", "head", "base", "policy"}
WORK_FIELDS = {
    "op",
    "op_key",
    "head",
    "base",
    "policy",
    "incarnation",
    "lineage",
    "kind",
    "instruction",
    "run_id",
    "attempt",
}
COMMANDS = ("admit_grant", "request_mutation", "set_provider_authority")
OBSERVATIONS = ("check", "state")
FAULTS = ("git_response_lost",)
TERMINALS = (Pushed, MovedM, FaultM, DeclinedM)

DEFAULT_BUDGET = Budget(
    operations=128,
    owner_steps=16,
    eligible_actions=8,
    leaf_calls=16,
    choice_draws=8,
    active_faults=8,
    generations=8,
    logical_time_us=1_000,
    journal_entries=512,
    artifact_bytes=1_000_000,
    resources={
        "readiness.calls": 32,
        "readiness.claims": 8,
        "readiness.publications": 8,
        "readiness.requests": 8,
        "readiness.terminals": 8,
    },
)


class CodingRunner(Protocol):
    def code(
        self,
        repository_url: str,
        request: CodingRequest,
        *,
        operation: str,
        attempt: int,
        is_current: Any = None,
    ) -> CodingResult: ...


def _exact_payload(value: object, fields: set[str], subject: str) -> dict[str, object]:
    if type(value) is not dict or set(cast(dict[object, object], value)) != fields:
        raise ValueError(f"{subject} payload must contain exactly {sorted(fields)!r}")
    return cast(dict[str, object], value)


def _authority(value: object) -> CurrentClaim:
    payload = _exact_payload(value, AUTHORITY_FIELDS, "authority")
    phase = payload["phase"]
    incarnation = payload["incarnation"]
    head, base, policy = payload["head"], payload["base"], payload["policy"]
    if phase not in {"running", "quiescent", "terminal"}:
        raise ValueError("authority phase must be running, quiescent, or terminal")
    if type(incarnation) is not int or incarnation < 1:
        raise ValueError("authority incarnation must be a positive integer")
    if any(type(item) is not str or not item for item in (head, base, policy)):
        raise ValueError("authority head, base, and policy must be non-empty strings")
    return CurrentClaim(
        cast(Any, phase),
        incarnation,
        cast(str, head),
        cast(str, base),
        cast(str, policy),
    )


def _authority_payload(claim: CurrentClaim) -> dict[str, object]:
    return {
        "phase": claim.phase,
        "incarnation": claim.incarnation,
        "head": claim.head,
        "base": claim.base,
        "policy": claim.policy,
    }


def _work(value: object) -> MutWork:
    payload = _exact_payload(value, WORK_FIELDS, "mutation work")
    work = MutWork(**cast(dict[str, Any], payload))
    V5MutationGate.request("owner/repo", 7, work)
    return work


def _terminal_payload(value: object) -> dict[str, object]:
    if not isinstance(value, TERMINALS):
        raise TypeError("production mutation gate returned an undeclared terminal")
    return {"variant": type(value).__name__, "value": value.dump()}


@dataclass
class Publication:
    operation: str
    payload_digest: str
    coding_result_digest: str
    expected_head: str
    base_head: str
    result_head: str
    accepted_authority: CurrentClaim
    accepted_sequence: int
    response_lost: bool = False
    recovered: bool = False

    def dump(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "payload_digest": self.payload_digest,
            "coding_result_digest": self.coding_result_digest,
            "expected_head": self.expected_head,
            "base_head": self.base_head,
            "result_head": self.result_head,
            "accepted_authority": _authority_payload(self.accepted_authority),
            "accepted_sequence": self.accepted_sequence,
            "response_lost": self.response_lost,
            "recovered": self.recovered,
        }


@dataclass
class ProviderTruth:
    authority: CurrentClaim | None = None
    publications: dict[str, Publication] = field(default_factory=dict)
    calls: list[dict[str, object]] = field(default_factory=list)
    sequence: int = 0

    def record(self, kind: str, operation: str) -> int:
        self.sequence += 1
        self.calls.append({"sequence": self.sequence, "kind": kind, "operation": operation})
        return self.sequence

    def dump(self) -> dict[str, object]:
        return {
            "authority": None if self.authority is None else _authority_payload(self.authority),
            "publications": [item.dump() for item in self.publications.values()],
            "calls": [dict(item) for item in self.calls],
        }


@dataclass
class ReadinessStore:
    grant: CurrentClaim | None = None
    requests: dict[str, MutWork] = field(default_factory=dict)
    claims: set[str] = field(default_factory=set)
    terminals: dict[str, dict[str, object]] = field(default_factory=dict)


class AuthorityReader:
    def __init__(self, readiness: ReadinessStore, provider: ProviderTruth, operation: str) -> None:
        self.readiness = readiness
        self.provider = provider
        self.operation = operation

    def __call__(self) -> CurrentClaim:
        self.provider.record("claim", self.operation)
        if self.readiness.grant is None or self.provider.authority is None:
            raise GitHubBoundaryError("readiness authority is unavailable")
        if self.readiness.grant != self.provider.authority:
            raise GitHubBoundaryError("fresh provider authority differs from the durable readiness grant")
        return self.readiness.grant


class DeterministicCodingAgent:
    def __init__(self, work: MutWork) -> None:
        self.work = work

    def code(
        self,
        repository_url: str,
        request: CodingRequest,
        *,
        operation: str,
        attempt: int,
        is_current: Any = None,
    ) -> CodingResult:
        expected_operation = f"mutation:owner/repo:pr:7:{self.work.op_key}"
        if repository_url != "https://example.test/owner/repo.git":
            raise AssertionError("coding agent received an undeclared repository URL")
        if operation != expected_operation or attempt != 1:
            raise AssertionError("coding agent received an undeclared operation or attempt")
        expected_request = V5MutationGate.request("owner/repo", 7, self.work)
        if request != expected_request:
            raise AssertionError("coding agent received an undeclared mutation request")
        if is_current is None or not is_current():
            raise AgentProtocolError("coding authority moved", canceled=True)
        return CodingResult(
            kind=request.kind,
            repository=request.repository,
            pull_request=request.pull_request,
            epoch=request.epoch,
            head=request.head,
            base=request.base,
            ref=request.ref,
            status="changed",
            reproduction_status="not_attempted",
            diff="diff --git a/a b/a\n",
            changed_files=["a"],
            validation_evidence=[],
            proposed_commit_message="Apply requested change",
        )


class RecordedCodingAgent:
    def __init__(self, provider: ProviderTruth, work: MutWork, runner: CodingRunner) -> None:
        self.provider = provider
        self.work = work
        self.runner = runner

    def code(
        self,
        repository_url: str,
        request: CodingRequest,
        *,
        operation: str,
        attempt: int,
        is_current: Any = None,
    ) -> CodingResult:
        self.provider.record("agent", self.work.op_key)
        return self.runner.code(
            repository_url,
            request,
            operation=operation,
            attempt=attempt,
            is_current=is_current,
        )


class DeterministicGitPublisher:
    def __init__(self, provider: ProviderTruth, work: MutWork, context: Any) -> None:
        self.provider = provider
        self.work = work
        self.context = context

    def reconcile(
        self,
        *,
        operation: str,
        payload_digest: str,
        expected_head: str,
        base_head: str,
        merge_base: bool = False,
    ) -> GitReconciliation:
        self.validate_operation(operation, expected_head, base_head, merge_base)
        self.provider.record("reconcile", operation)
        publication = self.provider.publications.get(operation)
        if publication is None:
            if self.provider.authority is None:
                raise GitPublishError(PublicationCategory.BOUNDARY_UNAVAILABLE, "provider authority is unavailable")
            return GitReconciliation("absent", self.provider.authority.head)
        if publication.payload_digest != payload_digest:
            raise GitPublishError(PublicationCategory.IDEMPOTENCY, "modeled Git operation identity collided")
        publication.recovered = True
        parents = (publication.expected_head, *([publication.base_head] if merge_base else []))
        observed = publication.result_head if self.provider.authority is None else self.provider.authority.head
        return GitReconciliation("existing", observed, publication.result_head, parents)

    def publish(
        self,
        result: CodingResult,
        *,
        operation: str,
        payload_digest: str,
        expected_head: str,
        base_head: str,
        merge_base: bool = False,
    ) -> GitPublishResult:
        self.validate_operation(operation, expected_head, base_head, merge_base)
        if operation in self.provider.publications:
            raise GitPublishError(PublicationCategory.IDEMPOTENCY, "modeled Git operation was accepted twice")
        expected_authority = CurrentClaim(
            "running",
            self.work.incarnation,
            self.work.head,
            self.work.base,
            self.work.policy,
        )
        if self.provider.authority != expected_authority:
            raise GitPublishError(PublicationCategory.CURRENT_AUTHORITY, "provider authority moved before Git effect")
        if (result.head, result.base, result.status) != (expected_head, base_head, "changed"):
            raise GitPublishError(PublicationCategory.CORRELATION, "modeled Git publication is stale")
        faults = self.context.faults("git.publish.after_accept")
        if len(faults) > 1:
            raise ValueError("git_response_lost matched more than one fault")
        response_lost = False
        if faults:
            payload = _exact_payload(faults[0].payload, {"operation", "response_lost"}, "git_response_lost")
            if payload != {"operation": operation, "response_lost": True}:
                raise ValueError("git_response_lost fault differs from the executing operation")
            response_lost = True
        coding_result_digest = digest_payload({"schema_version": 1, "coding_result": asdict(result)})
        result_head = sha256(
            f"{expected_head}\0{operation}\0{payload_digest}\0{coding_result_digest}".encode()
        ).hexdigest()[:40]
        accepted_sequence = self.provider.record("publish_accepted", operation)
        publication = Publication(
            operation=operation,
            payload_digest=payload_digest,
            coding_result_digest=coding_result_digest,
            expected_head=expected_head,
            base_head=base_head,
            result_head=result_head,
            accepted_authority=expected_authority,
            accepted_sequence=accepted_sequence,
            response_lost=response_lost,
        )
        self.provider.publications[operation] = publication
        self.provider.authority = replace(expected_authority, head=result_head)
        if response_lost:
            raise GitHubBoundaryError("modeled Git ref update response was lost after acceptance")
        return GitPublishResult(result_head)

    def validate_operation(self, operation: str, expected_head: str, base_head: str, merge_base: bool) -> None:
        if operation != self.work.op_key:
            raise AssertionError("Git publisher received an undeclared operation")
        if (expected_head, base_head, merge_base) != (
            self.work.head,
            self.work.base,
            self.work.kind in {"update_base", "resolve_conflict"},
        ):
            raise AssertionError("Git publisher received undeclared authority or parent semantics")


class ReadinessChecker:
    """Derive effect correctness from request facts, provider truth, and terminals."""

    def check(self, state: object) -> dict[str, object]:
        data = _exact_payload(state, {"grant", "provider", "requests", "claims", "terminals"}, "readiness state")
        provider = _exact_payload(data["provider"], {"authority", "publications", "calls"}, "provider state")
        requests = cast(list[dict[str, object]], data["requests"])
        terminals = cast(list[dict[str, object]], data["terminals"])
        publications = cast(list[dict[str, object]], provider["publications"])
        calls = cast(list[dict[str, object]], provider["calls"])
        request_by_operation = {
            cast(str, item["operation"]): cast(dict[str, object], item["value"]) for item in requests
        }
        terminal_by_operation = {cast(str, item["operation"]): item for item in terminals}
        publication_by_operation = {cast(str, publication["operation"]): publication for publication in publications}
        acceptances = [call for call in calls if call["kind"] == "publish_accepted"]
        violations: list[dict[str, object]] = []
        counts = Counter(cast(str, acceptance["operation"]) for acceptance in acceptances)
        for operation, observed in sorted(counts.items()):
            if observed > 1:
                violations.append(
                    {
                        "operation": operation,
                        "rule": "one_effect_acceptance_per_operation",
                        "observed": observed,
                    }
                )
                continue
            publication = publication_by_operation.get(operation)
            if publication is None:
                violations.append({"operation": operation, "rule": "accepted_effect_has_provider_result"})
                continue
            request = request_by_operation.get(operation)
            if request is None:
                violations.append({"operation": operation, "rule": "accepted_effect_has_request"})
                continue
            expected_authority = {
                "phase": "running",
                "incarnation": request["incarnation"],
                "head": request["head"],
                "base": request["base"],
                "policy": request["policy"],
            }
            if publication["accepted_authority"] != expected_authority:
                violations.append({"operation": operation, "rule": "effect_uses_requested_authority"})
            if publication["expected_head"] != request["head"] or publication["base_head"] != request["base"]:
                violations.append({"operation": operation, "rule": "effect_uses_requested_git_parents"})
            terminal = terminal_by_operation.get(operation)
            if terminal is not None and (
                terminal["variant"] != "Pushed"
                or cast(dict[str, object], terminal["value"])["new_head"] != publication["result_head"]
            ):
                violations.append({"operation": operation, "rule": "terminal_matches_provider_effect"})
            acceptance_index = next(
                index
                for index, call in enumerate(calls)
                if call["kind"] == "publish_accepted" and call["operation"] == operation
            )
            later = [call for call in calls[acceptance_index + 1 :] if call["operation"] == operation]
            if later and (
                later[0]["kind"] != "reconcile" or any(call["kind"] in {"agent", "publish_accepted"} for call in later)
            ):
                violations.append({"operation": operation, "rule": "recovery_is_lookup_first"})
        for operation in sorted(publication_by_operation.keys() - counts.keys()):
            violations.append({"operation": operation, "rule": "provider_result_has_accepted_effect"})
        facts = {
            "accepted_effects": len(acceptances),
            "agent_calls": sum(call["kind"] == "agent" for call in calls),
            "pending_requests": len(request_by_operation.keys() - terminal_by_operation.keys()),
            "terminals": len(terminals),
        }
        if acceptances and not terminals:
            status = "recoverable_ambiguity"
        elif acceptances:
            status = "settled"
        elif terminals:
            status = "fenced"
        else:
            status = "pending"
        return {"passed": not violations, "status": status, "violations": violations, "facts": facts}


class ReadinessModule:
    """One PR readiness owner mounted through experiment 9's module contract."""

    name = "readiness"

    def __init__(self, runner: CodingRunner | None = None) -> None:
        self.readiness = ReadinessStore()
        self.provider = ProviderTruth()
        self.runner = runner

    def open(self, _context: object) -> ReadinessGeneration:
        return ReadinessGeneration(self.readiness, self.provider, self.runner)

    def drop(self, _generation: ReadinessGeneration) -> None:
        pass

    def close(self, _generation: ReadinessGeneration) -> None:
        pass

    def resource_usage(self, _generation: ReadinessGeneration | None) -> dict[str, int]:
        return {
            "readiness.calls": len(self.provider.calls),
            "readiness.claims": len(self.readiness.claims),
            "readiness.publications": len(self.provider.publications),
            "readiness.requests": len(self.readiness.requests),
            "readiness.terminals": len(self.readiness.terminals),
        }


class ReadinessGeneration:
    def __init__(self, readiness: ReadinessStore, provider: ProviderTruth, runner: CodingRunner | None) -> None:
        self.readiness = readiness
        self.provider = provider
        self.runner = runner

    def command(self, name: str, payload: object, _context: object) -> object:
        if name == "admit_grant":
            return self.admit_grant(payload)
        if name == "set_provider_authority":
            return self.set_provider_authority(payload)
        if name == "request_mutation":
            return self.request_mutation(payload)
        raise ValueError(f"unknown readiness command {name!r}; expected {', '.join(COMMANDS[:-1])}, or {COMMANDS[-1]}")

    def admit_grant(self, payload: object) -> object:
        claim = _authority(payload)
        if self.readiness.requests and claim != self.readiness.grant:
            raise ValueError("readiness grant cannot move while mutation work is retained")
        existing = self.readiness.grant == claim
        self.readiness.grant = claim
        return {"existing": existing, "authority": _authority_payload(claim)}

    def set_provider_authority(self, payload: object) -> object:
        claim = _authority(payload)
        existing = self.provider.authority == claim
        self.provider.authority = claim
        return {"existing": existing, "authority": _authority_payload(claim)}

    def request_mutation(self, payload: object) -> object:
        work = _work(payload)
        if self.readiness.grant is None:
            raise ValueError("admit the readiness grant before requesting mutation")
        expected = CurrentClaim("running", work.incarnation, work.head, work.base, work.policy)
        if self.readiness.grant != expected:
            raise ValueError("mutation request authority differs from the durable readiness grant")
        previous = self.readiness.requests.get(work.op_key)
        if previous is not None and previous != work:
            raise ValueError("stable mutation operation was reused with different work")
        self.readiness.requests[work.op_key] = work
        return {"existing": previous is not None, "operation": work.op_key}

    def observe(self, name: str, payload: object, _context: object) -> object:
        if payload not in (None, {}):
            raise ValueError("readiness observations accept no parameters")
        if name == "state":
            return self.state()
        if name == "check":
            return ReadinessChecker().check(self.state())
        raise ValueError(f"unknown readiness observation {name!r}; expected {OBSERVATIONS[0]} or {OBSERVATIONS[1]}")

    def state(self) -> dict[str, object]:
        return {
            "grant": None if self.readiness.grant is None else _authority_payload(self.readiness.grant),
            "provider": self.provider.dump(),
            "requests": [
                {"operation": operation, "value": work.dump()}
                for operation, work in sorted(self.readiness.requests.items())
            ],
            "claims": sorted(self.readiness.claims),
            "terminals": [dict(value) for _, value in sorted(self.readiness.terminals.items())],
        }

    def eligible_actions(self, _context: object) -> tuple[ActionRef, ...]:
        return tuple(
            ActionRef(module="readiness", name="settle_mutation", identity=operation, eligible_at_us=0)
            for operation in sorted(self.readiness.requests.keys() - self.readiness.terminals.keys())
        )

    async def step(self, action: ActionRef, context: Any) -> object:
        if action.module != "readiness" or action.name != "settle_mutation" or action.eligible_at_us != 0:
            raise ValueError("readiness received an undeclared action")
        work = self.readiness.requests.get(action.identity)
        if work is None or action.identity in self.readiness.terminals:
            raise ValueError("readiness action does not name one pending mutation")
        self.readiness.claims.add(action.identity)
        terminal = await context.call(
            "mutation.git_gate",
            {"operation": action.identity},
            lambda: self.execute_mutation(work, context),
        )
        result = _exact_payload(terminal, {"variant", "value"}, "mutation terminal")
        variant = result["variant"]
        if variant not in {item.__name__ for item in TERMINALS} or type(result["value"]) is not dict:
            raise TypeError("mutation gate returned an undeclared terminal payload")
        self.readiness.terminals[action.identity] = {
            "operation": action.identity,
            "variant": variant,
            "value": cast(dict[str, object], result["value"]),
        }
        return {
            "cut": "activity_terminal_recorded",
            "operation": action.identity,
            "variant": variant,
        }

    def execute_mutation(self, work: MutWork, context: Any) -> dict[str, object]:
        reader = AuthorityReader(self.readiness, self.provider, work.op_key)
        selected = self.runner if self.runner is not None else cast(AgentRunner, DeterministicCodingAgent(work))
        gate = V5MutationGate(
            repository="owner/repo",
            pull_request=7,
            runner=cast(AgentRunner, RecordedCodingAgent(self.provider, work, selected)),
            publisher=DeterministicGitPublisher(self.provider, work, context),
            public_clone_url="https://example.test/owner/repo.git",
            claim=reader,
        )
        return _terminal_payload(gate.git_gate(work))


def arm_readiness_fault(
    timeline: Timeline,
    name: str,
    payload: object,
    *,
    occurrence: int,
) -> object:
    if name not in FAULTS:
        raise ValueError(f"unknown readiness fault {name!r}; expected {FAULTS[0]}")
    data = _exact_payload(payload, {"operation"}, name)
    operation = data["operation"]
    if type(operation) is not str or not operation:
        raise ValueError("git_response_lost operation must be a non-empty string")
    return timeline.fault(
        "readiness",
        "git.publish.after_accept",
        occurrence=occurrence,
        payload={"operation": operation, "response_lost": True},
    )


__all__ = [
    "DEFAULT_BUDGET",
    "ReadinessChecker",
    "ReadinessModule",
    "arm_readiness_fault",
]
