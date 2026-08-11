"""AX4 spike AST — Activity leaves with inferred ports, Sequence, Parallel.

Evolves AX2's nodes with AX3's conclusion: the leaf is built from an
``@activity`` definition and stores the *inferred* input colors and
result color (symbolic — the AST still carries no code). ``Parallel``
arrives with explicit semantics: one incoming token is duplicated to
every branch by a generated split transition, and synchronization is a
downstream multi-input consumer.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import MappingProxyType, UnionType
from typing import get_origin

from petrus.motus.activity import ActivityDefinition, AsyncActivityDefinition

type Node = Activity | Sequence | Parallel
type Definition = ActivityDefinition | AsyncActivityDefinition


class WorkflowShapeError(ValueError):
    """A combinator or leaf was constructed with an impossible shape."""


@dataclass(frozen=True)
class Origin:
    filename: str
    line: int


def _caller_origin(depth: int = 2) -> Origin:
    frame = sys._getframe(depth)
    return Origin(filename=frame.f_code.co_filename, line=frame.f_lineno)


@dataclass(frozen=True)
class Activity:
    """Leaf: one activity with colors inferred from its typed definition."""

    name: str
    inputs: dict[str, str]  # parameter name -> color
    result: str | None  # None: sink
    doc: str | None = None
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))


@dataclass(frozen=True)
class Sequence:
    steps: tuple[Node, ...]
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.steps:
            raise WorkflowShapeError("sequence() needs at least one step")


@dataclass(frozen=True)
class Parallel:
    branches: tuple[Node, ...]
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if len(self.branches) < 2:
            raise WorkflowShapeError(f"parallel() needs at least two branches, got {len(self.branches)}")


def _color(annotation: object, subject: str) -> str | None:
    """AX3's safe-inference rule, minimal spike copy."""
    if annotation is type(None):
        return None
    if isinstance(annotation, UnionType) or get_origin(annotation) is not None:
        raise WorkflowShapeError(
            f"{subject} annotation {annotation!r} has no single nominal color "
            "(unions mean branching, generics need a named dataclass — AX3)"
        )
    name = getattr(annotation, "__name__", None)
    if not isinstance(name, str) or not name:
        raise WorkflowShapeError(f"{subject} annotation {annotation!r} has no nominal name")
    return name


def step(definition: Definition) -> Activity:
    """Build a leaf from an activity definition; colors come from its hints."""
    name = definition.declaration.name
    inputs: dict[str, str] = {}
    for parameter, annotation in definition.parameters.items():
        color = _color(annotation, f"activity {name!r} parameter {parameter!r}")
        if color is None:
            raise WorkflowShapeError(f"activity {name!r} parameter {parameter!r} is None-typed")
        inputs[parameter] = color
    result = _color(definition.result, f"activity {name!r} return")
    doc = definition.function.__doc__
    return Activity(
        name=name,
        inputs=inputs,
        result=result,
        doc=doc.strip().splitlines()[0] if doc else None,
        origin=_caller_origin(),
    )


def sequence(*steps: Node) -> Sequence:
    return Sequence(steps=steps, origin=_caller_origin())


def parallel(*branches: Node) -> Parallel:
    return Parallel(branches=branches, origin=_caller_origin())


def address(path: tuple[int, ...]) -> str:
    return "/" + "/".join(str(index) for index in path) if path else "/"
