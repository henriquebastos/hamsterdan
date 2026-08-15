"""Durable Petrus runtime for one cohabited V5 PR instance."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from petrus.engine import DriveOutcome, Engine, choose_throughput
from petrus.impetus.history import ActivityCompleted, ActivityFailed, ActivityRequested, ActivityTerminalQuarantined
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Token
from petrus.motus.activity import ActivityDefinition
from petrus.motus.dispatch import InlineDispatch, LocalDispatch
from petrus.motus.worker import Worker

from hamsterdan.host.runtime import CompositeDispatch
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.ingress import IngressEntry
from hamsterdan.readiness.net_v5 import build_net_v5, seed_marking
from hamsterdan.readiness.net_v5.gating import wire_gates
from hamsterdan.readiness.net_v5.topology import DERIVED, GATES

_DURABLE_ACTIVITIES = frozenset({"reply_gate", "dash_gate", "announce_gate"})


def _durable_queue(instance: str) -> str:
    return f"v5-publication:{instance}"


def _terminal_occurrences(records: tuple[object, ...]) -> set[int]:
    return {
        record.occurrence
        for record in records
        if isinstance(record, (ActivityCompleted, ActivityFailed, ActivityTerminalQuarantined))
    }


class V5Runtime:
    """One V5 Engine whose JSONL History is the workflow authority."""

    def __init__(
        self,
        engine: Engine,
        loader: Callable[[], Engine],
        definitions: Mapping[str, ActivityDefinition],
        agent_settle: Callable[[set[str]], None] | None,
        mutation_operation: Callable[[str], str] | None,
        durable_worker: Worker | None,
    ) -> None:
        self.engine = engine
        self._loader = loader
        self._definitions = dict(definitions)
        self._agent_settle = agent_settle
        self._mutation_operation = mutation_operation
        self._durable_worker = durable_worker

    @classmethod
    def open(
        cls,
        root: Path,
        instance: str,
        definitions: Mapping[str, ActivityDefinition],
        *,
        dispatch_path: Path | None = None,
        agent_settle: Callable[[set[str]], None] | None = None,
        mutation_operation: Callable[[str], str] | None = None,
    ) -> V5Runtime:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        built = build_net_v5()
        handlers = wire_gates(built, GATES, definitions, DERIVED)
        declarations = tuple(definition.declaration for definition in definitions.values())

        def dispatch():
            inline = InlineDispatch(definitions)
            if dispatch_path is None:
                return inline
            durable = LocalDispatch(
                dispatch_path,
                instance=instance,
                activity_queues={name: _durable_queue(instance) for name in _DURABLE_ACTIVITIES},
            )
            return CompositeDispatch(inline, durable, _DURABLE_ACTIVITIES)

        history_path = root / "history.jsonl"

        def load() -> Engine:
            return Engine.load(
                built.net,
                instance,
                history=JsonlHistoryStore(history_path),
                dispatch=dispatch(),
                handlers=handlers,
                guards=built.guards,
                policy=choose_throughput,
                activities=declarations,
            )

        engine = (
            load()
            if history_path.exists()
            else Engine.create(
                built.net,
                instance,
                history=JsonlHistoryStore(history_path),
                dispatch=dispatch(),
                handlers=handlers,
                guards=built.guards,
                policy=choose_throughput,
                activities=declarations,
                marking=seed_marking(instance),
            )
        )
        durable_worker = None
        if dispatch_path is not None:
            provider = LocalDispatch(dispatch_path, instance=instance).worker((_durable_queue(instance),))
            durable_worker = Worker(provider, {name: definitions[name] for name in _DURABLE_ACTIVITIES})
        return cls(engine, load, definitions, agent_settle, mutation_operation, durable_worker)

    def deliver(self, entry: IngressEntry) -> object:
        try:
            return self.engine.deliver(
                entry.source,
                Token(entry.color, entry.payload),
                identity=entry.identity,
            )
        except Exception:
            # A JSONL append may have committed before its caller saw an
            # exception. Reopen canonical History before the exact retry;
            # never infer absence from an exception.
            replacement = self._loader()
            previous = self.engine
            self.engine = replacement
            previous.close()
            raise

    def drain(self, limit: int = 500) -> DriveOutcome:
        self._settle_agent_routes()
        for _ in range(limit):
            try:
                outcome = self.engine.advance()
            except Exception:
                replacement = self._loader()
                previous = self.engine
                self.engine = replacement
                previous.close()
                self._settle_agent_routes()
                raise
            self._settle_agent_routes()
            if not outcome.ready:
                return outcome
        raise RuntimeError("V5 Engine did not reach an external wait")

    def _settle_agent_routes(self) -> None:
        if self._agent_settle is None:
            return
        records = tuple(self.engine.records)
        requested: dict[int, tuple[str, str]] = {}
        for record in records:
            if not isinstance(record, ActivityRequested) or not isinstance(record.input, dict):
                continue
            work = record.input.get("work")
            if not isinstance(work, dict):
                continue
            operation = work.get("operation")
            if not isinstance(operation, str) and record.activity == "git_gate":
                op_key = work.get("op_key")
                if isinstance(op_key, str) and self._mutation_operation is not None:
                    operation = self._mutation_operation(op_key)
            if isinstance(operation, str):
                requested[record.occurrence] = record.activity, operation
        settled: set[str] = set()
        for record in records:
            if not isinstance(record, (ActivityCompleted, ActivityFailed)) or record.occurrence not in requested:
                continue
            activity_name, operation = requested[record.occurrence]
            if (
                activity_name == "git_gate"
                and isinstance(record, ActivityCompleted)
                and isinstance(record.result, dict)
                and record.result.get("$variant") == "FaultM"
            ):
                continue
            settled.add(operation)
        self._agent_settle(settled)

    def activity(self, name: str) -> ActivityDefinition | None:
        return self._definitions.get(name)

    def active_claim(self, operation: str) -> CurrentClaim | None:
        records = tuple(self.engine.records)
        terminal = _terminal_occurrences(records)
        claims: list[CurrentClaim] = []
        for record in records:
            if (
                not isinstance(record, ActivityRequested)
                or record.occurrence in terminal
                or not isinstance(record.input, dict)
                or not isinstance(record.input.get("work"), dict)
            ):
                continue
            payload = cast(dict[str, Any], record.input)
            work = cast(dict[str, object], payload["work"])
            if work.get("op") != operation:
                continue
            incarnation, head, base, policy = (
                work.get("incarnation"),
                work.get("head"),
                work.get("base"),
                work.get("policy"),
            )
            if (
                type(incarnation) is not int
                or not isinstance(head, str)
                or not isinstance(base, str)
                or not isinstance(policy, str)
            ):
                raise RuntimeError("active V5 effect claim is malformed")
            claims.append(CurrentClaim("running", incarnation, head, base, policy))
        if len(claims) > 1:
            raise RuntimeError("V5 effect operation has multiple active requests")
        return claims[0] if claims else None

    def has_unresolved_publication(self) -> bool:
        records = tuple(self.engine.records)
        terminal = _terminal_occurrences(records)
        return any(
            isinstance(record, ActivityRequested)
            and record.occurrence not in terminal
            and record.activity in _DURABLE_ACTIVITIES
            for record in records
        )

    def run_durable_activities(self, limit: int) -> int:
        if self._durable_worker is None:
            return 0
        return self._durable_worker.run_available(limit=limit)

    def close(self) -> None:
        try:
            if self._durable_worker is not None:
                self._durable_worker.close()
        finally:
            self.engine.close()


__all__ = ["V5Runtime"]
