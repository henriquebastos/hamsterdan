"""AX8 spike — lower the tree-shaped Retry node onto a cyclic frozen Net.

Generated shape (limit 3, retryable Transient):

    w.entry(ChargeRequest) ──▶ charge ──▶ on_confirmed(Confirmed) ─▶ case body
           ▲                        ├───▶ on_fatal(Fatal) ────────▶ case body
           │                        └───▶ on_transient(Transient)
           │                                  ├─[(attempt < 3)]──▶ rearm ──┐
           │                                  └─[!(attempt < 3)]─▶ to_exhausted ─▶ body
           └───────────────────────────────────────────────────────────────┘

One loop-back arc makes the cycle; everything else is the AX5/AX6/AX7
machinery unchanged. The variant projection (`VariantRoutingActivityHandler`,
carried from AX5) targets exactly one variant place per firing; the two
filtered arcs off the retryable place split below-limit from at-limit
tokens; ``rearm`` is a frozen `derive_typed_transform` — a pure, typed,
inline transform whose only job is to map the retryable variant back to
the source activity's input type with the counter advanced.

Replay note: the loop counter lives in token data, every attempt is an
ordinary durable activity round-trip, and the rearm transform is pure —
so replay over a recompiled cyclic net needs nothing new.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from collections.abc import Sequence as SequenceABC
from dataclasses import asdict, dataclass, field
from types import MappingProxyType, UnionType
from typing import get_args

from ax8_workflow_ast import Activity, Node, Retry, Sequence, address
from petrus.impetus.binding import (
    ActivityHandler,
    Binding,
    DerivedActivityHandler,
    Handler,
    derive_typed_transform,
    passthrough,
)
from petrus.impetus.dsl import BuiltNet, NetSpec, PlaceSpec, arc, petri_handler
from petrus.impetus.petrinet import Cel, NetPath, Token
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
    """AX5's converter, carried unchanged: stamp ``$variant`` durably."""

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
    """AX5's handler, carried unchanged: project by the durable ``$variant``."""

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
        inputs = [a for a in self.net.inputs(transition) if a.color == color]
        if len(inputs) != 1:
            raise ValueError(
                f"variant routing for {transition}: parameter {parameter!r} "
                f"({color}) requires exactly one input arc, found {len(inputs)}"
            )
        targets: dict[str, NetPath] = {}
        for output in self.net.outputs(transition):
            if output.color not in self.variants:
                raise ValueError(
                    f"variant routing for {transition}: output arc to "
                    f"{output.target} carries {output.color!r}, not a declared "
                    f"variant of {list(self.variants)}"
                )
            if output.color in targets:
                raise ValueError(f"variant routing for {transition}: variant {output.color!r} has two output arcs")
            targets[output.color] = output.target
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
    filters: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "source_map", MappingProxyType(dict(self.source_map)))
        object.__setattr__(self, "generated_by", MappingProxyType(dict(self.generated_by)))
        object.__setattr__(self, "filters", MappingProxyType(dict(self.filters)))


def _label(node: Node, path: tuple[int, ...]) -> str:
    match node:
        case Activity():
            kind = f"activity {node.name!r}"
        case Retry():
            kind = f"retry {node.name!r} x{node.limit}"
        case _:
            kind = type(node).__name__.lower()
    where = f" ({node.origin.filename}:{node.origin.line})" if node.origin else ""
    return f"{kind} at {address(path)}{where}"


