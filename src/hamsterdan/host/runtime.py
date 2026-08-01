"""Fresh-state Engine host and complete GitHub effect lease for PR readiness."""

from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from petrus.engine import Engine, choose_throughput
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.history import ActivityCompleted, ActivityFailed, ActivityRequested
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch

from hamsterdan.contracts.readiness import Control, Seed
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.readiness.net import ACTIVITY_TRANSITIONS, build_net

from .activities import PrReadinessActivities, activity_definitions


class StaleAuthorityError(RuntimeError):
    """An operation no longer has exact marking and GitHub authority."""


class WallClock:
    """Observe production timers without advancing beyond real wall time."""

    def now(self) -> float:
        return time.time()

    def observe(self, instant: float) -> float | None:
        now = self.now()
        return now if now >= instant else None


class AuthorityLease:
    """Join an Activity request to current marking and a fresh GitHub read."""

    def __init__(self, authority: GitHubAuthority):
        self.authority = authority
        self.engine: Engine | None = None

    def bind(self, engine: Engine) -> None:
        if self.engine is not None:
            raise RuntimeError("authority lease is already bound")
        self.engine = engine

    def control(self) -> Control | None:
        if self.engine is None:
            return None
        tokens = self.engine.marking.place(NetPath("current"))
        return Control(**tokens[0].data) if len(tokens) == 1 else None

    def is_current(self, epoch: int, head: str) -> bool:
        control = self.control()
        if control is None or control.provisional or (control.epoch, control.head) != (epoch, head):
            return False
        try:
            pull = self.authority.pull_request()
            if pull.closed or pull.merged or pull.draft or pull.head != head or pull.base != control.base_head:
                return False
            return self.authority.policy(pull.base_ref).digest == control.policy_digest
        except RuntimeError:
            return False

    def fence(self, epoch: int, head: str, operation: str, base_head: str, policy_digest: str) -> None:
        control = self.control()
        if control is None or (
            control.epoch,
            control.head,
            control.base_head,
            control.policy_digest,
        ) != (epoch, head, base_head, policy_digest):
            raise StaleAuthorityError("operation no longer matches current workflow authority")
        if control.provisional:
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
        terminal = {
            record.occurrence
            for record in self.engine.records
            if isinstance(record, (ActivityCompleted, ActivityFailed))
        }
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

    def __init__(self, root: Path, engine: Engine, lease: AuthorityLease, operations: PrReadinessActivities):
        self.root, self.engine, self.lease, self.operations = root, engine, lease, operations

    @classmethod
    def open(
        cls,
        root: Path,
        instance_id: str,
        authority: GitHubAuthority,
        operations_factory,
        *,
        reminder_delay: float = 3 * 24 * 60 * 60,
    ) -> PrReadinessHost:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        built = build_net(reminder_delay)
        lease = AuthorityLease(authority)
        operations = operations_factory(lease)
        definitions = activity_definitions(operations)
        handlers = cast(Any, dict(built.handlers))
        for path in ACTIVITY_TRANSITIONS:
            name = path.removeprefix("execute.")
            handlers[name] = DerivedActivityHandler(built.net, NetPath(path), definitions[name])
        history_path = root / "history.jsonl"
        exists = history_path.exists()
        history = JsonlHistoryStore(history_path)
        dispatch = InlineDispatch(definitions)
        activities = tuple(item.declaration for item in definitions.values())
        if exists:
            engine = Engine.load(
                built.net,
                instance_id,
                history=history,
                dispatch=dispatch,
                handlers=handlers,
                guards=built.guards,
                policy=choose_throughput,
                clock=WallClock(),
                activities=activities,
            )
        else:
            seed = Seed(authority.repository, authority.pr_number)
            marking = Marking({NetPath("seed"): (Token("Seed", asdict(seed)),)})
            engine = Engine.create(
                built.net,
                instance_id,
                history=history,
                dispatch=dispatch,
                handlers=handlers,
                guards=built.guards,
                policy=choose_throughput,
                clock=WallClock(),
                activities=activities,
                marking=marking,
            )
        lease.bind(engine)
        return cls(root, engine, lease, operations)

    @property
    def control(self) -> Control | None:
        return self.lease.control()

    def place(self, path: str) -> tuple[dict, ...]:
        return tuple(token.data for token in self.engine.marking.place(NetPath(path)))

    def deliver(self, source: str, value, identity: str):
        token = Token(type(value).__name__, asdict(value))
        return self.engine.deliver(source, token, identity=identity)

    def drain(self, limit: int = 500) -> None:
        for _ in range(limit):
            if not self.engine.advance().ready:
                return
        raise RuntimeError("PR-readiness Engine did not reach an external wait")

    def close(self) -> None:
        self.engine.close()


__all__ = ["AuthorityLease", "PrReadinessHost", "StaleAuthorityError", "WallClock"]
