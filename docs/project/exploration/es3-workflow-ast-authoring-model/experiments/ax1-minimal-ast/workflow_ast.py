"""AX1 spike — minimal workflow AST.

Three nodes only: ``Activity`` (leaf, a symbolic reference to a
worker-resolved activity name), ``Sequence``, and ``Parallel``. No net
generation, no execution — construction, traversal, printing, and a
canonical form for determinism checks.

Design decisions under test (recorded in index.md):

- Node identity is structural. ``origin`` (source location) is metadata
  and excluded from equality, so two builds of the same source produce
  equal ASTs — the property AX0 demands of any deterministic compiler.
- Activities are symbolic. The leaf stores the activity *name* exactly as
  the Petrus ``Worker`` resolves it; the Python callable is only a
  convenient source for name and docstring, never stored.
- The canonical form excludes origin and is JSON-faithful, mirroring the
  ``NetDefinitionV3`` stance: durable artifacts carry no Python code.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

type Node = Activity | Sequence | Parallel
type StepSource = Node | Callable[..., object] | str


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
    """Leaf: one worker-dispatched activity, referenced by name."""

    name: str
    doc: str | None = None
    origin: Origin | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Sequence:
    """Steps run one after another; each starts after the previous ends."""

    steps: tuple[Node, ...]
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.steps:
            raise WorkflowShapeError("sequence() needs at least one step; an empty sequence has no behavior")


@dataclass(frozen=True)
class Parallel:
    """Branches start together and run independently."""

    branches: tuple[Node, ...]
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if len(self.branches) < 2:
            raise WorkflowShapeError(
                f"parallel() needs at least two branches, got {len(self.branches)}; "
                "a single branch is just the step itself"
            )


def activity(ref: Callable[..., object] | str, *, doc: str | None = None) -> Activity:
    """Build a leaf from an activity name or an activity callable.

    A callable contributes its ``__name__`` and ``__doc__``; it is not
    retained. The name must match the worker-side activity registration.
    """
    if callable(ref):
        name = ref.__name__
        doc = doc if doc is not None else ref.__doc__
    else:
        name = ref
    if doc is not None:
        doc = doc.strip().splitlines()[0]
    return Activity(name=name, doc=doc, origin=_caller_origin())


def _coerce(step: StepSource) -> Node:
    if isinstance(step, Activity | Sequence | Parallel):
        return step
    return activity(step)


def sequence(*steps: StepSource) -> Sequence:
    return Sequence(steps=tuple(_coerce(s) for s in steps), origin=_caller_origin())


def parallel(*branches: StepSource) -> Parallel:
    return Parallel(branches=tuple(_coerce(b) for b in branches), origin=_caller_origin())


def children(node: Node) -> tuple[Node, ...]:
    match node:
        case Activity():
            return ()
        case Sequence(steps=steps):
            return steps
        case Parallel(branches=branches):
            return branches


def walk(node: Node) -> Iterator[tuple[tuple[int, ...], Node]]:
    """Preorder traversal yielding (structural path, node) pairs.

    The path — child indexes from the root — is the node's stable
    identity, the AX candidate for deterministic ``NetPath`` derivation.
    """

    def visit(path: tuple[int, ...], current: Node) -> Iterator[tuple[tuple[int, ...], Node]]:
        yield path, current
        for index, child in enumerate(children(current)):
            yield from visit((*path, index), child)

    yield from visit((), node)


def render(node: Node) -> str:
    """Human-readable indented tree with structural paths."""
    lines = []
    for path, current in walk(node):
        indent = "  " * len(path)
        address = "/" + "/".join(str(i) for i in path) if path else "/"
        match current:
            case Activity(name=name, doc=doc):
                suffix = f"  # {doc}" if doc else ""
                lines.append(f"{indent}activity {name} [{address}]{suffix}")
            case Sequence():
                lines.append(f"{indent}sequence [{address}]")
            case Parallel():
                lines.append(f"{indent}parallel [{address}]")
    return "\n".join(lines)


def canonical(node: Node) -> dict[str, object]:
    """JSON-faithful structural form. Excludes origin; carries no code."""
    match node:
        case Activity(name=name, doc=doc):
            return {"kind": "activity", "name": name, "doc": doc}
        case Sequence(steps=steps):
            return {"kind": "sequence", "steps": [canonical(s) for s in steps]}
        case Parallel(branches=branches):
            return {"kind": "parallel", "branches": [canonical(b) for b in branches]}


def fingerprint(node: Node) -> str:
    """Stable digest of the canonical form, for compile determinism checks."""
    payload = json.dumps(canonical(node), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
