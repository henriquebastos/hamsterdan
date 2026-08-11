"""AX3 spike — what typed activity signatures can safely tell the compiler.

Two pieces:

- ``infer_ports`` classifies an ``@activity``/``@async_activity``
  definition's annotations into inferable nominal colors or a loud,
  reasoned refusal. It never guesses: unions, optionals, and generic
  collections are refusals with the reason and the remedy in the message.
- ``PlaceBoundActivityHandler`` proves that *ports* — parameter-to-place
  bindings — are implementable above the frozen runtime: when two input
  places share one color, typed color-matching derivation must refuse,
  but place identity still disambiguates perfectly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType, UnionType
from typing import get_origin

from petrus.impetus.petrinet import Binding, Net, NetPath, Token
from petrus.motus.activity import (
    ActivityDefinition,
    ActivityInvocation,
    AsyncActivityDefinition,
)

type Definition = ActivityDefinition | AsyncActivityDefinition


class InferenceError(ValueError):
    """An annotation cannot be safely mapped to one nominal color."""


@dataclass(frozen=True)
class InferredPorts:
    """Colors safely derived from one typed activity definition."""

    inputs: Mapping[str, str]
    result: str | None  # None means the activity is a sink (returns None)

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))


def _classify(annotation: object, subject: str) -> str | None:
    if annotation is type(None):
        return None
    if isinstance(annotation, UnionType):
        raise InferenceError(
            f"{subject} is the union {annotation}: a union has no single nominal color; "
            "unions mean branching, which must be lowered to one typed output place per "
            "variant (AX5), not inferred as one color"
        )
    if get_origin(annotation) is not None:
        raise InferenceError(
            f"{subject} is the generic {annotation}: its nominal name erases the parameter "
            f"({get_origin(annotation).__name__!r} would collide with every other collection); "
            "wrap the collection in a named dataclass"
        )
    name = getattr(annotation, "__name__", None)
    if not isinstance(name, str) or not name:
        raise InferenceError(f"{subject} annotation {annotation!r} has no nominal type name")
    return name


def infer_ports(definition: Definition) -> InferredPorts:
    """Derive input and result colors from a typed activity definition."""
    activity_name = definition.declaration.name
    inputs: dict[str, str] = {}
    for parameter, annotation in definition.parameters.items():
        color = _classify(annotation, f"activity {activity_name!r} parameter {parameter!r}")
        if color is None:
            raise InferenceError(
                f"activity {activity_name!r} parameter {parameter!r} is annotated None: an input must carry a token"
            )
        inputs[parameter] = color
    result = _classify(definition.result, f"activity {activity_name!r} return")
    return InferredPorts(inputs=inputs, result=result)


@dataclass(frozen=True)
class PlaceBoundActivityHandler:
    """A port-style prepare/project bridge: parameters bind to *places*.

    Where ``DerivedActivityHandler`` matches parameters to input arcs by
    color (and loudly refuses two arcs with one color), this handler maps
    each parameter name to one source place path. Place identity is
    always unambiguous — this is the AX3 evidence that named ports need
    no Petrus change.
    """

    net: Net = field(repr=False)
    transition: NetPath
    activity: Definition
    bindings: Mapping[str, str]  # parameter name -> source place path
    output: NetPath
    _result_color: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", MappingProxyType(dict(self.bindings)))
        expected = set(self.activity.parameters)
        bound = set(self.bindings)
        if bound != expected:
            raise ValueError(
                f"place bindings for {self.transition} must cover parameters {sorted(expected)}, got {sorted(bound)}"
            )
        sources = {str(arc.source) for arc in self.net.inputs(self.transition)}
        for parameter, place in self.bindings.items():
            if place not in sources:
                raise ValueError(
                    f"parameter {parameter!r} binds to {place!r}, which is not an input "
                    f"place of {self.transition} (inputs: {sorted(sources)})"
                )
        result = infer_ports(self.activity).result
        if result is None:
            raise ValueError(
                f"activity {self.activity.declaration.name!r} returns None; sink projection is AX-future work"
            )
        object.__setattr__(self, "_result_color", result)

    def prepare(self, binding: Binding) -> ActivityInvocation:
        payload: dict[str, object] = {}
        for parameter, place in self.bindings.items():
            selected = next(
                (tokens for source, tokens in binding.consumed if str(source) == place),
                None,
            )
            if selected is None or len(selected) != 1:
                raise ValueError(f"parameter {parameter!r} requires exactly one consumed token from {place!r}")
            payload[parameter] = selected[0].data
        return ActivityInvocation(self.activity.declaration.name, input=payload)

    def project(self, binding: Binding, result: object) -> Mapping[NetPath, Sequence[Token]]:
        del binding
        return {self.output: (Token(self._result_color, result),)}
