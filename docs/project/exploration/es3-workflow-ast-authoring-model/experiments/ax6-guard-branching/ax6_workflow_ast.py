"""AX6 spike AST — value routing over one data type via guard predicates.

AX5 branched on *which type* an activity produced. AX6 branches on the
*value's structure* when every branch consumes the same type: no
artificial micro-types, no union return. The combinator is explicit:

    branch(
        when(app.score > 700, then=step(fast_track)),
        otherwise=step(manual_review),
    )

Policy decisions made explicitly, not silently:

- ``otherwise`` is **required**: the frozen runtime parks a token no
  input arc admits, so totality must be unrepresentable to break.
- Cases are **ordered-exclusive**: lowering conjoins each case with the
  negations of every earlier case (``p2 && !p1``), so overlapping
  authoring predicates route deterministically by declaration order —
  first match wins, XOR by construction, no runtime priority feature
  needed. The alternative (raw overlapping filters = nondeterministic
  Petri competition) is demonstrated but not adopted; see the tests.
- Structurally identical duplicate predicates are rejected at
  construction (the later case would be unreachable); arbitrary semantic
  overlap is statically undecidable and is *made harmless* by the
  ordered-exclusive lowering instead of pretended away.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import MappingProxyType, UnionType
from typing import get_origin

from ax6_predicates import Predicate, _Boolean, roots, validate_null_safety
from petrus.motus.activity import ActivityDefinition, AsyncActivityDefinition

type Node = Activity | Sequence | GuardBranch
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
class GuardCase:
    """One guarded route: a predicate over the subject type, and a body."""

    predicate: Predicate
    body: Node
    origin: Origin | None = field(default=None, compare=False)


@dataclass(frozen=True)
class GuardBranch:
    """Value routing: one subject color, ordered guarded cases, a default."""

    subject: str  # the single root color every predicate reads
    cases: tuple[GuardCase, ...]
    otherwise: Node
    origin: Origin | None = field(default=None, compare=False)


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


def when(predicate: Predicate, *, then: Node) -> GuardCase:
    """One guarded case. The predicate must be an expression object.

    Null-safety is enforced here: a comparison over an optional field
    without a securing ``is_not_null()`` would *raise* at evaluation,
    which the runtime reads as not-admitted — the token would park
    silently instead of routing.
    """
    if not isinstance(predicate, _Boolean):
        raise WorkflowShapeError(
            f"when() needs a predicate expression object, got "
            f"{type(predicate).__name__} — build one with on(Type) or trace()"
        )
    validate_null_safety(predicate)
    return GuardCase(predicate=predicate, body=then, origin=_caller_origin())


def branch(*cases: GuardCase, otherwise: Node) -> GuardBranch:
    """Ordered-exclusive value routing with a mandatory default.

    All predicates must read one root type — that type is the branch
    subject and must match the upstream place color. Declaration order is
    semantic: lowering makes case *n* fire only when cases ``1..n-1`` do
    not match, so the first matching case wins deterministically.
    """
    if not cases:
        raise WorkflowShapeError("branch() needs at least one when() case")
    subjects: set[str] = set()
    for guard in cases:
        subjects |= roots(guard.predicate)
    if len(subjects) != 1:
        raise WorkflowShapeError(
            f"branch() predicates must read exactly one subject type, got "
            f"{sorted(subjects) or 'none'} — a branch routes tokens of one color"
        )
    seen: list[Predicate] = []
    for index, guard in enumerate(cases):
        if guard.predicate in seen:
            raise WorkflowShapeError(
                f"branch() case {index} repeats an earlier predicate ({guard.predicate.cel()}) — it could never match"
            )
        seen.append(guard.predicate)
    [subject] = subjects
    return GuardBranch(subject=subject, cases=cases, otherwise=otherwise, origin=_caller_origin())


def address(path: tuple[int, ...]) -> str:
    return "/" + "/".join(str(index) for index in path) if path else "/"
