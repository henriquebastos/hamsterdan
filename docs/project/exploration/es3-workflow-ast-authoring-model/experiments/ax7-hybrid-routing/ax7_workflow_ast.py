"""AX7 spike AST — hybrid routing: one case keyed by type *and* predicate.

AX5 routed on which variant a union-returning activity produced; AX6
routed on the value's structure within one type. AX7 fuses them: a
``case`` names a variant type and optionally narrows it with a predicate
over *that variant's* fields —

    hybrid(
        evaluate,  # -> Approved | Rejected
        case(Approved, when=on(Approved).risk < 20, then=step(auto_processing)),
        case(Approved, then=step(senior_approval)),
        case(Rejected, then=step(manual_processing)),
    )

The frozen runtime makes this sound: ``enabledness.admitted`` matches the
arc's nominal color *before* evaluating its filter, so a predicate over
``Approved.risk`` can never raise on a ``Rejected`` token. The guard AST
therefore validates against the case's narrowed type — a ``when`` whose
root is not the case's variant is a shape error, and an unknown field on
the variant fails at proxy construction (AX6 machinery, unchanged).

Totality decisions, explicit as ever:

- every union member must be covered (AX5 exhaustiveness);
- within one variant, guarded cases are ordered-exclusive and exactly
  one *unguarded* case must come last — the variant's default. A case
  after the unguarded default could never match and is refused.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, is_dataclass
from types import MappingProxyType, UnionType
from typing import get_args, get_origin

from ax7_predicates import Predicate, _Boolean, roots, validate_null_safety
from petrus.motus.activity import ActivityDefinition, AsyncActivityDefinition

type Node = Activity | Sequence | HybridSwitch
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
class HybridCase:
    """One route: a variant color, an optional predicate over it, a body."""

    variant: str
    predicate: Predicate | None
    body: Node
    origin: Origin | None = field(default=None, compare=False)


@dataclass(frozen=True)
class HybridSwitch:
    """A union-returning activity routed by variant type and value guards."""

    name: str
    inputs: dict[str, str]
    variants: tuple[str, ...]  # union members, in annotation order
    cases: tuple[HybridCase, ...]  # authoring order
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))


def _color(annotation: object, subject: str) -> str | None:
    if annotation is type(None):
        return None
    if isinstance(annotation, UnionType) or get_origin(annotation) is not None:
        raise WorkflowShapeError(
            f"{subject} annotation {annotation!r} has no single nominal color "
            "(unions mean branching — use hybrid(); generics need a named dataclass)"
        )
    name = getattr(annotation, "__name__", None)
    if not isinstance(name, str) or not name:
        raise WorkflowShapeError(f"{subject} annotation {annotation!r} has no nominal name")
    return name


def step(definition: Definition) -> Activity:
    """Build a leaf from an activity definition; colors come from its hints."""
    name = definition.declaration.name
    result = _color(definition.result, f"activity {name!r} return")
    inputs: dict[str, str] = {}
    for parameter, annotation in definition.parameters.items():
        color = _color(annotation, f"activity {name!r} parameter {parameter!r}")
        if color is None:
            raise WorkflowShapeError(f"activity {name!r} parameter {parameter!r} is None-typed")
        inputs[parameter] = color
    return Activity(name=name, inputs=inputs, result=result, origin=_caller_origin())


def sequence(*steps: Node) -> Sequence:
    return Sequence(steps=steps, origin=_caller_origin())


def case(variant: type, *, when: Predicate | None = None, then: Node) -> HybridCase:
    """One hybrid route. ``when`` must read the case's own variant type.

    The narrowing is validated here: a predicate rooted in another type
    is a shape error, and the AX6 null-safety walk keeps raising filters
    unrepresentable. Field existence was already validated against the
    variant when the predicate was built (typed proxy).
    """
    name = getattr(variant, "__name__", None)
    if not isinstance(name, str) or not name:
        raise WorkflowShapeError(f"case variant {variant!r} has no nominal name")
    if when is not None:
        if not isinstance(when, _Boolean):
            raise WorkflowShapeError(
                f"case {name} when= needs a predicate expression object, got "
                f"{type(when).__name__} — build one with on({name})"
            )
        subjects = roots(when)
        if subjects != {name}:
            raise WorkflowShapeError(
                f"case {name} guard must read {name} fields, but reads "
                f"{sorted(subjects)} — the arc's color narrows the token to "
                f"{name} before the filter ever runs"
            )
        validate_null_safety(when)
    return HybridCase(variant=name, predicate=when, body=then, origin=_caller_origin())


def hybrid(definition: Definition, *cases: HybridCase) -> HybridSwitch:
    """Route a union-returning activity by variant type and value guards.

    Exhaustiveness has two levels, both enforced at construction because
    the frozen runtime parks or drops what nothing admits:

    - every union member appears in at least one case;
    - within a variant, exactly one unguarded case exists and it comes
      after every guarded one (the variant's default) — a case following
      the unguarded default could never match.
    """
    name = definition.declaration.name
    annotation = definition.result
    if not isinstance(annotation, UnionType):
        raise WorkflowShapeError(
            f"hybrid() needs a union-returning activity; {name!r} returns "
            f"{annotation!r} — use step() or branch() for single-type results"
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

    unknown = sorted({c.variant for c in cases} - set(variants))
    if unknown:
        raise WorkflowShapeError(f"hybrid on {name!r} has cases for unknown variants {unknown} (union: {variants})")
    per_variant: dict[str, list[HybridCase]] = {v: [] for v in variants}
    for guarded_case in cases:
        per_variant[guarded_case.variant].append(guarded_case)
    for variant, group in per_variant.items():
        if not group:
            raise WorkflowShapeError(f"hybrid on {name!r} covers no case for variant {variant}")
        defaults = [i for i, c in enumerate(group) if c.predicate is None]
        if not defaults:
            raise WorkflowShapeError(
                f"hybrid on {name!r}: variant {variant} has only guarded "
                f"cases — an unmatched token would park silently; add an "
                f"unguarded case({variant}, then=...) as its default"
            )
        if len(defaults) > 1 or defaults[0] != len(group) - 1:
            raise WorkflowShapeError(
                f"hybrid on {name!r}: variant {variant} must have exactly one "
                f"unguarded case and it must come last — later cases could "
                f"never match"
            )
        seen: list[Predicate] = []
        for guarded_case in group[:-1]:
            if guarded_case.predicate in seen:
                raise WorkflowShapeError(
                    f"hybrid on {name!r}: variant {variant} repeats predicate "
                    f"({guarded_case.predicate.cel()}) — it could never match"
                )
            seen.append(guarded_case.predicate)

    inputs: dict[str, str] = {}
    for parameter, parameter_annotation in definition.parameters.items():
        color = _color(parameter_annotation, f"activity {name!r} parameter {parameter!r}")
        if color is None:
            raise WorkflowShapeError(f"activity {name!r} parameter {parameter!r} is None-typed")
        inputs[parameter] = color
    if len(inputs) != 1:
        raise WorkflowShapeError(
            f"hybrid source {name!r} must take exactly one parameter in this spike, got {sorted(inputs)}"
        )
    return HybridSwitch(
        name=name,
        inputs=inputs,
        variants=tuple(variants),
        cases=tuple(cases),
        origin=_caller_origin(),
    )


def address(path: tuple[int, ...]) -> str:
    return "/" + "/".join(str(index) for index in path) if path else "/"
