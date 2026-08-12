"""AX10 spike — one minimal semantic core the authoring styles compete over.

The nodes are deliberately a structural skeleton (names only, no colors,
ports, or guards — those are AX3–AX8 territory): the question here is
purely *how Python spells the tree*, so every style must produce the
same canonical AST or it is not an authoring layer, it is a different
model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Activity:
    name: str


@dataclass(frozen=True)
class Sequence:
    steps: tuple[Node, ...]


@dataclass(frozen=True)
class Parallel:
    branches: tuple[Node, ...]


@dataclass(frozen=True)
class Retry:
    body: Node
    limit: int


Node = Activity | Sequence | Parallel | Retry


def coerce(value: object, *, position: str) -> Node:
    """Accept an activity name or a node; refuse everything else loudly."""

    if isinstance(value, str):
        if not value:
            raise TypeError(f"{position}: activity name must be non-empty")
        return Activity(value)
    if isinstance(value, (Activity, Sequence, Parallel, Retry)):
        return value
    build = getattr(value, "build", None)
    if callable(build):
        return coerce(build(), position=position)
    raise TypeError(f"{position}: expected an activity name or workflow node, got {type(value).__name__} ({value!r})")


def sequence(*steps: object) -> Node:
    """Sequential composition; flattens nesting, collapses singletons."""

    coerced: list[Node] = []
    for index, value in enumerate(steps):
        node = coerce(value, position=f"sequence step {index}")
        if isinstance(node, Sequence):
            coerced.extend(node.steps)
        else:
            coerced.append(node)
    if not coerced:
        raise TypeError("sequence requires at least one step")
    if len(coerced) == 1:
        return coerced[0]
    return Sequence(tuple(coerced))


def parallel(*branches: object) -> Parallel:
    if len(branches) < 2:
        raise TypeError("parallel requires at least two branches")
    return Parallel(tuple(coerce(value, position=f"parallel branch {index}") for index, value in enumerate(branches)))


def retry(body: object, *, limit: int) -> Retry:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise TypeError(f"retry limit must be a positive integer, got {limit!r}")
    return Retry(coerce(body, position="retry body"), limit)


def render(node: Node, indent: int = 0) -> str:
    """Human-readable tree, used by the record and readability probes."""

    pad = "  " * indent
    match node:
        case Activity(name):
            return f"{pad}activity {name}"
        case Sequence(steps):
            inner = "\n".join(render(step, indent + 1) for step in steps)
            return f"{pad}sequence\n{inner}"
        case Parallel(branches):
            inner = "\n".join(render(branch, indent + 1) for branch in branches)
            return f"{pad}parallel\n{inner}"
        case Retry(body, limit):
            return f"{pad}retry limit={limit}\n{render(body, indent + 1)}"
