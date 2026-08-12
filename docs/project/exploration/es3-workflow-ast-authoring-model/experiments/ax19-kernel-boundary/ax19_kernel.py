"""AX19 boundary kernel — testing that AX18's non-coverage is additive.

AX18 closed with a claim it did not prove: arc weights, per-arc CEL
filters, inhibitor arcs, timers, and external delivery are "additive
fields on ``KernelArc``/``KernelTransition``, not a redesign." This
module is that claim made executable — the AX18 kernel restated with
exactly the additions, nothing else moved:

- ``BoundaryArc`` gains ``weight`` (multiplicity: how many tokens the
  arc takes/observes/forbids) and ``filter`` (a rendered CEL string
  over the *token's own bare data fields* — per-token admission, the
  frozen ``compile_filter`` contract, distinct from a guard's
  binding-wide place-name scope).
- ``Mode`` gains ``INHIBIT`` — the frozen arc factory's third input
  inscription: the transition is enabled only while the place holds
  fewer than ``weight`` admitted tokens.
- ``BoundaryTransition`` gains ``timers`` — frozen ``Delay`` (matures
  a binding at anchor + duration, anchor = youngest entry instant among
  bound tokens) and ``Until`` (absolute instant), carried verbatim.
- A transition whose arcs are all ``produce`` is a **source**: frozen
  ``Net.is_source`` recognizes it, and it fires only through the
  engine's ``deliver`` door (external delivery with operation
  identity). The kernel's only duty is to permit the shape.

The lowering stays a decision-free replay. Because filters make arcs
individually distinct, input arcs wire one at a time in declared order
(AX18 wired consumes as one tuple; that was an economy, not a
semantic).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from types import MappingProxyType

from petrus.impetus.binding import ActivityHandler, DerivedActivityHandler, Handler
from petrus.impetus.dsl import BuiltNet, NetSpec, PlaceSpec, TransitionSpec, arc, petri_handler
from petrus.impetus.petrinet import Cel, Delay, NetPath, Until
from petrus.impetus.petrinet.schema import NetUri
from petrus.motus.activity import ActivityDeclaration, ActivityDefinition, AsyncActivityDefinition


class KernelShapeError(ValueError):
    """A boundary net was declared with an impossible shape."""


class Mode(Enum):
    CONSUME = "consume"
    READ = "read"
    INHIBIT = "inhibit"
    PRODUCE = "produce"


@dataclass(frozen=True)
class KernelPlace:
    name: str
    color: str
    origin: str | None = dataclass_field(default=None, compare=False)


@dataclass(frozen=True)
class BoundaryArc:
    place: str
    mode: Mode
    weight: int = 1
    filter: str | None = None  # rendered CEL over the token's bare data fields

    def __post_init__(self) -> None:
        if self.weight < 1:
            raise KernelShapeError(f"arc to {self.place!r} needs weight >= 1, got {self.weight}")
        if self.filter is not None and self.mode is Mode.PRODUCE:
            raise KernelShapeError(
                f"arc to {self.place!r}: frozen output arcs admit by color only — "
                f"a produce filter would silently not execute (the AX11 scatter "
                f"finding, now a declaration-time refusal)"
            )


def consume(place: str, *, weight: int = 1, filter: str | None = None) -> BoundaryArc:
    return BoundaryArc(place, Mode.CONSUME, weight, filter)


def read(place: str, *, weight: int = 1, filter: str | None = None) -> BoundaryArc:
    return BoundaryArc(place, Mode.READ, weight, filter)


def inhibit(place: str, *, weight: int = 1, filter: str | None = None) -> BoundaryArc:
    return BoundaryArc(place, Mode.INHIBIT, weight, filter)


def produce(place: str) -> BoundaryArc:
    return BoundaryArc(place, Mode.PRODUCE)


@dataclass(frozen=True)
class ActivityWork:
    definition: ActivityDefinition | AsyncActivityDefinition


@dataclass(frozen=True)
class PetriWork:
    handler: Handler


type Work = ActivityWork | PetriWork | None


@dataclass(frozen=True)
class BoundaryTransition:
    name: str
    arcs: tuple[BoundaryArc, ...]
    guard: str | None = None
    work: Work = None
    timers: tuple[Delay | Until, ...] = ()
    label: str | None = dataclass_field(default=None, compare=False)
    origin: str | None = dataclass_field(default=None, compare=False)

    @property
    def is_source(self) -> bool:
        return all(kernel_arc.mode is Mode.PRODUCE for kernel_arc in self.arcs)


type KernelNode = KernelPlace | BoundaryTransition


@dataclass(frozen=True)
class BoundaryNet:
    name: str
    nodes: tuple[KernelNode, ...]


def boundary_net(name: str, *nodes: KernelNode) -> BoundaryNet:
    place_names: set[str] = set()
    transition_names: set[str] = set()
    for node in nodes:
        match node:
            case KernelPlace():
                if not node.name.isidentifier():
                    raise KernelShapeError(f"place name {node.name!r} must be a bare identifier")
                if node.name in place_names:
                    raise KernelShapeError(f"duplicate place {node.name!r}")
                place_names.add(node.name)
            case BoundaryTransition():
                if node.name in transition_names:
                    raise KernelShapeError(f"duplicate transition {node.name!r}")
                transition_names.add(node.name)
                if not node.arcs:
                    raise KernelShapeError(f"transition {node.name!r} has no arcs — it can never participate")
                for kernel_arc in node.arcs:
                    if kernel_arc.place not in place_names:
                        raise KernelShapeError(
                            f"transition {node.name!r} references undeclared place {kernel_arc.place!r}"
                        )
            case _:
                raise KernelShapeError(f"kernel nodes are places and transitions, got {node!r}")
    return BoundaryNet(name=name, nodes=tuple(nodes))


@dataclass(frozen=True)
class LoweredBoundary:
    built: BuiltNet
    places: Mapping[str, NetPath]
    transitions: Mapping[str, NetPath]
    handlers: Mapping[NetUri | str, Handler | ActivityHandler]
    activities: tuple[ActivityDeclaration, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "places", MappingProxyType(dict(self.places)))
        object.__setattr__(self, "transitions", MappingProxyType(dict(self.transitions)))
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))


_INPUT_FACTORIES = {
    Mode.CONSUME: arc,
    Mode.READ: arc.read,
    Mode.INHIBIT: arc.inhibit,
}


def _wire(transition: TransitionSpec, node: BoundaryTransition, places: dict[str, PlaceSpec]) -> None:
    """Inputs one arc at a time in declared order (filters make each arc
    distinct), produces last as one tuple — same output economy as AX18."""
    produces: list[PlaceSpec] = []
    for kernel_arc in node.arcs:
        if kernel_arc.mode is Mode.PRODUCE:
            produces.append(places[kernel_arc.place])
            continue
        factory = _INPUT_FACTORIES[kernel_arc.mode]
        inscription = factory(
            weight=kernel_arc.weight,
            filter=Cel(kernel_arc.filter) if kernel_arc.filter is not None else None,
        )
        places[kernel_arc.place] >> inscription >> transition
    if produces:
        transition >> tuple(produces)


def lower_boundary(net: BoundaryNet) -> LoweredBoundary:
    spec = NetSpec(net.name)
    places: dict[str, PlaceSpec] = {}
    transitions: dict[str, TransitionSpec] = {}
    activity_transitions: list[tuple[TransitionSpec, ActivityWork]] = []

    for node in net.nodes:
        match node:
            case KernelPlace():
                places[node.name] = getattr(spec.p, node.name)(node.color)
            case BoundaryTransition():
                handler = None
                match node.work:
                    case ActivityWork(definition=definition):
                        handler = definition.declaration.name
                    case PetriWork(handler=implementation):
                        handler = petri_handler(implementation)
                guards = Cel(node.guard) if node.guard is not None else ()
                transition = getattr(spec.t, node.name)(handler=handler, guards=guards, timers=node.timers)
                _wire(transition, node, places)
                transitions[node.name] = transition
                if isinstance(node.work, ActivityWork):
                    activity_transitions.append((transition, node.work))

    built = spec.build()
    handlers: dict[NetUri | str, Handler | ActivityHandler] = dict(built.handlers)
    declarations: list[ActivityDeclaration] = []
    for transition, work in activity_transitions:
        uri = built.net.handler_uri(abs(transition))
        assert uri is not None
        handlers[uri] = DerivedActivityHandler(built.net, abs(transition), work.definition)
        declarations.append(work.definition.declaration)

    return LoweredBoundary(
        built=built,
        places={name: abs(place) for name, place in places.items()},
        transitions={name: abs(transition) for name, transition in transitions.items()},
        handlers=handlers,
        activities=tuple(declarations),
    )
