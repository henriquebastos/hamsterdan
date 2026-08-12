"""AX5 spike — lower TypeSwitch onto the frozen Net; variant-aware dispatch.

The runtime already routes by token color: ``route``/``complete_firing``
deposit a token on every output arc that admits it and **silently drop**
tokens no arc admits. AX5 therefore splits the responsibility honestly:

- the AST guarantees exhaustiveness (switch construction);
- ``VariantPayloadConverter`` makes the concrete variant durable — the
  worker boundary stamps ``$variant`` into the frozen result, refusing
  subclasses and unlisted types loudly;
- ``VariantRoutingActivityHandler.project`` reads the durable
  discriminator and targets exactly the matching variant place, raising
  loudly on anything unexpected — never relying on the silent drop;
- lowering generates one variant-colored place and one typed arc per
  union member, one branch subtree per case, and — when every case exits
  with the same color — an XOR merge: one passthrough transition per
  case into one shared merge place.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from collections.abc import Sequence as SequenceABC
from dataclasses import asdict, dataclass, field
from types import MappingProxyType, UnionType
from typing import get_args

from ax5_workflow_ast import Activity, Case, Node, Sequence, TypeSwitch, address
from petrus.impetus.binding import (
    ActivityHandler,
    Binding,
    DerivedActivityHandler,
    Handler,
    passthrough,
)
from petrus.impetus.dsl import BuiltNet, NetSpec, PlaceSpec, petri_handler
from petrus.impetus.petrinet import NetPath, Token
from petrus.impetus.petrinet.schema import Net, NetUri
from petrus.motus.activity import (
    ActivityDeclaration,
    ActivityDefinition,
    ActivityInvocation,
    DataclassPayloadConverter,
    JsonPayloadConverter,
)


class LoweringError(ValueError):
    """The workflow AST cannot be lowered onto a valid net."""


_JSON = JsonPayloadConverter()


@dataclass(frozen=True)
class VariantPayloadConverter:
    """Make the concrete union variant durable at the worker boundary.

    ``encode`` on a union annotation requires the value to be *exactly*
    one of the declared members (a subclass is refused — its name would
    route nowhere) and stamps ``$variant`` into the JSON-faithful
    payload. Everything else delegates to the ordinary dataclass
    converter.
    """

    fallback: DataclassPayloadConverter = field(default_factory=DataclassPayloadConverter)

    def decode(self, value: object, annotation: object) -> object:
        return self.fallback.decode(value, annotation)

    def encode(self, value: object, annotation: object) -> object:
        if isinstance(annotation, UnionType):
            members = {member.__name__: member for member in get_args(annotation)}
            concrete = type(value)
            if members.get(concrete.__name__) is not concrete:
                raise ValueError(
                    f"union activity result must be exactly one of "
                    f"{sorted(members)}, got {concrete.__name__} — subclasses "
                    f"and unlisted types have no routing arc"
                )
            return _JSON.encode({"$variant": concrete.__name__, **asdict(value)}, annotation)
        return self.fallback.encode(value, annotation)


@dataclass(frozen=True)
class VariantRoutingActivityHandler:
    """Prepare like the derived handler; project by the durable ``$variant``.

    Single-parameter sources only (the AX5 spike restriction, enforced at
    switch construction). Construction validates the topology carries
    exactly one typed output arc per declared variant.
    """

    net: Net = field(repr=False)
    transition: NetPath
    definition: ActivityDefinition
    variants: tuple[str, ...]
    _parameter: str = field(init=False, repr=False)
    _source: NetPath = field(init=False, repr=False)
    _targets: Mapping[str, NetPath] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        transition = NetPath(self.transition)
        [(parameter, annotation)] = list(self.definition.parameters.items())
        color = annotation.__name__
        inputs = [arc for arc in self.net.inputs(transition) if arc.color == color]
        if len(inputs) != 1:
            raise ValueError(
                f"variant routing for {transition}: parameter {parameter!r} "
                f"({color}) requires exactly one input arc, found {len(inputs)}"
            )
        targets: dict[str, NetPath] = {}
        for arc in self.net.outputs(transition):
            if arc.color not in self.variants:
                raise ValueError(
                    f"variant routing for {transition}: output arc to "
                    f"{arc.target} carries {arc.color!r}, not a declared "
                    f"variant of {list(self.variants)}"
                )
            if arc.color in targets:
                raise ValueError(f"variant routing for {transition}: variant {arc.color!r} has two output arcs")
            targets[arc.color] = arc.target
        missing = [v for v in self.variants if v not in targets]
        if missing:
            raise ValueError(f"variant routing for {transition}: no output arc for {missing}")
        object.__setattr__(self, "transition", transition)
        object.__setattr__(self, "_parameter", parameter)
        object.__setattr__(self, "_source", inputs[0].source)
        object.__setattr__(self, "_targets", MappingProxyType(targets))

    def prepare(self, binding: Binding) -> ActivityInvocation:
        [(place, tokens)] = list(binding.consumed)
        if place != self._source or len(tokens) != 1:
            raise ValueError(
                f"variant routing for {self.transition}: expected one token "
                f"from {self._source}, got {len(tokens)} from {place}"
            )
        return ActivityInvocation(self.definition.declaration.name, input={self._parameter: tokens[0].data})

    def project(self, binding: Binding, result: object) -> Mapping[NetPath, SequenceABC[Token]]:
        del binding
        if not isinstance(result, Mapping) or "$variant" not in result:
            raise ValueError(
                f"variant routing for {self.transition}: durable result lacks "
                f"the '$variant' discriminator — was the activity declared "
                f"with VariantPayloadConverter?"
            )
        payload = dict(result)
        variant = payload.pop("$variant")
        target = self._targets.get(variant)
        if target is None:
            raise ValueError(
                f"variant routing for {self.transition}: result variant "
                f"{variant!r} is not one of {list(self._targets)} — refusing "
                f"the runtime's silent drop"
            )
        return {target: (Token(variant, payload),)}


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


def _label(node: Node | Case, path: tuple[int, ...]) -> str:
    match node:
        case Activity():
            kind = f"activity {node.name!r}"
        case TypeSwitch():
            kind = f"switch {node.name!r}"
        case Case():
            kind = f"case {node.variant}"
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
        self.activity_paths: list[tuple[NetPath, str]] = []
        self.switch_paths: list[tuple[NetPath, str, tuple[str, ...]]] = []

    def scope(self, path: tuple[int, ...]):
        scope = self.spec.s["w"]
        segment = "_".join(str(index) for index in path)
        return scope[segment] if segment else scope

    def definition(self, node: Node, path: tuple[int, ...], name: str) -> ActivityDefinition:
        if name not in self.definitions:
            known = ", ".join(sorted(self.definitions)) or "none"
            raise LoweringError(
                f"cannot lower {_label(node, path)}: no activity definition named {name!r} (known: {known})"
            )
        return self.definitions[name]

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
            case TypeSwitch():
                return self._lower_switch(node, path, entries)

    def _lower_activity(
        self, node: Activity, path: tuple[int, ...], entries: tuple[PlaceSpec, ...]
    ) -> tuple[PlaceSpec, ...]:
        self.definition(node, path, node.name)
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

    def _lower_switch(
        self, node: TypeSwitch, path: tuple[int, ...], entries: tuple[PlaceSpec, ...]
    ) -> tuple[PlaceSpec, ...]:
        if len(entries) != 1:
            names = ", ".join(str(abs(p)) for p in entries)
            raise LoweringError(
                f"cannot lower {_label(node, path)}: a switch consumes exactly one place, got [{names}]"
            )
        [entry] = entries
        [expected] = node.inputs.values()
        if entry.color != expected:
            raise LoweringError(
                f"cannot lower {_label(node, path)}: consumes {expected}, but "
                f"upstream place {abs(entry)} carries {entry.color!r}"
            )
        scope = self.scope(path)
        transition = getattr(scope.t, node.name)(handler=node.name)
        variant_places = tuple(getattr(scope.p, f"on_{variant.lower()}")(variant) for variant in node.variants)
        entry >> transition >> variant_places
        self.switch_paths.append((abs(transition), node.name, node.variants))

        case_exits: list[tuple[Case, tuple[PlaceSpec, ...]]] = []
        for index, branch in enumerate(node.cases):
            entry_place = variant_places[node.variants.index(branch.variant)]
            exits = self.lower(branch.body, (*path, index), (entry_place,))
            case_exits.append((branch, exits))

        flat = [place for _, exits in case_exits for place in exits]
        colors = {place.color for place in flat}
        if len(colors) == 1 and all(len(exits) == 1 for _, exits in case_exits):
            [color] = colors
            merged = scope.p.out(color)
            for index, (_, exits) in enumerate(case_exits):
                merge = getattr(scope.t, f"merge_{index}")(handler=petri_handler(passthrough))
                exits[0] >> merge >> merged
                self.generated_by[str(abs(merge))] = address((*path, index))
            self._record(node, path, transition, (merged,))
            return (merged,)
        self._record(node, path, transition, tuple(flat))
        return tuple(flat)

    def _record(self, node: Node, path: tuple[int, ...], transition, exits) -> None:
        node_address = address(path)
        entry = SourceMapEntry(
            node=_label(node, path).split(" at ")[0],
            origin=f"{node.origin.filename}:{node.origin.line}" if node.origin else None,
            transition=str(abs(transition)) if transition is not None else None,
            exit_places=tuple(str(abs(place)) for place in exits),
        )
        self.source_map[node_address] = entry
        if transition is not None:
            self.generated_by[str(abs(transition))] = node_address


def _request_colors(node: Node) -> list[str]:
    match node:
        case Activity(inputs=inputs) | TypeSwitch(inputs=inputs):
            return sorted(set(inputs.values()))
        case Sequence(steps=steps):
            return _request_colors(steps[0])


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
    for transition_path, activity_name, variants in lowering.switch_paths:
        uri = built.net.handler_uri(transition_path)
        assert uri is not None
        handlers[uri] = VariantRoutingActivityHandler(built.net, transition_path, by_name[activity_name], variants)
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
