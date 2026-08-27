"""Owned deterministic runtime candidate for ES-010 experiment 9.

Provenance: the strict JSON digest, SHA-256 counter choices, ordered action
selection, occurrence faults, generation revocation, resource gauges, journal,
and expanded replay mechanisms were adapted from ``petrus.testing.dst`` at
Petrus commit 44cac5ff48ac371ebae56323941983f30db13c0d. This copy is
Hamsterdan-owned: it has no synchronization or artifact compatibility contract
with Petrus.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
from collections.abc import Callable, Coroutine, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, cast

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_MAX_INTEGER = 2**53 - 1
_MAX_ARTIFACT_BYTES = 4_194_304
_MISSING = object()


class SimulationError(RuntimeError):
    pass


class StaleGeneration(SimulationError):
    pass


class BudgetExceeded(SimulationError):
    def __init__(self, bound: str, limit: int) -> None:
        self.bound = bound
        self.limit = limit
        super().__init__(f"simulation budget {bound!r} exceeded at limit {limit}")


class ReplayMismatch(AssertionError):
    pass


class OneLeafViolation(SimulationError):
    pass


def _bounded_integer(value: object, name: str, *, zero: bool = False, ceiling: int = _MAX_INTEGER) -> int:
    minimum = 0 if zero else 1
    if type(value) is not int or not minimum <= value <= ceiling:
        raise ValueError(f"{name} must be an integer from {minimum} through {ceiling}")
    return value


def _name(value: object, subject: str) -> str:
    if type(value) is not str or not _NAME.fullmatch(value):
        raise ValueError(f"{subject} must be a normalized non-empty name")
    return value


def _strict_json(value: object, subject: str = "value") -> Any:
    def visit(item: object, path: str) -> Any:
        if item is None or type(item) in (bool, int, str):
            return item
        if type(item) is float:
            if not math.isfinite(cast(float, item)):
                raise ValueError(f"{subject} has a non-finite number at {path}")
            return item
        if type(item) is list:
            return [visit(child, f"{path}[{index}]") for index, child in enumerate(cast(list[object], item))]
        if type(item) is dict:
            result = {}
            for key, child in cast(dict[object, object], item).items():
                if type(key) is not str:
                    raise TypeError(f"{subject} has a non-string key at {path}")
                result[key] = visit(child, f"{path}.{key}")
            return result
        raise TypeError(f"{subject} must be strict JSON; found {type(item).__name__} at {path}")

    return visit(value, "$")


def digest_json(value: object) -> str:
    payload = json.dumps(
        _strict_json(value),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Budget:
    operations: int
    owner_steps: int
    eligible_actions: int
    leaf_calls: int
    choice_draws: int
    active_faults: int
    generations: int
    logical_time_us: int
    journal_entries: int
    artifact_bytes: int
    resources: dict[str, int]

    def __post_init__(self) -> None:
        for field in (
            "operations",
            "owner_steps",
            "eligible_actions",
            "leaf_calls",
            "choice_draws",
            "active_faults",
            "generations",
            "journal_entries",
        ):
            _bounded_integer(getattr(self, field), field, ceiling=100_000)
        if self.journal_entries < 2:
            raise ValueError("journal_entries must admit the initial generation and resource entries")
        _bounded_integer(self.logical_time_us, "logical_time_us", zero=True)
        _bounded_integer(self.artifact_bytes, "artifact_bytes", ceiling=_MAX_ARTIFACT_BYTES)
        resources = {}
        for name, limit in self.resources.items():
            resources[_name(name, "resource name")] = _bounded_integer(limit, f"resource {name}", zero=True)
        object.__setattr__(self, "resources", dict(sorted(resources.items())))

    def dump(self) -> dict[str, Any]:
        return {
            "operations": self.operations,
            "owner_steps": self.owner_steps,
            "eligible_actions": self.eligible_actions,
            "leaf_calls": self.leaf_calls,
            "choice_draws": self.choice_draws,
            "active_faults": self.active_faults,
            "generations": self.generations,
            "logical_time_us": self.logical_time_us,
            "journal_entries": self.journal_entries,
            "artifact_bytes": self.artifact_bytes,
            "resources": dict(self.resources),
        }

    @classmethod
    def load(cls, value: object) -> Budget:
        data = _exact_object(
            value,
            {
                "operations",
                "owner_steps",
                "eligible_actions",
                "leaf_calls",
                "choice_draws",
                "active_faults",
                "generations",
                "logical_time_us",
                "journal_entries",
                "artifact_bytes",
                "resources",
            },
            "budget",
        )
        resources = data["resources"]
        if type(resources) is not dict:
            raise TypeError("budget resources must be an object")
        return cls(**cast(dict[str, Any], data))


@dataclass(frozen=True)
class ActionRef:
    module: str
    name: str
    identity: str
    eligible_at_us: int

    def __post_init__(self) -> None:
        _name(self.module, "action module")
        _name(self.name, "action name")
        _name(self.identity, "action identity")
        _bounded_integer(self.eligible_at_us, "eligible_at_us", zero=True)

    def dump(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "name": self.name,
            "identity": self.identity,
            "eligible_at_us": self.eligible_at_us,
        }


@dataclass(frozen=True)
class Fault:
    module: str
    point: str
    occurrence: int
    payload: Any
    sequence: int

    def dump(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "point": self.point,
            "occurrence": self.occurrence,
            "payload": _strict_json(self.payload, "fault payload"),
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class ErrorRef:
    kind: str
    message: str

    def dump(self) -> dict[str, str]:
        return {"kind": self.kind, "message": self.message}


@dataclass(frozen=True)
class LeafRef:
    module: str
    action: str
    name: str
    payload: Any

    def dump(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "action": self.action,
            "name": self.name,
            "payload": _strict_json(self.payload, "leaf payload"),
        }


@dataclass(frozen=True)
class LeafOffered:
    action: ActionRef
    leaf: LeafRef


@dataclass(frozen=True)
class LeafExecuted:
    action: ActionRef
    leaf: LeafRef
    value: Any | None
    error: ErrorRef | None


@dataclass(frozen=True)
class StepCompleted:
    action: ActionRef
    value: Any


@dataclass(frozen=True)
class Waiting:
    next_at_us: int | None


@dataclass(frozen=True)
class Observation:
    module: str
    name: str
    value: Any
    instant_us: int
    generation: int
    sequence: int


@dataclass(frozen=True)
class RunResult:
    results: tuple[StepCompleted | Waiting, ...]
    budget_exhausted: bool


@dataclass(frozen=True)
class ReplayResult:
    exact: bool
    operations: int
    journal_entries: int
    journal_digest: str


@dataclass(frozen=True)
class Artifact:
    format: str
    version: int
    scenario_id: str
    modules: tuple[str, ...]
    budget: Budget
    operations: tuple[dict[str, Any], ...]
    journal: tuple[dict[str, Any], ...]
    journal_digest: str
    instant_us: int
    generation: int | None
    origin: dict[str, Any]

    def __post_init__(self) -> None:
        if self.format != "hamsterdan-simulation" or self.version != 1:
            raise ValueError("only hamsterdan-simulation artifact version 1 is supported")
        _name(self.scenario_id, "scenario id")
        if not self.modules or any(not _NAME.fullmatch(module) for module in self.modules):
            raise ValueError("artifact modules must be normalized names")
        if len(self.modules) != len(set(self.modules)):
            raise ValueError("artifact modules must be unique")
        if [item.get("position") for item in self.operations] != list(range(len(self.operations))):
            raise ValueError("artifact operation positions must be dense and zero-based")
        if [item.get("position") for item in self.journal] != list(range(len(self.journal))):
            raise ValueError("artifact journal positions must be dense and zero-based")
        if self.journal_digest != digest_json(list(self.journal)):
            raise ValueError("artifact journal digest does not match its journal")
        if self.operations and self.operations[-1].get("kind") == "failure":
            if any(item.get("kind") == "failure" for item in self.operations[:-1]):
                raise ValueError("artifact failure must be the final operation")
        elif any(item.get("kind") == "failure" for item in self.operations):
            raise ValueError("artifact failure must be the final operation")
        _bounded_integer(self.instant_us, "artifact instant", zero=True)
        if self.generation is not None:
            _bounded_integer(self.generation, "artifact generation")
        _strict_json(self.dump(), "artifact")

    def dump(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "version": self.version,
            "scenario_id": self.scenario_id,
            "modules": list(self.modules),
            "budget": self.budget.dump(),
            "operations": list(self.operations),
            "journal": list(self.journal),
            "journal_digest": self.journal_digest,
            "instant_us": self.instant_us,
            "generation": self.generation,
            "origin": self.origin,
        }

    def encode(self) -> bytes:
        payload = json.dumps(
            self.dump(),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        if len(payload) > self.budget.artifact_bytes:
            raise BudgetExceeded("artifact_bytes", self.budget.artifact_bytes)
        return payload

    @classmethod
    def decode(cls, payload: bytes) -> Artifact:
        if len(payload) > _MAX_ARTIFACT_BYTES:
            raise ValueError(f"artifact exceeds the format ceiling of {_MAX_ARTIFACT_BYTES} bytes")
        try:
            value = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_refuse_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"invalid simulation artifact: {error}") from None
        data = _exact_object(
            value,
            {
                "format",
                "version",
                "scenario_id",
                "modules",
                "budget",
                "operations",
                "journal",
                "journal_digest",
                "instant_us",
                "generation",
                "origin",
            },
            "artifact",
        )
        modules, operations, journal, origin = (
            data["modules"],
            data["operations"],
            data["journal"],
            data["origin"],
        )
        if type(modules) is not list or type(operations) is not list or type(journal) is not list:
            raise TypeError("artifact modules, operations, and journal must be lists")
        if type(origin) is not dict:
            raise TypeError("artifact origin must be an object")
        artifact = cls(
            format=cast(str, data["format"]),
            version=cast(int, data["version"]),
            scenario_id=cast(str, data["scenario_id"]),
            modules=tuple(cast(list[str], modules)),
            budget=Budget.load(data["budget"]),
            operations=tuple(cast(list[dict[str, Any]], operations)),
            journal=tuple(cast(list[dict[str, Any]], journal)),
            journal_digest=cast(str, data["journal_digest"]),
            instant_us=cast(int, data["instant_us"]),
            generation=cast(int | None, data["generation"]),
            origin=cast(dict[str, Any], origin),
        )
        artifact.encode()
        return artifact


@dataclass
class _ActiveFault:
    fault: Fault
    seen: int = 0


class _Faults:
    def __init__(self, owner: _Runtime) -> None:
        self._owner = owner
        self._active: list[_ActiveFault] = []
        self._sequence = 0

    def arm(self, module: str, point: str, occurrence: int, payload: object) -> Fault:
        if len(self._active) >= self._owner.budget.active_faults:
            raise BudgetExceeded("active_faults", self._owner.budget.active_faults)
        self._sequence += 1
        fault = Fault(
            module=module,
            point=point,
            occurrence=occurrence,
            payload=_strict_json(payload, "fault payload"),
            sequence=self._sequence,
        )
        self._active.append(_ActiveFault(fault))
        return fault

    def match(self, module: str, point: str) -> tuple[Fault, ...]:
        matched = []
        retained = []
        for active in self._active:
            if active.fault.module == module and active.fault.point == point:
                active.seen += 1
                if active.seen == active.fault.occurrence:
                    matched.append(active.fault)
                    self._owner._record("fault_match", point, active.fault.dump())
                    continue
            retained.append(active)
        self._active = retained
        return tuple(matched)


class _Choices:
    algorithm = "sha256-counter-v1"

    def __init__(self, owner: _Runtime, seed: int) -> None:
        self._owner = owner
        self.seed = _bounded_integer(seed, "choice seed", zero=True)
        self.draws: dict[str, int] = {}
        self._trace: list[dict[str, Any]] | None = None
        self._expected: tuple[dict[str, Any], ...] = ()
        self._expected_position = 0
        self._replaying = False

    def begin(self, expected: object) -> None:
        if self._trace is not None:
            raise SimulationError("choice capture is already active")
        if expected is not None and type(expected) is not list:
            raise TypeError("expected operation choices must be a list")
        self._trace = []
        self._expected = () if expected is None else tuple(cast(list[dict[str, Any]], expected))
        self._expected_position = 0
        self._replaying = expected is not None

    def choose(self, stream: str, options: Sequence[str]) -> str:
        if self._trace is None:
            raise SimulationError("deterministic choices are only available inside one Timeline operation")
        _name(stream, "choice stream")
        values = tuple(options)
        if not values or len(values) != len(set(values)) or any(type(item) is not str for item in values):
            raise ValueError("choice options must be a non-empty sequence of unique strings")
        total = sum(self.draws.values())
        if total >= self._owner.budget.choice_draws:
            raise BudgetExceeded("choice_draws", self._owner.budget.choice_draws)
        ordinal = self.draws.get(stream, 0)
        expected = None
        if self._expected_position < len(self._expected):
            expected = self._expected[self._expected_position]
        if expected is None and not self._replaying:
            selected = values[self._index(stream, ordinal, len(values))]
        elif expected is None:
            raise ReplayMismatch("operation consumed more deterministic choices than its artifact")
        else:
            selected = cast(str, expected.get("selected"))
            candidate = {
                "stream": stream,
                "ordinal": ordinal,
                "options": list(values),
                "selected": selected,
            }
            if candidate != expected or selected not in values:
                raise ReplayMismatch(f"choice diverged: expected {expected!r}, available {candidate!r}")
        self.draws[stream] = ordinal + 1
        record = {"stream": stream, "ordinal": ordinal, "options": list(values), "selected": selected}
        self._trace.append(record)
        self._expected_position += 1
        self._owner._record("choice", stream, record)
        return selected

    def finish(self) -> list[dict[str, Any]]:
        if self._trace is None:
            raise SimulationError("choice capture is not active")
        if self._replaying and self._expected_position != len(self._expected):
            raise ReplayMismatch("operation consumed fewer deterministic choices than its artifact")
        trace = self._trace
        self._trace = None
        self._expected = ()
        self._expected_position = 0
        self._replaying = False
        return trace

    def abort(self) -> list[dict[str, Any]]:
        if self._trace is None:
            return []
        trace = self._trace
        self._trace = None
        self._expected = ()
        self._expected_position = 0
        self._replaying = False
        return trace

    def _index(self, stream: str, ordinal: int, stop: int) -> int:
        space = 1 << 256
        ceiling = space - (space % stop)
        for probe in range(16):
            payload = json.dumps(
                [self.algorithm, self.seed, stream, ordinal, probe],
                separators=(",", ":"),
            ).encode()
            value = int.from_bytes(hashlib.sha256(payload).digest())
            if value < ceiling:
                return value % stop
        raise RuntimeError("choice rejection sampling exceeded 16 deterministic probes")


@dataclass(frozen=True)
class _LeafCall:
    ref: LeafRef
    operation: Callable[[], object]


class _LeafAwaitable:
    def __init__(self, call: _LeafCall) -> None:
        self._call = call

    def __await__(self) -> Any:
        result = yield self._call
        return result


class _ModuleContext:
    def __init__(self, owner: _Runtime, module: str) -> None:
        self._owner = owner
        self.module = module

    @property
    def now_us(self) -> int:
        return self._owner.instant_us

    @property
    def generation(self) -> int:
        if self._owner.generation is None:
            raise StaleGeneration("no live generation")
        return self._owner.generation

    def choose(self, stream: str, options: Sequence[str]) -> str:
        return self._owner._choices.choose(f"{self.module}:{_name(stream, 'choice stream')}", options)

    def faults(self, point: str) -> tuple[Fault, ...]:
        return self._owner._faults.match(self.module, _name(point, "fault point"))


class _StepContext(_ModuleContext):
    def __init__(self, owner: _Runtime, action: ActionRef) -> None:
        super().__init__(owner, action.module)
        self._action = action

    def call(self, name: str, payload: object, operation: Callable[[], object]) -> _LeafAwaitable:
        if not callable(operation):
            raise TypeError("leaf operation must be callable")
        ref = LeafRef(
            module=self.module,
            action=self._action.identity,
            name=_name(name, "leaf name"),
            payload=_strict_json(payload, "leaf payload"),
        )
        return _LeafAwaitable(_LeafCall(ref, operation))


class CoroutineStepper:
    """Process-local execution of one owner coroutine and at most one leaf."""

    def __init__(self, action: ActionRef, coroutine: Coroutine[Any, Any, object]) -> None:
        self.action = action
        self._coroutine = coroutine
        self._call: _LeafCall | None = None
        self._value: object = _MISSING
        self._error: Exception | None = None
        self.phase = "new"

    def start(self) -> LeafRef | object:
        if self.phase != "new":
            raise SimulationError("coroutine step has already started")
        try:
            yielded = self._coroutine.send(None)
        except StopIteration as completed:
            self.phase = "completed"
            return completed.value
        if not isinstance(yielded, _LeafCall):
            self._coroutine.close()
            self.phase = "closed"
            raise TypeError("owner coroutine must yield a leaf created by context.call")
        self._call = yielded
        self.phase = "offered"
        return yielded.ref

    def execute(self) -> tuple[object | None, ErrorRef | None]:
        if self.phase != "offered" or self._call is None:
            raise SimulationError("execute requires one offered leaf")
        try:
            value = self._call.operation()
            if inspect.isawaitable(value):
                raise TypeError("synchronous Timeline cannot execute an awaitable leaf")
            self._value = _strict_json(value, "leaf result")
        except Exception as error:  # noqa: BLE001 - the owner receives its exact process-local exception
            self._error = error
        self.phase = "executed"
        if self._error is not None:
            return None, ErrorRef(type(self._error).__qualname__, str(self._error))
        return self._value, None

    def finish(self) -> object:
        if self.phase != "executed":
            raise SimulationError("finish requires one executed leaf")
        try:
            if self._error is None:
                yielded = self._coroutine.send(self._value)
            else:
                yielded = self._coroutine.throw(self._error)
        except StopIteration as completed:
            self.phase = "completed"
            return completed.value
        except BaseException:
            self.phase = "closed"
            raise
        self._coroutine.close()
        self.phase = "closed"
        if isinstance(yielded, _LeafCall):
            raise OneLeafViolation("one owner step yielded more than one leaf callable")
        raise TypeError("owner coroutine yielded an unsupported value after its leaf")

    def close(self) -> None:
        if self.phase not in {"completed", "closed"}:
            self._coroutine.close()
        self.phase = "closed"
        self._call = None
        self._value = _MISSING
        self._error = None

    @property
    def leaf(self) -> LeafRef | None:
        return None if self._call is None else self._call.ref


class _Runtime:
    def __init__(
        self,
        modules: Iterable[object],
        budget: Budget,
        seed: int,
        expected: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.budget = budget
        self.instant_us = 0
        self.generation: int | None = None
        self._last_generation = 0
        self._module_order: list[str] = []
        self._modules: dict[str, object] = {}
        for module in modules:
            name = _name(getattr(module, "name", None), "module name")
            if name in self._modules:
                raise ValueError(f"module name is already mounted: {name}")
            self._module_order.append(name)
            self._modules[name] = module
        if not self._modules:
            raise ValueError("Timeline requires at least one module")
        self._generations: dict[str, object] = {}
        self._operations: list[dict[str, Any]] = []
        self._journal: list[dict[str, Any]] = []
        self._accepted_operations = 0
        self._owner_steps = 0
        self._leaf_calls = 0
        self._stepper: CoroutineStepper | None = None
        self._failure: dict[str, Any] | None = None
        self._faults = _Faults(self)
        self._choices = _Choices(self, seed)
        self._expected = expected
        self._expected_position = 0
        self._open_generation("created")

    def timeline(self) -> Timeline:
        if self.generation is None:
            raise StaleGeneration("restart before requesting a Timeline")
        return Timeline(self, self.generation)

    def command(self, generation: int, module: str, name: str, payload: object) -> object:
        request = {
            "module": _name(module, "command module"),
            "name": _name(name, "command name"),
            "payload": _strict_json(payload, "command payload"),
        }

        def apply() -> tuple[object, Any]:
            self._require_idle(generation)
            target = self._module_generation(module)
            value = target.command(name, request["payload"], _ModuleContext(self, module))
            detached = _strict_json(value, "command result")
            return detached, detached

        return self._boundary("command", request, apply)

    def observe(self, generation: int, module: str, name: str, payload: object) -> Observation:
        request = {
            "module": _name(module, "observation module"),
            "name": _name(name, "observation name"),
            "payload": _strict_json(payload, "observation payload"),
        }

        def read() -> tuple[Observation, Any]:
            self._require_current(generation)
            target = self._module_generation(module)
            value = _strict_json(
                target.observe(name, request["payload"], _ModuleContext(self, module)),
                "observation result",
            )
            observation = Observation(
                module=module,
                name=name,
                value=value,
                instant_us=self.instant_us,
                generation=generation,
                sequence=len(self._operations),
            )
            return observation, _observation_data(observation)

        return cast(Observation, self._boundary("observe", request, read))

    def advance(self, generation: int, to_us: int) -> int:
        request = {"to_us": _bounded_integer(to_us, "logical instant", zero=True)}

        def move() -> tuple[int, Any]:
            self._require_idle(generation)
            if to_us < self.instant_us:
                raise ValueError("logical clock cannot move backward")
            if to_us > self.budget.logical_time_us:
                raise BudgetExceeded("logical_time_us", self.budget.logical_time_us)
            previous = self.instant_us
            self.instant_us = to_us
            return to_us, {"from_us": previous, "to_us": to_us}

        return cast(int, self._boundary("advance", request, move))

    def arm_fault(
        self,
        generation: int,
        module: str,
        point: str,
        occurrence: int,
        payload: object,
    ) -> Fault:
        request = {
            "module": _name(module, "fault module"),
            "point": _name(point, "fault point"),
            "occurrence": _bounded_integer(occurrence, "fault occurrence"),
            "payload": _strict_json(payload, "fault payload"),
        }

        def arm() -> tuple[Fault, Any]:
            self._require_idle(generation)
            self._module_generation(module)
            fault = self._faults.arm(module, point, occurrence, request["payload"])
            return fault, fault.dump()

        return cast(Fault, self._boundary("fault", request, arm))

    def start(self, generation: int) -> LeafOffered | StepCompleted | Waiting:
        def begin() -> tuple[LeafOffered | StepCompleted | Waiting, Any]:
            self._require_idle(generation)
            actions = self._eligible_actions()
            eligible = [action for action in actions if action.eligible_at_us <= self.instant_us]
            if not eligible:
                future = [action.eligible_at_us for action in actions if action.eligible_at_us > self.instant_us]
                waiting = Waiting(min(future) if future else None)
                return waiting, {"status": "waiting", "next_at_us": waiting.next_at_us}
            if self._owner_steps >= self.budget.owner_steps:
                raise BudgetExceeded("owner_steps", self.budget.owner_steps)
            earliest = min(action.eligible_at_us for action in eligible)
            candidates = [action for action in eligible if action.eligible_at_us == earliest]
            candidates.sort(key=lambda action: (action.module, action.name, action.identity))
            if len(candidates) == 1:
                action = candidates[0]
            else:
                keys = [f"{item.module}:{item.name}:{item.identity}" for item in candidates]
                selected = self._choices.choose("runtime:event_order", keys)
                action = candidates[keys.index(selected)]
            target = self._module_generation(action.module)
            coroutine = target.step(action, _StepContext(self, action))
            if not inspect.iscoroutine(coroutine):
                raise TypeError("module step must return a coroutine")
            stepper = CoroutineStepper(action, coroutine)
            self._stepper = stepper
            try:
                result = stepper.start()
            except BaseException:
                stepper.close()
                self._stepper = None
                raise
            if isinstance(result, LeafRef):
                offered = LeafOffered(action, result)
                return offered, {"status": "offered", "action": action.dump(), "leaf": result.dump()}
            self._stepper = None
            completed = self._complete(action, result)
            return completed, {"status": "completed", "action": action.dump()}

        return cast(LeafOffered | StepCompleted | Waiting, self._boundary("start", {}, begin))

    def execute(self, generation: int) -> LeafExecuted:
        def call() -> tuple[LeafExecuted, Any]:
            self._require_current(generation)
            stepper = self._require_phase("offered")
            if self._leaf_calls >= self.budget.leaf_calls:
                raise BudgetExceeded("leaf_calls", self.budget.leaf_calls)
            self._leaf_calls += 1
            value, error = stepper.execute()
            leaf = stepper.leaf
            if leaf is None:
                raise AssertionError("executed step has no leaf reference")
            executed = LeafExecuted(stepper.action, leaf, value, error)
            return executed, {
                "action": stepper.action.dump(),
                "leaf": leaf.dump(),
                "outcome": "returned" if error is None else "raised",
            }

        return cast(LeafExecuted, self._boundary("execute", {}, call))

    def finish(self, generation: int) -> StepCompleted:
        def return_to_owner() -> tuple[StepCompleted, Any]:
            self._require_current(generation)
            stepper = self._require_phase("executed")
            try:
                value = stepper.finish()
            finally:
                if stepper.phase in {"completed", "closed"}:
                    self._stepper = None
            completed = self._complete(stepper.action, value)
            return completed, {"action": stepper.action.dump(), "outcome": "completed"}

        return cast(StepCompleted, self._boundary("finish", {}, return_to_owner))

    def crash(self, generation: int, cut: str) -> None:
        request = {"cut": _name(cut, "crash cut")}

        def drop() -> tuple[None, Any]:
            self._require_current(generation)
            phase = "idle" if self._stepper is None else self._stepper.phase
            action = None if self._stepper is None else self._stepper.action.dump()
            leaf = None if self._stepper is None or self._stepper.leaf is None else self._stepper.leaf.dump()
            if self._stepper is not None:
                self._stepper.close()
                self._stepper = None
            generations = self._generations
            self._generations = {}
            self.generation = None
            for module, target in generations.items():
                self._modules[module].drop(target)
            return None, {"phase": phase, "action": action, "leaf": leaf, "generation": generation}

        self._boundary("crash", request, drop)

    def restart(self, stale_generation: int) -> Timeline:
        def load() -> tuple[int, Any]:
            if self.generation is not None or stale_generation != self._last_generation:
                raise StaleGeneration("restart requires the most recently crashed generation")
            self._open_generation("loaded")
            if self.generation is None:
                raise AssertionError("restart did not install a generation")
            return self.generation, {"generation": self.generation}

        generation = cast(int, self._boundary("restart", {}, load))
        return Timeline(self, generation)

    def artifact(self, scenario_id: str) -> Artifact:
        if self._stepper is not None:
            raise SimulationError("finish or crash the pending owner step before creating an artifact")
        artifact = Artifact(
            format="hamsterdan-simulation",
            version=1,
            scenario_id=_name(scenario_id, "scenario id"),
            modules=tuple(self._module_order),
            budget=self.budget,
            operations=tuple(self._operations),
            journal=tuple(self._journal),
            journal_digest=digest_json(self._journal),
            instant_us=self.instant_us,
            generation=self.generation,
            origin={
                "algorithm": self._choices.algorithm,
                "seed": self._choices.seed,
                "draws": dict(sorted(self._choices.draws.items())),
            },
        )
        artifact.encode()
        return artifact

    def close(self) -> None:
        if self._stepper is not None:
            self._stepper.close()
            self._stepper = None
        generations = self._generations
        self._generations = {}
        self.generation = None
        for module, target in generations.items():
            self._modules[module].close(target)

    def assert_replayed(self, artifact: Artifact) -> ReplayResult:
        if self._expected_position != len(self._expected):
            raise ReplayMismatch("replay consumed fewer operations than the artifact")
        if tuple(self._operations) != artifact.operations:
            raise ReplayMismatch("replay operations diverged")
        if tuple(self._journal) != artifact.journal:
            raise ReplayMismatch("replay journal diverged")
        if self.instant_us != artifact.instant_us or self.generation != artifact.generation:
            raise ReplayMismatch("replay final clock or generation diverged")
        digest = digest_json(self._journal)
        if digest != artifact.journal_digest:
            raise ReplayMismatch("replay journal digest diverged")
        return ReplayResult(True, len(self._operations), len(self._journal), digest)

    def _boundary(
        self,
        kind: str,
        request: dict[str, Any],
        operation: Callable[[], tuple[object, Any]],
    ) -> object:
        if self._failure is not None:
            raise SimulationError("simulation already ended with a budget failure")
        expected = self._expected_operation(kind, request)
        expected_choices = None if expected is None else expected.get("choices", [])
        self._choices.begin(expected_choices)
        accepted = False
        result: object = None
        result_data: Any = None
        try:
            if self._accepted_operations >= self.budget.operations:
                raise BudgetExceeded("operations", self.budget.operations)
            self._accepted_operations += 1
            result, result_data = operation()
            accepted = True
            usage = self._resource_usage()
            exceeded = sorted(name for name, value in usage.items() if value > self.budget.resources[name])
            if exceeded:
                name = exceeded[0]
                raise BudgetExceeded(f"resource:{name}", self.budget.resources[name])
            if len(self._journal) + 2 > self.budget.journal_entries:
                raise BudgetExceeded("journal_entries", self.budget.journal_entries)
            choices = self._choices.finish()
        except BudgetExceeded as error:
            choices = self._choices.abort()
            failure = {
                "kind": "failure",
                "position": len(self._operations),
                "attempt": {"kind": kind, "request": request},
                "accepted": accepted,
                "result": result_data if accepted else None,
                "choices": choices,
                "error": {"bound": error.bound, "limit": error.limit, "message": str(error)},
            }
            self._append_operation(failure, expected)
            self._failure = failure
            if self._stepper is not None:
                self._stepper.close()
                self._stepper = None
            try:
                self._record("failure", error.bound, failure)
            except BudgetExceeded:
                pass
            raise
        except BaseException:
            self._choices.abort()
            raise
        completed = {
            "kind": kind,
            "position": len(self._operations),
            "request": request,
            "result": _strict_json(result_data, f"{kind} operation result"),
            "choices": choices,
        }
        self._append_operation(completed, expected)
        self._record("operation", kind, completed)
        self._record("resources", kind, {"usage": usage})
        return result

    def _expected_operation(self, kind: str, request: dict[str, Any]) -> dict[str, Any] | None:
        if not self._expected:
            return None
        if self._expected_position >= len(self._expected):
            raise ReplayMismatch(f"replay produced additional {kind!r} operation")
        expected = self._expected[self._expected_position]
        attempt = expected.get("attempt") if expected.get("kind") == "failure" else expected
        if type(attempt) is not dict or attempt.get("kind") != kind or attempt.get("request") != request:
            raise ReplayMismatch(f"replay attempt diverged: expected {expected!r}, observed {kind!r} {request!r}")
        return expected

    def _append_operation(self, operation: dict[str, Any], expected: dict[str, Any] | None) -> None:
        detached = cast(dict[str, Any], _strict_json(operation, "expanded operation"))
        if expected is not None and detached != expected:
            raise ReplayMismatch(f"expanded operation diverged: expected {expected!r}, observed {detached!r}")
        self._operations.append(detached)
        if self._expected:
            self._expected_position += 1

    def _record(self, kind: str, name: str, value: object) -> None:
        if len(self._journal) >= self.budget.journal_entries:
            raise BudgetExceeded("journal_entries", self.budget.journal_entries)
        self._journal.append(
            cast(
                dict[str, Any],
                _strict_json(
                    {
                        "position": len(self._journal),
                        "instant_us": self.instant_us,
                        "generation": self.generation,
                        "kind": kind,
                        "name": name,
                        "value": value,
                    },
                    "journal entry",
                ),
            )
        )

    def _open_generation(self, journal_name: str) -> None:
        if self._last_generation >= self.budget.generations:
            raise BudgetExceeded("generations", self.budget.generations)
        self._last_generation += 1
        self.generation = self._last_generation
        opened = {}
        try:
            for module in self._module_order:
                opened[module] = self._modules[module].open(_ModuleContext(self, module))
        except BaseException:
            for module, target in opened.items():
                self._modules[module].close(target)
            self.generation = None
            raise
        self._generations = opened
        self._record("generation", journal_name, {"generation": self.generation, "modules": self._module_order})
        self._record("resources", journal_name, {"usage": self._checked_resources()})

    def _checked_resources(self) -> dict[str, int]:
        usage = self._resource_usage()
        exceeded = sorted(name for name, value in usage.items() if value > self.budget.resources[name])
        if exceeded:
            name = exceeded[0]
            raise BudgetExceeded(f"resource:{name}", self.budget.resources[name])
        return usage

    def _resource_usage(self) -> dict[str, int]:
        values = {}
        for module in self._module_order:
            generation = self._generations.get(module)
            usage = self._modules[module].resource_usage(generation)
            if type(usage) is not dict:
                raise TypeError("module resource_usage must return an object")
            for name, count in usage.items():
                normalized = _name(name, "resource usage name")
                if normalized in values:
                    raise ValueError(f"resource usage name is duplicated: {normalized}")
                values[normalized] = _bounded_integer(count, f"resource usage {normalized}", zero=True)
        expected, actual = set(self.budget.resources), set(values)
        if actual != expected:
            raise ValueError(
                "module resource usage must exactly match the budget; "
                f"missing={sorted(expected - actual)!r}, additional={sorted(actual - expected)!r}"
            )
        return dict(sorted(values.items()))

    def _eligible_actions(self) -> tuple[ActionRef, ...]:
        actions = []
        identities = set()
        for module in self._module_order:
            target = self._module_generation(module)
            proposed = target.eligible_actions(_ModuleContext(self, module))
            if type(proposed) is not tuple or any(not isinstance(action, ActionRef) for action in proposed):
                raise TypeError("module eligible_actions must return a tuple of ActionRef values")
            for action in proposed:
                if action.module != module:
                    raise ValueError("eligible action names a module other than its owner")
                identity = (action.module, action.name, action.identity)
                if identity in identities:
                    raise ValueError(f"eligible action identity is duplicated: {identity!r}")
                identities.add(identity)
                actions.append(action)
        if len(actions) > self.budget.eligible_actions:
            raise BudgetExceeded("eligible_actions", self.budget.eligible_actions)
        return tuple(actions)

    def _complete(self, action: ActionRef, value: object) -> StepCompleted:
        if self._owner_steps >= self.budget.owner_steps:
            raise BudgetExceeded("owner_steps", self.budget.owner_steps)
        self._owner_steps += 1
        return StepCompleted(action, _strict_json(value, "owner step result"))

    def _module_generation(self, module: str) -> Any:
        try:
            return self._generations[module]
        except KeyError:
            if module not in self._modules:
                raise ValueError(f"unknown module {module!r}") from None
            raise StaleGeneration("no live module generation") from None

    def _require_current(self, generation: int) -> None:
        if self.generation != generation:
            raise StaleGeneration(f"Timeline generation {generation} is stale; live generation is {self.generation}")

    def _require_artifact_generation(self, generation: int) -> None:
        if self._failure is None:
            self._require_current(generation)

    def _require_idle(self, generation: int) -> None:
        self._require_current(generation)
        if self._stepper is not None:
            raise SimulationError(f"owner step is already {self._stepper.phase}")

    def _require_phase(self, phase: str) -> CoroutineStepper:
        if self._stepper is None or self._stepper.phase != phase:
            actual = "idle" if self._stepper is None else self._stepper.phase
            raise SimulationError(f"Timeline phase {phase!r} required; current phase is {actual!r}")
        return self._stepper


class Timeline:
    """Public deterministic simulation and bounded debugging API."""

    def __init__(self, owner: _Runtime, generation: int) -> None:
        self._owner = owner
        self.generation = generation

    @classmethod
    def open(cls, modules: Iterable[object], budget: Budget, *, seed: int = 0) -> Timeline:
        return _Runtime(modules, budget, seed).timeline()

    @property
    def now_us(self) -> int:
        self._owner._require_current(self.generation)
        return self._owner.instant_us

    def command(self, module: str, name: str, payload: object) -> object:
        return self._owner.command(self.generation, module, name, payload)

    def observe(self, module: str, name: str, payload: object = None) -> Observation:
        return self._owner.observe(self.generation, module, name, payload)

    def advance(self, to_us: int) -> int:
        return self._owner.advance(self.generation, to_us)

    def fault(
        self,
        module: str,
        point: str,
        *,
        occurrence: int = 1,
        payload: object = None,
    ) -> Fault:
        return self._owner.arm_fault(self.generation, module, point, occurrence, payload)

    def start(self) -> LeafOffered | StepCompleted | Waiting:
        return self._owner.start(self.generation)

    def execute(self) -> LeafExecuted:
        return self._owner.execute(self.generation)

    def finish(self) -> StepCompleted:
        return self._owner.finish(self.generation)

    def step(self) -> StepCompleted | Waiting:
        result = self.start()
        if isinstance(result, LeafOffered):
            self.execute()
            return self.finish()
        return result

    def run(self, step_budget: int) -> RunResult:
        _bounded_integer(step_budget, "step budget", zero=True, ceiling=100_000)
        results = []
        for _ in range(step_budget):
            result = self.step()
            results.append(result)
            if isinstance(result, Waiting):
                return RunResult(tuple(results), False)
        return RunResult(tuple(results), True)

    def crash(self, cut: str) -> None:
        self._owner.crash(self.generation, cut)

    def restart(self) -> Timeline:
        return self._owner.restart(self.generation)

    def artifact(self, scenario_id: str) -> Artifact:
        self._owner._require_artifact_generation(self.generation)
        return self._owner.artifact(scenario_id)


def replay(artifact: Artifact, build_modules: Callable[[], Iterable[object]]) -> ReplayResult:
    modules = tuple(build_modules())
    names = tuple(_name(getattr(module, "name", None), "module name") for module in modules)
    if names != artifact.modules:
        raise ReplayMismatch(f"replay module order diverged: expected {artifact.modules!r}, observed {names!r}")
    owner = _Runtime(modules, artifact.budget, seed=0, expected=artifact.operations)
    timeline = owner.timeline()
    try:
        for expected in artifact.operations:
            failed = expected["kind"] == "failure"
            attempt = expected["attempt"] if failed else expected
            kind, request = attempt["kind"], attempt["request"]
            try:
                if kind == "command":
                    timeline.command(request["module"], request["name"], request["payload"])
                elif kind == "observe":
                    timeline.observe(request["module"], request["name"], request["payload"])
                elif kind == "advance":
                    timeline.advance(request["to_us"])
                elif kind == "fault":
                    timeline.fault(
                        request["module"],
                        request["point"],
                        occurrence=request["occurrence"],
                        payload=request["payload"],
                    )
                elif kind == "start":
                    timeline.start()
                elif kind == "execute":
                    timeline.execute()
                elif kind == "finish":
                    timeline.finish()
                elif kind == "crash":
                    timeline.crash(request["cut"])
                elif kind == "restart":
                    timeline = timeline.restart()
                else:
                    raise ReplayMismatch(f"artifact has unknown operation kind {kind!r}")
            except BudgetExceeded:
                if not failed:
                    raise ReplayMismatch(f"replay unexpectedly exhausted a budget during {kind!r}") from None
            else:
                if failed:
                    raise ReplayMismatch(f"replay did not reproduce failed {kind!r} operation")
        return owner.assert_replayed(artifact)
    finally:
        owner.close()


def _observation_data(value: Observation) -> dict[str, Any]:
    return {
        "module": value.module,
        "name": value.name,
        "value": value.value,
        "instant_us": value.instant_us,
        "generation": value.generation,
        "sequence": value.sequence,
    }


def _exact_object(value: object, keys: set[str], subject: str) -> dict[str, Any]:
    if type(value) is not dict or set(cast(dict[object, object], value)) != keys:
        raise ValueError(f"{subject} must contain exactly {sorted(keys)!r}")
    return cast(dict[str, Any], value)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _refuse_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value}")


__all__ = [
    "ActionRef",
    "Artifact",
    "Budget",
    "BudgetExceeded",
    "ErrorRef",
    "Fault",
    "LeafExecuted",
    "LeafOffered",
    "LeafRef",
    "Observation",
    "OneLeafViolation",
    "ReplayMismatch",
    "ReplayResult",
    "RunResult",
    "SimulationError",
    "StaleGeneration",
    "StepCompleted",
    "Timeline",
    "Waiting",
    "digest_json",
    "replay",
]
