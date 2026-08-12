"""AX5 spike AST — branching by output type via an explicit switch combinator.

The union return annotation is the *trigger and the validator*, not the
topology: `step()` keeps refusing unions (AX3), and `switch(definition,
case(...), ...)` is the explicit combinator that turns a union-returning
activity into one typed branch per variant. Exhaustiveness is checked at
construction — the runtime silently drops unrouted tokens, so the AST
layer must make non-exhaustive switches unrepresentable.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, is_dataclass
from types import MappingProxyType, UnionType
from typing import get_args, get_origin

from petrus.motus.activity import ActivityDefinition, AsyncActivityDefinition

type Node = Activity | Sequence | TypeSwitch
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
class Case:
    """One switch branch: the variant color it consumes and its body."""

    variant: str
    body: Node
    origin: Origin | None = field(default=None, compare=False)


@dataclass(frozen=True)
class TypeSwitch:
    """One union-returning activity exploded into one typed branch per variant."""

    name: str
    inputs: dict[str, str]
    variants: tuple[str, ...]  # union members, in annotation order
    cases: tuple[Case, ...]
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))


def _color(annotation: object, subject: str) -> str | None:
    if annotation is type(None):
        return None
    if isinstance(annotation, UnionType) or get_origin(annotation) is not None:
        raise WorkflowShapeError(
            f"{subject} annotation {annotation!r} has no single nominal color "
            "(unions mean branching — use switch(); generics need a named dataclass)"
        )
    name = getattr(annotation, "__name__", None)
    if not isinstance(name, str) or not name:
        raise WorkflowShapeError(f"{subject} annotation {annotation!r} has no nominal name")
    return name


def _leaf_inputs(definition: Definition) -> dict[str, str]:
    name = definition.declaration.name
    inputs: dict[str, str] = {}
    for parameter, annotation in definition.parameters.items():
        color = _color(annotation, f"activity {name!r} parameter {parameter!r}")
        if color is None:
            raise WorkflowShapeError(f"activity {name!r} parameter {parameter!r} is None-typed")
        inputs[parameter] = color
    return inputs


def step(definition: Definition) -> Activity:
    """Build a leaf from an activity definition; colors come from its hints."""
    name = definition.declaration.name
    result = _color(definition.result, f"activity {name!r} return")
    return Activity(
        name=name,
        inputs=_leaf_inputs(definition),
        result=result,
        origin=_caller_origin(),
    )


def sequence(*steps: Node) -> Sequence:
    return Sequence(steps=steps, origin=_caller_origin())


def case(variant: type, *, then: Node) -> Case:
    name = getattr(variant, "__name__", None)
    if not isinstance(name, str) or not name:
        raise WorkflowShapeError(f"case variant {variant!r} has no nominal name")
    return Case(variant=name, body=then, origin=_caller_origin())


def switch(definition: Definition, *cases: Case) -> TypeSwitch:
    """Explode a union-returning activity into one typed branch per variant.

    Exhaustiveness is enforced here: every union member needs exactly one
    case and every case must name a union member — the frozen runtime
    silently drops tokens no output arc admits, so missing coverage must
    be unrepresentable, not discovered at runtime.
    """
    name = definition.declaration.name
    annotation = definition.result
    if not isinstance(annotation, UnionType):
        raise WorkflowShapeError(
            f"switch() needs a union-returning activity; {name!r} returns "
            f"{annotation!r} — use step() for single-result activities"
        )
    variants: list[str] = []
    for member in get_args(annotation):
        member_name = _color(member, f"activity {name!r} union member")
        if member_name is None:
            raise WorkflowShapeError(
                f"activity {name!r} union includes None; optional results are "
                "not a branch — model absence as an explicit variant type"
            )
        if not is_dataclass(member):
            raise WorkflowShapeError(
                f"activity {name!r} union member {member_name} must be a "
                "dataclass so the variant survives payload conversion"
            )
        variants.append(member_name)
    if len(set(variants)) != len(variants):
        raise WorkflowShapeError(f"activity {name!r} union repeats a member: {variants}")

    covered = [c.variant for c in cases]
    if len(set(covered)) != len(covered):
        raise WorkflowShapeError(f"switch on {name!r} has duplicate cases: {sorted(covered)}")
    missing = [v for v in variants if v not in covered]
    extra = [c for c in covered if c not in variants]
    if missing or extra:
        raise WorkflowShapeError(
            f"switch on {name!r} must cover exactly {list(variants)}: "
            f"missing {missing or 'none'}, unknown {extra or 'none'}"
        )
    inputs = _leaf_inputs(definition)
    if len(inputs) != 1:
        raise WorkflowShapeError(
            f"switch source {name!r} must take exactly one parameter in this spike, got {sorted(inputs)}"
        )
    ordered = tuple(sorted(cases, key=lambda c: variants.index(c.variant)))
    return TypeSwitch(
        name=name,
        inputs=inputs,
        variants=tuple(variants),
        cases=ordered,
        origin=_caller_origin(),
    )


def address(path: tuple[int, ...]) -> str:
    return "/" + "/".join(str(index) for index in path) if path else "/"
