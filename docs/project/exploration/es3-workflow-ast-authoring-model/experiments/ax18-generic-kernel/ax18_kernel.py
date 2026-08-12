"""AX18 kernel — a net-agnostic fragment IR beneath the domain vocabulary.

The kernel answers one question: what does the Petri-net layer *actually*
need to know, once every domain decision (port resolution, guard
rendering, exclusivity chaining, handler synthesis) has already been
made? The answer this IR asserts:

- **Places** are (identifier name, nominal color string). No Python
  type is required at this layer: frozen Petrus colors are strings, and
  ``PlaceSpec`` accepts them directly. Identity is the *name* — two
  places may share a color (AX3's ruling made structural).
- **Transitions** are (identifier name, ordered arcs, optional rendered
  CEL guard, optional work). The guard arrives as a *string*: predicate
  safety (AX16), scope resolution, and exclusivity chaining are
  authoring-layer duties. The kernel only promises the guard's variable
  scope is the transition's consume/read place names.
- **Arcs** are (place name, mode) with mode ∈ consume | read | produce.
  Arc order is meaningful and preserved verbatim: it is the wiring
  order onto the frozen ``NetSpec``, and serialized ``NetDefinitionV3``
  arc positions follow it (AX14's composition-order finding).
- **Work** is one of three things, exactly the three the frozen runtime
  distinguishes: nothing (Petrus default-binds pure ``passthrough``),
  a Petri-aware handler function (``petri_handler``), or an activity
  definition (string declaration + post-build ``DerivedActivityHandler``,
  dispatched through Motus — AX2's contract).

Everything else the domain AST says — lanes, choices, folds, updates,
retirement, scatter routing — desugars *into* these four notions (see
``ax18_desugar``), which is the experiment's claim: the AX11 vocabulary
is sugar, not semantics.

Handler output contract: every kernel place is root-scope, so a
``PetriWork`` handler addresses its outputs as ``NetPath(place_name)``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from types import MappingProxyType

from petrus.impetus.binding import ActivityHandler, DerivedActivityHandler, Handler
from petrus.impetus.dsl import BuiltNet, NetSpec, PlaceSpec, TransitionSpec, arc, petri_handler
from petrus.impetus.petrinet import Cel, NetPath
from petrus.impetus.petrinet.schema import NetUri
from petrus.motus.activity import ActivityDeclaration, ActivityDefinition, AsyncActivityDefinition


class KernelShapeError(ValueError):
    """A kernel net was declared with an impossible shape."""


class Mode(Enum):
    CONSUME = "consume"
    READ = "read"
    PRODUCE = "produce"


@dataclass(frozen=True)
class KernelPlace:
    """A named, colored place. Name is identity; color is a nominal string."""

    name: str
    color: str
    origin: str | None = dataclass_field(default=None, compare=False)


@dataclass(frozen=True)
class KernelArc:
    place: str
    mode: Mode


def consume(place: str) -> KernelArc:
    return KernelArc(place, Mode.CONSUME)


def read(place: str) -> KernelArc:
    return KernelArc(place, Mode.READ)


def produce(place: str) -> KernelArc:
    return KernelArc(place, Mode.PRODUCE)


@dataclass(frozen=True)
class ActivityWork:
    """Dispatch through the frozen dispatcher: string declaration now,
    ``DerivedActivityHandler`` bound post-build (AX2's lowering)."""

    definition: ActivityDefinition | AsyncActivityDefinition


@dataclass(frozen=True)
class PetriWork:
    """A ready Petri-aware handler: ``(binding, outputs) -> {NetPath: tokens}``.

    The kernel does not synthesize handlers — the authoring layer that
    knows about hydration, routing, and typed steps builds the closure
    and hands it down whole.
    """

    handler: Handler


type Work = ActivityWork | PetriWork | None


@dataclass(frozen=True)
class KernelTransition:
    """One transition: ordered arcs, an optional *rendered* CEL guard
    (variables are the consume/read place names), and optional work."""

    name: str
    arcs: tuple[KernelArc, ...]
    guard: str | None = None
    work: Work = None
    label: str | None = dataclass_field(default=None, compare=False)
    address: str | None = dataclass_field(default=None, compare=False)
    origin: str | None = dataclass_field(default=None, compare=False)


type KernelNode = KernelPlace | KernelTransition


@dataclass(frozen=True)
class KernelNet:
    """An ordered net declaration. Node order is deterministic build
    order: places serialize in declaration order, transitions likewise,
    and each transition's arcs wire in their stored order."""

    name: str
    nodes: tuple[KernelNode, ...]


def kernel_net(name: str, *nodes: KernelNode) -> KernelNet:
    place_names: set[str] = set()
    transition_names: set[str] = set()
    for node in nodes:
        match node:
            case KernelPlace():
                if not node.name.isidentifier():
                    raise KernelShapeError(
                        f"place name {node.name!r} must be a bare identifier — it is "
                        f"the root-scope place path and the CEL guard variable"
                    )
                if node.name in place_names:
                    raise KernelShapeError(f"duplicate place {node.name!r}")
                place_names.add(node.name)
            case KernelTransition():
                if not node.name.isidentifier():
                    raise KernelShapeError(f"transition name {node.name!r} must be a bare identifier")
                if node.name in transition_names:
                    raise KernelShapeError(f"duplicate transition {node.name!r}")
                transition_names.add(node.name)
                if not node.arcs:
                    raise KernelShapeError(f"transition {node.name!r} has no arcs — it can never participate")
                for kernel_arc in node.arcs:
                    if kernel_arc.place not in place_names:
                        raise KernelShapeError(
                            f"transition {node.name!r} references undeclared place "
                            f"{kernel_arc.place!r} — kernel places must be declared "
                            f"before the transitions that touch them"
                        )
            case _:
                raise KernelShapeError(f"kernel nodes are places and transitions, got {node!r}")
    return KernelNet(name=name, nodes=tuple(nodes))


@dataclass(frozen=True)
class KernelSourceEntry:
    label: str
    origin: str | None
    transition: str | None = None
    guard_cel: str | None = None
    places: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoweredKernel:
    built: BuiltNet
    places: Mapping[str, NetPath]
    handlers: Mapping[NetUri | str, Handler | ActivityHandler]
    activities: tuple[ActivityDeclaration, ...]
    source_map: Mapping[str, KernelSourceEntry] = dataclass_field(default_factory=dict)
    generated_by: Mapping[str, str] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "places", MappingProxyType(dict(self.places)))
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "source_map", MappingProxyType(dict(self.source_map)))
        object.__setattr__(self, "generated_by", MappingProxyType(dict(self.generated_by)))


