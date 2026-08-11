"""AX2 spike AST — deliberate evolved copy of the AX1 nodes.

Only what lowering needs: ``Activity`` leaves and ``Sequence``. The AX2
leaf grows explicit ``request`` and ``result`` colors (nominal names,
exactly what the frozen Petrus runtime stores); inference is AX3's
question and is deliberately absent here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

type Node = Activity | Sequence


class WorkflowShapeError(ValueError):
    """A combinator was constructed with an impossible shape."""


@dataclass(frozen=True)
class Origin:
    """Authoring source location. Metadata only — never identity."""

    filename: str
    line: int


def _caller_origin(depth: int = 2) -> Origin:
    frame = sys._getframe(depth)
    return Origin(filename=frame.f_code.co_filename, line=frame.f_lineno)


@dataclass(frozen=True)
class Activity:
    """Leaf: one worker-dispatched activity with explicit token colors."""

    name: str
    request: str
    result: str
    doc: str | None = None
    origin: Origin | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Sequence:
    """Steps run one after another; each consumes the previous result."""

    steps: tuple[Node, ...]
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.steps:
            raise WorkflowShapeError("sequence() needs at least one step; an empty sequence has no behavior")


def _color(value: type | str, subject: str) -> str:
    if isinstance(value, str):
        if not value:
            raise WorkflowShapeError(f"{subject} color must be a non-empty name")
        return value
    return value.__name__


def activity(name: str, *, request: type | str, result: type | str, doc: str | None = None) -> Activity:
    return Activity(
        name=name,
        request=_color(request, f"activity {name!r} request"),
        result=_color(result, f"activity {name!r} result"),
        doc=doc,
        origin=_caller_origin(),
    )


def sequence(*steps: Node) -> Sequence:
    return Sequence(steps=steps, origin=_caller_origin())


def address(path: tuple[int, ...]) -> str:
    """Human-readable structural address, as in AX1 (``/``, ``/1/0``)."""
    return "/" + "/".join(str(index) for index in path) if path else "/"
