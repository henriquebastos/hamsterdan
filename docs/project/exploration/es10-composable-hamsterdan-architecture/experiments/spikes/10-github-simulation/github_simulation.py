"""Isolated GitHub simulation module for ES-010 experiment 10.

The module mounts beneath the exact Timeline boundary fixed by experiment 9.
It drives the production GitHubAuthority and CommentPublisher interfaces over a
strict deterministic transport. No credential or installation authority enters
its commands, observations, faults, durable store, or replay artifact.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from runtime import ActionRef, Budget, Timeline

from hamsterdan.github_app.effects import CommentPublisher
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.github_app.models import GitHubBoundaryError, WireResponse

MODULE_NAME = "github"
REPOSITORY = "owner/repo"
PULL_REQUEST = 7
BOT_LOGIN = "hamsterdan[bot]"
COMMENTS_PATH = "/repos/owner/repo/issues/7/comments"
COMMENT_PAGES_PATH = f"{COMMENTS_PATH}?per_page=100"
PULL_PATH = "/repos/owner/repo/pulls/7"
BASE_REF_PATH = "/repos/owner/repo/git/ref/heads/main"

MAX_AUTHORITIES = 16
MAX_PENDING = 32
MAX_EFFECTS = 32
MAX_CALLS = 128
MAX_READS = 32
MAX_BODY_BYTES = 4_096
MAX_RETAINED_BYTES = 262_144

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_IDENTITY = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_POLICY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class AuthorityMoved(RuntimeError):
    pass


class GitHubSimulationContractError(ValueError):
    pass


@dataclass(frozen=True)
class _Authority:
    epoch: int
    head: str
    base: str
    policy: str


@dataclass(frozen=True)
class _AuthorityRead:
    request: str
    at_us: int


@dataclass(frozen=True)
class _Publication:
    request: str
    operation: str
    body: str
    authority: _Authority
    at_us: int


@dataclass
class _Store:
    authorities: list[_Authority] = field(default_factory=list)
    pending: dict[str, _AuthorityRead | _Publication] = field(default_factory=dict)
    outcomes: dict[str, dict[str, object]] = field(default_factory=dict)
    effects: list[dict[str, object]] = field(default_factory=list)
    reads: list[dict[str, object]] = field(default_factory=list)
    calls: list[dict[str, object]] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)


RESOURCE_LIMITS = {
    "github.authorities": MAX_AUTHORITIES,
    "github.pending": MAX_PENDING,
    "github.effects": MAX_EFFECTS,
    "github.calls": MAX_CALLS,
    "github.reads": MAX_READS,
    "github.retained_bytes": MAX_RETAINED_BYTES,
}

DEFAULT_BUDGET = Budget(
    operations=256,
    owner_steps=64,
    eligible_actions=32,
    leaf_calls=64,
    choice_draws=32,
    active_faults=16,
    generations=16,
    logical_time_us=1_000_000,
    journal_entries=1_024,
    artifact_bytes=1_000_000,
    resources=RESOURCE_LIMITS,
)


def _exact_object(value: object, fields: set[str], subject: str) -> dict[str, object]:
    expected = ", ".join(sorted(fields))
    if type(value) is not dict or set(cast(dict[object, object], value)) != fields:
        raise ValueError(f"{subject} payload must contain exactly: {expected}")
    return cast(dict[str, object], value)


def _identity(value: object, subject: str) -> str:
    if type(value) is not str or not _IDENTITY.fullmatch(value):
        raise ValueError(f"{subject} must be a normalized identity of at most 128 characters")
    return value


def _instant(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("at_us must be a non-negative integer")
    return value


def _authority(value: object) -> _Authority:
    data = _exact_object(value, {"epoch", "head", "base", "policy"}, "authority.set")
    epoch, head, base, policy = data["epoch"], data["head"], data["base"], data["policy"]
    if type(epoch) is not int or epoch <= 0:
        raise ValueError("authority epoch must be a positive integer")
    if type(head) is not str or not _SHA.fullmatch(head):
        raise ValueError("authority head must be an exact lowercase commit SHA")
    if type(base) is not str or not _SHA.fullmatch(base):
        raise ValueError("authority base must be an exact lowercase commit SHA")
    if type(policy) is not str or not _POLICY.fullmatch(policy):
        raise ValueError("authority policy must be a normalized identity of at most 128 characters")
    return _Authority(epoch, head, base, policy)


def _authority_value(value: _Authority) -> dict[str, object]:
    return {"epoch": value.epoch, "head": value.head, "base": value.base, "policy": value.policy}


def _work_value(work: _AuthorityRead | _Publication) -> dict[str, object]:
    if isinstance(work, _AuthorityRead):
        return {"kind": "authority_read", "request": work.request, "at_us": work.at_us}
    return {
        "kind": "publication",
        "request": work.request,
        "operation": work.operation,
        "body": work.body,
        "authority": _authority_value(work.authority),
        "at_us": work.at_us,
    }


def _state(store: _Store) -> dict[str, object]:
    current = store.authorities[-1] if store.authorities else None
    return {
        "authority": None if current is None else _authority_value(current),
        "authorities": [_authority_value(value) for value in store.authorities],
        "pending": [_work_value(store.pending[key]) for key in sorted(store.pending)],
        "outcomes": [dict(store.outcomes[key]) for key in sorted(store.outcomes)],
        "effects": [dict(effect) for effect in store.effects],
        "reads": [dict(read) for read in store.reads],
        "calls": [dict(call) for call in store.calls],
        "collisions": list(store.collisions),
    }


class GitHubSimulation:
    name = MODULE_NAME

    def __init__(self) -> None:
        self.store = _Store()

    def open(self, _context: object) -> _Generation:
        return _Generation(self.store)

    def drop(self, _generation: _Generation) -> None:
        pass

    def close(self, _generation: _Generation) -> None:
        pass

    def resource_usage(self, _generation: _Generation | None) -> dict[str, int]:
        retained = json.dumps(_state(self.store), allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
        return {
            "github.authorities": len(self.store.authorities),
            "github.pending": len(self.store.pending),
            "github.effects": len(self.store.effects),
            "github.calls": len(self.store.calls),
            "github.reads": len(self.store.reads),
            "github.retained_bytes": len(retained),
        }

    def state(self) -> dict[str, object]:
        return _state(self.store)


class _Generation:
    def __init__(self, store: _Store) -> None:
        self.store = store

    def command(self, name: str, payload: object, context: Any) -> object:
        if name == "authority.set":
            return self._set_authority(payload)
        if name == "authority.read":
            return self._schedule_read(payload, context.now_us)
        if name == "publication.request":
            return self._schedule_publication(payload, context.now_us)
        raise ValueError(f"unknown GitHub simulation command: {name}")

    def observe(self, name: str, payload: object, _context: object) -> object:
        if name != "state":
            raise ValueError(f"unknown GitHub simulation observation: {name}")
        if payload is not None and payload != {}:
            raise ValueError("state observation accepts no payload")
        return _state(self.store)

    def eligible_actions(self, _context: object) -> tuple[ActionRef, ...]:
        return tuple(
            ActionRef(
                module=MODULE_NAME,
                name="read" if isinstance(work, _AuthorityRead) else "publish",
                identity=request,
                eligible_at_us=work.at_us,
            )
            for request, work in sorted(self.store.pending.items())
        )

    async def step(self, action: ActionRef, context: Any) -> object:
        work = self.store.pending.get(action.identity)
        if work is None:
            raise ValueError(f"GitHub action has no pending request: {action.identity}")
        expected = "read" if isinstance(work, _AuthorityRead) else "publish"
        if action.module != MODULE_NAME or action.name != expected:
            raise ValueError(f"GitHub action does not match pending request: {action.identity}")
        if isinstance(work, _AuthorityRead):
            outcome = await self._read(work, context)
        else:
            outcome = await self._publish(work, context)
        self.store.outcomes[action.identity] = outcome
        del self.store.pending[action.identity]
        return outcome

    def _set_authority(self, payload: object) -> object:
        value = _authority(payload)
        current = self.store.authorities[-1] if self.store.authorities else None
        if current == value:
            return {"version": len(self.store.authorities), "existing": True, **_authority_value(value)}
        if current is not None and value.epoch <= current.epoch:
            raise ValueError("authority movement must increase its epoch")
        if len(self.store.authorities) >= MAX_AUTHORITIES:
            raise ValueError(f"GitHub authority bound exhausted at {MAX_AUTHORITIES}")
        self.store.authorities.append(value)
        return {"version": len(self.store.authorities), "existing": False, **_authority_value(value)}

    def _schedule_read(self, payload: object, now_us: int) -> object:
        data = _exact_object(payload, {"request", "at_us"}, "authority.read")
        request = _identity(data["request"], "authority read request")
        at_us = _instant(data["at_us"])
        self._require_schedule(request, at_us, now_us)
        work = _AuthorityRead(request, at_us)
        self.store.pending[request] = work
        return _work_value(work)

    def _schedule_publication(self, payload: object, now_us: int) -> object:
        data = _exact_object(
            payload,
            {"request", "operation", "body", "authority", "at_us"},
            "publication.request",
        )
        request = _identity(data["request"], "publication request")
        operation = _identity(data["operation"], "publication operation")
        body = data["body"]
        if type(body) is not str or not body or len(body.encode()) > MAX_BODY_BYTES:
            raise ValueError(f"publication body must contain 1 through {MAX_BODY_BYTES} UTF-8 bytes")
        at_us = _instant(data["at_us"])
        self._require_schedule(request, at_us, now_us)
        work = _Publication(request, operation, body, _authority(data["authority"]), at_us)
        self.store.pending[request] = work
        return _work_value(work)

    def _require_schedule(self, request: str, at_us: int, now_us: int) -> None:
        if at_us < now_us:
            raise ValueError("GitHub work cannot be scheduled in the logical past")
        if request in self.store.pending or request in self.store.outcomes:
            raise ValueError(f"GitHub request identity was reused: {request}")
        if len(self.store.pending) >= MAX_PENDING:
            raise ValueError(f"GitHub pending-work bound exhausted at {MAX_PENDING}")

    async def _read(self, work: _AuthorityRead, context: Any) -> dict[str, object]:
        try:
            result = await context.call(
                "authority.read",
                {"request": work.request},
                lambda: self._read_now(work, context),
            )
        except GitHubBoundaryError:
            return {
                "kind": "authority_read",
                "request": work.request,
                "status": "boundary_failure",
                "error": "GitHubBoundaryError",
            }
        return cast(dict[str, object], result)

    def _read_now(self, work: _AuthorityRead, context: Any) -> dict[str, object]:
        outcome = _read_fault(context.faults("read.response"))
        transport = _Transport(self.store, context, work, outcome)
        snapshot = GitHubAuthority(transport, REPOSITORY, PULL_REQUEST).pull_request()
        return {
            "kind": "authority_read",
            "request": work.request,
            "status": "returned",
            "head": snapshot.head,
            "base": snapshot.base,
        }

    async def _publish(self, work: _Publication, context: Any) -> dict[str, object]:
        try:
            result = await context.call(
                "publication.apply",
                {"request": work.request, "operation": work.operation},
                lambda: self._publish_now(work, context),
            )
        except AuthorityMoved:
            return {
                "kind": "publication",
                "request": work.request,
                "operation": work.operation,
                "status": "authority_moved",
            }
        except GitHubBoundaryError:
            return {
                "kind": "publication",
                "request": work.request,
                "operation": work.operation,
                "status": "boundary_failure",
                "error": "GitHubBoundaryError",
            }
        except ValueError as error:
            if error.args != ("stable publication operation collided with a different payload",):
                raise
            self.store.collisions.append(work.operation)
            return {
                "kind": "publication",
                "request": work.request,
                "operation": work.operation,
                "status": "identity_collision",
            }
        return cast(dict[str, object], result)

    def _publish_now(self, work: _Publication, context: Any) -> dict[str, object]:
        authored_authority = _authority_value(work.authority)
        if any(
            effect["operation"] == work.operation and effect["authority"] != authored_authority
            for effect in self.store.effects
        ):
            self.store.collisions.append(work.operation)
            return {
                "kind": "publication",
                "request": work.request,
                "operation": work.operation,
                "status": "identity_collision",
            }
        transport = _Transport(self.store, context, work, None)
        publisher = CommentPublisher(
            transport,
            REPOSITORY,
            PULL_REQUEST,
            BOT_LOGIN,
            lambda repository, pr_number, epoch, head, operation: self._fence(
                work,
                repository,
                pr_number,
                epoch,
                head,
                operation,
            ),
        )
        result = publisher.immutable(
            "readiness",
            work.operation,
            work.authority.epoch,
            work.authority.head,
            work.body,
        )
        return {
            "kind": "publication",
            "request": work.request,
            "operation": work.operation,
            "status": result.status,
        }

    def _fence(
        self,
        work: _Publication,
        repository: str,
        pr_number: int,
        epoch: int,
        head: str,
        operation: str,
    ) -> None:
        if (repository, pr_number, epoch, head, operation) != (
            REPOSITORY,
            PULL_REQUEST,
            work.authority.epoch,
            work.authority.head,
            work.operation,
        ):
            raise AssertionError("production publication called its fence with changed identity")
        current = self.store.authorities[-1] if self.store.authorities else None
        allowed = current == work.authority
        _append_call(
            self.store,
            {
                "kind": "fence",
                "request": work.request,
                "operation": work.operation,
                "authority_version": _authority_version(self.store, current),
                "allowed": allowed,
            },
        )
        if not allowed:
            raise AuthorityMoved("publication authority moved immediately before the provider effect")


class _Transport:
    def __init__(
        self,
        store: _Store,
        context: Any,
        work: _AuthorityRead | _Publication,
        read_outcome: str | None,
    ) -> None:
        self.store = store
        self.context = context
        self.work = work
        self.read_outcome = read_outcome
        self.selected_authority: _Authority | None = None

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> WireResponse:
        if isinstance(self.work, _AuthorityRead) and method == "GET" and path == PULL_PATH and body is None:
            return self._pull_response()
        if isinstance(self.work, _AuthorityRead) and method == "GET" and path == BASE_REF_PATH and body is None:
            return self._base_response()
        if isinstance(self.work, _Publication) and method == "POST" and path == COMMENTS_PATH:
            return self._publication_response(body)
        raise AssertionError(f"undeclared modeled GitHub request: {method} {path}")

    def pages(self, path: str) -> tuple[dict[str, Any], ...]:
        if not isinstance(self.work, _Publication) or path != COMMENT_PAGES_PATH:
            raise AssertionError(f"undeclared modeled GitHub pages request: {path}")
        _append_call(
            self.store,
            {"kind": "pages", "request": self.work.request, "operation": self.work.operation},
        )
        for effect in self.store.effects:
            if effect["operation"] == self.work.operation and effect["visible"] is False:
                effect["visible"] = True
        return tuple(
            {
                "id": effect["id"],
                "html_url": f"https://example.test/comments/{effect['id']}",
                "body": effect["body"],
                "user": {"login": BOT_LOGIN},
            }
            for effect in self.store.effects
            if effect["visible"] is True
        )

    def _pull_response(self) -> WireResponse:
        if self.read_outcome == "stale" and len(self.store.authorities) < 2:
            raise GitHubSimulationContractError(
                "stale read.response requires prior and current authority versions; "
                "set two authority versions before stepping"
            )
        current = self._current_authority()
        if len(self.store.reads) >= MAX_READS:
            raise ValueError(f"GitHub read bound exhausted at {MAX_READS}")
        if self.read_outcome == "rate_limited":
            self.store.reads.append(
                {
                    "request": self.work.request,
                    "provider_version": len(self.store.authorities),
                    "returned_version": None,
                    "status": 429,
                }
            )
            _append_call(self.store, {"kind": "get", "request": self.work.request, "path": PULL_PATH, "status": 429})
            return WireResponse(429, {})
        selected = self.store.authorities[-2] if self.read_outcome == "stale" else current
        self.selected_authority = selected
        self.store.reads.append(
            {
                "request": self.work.request,
                "provider_version": len(self.store.authorities),
                "returned_version": _authority_version(self.store, selected),
                "status": 200,
            }
        )
        _append_call(self.store, {"kind": "get", "request": self.work.request, "path": PULL_PATH, "status": 200})
        return WireResponse(
            200,
            {
                "state": "open",
                "draft": False,
                "mergeable": True,
                "mergeable_state": "clean",
                "merged": False,
                "html_url": "https://example.test/owner/repo/pull/7",
                "user": {"login": "author"},
                "head": {"sha": selected.head, "ref": "feature", "repo": {"full_name": REPOSITORY}},
                "base": {"sha": selected.base, "ref": "main"},
            },
        )

    def _base_response(self) -> WireResponse:
        if self.selected_authority is None:
            raise AssertionError("base ref was read before pull authority")
        _append_call(self.store, {"kind": "get", "request": self.work.request, "path": BASE_REF_PATH, "status": 200})
        return WireResponse(200, {"object": {"sha": self.selected_authority.base}})

    def _publication_response(self, body: Mapping[str, Any] | None) -> WireResponse:
        work = cast(_Publication, self.work)
        expected_marker = CommentPublisher.marker("readiness", work.operation, work.authority.head)
        expected_body = f"{work.body}\n\n{expected_marker}"
        if body is None or set(body) != {"body"} or body.get("body") != expected_body:
            raise AssertionError("production publication sent an undeclared provider payload")
        if len(self.store.effects) >= MAX_EFFECTS:
            raise ValueError(f"GitHub effect bound exhausted at {MAX_EFFECTS}")
        fault = _publication_fault(self.context.faults("publication.acceptance"), self.context)
        current = self._current_authority()
        visible, response = fault if fault is not None else (True, "returned")
        _append_call(
            self.store,
            {
                "kind": "post",
                "request": work.request,
                "operation": work.operation,
                "provider_version": len(self.store.authorities),
            },
        )
        identifier = len(self.store.effects) + 1
        self.store.effects.append(
            {
                "id": identifier,
                "request": work.request,
                "operation": work.operation,
                "body": expected_body,
                "authority": _authority_value(work.authority),
                "provider_authority": _authority_value(current),
                "provider_version": len(self.store.authorities),
                "accepted_visible": visible,
                "visible": visible,
                "response": response,
            }
        )
        if response == "lost":
            raise GitHubBoundaryError("modeled GitHub effect was accepted without a response")
        return WireResponse(
            201,
            {
                "id": identifier,
                "html_url": f"https://example.test/comments/{identifier}",
                "body": expected_body,
                "user": {"login": BOT_LOGIN},
            },
        )

    def _current_authority(self) -> _Authority:
        if not self.store.authorities:
            raise GitHubBoundaryError("modeled GitHub authority is unavailable")
        return self.store.authorities[-1]


def _append_call(store: _Store, value: dict[str, object]) -> None:
    if len(store.calls) >= MAX_CALLS:
        raise ValueError(f"GitHub provider-call bound exhausted at {MAX_CALLS}")
    store.calls.append({"sequence": len(store.calls) + 1, **value})


def _authority_version(store: _Store, authority: _Authority | None) -> int | None:
    if authority is None:
        return None
    return next(index for index, value in enumerate(store.authorities, start=1) if value == authority)


def _read_fault(faults: tuple[object, ...]) -> str | None:
    if not faults:
        return None
    if len(faults) != 1:
        raise ValueError("one authority read can consume at most one read.response fault")
    payload = cast(Any, faults[0]).payload
    data = _exact_object(payload, {"outcome"}, "read.response fault")
    outcome = data["outcome"]
    if outcome not in {"stale", "rate_limited"}:
        raise ValueError("read.response fault outcome must be 'stale' or 'rate_limited'")
    return cast(str, outcome)


def _publication_fault(faults: tuple[object, ...], context: Any) -> tuple[bool, str] | None:
    if not faults:
        return None
    if len(faults) != 1:
        raise ValueError("one publication can consume at most one publication.acceptance fault")
    payload = cast(Any, faults[0]).payload
    data = _exact_object(payload, {"visibility", "response"}, "publication.acceptance fault")
    visibility, response = data["visibility"], data["response"]
    if visibility not in {"visible", "hidden", "generated"}:
        raise ValueError("publication visibility must be 'visible', 'hidden', or 'generated'")
    if response not in {"returned", "lost"}:
        raise ValueError("publication response must be 'returned' or 'lost'")
    if visibility == "generated":
        visibility = context.choose("effect_visibility", ("visible", "hidden"))
    return visibility == "visible", cast(str, response)


def github_fault(
    timeline: Timeline,
    point: str,
    payload: object,
    *,
    occurrence: int = 1,
) -> object:
    fields = {
        "read.response": {"outcome"},
        "publication.acceptance": {"visibility", "response"},
    }
    if point not in fields:
        raise ValueError(f"unknown GitHub simulation fault: {point}")
    _exact_object(payload, fields[point], f"{point} fault")
    return timeline.fault(MODULE_NAME, point, occurrence=occurrence, payload=payload)


class GitHubChecker:
    """Derive provider safety from raw reads, calls, and accepted effects."""

    def check(self, state: object) -> tuple[str, ...]:
        data = _exact_object(
            state,
            {"authority", "authorities", "pending", "outcomes", "effects", "reads", "calls", "collisions"},
            "GitHub checker state",
        )
        effects = cast(list[dict[str, object]], data["effects"])
        reads = cast(list[dict[str, object]], data["reads"])
        calls = cast(list[dict[str, object]], data["calls"])
        violations = set()
        identities: dict[str, set[tuple[str, str]]] = {}
        for effect in effects:
            operation = cast(str, effect["operation"])
            identity = (
                cast(str, effect["body"]),
                json.dumps(effect["authority"], allow_nan=False, separators=(",", ":"), sort_keys=True),
            )
            identities.setdefault(operation, set()).add(identity)
        violations.update(
            f"effect_identity_collision:{operation}" for operation, values in identities.items() if len(values) > 1
        )
        violations.update(
            f"stale_effect_authority:{effect['operation']}"
            for effect in effects
            if effect["authority"] != effect["provider_authority"]
        )
        violations.update(
            f"stale_authority_read:{read['request']}"
            for read in reads
            if read["status"] == 200 and read["returned_version"] != read["provider_version"]
        )
        for index, call in enumerate(calls):
            if call["kind"] != "post":
                continue
            preceding = calls[index - 1] if index else {}
            if (
                preceding.get("kind") != "fence"
                or preceding.get("request") != call["request"]
                or preceding.get("operation") != call["operation"]
                or preceding.get("allowed") is not True
                or preceding.get("authority_version") != call["provider_version"]
            ):
                violations.add(f"effect_without_current_fence:{call['operation']}")
        return tuple(sorted(violations))
