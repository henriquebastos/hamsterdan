"""Durable Petrus runtime for one cohabited V5 PR instance."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from petrus.engine import Action, BeginCandidate, DriveOutcome, Engine, Snapshot, choose_throughput
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    ActivityTerminalQuarantined,
    ExternalEventDelivered,
)
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Binding, NetPath, Token
from petrus.impetus.selection import SelectionPipeline, SelectionProposal, SelectionState
from petrus.motus.activity import Activity, ActivityDefinition
from petrus.motus.dispatch import InlineDispatch, LocalDispatch
from petrus.motus.worker import Worker
from pydantic import TypeAdapter, ValidationError

from hamsterdan.contracts.readiness_v5 import (
    ADeferred,
    AnnounceReq,
    AWake,
    RoundDeferred,
    RoundWake,
    TimerCommand,
    TimerCommandApplied,
    TimerDue,
)
from hamsterdan.host.protocol import DurableActivityResolver
from hamsterdan.host.runtime import CompositeDispatch
from hamsterdan.host.v5.claim import CurrentClaim
from hamsterdan.host.v5.ingress import IngressEntry
from hamsterdan.host.v5.timers import V5TimerStore
from hamsterdan.readiness.net_v5 import build_net_v5, seed_marking
from hamsterdan.readiness.net_v5.gating import wire_gates
from hamsterdan.readiness.net_v5.topology import DERIVED, GATES

_DURABLE_ACTIVITIES = frozenset({"reply_gate", "dash_gate", "announce_gate"})
_INGRESS_FOLDS = {
    "on_head": (NetPath("life.heads"), NetPath("life.admit_head")),
    "on_draft": (NetPath("life.drafts"), NetPath("life.admit_draft")),
    "on_ready": (NetPath("life.readies"), NetPath("life.admit_ready")),
    "on_close": (NetPath("life.closes"), NetPath("life.admit_close")),
    "on_comment": (NetPath("life.comments"), NetPath("life.admit_comment")),
    "on_human": (NetPath("life.humans"), NetPath("life.admit_human")),
    "on_runs": (NetPath("life.runs"), NetPath("life.admit_runs")),
}


def _durable_queue(instance: str) -> str:
    return f"v5-publication:{instance}"


def _terminal_occurrences(records: tuple[object, ...]) -> set[int]:
    return {
        record.occurrence
        for record in records
        if isinstance(record, (ActivityCompleted, ActivityFailed, ActivityTerminalQuarantined))
    }


class _V5EnginePolicy:
    """Throughput normally; select one exact lifecycle fold during ingress admission."""

    target: NetPath | None = None
    _selection = SelectionPipeline()

    def propose(self, candidates: tuple[Binding, ...], state: SelectionState) -> SelectionProposal | None:
        if self.target is not None:
            candidates = tuple(candidate for candidate in candidates if candidate.transition == self.target)
        return self._selection.propose(candidates, state)

    def fold_committed(self, state: SelectionState, transition: NetPath) -> SelectionState:
        return self._selection.fold_committed(state, transition)

    def __call__(self, snapshot: Snapshot) -> Action:
        if self.target is not None:
            selected = next(
                (
                    action
                    for action in snapshot.actions
                    if isinstance(action, BeginCandidate) and action.binding.transition == self.target
                ),
                None,
            )
            if selected is None:
                raise RuntimeError(f"V5 ingress row cannot fold through {self.target}")
            return selected
        return choose_throughput(snapshot)


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
        policy: _V5EnginePolicy,
    ) -> None:
        self.engine = engine
        self._loader = loader
        self._definitions = dict(definitions)
        self._agent_settle = agent_settle
        self._mutation_operation = mutation_operation
        self._durable_worker = durable_worker
        self._policy = policy

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
        reminder_delay_s: int = 3 * 24 * 60 * 60,
        durable_activity_resolver: DurableActivityResolver | None = None,
    ) -> V5Runtime:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        built = build_net_v5()
        handlers = wire_gates(built, GATES, definitions, DERIVED)
        declarations = tuple(definition.declaration for definition in definitions.values())
        policy = _V5EnginePolicy()

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
                policy=policy,
                selection=policy,
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
                policy=policy,
                selection=policy,
                activities=declarations,
                marking=seed_marking(instance, reminder_delay_s=reminder_delay_s),
            )
        )
        durable_worker = None
        if dispatch_path is not None:
            provider = LocalDispatch(dispatch_path, instance=instance).worker((_durable_queue(instance),))
            activities = {name: definitions[name] for name in _DURABLE_ACTIVITIES}
            resolver = None
            if durable_activity_resolver is not None:

                def resolve(attempt_instance: str, activity: str) -> Activity | None:
                    definition = activities.get(activity)
                    if definition is None:
                        return None
                    return durable_activity_resolver(attempt_instance, activity, definition)

                resolver = resolve
            durable_worker = Worker(provider, activities, resolver=resolver)
        runtime = cls(engine, load, definitions, agent_settle, mutation_operation, durable_worker, policy)
        runtime._validate_review_wake_history()
        runtime._validate_announce_wake_history()
        return runtime

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

    def manifest_accepted(self, entries: tuple[IngressEntry, ...]) -> bool:
        """Whether canonical History has accepted every frozen ingress identity."""
        accepted: dict[str, ExternalEventDelivered] = {}
        for record in self.engine.records:
            if not isinstance(record, ExternalEventDelivered):
                continue
            if record.identity in accepted:
                raise RuntimeError("V5 ingress identity occurs more than once in canonical History")
            accepted[record.identity] = record
        missing = False
        for entry in entries:
            record = accepted.get(entry.identity)
            if record is None:
                missing = True
                continue
            if (
                str(record.source) != entry.source
                or len(record.tokens) != 1
                or record.tokens[0].color != entry.color
                or record.tokens[0].data != entry.payload
            ):
                raise RuntimeError("V5 ingress manifest conflicts with canonical History")
        return not missing

    def manifest_folded(self, entries: tuple[IngressEntry, ...]) -> bool:
        """Whether every accepted manifest row completed its lifecycle fold."""
        if not self.manifest_accepted(entries):
            return False
        for entry in entries:
            try:
                mailbox, _ = _INGRESS_FOLDS[entry.source]
            except KeyError:
                raise ValueError("V5 ingress source has no lifecycle fold") from None
            if Token(entry.color, entry.payload) in self.engine.marking.place(mailbox):
                return False
        return True

    def fold_ingress(self, entry: IngressEntry) -> DriveOutcome | None:
        """Apply the accepted row's pending lifecycle fold, if replay has not already done so."""
        try:
            mailbox, target = _INGRESS_FOLDS[entry.source]
        except KeyError:
            raise ValueError("V5 ingress source has no lifecycle fold") from None
        token = Token(entry.color, entry.payload)
        if token not in self.engine.marking.place(mailbox):
            return None
        self._policy.target = target
        try:
            outcome = self.engine.advance()
        except Exception:
            replacement = self._loader()
            previous = self.engine
            self.engine = replacement
            previous.close()
            raise
        finally:
            self._policy.target = None
        if not any(firing.transition == target for firing in outcome.firings):
            raise RuntimeError("V5 ingress row did not complete its lifecycle fold")
        return outcome

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
            if (
                activity_name == "review_agent"
                and isinstance(record, ActivityCompleted)
                and isinstance(record.result, dict)
                and record.result.get("$variant") == "RoundDeferred"
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

    @staticmethod
    def _timer_value(model, data: object, label: str):
        try:
            return TypeAdapter(model).validate_json(json.dumps(data, sort_keys=True, separators=(",", ":")))
        except TypeError, ValidationError:
            raise RuntimeError(f"V5 timer {label} is malformed") from None

    def timer_command(self) -> TimerCommand | None:
        """Return the intentional Net→host timer outbox token, if any."""
        tokens = tuple(self.engine.marking.place(NetPath("rem.commands")))
        if not tokens:
            return None
        if len(tokens) != 1 or tokens[0].color != "TimerCommand":
            raise RuntimeError("V5 timer outbox has invalid cardinality or color")
        return self._timer_value(TimerCommand, tokens[0].data, "command")

    def timer_history(self) -> tuple[TimerCommandApplied | TimerDue, ...]:
        """Project accepted typed timer boundary facts in canonical History order."""
        facts: list[TimerCommandApplied | TimerDue] = []
        types = {
            NetPath("on_timer_command_applied"): ("TimerCommandApplied", TimerCommandApplied),
            NetPath("on_timer"): ("TimerDue", TimerDue),
        }
        for record in self.engine.records:
            if not isinstance(record, ExternalEventDelivered) or record.source not in types:
                continue
            color, model = types[record.source]
            if len(record.tokens) != 1 or record.tokens[0].color != color:
                raise RuntimeError("V5 timer History delivery is malformed")
            fact = self._timer_value(model, record.tokens[0].data, "History delivery")
            expected_identity = (
                V5TimerStore.ack_identity(fact.operation)
                if isinstance(fact, TimerCommandApplied)
                else V5TimerStore.due_identity(fact)
            )
            if record.identity != expected_identity:
                raise RuntimeError("V5 timer History delivery identity is malformed")
            facts.append(fact)
        return tuple(facts)

    def deliver_timer_ack(self, value: TimerCommandApplied, identity: str) -> object:
        return self.deliver(IngressEntry.from_value("on_timer_command_applied", value, identity))

    def deliver_timer_due(self, value: TimerDue, identity: str) -> object:
        return self.deliver(IngressEntry.from_value("on_timer", value, identity))

    def review_deferred(self) -> RoundDeferred | None:
        self._validate_review_wake_history()
        tokens = tuple(self.engine.marking.place(NetPath("review.deferred")))
        if not tokens:
            return None
        if len(tokens) != 1 or tokens[0].color != "RoundDeferred":
            raise RuntimeError("V5 deferred review has invalid cardinality or color")
        return self._review_value(RoundDeferred, tokens[0].data, "deferred review")

    @staticmethod
    def _review_value(model, data: object, label: str):
        try:
            return TypeAdapter(model).validate_json(json.dumps(data, sort_keys=True, separators=(",", ":")))
        except TypeError, ValidationError:
            raise RuntimeError(f"V5 {label} is malformed") from None

    def _validate_review_wake_history(self) -> None:
        deferred: set[str] = set()
        seen: set[str] = set()
        for record in self.engine.records:
            if (
                isinstance(record, ActivityCompleted)
                and record.transition == NetPath("review.agent")
                and isinstance(record.result, dict)
                and record.result.get("$variant") == "RoundDeferred"
            ):
                value = self._review_value(
                    RoundDeferred,
                    {key: item for key, item in record.result.items() if key != "$variant"},
                    "deferred review History terminal",
                )
                identity = self.review_wake_identity(
                    RoundWake(operation=value.operation, attempt=value.attempt, blocker=value.blocker)
                )
                if identity in deferred:
                    raise RuntimeError("V5 deferred review History terminal occurs more than once")
                deferred.add(identity)
                continue
            if not isinstance(record, ExternalEventDelivered) or record.source != NetPath("on_review_round_wake"):
                continue
            if len(record.tokens) != 1 or record.tokens[0].color != "RoundWake":
                raise RuntimeError("V5 review wake History delivery is malformed")
            wake = self._review_value(RoundWake, record.tokens[0].data, "review wake History delivery")
            expected = self.review_wake_identity(wake)
            if record.identity != expected or record.identity in seen:
                raise RuntimeError("V5 review wake History identity is malformed")
            if expected not in deferred:
                raise RuntimeError("V5 review wake History has no deferred round")
            seen.add(record.identity)

    @staticmethod
    def review_wake_identity(value: RoundWake) -> str:
        digest = sha256(f"{value.operation}\0{value.attempt}\0{value.blocker}".encode()).hexdigest()
        return f"v5-review-wake:{digest}"

    def deliver_review_wake(self, value: RoundWake, identity: str) -> object:
        return self.deliver(IngressEntry.from_value("on_review_round_wake", value, identity))

    def announce_deferred(self) -> ADeferred | None:
        self._validate_announce_wake_history()
        tokens = tuple(self.engine.marking.place(NetPath("ready.deferred")))
        if not tokens:
            return None
        if len(tokens) != 1 or tokens[0].color != "ADeferred":
            raise RuntimeError("V5 deferred announcement has invalid cardinality or color")
        return self._announce_value(ADeferred, tokens[0].data, "deferred announcement")

    @staticmethod
    def _announce_value(model, data: object, label: str):
        try:
            return TypeAdapter(model).validate_json(json.dumps(data, sort_keys=True, separators=(",", ":")))
        except TypeError, ValidationError:
            raise RuntimeError(f"V5 {label} is malformed") from None

    @staticmethod
    def _deferred_request(value: ADeferred) -> AnnounceReq:
        return AnnounceReq(
            op=value.op,
            incarnation=value.incarnation,
            head=value.head,
            base=value.base,
            policy=value.policy,
            strict_base=value.strict_base,
            base_current=value.base_current,
        )

    def _validate_announce_wake_history(self) -> None:
        requested: dict[int, AnnounceReq] = {}
        deferred: set[str] = set()
        seen: set[str] = set()
        for record in self.engine.records:
            if (
                isinstance(record, ActivityRequested)
                and record.transition == NetPath("ready.gate")
                and record.activity == "announce_gate"
                and isinstance(record.input, dict)
                and isinstance(record.input.get("work"), dict)
            ):
                payload = cast(dict[str, Any], record.input)
                requested[record.occurrence] = self._announce_value(
                    AnnounceReq, payload["work"], "announcement History request"
                )
                continue
            if (
                isinstance(record, ActivityCompleted)
                and record.transition == NetPath("ready.gate")
                and isinstance(record.result, dict)
                and record.result.get("$variant") == "ADeferred"
            ):
                value = self._announce_value(
                    ADeferred,
                    {key: item for key, item in record.result.items() if key != "$variant"},
                    "deferred announcement History terminal",
                )
                if requested.get(record.occurrence) != self._deferred_request(value):
                    raise RuntimeError("V5 deferred announcement differs from its History request")
                wake = AWake(**value.dump())
                identity = self.announce_wake_identity(wake)
                if identity in deferred:
                    raise RuntimeError("V5 deferred announcement History terminal occurs more than once")
                deferred.add(identity)
                continue
            if not isinstance(record, ExternalEventDelivered) or record.source != NetPath("on_announce_wake"):
                continue
            if len(record.tokens) != 1 or record.tokens[0].color != "AWake":
                raise RuntimeError("V5 announcement wake History delivery is malformed")
            wake = self._announce_value(AWake, record.tokens[0].data, "announcement wake History delivery")
            expected = self.announce_wake_identity(wake)
            if record.identity != expected or record.identity in seen:
                raise RuntimeError("V5 announcement wake History identity is malformed")
            if expected not in deferred:
                raise RuntimeError("V5 announcement wake History has no deferred request")
            seen.add(record.identity)

    @staticmethod
    def announce_wake_identity(value: AWake) -> str:
        encoded = json.dumps(value.dump(), sort_keys=True, separators=(",", ":"))
        return f"v5-announce-wake:{sha256(encoded.encode()).hexdigest()}"

    def deliver_announce_wake(self, value: AWake, identity: str) -> object:
        return self.deliver(IngressEntry.from_value("on_announce_wake", value, identity))

    def run_durable_activities(self, limit: int) -> int:
        if self._durable_worker is None:
            return 0
        return self._durable_worker.run_available(limit=limit)

    def stop_durable_activities(self) -> None:
        if self._durable_worker is not None:
            self._durable_worker.stop()

    def close(self) -> None:
        try:
            if self._durable_worker is not None:
                self._durable_worker.close()
        finally:
            self.engine.close()


__all__ = ["V5Runtime"]
