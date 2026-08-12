"""AX11 compiler — lowering the fragment AST onto the frozen Petrus Net.

Lowering contract, extended from AX2/AX4 for the state-machine shape:

- Every declared port becomes one **root-scope place named by the
  author** (flat, identifier-safe). This is not cosmetic: a CEL binding
  guard's variable scope is exactly the transition's consume/read input
  place names, and dotted scoped paths (``w.0.out``) cannot be CEL
  variables. Flat authored names are what make guards compilable.
- ``ActivityStep`` lowers exactly as AX2: one transition, a string
  handler declaration, a ``DerivedActivityHandler`` bound post-build.
- ``Scatter`` lowers to one transition with a synthesized routing
  handler: hydrate the batch, apply the pure transform, route each item
  to the single lane whose predicate holds (decided in Python — frozen
  output arcs admit by color only, so the net cannot carry this filter;
  see SP-7 candidate in the speculation ledger). Items no lane admits
  are dropped, exactly as the declared ``rest=DROP`` says.
- ``Choice`` lowers each case to its own transition competing on the
  lane place. Guards are inline CEL over the binding
  (``authority[0].data.epoch == reply_basis[0].data.epoch && ...``),
  chained ordered-exclusive: case *k* conjoins the negations of every
  predecessor. When a predecessor's predicate reads a port the case
  itself would not bind, the compiler **widens the case's scope with a
  read arc** on that port — mechanical exclusivity instead of a
  hand-waved disjointness argument, at the visible cost of one arc.
- ``fold``/``update`` bodies become synthesized typed handlers: binding
  tokens hydrate by declared parameter annotation, outputs route to the
  state place and emit ports by name. (Frozen ``derive_typed_transform``
  handles single-result transforms only — multi-output steps are why
  production writes binding-level ``_route`` plumbing by hand.)
- Every generated element carries a source-map entry back to its AST
  node's construction site, including the rendered guard CEL.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from types import MappingProxyType

from ax11_ast import (
    ActivityStep,
    Case,
    Choice,
    Fold,
    Fragment,
    Lane,
    Port,
    Retire,
    Scatter,
    StatePort,
    Update,
    _hints,
)
from ax11_predicates import Predicate, holds, roots
from petrus.impetus.binding import ActivityHandler, DerivedActivityHandler, Handler
from petrus.impetus.dsl import BuiltNet, NetSpec, PlaceSpec, arc, petri_handler
from petrus.impetus.petrinet import Cel, NetPath, Token
from petrus.impetus.petrinet.schema import NetUri
from petrus.motus.activity import ActivityDeclaration
from pydantic import TypeAdapter


class LoweringError(ValueError):
    """The fragment AST cannot be lowered onto a valid net."""


@dataclass(frozen=True)
class SourceMapEntry:
    node: str
    origin: str | None
    transition: str | None = None
    guard_cel: str | None = None
    places: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompiledFragment:
    built: BuiltNet
    entry: NetPath
    places: Mapping[str, NetPath]  # port name -> place path
    handlers: Mapping[NetUri | str, Handler | ActivityHandler]
    activities: tuple[ActivityDeclaration, ...]
    source_map: Mapping[str, SourceMapEntry] = dataclass_field(default_factory=dict)
    generated_by: Mapping[str, str] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "places", MappingProxyType(dict(self.places)))
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "source_map", MappingProxyType(dict(self.source_map)))
        object.__setattr__(self, "generated_by", MappingProxyType(dict(self.generated_by)))


def _hydrator(model: type):
    adapter = TypeAdapter(model)

    def hydrate(data: object):
        return adapter.validate_json(json.dumps(data, sort_keys=True, separators=(",", ":")))

    return hydrate


def _token(value: object) -> Token:
    return Token(type(value).__name__, value.dump())  # type: ignore[attr-defined]


class _Lowering:
    def __init__(self, fragment: Fragment) -> None:
        self.fragment = fragment
        self.spec = NetSpec(fragment.name)
        self.place_specs: dict[str, PlaceSpec] = {}
        self.transition_names: set[str] = set()
        self.source_map: dict[str, SourceMapEntry] = {}
        self.generated_by: dict[str, str] = {}
        self.activity_steps: list[tuple[PlaceSpec, ActivityStep]] = []

    # -- ports -----------------------------------------------------------

    def place(self, port: Port) -> PlaceSpec:
        if port.name not in self.place_specs:
            self.place_specs[port.name] = getattr(self.spec.p, port.name)(port.model)
        return self.place_specs[port.name]

    def _resolvable(self, lane_port: Port) -> dict[str, Port]:
        """Ports a lane transition may bind, keyed by model name; ambiguity fails."""
        candidates: list[Port] = [lane_port, *self.fragment.reads, *self.fragment.states]
        by_type: dict[str, list[Port]] = {}
        for candidate in candidates:
            by_type.setdefault(candidate.color, []).append(candidate)
        resolved: dict[str, Port] = {}
        for color, owners in by_type.items():
            if len(owners) == 1:
                resolved[color] = owners[0]
        self._ambiguous = {color: [o.name for o in owners] for color, owners in by_type.items() if len(owners) > 1}
        return resolved

    def _resolve(self, color: str, resolved: dict[str, Port], subject: str) -> Port:
        if color in resolved:
            return resolved[color]
        if color in getattr(self, "_ambiguous", {}):
            raise LoweringError(
                f"{subject} reads {color}, but ports {self._ambiguous[color]} all carry "
                f"that type — types never identify places (AX3); this fragment "
                f"shape needs explicitly wired ports"
            )
        raise LoweringError(f"{subject} reads {color}, but the fragment declares no port of that type")

    # -- transitions -----------------------------------------------------

    def _transition_name(self, name: str, subject: str) -> str:
        if name in self.transition_names:
            raise LoweringError(f"{subject} would generate duplicate transition {name!r}")
        self.transition_names.add(name)
        return name

    def lower(self) -> None:
        current = self.place(self.fragment.entry)
        for read in self.fragment.reads:
            self.place(read)
        for state in self.fragment.states:
            self.place(state)
        for index, step in enumerate(self.fragment.body):
            match step:
                case ActivityStep():
                    current = self._lower_activity(step, f"/body/{index}", current)
                case Scatter():
                    self._lower_scatter(step, f"/body/{index}", current)

    def _lower_activity(self, step: ActivityStep, address: str, entry: PlaceSpec) -> PlaceSpec:
        name = self._transition_name(step.definition.declaration.name, f"activity at {address}")
        transition = getattr(self.spec.t, name)(handler=name)
        out = self.place(step.out)
        entry >> transition >> out
        self.activity_steps.append((transition, step))
        self._record(address, f"activity {name!r}", step.origin, transition, places=(str(abs(out)),))
        return out

    def _lower_scatter(self, node: Scatter, address: str, entry: PlaceSpec) -> None:
        name = self._transition_name(node.transform.__name__, f"scatter at {address}")
        hydrate = _hydrator(node.input_model)
        item_root = node.item_model.__name__
        lane_places = {entry_lane.port.name: self.place(entry_lane.port) for entry_lane in node.lanes}
        routes = tuple(
            (entry_lane.where, abs(lane_places[entry_lane.port.name]), entry_lane.port.name)
            for entry_lane in node.lanes
        )
        transform = node.transform

        def scatter_handler(binding, outputs, *, _routes=routes, _hydrate=hydrate, _transform=transform):
            del outputs
            [batch_token] = binding.tokens
            items = _transform(_hydrate(batch_token.data))
            routed: dict[NetPath, tuple[Token, ...]] = {}
            for item in items:
                destinations = [
                    (path, lane_name) for where, path, lane_name in _routes if holds(where, {item_root: item})
                ]
                if len(destinations) > 1:
                    lanes = [lane_name for _, lane_name in destinations]
                    raise LoweringError(f"scattered item {item!r} matched lanes {lanes}; routing must be exclusive")
                for path, _ in destinations:
                    routed[path] = routed.get(path, ()) + (_token(item),)
                # no destination: rest=DROP, declared in the AST
            return routed

        transition = getattr(self.spec.t, name)(handler=petri_handler(scatter_handler))
        entry >> transition >> tuple(lane_places.values())
        self._record(
            address,
            f"scatter {name!r} (rest=DROP)",
            node.origin,
            transition,
            places=tuple(str(abs(place)) for place in lane_places.values()),
        )
        for entry_lane in node.lanes:
            self._lower_lane(entry_lane, f"{address}/lanes/{entry_lane.port.name}")

    def _lower_lane(self, entry_lane: Lane, address: str) -> None:
        if not isinstance(entry_lane.then, Choice):
            self._record(address, f"lane {entry_lane.port.name!r} -> EXIT", entry_lane.origin, None)
            return
        node = entry_lane.then
        resolved = self._resolvable(entry_lane.port)
        predecessors: list[Predicate] = []
        for index, current_case in enumerate(node.cases):
            self._lower_case(
                current_case,
                entry_lane.port,
                resolved,
                tuple(predecessors),
                f"{address}/cases/{index}",
            )
            predecessors.append(current_case.when)
        if isinstance(node.otherwise, Retire):
            self._lower_otherwise(entry_lane.port, resolved, tuple(predecessors), f"{address}/otherwise")
        else:
            self._record(
                address + "/otherwise",
                f"lane {entry_lane.port.name!r} gap policy WAIT: a token matching no "
                f"case parks on the lane place until state changes re-enable a case",
                node.origin,
                None,
            )

    def _guard_scope(self, ports: dict[str, Port]) -> dict[str, str]:
        return {color: f"{port.name}[0].data" for color, port in ports.items()}

    def _case_ports(
        self,
        case_predicates: tuple[Predicate, ...],
        function: object | None,
        lane_port: Port,
        resolved: dict[str, Port],
        subject: str,
    ) -> tuple[dict[str, Port], dict[str, Port], set[str]]:
        """(consumed, read, widened-color-names) for one case transition."""
        consumed: dict[str, Port] = {lane_port.color: lane_port}
        read: dict[str, Port] = {}
        needed: set[str] = set()
        for predicate in case_predicates:
            needed |= roots(predicate)
        parameters: dict[str, type] = {}
        if function is not None:
            parameters, _ = _hints(function, subject)
            needed |= {annotation.__name__ for annotation in parameters.values()}
        widened: set[str] = set()
        own = roots(case_predicates[0]) if case_predicates else set()
        parameter_colors = {annotation.__name__ for annotation in parameters.values()}
        for color in sorted(needed):
            if color == lane_port.color:
                continue
            target = self._resolve(color, resolved, subject)
            if isinstance(target, StatePort) and color in parameter_colors:
                consumed[color] = target  # the case's own state: consumed, re-produced
            else:
                read[color] = target
                if color not in own and color not in parameter_colors:
                    widened.add(color)  # bound only for a negated predecessor's scope
        return consumed, read, widened

    def _lower_case(
        self,
        node: Case,
        lane_port: Port,
        resolved: dict[str, Port],
        predecessors: tuple[Predicate, ...],
        address: str,
    ) -> None:
        body = node.then
        subject = f"case at {address}"
        match body:
            case Retire():
                function = None
                name = self._transition_name(f"retire_{lane_port.name}", subject)
            case Fold() | Update():
                function = body.function
                name = self._transition_name(function.__name__, subject)
        consumed, read, widened = self._case_ports((node.when, *predecessors), function, lane_port, resolved, subject)
        if isinstance(body, (Fold, Update)) and body.state.color not in consumed:
            raise LoweringError(f"{subject}: {function.__name__} never receives its state {body.state.color}")
        scope = self._guard_scope(consumed | read)
        guard = node.when.cel(scope)
        for predecessor in predecessors:
            guard = f"{guard} && !{predecessor.cel(scope)}"
        handler = petri_handler(self._step_handler(body)) if function is not None else None
        transition = getattr(self.spec.t, name)(handler=handler, guards=Cel(guard))
        for port in read.values():
            self.place(port) >> arc.read() >> transition
        outputs: list[PlaceSpec] = []
        if isinstance(body, (Fold, Update)):
            outputs.append(self.place(body.state))
        if isinstance(body, Update):
            outputs.extend(self.place(port) for port in body.emits)
        inputs = tuple(self.place(port) for port in consumed.values())
        if outputs:
            inputs >> transition >> tuple(outputs)
        else:
            inputs >> transition
        widening = f" (scope widened by read arcs on {sorted(widened)})" if widened else ""
        kind = "retire" if function is None else f"{type(body).__name__.lower()} {function.__name__!r}"
        self._record(
            address,
            f"{kind} on lane {lane_port.name!r}{widening}",
            node.origin,
            transition,
            guard_cel=guard,
            places=tuple(str(abs(place)) for place in outputs),
        )

    def _lower_otherwise(
        self,
        lane_port: Port,
        resolved: dict[str, Port],
        predecessors: tuple[Predicate, ...],
        address: str,
    ) -> None:
        subject = f"otherwise at {address}"
        name = self._transition_name(f"retire_{lane_port.name}_otherwise", subject)
        consumed, read, widened = self._case_ports(predecessors, None, lane_port, resolved, subject)
        scope = self._guard_scope(consumed | read)
        guard = " && ".join(f"!{predecessor.cel(scope)}" for predecessor in predecessors)
        transition = getattr(self.spec.t, name)(guards=Cel(guard))
        for port in read.values():
            self.place(port) >> arc.read() >> transition
        tuple(self.place(port) for port in consumed.values()) >> transition
        widening = f" (scope widened by read arcs on {sorted(widened)})" if widened else ""
        self._record(
            address,
            f"otherwise-retire on lane {lane_port.name!r}{widening}",
            None,
            transition,
            guard_cel=guard,
        )

    def _step_handler(self, body: Fold | Update) -> Handler:
        parameters, _ = _hints(body.function, "step")
        hydrators = {name: (_hydrator(annotation), annotation.__name__) for name, annotation in parameters.items()}
        targets = (body.state, *(body.emits if isinstance(body, Update) else ()))
        place_paths = {port.name: abs(self.place(port)) for port in targets}
        target_names = tuple(port.name for port in targets)
        function = body.function
        is_update = isinstance(body, Update)

        def handler(binding, outputs):
            del outputs
            by_color = {}
            for _, selected in (*binding.consumed, *binding.read):
                for token in selected:
                    by_color[token.color] = token.data
            arguments = {name: hydrate(by_color[color]) for name, (hydrate, color) in hydrators.items()}
            result = function(**arguments)
            values = result if is_update else (result,)
            return {place_paths[target]: (_token(value),) for target, value in zip(target_names, values)}

        return handler

    def _record(self, address, node, origin, transition, *, guard_cel=None, places=()):
        entry = SourceMapEntry(
            node=node,
            origin=str(origin) if origin else None,
            transition=str(abs(transition)) if transition is not None else None,
            guard_cel=guard_cel,
            places=places,
        )
        self.source_map[address] = entry
        if transition is not None:
            self.generated_by[str(abs(transition))] = address


def compile_fragment(fragment: Fragment) -> CompiledFragment:
    lowering = _Lowering(fragment)
    lowering.lower()
    built = lowering.spec.build()

    handlers: dict[NetUri | str, Handler | ActivityHandler] = dict(built.handlers)
    declarations: list[ActivityDeclaration] = []
    for transition, step in lowering.activity_steps:
        uri = built.net.handler_uri(abs(transition))
        assert uri is not None
        handlers[uri] = DerivedActivityHandler(built.net, abs(transition), step.definition)
        declarations.append(step.definition.declaration)

    return CompiledFragment(
        built=built,
        entry=abs(lowering.place(fragment.entry)),
        places={name: abs(place) for name, place in lowering.place_specs.items()},
        handlers=handlers,
        activities=tuple(declarations),
        source_map=lowering.source_map,
        generated_by=lowering.generated_by,
    )