class _Lowering:
    def __init__(
        self,
        spec: NetSpec,
        definitions: Mapping[str, ActivityDefinition],
        transforms: Mapping[str, Callable[..., object]],
    ) -> None:
        self.spec = spec
        self.definitions = definitions
        self.transforms = transforms
        self.source_map: dict[str, SourceMapEntry] = {}
        self.generated_by: dict[str, str] = {}
        self.filters: dict[str, str] = {}
        self.activity_paths: list[tuple[NetPath, str]] = []
        self.retry_paths: list[tuple[NetPath, str, tuple[str, ...]]] = []
        self.rearm_paths: list[tuple[NetPath, str]] = []

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
            case Retry():
                return self._lower_retry(node, path, entries)

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

    def _lower_retry(self, node: Retry, path: tuple[int, ...], entries: tuple[PlaceSpec, ...]) -> tuple[PlaceSpec, ...]:
        if len(entries) != 1:
            names = ", ".join(str(abs(p)) for p in entries)
            raise LoweringError(f"cannot lower {_label(node, path)}: a retry consumes exactly one place, got [{names}]")
        [entry] = entries
        [expected] = node.inputs.values()
        if entry.color != expected:
            raise LoweringError(
                f"cannot lower {_label(node, path)}: consumes {expected}, but "
                f"upstream place {abs(entry)} carries {entry.color!r}"
            )
        if node.rearm_name not in self.transforms:
            known = ", ".join(sorted(self.transforms)) or "none"
            raise LoweringError(
                f"cannot lower {_label(node, path)}: no transform named {node.rearm_name!r} (known: {known})"
            )
        scope = self.scope(path)
        transition = getattr(scope.t, node.name)(handler=node.name)
        variant_places = {variant: getattr(scope.p, f"on_{variant.lower()}")(variant) for variant in node.variants}
        entry >> transition >> tuple(variant_places.values())
        self.retry_paths.append((abs(transition), node.name, node.variants))

        # The loop-back: below the limit, rearm and deposit into the SAME
        # entry place — this one arc is the whole cycle.
        retryable_place = variant_places[node.retryable]
        rearm = scope.t.rearm(handler=node.rearm_name)
        retryable_place >> arc(color=node.retryable, filter=Cel(node.loop_cel)) >> rearm
        rearm >> entry
        self.rearm_paths.append((abs(rearm), node.rearm_name))
        self.filters[str(abs(rearm))] = node.loop_cel
        self.generated_by[str(abs(rearm))] = address(path)

        # At the limit: route the retryable variant to the exhausted body.
        to_exhausted = scope.t.to_exhausted(handler=petri_handler(passthrough))
        exhausted_entry = scope.p.when_exhausted(node.retryable)
        retryable_place >> arc(color=node.retryable, filter=Cel(node.exhausted_cel)) >> to_exhausted
        to_exhausted >> exhausted_entry
        self.filters[str(abs(to_exhausted))] = node.exhausted_cel
        self.generated_by[str(abs(to_exhausted))] = address(path)

        routed: list[tuple[Node, tuple[int, ...]]] = []
        route_exits: list[tuple[PlaceSpec, ...]] = []
        for index, branch in enumerate(node.cases):
            body_path = (*path, index, 0)
            routed.append((branch.body, body_path))
            route_exits.append(self.lower(branch.body, body_path, (variant_places[branch.variant],)))
        exhausted_path = (*path, len(node.cases), 0)
        routed.append((node.exhausted, exhausted_path))
        route_exits.append(self.lower(node.exhausted, exhausted_path, (exhausted_entry,)))

        flat = [place for exits in route_exits for place in exits]
        colors = {place.color for place in flat}
        if len(colors) == 1 and all(len(exits) == 1 for exits in route_exits):
            [color] = colors
            merged = scope.p.out(color)
            for index, exits in enumerate(route_exits):
                merge = getattr(scope.t, f"merge_{index}")(handler=petri_handler(passthrough))
                exits[0] >> merge >> merged
                self.generated_by[str(abs(merge))] = address((*path, index))
            self._record(node, path, transition, (merged,))
            return (merged,)
        self._record(node, path, transition, tuple(flat))
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
        case Activity(inputs=inputs) | Retry(inputs=inputs):
            return sorted(set(inputs.values()))
        case Sequence(steps=steps):
            return _request_colors(steps[0])


def compile_workflow(
    root: Node,
    definitions: Iterable[ActivityDefinition],
    *,
    transforms: Iterable[Callable[..., object]] = (),
    name: str = "workflow",
) -> CompiledWorkflow:
    by_name = {definition.declaration.name: definition for definition in definitions}
    transforms_by_name = {transform.__name__: transform for transform in transforms}
    request = _request_colors(root)
    if len(request) != 1:
        raise LoweringError(f"workflow root must consume exactly one token color at its entry, got {request}")

    spec = NetSpec(name)
    lowering = _Lowering(spec, by_name, transforms_by_name)
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
    for transition_path, activity_name, variants in lowering.retry_paths:
        uri = built.net.handler_uri(transition_path)
        assert uri is not None
        handlers[uri] = VariantRoutingActivityHandler(built.net, transition_path, by_name[activity_name], variants)
        declarations[activity_name] = by_name[activity_name].declaration
    for transition_path, transform_name in lowering.rearm_paths:
        uri = built.net.handler_uri(transition_path)
        assert uri is not None
        handlers[uri] = derive_typed_transform(built.net, transition_path, transforms_by_name[transform_name])

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
