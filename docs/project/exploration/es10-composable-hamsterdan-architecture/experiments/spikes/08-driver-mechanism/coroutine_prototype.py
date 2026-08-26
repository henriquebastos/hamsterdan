"""Timeline and coroutine stepper for the amended S8 mechanism comparison.

The owner functions are ordinary nested ``async`` code. ``perform`` yields an
actual callable through that stack so one generic stepper can stop before the
call, after the call, or after its value returns to the owners. Coroutine frames
are process-local and disposable; only ``RetainedState`` and ``EffectLedger``
survive ``restore``.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Coroutine, Generator
from dataclasses import asdict, dataclass
from enum import StrEnum
from functools import partial
from types import coroutine
from typing import Any, cast

from prototype import (
    MAX_DRIVER_BUDGET,
    CutRef,
    Disposition,
    DriverReport,
    EffectLedger,
    StepResult,
)

MAX_STEP_BUDGET = MAX_DRIVER_BUDGET
DrainReport = DriverReport

type Operation[T] = Callable[[], Awaitable[T]]
type AnyOperation = Operation[Any]
type Entry = Callable[[], Coroutine[Any, Any, StepResult]]


@coroutine
def perform[T](operation: Operation[T]) -> Generator[Operation[T], T, T]:
    """Suspend nested owner code at one executable operation."""
    return (yield operation)


class ActivityPhase(StrEnum):
    CLAIM = "claim"
    EFFECT = "effect"
    DONE = "done"


class Release(StrEnum):
    REQUEUE = "requeue"
    CLOSE = "close"


@dataclass
class SubjectState:
    phase: ActivityPhase = ActivityPhase.CLAIM


@dataclass
class RetainedState:
    """The complete scheduling and Activity authority retained on restart."""

    queue: list[str]
    subjects: dict[str, SubjectState]
    selected: str | None = None
    posture_pending: bool = False
    release: Release | None = None
    turn: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> RetainedState:
        raw = json.loads(payload)
        return cls(
            queue=list(raw["queue"]),
            subjects={name: SubjectState(ActivityPhase(state["phase"])) for name, state in raw["subjects"].items()},
            selected=raw["selected"],
            posture_pending=raw["posture_pending"],
            release=None if raw["release"] is None else Release(raw["release"]),
            turn=raw["turn"],
        )


def _callable_function(value: Callable[..., object]) -> Callable[..., object]:
    while isinstance(value, partial):
        value = value.func
    return cast(Callable[..., object], getattr(value, "__func__", value))


def calls(operation: Callable[..., object], target: Callable[..., object]) -> bool:
    """Whether an offered callable invokes the named function or method."""
    return _callable_function(operation) is _callable_function(target)


_EMPTY = object()


class CoroutineStepper:
    """Advance one owner step through one callable and an ordinary return path."""

    def __init__(self, entry: Entry):
        self._entry = entry
        self._iterator: Generator[Any, Any, StepResult] | None = None
        self._pending: AnyOperation | None = None
        self._reply: object = _EMPTY
        self._reply_is_error = False
        self._cancelled = False

    def offer(self) -> AnyOperation | StepResult:
        """Descend through owner code and stop before its one leaf operation."""
        if self._cancelled:
            return StepResult(Disposition.WAITING)
        if self._pending is not None:
            return self._pending
        if self._reply is not _EMPTY:
            raise RuntimeError("finish the executed operation before offering another")

        iterator = self._entry().__await__()
        self._iterator = iterator
        try:
            operation = next(self._iterator)
        except StopIteration as completed:
            self._iterator = None
            return cast(StepResult, completed.value)

        if not callable(operation):
            self.close()
            raise TypeError("owner step must yield an executable callable")
        self._pending = cast(AnyOperation, operation)
        return self._pending

    async def execute_pending(self) -> tuple[AnyOperation, object]:
        """Execute the offered leaf while its result remains outside the owners."""
        if self._pending is None:
            raise RuntimeError("no callable is pending")

        operation, self._pending = self._pending, None
        try:
            result = await operation()
        except BaseException as error:  # noqa: BLE001 - the owner coroutine receives the original failure
            self._reply = error
            self._reply_is_error = True
            return operation, error

        self._reply = result
        self._reply_is_error = False
        return operation, result

    def finish_step(self) -> StepResult:
        """Return the leaf result through every owner and complete one semantic step."""
        if self._iterator is None or self._reply is _EMPTY:
            raise RuntimeError("no executed callable is waiting to return")

        iterator = self._iterator
        reply, self._reply = self._reply, _EMPTY
        reply_is_error, self._reply_is_error = self._reply_is_error, False
        try:
            if reply_is_error:
                iterator.throw(cast(BaseException, reply))
            else:
                iterator.send(reply)
        except StopIteration as completed:
            self._iterator = None
            return cast(StepResult, completed.value)
        except BaseException:
            self._iterator = None
            raise

        iterator.close()
        self._iterator = None
        raise RuntimeError(
            "one owner step awaited more than one operation; return and let the production stepper allocate another step"
        )

    async def step(self) -> StepResult:
        """Execute at most one leaf and return one completed owner result."""
        if self._reply is not _EMPTY:
            return self.finish_step()

        offered = self.offer()
        if isinstance(offered, StepResult):
            return offered
        await self.execute_pending()
        return self.finish_step()

    async def run(self, budget: int) -> DrainReport:
        _validate_budget(budget)
        results: list[StepResult] = []
        for _ in range(budget):
            if self._cancelled:
                return DrainReport(tuple(results), budget_exhausted=False, cancelled=True)
            result = await self.step()
            results.append(result)
            if result.disposition is not Disposition.PROGRESSED:
                return DrainReport(tuple(results), budget_exhausted=False)
        return DrainReport(tuple(results), budget_exhausted=True, cancelled=self._cancelled)

    def cancel(self) -> None:
        self._cancelled = True
        self.close()

    def close(self) -> None:
        if self._iterator is not None:
            self._iterator.close()
        self._iterator = None
        self._pending = None
        self._reply = _EMPTY
        self._reply_is_error = False


class Timeline:
    """Thin S8 debugger facade over the production-shaped coroutine stepper."""

    def __init__(self, stepper: CoroutineStepper):
        self._stepper = stepper

    async def step(self) -> StepResult:
        return await self._stepper.step()

    async def run(self, budget: int) -> DrainReport:
        return await self._stepper.run(budget)

    async def run_until_before(self, target: Callable[..., object], budget: int = MAX_STEP_BUDGET) -> AnyOperation:
        """Run completed steps until the next leaf is the named callable."""
        _validate_budget(budget)
        for _ in range(budget):
            offered = self._stepper.offer()
            if isinstance(offered, StepResult):
                if offered.disposition is not Disposition.PROGRESSED:
                    break
                continue
            if calls(offered, target):
                return offered
            await self._stepper.execute_pending()
            result = self._stepper.finish_step()
            if result.disposition is not Disposition.PROGRESSED:
                break
        name = getattr(target, "__qualname__", repr(target))
        raise LookupError(f"callable {name} was not offered within {budget} steps")

    async def run_until_after(
        self,
        target: Callable[..., object],
        budget: int = MAX_STEP_BUDGET,
    ) -> tuple[AnyOperation, object]:
        """Run until the named callable executed, leaving its result outside owners."""
        operation = await self.run_until_before(target, budget)
        executed = await self._stepper.execute_pending()
        assert executed[0] is operation
        return executed

    async def execute_pending(self) -> tuple[AnyOperation, object]:
        return await self._stepper.execute_pending()

    def finish_step(self) -> StepResult:
        return self._stepper.finish_step()

    def close(self) -> None:
        self._stepper.close()


def _validate_budget(budget: int) -> None:
    if isinstance(budget, bool) or not isinstance(budget, int) or not 0 <= budget <= MAX_STEP_BUDGET:
        raise ValueError(f"step budget must be an integer from 0 through {MAX_STEP_BUDGET}")


class LayeredWorld:
    """Focused host → readiness → workflow/Activity callable-stack model."""

    def __init__(self, retained: RetainedState, effects: EffectLedger):
        self.retained = retained
        self.effects = effects
        self._observed: dict[str, tuple[str, str, int]] = {}

    @classmethod
    def fresh(cls, subjects: tuple[str, ...] = ("pr-1", "pr-2")) -> LayeredWorld:
        if not subjects or len(set(subjects)) != len(subjects):
            raise ValueError("subjects must be a non-empty unique tuple")
        return cls(
            RetainedState(
                queue=list(subjects),
                subjects={subject: SubjectState() for subject in subjects},
            ),
            EffectLedger(),
        )

    def stepper(self) -> CoroutineStepper:
        return CoroutineStepper(self.host_once)

    def timeline(self) -> Timeline:
        return Timeline(self.stepper())

    def snapshot(self) -> tuple[str, str]:
        return self.retained.to_json(), self.effects.to_json()

    @classmethod
    def restore(cls, retained: str, effects: str) -> LayeredWorld:
        return cls(RetainedState.from_json(retained), EffectLedger.from_json(effects))

    async def host_once(self) -> StepResult:
        """Cross one host cut or return one nested readiness cut unchanged."""
        if self.retained.posture_pending:
            return await perform(partial(self.record_posture))
        if self.retained.release is not None:
            return await perform(partial(self.release_subject))
        if self.retained.selected is None:
            if not self.retained.queue:
                return StepResult(Disposition.TERMINAL)
            return await perform(partial(self.select_subject))

        subject = self.retained.selected
        readiness = await self.readiness_once(subject)
        self.retained.posture_pending = True
        self.retained.release = Release.CLOSE if readiness.disposition is Disposition.TERMINAL else Release.REQUEUE
        return StepResult(
            Disposition.PROGRESSED,
            CutRef("host", "readiness_step_returned", subject),
            nested=readiness.cuts,
            rows=readiness.rows,
            external_calls=readiness.external_calls,
            effect_source=readiness.effect_source,
            admission=readiness.admission,
        )

    async def readiness_once(self, subject: str) -> StepResult:
        """Choose one readiness lane after one pure workflow observation."""
        phase = await self.workflow_once(subject)
        if phase is ActivityPhase.DONE:
            return StepResult(Disposition.TERMINAL)
        return await self.activity_once(subject, phase)

    async def workflow_once(self, subject: str) -> ActivityPhase:
        """Return the pure workflow-owned Activity posture for this turn."""
        return self.retained.subjects[subject].phase

    async def activity_once(self, subject: str, phase: ActivityPhase) -> StepResult:
        if phase is ActivityPhase.CLAIM:
            return await perform(partial(self.claim_activity, subject))

        observed = self._observed.get(subject)
        if observed is None:
            observed = await perform(partial(self.observe_or_execute_activity, subject))
            self._observed[subject] = observed
            _result, source, calls_count = observed
            return StepResult(
                Disposition.PROGRESSED,
                CutRef("readiness", "activity_effect_observed", subject, self._operation(subject)),
                external_calls=calls_count,
                effect_source=source,
            )

        result = await perform(partial(self.record_activity_terminal, subject, observed[0]))
        self._observed.pop(subject, None)
        return result

    async def select_subject(self) -> StepResult:
        subject = self.retained.queue.pop(0)
        self.retained.selected = subject
        self.retained.turn += 1
        return StepResult(
            Disposition.PROGRESSED,
            CutRef("host", "subject_selected", subject, f"turn-{self.retained.turn}"),
        )

    async def record_posture(self) -> StepResult:
        subject = self._selected()
        self.retained.posture_pending = False
        return StepResult(Disposition.PROGRESSED, CutRef("host", "posture_recorded", subject))

    async def release_subject(self) -> StepResult:
        subject = self._selected()
        release = self.retained.release
        if release is None or self.retained.posture_pending:
            raise RuntimeError("subject release requires recorded posture")
        if release is Release.REQUEUE:
            self.retained.queue.append(subject)
            kind = "subject_requeued"
        else:
            kind = "instance_closed"
        self.retained.selected = None
        self.retained.release = None
        return StepResult(Disposition.PROGRESSED, CutRef("host", kind, subject))

    async def claim_activity(self, subject: str) -> StepResult:
        state = self.retained.subjects[subject]
        if state.phase is not ActivityPhase.CLAIM:
            raise RuntimeError(f"{subject} has no claimable Activity")
        state.phase = ActivityPhase.EFFECT
        return StepResult(
            Disposition.PROGRESSED,
            CutRef("readiness", "activity_attempt_claimed", subject, self._operation(subject)),
        )

    async def observe_or_execute_activity(self, subject: str) -> tuple[str, str, int]:
        return self.effects.observe(self._operation(subject))

    async def record_activity_terminal(self, subject: str, result: str) -> StepResult:
        operation = self._operation(subject)
        if self.effects.outcomes.get(operation) != result:
            raise RuntimeError(f"{operation} has no matching observed result")
        self.retained.subjects[subject].phase = ActivityPhase.DONE
        return StepResult(
            Disposition.PROGRESSED,
            CutRef("readiness", "activity_terminal_recorded", subject, operation),
        )

    def _selected(self) -> str:
        if self.retained.selected is None:
            raise RuntimeError("no subject is selected")
        return self.retained.selected

    @staticmethod
    def _operation(subject: str) -> str:
        return f"{subject}:publication"


__all__ = [
    "ActivityPhase",
    "CoroutineStepper",
    "LayeredWorld",
    "Release",
    "RetainedState",
    "Timeline",
    "calls",
    "perform",
]
