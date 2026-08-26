"""Executable S8 comparison of bounded driver control-flow mechanisms.

This is exploration code, not a production architecture candidate. All three
drivers consume the same retained-state ``World.step`` contract.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Protocol


class Disposition(StrEnum):
    PROGRESSED = "progressed"
    WAITING = "waiting"
    QUIESCENT = "quiescent"
    TERMINAL = "terminal"
    UNAVAILABLE = "unavailable"


class DriverKind(StrEnum):
    EXPLICIT = "explicit"
    TRAMPOLINE = "trampoline"
    GENERATOR = "generator"


MAX_DRIVER_BUDGET = 10_001


@dataclass(frozen=True)
class CutRef:
    owner: str
    kind: str
    subject: str | None = None
    identity: str | None = None


@dataclass(frozen=True)
class StepResult:
    disposition: Disposition
    cut: CutRef | None = None
    nested: tuple[CutRef, ...] = ()
    rows: int = 0
    external_calls: int = 0
    effect_source: str | None = None
    admission: str | None = None

    @property
    def cuts(self) -> tuple[CutRef, ...]:
        return (() if self.cut is None else (self.cut,)) + self.nested


@dataclass
class SubjectState:
    history_remaining: int = 3
    repairs_remaining: int = 1
    action_index: int = 0


@dataclass
class RetainedState:
    """The complete authority allowed to survive a process generation."""

    queue: list[str]
    subjects: dict[str, SubjectState]
    startup_cuts: list[str] = field(default_factory=lambda: ["catalog_page_inspected", "custody_item_disposed"])
    selected: str | None = None
    selected_open: bool = False
    pending_host_cuts: list[str] = field(default_factory=list)
    turn: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> RetainedState:
        raw = json.loads(payload)
        return cls(
            queue=list(raw["queue"]),
            subjects={name: SubjectState(**state) for name, state in raw["subjects"].items()},
            startup_cuts=list(raw["startup_cuts"]),
            selected=raw["selected"],
            selected_open=raw["selected_open"],
            pending_host_cuts=list(raw["pending_host_cuts"]),
            turn=raw["turn"],
        )


@dataclass
class EffectLedger:
    """Durable provider truth used for lookup-first effect recovery."""

    outcomes: dict[str, str] = field(default_factory=dict)
    effect_calls: dict[str, int] = field(default_factory=dict)

    def observe(self, operation: str) -> tuple[str, str, int]:
        if operation in self.outcomes:
            return self.outcomes[operation], "lookup", 0
        result = f"accepted:{operation}"
        self.outcomes[operation] = result
        self.effect_calls[operation] = self.effect_calls.get(operation, 0) + 1
        return result, "effect", 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> EffectLedger:
        raw = json.loads(payload)
        return cls(outcomes=dict(raw["outcomes"]), effect_calls=dict(raw["effect_calls"]))


@dataclass(frozen=True)
class _ReadinessAction:
    kind: str
    workflow_kind: str | None = None
    admission: str | None = None
    route_settled: bool = False
    effect: bool = False


_READINESS_ACTIONS = (
    _ReadinessAction("ingress_staged", admission="pending"),
    _ReadinessAction("ingress_entry_accepted", workflow_kind="observation_accepted"),
    _ReadinessAction(
        "ingress_entry_folded",
        workflow_kind="observation_folded",
        admission="accepted",
    ),
    _ReadinessAction("workflow_advanced", workflow_kind="workflow_action_committed"),
    _ReadinessAction("activity_attempt_claimed"),
    _ReadinessAction("activity_effect_observed", effect=True),
    _ReadinessAction("workflow_advanced", workflow_kind="workflow_action_committed"),
    _ReadinessAction("timer_command_applied"),
    _ReadinessAction("timer_ack_accepted"),
    _ReadinessAction("timer_ack_marked"),
    _ReadinessAction("timer_maturity_claimed"),
    _ReadinessAction("timer_maturity_accepted"),
    _ReadinessAction("timer_maturity_marked"),
    _ReadinessAction("deferred_wake_accepted", workflow_kind="observation_accepted"),
    _ReadinessAction("agent_route_settled", route_settled=True),
)


@dataclass(frozen=True)
class _ReadinessResult:
    disposition: Disposition
    cuts: tuple[CutRef, ...] = ()
    rows: int = 0
    external_calls: int = 0
    effect_source: str | None = None
    admission: str | None = None
    route_settled: bool = False


class World:
    """Small retained-state model of the S7 workflow/readiness/host cuts."""

    history_records_per_page = 2

    def __init__(self, retained: RetainedState, effects: EffectLedger):
        self.retained = retained
        self.effects = effects
        # An observed result can make the adjacent terminal step cheaper, but
        # it is deliberately absent from RetainedState and lost on restore.
        self._observed: dict[str, str] = {}

    @classmethod
    def fresh(cls, subjects: tuple[str, ...] = ("pr-1", "pr-2")) -> World:
        return cls(
            RetainedState(
                queue=list(subjects),
                subjects={subject: SubjectState() for subject in subjects},
            ),
            EffectLedger(),
        )

    def snapshot(self) -> tuple[str, str]:
        return self.retained.to_json(), self.effects.to_json()

    @classmethod
    def restore(cls, retained: str, effects: str) -> World:
        return cls(RetainedState.from_json(retained), EffectLedger.from_json(effects))

    def step(self) -> StepResult:
        if self.retained.startup_cuts:
            kind = self.retained.startup_cuts.pop(0)
            return StepResult(Disposition.PROGRESSED, CutRef("host", kind))

        if self.retained.pending_host_cuts:
            return self._apply_host_cut()

        if self.retained.selected is None:
            if not self.retained.queue:
                return StepResult(Disposition.TERMINAL)
            self.retained.selected = self.retained.queue.pop(0)
            self.retained.turn += 1
            return StepResult(
                Disposition.PROGRESSED,
                CutRef(
                    "host",
                    "subject_selected",
                    self.retained.selected,
                    f"turn-{self.retained.turn}",
                ),
            )

        subject = self.retained.selected
        if not self.retained.selected_open:
            self.retained.selected_open = True
            return StepResult(
                Disposition.PROGRESSED,
                CutRef("host", "instance_opened", subject),
            )

        readiness = self._readiness_step(subject)
        followups = ["posture_recorded"]
        if readiness.admission == "accepted":
            followups.append("delivery_acknowledged")
        if readiness.route_settled:
            followups.append("agent_route_recorded")
        followups.append("instance_closed" if readiness.disposition is Disposition.TERMINAL else "subject_requeued")
        self.retained.pending_host_cuts = followups
        return StepResult(
            Disposition.PROGRESSED,
            CutRef("host", "readiness_step_returned", subject),
            nested=readiness.cuts,
            rows=readiness.rows,
            external_calls=readiness.external_calls,
            effect_source=readiness.effect_source,
            admission=readiness.admission,
        )

    def _apply_host_cut(self) -> StepResult:
        subject = self.retained.selected
        assert subject is not None
        kind = self.retained.pending_host_cuts.pop(0)
        result = StepResult(Disposition.PROGRESSED, CutRef("host", kind, subject))
        if kind == "subject_requeued":
            self.retained.queue.append(subject)
            self.retained.selected = None
            self.retained.selected_open = False
        elif kind == "instance_closed":
            self.retained.selected = None
            self.retained.selected_open = False
        return result

    def _readiness_step(self, subject: str) -> _ReadinessResult:
        state = self.retained.subjects[subject]
        if state.history_remaining:
            rows = min(state.history_remaining, self.history_records_per_page)
            state.history_remaining -= rows
            return _ReadinessResult(
                Disposition.PROGRESSED,
                (
                    CutRef("readiness", "runtime_reconstructed", subject),
                    CutRef("workflow", "history_page_replayed", subject),
                ),
                rows=rows,
            )
        if state.repairs_remaining:
            state.repairs_remaining -= 1
            return _ReadinessResult(
                Disposition.PROGRESSED,
                (
                    CutRef("readiness", "runtime_reconstructed", subject),
                    CutRef("workflow", "occurrence_repaired", subject, f"{subject}:occurrence"),
                ),
                rows=1,
            )
        if state.action_index == len(_READINESS_ACTIONS):
            return _ReadinessResult(Disposition.TERMINAL)

        action = _READINESS_ACTIONS[state.action_index]
        operation = f"{subject}:publication"
        if action.effect:
            if subject in self._observed:
                del self._observed[subject]
                state.action_index += 1
                return _ReadinessResult(
                    Disposition.PROGRESSED,
                    (CutRef("readiness", "activity_terminal_recorded", subject, operation),),
                )
            result, source, calls = self.effects.observe(operation)
            self._observed[subject] = result
            return _ReadinessResult(
                Disposition.PROGRESSED,
                (CutRef("readiness", action.kind, subject, operation),),
                external_calls=calls,
                effect_source=source,
            )

        state.action_index += 1
        cuts = [CutRef("readiness", action.kind, subject, operation if action.route_settled else None)]
        if action.workflow_kind is not None:
            cuts.append(CutRef("workflow", action.workflow_kind, subject))
        return _ReadinessResult(
            Disposition.PROGRESSED,
            tuple(cuts),
            admission=action.admission,
            route_settled=action.route_settled,
        )


class Stepper(Protocol):
    def step(self) -> StepResult: ...


@dataclass(frozen=True)
class DriverReport:
    results: tuple[StepResult, ...]
    budget_exhausted: bool
    cancelled: bool = False


class Driver(Protocol):
    def one(self) -> StepResult: ...

    def run(self, budget: int) -> DriverReport: ...

    def cancel(self) -> None: ...


def _validate_budget(budget: int) -> None:
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0 or budget > MAX_DRIVER_BUDGET:
        raise ValueError(f"driver budget must be an integer from 0 through {MAX_DRIVER_BUDGET}")


class ExplicitDriver:
    def __init__(self, stepper: Stepper):
        self._stepper = stepper
        self._cancelled = False

    def one(self) -> StepResult:
        if self._cancelled:
            return StepResult(Disposition.WAITING)
        return self._stepper.step()

    def run(self, budget: int) -> DriverReport:
        _validate_budget(budget)
        results: list[StepResult] = []
        for _ in range(budget):
            if self._cancelled:
                return DriverReport(tuple(results), budget_exhausted=False, cancelled=True)
            result = self._stepper.step()
            results.append(result)
            if result.disposition is not Disposition.PROGRESSED:
                return DriverReport(tuple(results), budget_exhausted=False)
        return DriverReport(tuple(results), budget_exhausted=True, cancelled=self._cancelled)

    def cancel(self) -> None:
        self._cancelled = True


@dataclass(frozen=True)
class _Bounce:
    command: str = "step"


class TrampolineDriver:
    """Iterative data trampoline; the bounce carries no semantic authority."""

    def __init__(self, stepper: Stepper):
        self._stepper = stepper
        self._next = _Bounce()
        self._cancelled = False

    def _bounce(self) -> StepResult:
        if self._next.command != "step":
            raise ValueError(f"unknown trampoline command {self._next.command!r}")
        result = self._stepper.step()
        self._next = _Bounce()
        return result

    def one(self) -> StepResult:
        if self._cancelled:
            return StepResult(Disposition.WAITING)
        return self._bounce()

    def run(self, budget: int) -> DriverReport:
        _validate_budget(budget)
        results: list[StepResult] = []
        bounces = 0
        while bounces < budget:
            if self._cancelled:
                return DriverReport(tuple(results), budget_exhausted=False, cancelled=True)
            result = self._bounce()
            results.append(result)
            bounces += 1
            if result.disposition is not Disposition.PROGRESSED:
                return DriverReport(tuple(results), budget_exhausted=False)
        return DriverReport(tuple(results), budget_exhausted=True, cancelled=self._cancelled)

    def cancel(self) -> None:
        self._cancelled = True


def _generate(stepper: Stepper) -> Generator[StepResult]:
    while True:
        yield stepper.step()


class GeneratorDriver:
    """Yield spelling whose frame is always disposable and never restored."""

    def __init__(self, stepper: Stepper):
        self._steps = _generate(stepper)
        self._cancelled = False

    def one(self) -> StepResult:
        if self._cancelled:
            return StepResult(Disposition.WAITING)
        return next(self._steps)

    def run(self, budget: int) -> DriverReport:
        _validate_budget(budget)
        results: list[StepResult] = []
        for _ in range(budget):
            if self._cancelled:
                return DriverReport(tuple(results), budget_exhausted=False, cancelled=True)
            result = next(self._steps)
            results.append(result)
            if result.disposition is not Disposition.PROGRESSED:
                return DriverReport(tuple(results), budget_exhausted=False)
        return DriverReport(tuple(results), budget_exhausted=True, cancelled=self._cancelled)

    def cancel(self) -> None:
        self._cancelled = True
        self._steps.close()


def make_driver(kind: DriverKind, stepper: Stepper) -> Driver:
    if kind is DriverKind.EXPLICIT:
        return ExplicitDriver(stepper)
    if kind is DriverKind.TRAMPOLINE:
        return TrampolineDriver(stepper)
    if kind is DriverKind.GENERATOR:
        return GeneratorDriver(stepper)
    raise ValueError(f"unknown driver kind {kind!r}")


__all__ = [
    "MAX_DRIVER_BUDGET",
    "CutRef",
    "Disposition",
    "DriverKind",
    "DriverReport",
    "EffectLedger",
    "RetainedState",
    "StepResult",
    "World",
    "make_driver",
]
