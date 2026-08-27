"""Isolated host simulation candidate for ES-010 experiment 10.

The module mounts on the exact Timeline contract fixed by experiment 9. It
models only trusted host supervision and injects a strict deterministic
readiness lifecycle. It does not construct workflow, Petrus, GitHub, agents, or
the maintained Hamsterdan host.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, cast

from runtime import ActionRef, Artifact, Budget, Timeline

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
FAULT_PAYLOADS = {
    "readiness.progress.unavailable": {"subject"},
    "readiness.progress.after_commit": {"response_lost", "subject"},
}


class HostSimulationError(RuntimeError):
    pass


class HostCommandError(HostSimulationError):
    pass


class HostObservationError(HostSimulationError):
    pass


class HostFaultError(HostSimulationError):
    pass


class HostInputError(HostSimulationError):
    pass


class HostCheckFailed(HostSimulationError):
    pass


class ReadinessAdapterError(HostSimulationError):
    pass


class ReadinessUnavailable(ReadinessAdapterError):
    pass


class ReadinessResponseLost(ReadinessAdapterError):
    pass


class ReadinessCloseFailed(ReadinessAdapterError):
    pass


def _payload(value: object, keys: set[str], subject: str) -> dict[str, object]:
    expected = ", ".join(sorted(keys))
    if type(value) is not dict or set(value) != keys:
        raise HostInputError(f"{subject} payload must contain exactly: {expected}")
    return cast(dict[str, object], value)


def _identifier(value: object, subject: str) -> str:
    if type(value) is not str or len(value.encode()) > 256 or not NAME.fullmatch(value):
        raise HostInputError(f"{subject} must be a normalized identifier of at most 256 bytes")
    return value


def _instant(value: object, subject: str = "at_us") -> int:
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise HostInputError(f"{subject} must be a non-negative integer")
    return value


def _flag(value: object, subject: str) -> bool:
    if type(value) is not bool:
        raise HostInputError(f"{subject} must be a boolean")
    return value


@dataclass
class RouteState:
    generation: int = 1
    status: str = "active"


@dataclass
class SubjectState:
    route: str
    custody_generation: int = 1
    due_at_us: int | None = None
    enqueue_sequence: int | None = None
    reason: str | None = None
    retry_operation: str | None = None
    last_result: dict[str, object] | None = None


@dataclass
class TurnState:
    identity: str
    subject: str
    reason: str
    phase: str = "selected"
    result: dict[str, object] | None = None


@dataclass
class ReadinessState:
    route: str
    operations: dict[str, dict[str, object]] = field(default_factory=dict)
    progressed: int = 0
    blocked: int = 0
    lookups: int = 0
    opens: int = 0
    last_route_generation: int = 0
    evidence: list[dict[str, object]] = field(default_factory=list)
    close_failure: bool = False


@dataclass
class HostStore:
    routes: dict[str, RouteState] = field(default_factory=dict)
    subjects: dict[str, SubjectState] = field(default_factory=dict)
    readiness: dict[str, ReadinessState] = field(default_factory=dict)
    selected: TurnState | None = None
    next_enqueue_sequence: int = 1
    next_turn_sequence: int = 1
    stopping: bool = False
    service_order: list[str] = field(default_factory=list)
    cleanup_attempts: list[dict[str, object]] = field(default_factory=list)
    cleanup_errors: list[dict[str, object]] = field(default_factory=list)


def _subject(store: HostStore, value: object) -> tuple[str, SubjectState]:
    subject = _identifier(value, "subject")
    try:
        return subject, store.subjects[subject]
    except KeyError:
        raise HostInputError(f"unknown host subject {subject!r}") from None


def _route(store: HostStore, value: object) -> tuple[str, RouteState]:
    route = _identifier(value, "route")
    try:
        return route, store.routes[route]
    except KeyError:
        raise HostInputError(f"unknown host route {route!r}") from None


def _wake(store: HostStore, subject: str, reason: str, at_us: int) -> None:
    state = store.subjects[subject]
    if state.due_at_us is None:
        state.due_at_us = at_us
        state.enqueue_sequence = store.next_enqueue_sequence
        state.reason = reason
        store.next_enqueue_sequence += 1
        return
    if at_us < state.due_at_us:
        state.due_at_us = at_us
        state.reason = reason


def _evidence(store: HostStore, subject: str) -> dict[str, object]:
    instance = store.subjects[subject]
    route = store.routes[instance.route]
    return {
        "route_generation": route.generation,
        "route_status": route.status,
        "custody_generation": instance.custody_generation,
    }


def _cut(
    kind: str,
    *,
    subject: str | None,
    identity: str,
    generation: int,
    **values: object,
) -> dict[str, object]:
    return {
        "owner": "host",
        "kind": kind,
        "subject": subject,
        "identity": identity,
        "generation": generation,
        **values,
    }


def _matching_fault(context: Any, point: str, subject: str) -> bool:
    matches = context.faults(point)
    if not matches:
        return False
    if len(matches) != 1:
        raise HostFaultError(f"host fault point {point!r} matched more than one occurrence")
    expected = FAULT_PAYLOADS[point]
    payload = _payload(matches[0].payload, expected, point)
    if payload["subject"] != subject:
        raise HostFaultError(
            f"host fault point {point!r} expected subject {payload['subject']!r}, observed {subject!r}"
        )
    if point == "readiness.progress.after_commit" and payload["response_lost"] is not True:
        raise HostFaultError("readiness.progress.after_commit requires response_lost=true")
    return True


class HostLifecycleView:
    def __init__(self, store: HostStore) -> None:
        self.store = store

    def observe(self, subject: str) -> dict[str, object]:
        _subject(self.store, subject)
        return _evidence(self.store, subject)


class StrictReadinessLifecycle:
    def __init__(self, subject: str, state: ReadinessState) -> None:
        self.subject = subject
        self.state = state

    def progress(
        self,
        reason: str,
        lifecycle_evidence: dict[str, object],
        *,
        operation: str,
        context: Any,
    ) -> dict[str, object]:
        if reason != "runnable":
            raise HostInputError(f"unknown readiness progress reason {reason!r}")
        if set(lifecycle_evidence) != {"custody_generation", "route_generation", "route_status"}:
            raise HostInputError("readiness lifecycle evidence has an unknown shape")
        route_generation = _instant(lifecycle_evidence["route_generation"], "route_generation")
        route_status = lifecycle_evidence["route_status"]
        if route_status not in {"active", "revoked"}:
            raise HostInputError(f"unknown readiness route status {route_status!r}")
        if route_generation < self.state.last_route_generation:
            raise HostInputError("readiness lifecycle evidence moved backward")
        self.state.last_route_generation = route_generation
        self.state.evidence.append(
            {
                "custody_generation": lifecycle_evidence["custody_generation"],
                "operation": operation,
                "route_generation": route_generation,
                "route_status": route_status,
            }
        )
        if operation in self.state.operations:
            self.state.lookups += 1
            return {**self.state.operations[operation], "source": "lookup"}
        if _matching_fault(context, "readiness.progress.unavailable", self.subject):
            raise ReadinessUnavailable(f"readiness is unavailable for {self.subject}")
        result: dict[str, object]
        if route_status == "revoked":
            result = {
                "disposition": "waiting",
                "posture": "route_revoked",
                "eligible_at_us": None,
                "route_generation": route_generation,
                "source": "lifecycle",
            }
            self.state.blocked += 1
        else:
            result = {
                "disposition": "progressed",
                "posture": "quiescent",
                "eligible_at_us": None,
                "route_generation": route_generation,
                "source": "lifecycle",
            }
            self.state.progressed += 1
        self.state.operations[operation] = result
        if _matching_fault(context, "readiness.progress.after_commit", self.subject):
            raise ReadinessResponseLost(f"readiness response was lost after {operation}")
        return dict(result)

    def close(self, mode: str) -> None:
        if mode not in {"abort", "graceful", "release"}:
            raise HostInputError(f"unknown readiness close mode {mode!r}")
        if self.state.close_failure:
            raise ReadinessCloseFailed(f"readiness close failed for {self.subject}")


class StrictReadinessFactory:
    def __init__(self, store: HostStore) -> None:
        self.store = store

    def open(self, subject: str, lifecycle_view: HostLifecycleView) -> StrictReadinessLifecycle:
        instance, state = _subject(self.store, subject)
        evidence = lifecycle_view.observe(instance)
        if set(evidence) != {"custody_generation", "route_generation", "route_status"}:
            raise HostInputError("host lifecycle view returned an unknown shape")
        readiness = self.store.readiness[instance]
        if readiness.route != state.route:
            raise HostInputError(f"readiness binding for {instance!r} does not match route {state.route!r}")
        readiness.opens += 1
        return StrictReadinessLifecycle(instance, readiness)


class HostSimulation:
    name = "host"

    def __init__(self) -> None:
        self.store = HostStore()
        self.factory = StrictReadinessFactory(self.store)

    def open(self, _context: object) -> HostGeneration:
        return HostGeneration(self.store, self.factory)

    def drop(self, generation: HostGeneration) -> None:
        generation.release_all("abort")

    def close(self, generation: HostGeneration) -> None:
        generation.release_all("release")

    def resource_usage(self, generation: HostGeneration | None) -> dict[str, int]:
        loaded = 0 if generation is None else len(generation.lifecycles)
        return {
            "host.cleanup_errors": len(self.store.cleanup_errors),
            "host.instances": len(self.store.subjects),
            "host.loaded": loaded,
            "host.readiness_operations": sum(len(state.operations) for state in self.store.readiness.values()),
            "host.routes": len(self.store.routes),
            "host.runnable": sum(state.due_at_us is not None for state in self.store.subjects.values()),
        }

    def arm_fault(
        self,
        timeline: Timeline,
        point: str,
        *,
        occurrence: int = 1,
        payload: object = None,
    ) -> object:
        if point not in FAULT_PAYLOADS:
            raise HostFaultError(f"unknown host fault point {point!r}")
        values = _payload(payload, FAULT_PAYLOADS[point], point)
        subject, _state = _subject(self.store, values["subject"])
        if point == "readiness.progress.after_commit":
            _flag(values["response_lost"], "response_lost")
        return timeline.fault(self.name, point, occurrence=occurrence, payload={**values, "subject": subject})


class HostGeneration:
    def __init__(self, store: HostStore, factory: StrictReadinessFactory) -> None:
        self.store = store
        self.factory = factory
        self.lifecycle_view = HostLifecycleView(store)
        self.lifecycles: dict[str, StrictReadinessLifecycle] = {}

    def command(self, name: str, payload: object, context: Any) -> object:
        try:
            handler = COMMANDS[name]
        except KeyError:
            raise HostCommandError(f"unknown host command {name!r}") from None
        return handler(self, payload, context)

    def observe(self, name: str, payload: object, _context: object) -> object:
        try:
            handler = OBSERVATIONS[name]
        except KeyError:
            raise HostObservationError(f"unknown host observation {name!r}") from None
        return handler(self, payload)

    def eligible_actions(self, context: Any) -> tuple[ActionRef, ...]:
        if self.store.stopping:
            if not self.lifecycles:
                return ()
            subject = min(self.lifecycles)
            return (ActionRef("host", "instance_closed", subject, context.now_us),)
        selected = self.store.selected
        if selected is not None:
            if selected.phase == "selected" and selected.subject not in self.lifecycles:
                return (ActionRef("host", "instance_opened", selected.subject, context.now_us),)
            actions = {
                "selected": "readiness_step_returned",
                "returned": "posture_recorded",
                "recorded": "subject_requeued",
            }
            try:
                name = actions[selected.phase]
            except KeyError:
                raise HostSimulationError(f"unknown selected-turn phase {selected.phase!r}") from None
            return (ActionRef("host", name, selected.identity, context.now_us),)
        due = [
            (state.due_at_us, state.enqueue_sequence, subject)
            for subject, state in self.store.subjects.items()
            if state.due_at_us is not None
        ]
        if not due:
            return ()
        due_at_us, _sequence, subject = min(due)
        if due_at_us is None:
            raise AssertionError("due subject has no due instant")
        return (ActionRef("host", "subject_selected", subject, due_at_us),)

    async def step(self, action: ActionRef, context: Any) -> object:
        expected = self.eligible_actions(context)
        if expected != (action,):
            raise HostSimulationError(f"host action is not the one durable authority selected: {action!r}")
        return await ACTIONS[action.name](self, action, context)

    def release(self, subject: str, mode: str) -> str:
        lifecycle = self.lifecycles.pop(subject)
        self.store.cleanup_attempts.append({"mode": mode, "subject": subject})
        try:
            lifecycle.close(mode)
        except ReadinessCloseFailed as error:
            self.store.cleanup_errors.append({"error_class": type(error).__name__, "subject": subject})
            return "failed"
        return "closed"

    def release_all(self, mode: str) -> None:
        for subject in sorted(self.lifecycles):
            self.release(subject, mode)


def command_register_route(generation: HostGeneration, payload: object, _context: Any) -> object:
    values = _payload(payload, {"route"}, "register_route")
    route = _identifier(values["route"], "route")
    existing = route in generation.store.routes
    if not existing:
        generation.store.routes[route] = RouteState()
    return {"existing": existing, "generation": generation.store.routes[route].generation, "route": route}


def command_register_instance(generation: HostGeneration, payload: object, _context: Any) -> object:
    values = _payload(payload, {"route", "subject"}, "register_instance")
    route, route_state = _route(generation.store, values["route"])
    if route_state.status != "active":
        raise HostInputError(f"cannot register a new instance on revoked route {route!r}")
    subject = _identifier(values["subject"], "subject")
    existing = generation.store.subjects.get(subject)
    if existing is not None and existing.route != route:
        raise HostInputError(f"host subject {subject!r} is already bound to route {existing.route!r}")
    if existing is None:
        generation.store.subjects[subject] = SubjectState(route)
        generation.store.readiness[subject] = ReadinessState(route)
    return {"existing": existing is not None, "route": route, "subject": subject}


def command_wake(generation: HostGeneration, payload: object, _context: Any) -> object:
    if generation.store.stopping:
        raise HostInputError("cannot wake a host instance after stop")
    values = _payload(payload, {"at_us", "reason", "subject"}, "wake")
    subject, _state = _subject(generation.store, values["subject"])
    reason = _identifier(values["reason"], "wake reason")
    at_us = _instant(values["at_us"])
    _wake(generation.store, subject, reason, at_us)
    state = generation.store.subjects[subject]
    return {
        "at_us": state.due_at_us,
        "enqueue_sequence": state.enqueue_sequence,
        "reason": state.reason,
        "subject": subject,
    }


def command_revoke_route(generation: HostGeneration, payload: object, context: Any) -> object:
    values = _payload(payload, {"route"}, "revoke_route")
    route, state = _route(generation.store, values["route"])
    changed = state.status != "revoked"
    if changed:
        state.status = "revoked"
        state.generation += 1
        for subject in sorted(generation.store.subjects):
            if generation.store.subjects[subject].route == route:
                _wake(generation.store, subject, "route_revoked", context.now_us)
    return {"changed": changed, "generation": state.generation, "route": route, "status": state.status}


def command_readiness_close_failure(generation: HostGeneration, payload: object, _context: Any) -> object:
    values = _payload(payload, {"enabled", "subject"}, "readiness_close_failure")
    subject, _state = _subject(generation.store, values["subject"])
    enabled = _flag(values["enabled"], "enabled")
    generation.store.readiness[subject].close_failure = enabled
    return {"enabled": enabled, "subject": subject}


def command_stop(generation: HostGeneration, payload: object, _context: Any) -> object:
    _payload(payload, set(), "stop")
    if generation.store.selected is not None:
        raise HostInputError("finish the selected host turn before stop")
    generation.store.stopping = True
    return {"stopping": True}


def observation_state(generation: HostGeneration, payload: object) -> object:
    if payload not in (None, {}):
        raise HostInputError("state observation accepts no payload")
    return {
        "cleanup": {
            "attempts": list(generation.store.cleanup_attempts),
            "errors": list(generation.store.cleanup_errors),
        },
        "loaded": sorted(generation.lifecycles),
        "readiness": {
            subject: {
                "blocked": state.blocked,
                "evidence": list(state.evidence),
                "lookups": state.lookups,
                "opens": state.opens,
                "operations": len(state.operations),
                "progressed": state.progressed,
            }
            for subject, state in sorted(generation.store.readiness.items())
        },
        "routes": {
            route: {"generation": state.generation, "status": state.status}
            for route, state in sorted(generation.store.routes.items())
        },
        "selected": None
        if generation.store.selected is None
        else {
            "identity": generation.store.selected.identity,
            "phase": generation.store.selected.phase,
            "subject": generation.store.selected.subject,
        },
        "service_order": list(generation.store.service_order),
        "stopping": generation.store.stopping,
        "subjects": {
            subject: {
                "custody_generation": state.custody_generation,
                "due_at_us": state.due_at_us,
                "enqueue_sequence": state.enqueue_sequence,
                "last_result": state.last_result,
                "reason": state.reason,
                "route": state.route,
            }
            for subject, state in sorted(generation.store.subjects.items())
        },
    }


def observation_instance(generation: HostGeneration, payload: object) -> object:
    values = _payload(payload, {"subject"}, "instance")
    subject, state = _subject(generation.store, values["subject"])
    return {
        "custody_generation": state.custody_generation,
        "last_result": state.last_result,
        "route": state.route,
        "subject": subject,
    }


async def action_subject_selected(generation: HostGeneration, action: ActionRef, context: Any) -> object:
    subject, state = _subject(generation.store, action.identity)
    if state.reason is None:
        raise HostSimulationError(f"due subject {subject!r} has no wake reason")
    identity = state.retry_operation
    if identity is None:
        identity = f"turn:{generation.store.next_turn_sequence}"
        generation.store.next_turn_sequence += 1
    generation.store.selected = TurnState(identity, subject, state.reason)
    generation.store.service_order.append(subject)
    state.due_at_us = None
    state.enqueue_sequence = None
    state.reason = None
    state.retry_operation = None
    return _cut(
        "subject_selected",
        subject=subject,
        identity=identity,
        generation=context.generation,
    )


async def action_instance_opened(generation: HostGeneration, _action: ActionRef, context: Any) -> object:
    selected = generation.store.selected
    if selected is None:
        raise HostSimulationError("instance_opened requires a selected host turn")
    generation.lifecycles[selected.subject] = generation.factory.open(selected.subject, generation.lifecycle_view)
    return _cut(
        "instance_opened",
        subject=selected.subject,
        identity=selected.identity,
        generation=context.generation,
    )


async def action_readiness_step_returned(generation: HostGeneration, _action: ActionRef, context: Any) -> object:
    selected = generation.store.selected
    if selected is None:
        raise HostSimulationError("readiness_step_returned requires a selected host turn")
    lifecycle = generation.lifecycles[selected.subject]
    evidence = generation.lifecycle_view.observe(selected.subject)
    try:
        result = await context.call(
            "readiness.progress",
            {
                "evidence": evidence,
                "operation": selected.identity,
                "reason": "runnable",
                "subject": selected.subject,
            },
            lambda: lifecycle.progress(
                "runnable",
                evidence,
                operation=selected.identity,
                context=context,
            ),
        )
    except ReadinessResponseLost as error:
        result = {
            "disposition": "unavailable",
            "eligible_at_us": context.now_us,
            "error_class": type(error).__name__,
            "posture": "ambiguous",
            "source": "exception",
        }
    except ReadinessUnavailable as error:
        result = {
            "disposition": "unavailable",
            "eligible_at_us": context.now_us,
            "error_class": type(error).__name__,
            "posture": "retry",
            "source": "exception",
        }
    selected.result = result
    selected.phase = "returned"
    return _cut(
        "readiness_step_returned",
        subject=selected.subject,
        identity=selected.identity,
        generation=context.generation,
        result=result,
    )


async def action_posture_recorded(generation: HostGeneration, _action: ActionRef, context: Any) -> object:
    selected = generation.store.selected
    if selected is None or selected.result is None:
        raise HostSimulationError("posture_recorded requires one returned readiness result")
    generation.store.subjects[selected.subject].last_result = dict(selected.result)
    selected.phase = "recorded"
    return _cut(
        "posture_recorded",
        subject=selected.subject,
        identity=selected.identity,
        generation=context.generation,
    )


async def action_subject_requeued(generation: HostGeneration, _action: ActionRef, context: Any) -> object:
    selected = generation.store.selected
    if selected is None or selected.result is None:
        raise HostSimulationError("subject_requeued requires one recorded readiness result")
    eligible_at_us = selected.result.get("eligible_at_us")
    disposition = "released"
    if eligible_at_us is not None:
        if selected.result.get("posture") == "ambiguous":
            generation.store.subjects[selected.subject].retry_operation = selected.identity
        _wake(generation.store, selected.subject, "retry", _instant(eligible_at_us, "eligible_at_us"))
        disposition = "requeued"
    result = _cut(
        "subject_requeued",
        subject=selected.subject,
        identity=selected.identity,
        generation=context.generation,
        disposition=disposition,
    )
    generation.store.selected = None
    return result


async def action_instance_closed(generation: HostGeneration, action: ActionRef, context: Any) -> object:
    subject = action.identity
    disposition = generation.release(subject, "graceful")
    return _cut(
        "instance_closed",
        subject=subject,
        identity=subject,
        generation=context.generation,
        disposition=disposition,
    )


COMMANDS = {
    "readiness_close_failure": command_readiness_close_failure,
    "register_instance": command_register_instance,
    "register_route": command_register_route,
    "revoke_route": command_revoke_route,
    "stop": command_stop,
    "wake": command_wake,
}

OBSERVATIONS = {
    "instance": observation_instance,
    "state": observation_state,
}

ACTIONS = {
    "instance_closed": action_instance_closed,
    "instance_opened": action_instance_opened,
    "posture_recorded": action_posture_recorded,
    "readiness_step_returned": action_readiness_step_returned,
    "subject_requeued": action_subject_requeued,
    "subject_selected": action_subject_selected,
}


class HostArtifactChecker:
    """Derive fairness and authority from the artifact, never from HostStore."""

    @classmethod
    def check(cls, artifact: Artifact) -> dict[str, int]:
        routes: dict[str, dict[str, object]] = {}
        subjects: dict[str, str] = {}
        pending_wakes: list[str] = []
        cohort: set[str] | None = None
        seen: set[str] = set()
        fair_cohorts = 0
        authority_calls = 0
        for operation in artifact.operations:
            kind = operation["kind"]
            if kind == "command":
                request = operation["request"]
                if request["module"] != "host":
                    continue
                name = request["name"]
                payload = request["payload"]
                if name == "register_route":
                    routes[payload["route"]] = {"generation": 1, "status": "active"}
                elif name == "register_instance":
                    subjects[payload["subject"]] = payload["route"]
                elif name == "revoke_route":
                    route = routes[payload["route"]]
                    if route["status"] != "revoked":
                        route["status"] = "revoked"
                        route["generation"] = cast(int, route["generation"]) + 1
                elif name == "wake" and cohort is None and payload["subject"] not in pending_wakes:
                    pending_wakes.append(payload["subject"])
                continue
            if kind != "start" or operation["result"]["status"] == "waiting":
                continue
            action = operation["result"]["action"]
            if action["name"] == "subject_selected":
                subject = action["identity"]
                if cohort is None and len(pending_wakes) > 1:
                    cohort = set(pending_wakes)
                    seen = set()
                if cohort is not None:
                    if subject in seen:
                        missing = sorted(cohort - seen)
                        raise HostCheckFailed(
                            f"host selected {subject!r} twice before due peers received a turn: {missing!r}"
                        )
                    if subject in cohort:
                        seen.add(subject)
                    if seen == cohort:
                        fair_cohorts += 1
                        cohort = None
                        pending_wakes = []
                continue
            if action["name"] != "readiness_step_returned" or operation["result"]["status"] != "offered":
                continue
            leaf = operation["result"]["leaf"]
            payload = leaf["payload"]
            subject = payload["subject"]
            route = routes[subjects[subject]]
            evidence = payload["evidence"]
            expected = {
                "custody_generation": 1,
                "route_generation": route["generation"],
                "route_status": route["status"],
            }
            if evidence != expected:
                raise HostCheckFailed(
                    f"readiness call for {subject!r} used stale lifecycle evidence: "
                    f"expected {expected!r}, observed {evidence!r}"
                )
            authority_calls += 1
        if cohort is not None:
            raise HostCheckFailed(f"artifact ended before due peers received a turn: {sorted(cohort - seen)!r}")
        return {"authority_calls": authority_calls, "fair_cohorts": fair_cohorts}


DEFAULT_BUDGET = Budget(
    operations=512,
    owner_steps=128,
    eligible_actions=8,
    leaf_calls=64,
    choice_draws=16,
    active_faults=16,
    generations=16,
    logical_time_us=1_000_000,
    journal_entries=2_048,
    artifact_bytes=2_000_000,
    resources={
        "host.cleanup_errors": 8,
        "host.instances": 8,
        "host.loaded": 8,
        "host.readiness_operations": 64,
        "host.routes": 8,
        "host.runnable": 8,
    },
)
