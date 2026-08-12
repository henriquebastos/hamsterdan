"""AX9 spike — effect-oriented activity authoring, Interpretation A.

Effects are frozen dataclass **values** an activity program yields. A
worker-side interpreter performs them through an ``EffectRuntime`` and
journals every completed effect result. The journal — not the generator
frame — is the durable state:

- The generator is reconstructed from scratch on every attempt and
  replayed deterministically: journaled steps get their recorded results
  ``send``-ed back in; only the first un-journaled effect executes.
- The journal travels through the frozen dispatch's **heartbeat details
  channel**: ``LocalWorkerDispatch.claim`` returns the details persisted
  by the previous attempt's last heartbeat, so a crashed worker's
  successor resumes mid-program with zero Petrus changes.
- The Petri net sees exactly one activity. History records one
  ``ActivityRequested``/``ActivityCompleted`` pair regardless of how
  many effects the program performs.

The at-least-once boundary is per **effect**: a crash after an effect
performs but before its journal heartbeat lands re-performs that one
effect on the next attempt. Effect handlers therefore carry the same
idempotency obligation activity implementations already carry.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from inspect import Parameter, isgeneratorfunction, signature
from types import MappingProxyType
from typing import get_type_hints

from petrus.motus.activity import (
    ActivityDeclaration,
    ActivityExecutionContext,
    ActivityInvocation,
    DataclassPayloadConverter,
    PayloadConverter,
)

JOURNAL_KEY = "ax9_effect_journal"

_DEFAULT_CONVERTER = DataclassPayloadConverter()


class EffectProgramError(ValueError):
    """The effect program cannot be interpreted safely."""


class NondeterministicEffectProgram(EffectProgramError):
    """Replay produced a different effect than the journal recorded."""


@dataclass(frozen=True)
class EffectHandler:
    """One effect type's worker-side implementation and result contract."""

    perform: Callable[[object], object]
    result: type | None


class EffectRuntime:
    """Worker-side effect execution environment. Nothing here is durable."""

    def __init__(self, handlers: Mapping[type, EffectHandler]) -> None:
        for effect_type in handlers:
            if not (isinstance(effect_type, type) and is_dataclass(effect_type)):
                raise EffectProgramError(f"effect types must be dataclasses, got {effect_type!r}")
        self._handlers = dict(handlers)

    def handler_for(self, effect_type: type) -> EffectHandler:
        handler = self._handlers.get(effect_type)
        if handler is None:
            known = ", ".join(sorted(t.__name__ for t in self._handlers)) or "none"
            raise EffectProgramError(f"no effect handler for {effect_type.__name__!r}; known effects: {known}")
        return handler


