"""AX8 spike AST — a tree-shaped retry combinator lowered to a cyclic net.

The hypothesis under test: *the authoring AST may remain a tree even when
compilation produces a cyclic graph.* ``Retry`` is one tree node — the
cycle exists only in the lowering, as one loop-back arc.

    retry(
        charge,  # -> Confirmed | Transient | Fatal
        case(Confirmed, then=step(record)),
        case(Fatal, then=step(refund)),
        retryable=Transient,
        rearm=rearm_charge,       # pure typed: Transient -> ChargeRequest
        limit=3,
        exhausted=step(escalate), # Transient tokens at the attempt limit
    )

Explicit design decisions (workflow-level retry, not worker-level):

- **Loop state lives in token data.** The retryable variant must carry
  the counter field (default ``attempt: int``) as a declared domain
  field — durable, replayable, visible in every marking and predicate.
  No hidden engine state, no compiler-stamped shadow keys.
- **The loop guard is a compiled predicate.** ``on(Transient).attempt <
  limit`` is built with the AX6 typed proxy at construction (so the
  counter field is validated to exist and be an int) and rendered to the
  two CEL filters: loop-back (``attempt < 3``) and exhausted
  (``!(attempt < 3)``).
- **Re-arming is a typed pure transform.** ``rearm`` maps the retryable
  variant back to the source activity's input type; its signature is
  validated at construction and it lowers onto the frozen
  ``derive_typed_transform`` — inline, deterministic, re-executed on
  replay like any pure handler. Incrementing the counter is rearm's
  deterministic job; the compiler cannot prove it increments (see the
  bounded-driving diagnostic in the tests).
- **Exits are total.** Non-retryable variants need exactly one case each
  (AX5 exhaustiveness); the mandatory ``exhausted`` body receives the
  retryable variant once the counter reaches the limit.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields, is_dataclass
from types import MappingProxyType, UnionType
from typing import get_args, get_origin, get_type_hints

from ax8_predicates import on
from petrus.motus.activity import ActivityDefinition, AsyncActivityDefinition

type Node = Activity | Sequence | Retry
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
    """One exit branch: the variant color it consumes and its body."""

    variant: str
    body: Node
    origin: Origin | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Retry:
    """A union-returning activity whose retryable variant loops back."""

    name: str
    inputs: dict[str, str]  # the source activity's single parameter
    variants: tuple[str, ...]  # all union members, annotation order
    retryable: str
    counter: str
    limit: int
    loop_cel: str  # e.g. "(attempt < 3)"
    exhausted_cel: str  # e.g. "!(attempt < 3)"
    rearm_name: str
    exhausted: Node
    cases: tuple[Case, ...]  # non-retryable variants, annotation order
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))


def _color(annotation: object, subject: str) -> str | None:
    if annotation is type(None):
        return None
    if isinstance(annotation, UnionType) or get_origin(annotation) is not None:
        raise WorkflowShapeError(
            f"{subject} annotation {annotation!r} has no single nominal color "
            "(unions mean branching; generics need a named dataclass)"
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


def case(variant: type, *, then: Node) -> Case:
    name = getattr(variant, "__name__", None)
    if not isinstance(name, str) or not name:
        raise WorkflowShapeError(f"case variant {variant!r} has no nominal name")
    return Case(variant=name, body=then, origin=_caller_origin())


def retry(
    definition: Definition,
    *cases: Case,
    retryable: type,
    rearm,
    limit: int,
    exhausted: Node,
    counter: str = "attempt",
) -> Retry:
    """One activity attempted up to ``limit`` times via a loop-back cycle."""
    name = definition.declaration.name
    annotation = definition.result
    if not isinstance(annotation, UnionType):
        raise WorkflowShapeError(
            f"retry() needs a union-returning activity; {name!r} returns "
            f"{annotation!r} — a retry decision is a branch on the result type"
        )
    members = list(get_args(annotation))
    variants: list[str] = []
    for member in members:
        member_name = _color(member, f"activity {name!r} union member")
        if member_name is None:
            raise WorkflowShapeError(f"activity {name!r} union includes None; model absence as a variant type")
        if not is_dataclass(member):
            raise WorkflowShapeError(
                f"activity {name!r} union member {member_name} must be a "
                "dataclass so the variant survives payload conversion"
            )
        variants.append(member_name)
    if len(set(variants)) != len(variants):
        raise WorkflowShapeError(f"activity {name!r} union repeats a member: {variants}")
    retryable_name = getattr(retryable, "__name__", None)
    if retryable_name not in variants:
        raise WorkflowShapeError(f"retry on {name!r}: retryable {retryable_name!r} is not a union member of {variants}")

    if not isinstance(limit, int) or limit < 1:
        raise WorkflowShapeError(f"retry on {name!r}: limit must be a positive int, got {limit!r}")
    counter_fields = {f.name for f in fields(retryable)}
    if counter not in counter_fields:
        raise WorkflowShapeError(
            f"retry on {name!r}: retryable {retryable_name} needs the counter "
            f"field {counter!r} (an int) to carry loop state in token data; "
            f"it has {sorted(counter_fields)}"
        )
    # The typed proxy validates the counter is an orderable int field and
    # renders the durable loop guard.
    loop_predicate = getattr(on(retryable), counter) < limit
    loop_cel = loop_predicate.cel()

    inputs: dict[str, str] = {}
    for parameter, parameter_annotation in definition.parameters.items():
        color = _color(parameter_annotation, f"activity {name!r} parameter {parameter!r}")
        if color is None:
            raise WorkflowShapeError(f"activity {name!r} parameter {parameter!r} is None-typed")
        inputs[parameter] = color
    if len(inputs) != 1:
        raise WorkflowShapeError(
            f"retry source {name!r} must take exactly one parameter in this spike, got {sorted(inputs)}"
        )
    [(input_parameter, input_color)] = inputs.items()
    del input_parameter

    rearm_hints = get_type_hints(rearm)
    rearm_name = getattr(rearm, "__name__", repr(rearm))
    rearm_parameters = {k: v for k, v in rearm_hints.items() if k != "return"}
    if list(rearm_parameters.values()) != [retryable]:
        raise WorkflowShapeError(
            f"retry on {name!r}: rearm {rearm_name!r} must take exactly one "
            f"{retryable_name} parameter, got {rearm_parameters!r}"
        )
    rearm_result = _color(rearm_hints.get("return"), f"rearm {rearm_name!r} return")
    if rearm_result != input_color:
        raise WorkflowShapeError(
            f"retry on {name!r}: rearm {rearm_name!r} must return {input_color} "
            f"(the activity's input) to close the loop, got {rearm_result!r}"
        )

    expected = [v for v in variants if v != retryable_name]
    covered = [c.variant for c in cases]
    if len(set(covered)) != len(covered):
        raise WorkflowShapeError(f"retry on {name!r} has duplicate cases: {sorted(covered)}")
    missing = [v for v in expected if v not in covered]
    extra = [c for c in covered if c not in expected]
    if missing or extra:
        raise WorkflowShapeError(
            f"retry on {name!r} cases must cover exactly the non-retryable "
            f"variants {expected}: missing {missing or 'none'}, unknown {extra or 'none'} "
            f"(the retryable variant exits through exhausted=)"
        )
    ordered = tuple(sorted(cases, key=lambda c: expected.index(c.variant)))

    return Retry(
        name=name,
        inputs=inputs,
        variants=tuple(variants),
        retryable=retryable_name,
        counter=counter,
        limit=limit,
        loop_cel=loop_cel,
        exhausted_cel=f"!{loop_cel}",
        rearm_name=rearm_name,
        exhausted=exhausted,
        cases=ordered,
        origin=_caller_origin(),
    )


def address(path: tuple[int, ...]) -> str:
    return "/" + "/".join(str(index) for index in path) if path else "/"
