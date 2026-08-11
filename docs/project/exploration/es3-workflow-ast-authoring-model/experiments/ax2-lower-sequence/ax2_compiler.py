"""AX2 spike — lower ``Activity`` and ``Sequence`` onto the frozen Petrus ``Net``.

Lowering contract (threaded fragments):

- A compiled fragment is a function from an **entry place** to an **exit
  place**. An ``Activity`` leaf owns one transition and one exit place;
  a ``Sequence`` owns nothing — it threads its children so each step's
  exit place *is* the next step's entry place. No glue transitions.
- Generated paths derive only from the AST structure, never from object
  identity or time, so compilation is deterministic (AX0 requirement):
  entry place ``w.entry``; a leaf at structural address (1, 0) becomes
  transition ``w.1_0.<activity>`` and exit place ``w.1_0.out``.
- Colors: the entry place carries the root request color; each leaf's
  exit place carries its result color. ``Net`` resolves place colors
  onto the incident arcs, which is exactly what
  ``DerivedActivityHandler`` matches parameters and results against.
- Handlers: each generated transition declares the activity name as its
  handler symbol (readable, matching production convention) and the
  compiler binds a per-occurrence ``DerivedActivityHandler`` by exact
  handler ``NetUri``, so the same activity may appear at several
  transitions without collision.
- Source map: every AST address maps to its generated element paths and
  authoring origin, and every generated path maps back to its AST
  address.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ax2_workflow_ast import Activity, Node, Sequence, address
from petrus.impetus.binding import ActivityHandler, DerivedActivityHandler, Handler
from petrus.impetus.dsl import BuiltNet, NetSpec, PlaceSpec
from petrus.impetus.petrinet import NetPath
from petrus.impetus.petrinet.schema import NetUri
from petrus.motus.activity import ActivityDeclaration, ActivityDefinition


class LoweringError(ValueError):
    """The workflow AST cannot be lowered onto a valid net."""


@dataclass(frozen=True)
class SourceMapEntry:
    """Generated elements owned by one AST node, keyed by its address."""

    node: str  # e.g. "activity review" or "sequence"
    origin: str | None  # "file:line" authoring location
    transition: str | None = None
    exit_place: str | None = None


@dataclass(frozen=True)
class CompiledWorkflow:
    """One deterministic lowering of a workflow AST."""

    built: BuiltNet
    entry: NetPath
    exit: NetPath
    handlers: Mapping[NetUri | str, Handler | ActivityHandler]
    activities: tuple[ActivityDeclaration, ...]
    source_map: Mapping[str, SourceMapEntry] = field(default_factory=dict)
    generated_by: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "source_map", MappingProxyType(dict(self.source_map)))
        object.__setattr__(self, "generated_by", MappingProxyType(dict(self.generated_by)))


def request_color(node: Node) -> str:
    match node:
        case Activity(request=request):
            return request
        case Sequence(steps=steps):
            return request_color(steps[0])


def result_color(node: Node) -> str:
    match node:
        case Activity(result=result):
            return result
        case Sequence(steps=steps):
            return result_color(steps[-1])


def _label(node: Node, path: tuple[int, ...]) -> str:
    kind = f"activity {node.name!r}" if isinstance(node, Activity) else "sequence"
    where = f" ({node.origin.filename}:{node.origin.line})" if node.origin else ""
    return f"{kind} at {address(path)}{where}"


def _check_chaining(node: Node, path: tuple[int, ...]) -> None:
    if isinstance(node, Activity):
        return
    for index, step in enumerate(node.steps):
        _check_chaining(step, (*path, index))
    for index in range(len(node.steps) - 1):
        producer, consumer = node.steps[index], node.steps[index + 1]
        produced = result_color(producer)
        consumed = request_color(consumer)
        if produced != consumed:
            raise LoweringError(
                f"cannot lower {_label(node, path)}: "
                f"{_label(producer, (*path, index))} produces {produced} but "
                f"{_label(consumer, (*path, index + 1))} consumes {consumed}"
            )


class _Lowering:
    def __init__(self, spec: NetSpec, definitions: Mapping[str, ActivityDefinition]) -> None:
        self.spec = spec
        self.definitions = definitions
        self.source_map: dict[str, SourceMapEntry] = {}
        self.generated_by: dict[str, str] = {}
        self.activity_paths: list[tuple[NetPath, str]] = []

    def lower(self, node: Node, path: tuple[int, ...], entry: PlaceSpec) -> PlaceSpec:
        """Lower one fragment from its entry place; return its exit place."""
        match node:
            case Activity():
                return self._lower_activity(node, path, entry)
            case Sequence(steps=steps):
                current = entry
                for index, step in enumerate(steps):
                    current = self.lower(step, (*path, index), current)
                self.source_map[address(path)] = SourceMapEntry(
                    node="sequence",
                    origin=self._origin(node),
                )
                return current

    def _lower_activity(self, node: Activity, path: tuple[int, ...], entry: PlaceSpec) -> PlaceSpec:
        if node.name not in self.definitions:
            known = ", ".join(sorted(self.definitions)) or "none"
            raise LoweringError(
                f"cannot lower {_label(node, path)}: no activity definition named {node.name!r} (known: {known})"
            )
        definition = self.definitions[node.name]
        scope = self.spec.s["w"]
        segment = "_".join(str(index) for index in path)
        if segment:
            scope = scope[segment]
        del definition  # existence checked here; bound after build by exact handler URI
        transition = getattr(scope.t, node.name)(handler=node.name)
        exit_place = scope.p.out(node.result)
        entry >> transition >> exit_place
        self.activity_paths.append((abs(transition), node.name))
        node_address = address(path)
        self.source_map[node_address] = SourceMapEntry(
            node=f"activity {node.name!r}",
            origin=self._origin(node),
            transition=str(abs(transition)),
            exit_place=str(abs(exit_place)),
        )
        self.generated_by[str(abs(transition))] = node_address
        self.generated_by[str(abs(exit_place))] = node_address
        return exit_place

    @staticmethod
    def _origin(node: Node) -> str | None:
        return f"{node.origin.filename}:{node.origin.line}" if node.origin else None


def compile_workflow(
    root: Node,
    definitions: Iterable[ActivityDefinition],
    *,
    name: str = "workflow",
) -> CompiledWorkflow:
    """Deterministically lower a workflow AST into a runnable ``BuiltNet``."""
    by_name = {definition.declaration.name: definition for definition in definitions}
    _check_chaining(root, ())

    spec = NetSpec(name)
    lowering = _Lowering(spec, by_name)
    entry = spec.s["w"].p.entry(request_color(root))
    exit_place = lowering.lower(root, (), entry)
    built = spec.build()

    handlers: dict[NetUri | str, Handler | ActivityHandler] = dict(built.handlers)
    declarations: dict[str, ActivityDeclaration] = {}
    for transition_path, activity_name in lowering.activity_paths:
        uri = built.net.handler_uri(transition_path)
        assert uri is not None
        handlers[uri] = DerivedActivityHandler(built.net, transition_path, by_name[activity_name])
        declarations[activity_name] = by_name[activity_name].declaration

    return CompiledWorkflow(
        built=built,
        entry=abs(entry),
        exit=abs(exit_place),
        handlers=handlers,
        activities=tuple(declarations.values()),
        source_map=lowering.source_map,
        generated_by=lowering.generated_by,
    )
