"""AX9 spike — effect-oriented activity authoring, Interpretation B.

The same generator program is used **only as compile-time syntax**: it is
traced once with symbolic proxies to extract a static effect-step graph,
then each step lowers to an ordinary Motus activity transition threading
an environment token through generated places. No generator frame exists
at runtime; durability is the ordinary per-effect
``ActivityRequested``/``ActivityCompleted`` history.

The tracing boundary is deliberately loud: data-dependent control flow
(``if``/``while`` over an effect result) raises ``TraceBranchError``,
because a traced program is straight-line by construction — branching is
workflow-combinator territory (AX5–AX7), not effect territory.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields, is_dataclass
from inspect import Parameter, isgeneratorfunction, signature
from types import MappingProxyType
from typing import get_type_hints

from ax9_effects import EffectProgramError, EffectRuntime
from petrus.impetus.binding import ActivityHandler, DerivedActivityHandler, Handler
from petrus.impetus.dsl import BuiltNet, NetSpec
from petrus.impetus.petrinet import NetPath
from petrus.impetus.petrinet.schema import NetUri
from petrus.motus.activity import (
    ActivityDeclaration,
    ActivityDefinition,
    DataclassPayloadConverter,
)
from petrus.motus.activity import activity as motus_activity


class TraceBranchError(TypeError):
    """The effect program branched on a symbolic value during tracing."""


@dataclass(frozen=True)
class Ref:
    """A symbolic reference into the threaded environment."""

    root: str
    path: tuple[str, ...] = ()


class TraceValue:
    """Field-access-recording stand-in for an input or an effect result."""

    def __init__(self, ref: Ref) -> None:
        object.__setattr__(self, "_ref", ref)

    def __getattr__(self, name: str) -> TraceValue:
        if name.startswith("_"):
            raise AttributeError(name)
        ref: Ref = object.__getattribute__(self, "_ref")
        return TraceValue(Ref(ref.root, (*ref.path, name)))

    def __bool__(self) -> bool:
        ref: Ref = object.__getattribute__(self, "_ref")
        raise TraceBranchError(
            f"effect program tracing cannot follow data-dependent control flow "
            f"(branched on {'.'.join((ref.root, *ref.path))}); branching belongs "
            "to workflow combinators (switch/branch/hybrid), not inside a traced "
            "effect program"
        )

    __iter__ = __len__ = __index__ = __bool__  # type: ignore[assignment]


def _unwrap(value: object) -> object:
    if isinstance(value, TraceValue):
        return object.__getattribute__(value, "_ref")
    return value


@dataclass(frozen=True)
class EffectStep:
    """One traced effect: its type, symbolic arguments, and result slot."""

    effect_type: type
    arguments: Mapping[str, object]
    result: type | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True)
class EffectProgramGraph:
    """The static, serializable shape of one traced effect program."""

    name: str
    parameter: str
    parameter_type: type
    steps: tuple[EffectStep, ...]
    returns: type
    return_arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "return_arguments", MappingProxyType(dict(self.return_arguments)))


def trace_effect_program(program: Callable[..., object], *, runtime: EffectRuntime) -> EffectProgramGraph:
    """Run the generator once with proxies and record its static step graph."""

    program_name = getattr(program, "__name__", type(program).__name__)
    if not isgeneratorfunction(program):
        raise TypeError(f"cannot trace {program_name!r}: not a generator function")
    hints = get_type_hints(program)
    names = [
        parameter.name
        for parameter in signature(program).parameters.values()
        if parameter.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
    ]
    if len(names) != 1:
        raise EffectProgramError(f"this spike traces single-parameter programs, {program_name!r} has {len(names)}")
    [parameter] = names
    generator = program(TraceValue(Ref(parameter)))
    steps: list[EffectStep] = []
    to_send: object = None
    while True:
        try:
            effect = generator.send(to_send)
        except StopIteration as stop:
            returned = stop.value
            break
        if not is_dataclass(effect) or isinstance(effect, type):
            raise EffectProgramError(f"traced program {program_name!r} yielded a non-dataclass {type(effect).__name__}")
        handler = runtime.handler_for(type(effect))
        arguments = {field.name: _unwrap(getattr(effect, field.name)) for field in fields(effect)}
        index = len(steps)
        steps.append(EffectStep(type(effect), arguments, handler.result))
        to_send = TraceValue(Ref(f"step_{index}")) if handler.result is not None else None
    if not is_dataclass(returned) or isinstance(returned, type):
        raise EffectProgramError(
            f"traced program {program_name!r} must return a dataclass value, got {type(returned).__name__}"
        )
    return EffectProgramGraph(
        name=program_name,
        parameter=parameter,
        parameter_type=hints[parameter],
        steps=tuple(steps),
        returns=type(returned),
        return_arguments={field.name: _unwrap(getattr(returned, field.name)) for field in fields(returned)},
    )


def _resolve(value: object, env: Mapping[str, object]) -> object:
    if not isinstance(value, Ref):
        return value
    node: object = env[value.root]
    for segment in value.path:
        node = node[segment]  # type: ignore[index]
    return node


@dataclass(frozen=True)
class CompiledEffectNet:
    built: BuiltNet
    entry: NetPath
    exit: NetPath
    handlers: Mapping[NetUri | str, Handler | ActivityHandler]
    activities: tuple[ActivityDeclaration, ...]
    definitions: tuple[ActivityDefinition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))


def lower_effect_graph(
    graph: EffectProgramGraph, *, runtime: EffectRuntime, name: str = "effects"
) -> CompiledEffectNet:
    """Lower the traced graph to a linear net: enter → one transition per
    effect (threading a ``dict`` environment token) → return projection."""

    definitions: list[ActivityDefinition] = []

    def enter(request) -> dict:  # full annotations injected below
        return {graph.parameter: asdict(request)}

    enter.__annotations__ = {"request": graph.parameter_type, "return": dict}
    enter.__name__ = f"{graph.name}_enter"
    definitions.append(motus_activity(enter, converter=DataclassPayloadConverter()))

    def make_step(index: int, step: EffectStep) -> ActivityDefinition:
        def perform(env: dict) -> dict:
            effect = step.effect_type(**{key: _resolve(value, env) for key, value in step.arguments.items()})
            result = runtime.handler_for(step.effect_type).perform(effect)
            out = dict(env)
            if step.result is not None:
                out[f"step_{index}"] = asdict(result)
            return out

        perform.__name__ = f"{graph.name}_{index}_{step.effect_type.__name__.lower()}"
        return motus_activity(perform)

    for index, step in enumerate(graph.steps):
        definitions.append(make_step(index, step))

    def project(env: dict):  # return annotation injected below
        return graph.returns(**{key: _resolve(value, env) for key, value in graph.return_arguments.items()})

    project.__annotations__ = {"env": dict, "return": graph.returns}
    project.__name__ = f"{graph.name}_project"
    definitions.append(motus_activity(project, converter=DataclassPayloadConverter()))

    spec = NetSpec(name)
    scope = spec.s["e"]
    entry_place = scope.p.entry(graph.parameter_type.__name__)
    current = entry_place
    activity_paths: list[tuple[NetPath, ActivityDefinition]] = []
    for position, definition in enumerate(definitions):
        transition = getattr(scope.t, definition.declaration.name)(handler=definition.declaration.name)
        last = position == len(definitions) - 1
        color = graph.returns.__name__ if last else "dict"
        place = getattr(scope.p, f"after_{position}" if not last else "exit")(color)
        current >> transition >> place
        activity_paths.append((abs(transition), definition))
        current = place

    built = spec.build()
    handlers: dict[NetUri | str, Handler | ActivityHandler] = dict(built.handlers)
    for transition_path, definition in activity_paths:
        uri = built.net.handler_uri(transition_path)
        assert uri is not None
        handlers[uri] = DerivedActivityHandler(built.net, transition_path, definition)

    return CompiledEffectNet(
        built=built,
        entry=abs(entry_place),
        exit=abs(current),
        handlers=handlers,
        activities=tuple(d.declaration for d in definitions),
        definitions=tuple(definitions),
    )
