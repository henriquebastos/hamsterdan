"""AX14 — composing independently authored fragments into one net.

Design question: can two concern fragments, authored independently as
values, be composed into one deterministic net by **explicit named-port
identity** — without mutating either source AST (AX13 grew the net by
tree surgery / restating the whole fragment) and without Python type
identity ever merging places (AX3's ruling)?

The mechanism this spike tests:

- ``compose(name, *fragments)`` lowers each fragment into **one shared
  ``NetSpec``**, merging places by port *name* only. A name shared
  across fragments is the composition surface — the hand-off.
- A shared name must agree exactly in color and port kind across
  fragments; disagreement is a loud ``CompositionError``, never a silent
  first-declaration-wins (which is what naive shared ``place_specs``
  reuse would do).
- ``handoff_fragment()`` is the minimal AST growth composition demands:
  a fragment whose entry tokens are adjudicated by a guarded ``choice``
  rather than transformed by an activity — the shape every consumer of
  another fragment's ``EXIT`` lane takes. Its lowering is exactly AX11's
  lane-choice machinery applied to the entry port; routing stays with
  the producer.
- Transition names share one namespace: cross-fragment duplicates fail
  through AX11's existing ``_transition_name`` check.
- Source-map addresses are prefixed with the owning fragment's name, so
  every generated transition still maps to its true authoring site —
  even when concerns live in different files.
"""

from __future__ import annotations

from dataclasses import dataclass

from ax11_ast import (
    WAIT,
    ActivityStep,
    Choice,
    Fragment,
    Port,
    ReadPort,
    Retire,
    Scatter,
    StatePort,
    Update,
    WorkflowShapeError,
    _caller_origin,
)
from ax11_compiler import SourceMapEntry, _Lowering
from petrus.impetus.binding import ActivityHandler, DerivedActivityHandler, Handler
from petrus.impetus.dsl import BuiltNet, NetSpec, PlaceSpec
from petrus.impetus.petrinet import NetPath
from petrus.impetus.petrinet.schema import NetUri
from petrus.motus.activity import ActivityDeclaration


class CompositionError(ValueError):
    """Fragments disagree about a shared surface."""


def handoff_fragment(
    name: str,
    *,
    entry: Port,
    reads: tuple[ReadPort, ...] = (),
    states: tuple[StatePort, ...] = (),
    body: Choice,
) -> Fragment:
    """A concern that consumes another fragment's exit port.

    Its entry tokens are adjudicated by a guarded ``choice`` rather than
    transformed by an activity: the producer already routed them, so the
    consumer's first move is a decision, not a transformation.
    """
    if not isinstance(body, Choice):
        raise WorkflowShapeError(f"handoff_fragment {name!r} body= needs choice(...), got {type(body).__name__}")
    surface: list[Port] = [entry, *reads, *states]
    for current_case in body.cases:
        if isinstance(current_case.then, Update):
            surface.extend(current_case.then.emits)
    names = [p.name for p in surface]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise WorkflowShapeError(f"handoff fragment {name!r} declares duplicate port names: {duplicates}")
    return Fragment(name=name, entry=entry, reads=reads, states=states, body=(body,), origin=_caller_origin())


