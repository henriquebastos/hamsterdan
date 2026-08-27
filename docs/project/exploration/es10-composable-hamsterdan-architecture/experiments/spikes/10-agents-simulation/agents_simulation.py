"""Isolated deterministic agents simulation for ES-010 Experiment 10.

The module implements the exact structural module boundary fixed by Experiment
9. It imports Hamsterdan's current credential-free request/result values for
correspondence, but owns only experimental commands, observations, faults,
durable modeled state, and checking.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
from hashlib import sha256
from pathlib import Path
from typing import Any, TypedDict, cast

from hamsterdan.agents.pi import encode_prompt
from hamsterdan.agents.protocol import (
    AgentRequest,
    AgentResult,
    CodingRequest,
    ConversationRequest,
    ReviewRequest,
    _validate_result,
)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "09-simulation-runtime"))

from runtime import (
    ActionRef,
    Artifact,
    Budget,
    LeafExecuted,
    LeafOffered,
    ReplayResult,
    StepCompleted,
    Timeline,
    replay,
)

MODULE = "agents"
KINDS = ("review", "conversation", "coding")
REQUEST_TYPES = {
    "review": ReviewRequest,
    "conversation": ConversationRequest,
    "coding": CodingRequest,
}
SECRET_FIELDS = ("TOKEN", "PASSWORD", "PASSWD", "SECRET", "CREDENTIAL", "PRIVATE_KEY", "API_KEY")
MAX_COMMAND_BYTES = 256_000
MAX_TERMINAL_BYTES = 4_000_000


class OperationSummary(TypedDict):
    kind: str
    operation: str
    attempt: int
    execution_id: str
    state: str
    cancellation_requested: bool
    terminal_kind: str | None
    terminal_status: str | None
    run_source: str | None
    delivery_source: str | None
    runtime_terminal_available: bool
    receiver_terminal_available: bool
    runtime_starts: int
    terminal_lookups: int
    cancel_calls: int
    delivery_attempts: int
    accepted_deliveries: int


class ProofMetrics(TypedDict):
    operations: int
    journal_entries: int
    artifact_bytes: int
    final_generation: int | None
    runtime_starts: int
    terminal_lookups: int
    delivery_attempts: int
    accepted_deliveries: int
    crash_phases: list[str]
    checker_passed: bool
    replay_exact: bool
    journal_digest: str


class AgentSimulationFailure(RuntimeError):
    pass


class AgentRuntimeLost(AgentSimulationFailure):
    pass


class TerminalDeliveryResponseLost(AgentSimulationFailure):
    pass


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    violations: tuple[str, ...]
    checked_operations: int


@dataclass(frozen=True)
class DeliveredExecution:
    kind: str
    repository_url: str
    operation: str
    attempt: int
    request: AgentRequest
    result: AgentResult


@dataclass(frozen=True)
class FailureProof:
    artifact: Artifact
    replay: ReplayResult
    check: CheckResult
    final: OperationSummary
    crash_phases: tuple[str, ...]

    def metrics(self) -> ProofMetrics:
        return {
            "operations": len(self.artifact.operations),
            "journal_entries": len(self.artifact.journal),
            "artifact_bytes": len(self.artifact.encode()),
            "final_generation": self.artifact.generation,
            "runtime_starts": self.final["runtime_starts"],
            "terminal_lookups": self.final["terminal_lookups"],
            "delivery_attempts": self.final["delivery_attempts"],
            "accepted_deliveries": self.final["accepted_deliveries"],
            "crash_phases": list(self.crash_phases),
            "checker_passed": self.check.passed,
            "replay_exact": self.replay.exact,
            "journal_digest": self.artifact.journal_digest,
        }


@dataclass
class _Operation:
    kind: str
    repository_url: str
    operation: str
    attempt: int
    request: AgentRequest
    state: str = "submitted"
    cancellation_reason: str | None = None
    terminal: dict[str, Any] | None = None
    run_source: str | None = None
    delivery_source: str | None = None

    @property
    def execution_id(self) -> str:
        return execution_identity(self.operation, self.attempt)


@dataclass
class _Store:
    operations: dict[str, _Operation] = field(default_factory=dict)
    terminal_declarations: dict[str, dict[str, Any]] = field(default_factory=dict)
    runtime_terminals: dict[str, dict[str, Any]] = field(default_factory=dict)
    receiver_terminals: dict[str, dict[str, Any]] = field(default_factory=dict)
    runtime_starts: dict[str, int] = field(default_factory=dict)
    terminal_lookups: dict[str, int] = field(default_factory=dict)
    cancel_calls: dict[str, int] = field(default_factory=dict)
    delivery_attempts: dict[str, int] = field(default_factory=dict)


class AgentsSimulation:
    name = MODULE

    def __init__(self, *, max_operations: int = 16) -> None:
        if type(max_operations) is not int or max_operations < 1:
            raise ValueError("max_operations must be a positive integer")
        self.max_operations = max_operations
        self.store = _Store()

    def open(self, _context: object) -> _AgentsGeneration:
        return _AgentsGeneration(self.store, self.max_operations)

    def drop(self, _generation: _AgentsGeneration) -> None:
        pass

    def close(self, _generation: _AgentsGeneration) -> None:
        pass

    def resource_usage(self, _generation: _AgentsGeneration | None) -> dict[str, int]:
        return {
            "agents.operations": len(self.store.operations),
            "agents.pending": sum(operation.state != "delivered" for operation in self.store.operations.values()),
            "agents.runtime_terminals": len(self.store.runtime_terminals),
            "agents.receiver_terminals": len(self.store.receiver_terminals),
            "agents.terminal_declarations": len(self.store.terminal_declarations),
        }

    def delivered(self, operation: str, attempt: int) -> DeliveredExecution:
        execution_id = execution_identity(operation, attempt)
        retained = self.store.operations.get(execution_id)
        if retained is None:
            raise ValueError(f"unknown agent operation {execution_id!r}; submit it first")
        terminal = self.store.receiver_terminals.get(execution_id)
        if retained.state != "delivered" or terminal is None:
            raise ValueError(f"agent execution {execution_id!r} has not delivered a result terminal")
        if terminal.get("kind") != "result" or type(terminal.get("value")) is not dict:
            raise ValueError(f"agent execution {execution_id!r} did not deliver a result terminal")
        value = deepcopy(cast(dict[str, Any], terminal["value"]))
        changed = value.get("changed_files") if retained.kind == "coding" else None
        result = _validate_result(retained.kind, value, retained.request, changed)
        return DeliveredExecution(
            retained.kind,
            retained.repository_url,
            retained.operation,
            retained.attempt,
            deepcopy(retained.request),
            result,
        )


class _AgentsGeneration:
    def __init__(self, store: _Store, max_operations: int) -> None:
        self.store = store
        self.max_operations = max_operations

    def command(self, name: str, payload: object, _context: object) -> object:
        commands = {
            "submit": self._submit,
            "terminal": self._terminal,
            "cancel": self._cancel,
        }
        try:
            command = commands[name]
        except KeyError:
            raise ValueError(f"unknown agents command {name!r}; expected {sorted(commands)!r}") from None
        _bounded_json(payload, MAX_COMMAND_BYTES, f"agents command {name}")
        return command(payload)

    def observe(self, name: str, payload: object, _context: object) -> object:
        if name == "state":
            if payload not in (None, {}):
                raise ValueError("agents state observation accepts no parameters")
            return {"operations": self._summaries()}
        if name == "operation":
            data = _exact(payload, {"operation", "attempt"}, "agents operation observation")
            return self._summary(self._operation(data["operation"], data["attempt"]))
        raise ValueError("unknown agents observation; expected 'operation' or 'state'")

    def eligible_actions(self, _context: object) -> tuple[ActionRef, ...]:
        actions = []
        for operation in sorted(self.store.operations.values(), key=lambda item: item.execution_id):
            name = self._next_action(operation)
            if name is not None:
                actions.append(ActionRef(MODULE, name, operation.execution_id, 0))
        return tuple(actions)

    async def step(self, action: ActionRef, context: Any) -> object:
        operation = self.store.operations.get(action.identity)
        if operation is None:
            raise ValueError(f"unknown eligible agent execution {action.identity!r}")
        expected = self._next_action(operation)
        if action.name != expected:
            raise ValueError(f"agent action {action.name!r} is stale for {action.identity!r}; expected {expected!r}")
        actions = {
            "accept": self._accept_action,
            "run": self._run_action,
            "terminal.available": self._terminal_available_action,
            "cancel": self._cancel_action,
            "deliver": self._deliver_action,
        }
        return await actions[action.name](operation, context)

    def _submit(self, payload: object) -> OperationSummary:
        data = _exact(payload, {"kind", "repository_url", "operation", "attempt", "request"}, "agent submit")
        kind = _kind(data["kind"])
        repository_url = _text(data["repository_url"], "repository_url", 4096)
        operation = _text(data["operation"], "operation", 1024)
        attempt = _attempt(data["attempt"])
        _credential_free(data["request"])
        request = _request(kind, repository_url, data["request"])
        execution_id = execution_identity(operation, attempt)
        existing = self.store.operations.get(execution_id)
        if existing is not None:
            if (
                existing.kind,
                existing.repository_url,
                existing.operation,
                existing.attempt,
                existing.request,
            ) != (kind, repository_url, operation, attempt, request):
                raise ValueError("agent execution identity collides with a different submission")
            return self._summary(existing)
        if len(self.store.operations) >= self.max_operations:
            raise ValueError(f"agent operation bound {self.max_operations} would be exceeded")
        submitted = _Operation(kind, repository_url, operation, attempt, request)
        self.store.operations[execution_id] = submitted
        return self._summary(submitted)

    def _terminal(self, payload: object) -> OperationSummary:
        data = _exact(payload, {"operation", "attempt", "result"}, "agent terminal declaration")
        operation = self._operation(data["operation"], data["attempt"])
        if operation.cancellation_reason is not None:
            raise ValueError("a canceled agent operation cannot declare a result terminal")
        if operation.state in {"available", "delivered"}:
            raise ValueError("an available agent terminal cannot be replaced")
        _credential_free(data["result"])
        result = _result(operation, data["result"])
        _bounded_json(result, MAX_TERMINAL_BYTES, "agent terminal result")
        previous = self.store.terminal_declarations.get(operation.execution_id)
        if previous is not None and previous != result:
            raise ValueError("agent terminal declaration differs from its retained value")
        self.store.terminal_declarations[operation.execution_id] = result
        return self._summary(operation)

    def _cancel(self, payload: object) -> OperationSummary:
        data = _exact(payload, {"operation", "attempt", "reason"}, "agent cancellation")
        operation = self._operation(data["operation"], data["attempt"])
        reason = _text(data["reason"], "cancellation reason", 256)
        if operation.state in {"available", "delivered"}:
            raise ValueError("agent cancellation arrived after a terminal was available")
        if operation.cancellation_reason not in (None, reason):
            raise ValueError("agent cancellation reason differs from its retained value")
        operation.cancellation_reason = reason
        return self._summary(operation)

    def _operation(self, raw_operation: object, raw_attempt: object) -> _Operation:
        execution_id = execution_identity(
            _text(raw_operation, "operation", 1024),
            _attempt(raw_attempt),
        )
        try:
            return self.store.operations[execution_id]
        except KeyError:
            raise ValueError(f"unknown agent operation {execution_id!r}; submit it first") from None

    def _next_action(self, operation: _Operation) -> str | None:
        if operation.state == "submitted":
            return "accept"
        if operation.state == "accepted":
            if operation.execution_id in self.store.runtime_terminals:
                return "terminal.available"
            if operation.cancellation_reason is not None:
                return "cancel"
            if operation.execution_id in self.store.terminal_declarations:
                return "run"
            return None
        if operation.state == "available":
            return "deliver"
        if operation.state == "delivered":
            return None
        raise ValueError(f"agent operation has unknown state {operation.state!r}")

    async def _accept_action(self, operation: _Operation, _context: Any) -> object:
        operation.state = "accepted"
        return {"cut": "accepted", "execution_id": operation.execution_id}

    async def _run_action(self, operation: _Operation, context: Any) -> object:
        result = await context.call(
            "runtime.run",
            self._leaf_payload(operation),
            lambda: self._run(operation, context),
        )
        operation.terminal = result["terminal"]
        operation.run_source = result["source"]
        operation.state = "available"
        return {"cut": "terminal_available", "execution_id": operation.execution_id, "source": result["source"]}

    async def _terminal_available_action(self, operation: _Operation, context: Any) -> object:
        result = await context.call(
            "runtime.terminal.lookup",
            self._leaf_payload(operation),
            lambda: self._lookup_terminal(operation),
        )
        operation.terminal = result["terminal"]
        operation.run_source = "lookup"
        operation.state = "available"
        return {"cut": "terminal_available", "execution_id": operation.execution_id, "source": "lookup"}

    async def _cancel_action(self, operation: _Operation, context: Any) -> object:
        result = await context.call(
            "runtime.cancel",
            {**self._leaf_payload(operation), "reason": operation.cancellation_reason},
            lambda: self._cancel_runtime(operation),
        )
        operation.terminal = result["terminal"]
        operation.state = "available"
        return {"cut": "terminal_available", "execution_id": operation.execution_id, "source": "cancel"}

    async def _deliver_action(self, operation: _Operation, context: Any) -> object:
        result = await context.call(
            "terminal.deliver",
            self._leaf_payload(operation),
            lambda: self._deliver(operation, context),
        )
        operation.delivery_source = result["source"]
        operation.state = "delivered"
        return {"cut": "terminal_delivered", "execution_id": operation.execution_id, "source": result["source"]}

    def _run(self, operation: _Operation, context: Any) -> object:
        execution_id = operation.execution_id
        existing = self.store.runtime_terminals.get(execution_id)
        if existing is not None:
            return {"source": "lookup", "terminal": existing}
        terminal = self.store.terminal_declarations.get(execution_id)
        if terminal is None:
            raise ValueError("agent run has no declared deterministic terminal")
        self.store.runtime_starts[execution_id] = self.store.runtime_starts.get(execution_id, 0) + 1
        self.store.runtime_terminals[execution_id] = terminal
        if self._faulted(context, "runtime.loss.after_terminal", execution_id):
            raise AgentRuntimeLost(f"agent runtime lost after terminal {execution_id}")
        return {"source": "effect", "terminal": terminal}

    def _lookup_terminal(self, operation: _Operation) -> object:
        execution_id = operation.execution_id
        try:
            terminal = self.store.runtime_terminals[execution_id]
        except KeyError:
            raise ValueError("agent runtime terminal lookup found no retained terminal") from None
        self.store.terminal_lookups[execution_id] = self.store.terminal_lookups.get(execution_id, 0) + 1
        return {"source": "lookup", "terminal": terminal}

    def _cancel_runtime(self, operation: _Operation) -> object:
        execution_id = operation.execution_id
        existing = self.store.runtime_terminals.get(execution_id)
        if existing is not None:
            return {"source": "lookup", "terminal": existing}
        self.store.cancel_calls[execution_id] = self.store.cancel_calls.get(execution_id, 0) + 1
        terminal = {
            "kind": "failure",
            "status": "canceled",
            "category": "runtime_lifecycle",
            "canceled": True,
            "timed_out": False,
        }
        self.store.runtime_terminals[execution_id] = terminal
        return {"source": "cancel", "terminal": terminal}

    def _deliver(self, operation: _Operation, context: Any) -> object:
        if operation.terminal is None:
            raise ValueError("agent terminal delivery has no available terminal")
        execution_id = operation.execution_id
        self.store.delivery_attempts[execution_id] = self.store.delivery_attempts.get(execution_id, 0) + 1
        existing = self.store.receiver_terminals.get(execution_id)
        if existing is not None:
            if existing != operation.terminal:
                raise ValueError("agent terminal delivery collided with a different terminal")
            return {"source": "lookup"}
        self.store.receiver_terminals[execution_id] = operation.terminal
        if self._faulted(context, "terminal.delivery.response_lost", execution_id):
            raise TerminalDeliveryResponseLost(f"agent terminal delivery response lost for {execution_id}")
        return {"source": "effect"}

    @staticmethod
    def _faulted(context: Any, point: str, execution_id: str) -> bool:
        faults = context.faults(point)
        if len(faults) > 1:
            raise ValueError(f"agent fault point {point!r} matched more than one occurrence")
        for fault in faults:
            if fault.payload != {"execution_id": execution_id}:
                raise ValueError(
                    f"agent fault {point!r} must name execution_id {execution_id!r}; got {fault.payload!r}"
                )
        return bool(faults)

    @staticmethod
    def _leaf_payload(operation: _Operation) -> dict[str, object]:
        return {
            "kind": operation.kind,
            "operation": operation.operation,
            "attempt": operation.attempt,
            "execution_id": operation.execution_id,
        }

    def _summaries(self) -> list[OperationSummary]:
        operations = sorted(self.store.operations.values(), key=lambda item: (item.kind, item.operation, item.attempt))
        return [self._summary(operation) for operation in operations]

    def _summary(self, operation: _Operation) -> OperationSummary:
        terminal = operation.terminal
        return {
            "kind": operation.kind,
            "operation": operation.operation,
            "attempt": operation.attempt,
            "execution_id": operation.execution_id,
            "state": operation.state,
            "cancellation_requested": operation.cancellation_reason is not None,
            "terminal_kind": None if terminal is None else cast(str, terminal["kind"]),
            "terminal_status": None if terminal is None else cast(str, terminal["status"]),
            "run_source": operation.run_source,
            "delivery_source": operation.delivery_source,
            "runtime_terminal_available": operation.execution_id in self.store.runtime_terminals,
            "receiver_terminal_available": operation.execution_id in self.store.receiver_terminals,
            "runtime_starts": self.store.runtime_starts.get(operation.execution_id, 0),
            "terminal_lookups": self.store.terminal_lookups.get(operation.execution_id, 0),
            "cancel_calls": self.store.cancel_calls.get(operation.execution_id, 0),
            "delivery_attempts": self.store.delivery_attempts.get(operation.execution_id, 0),
            "accepted_deliveries": int(operation.execution_id in self.store.receiver_terminals),
        }


@dataclass
class _ExpectedOperation:
    kind: str
    operation: str
    attempt: int
    execution_id: str
    submission: dict[str, Any]
    state: str = "submitted"
    cancellation_requested: bool = False
    terminal_kind: str | None = None
    terminal_status: str | None = None
    run_source: str | None = None
    delivery_source: str | None = None
    runtime_terminal_available: bool = False
    receiver_terminal_available: bool = False
    runtime_starts: int = 0
    terminal_lookups: int = 0
    cancel_calls: int = 0
    delivery_attempts: int = 0
    accepted_deliveries: int = 0
    declared_status: str | None = None


class AgentsChecker:
    """Derive expected agent state from expanded operations, not module stores."""

    @classmethod
    def check(cls, artifact: Artifact) -> CheckResult:
        expected: dict[str, _ExpectedOperation] = {}
        violations: list[str] = []
        observed: dict[str, OperationSummary] | None = None
        for item in artifact.operations:
            kind = item["kind"]
            if kind == "failure":
                continue
            if kind == "command":
                cls._command(item, expected, violations)
            elif kind == "execute":
                cls._execute(item, expected, violations)
            elif kind in {"start", "finish"}:
                cls._complete(item, expected, violations)
            elif kind == "observe":
                state = cls._state_observation(item)
                if state is not None:
                    observed = state
        if observed is None:
            violations.append("artifact has no final agents state observation")
        else:
            cls._compare(expected, observed, violations)
        return CheckResult(not violations, tuple(violations), len(expected))

    @staticmethod
    def _command(
        item: dict[str, Any],
        expected: dict[str, _ExpectedOperation],
        violations: list[str],
    ) -> None:
        request = item["request"]
        if request["module"] != MODULE:
            return
        name, payload = request["name"], request["payload"]
        if name == "submit":
            identity = execution_identity(payload["operation"], payload["attempt"])
            previous = expected.get(identity)
            if previous is not None:
                if previous.submission != payload:
                    violations.append(f"submit identity collision for {identity!r}")
                return
            expected[identity] = _ExpectedOperation(
                payload["kind"],
                payload["operation"],
                payload["attempt"],
                identity,
                payload,
            )
        elif name == "terminal":
            operation = _checker_operation(expected, payload, violations)
            if operation is not None:
                operation.declared_status = payload["result"]["status"]
        elif name == "cancel":
            operation = _checker_operation(expected, payload, violations)
            if operation is not None:
                operation.cancellation_requested = True
        else:
            violations.append(f"checker encountered undeclared agents command {name!r}")

    @staticmethod
    def _execute(
        item: dict[str, Any],
        expected: dict[str, _ExpectedOperation],
        violations: list[str],
    ) -> None:
        result = item["result"]
        leaf = result["leaf"]
        if leaf["module"] != MODULE:
            return
        operation = expected.get(leaf["action"])
        if operation is None:
            violations.append(f"checker saw leaf for undeclared execution {leaf['action']!r}")
            return
        name = leaf["name"]
        if name == "runtime.run":
            operation.runtime_starts += 1
            operation.runtime_terminal_available = True
        elif name == "runtime.terminal.lookup":
            operation.terminal_lookups += 1
        elif name == "runtime.cancel":
            operation.cancel_calls += 1
            operation.runtime_terminal_available = True
        elif name == "terminal.deliver":
            operation.delivery_attempts += 1
            operation.accepted_deliveries = 1
            operation.receiver_terminal_available = True
        else:
            violations.append(f"checker encountered undeclared agents leaf {name!r}")

    @staticmethod
    def _complete(
        item: dict[str, Any],
        expected: dict[str, _ExpectedOperation],
        violations: list[str],
    ) -> None:
        result = item["result"]
        if item["kind"] == "start" and result.get("status") != "completed":
            return
        action = result["action"]
        if action["module"] != MODULE:
            return
        operation = expected.get(action["identity"])
        if operation is None:
            violations.append(f"checker saw completion for undeclared execution {action['identity']!r}")
            return
        name = action["name"]
        if name == "accept":
            operation.state = "accepted"
        elif name == "run":
            operation.state = "available"
            operation.terminal_kind = "result"
            operation.terminal_status = operation.declared_status
            operation.run_source = "effect"
        elif name == "terminal.available":
            operation.state = "available"
            operation.terminal_kind = "result"
            operation.terminal_status = operation.declared_status
            operation.run_source = "lookup"
        elif name == "cancel":
            operation.state = "available"
            operation.terminal_kind = "failure"
            operation.terminal_status = "canceled"
        elif name == "deliver":
            operation.state = "delivered"
            operation.delivery_source = "effect" if operation.delivery_attempts == 1 else "lookup"
        else:
            violations.append(f"checker encountered undeclared agents action {name!r}")

    @staticmethod
    def _state_observation(item: dict[str, Any]) -> dict[str, OperationSummary] | None:
        request, result = item["request"], item["result"]
        if request["module"] != MODULE or request["name"] != "state":
            return None
        return {operation["execution_id"]: operation for operation in result["value"]["operations"]}

    @staticmethod
    def _compare(
        expected: dict[str, _ExpectedOperation],
        observed: dict[str, OperationSummary],
        violations: list[str],
    ) -> None:
        if set(expected) != set(observed):
            violations.append(
                f"operation identities differ: expected {sorted(expected)!r}, observed {sorted(observed)!r}"
            )
            return
        names = tuple(
            field.name for field in fields(_ExpectedOperation) if field.name not in {"declared_status", "submission"}
        )
        for identity, model in expected.items():
            actual = observed[identity]
            for name in names:
                before, after = getattr(model, name), cast(dict[str, Any], actual)[name]
                if before != after:
                    violations.append(f"{name} expected {before!r}, observed {after!r}")


AGENT_BUDGET = Budget(
    operations=256,
    owner_steps=64,
    eligible_actions=16,
    leaf_calls=64,
    choice_draws=64,
    active_faults=16,
    generations=16,
    logical_time_us=1_000,
    journal_entries=2_048,
    artifact_bytes=1_000_000,
    resources={
        "agents.operations": 16,
        "agents.pending": 16,
        "agents.runtime_terminals": 16,
        "agents.receiver_terminals": 16,
        "agents.terminal_declarations": 16,
    },
)


def execution_identity(operation: str, attempt: int) -> str:
    logical_operation = _text(operation, "operation", 1024)
    exact_attempt = _attempt(attempt)
    return f"pi:{sha256(f'{logical_operation}\0{exact_attempt}'.encode()).hexdigest()}"


def production_port_submissions() -> tuple[dict[str, Any], ...]:
    head, base = "a" * 40, "b" * 40
    return (
        {
            "kind": "review",
            "repository_url": "https://example.test/owner/repo.git",
            "operation": f"review:owner/repo:pr:7:{head}",
            "attempt": 1,
            "request": {
                "repository": "owner/repo",
                "pull_request": 7,
                "epoch": 3,
                "head": head,
                "base": base,
                "diff_path": "review.diff",
                "policy": {},
                "review_lenses": ["correctness"],
                "context_paths": [],
                "actions_evidence": [],
                "prior_findings": [],
                "prior_comments": [],
                "prior_replies": [],
                "applied_changes": [],
            },
        },
        {
            "kind": "conversation",
            "repository_url": "https://example.test/owner/repo.git",
            "operation": "conversation:owner/repo:pr:7:delivery:fixture",
            "attempt": 1,
            "request": {
                "repository": "owner/repo",
                "pull_request": 7,
                "epoch": 3,
                "head": head,
                "base": base,
                "comment_context": {"id": 41, "body": "Apply the bounded change."},
                "actor": {"id": 9, "login": "navigator"},
                "dashboard": {"phase": "running", "head": head},
                "gates": [],
                "findings": [],
                "allowed_intents": [
                    {
                        "type": "change",
                        "arguments": ["request"],
                        "mutation": True,
                        "requires_explicit": True,
                    }
                ],
            },
        },
        {
            "kind": "coding",
            "repository_url": "https://example.test/owner/repo.git",
            "operation": "mutation:owner/repo:pr:7:fixture",
            "attempt": 1,
            "request": {
                "kind": "change",
                "repository": "owner/repo",
                "pull_request": 7,
                "epoch": 3,
                "head": head,
                "base": base,
                "ref": "hamsterdan/mutation/fixture",
                "selected_work": [{"kind": "change", "request": "Apply the bounded change."}],
                "failure_evidence": [],
                "fingerprint": "",
                "lineage": [],
                "reproduction_status": "unknown",
                "merge_base": False,
            },
        },
    )


def canceled_coding_submission() -> dict[str, Any]:
    return production_port_submissions()[2]


def run_failure_proof() -> FailureProof:
    module = AgentsSimulation()
    timeline = Timeline.open((module,), AGENT_BUDGET, seed=10)
    submission = production_port_submissions()[0]
    operation, attempt = submission["operation"], submission["attempt"]
    execution_id = execution_identity(operation, attempt)
    request = submission["request"]
    timeline.command(MODULE, "submit", submission)
    accepted = timeline.step()
    if not isinstance(accepted, StepCompleted) or accepted.action.name != "accept":
        raise AssertionError("failure proof did not expose the acceptance cut")
    timeline.command(
        MODULE,
        "terminal",
        {
            "operation": operation,
            "attempt": attempt,
            "result": {
                "repository": request["repository"],
                "pull_request": request["pull_request"],
                "epoch": request["epoch"],
                "head": request["head"],
                "base": request["base"],
                "status": "clear",
                "findings": [],
                "lineage": [],
            },
        },
    )
    timeline.fault(
        MODULE,
        "runtime.loss.after_terminal",
        payload={"execution_id": execution_id},
    )
    offered = timeline.start()
    if not isinstance(offered, LeafOffered) or offered.action.name != "run":
        raise AssertionError("failure proof did not expose the run cut")
    executed = timeline.execute()
    if not isinstance(executed, LeafExecuted) or executed.error is None or executed.error.kind != "AgentRuntimeLost":
        raise AssertionError("failure proof did not lose the runtime after terminal availability")
    available_at_runtime = timeline.observe(
        MODULE,
        "operation",
        {"operation": operation, "attempt": attempt},
    ).value
    if available_at_runtime["state"] != "accepted" or not available_at_runtime["runtime_terminal_available"]:
        raise AssertionError("runtime terminal was not durable before owner return")
    timeline.crash("runtime_lost_after_terminal")
    timeline = timeline.restart()
    recovered = timeline.step()
    if not isinstance(recovered, StepCompleted) or recovered.action.name != "terminal.available":
        raise AssertionError("failure proof did not recover the terminal lookup-first")

    timeline.fault(
        MODULE,
        "terminal.delivery.response_lost",
        payload={"execution_id": execution_id},
    )
    offered = timeline.start()
    if not isinstance(offered, LeafOffered) or offered.action.name != "deliver":
        raise AssertionError("failure proof did not expose terminal delivery")
    executed = timeline.execute()
    if (
        not isinstance(executed, LeafExecuted)
        or executed.error is None
        or executed.error.kind != "TerminalDeliveryResponseLost"
    ):
        raise AssertionError("failure proof did not lose the terminal delivery response")
    accepted_at_receiver = timeline.observe(
        MODULE,
        "operation",
        {"operation": operation, "attempt": attempt},
    ).value
    if accepted_at_receiver["state"] != "available" or not accepted_at_receiver["receiver_terminal_available"]:
        raise AssertionError("receiver terminal was not durable before owner return")
    timeline.crash("terminal_delivery_response_lost")
    timeline = timeline.restart()
    delivered = timeline.step()
    if not isinstance(delivered, StepCompleted) or delivered.action.name != "deliver":
        raise AssertionError("failure proof did not redeliver lookup-first")
    final = cast(
        OperationSummary,
        timeline.observe(MODULE, "operation", {"operation": operation, "attempt": attempt}).value,
    )
    timeline.observe(MODULE, "state")
    artifact = timeline.artifact("agents-runtime-loss")
    check = AgentsChecker.check(artifact)
    replay_report = replay(artifact, lambda: (AgentsSimulation(),))
    crashes = tuple(item["result"]["phase"] for item in artifact.operations if item["kind"] == "crash")
    return FailureProof(artifact, replay_report, check, final, crashes)


def _kind(value: object) -> str:
    if value not in KINDS:
        raise ValueError(f"agent kind must be one of {list(KINDS)!r}")
    return cast(str, value)


def _text(value: object, name: str, limit: int) -> str:
    if (
        type(value) is not str
        or not value
        or len(cast(str, value).encode()) > limit
        or not cast(str, value).isascii()
        or not cast(str, value).isprintable()
    ):
        raise ValueError(f"agent {name} must be non-empty printable ASCII within {limit} bytes")
    return cast(str, value)


def _attempt(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("agent attempt must be a positive integer")
    return value


def _exact(value: object, keys: set[str], subject: str) -> dict[str, Any]:
    if type(value) is not dict or set(cast(dict[object, object], value)) != keys:
        raise ValueError(f"{subject} must contain exactly {sorted(keys)!r}")
    return cast(dict[str, Any], value)


def _request(kind: str, repository_url: str, value: object) -> AgentRequest:
    request_type = REQUEST_TYPES[kind]
    keys = {field.name for field in fields(request_type)}
    data = _exact(value, keys, f"{kind} request")
    request = cast(Any, request_type)(**data)
    encode_prompt(kind, repository_url, request)
    return request


def _result(operation: _Operation, value: object) -> dict[str, Any]:
    changed = None
    if operation.kind == "coding" and type(value) is dict:
        changed = cast(dict[str, Any], value).get("changed_files")
    validated: AgentResult = _validate_result(operation.kind, value, operation.request, changed)
    return {
        "kind": "result",
        "status": cast(Any, validated).status,
        "value": asdict(validated),
    }


def _bounded_json(value: object, limit: int, subject: str) -> None:
    try:
        size = len(json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode())
    except TypeError, ValueError:
        raise ValueError(f"{subject} must be strict finite JSON") from None
    if size > limit:
        raise ValueError(f"{subject} exceeds its {limit}-byte bound")


def _credential_free(value: object, path: str = "request") -> None:
    if type(value) is dict:
        for key, child in cast(dict[object, object], value).items():
            if type(key) is not str:
                raise ValueError(f"agent {path} contains a non-string field")
            normalized = key.upper()
            if any(secret in normalized for secret in SECRET_FIELDS):
                raise ValueError(f"agent {path} contains credential-shaped field {key!r}")
            _credential_free(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(cast(list[object], value)):
            _credential_free(child, f"{path}[{index}]")


def _checker_operation(
    expected: dict[str, _ExpectedOperation],
    payload: dict[str, Any],
    violations: list[str],
) -> _ExpectedOperation | None:
    identity = execution_identity(payload["operation"], payload["attempt"])
    operation = expected.get(identity)
    if operation is None:
        violations.append(f"checker saw command for undeclared execution {identity!r}")
    return operation


if __name__ == "__main__":
    print(json.dumps(run_failure_proof().metrics(), indent=2, sort_keys=True))