def fingerprint(effect: object) -> str:
    """Canonical durable identity of one yielded effect value."""

    if not is_dataclass(effect) or isinstance(effect, type):
        raise EffectProgramError(f"effect programs may yield only dataclass effect values, got {type(effect).__name__}")
    try:
        encoded = json.dumps(asdict(effect), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise EffectProgramError(f"effect {type(effect).__name__} is not JSON-faithful: {error}") from None
    return f"{type(effect).__name__}:{encoded}"


def _journal(latest_details: object) -> list[dict[str, object]]:
    if latest_details is None:
        return []
    if not isinstance(latest_details, Mapping) or JOURNAL_KEY not in latest_details:
        raise EffectProgramError(
            f"attempt details are not an effect journal (missing {JOURNAL_KEY!r}); "
            "effect activities must own their heartbeat details exclusively"
        )
    entries = latest_details[JOURNAL_KEY]
    if not isinstance(entries, list) or any(
        not isinstance(entry, Mapping) or not isinstance(entry.get("effect"), str) for entry in entries
    ):
        raise EffectProgramError("effect journal entries are malformed")
    return [dict(entry) for entry in entries]


def run_effect_program(
    program: Callable[..., object],
    arguments: Mapping[str, object],
    *,
    runtime: EffectRuntime,
    context: ActivityExecutionContext,
    converter: PayloadConverter = _DEFAULT_CONVERTER,
) -> object:
    """Replay journaled effects, perform the first un-journaled one, repeat."""

    journal = _journal(context.latest_details)
    generator = program(**arguments)
    index = 0
    to_send: object = None
    while True:
        try:
            effect = generator.send(to_send)
        except StopIteration as stop:
            return stop.value
        mark = fingerprint(effect)
        handler = runtime.handler_for(type(effect))
        if index < len(journal):
            recorded = journal[index]
            if recorded["effect"] != mark:
                raise NondeterministicEffectProgram(
                    f"replay diverged at effect {index}: the journal recorded "
                    f"{recorded['effect']!r} but the program yielded {mark!r}; an "
                    "effect program must be a deterministic function of its "
                    "arguments and journaled effect results"
                )
            to_send = None if handler.result is None else converter.decode(recorded["result"], handler.result)
        else:
            result = handler.perform(effect)
            if handler.result is None:
                if result is not None:
                    raise EffectProgramError(
                        f"effect {type(effect).__name__} declares no result but its "
                        f"handler returned {type(result).__name__}"
                    )
                encoded: object = None
            else:
                encoded = converter.encode(result, handler.result)
            journal.append({"effect": mark, "result": encoded})
            context.heartbeat(details={JOURNAL_KEY: journal})
            to_send = result
        index += 1


@dataclass(frozen=True)
class EffectActivityDefinition:
    """An effect program adapted to the frozen synchronous Activity protocol.

    Unlike ``petrus.motus.activity.ActivityDefinition`` — which discards its
    execution context — this definition **uses** the context: the journal
    resumes from ``context.latest_details`` and checkpoints via
    ``context.heartbeat``.
    """

    program: Callable[..., object]
    declaration: ActivityDeclaration
    converter: PayloadConverter
    parameters: Mapping[str, object]
    result: object
    runtime: EffectRuntime

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))

    def __call__(self, invocation: ActivityInvocation, *, context: ActivityExecutionContext) -> object:
        if invocation.activity != self.declaration.name:
            raise ValueError(
                f"Effect activity {self.declaration.name!r} cannot execute an invocation for {invocation.activity!r}"
            )
        supplied = invocation.input
        if not isinstance(supplied, Mapping):
            raise TypeError(
                f"Effect activity {self.declaration.name!r} requires a parameter mapping, got {type(supplied).__name__}"
            )
        if set(supplied) != set(self.parameters):
            raise ValueError(
                f"Effect activity {self.declaration.name!r} requires parameters "
                f"{sorted(self.parameters)}, got {sorted(supplied)}"
            )
        arguments = {
            name: self.converter.decode(supplied[name], annotation) for name, annotation in self.parameters.items()
        }
        value = run_effect_program(
            self.program,
            arguments,
            runtime=self.runtime,
            context=context,
            converter=self.converter,
        )
        return self.converter.encode(value, self.result)


def effect_activity(
    program: Callable[..., object],
    *,
    runtime: EffectRuntime,
    name: str | None = None,
    heartbeat_timeout: int | None = None,
    converter: PayloadConverter = _DEFAULT_CONVERTER,
) -> EffectActivityDefinition:
    """Declare a typed generator function as one effect-interpreted Activity."""

    program_name = getattr(program, "__name__", type(program).__name__)
    if not isgeneratorfunction(program):
        raise TypeError(
            f"effect_activity {program_name!r} requires a generator function that "
            "yields effect values; a plain function should use petrus.motus.activity"
        )
    hints = get_type_hints(program)
    parameters: dict[str, object] = {}
    for parameter in signature(program).parameters.values():
        if parameter.kind not in (
            Parameter.POSITIONAL_OR_KEYWORD,
            Parameter.KEYWORD_ONLY,
        ):
            raise TypeError(f"effect_activity {program_name!r} parameter {parameter.name!r} must be a named parameter")
        if parameter.name not in hints:
            raise TypeError(f"effect_activity {program_name!r} parameter {parameter.name!r} requires a type annotation")
        parameters[parameter.name] = hints[parameter.name]
    if "return" not in hints:
        raise TypeError(
            f"effect_activity {program_name!r} requires a return type annotation naming the program's final result"
        )
    declaration = ActivityDeclaration(program_name if name is None else name, heartbeat_timeout=heartbeat_timeout)
    return EffectActivityDefinition(program, declaration, converter, parameters, hints["return"], runtime)
