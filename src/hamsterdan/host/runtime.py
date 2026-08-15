"""Fresh-state Engine host and complete GitHub effect lease for PR readiness."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from petrus.engine import DriveOutcome, Engine, choose_throughput
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    ActivityTerminalQuarantined,
    FiringFailed,
    ScopeClosed,
    ScopeReset,
)
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Binding, Marking, NetPath, Token
from petrus.impetus.scope import LifecycleScope
from petrus.motus.activity import ActivityFailure, ActivityInvocation, ExecutionPolicy
from petrus.motus.dispatch import (
    CancellableDispatch,
    CancellationDisposition,
    CancellationInstruction,
    Dispatch,
    InlineDispatch,
    LocalDispatch,
)
from pydantic import TypeAdapter

from hamsterdan.contracts.readiness import (
    ActionsState,
    Authority,
    ConversationPublicationResult,
    ConversationPublicationState,
    DashboardPublicationResult,
    DashboardPublicationState,
    FindingPublicationState,
    HumanState,
    MutationState,
    ReadinessPublicationResult,
    ReadinessPublicationState,
    ReadinessSnapshot,
    ReviewState,
    Seed,
    project_readiness,
)
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.readiness.net import ACTIVITY_TRANSITIONS, build_net

from .activities import PrReadinessActivities, StaleAuthorityError, activity_definitions

_DURABLE_ACTIVITIES = frozenset({"conversation_publish", "dashboard_publish", "readiness_publish"})
_GENERATION_SCOPE = "readiness-generation"
_PUBLICATION_POLICY = ExecutionPolicy(
    attempts=3, initial_interval=5, coefficient=2, max_interval=10, jitter=0, schedule_to_close=60
)


def _terminal_occurrences(records) -> set[int]:
    terminal: set[int] = set()
    for record in records:
        if isinstance(record, (ActivityCompleted, ActivityFailed, ActivityTerminalQuarantined)):
            terminal.add(record.occurrence)
        elif isinstance(record, (ScopeClosed, ScopeReset)):
            terminal.update(record.cancelled)
    return terminal


@dataclass(frozen=True)
class CompositeDispatch:
    """Route selected Activities durably while retaining ordinary collection."""

    inline: Dispatch
    durable: Dispatch
    durable_activities: frozenset[str] = _DURABLE_ACTIVITIES

    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None:
        target = self.durable if invocation.activity in self.durable_activities else self.inline
        target.dispatch(occurrence, invocation)

    def collect(self) -> Sequence[tuple[int, object]]:
        return (*self.inline.collect(), *self.durable.collect())

    def cancel(self, instruction: CancellationInstruction) -> CancellationDisposition:
        target = self.durable if instruction.invocation.activity in self.durable_activities else self.inline
        if not isinstance(target, CancellableDispatch):
            raise TypeError("scope-managed Activity target does not support cancellation")
        return target.cancel(instruction)


@dataclass(frozen=True)
class PublicationActivityHandler:
    """Add durable publication policy and a narrow terminal blocker projection."""

    derived: DerivedActivityHandler

    def prepare(self, binding: Binding) -> ActivityInvocation:
        invocation = self.derived.prepare(binding)
        payload = invocation.input
        work = payload.get("work", payload.get("command")) if isinstance(payload, dict) else None
        operation = work.get("operation") if isinstance(work, dict) else None
        if not isinstance(operation, str) or not operation:
            raise ValueError("publication request has no immutable operation identity")
        return replace(invocation, policy=_PUBLICATION_POLICY, correlation=operation, idempotency=operation)

    def project(self, binding: Binding, result: object):
        return self.derived.project(binding, result)

    def project_failure(self, binding: Binding, failure: ActivityFailure):
        # Capability failures remain explicitly recoverable; every other
        # terminal failure projects a nonrecoverable fault so lifecycle close
        # is never wedged behind projection-pending custody.
        capability_failure = failure.kind in {"GitHubBoundaryError", "DeadlineExceeded"}
        activity = self.derived.activity.declaration.name
        expected_color = {
            "conversation_publish": "ConversationPublicationRequest",
            "dashboard_publish": "DashboardPublicationRequest",
            "readiness_publish": "ReadinessCommand",
        }[activity]
        tokens = (token for _, selected in (*binding.consumed, *binding.read) for token in selected)
        matches = [token.data for token in tokens if token.color == expected_color]
        if len(matches) != 1:
            raise TypeError("publication binding has no unique immutable request")
        work = matches[0]
        if not isinstance(work, dict):
            raise TypeError("publication binding request is not an object")
        epoch, head, operation = work.get("epoch"), work.get("head"), work.get("operation")
        if not isinstance(epoch, int) or not isinstance(head, str) or not isinstance(operation, str):
            raise TypeError("publication invocation request identity is malformed")
        result_type = {
            "conversation_publish": ConversationPublicationResult,
            "dashboard_publish": DashboardPublicationResult,
            "readiness_publish": ReadinessPublicationResult,
        }[activity]
        result = result_type(
            epoch,
            head,
            False,
            operation,
            capability_available=not capability_failure,
            faulted=not capability_failure,
        )
        return self.derived.project(binding, result.dump())


class WallClock:
    """Observe production timers without advancing beyond real wall time."""

    def now(self) -> float:
        return time.time()

    def observe(self, instant: float) -> float | None:
        now = self.now()
        return now if now >= instant else None


class AuthorityLease:
    """Join fast local cancellation to fresh provider-backed effect fencing."""

    def __init__(self, authority: GitHubAuthority):
        self.authority = authority
        self.engine: Engine | None = None

    def bind(self, engine: Engine) -> None:
        if self.engine is not None:
            raise RuntimeError("authority lease is already bound")
        self.engine = engine

    def replace(self, expected: Engine, replacement: Engine) -> None:
        if self.engine is not expected:
            raise RuntimeError("authority lease Engine changed during recovery")
        self.engine = replacement

    def _singleton(self, path: str, value_type):
        if self.engine is None:
            return None
        tokens = self.engine.marking.place(NetPath(path))
        if len(tokens) != 1:
            raise RuntimeError(f"active readiness place {path!r} must contain exactly one token")
        return TypeAdapter(value_type).validate_json(json.dumps(tokens[0].data))

    def authority_state(self) -> Authority | None:
        if self.engine is None or not self.engine.marking.place(NetPath("authority")):
            return None
        return self._singleton("authority", Authority)

    def mutation_state(self) -> MutationState | None:
        if self.engine is None or not self.engine.marking.place(NetPath("mutation_state")):
            return None
        return self._singleton("mutation_state", MutationState)

    def snapshot(self) -> ReadinessSnapshot | None:
        if self.engine is None:
            return None
        cohort = (
            ("authority", Authority),
            ("actions_state", ActionsState),
            ("review_state", ReviewState),
            ("human_state", HumanState),
            ("mutation_state", MutationState),
            ("finding_publication_state", FindingPublicationState),
            ("conversation_publication_state", ConversationPublicationState),
            ("dashboard_publication_state", DashboardPublicationState),
            ("readiness_publication_state", ReadinessPublicationState),
        )
        populated = [bool(self.engine.marking.place(NetPath(path))) for path, _ in cohort]
        if not any(populated):
            return None
        if not all(populated):
            state = ", ".join(f"{path}={int(present)}" for (path, _), present in zip(cohort, populated, strict=True))
            raise RuntimeError(f"active readiness concern cohort is incomplete: {state}")
        values = tuple(self._singleton(path, value_type) for path, value_type in cohort)
        return project_readiness(*values)

    def control(self) -> ReadinessSnapshot | None:
        return self.snapshot()

    def is_current(self, epoch: int, head: str) -> bool:
        authority = self.authority_state()
        mutation = self.mutation_state()
        return (
            authority is not None
            and mutation is not None
            and not mutation.provisional
            and (authority.epoch, authority.head) == (epoch, head)
        )

    def fence(self, epoch: int, head: str, operation: str, base_head: str, policy_digest: str) -> None:
        authority = self.authority_state()
        mutation = self.mutation_state()
        if (
            authority is None
            or mutation is None
            or (
                authority.epoch,
                authority.head,
                authority.base_head,
                authority.policy_digest,
            )
            != (epoch, head, base_head, policy_digest)
        ):
            raise StaleAuthorityError("operation no longer matches current workflow authority")
        if mutation.provisional:
            raise StaleAuthorityError("provisional authority cannot publish additional effects")
        if operation not in self._requested_operations():
            raise StaleAuthorityError("operation is not an active durable Activity request")
        pull = self.authority.pull_request()
        if pull.closed or pull.merged or pull.draft or pull.head != head or pull.base != base_head:
            raise StaleAuthorityError("GitHub lifecycle, head, or base superseded the operation")
        if self.authority.policy(pull.base_ref).digest != policy_digest:
            raise StaleAuthorityError("GitHub policy superseded the operation")
        final = self.authority.pull_request()
        if (
            final.closed
            or final.merged
            or final.draft
            or final.head != head
            or final.base != base_head
            or final.base_ref != pull.base_ref
        ):
            raise StaleAuthorityError("GitHub authority changed during the operation fence")

    def publisher_fence(self, repository: str, pr_number: int, epoch: int, head: str, operation: str) -> None:
        if repository != self.authority.repository or pr_number != self.authority.pr_number:
            raise StaleAuthorityError("publication escaped its configured PR")
        basis = self._request_basis(operation)
        if basis is None:
            raise StaleAuthorityError("publication has no active durable Activity request")
        self.fence(epoch, head, operation, basis[0], basis[1])

    def _requested_operations(self) -> set[str]:
        return {operation for operation, _, _ in self._active_requests()}

    def _request_basis(self, operation: str) -> tuple[str, str] | None:
        return next(((base, policy) for item, base, policy in self._active_requests() if item == operation), None)

    def _active_requests(self) -> list[tuple[str, str, str]]:
        if self.engine is None:
            return []
        terminal = _terminal_occurrences(self.engine.records)
        values: list[tuple[str, str, str]] = []
        for record in self.engine.records:
            if (
                not isinstance(record, ActivityRequested)
                or record.occurrence in terminal
                or not isinstance(record.input, dict)
            ):
                continue
            raw = record.input.get("work", record.input.get("command"))
            if not isinstance(raw, dict):
                continue
            operation = raw.get("operation")
            payload = raw.get("payload", {})
            if not isinstance(payload, dict):
                continue
            base = raw.get("base_head") if "base_head" in raw else payload.get("base_head")
            policy = raw.get("policy_digest") if "policy_digest" in raw else payload.get("policy_digest")
            if all(isinstance(item, str) and item for item in (operation, base, policy)):
                values.append(cast(tuple[str, str, str], (operation, base, policy)))
        return values


class PrReadinessHost:
    """One replacement Engine using an independent canonical History."""

    def __init__(
        self,
        root: Path,
        engine: Engine,
        lease: AuthorityLease,
        operations: PrReadinessActivities,
        loader: Callable[[], Engine],
        agent_settle: Callable[[set[str]], None] | None = None,
    ):
        self.root, self.engine, self.lease, self.operations = root, engine, lease, operations
        self._loader, self._agent_settle = loader, agent_settle

    @classmethod
    def open(
        cls,
        root: Path,
        instance_id: str,
        authority: GitHubAuthority,
        operations_factory,
        *,
        reminder_delay: float = 3 * 24 * 60 * 60,
        agent_settle: Callable[[set[str]], None] | None = None,
        dispatch_path: Path | None = None,
    ) -> PrReadinessHost:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        built = build_net(reminder_delay)
        lease = AuthorityLease(authority)
        operations = operations_factory(lease)
        definitions = activity_definitions(operations)
        handlers = cast(Any, dict(built.handlers))
        for path in ACTIVITY_TRANSITIONS:
            name = path.removeprefix("execute.")
            derived = DerivedActivityHandler(built.net, NetPath(path), definitions[name])
            handlers[name] = PublicationActivityHandler(derived) if name in _DURABLE_ACTIVITIES else derived
        activities = tuple(item.declaration for item in definitions.values())

        def dispatch():
            inline = InlineDispatch(definitions)
            if dispatch_path is None:
                return inline
            durable = LocalDispatch(
                dispatch_path,
                instance=instance_id,
                activity_queues={name: "publication" for name in _DURABLE_ACTIVITIES},
            )
            return CompositeDispatch(inline, durable)

        def load() -> Engine:
            return Engine.load(
                built.net,
                instance_id,
                history=JsonlHistoryStore(root / "history.jsonl"),
                dispatch=dispatch(),
                handlers=handlers,
                guards=built.guards,
                policy=choose_throughput,
                clock=WallClock(),
                activities=activities,
            )

        history_path = root / "history.jsonl"
        if history_path.exists():
            engine = load()
        else:
            seed = Seed(repository_id=authority.repository, pr_number=authority.pr_number)
            marking = Marking({NetPath("seed"): (Token("Seed", (seed).dump()),)})
            engine = Engine.create(
                built.net,
                instance_id,
                history=JsonlHistoryStore(history_path),
                dispatch=dispatch(),
                handlers=handlers,
                guards=built.guards,
                policy=choose_throughput,
                clock=WallClock(),
                activities=activities,
                marking=marking,
            )
            engine.open_scope(_GENERATION_SCOPE)
        lease.bind(engine)
        return cls(root, engine, lease, operations, load, agent_settle)

    @property
    def snapshot(self) -> ReadinessSnapshot | None:
        return self.lease.snapshot()

    @property
    def control(self) -> ReadinessSnapshot | None:
        return self.lease.control()

    @property
    def generation_scope(self) -> LifecycleScope | None:
        return self.engine.active_scopes.get(_GENERATION_SCOPE)

    def open_generation(self) -> LifecycleScope:
        return self.engine.open_scope(_GENERATION_SCOPE)

    def reset_generation(self) -> LifecycleScope:
        scope = self.generation_scope
        if scope is None:
            raise RuntimeError("readiness generation is not active")
        return self.engine.reset_scope(scope)

    def close_generation(self) -> None:
        scope = self.generation_scope
        if scope is None:
            raise RuntimeError("readiness generation is not active")
        self.engine.close_scope(scope)

    def place(self, path: str) -> tuple[dict, ...]:
        return tuple(token.data for token in self.engine.marking.place(NetPath(path)))

    def deliver(self, source: str, value, identity: str, *, scope: LifecycleScope | str | None = None):
        token = Token(type(value).__name__, (value).dump())
        return self.engine.deliver(source, token, identity=identity, scope=scope)

    def drain(self, limit: int = 500) -> DriveOutcome:
        self._settle_agent_routes()
        for _ in range(limit):
            before = tuple(self.engine.records)
            unresolved = self._unresolved(before)
            try:
                outcome = self.engine.advance()
                if not outcome.ready:
                    self._settle_agent_routes()
                    return outcome
                self._settle_agent_routes()
            except RuntimeError:
                replacement = self._loader()
                after = tuple(replacement.records)
                prefix_matches = after[: len(before)] == before
                suffix = after[len(before) :]
                failed = [record for record in suffix if isinstance(record, ActivityFailed)]
                firing_failed = [record for record in suffix if isinstance(record, FiringFailed)]
                request = unresolved.get(failed[0].occurrence) if len(failed) == 1 else None
                if (
                    not prefix_matches
                    or len(suffix) != 2
                    or not isinstance(suffix[0], ActivityFailed)
                    or not isinstance(suffix[1], FiringFailed)
                    or len(firing_failed) != 1
                    or request is None
                    or failed[0].occurrence != firing_failed[0].occurrence
                    or failed[0].transition != request.transition
                    or firing_failed[0].transition != request.transition
                ):
                    replacement.close()
                    raise
                previous = self.engine
                try:
                    self.lease.replace(previous, replacement)
                except Exception:
                    replacement.close()
                    raise
                self.engine = replacement
                self._settle_agent_routes()
        raise RuntimeError("PR-readiness Engine did not reach an external wait")

    def _settle_agent_routes(self) -> None:
        if self._agent_settle is None:
            return
        requested: dict[int, str] = {}
        for record in self.engine.records:
            if isinstance(record, ActivityRequested) and isinstance(record.input, dict):
                work = record.input.get("work", record.input.get("command"))
                operation = work.get("operation") if isinstance(work, dict) else None
                if isinstance(operation, str):
                    requested[record.occurrence] = operation
        terminal = _terminal_occurrences(self.engine.records)
        self._agent_settle({requested[item] for item in terminal & requested.keys()})

    @staticmethod
    def _unresolved(records: tuple[object, ...]) -> dict[int, ActivityRequested]:
        terminal = _terminal_occurrences(records)
        return {
            record.occurrence: record
            for record in records
            if isinstance(record, ActivityRequested) and record.occurrence not in terminal
        }

    def close(self) -> None:
        self.engine.close()

    def activity(self, name: str):
        definition = activity_definitions(self.operations).get(name)
        return definition

    def has_unresolved_publication(self) -> bool:
        """Return whether this Instance has an uncollected durable publication request."""
        terminal = _terminal_occurrences(self.engine.records)
        return any(
            isinstance(record, ActivityRequested)
            and record.occurrence not in terminal
            and record.activity in _DURABLE_ACTIVITIES
            for record in self.engine.records
        )


__all__ = [
    "AuthorityLease",
    "CompositeDispatch",
    "PrReadinessHost",
    "PublicationActivityHandler",
    "StaleAuthorityError",
    "WallClock",
]