class _CompositionLowering(_Lowering):
    """AX11's lowering, sharing spec/places/transition-namespace across
    fragments and refusing shared-name disagreements loudly."""

    def __init__(
        self,
        fragment: Fragment,
        spec: NetSpec,
        place_specs: dict[str, PlaceSpec],
        transition_names: set[str],
        declared_ports: dict[str, tuple[Port, str]],
    ) -> None:
        super().__init__(fragment)
        self.spec = spec
        self.place_specs = place_specs
        self.transition_names = transition_names
        self._declared = declared_ports

    def place(self, port: Port) -> PlaceSpec:
        prior = self._declared.get(port.name)
        if prior is not None:
            prior_port, owner = prior
            if prior_port.color != port.color or type(prior_port) is not type(port):
                raise CompositionError(
                    f"port {port.name!r}: fragment {self.fragment.name!r} declares "
                    f"{type(port).__name__}[{port.color}], but fragment {owner!r} declared "
                    f"{type(prior_port).__name__}[{prior_port.color}] — composition merges places "
                    f"by name, so a shared port must agree exactly in color and kind"
                )
        else:
            self._declared[port.name] = (port, self.fragment.name)
        return super().place(port)

    def lower(self) -> None:
        current = self.place(self.fragment.entry)
        for read in self.fragment.reads:
            self.place(read)
        for state in self.fragment.states:
            self.place(state)
        for index, step in enumerate(self.fragment.body):
            address = f"/body/{index}"
            match step:
                case ActivityStep():
                    current = self._lower_activity(step, address, current)
                case Scatter():
                    self._lower_scatter(step, address, current)
                case Choice():
                    self._lower_entry_choice(step, address)
                case other:
                    raise CompositionError(f"fragment {self.fragment.name!r} cannot lower body step {other!r}")

    def _lower_entry_choice(self, node: Choice, address: str) -> None:
        """AX11's lane-choice lowering applied to the hand-off entry port."""
        entry = self.fragment.entry
        resolved = self._resolvable(entry)
        predecessors = []
        for index, current_case in enumerate(node.cases):
            self._lower_case(current_case, entry, resolved, tuple(predecessors), f"{address}/cases/{index}")
            predecessors.append(current_case.when)
        if isinstance(node.otherwise, Retire):
            self._lower_otherwise(entry, resolved, tuple(predecessors), f"{address}/otherwise")
        else:
            self._record(
                f"{address}/otherwise",
                f"hand-off {entry.name!r} gap policy WAIT: a token matching no case "
                f"parks on the hand-off place until state changes re-enable a case",
                node.origin,
                None,
            )


@dataclass(frozen=True)
class ComposedNet:
    built: BuiltNet
    places: dict[str, NetPath]
    handlers: dict[NetUri | str, Handler | ActivityHandler]
    activities: tuple[ActivityDeclaration, ...]
    source_map: dict[str, SourceMapEntry]
    generated_by: dict[str, str]


def compose(name: str, *fragments: Fragment) -> ComposedNet:
    """Lower fragments in the given (deterministic) order into one net,
    merging places by explicit port-name identity."""
    if not fragments:
        raise CompositionError("compose() needs at least one fragment")
    if len({fragment.name for fragment in fragments}) != len(fragments):
        raise CompositionError("composed fragments need unique names — they prefix the source map")
    spec = NetSpec(name)
    place_specs: dict[str, PlaceSpec] = {}
    transition_names: set[str] = set()
    declared_ports: dict[str, tuple[Port, str]] = {}
    lowerings: list[_CompositionLowering] = []
    for fragment in fragments:
        lowering = _CompositionLowering(fragment, spec, place_specs, transition_names, declared_ports)
        lowering.lower()
        lowerings.append(lowering)
    built = spec.build()

    handlers: dict[NetUri | str, Handler | ActivityHandler] = dict(built.handlers)
    declarations: list[ActivityDeclaration] = []
    source_map: dict[str, SourceMapEntry] = {}
    generated_by: dict[str, str] = {}
    for fragment, lowering in zip(fragments, lowerings):
        for transition, step in lowering.activity_steps:
            uri = built.net.handler_uri(abs(transition))
            assert uri is not None
            handlers[uri] = DerivedActivityHandler(built.net, abs(transition), step.definition)
            declarations.append(step.definition.declaration)
        for address, entry in lowering.source_map.items():
            source_map[f"/{fragment.name}{address}"] = entry
        for transition_name, address in lowering.generated_by.items():
            generated_by[transition_name] = f"/{fragment.name}{address}"

    return ComposedNet(
        built=built,
        places={port_name: abs(place) for port_name, place in place_specs.items()},
        handlers=handlers,
        activities=tuple(declarations),
        source_map=source_map,
        generated_by=generated_by,
    )


__all__ = ["WAIT", "ComposedNet", "CompositionError", "compose", "handoff_fragment"]
