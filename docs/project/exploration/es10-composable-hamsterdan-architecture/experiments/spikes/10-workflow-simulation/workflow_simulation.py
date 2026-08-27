"""Workflow-local simulation mounted on the Experiment 9 Timeline contract.

The real execution seams are Petrus ``Engine.advance()``, History, Dispatch,
ActivityDefinition, and the accepted Experiment 3 workflow package. The store
retains History and accepted simulation commands; every generation rebuilds its
Engine and Dispatch handles from that retained state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from petrus.engine import Engine
from petrus.impetus.history import ActivityCompleted, ActivityFailed, ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import NetPath, Token
from petrus.motus.activity import activity
from petrus.motus.dispatch import InMemoryDispatch
from runtime import ActionRef
from workflow.activities import RerunFault, RerunLanded, RerunMoved, RerunReq
from workflow.net.gating import VariantPayloadConverter, wire_gates
from workflow.net.topology import GATES, MANIFEST, build_net, seed_marking
from workflow.observations import HeadSeen, RunSeen

_HEAD_FIELDS = {"base", "head", "identity", "incarnation", "policy"}
_RUN_FIELDS = {"attempt", "conclusion", "fingerprint", "head", "identity", "run_id"}
_TERMINAL_FIELDS = {"operation", "variant"}


def _unexecuted_rerun_port(work: RerunReq) -> RerunLanded | RerunMoved | RerunFault:
    raise RuntimeError(f"rerun operation {work.op!r} requires the terminal.rerun simulation command")


@dataclass
class _Store:
    history: InMemoryHistoryStore = field(default_factory=InMemoryHistoryStore)
    commands: list[dict[str, Any]] = field(default_factory=list)
    deliveries: dict[str, dict[str, Any]] = field(default_factory=dict)
    created: bool = False
    generation_loads: int = 0


class WorkflowSimulation:
    name = "workflow"

    def __init__(self, store: _Store) -> None:
        self.store = store

    @classmethod
    def fresh(cls) -> WorkflowSimulation:
        return cls(_Store())

    def open(self, _context: object) -> _Generation:
        return _Generation.open(self.store)

    def drop(self, generation: _Generation) -> None:
        generation.close()

    def close(self, generation: _Generation) -> None:
        generation.close()

    def resource_usage(self, _generation: _Generation | None) -> dict[str, int]:
        return {
            "workflow.commands": len(self.store.commands),
            "workflow.history_records": len(self.store.history),
            "workflow.pending_activities": _unresolved_activity_count(self.store.history.records),
        }


class _Generation:
    def __init__(
        self, store: _Store, engine: Engine, dispatch: InMemoryDispatch, definition: object, ready: bool
    ) -> None:
        self.store = store
        self.engine = engine
        self.dispatch = dispatch
        self.definition = definition
        self.ready = ready
        self.turn = 0

    @classmethod
    def open(cls, store: _Store) -> _Generation:
        built = build_net()
        definition = activity(
            _unexecuted_rerun_port,
            name="rerun_gate",
            converter=VariantPayloadConverter(),
        )
        definitions = {"rerun_gate": definition}
        dispatch = InMemoryDispatch()
        options = {
            "history": store.history,
            "dispatch": dispatch,
            "handlers": wire_gates(built, GATES, definitions, MANIFEST),
            "guards": dict(built.guards),
            "activities": (definition.declaration,),
        }
        if store.created:
            engine = Engine.load(built.net, "workflow-spike", **options)
            ready = True
        else:
            engine = Engine.create(
                built.net,
                "workflow-spike",
                marking=seed_marking("workflow:spike"),
                **options,
            )
            store.created = True
            ready = False
        store.generation_loads += 1
        return cls(store, engine, dispatch, definition, ready)

    def close(self) -> None:
        self.engine.close()

    def command(self, name: str, payload: object, context: Any) -> object:
        if name == "observe.head":
            return self._deliver_head(payload)
        if name == "observe.run":
            return self._deliver_run(payload)
        if name == "terminal.rerun":
            return self._complete_rerun(payload, context)
        raise ValueError(f"unknown workflow command {name!r}")

    def observe(self, name: str, payload: object, _context: object) -> object:
        if payload not in (None, {}):
            raise ValueError(f"workflow observation {name!r} takes no payload")
        if name == "state":
            return self._state()
        if name == "check":
            return self._check()
        raise ValueError(f"unknown workflow observation {name!r}")

    def eligible_actions(self, context: Any) -> tuple[ActionRef, ...]:
        if not self.ready:
            return ()
        return (
            ActionRef(
                module="workflow",
                name="advance",
                identity=f"advance:{context.generation}:{len(self.store.history)}:{self.turn}",
                eligible_at_us=0,
            ),
        )

    async def step(self, action: ActionRef, context: Any) -> object:
        [expected] = self.eligible_actions(context)
        if action != expected:
            raise ValueError(f"undeclared workflow action {action!r}")
        result = await context.call(
            "engine.advance",
            {"history_position": len(self.store.history)},
            self._advance,
        )
        self.ready = result["ready"]
        self.turn += 1
        return result

    def _deliver_head(self, payload: object) -> object:
        data = _exact_payload(payload, _HEAD_FIELDS, "observe.head")
        value = HeadSeen(
            head=_text(data["head"], "head"),
            base=_text(data["base"], "base"),
            policy=_text(data["policy"], "policy"),
            incarnation=_integer(data["incarnation"], "incarnation"),
        )
        return self._deliver(
            "observe.head",
            "on_head",
            "HeadSeen",
            value.dump(),
            _text(data["identity"], "identity"),
        )

    def _deliver_run(self, payload: object) -> object:
        data = _exact_payload(payload, _RUN_FIELDS, "observe.run")
        conclusion = data["conclusion"]
        if conclusion not in {"queued", "in_progress", "success", "failure"}:
            raise ValueError("observe.run conclusion is not declared")
        value = RunSeen(
            head=_text(data["head"], "head"),
            run_id=_integer(data["run_id"], "run_id"),
            attempt=_integer(data["attempt"], "attempt"),
            conclusion=conclusion,
            fingerprint=_text(data["fingerprint"], "fingerprint"),
        )
        return self._deliver(
            "observe.run",
            "on_runs",
            "RunSeen",
            value.dump(),
            _text(data["identity"], "identity"),
        )

    def _deliver(
        self,
        command_name: str,
        source: str,
        color: str,
        payload: dict[str, Any],
        identity: str,
    ) -> object:
        command = {"name": command_name, "payload": {"identity": identity, **payload}}
        prior = self.store.deliveries.get(identity)
        if prior is not None and prior != command:
            raise ValueError(f"workflow delivery identity {identity!r} conflicts with its retained command")
        self.engine.deliver(source, Token(color, payload), identity=identity)
        if prior is None:
            self.store.deliveries[identity] = command
            self.store.commands.append(command)
        self.ready = True
        return {"accepted": prior is None, "identity": identity, "source": source}

    def _complete_rerun(self, payload: object, context: Any) -> object:
        data = _exact_payload(payload, _TERMINAL_FIELDS, "terminal.rerun")
        if data["variant"] != "landed":
            raise ValueError("terminal.rerun variant must be 'landed'")
        occurrence, invocation = _one_pending(self.dispatch)
        operation = _text(data["operation"], "operation")
        if (
            invocation.activity != "rerun_gate"
            or invocation.correlation != operation
            or invocation.idempotency != operation
        ):
            raise ValueError(f"terminal.rerun operation {operation!r} does not match the pending rerun")
        work = self.definition.converter.decode(invocation.input["work"], RerunReq)
        actual_operation = operation
        faults = context.faults("terminal.rerun.corrupt_operation")
        if faults:
            [fault] = faults
            fault_payload = _exact_payload(fault.payload, {"replacement"}, "terminal.rerun.corrupt_operation")
            actual_operation = _text(fault_payload["replacement"], "replacement")
        terminal = RerunLanded(
            fingerprint=work.fingerprint,
            op=actual_operation,
            run_id=work.run_id,
            attempt=work.attempt,
        )
        encoded = self.definition.converter.encode(terminal, self.definition.result)
        self.dispatch.complete(occurrence, encoded)
        self.store.commands.append({"name": "terminal.rerun", "payload": {"operation": operation, "variant": "landed"}})
        self.ready = True
        return {"occurrence": occurrence, "operation": operation, "terminal_operation": actual_operation}

    def _advance(self) -> dict[str, Any]:
        before = len(self.store.history)
        pending_before = bool(self.dispatch.pending)
        outcome = self.engine.advance()
        added = self.store.history.records[before:]
        requested = next((record for record in added if isinstance(record, ActivityRequested)), None)
        completed = next((record for record in added if isinstance(record, (ActivityCompleted, ActivityFailed))), None)
        pending_after = bool(self.dispatch.pending)
        if requested is not None:
            cut = "activity_requested"
            activity = requested.activity
            operation = requested.correlation
        elif completed is not None:
            cut = "activity_terminal_projected"
            activity = "rerun_gate"
            operation = _terminal_operation(completed)
        elif not pending_before and pending_after:
            cut = "activity_request_reconstructed"
            [(activity, operation)] = [
                (invocation.activity, invocation.correlation) for invocation in self.dispatch.pending.values()
            ]
        else:
            cut = "workflow_action_committed"
            activity = None
            operation = None
        return {
            "activity": activity,
            "cut": cut,
            "operation": operation,
            "ready": outcome.ready,
            "records_added": len(added),
        }

    def _state(self) -> dict[str, Any]:
        return {
            "generation_loads": self.store.generation_loads,
            "history_records": len(self.store.history),
            "ladder": _one_token(self.engine, "esc.ladder"),
            "pending": _pending_projection(self.dispatch),
            "terminal": _terminal_projection(self.store.history.records),
        }

    def _check(self) -> dict[str, Any]:
        expected = _expected_operation(self.store.commands)
        violations: list[str] = []
        requests = [record for record in self.store.history.records if isinstance(record, ActivityRequested)]
        if expected is not None and requests:
            if len(requests) != 1:
                violations.append(f"expected one rerun request, observed {len(requests)}")
            elif requests[0].correlation != expected:
                violations.append(
                    f"rerun request operation {requests[0].correlation!r} does not match derived operation {expected!r}"
                )
        terminal = _terminal_projection(self.store.history.records)
        if expected is not None and terminal is not None and terminal["op"] != expected:
            violations.append(
                f"{terminal['variant']} terminal operation {terminal['op']!r} "
                f"does not match requested operation {expected!r}"
            )
        return {"expected_operation": expected, "ok": not violations, "violations": violations}


def _exact_payload(payload: object, fields: set[str], command: str) -> dict[str, Any]:
    if type(payload) is not dict or set(payload) != fields:
        raise ValueError(f"{command} requires exactly {', '.join(sorted(fields))}")
    return payload


def _text(value: object, field_name: str) -> str:
    if type(value) is not str or not value or not value.isascii() or not value.isprintable():
        raise ValueError(f"{field_name} must be a non-empty printable ASCII string")
    return value


def _integer(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _one_pending(dispatch: InMemoryDispatch) -> tuple[int, Any]:
    pending = list(dispatch.pending.items())
    if len(pending) != 1:
        raise ValueError(f"terminal.rerun requires one pending Activity, observed {len(pending)}")
    return pending[0]


def _pending_projection(dispatch: InMemoryDispatch) -> dict[str, Any] | None:
    pending = list(dispatch.pending.items())
    if not pending:
        return None
    if len(pending) != 1:
        raise RuntimeError(f"workflow simulation has {len(pending)} pending Activities, expected at most one")
    occurrence, invocation = pending[0]
    return {"activity": invocation.activity, "occurrence": occurrence, "operation": invocation.correlation}


def _terminal_projection(records: tuple[object, ...]) -> dict[str, Any] | None:
    terminals = [record for record in records if isinstance(record, (ActivityCompleted, ActivityFailed))]
    if not terminals:
        return None
    if len(terminals) != 1:
        raise RuntimeError(f"workflow simulation has {len(terminals)} Activity terminals, expected at most one")
    terminal = terminals[0]
    if not isinstance(terminal, ActivityCompleted) or not isinstance(terminal.result, Mapping):
        return {"occurrence": terminal.occurrence, "op": None, "variant": type(terminal).__name__}
    return {
        "occurrence": terminal.occurrence,
        "op": terminal.result.get("op"),
        "variant": terminal.result.get("$variant"),
    }


def _terminal_operation(record: ActivityCompleted | ActivityFailed) -> object:
    if isinstance(record, ActivityCompleted) and isinstance(record.result, Mapping):
        return record.result.get("op")
    return None


def _one_token(engine: Engine, place: str) -> dict[str, Any]:
    tokens = tuple(engine.marking.place(NetPath(place)))
    if len(tokens) != 1:
        raise RuntimeError(f"workflow projection {place!r} expected one token, observed {len(tokens)}")
    return dict(tokens[0].data)


def _expected_operation(commands: list[dict[str, Any]]) -> str | None:
    heads = [command["payload"] for command in commands if command["name"] == "observe.head"]
    runs = [command["payload"] for command in commands if command["name"] == "observe.run"]
    if not heads or not runs:
        return None
    head, run = heads[-1], runs[-1]
    if run["conclusion"] != "failure" or run["head"] != head["head"]:
        return None
    return f"rerun:{run['fingerprint']}:{run['run_id']}:{run['attempt']}"


def _unresolved_activity_count(records: tuple[object, ...]) -> int:
    requested = {record.occurrence for record in records if isinstance(record, ActivityRequested)}
    terminal = {record.occurrence for record in records if isinstance(record, (ActivityCompleted, ActivityFailed))}
    return len(requested - terminal)
