"""AX7 spike — lower HybridSwitch onto the frozen Net via hybrid arcs.

The generated shape makes the hybrid constraint literal: the union
activity's result lands (variant-stamped, variant-colored) in one
**untyped pool place**, and each case is one input arc carrying *both*
constraints — ``arc(color=variant, filter=Cel(predicate))``. The frozen
``enabledness.admitted`` checks the color first and only then evaluates
the filter, so a guard over ``Approved.risk`` never sees a ``Rejected``
token: the type narrows, the predicate selects, exactly as authored.

Within one variant the guarded cases compile ordered-exclusive (AX6
lowering) and the mandatory unguarded default carries the conjunction of
all negations, so every token of every variant has exactly one route.
Across variants there is no exclusion to encode — colors are disjoint by
construction.

``PoolVariantHandler`` adapts AX5's variant routing to a single target:
it stamps nothing itself (the ``VariantPayloadConverter`` did, durably,
at the worker boundary) but projects the result as a token *colored by
its variant* into the pool, refusing unknown variants loudly rather than
relying on parking.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from collections.abc import Sequence as SequenceABC
from dataclasses import asdict, dataclass, field
from types import MappingProxyType, UnionType
from typing import get_args

from ax7_workflow_ast import Activity, HybridCase, HybridSwitch, Node, Sequence, address
from petrus.impetus.binding import (
    ActivityHandler,
    Binding,
    DerivedActivityHandler,
    Handler,
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
class PoolVariantHandler:
    """Project the variant-stamped result into one pool, variant-colored.

    The pool place is untyped; the token's color carries the variant so
    the hybrid input arcs can do their color-then-filter admission.
    Construction validates the transition has exactly one untyped output
    arc (the pool); projection refuses variants outside the declaration.
    """

    net: Net = field(repr=False)
    transition: NetPath
    definition: ActivityDefinition
    variants: tuple[str, ...]
    _parameter: str = field(init=False, repr=False)
    _source: NetPath = field(init=False, repr=False)
    _pool: NetPath = field(init=False, repr=False)

    def __post_init__(self) -> None:
        transition = NetPath(self.transition)
        [(parameter, annotation)] = list(self.definition.parameters.items())
        color = annotation.__name__
        inputs = [a for a in self.net.inputs(transition) if a.color == color]
        if len(inputs) != 1:
            raise ValueError(
                f"pool routing for {transition}: parameter {parameter!r} "
                f"({color}) requires exactly one input arc, found {len(inputs)}"
            )
        outputs = list(self.net.outputs(transition))
        if len(outputs) != 1 or outputs[0].color is not None:
            shapes = [(str(a.target), a.color) for a in outputs]
            raise ValueError(
                f"pool routing for {transition}: requires exactly one untyped "
                f"output arc to the pool place, found {shapes}"
            )
        object.__setattr__(self, "transition", transition)
        object.__setattr__(self, "_parameter", parameter)
        object.__setattr__(self, "_source", inputs[0].source)
        object.__setattr__(self, "_pool", outputs[0].target)

    def prepare(self, binding: Binding) -> ActivityInvocation:
        [(place, tokens)] = list(binding.consumed)
        if place != self._source or len(tokens) != 1:
            raise ValueError(
                f"pool routing for {self.transition}: expected one token "
                f"from {self._source}, got {len(tokens)} from {place}"
            )
        return ActivityInvocation(self.definition.declaration.name, input={self._parameter: tokens[0].data})

    def project(self, binding: Binding, result: object) -> Mapping[NetPath, SequenceABC[Token]]:
        del binding
        if not isinstance(result, Mapping) or "$variant" not in result:
            raise ValueError(
                f"pool routing for {self.transition}: durable result lacks "
                f"the '$variant' discriminator — was the activity declared "
                f"with VariantPayloadConverter?"
            )
        payload = dict(result)
        variant = payload.pop("$variant")
        if variant not in self.variants:
            raise ValueError(
                f"pool routing for {self.transition}: result variant "
                f"{variant!r} is not one of {list(self.variants)} — refusing "
                f"the runtime's silent park"
            )
        return {self._pool: (Token(variant, payload),)}


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
    filters: Mapping[str, str | None] = field(default_factory=dict)  # router -> CEL

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "source_map", MappingProxyType(dict(self.source_map)))
        object.__setattr__(self, "generated_by", MappingProxyType(dict(self.generated_by)))
        object.__setattr__(self, "filters", MappingProxyType(dict(self.filters)))


def hybrid_filters(node: HybridSwitch) -> tuple[str | None, ...]:
    """One CEL expression (or None) per case, in authoring order.

    Exclusion is *within* a variant only — colors already separate the
    variants. A guarded case conjoins the negations of earlier guards on
    the same variant; the unguarded default carries all negations, or no
    filter at all when its variant has no guarded cases.
    """
    rendered_by_variant: dict[str, list[str]] = {}
    expressions: list[str | None] = []
    for guarded_case in node.cases:
        earlier = rendered_by_variant.setdefault(guarded_case.variant, [])
        negations = [f"!{expression}" for expression in earlier]
        if guarded_case.predicate is None:
            expressions.append(" && ".join(negations) if negations else None)
        else:
            own = guarded_case.predicate.cel()
            expressions.append(" && ".join([own, *negations]))
            earlier.append(own)
    return tuple(expressions)


def _label(node: Node | HybridCase, path: tuple[int, ...]) -> str:
    match node:
        case Activity():
            kind = f"activity {node.name!r}"
        case HybridSwitch():
            kind = f"hybrid {node.name!r}"
        case HybridCase():
            guard = f" when {node.predicate.cel()}" if node.predicate is not None else ""
            kind = f"case {node.variant}{guard}"
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
        self.filters: dict[str, str | None] = {}
        self.activity_paths: list[tuple[NetPath, str]] = []
        self.hybrid_paths: list[tuple[NetPath, str, tuple[str, ...]]] = []

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
            case HybridSwitch():
                return self._lower_hybrid(node, path, entries)

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

    def _lower_hybrid(
        self, node: HybridSwitch, path: tuple[int, ...], entries: tuple[PlaceSpec, ...]
    ) -> tuple[PlaceSpec, ...]:
        if len(entries) != 1:
            names = ", ".join(str(abs(p)) for p in entries)
            raise LoweringError(
                f"cannot lower {_label(node, path)}: a hybrid consumes exactly one place, got [{names}]"
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
        pool = scope.p.pool(None)
        entry >> transition >> pool
        self.hybrid_paths.append((abs(transition), node.name, node.variants))

        expressions = hybrid_filters(node)
        routed: list[tuple[Node, tuple[int, ...], PlaceSpec]] = []
        for index, (guarded_case, expression) in enumerate(zip(node.cases, expressions)):
            router = getattr(scope.t, f"case_{index}")(handler=petri_handler(passthrough))
            target = getattr(scope.p, f"on_{index}")(guarded_case.variant)
            inscription = arc(
                color=guarded_case.variant,
                filter=Cel(expression) if expression is not None else None,
            )
            pool >> inscription >> router
            router >> target
            self.filters[str(abs(router))] = expression
            self.generated_by[str(abs(router))] = address((*path, index))
            self.source_map[address((*path, index))] = SourceMapEntry(
                node=_label(guarded_case, (*path, index)).split(" at ")[0],
                origin=(f"{guarded_case.origin.filename}:{guarded_case.origin.line}" if guarded_case.origin else None),
                transition=str(abs(router)),
            )
            routed.append((guarded_case.body, (*path, index, 0), target))

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
        case Activity(inputs=inputs) | HybridSwitch(inputs=inputs):
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
    for transition_path, activity_name, variants in lowering.hybrid_paths:
        uri = built.net.handler_uri(transition_path)
        assert uri is not None
        handlers[uri] = PoolVariantHandler(built.net, transition_path, by_name[activity_name], variants)
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
