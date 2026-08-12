"""AX6 spike — lower GuardBranch onto the frozen Net via filtered input arcs.

Where AX5 routed on *output* arcs by token color, AX6 routes on *input*
arcs by CEL filter: the branch entry place feeds one pure router
transition per case, each admitted by a filter compiled from the case's
predicate AST. Two properties of the frozen runtime shape the lowering:

- Filtered input arcs are **competition**, not duplication: transitions
  sharing one place race for the token, and enabledness picks one. Raw
  overlapping filters are therefore legal Petri nondeterminism.
- A token admitted by *no* input arc **parks** in the place (with a
  ``FilterEvaluationWarning`` if a filter raised) — not dropped, but
  silently stuck.

The lowering makes both harmless: cases compile ordered-exclusive
(case *n* carries the negations of cases ``1..n-1``), so at most one
router is ever enabled — deterministic first-match-wins without any
runtime priority feature — and the mandatory ``otherwise`` carries the
conjunction of all negations, so every *evaluable* token has exactly one
route. Only a token whose filter evaluation raises (e.g. a null where
the predicate compares) can park; the predicate layer's null-safety
validation exists to keep that unrepresentable from typed authoring.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ax6_workflow_ast import Activity, GuardBranch, GuardCase, Node, Sequence, address
from petrus.impetus.binding import (
    ActivityHandler,
    DerivedActivityHandler,
    Handler,
    passthrough,
)
from petrus.impetus.dsl import BuiltNet, NetSpec, PlaceSpec, arc, petri_handler
from petrus.impetus.petrinet import Cel, NetPath
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
    filters: Mapping[str, str] = field(default_factory=dict)  # router transition -> CEL

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "source_map", MappingProxyType(dict(self.source_map)))
        object.__setattr__(self, "generated_by", MappingProxyType(dict(self.generated_by)))
        object.__setattr__(self, "filters", MappingProxyType(dict(self.filters)))


def case_filters(node: GuardBranch) -> tuple[tuple[str, ...], str]:
    """The ordered-exclusive CEL expressions: one per case, plus otherwise.

    Case *n* is its own predicate conjoined with the negation of every
    earlier predicate; ``otherwise`` is the conjunction of all negations.
    Deterministic and pure — replay recompiles to identical filters.
    """
    rendered = [guard.predicate.cel() for guard in node.cases]
    cases = tuple(
        " && ".join([rendered[index], *(f"!{earlier}" for earlier in rendered[:index])])
        for index in range(len(rendered))
    )
    return cases, " && ".join(f"!{expression}" for expression in rendered)


def _label(node: Node | GuardCase, path: tuple[int, ...]) -> str:
    match node:
        case Activity():
            kind = f"activity {node.name!r}"
        case GuardBranch():
            kind = f"branch on {node.subject}"
        case GuardCase():
            kind = f"when {node.predicate.cel()}"
        case _:
            kind = type(node).__name__.lower()
    where = f" ({node.origin.filename}:{node.origin.line})" if node.origin else ""
    return f"{kind} at {address(path)}{where}"


class _Lowering:
    def __init__(self, spec: NetSpec, definitions: Mapping[str, ActivityDefinition]) -> None:
        self.spec = spec
        self.definitions = definitions
        self.source_map: dict[str, SourceMapEntry] = {}
        self.generated_by: dict[str, str] = {}
        self.filters: dict[str, str] = {}
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
            case GuardBranch():
                return self._lower_branch(node, path, entries)

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
                raise LoweringError(
                    f"cannot lower {_label(node, path)}: parameter {parameter!r} "
                    f"({color}) requires exactly one upstream place with that "
                    f"color, found {len(indexes)} among [{upstream}]"
                )
            matched[parameter] = entries[indexes[0]]
            used.add(indexes[0])
        leftover = [entries[i] for i in range(len(entries)) if i not in used]
        if leftover:
            names = ", ".join(f"{abs(p)}({p.color})" for p in leftover)
            raise LoweringError(
                f"cannot lower {_label(node, path)}: upstream places [{names}] "
                f"carry tokens this activity does not consume"
            )
        scope = self.scope(path)
        transition = getattr(scope.t, node.name)(handler=node.name)
        out_color = node.result if node.result is not None else "NoneType"
        exit_place = scope.p.out(out_color)
        tuple(matched.values()) >> transition >> exit_place
        self.activity_paths.append((abs(transition), node.name))
        self._record(node, path, transition, (exit_place,))
        return (exit_place,)

    def _lower_branch(
        self, node: GuardBranch, path: tuple[int, ...], entries: tuple[PlaceSpec, ...]
    ) -> tuple[PlaceSpec, ...]:
        if len(entries) != 1:
            names = ", ".join(str(abs(p)) for p in entries)
            raise LoweringError(
                f"cannot lower {_label(node, path)}: a branch consumes exactly one place, got [{names}]"
            )
        [entry] = entries
        if entry.color != node.subject:
            raise LoweringError(
                f"cannot lower {_label(node, path)}: predicates read "
                f"{node.subject}, but upstream place {abs(entry)} carries "
                f"{entry.color!r}"
            )
        scope = self.scope(path)
        expressions, fallback = case_filters(node)

        routed: list[tuple[Node, tuple[int, ...], PlaceSpec]] = []
        for index, (guard, expression) in enumerate(zip(node.cases, expressions)):
            router = getattr(scope.t, f"case_{index}")(handler=petri_handler(passthrough))
            target = getattr(scope.p, f"when_{index}")(node.subject)
            entry >> arc(color=node.subject, filter=Cel(expression)) >> router
            router >> target
            self.filters[str(abs(router))] = expression
            self.generated_by[str(abs(router))] = address((*path, index))
            self.source_map[address((*path, index))] = SourceMapEntry(
                node=_label(guard, (*path, index)).split(" at ")[0],
                origin=f"{guard.origin.filename}:{guard.origin.line}" if guard.origin else None,
                transition=str(abs(router)),
            )
            # The body lowers one level below the case so the case keeps
            # its own structural address in the source map.
            routed.append((guard.body, (*path, index, 0), target))

        otherwise_index = len(node.cases)
        router = scope.t.otherwise(handler=petri_handler(passthrough))
        target = scope.p.when_otherwise(node.subject)
        entry >> arc(color=node.subject, filter=Cel(fallback)) >> router
        router >> target
        self.filters[str(abs(router))] = fallback
        self.generated_by[str(abs(router))] = address((*path, otherwise_index))
        routed.append((node.otherwise, (*path, otherwise_index, 0), target))

        route_exits = [self.lower(body, body_path, (place,)) for body, body_path, place in routed]

        flat = [place for exits in route_exits for place in exits]
        colors = {place.color for place in flat}
        if len(colors) == 1 and all(len(exits) == 1 for exits in route_exits):
            [color] = colors
            merged = scope.p.out(color)
            for index, exits in enumerate(route_exits):
                merge = getattr(scope.t, f"merge_{index}")(handler=petri_handler(passthrough))
                exits[0] >> merge >> merged
                self.generated_by[str(abs(merge))] = address((*path, index))
            self._record(node, path, None, (merged,))
            return (merged,)
        self._record(node, path, None, tuple(flat))
        return tuple(flat)

    def _record(self, node: Node, path: tuple[int, ...], transition, exits) -> None:
        node_address = address(path)
        self.source_map[node_address] = SourceMapEntry(
            node=_label(node, path).split(" at ")[0],
            origin=f"{node.origin.filename}:{node.origin.line}" if node.origin else None,
            transition=str(abs(transition)) if transition is not None else None,
            exit_places=tuple(str(abs(place)) for place in exits),
        )
        if transition is not None:
            self.generated_by[str(abs(transition))] = node_address


def _request_colors(node: Node) -> list[str]:
    match node:
        case Activity(inputs=inputs):
            return sorted(set(inputs.values()))
        case Sequence(steps=steps):
            return _request_colors(steps[0])
        case GuardBranch(subject=subject):
            return [subject]


def compile_workflow(
    root: Node,
    definitions: Iterable[ActivityDefinition],
    *,
    name: str = "workflow",
) -> CompiledWorkflow:
    by_name = {definition.declaration.name: definition for definition in definitions}
    request = _request_colors(root)
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
        filters=lowering.filters,
    )
