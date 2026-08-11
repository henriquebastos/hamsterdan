"""AX4 spike — lower Parallel (AND-split + synchronizing join) onto the Net.

The AX2 threaded contract generalizes from one place to a **place set**:

    lower(node, entries: tuple[PlaceSpec, ...]) -> tuple[PlaceSpec, ...]

- ``Activity`` consumes **all** its entry places through one transition.
  Parameters match entry places by color, each exactly once — the join
  is therefore not a hidden mechanism: it *is* the downstream activity's
  transition, whose Petri enabledness (one token on every input place)
  is the synchronization.
- ``Parallel`` requires exactly one entry place. It generates an
  explicit, observable **split transition** bound to the frozen
  ``passthrough`` handler: the consumed token is deposited on every
  branch entry place (all colored with the incoming color — AND-split
  duplication, not competition). Branch exits concatenate.
- ``Sequence`` threads place sets unchanged.

Choice made explicit (the experiment's aggregation decision): branch
results stay **separate typed tokens** consumed by the next activity's
multi-input transition. No generated aggregate dataclass, no hidden
combiner — the tokens and the synchronizing transition are visible in
the net and in History.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ax4_workflow_ast import Activity, Node, Parallel, Sequence, address
from petrus.impetus.binding import (
    ActivityHandler,
    DerivedActivityHandler,
    Handler,
    passthrough,
)
from petrus.impetus.dsl import BuiltNet, NetSpec, PlaceSpec, petri_handler
from petrus.impetus.petrinet import NetPath
from petrus.impetus.petrinet.schema import NetUri
from petrus.motus.activity import ActivityDeclaration, ActivityDefinition


class LoweringError(ValueError):
    """The workflow AST cannot be lowered onto a valid net."""


@dataclass(frozen=True)
class SourceMapEntry:
    node: str
    origin: str | None
    transition: str | None = None
    exit_places: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompiledWorkflow:
    built: BuiltNet
    entry: NetPath
    exits: tuple[NetPath, ...]
    handlers: Mapping[NetUri | str, Handler | ActivityHandler]
    activities: tuple[ActivityDeclaration, ...]
    source_map: Mapping[str, SourceMapEntry] = field(default_factory=dict)
    generated_by: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "source_map", MappingProxyType(dict(self.source_map)))
        object.__setattr__(self, "generated_by", MappingProxyType(dict(self.generated_by)))


def _label(node: Node, path: tuple[int, ...]) -> str:
    kind = f"activity {node.name!r}" if isinstance(node, Activity) else type(node).__name__.lower()
    where = f" ({node.origin.filename}:{node.origin.line})" if node.origin else ""
    return f"{kind} at {address(path)}{where}"


class _Lowering:
    def __init__(self, spec: NetSpec, definitions: Mapping[str, ActivityDefinition]) -> None:
        self.spec = spec
        self.definitions = definitions
        self.source_map: dict[str, SourceMapEntry] = {}
        self.generated_by: dict[str, str] = {}
        self.activity_paths: list[tuple[NetPath, str]] = []

    def scope(self, path: tuple[int, ...]):
        scope = self.spec.s["w"]
        segment = "_".join(str(index) for index in path)
        return scope[segment] if segment else scope

    def lower(self, node: Node, path: tuple[int, ...], entries: tuple[PlaceSpec, ...]) -> tuple[PlaceSpec, ...]:
        match node:
            case Activity():
                return self._lower_activity(node, path, entries)
            case Sequence(steps=steps):
                current = entries
                for index, child in enumerate(steps):
                    current = self.lower(child, (*path, index), current)
                self._record(node, path, None, current)
                return current
            case Parallel():
                return self._lower_parallel(node, path, entries)

    def _lower_activity(
        self, node: Activity, path: tuple[int, ...], entries: tuple[PlaceSpec, ...]
    ) -> tuple[PlaceSpec, ...]:
        if node.name not in self.definitions:
            known = ", ".join(sorted(self.definitions)) or "none"
            raise LoweringError(
                f"cannot lower {_label(node, path)}: no activity definition named {node.name!r} (known: {known})"
            )
        entry_colors = [place.color for place in entries]
        matched: dict[str, PlaceSpec] = {}
        used: set[int] = set()
        for parameter, color in node.inputs.items():
            indexes = [i for i, c in enumerate(entry_colors) if c == color and i not in used]
            if len(indexes) != 1:
                upstream = ", ".join(f"{abs(p)}({c})" for p, c in zip(entries, entry_colors))
                hint = (
                    "; two upstream places share this color — named ports are required (AX3)"
                    if len(indexes) > 1
                    else ""
                )
                raise LoweringError(
                    f"cannot lower {_label(node, path)}: parameter {parameter!r} ({color}) "
                    f"requires exactly one upstream place with that color, found "
                    f"{len(indexes)} among [{upstream}]{hint}"
                )
            matched[parameter] = entries[indexes[0]]
            used.add(indexes[0])
        leftover = [entries[i] for i in range(len(entries)) if i not in used]
        if leftover:
            names = ", ".join(f"{abs(p)}({p.color})" for p in leftover)
            raise LoweringError(
                f"cannot lower {_label(node, path)}: upstream places [{names}] carry tokens "
                f"this activity does not consume"
            )

        scope = self.scope(path)
        transition = getattr(scope.t, node.name)(handler=node.name)
        out_color = node.result if node.result is not None else "NoneType"
        exit_place = scope.p.out(out_color)
        tuple(matched.values()) >> transition >> exit_place
        self.activity_paths.append((abs(transition), node.name))
        self._record(node, path, transition, (exit_place,))
        return (exit_place,)

    def _lower_parallel(
        self, node: Parallel, path: tuple[int, ...], entries: tuple[PlaceSpec, ...]
    ) -> tuple[PlaceSpec, ...]:
        if len(entries) != 1:
            names = ", ".join(str(abs(p)) for p in entries)
            raise LoweringError(
                f"cannot lower {_label(node, path)}: an AND-split duplicates exactly one "
                f"incoming token, got {len(entries)} upstream places [{names}]"
            )
        [entry] = entries
        scope = self.scope(path)
        split = scope.t.split(handler=petri_handler(passthrough))
        branch_entries: list[PlaceSpec] = []
        for index, branch in enumerate(node.branches):
            colors = _request_colors(branch, (*path, index))
            if len(colors) != 1 or colors[0] != entry.color:
                raise LoweringError(
                    f"cannot lower {_label(node, path)}: branch {index} "
                    f"({_label(branch, (*path, index))}) must consume exactly the split "
                    f"token color {entry.color!r}, but consumes {colors}"
                )
            branch_scope = self.scope((*path, index))
            branch_entries.append(getattr(branch_scope.p, "in")(entry.color))
        entry >> split >> tuple(branch_entries)
        exits: list[PlaceSpec] = []
        for index, branch in enumerate(node.branches):
            exits.extend(self.lower(branch, (*path, index), (branch_entries[index],)))
        self._record(node, path, split, tuple(exits))
        return tuple(exits)

    def _record(self, node: Node, path: tuple[int, ...], transition, exits) -> None:
        node_address = address(path)
        kind = f"activity {node.name!r}" if isinstance(node, Activity) else type(node).__name__.lower()
        entry = SourceMapEntry(
            node=kind,
            origin=f"{node.origin.filename}:{node.origin.line}" if node.origin else None,
            transition=str(abs(transition)) if transition is not None else None,
            exit_places=tuple(str(abs(place)) for place in exits),
        )
        self.source_map[node_address] = entry
        if transition is not None:
            self.generated_by[str(abs(transition))] = node_address


def _request_colors(node: Node, path: tuple[int, ...]) -> list[str]:
    match node:
        case Activity(inputs=inputs):
            return sorted(set(inputs.values()))
        case Sequence(steps=steps):
            return _request_colors(steps[0], (*path, 0))
        case Parallel():
            # A parallel's own request is its split token color; delegate to branches.
            colors = {
                color for index, branch in enumerate(node.branches) for color in _request_colors(branch, (*path, index))
            }
            return sorted(colors)


def compile_workflow(
    root: Node,
    definitions: Iterable[ActivityDefinition],
    *,
    name: str = "workflow",
) -> CompiledWorkflow:
    by_name = {definition.declaration.name: definition for definition in definitions}
    request = _request_colors(root, ())
    if len(request) != 1:
        raise LoweringError(f"workflow root must consume exactly one token color at its entry, got {request}")

    spec = NetSpec(name)
    lowering = _Lowering(spec, by_name)
    entry = spec.s["w"].p.entry(request[0])
    exits = lowering.lower(root, (), (entry,))
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
        exits=tuple(abs(place) for place in exits),
        handlers=handlers,
        activities=tuple(declarations.values()),
        source_map=lowering.source_map,
        generated_by=lowering.generated_by,
    )