def _wire(transition: TransitionSpec, node: KernelTransition, places: dict[str, PlaceSpec]) -> None:
    """Wire arcs in stored order: reads first, then consumes >> t >> produces.

    This is the exact order the AX11 compiler wires (read arcs before
    the consume/produce statement), so a desugared net serializes with
    identical arc positions.
    """
    reads = [kernel_arc for kernel_arc in node.arcs if kernel_arc.mode is Mode.READ]
    consumes = [kernel_arc for kernel_arc in node.arcs if kernel_arc.mode is Mode.CONSUME]
    produces = [kernel_arc for kernel_arc in node.arcs if kernel_arc.mode is Mode.PRODUCE]
    for kernel_arc in reads:
        places[kernel_arc.place] >> arc.read() >> transition
    inputs = tuple(places[kernel_arc.place] for kernel_arc in consumes)
    outputs = tuple(places[kernel_arc.place] for kernel_arc in produces)
    if inputs and outputs:
        inputs >> transition >> outputs
    elif inputs:
        inputs >> transition
    elif outputs:
        transition >> outputs


def lower_kernel(net: KernelNet) -> LoweredKernel:
    """Replay the kernel declaration onto the frozen ``NetSpec`` — no
    decisions, only emission. Every decision already happened upstream."""

    spec = NetSpec(net.name)
    places: dict[str, PlaceSpec] = {}
    activity_transitions: list[tuple[TransitionSpec, ActivityWork]] = []
    source_map: dict[str, KernelSourceEntry] = {}
    generated_by: dict[str, str] = {}

    for node in net.nodes:
        match node:
            case KernelPlace():
                places[node.name] = getattr(spec.p, node.name)(node.color)
            case KernelTransition():
                handler = None
                match node.work:
                    case ActivityWork(definition=definition):
                        handler = definition.declaration.name
                    case PetriWork(handler=implementation):
                        handler = petri_handler(implementation)
                guards = Cel(node.guard) if node.guard is not None else ()
                transition = getattr(spec.t, node.name)(handler=handler, guards=guards)
                _wire(transition, node, places)
                if isinstance(node.work, ActivityWork):
                    activity_transitions.append((transition, node.work))
                address = node.address if node.address is not None else node.name
                source_map[address] = KernelSourceEntry(
                    label=node.label if node.label is not None else node.name,
                    origin=node.origin,
                    transition=str(abs(transition)),
                    guard_cel=node.guard,
                    places=tuple(
                        str(abs(places[kernel_arc.place]))
                        for kernel_arc in node.arcs
                        if kernel_arc.mode is Mode.PRODUCE
                    ),
                )
                generated_by[str(abs(transition))] = address

    built = spec.build()
    handlers: dict[NetUri | str, Handler | ActivityHandler] = dict(built.handlers)
    declarations: list[ActivityDeclaration] = []
    for transition, work in activity_transitions:
        uri = built.net.handler_uri(abs(transition))
        assert uri is not None
        handlers[uri] = DerivedActivityHandler(built.net, abs(transition), work.definition)
        declarations.append(work.definition.declaration)

    return LoweredKernel(
        built=built,
        places={name: abs(place) for name, place in places.items()},
        handlers=handlers,
        activities=tuple(declarations),
        source_map=source_map,
        generated_by=generated_by,
    )
