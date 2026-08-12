"""AX10 spike — three authoring layers over the same combinator core.

Style A (nested combinators) is the core itself — ``ax10_ast.sequence``
etc. This module adds the three challenger spellings:

- ``Flow`` — an immutable fluent chain (each call returns a new value;
  prefix reuse is safe by construction).
- ``WorkflowBuilder`` — a context-manager builder with an explicit
  mutable scope stack (the style's essential liability, made honest).
- ``build_workflow`` — a generator driver: yields are collected into a
  sequence, and the value sent back is a **symbolic handle** that
  refuses to be branched on, mirroring the AX9-B tracing boundary.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from ax10_ast import Node, Parallel, Retry, Sequence, coerce, parallel, retry, sequence

# --- Style B: immutable fluent chain ---------------------------------------


@dataclass(frozen=True)
class Flow:
    """A fluent, immutable prefix of a sequential workflow."""

    nodes: tuple[Node, ...] = ()

    @staticmethod
    def start(first: object) -> Flow:
        return Flow((coerce(first, position="Flow.start"),))

    def then(self, step: object) -> Flow:
        return Flow((*self.nodes, coerce(step, position="Flow.then")))

    def parallel(self, *branches: object) -> Flow:
        return Flow((*self.nodes, parallel(*branches)))

    def retry(self, body: object, *, limit: int) -> Flow:
        return Flow((*self.nodes, retry(body, limit=limit)))

    def build(self) -> Node:
        if not self.nodes:
            raise TypeError("cannot build an empty Flow")
        return sequence(*self.nodes)


# --- Style C: context-manager builder ---------------------------------------


class BuilderError(RuntimeError):
    """The builder was used outside its live scope discipline."""


class WorkflowBuilder:
    """Statement-ordered builder. Structure comes from a mutable scope
    stack — the hidden state this style is evaluated for."""

    def __init__(self) -> None:
        self._stack: list[tuple[str, list[Node]]] = [("sequence", [])]
        self._built = False

    def _top(self) -> list[Node]:
        if self._built:
            raise BuilderError("this WorkflowBuilder is already built; builders are single-use")
        return self._stack[-1][1]

    def do(self, name: object) -> None:
        self._top().append(coerce(name, position="WorkflowBuilder.do"))

    @contextmanager
    def parallel(self):
        self._top()
        self._stack.append(("parallel", []))
        yield self
        kind, branches = self._stack.pop()
        assert kind == "parallel"
        if len(branches) < 2:
            raise BuilderError(
                "a parallel scope needs at least two branches; wrap multi-step branches in `with builder.branch():`"
            )
        self._top().append(Parallel(tuple(branches)))

    @contextmanager
    def branch(self):
        if self._stack[-1][0] != "parallel":
            raise BuilderError("branch() is only meaningful inside a parallel scope")
        self._stack.append(("sequence", []))
        yield self
        _, steps = self._stack.pop()
        if not steps:
            raise BuilderError("a branch scope must contain at least one step")
        self._top().append(steps[0] if len(steps) == 1 else Sequence(tuple(steps)))

    @contextmanager
    def retry(self, *, limit: int):
        self._top()
        self._stack.append(("sequence", []))
        yield self
        _, steps = self._stack.pop()
        if not steps:
            raise BuilderError("a retry scope must contain at least one step")
        body = steps[0] if len(steps) == 1 else Sequence(tuple(steps))
        self._top().append(Retry(body, limit))

    def build(self) -> Node:
        if len(self._stack) != 1:
            raise BuilderError("cannot build inside an open scope")
        self._built = True
        return sequence(*self._stack[0][1])


# --- Style D: generator driver ----------------------------------------------


class SymbolicResult:
    """The value sent back for each yield. It names a step, nothing more —
    branching on it would smuggle Python control flow into workflow
    structure, which AX9-B already proved cannot be durable."""

    def __init__(self, index: int) -> None:
        self.index = index

    def __bool__(self) -> bool:
        raise TypeError(
            f"the result of workflow step {self.index} is symbolic at authoring "
            "time; branch with workflow combinators (switch/branch/retry), not "
            "Python `if`"
        )

    __iter__ = __len__ = __index__ = __bool__  # type: ignore[assignment]


def build_workflow(program) -> Node:
    """Run the generator once, collecting yields into a sequence."""

    generator = program()
    nodes: list[Node] = []
    handle: object = None
    while True:
        try:
            value = generator.send(handle)
        except StopIteration:
            break
        nodes.append(coerce(value, position=f"workflow yield {len(nodes)}"))
        handle = SymbolicResult(len(nodes) - 1)
    return sequence(*nodes)
