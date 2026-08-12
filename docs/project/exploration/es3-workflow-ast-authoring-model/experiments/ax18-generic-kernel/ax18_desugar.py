"""AX18 desugarer — the AX11 domain vocabulary lowered onto the kernel IR.

This module is a deliberate restatement of ``ax11_compiler._Lowering``
with one difference: it never touches ``NetSpec``. Every decision the
AX11 compiler makes — port resolution by type with ambiguity refusal,
guard scope construction, ordered-exclusive predecessor chaining, scope
widening with read arcs, routing- and step-handler synthesis — happens
here, and the *outcome* is expressed purely in kernel notions: places,
transitions, consume/read/produce arcs, rendered CEL guard strings, and
ready handlers.

If the claim of the experiment holds, ``lower_kernel(desugar_fragment(f))``
serializes byte-for-byte with ``compile_fragment(f)``: the domain layer
is sugar over the kernel, and the kernel is the entire net semantics.

Emission-order discipline (what byte-identity actually requires):

- relative *place* order must match AX11's lazy creation order, so a
  place node is emitted at the same walk position AX11 first touches
  the port — including emit ports that AX11 only creates mid-case;
- relative *transition* order must match AX11's walk;
- per-transition arc order is read → consume → produce, exactly the
  AX11 wiring order.
"""

from __future__ import annotations

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
from ax11_compiler import LoweringError, _hydrator, _token
from ax11_predicates import Predicate, holds, roots
from ax18_kernel import (
    ActivityWork,
    KernelNet,
    KernelNode,
    KernelPlace,
    KernelTransition,
    LoweredKernel,
    PetriWork,
    consume,
    kernel_net,
    lower_kernel,
    produce,
)
from ax18_kernel import (
    read as read_arc,
)
from petrus.impetus.petrinet import NetPath, Token


class _Desugar:
    def __init__(self, fragment: Fragment) -> None:
        self.fragment = fragment
        self.nodes: list[KernelNode] = []
        self.declared: set[str] = set()
        self.transition_names: set[str] = set()

    # -- ports (identical resolution rules to ax11_compiler) --------------

    def place(self, port: Port) -> str:
        if port.name not in self.declared:
            self.declared.add(port.name)
            self.nodes.append(KernelPlace(port.name, port.color))
        return port.name

    def _resolvable(self, lane_port: Port) -> dict[str, Port]:
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

    def _transition_name(self, name: str, subject: str) -> str:
        if name in self.transition_names:
            raise LoweringError(f"{subject} would generate duplicate transition {name!r}")
        self.transition_names.add(name)
        return name

    # -- walk (identical order to ax11_compiler._Lowering.lower) ----------

    def desugar(self) -> KernelNet:
        current = self.place(self.fragment.entry)
        for read_port in self.fragment.reads:
            self.place(read_port)
        for state in self.fragment.states:
            self.place(state)
        for index, step in enumerate(self.fragment.body):
            match step:
                case ActivityStep():
                    current = self._activity(step, f"/body/{index}", current)
                case Scatter():
                    self._scatter(step, f"/body/{index}", current)
        return kernel_net(self.fragment.name, *self.nodes)

    def _activity(self, step: ActivityStep, address: str, entry: str) -> str:
        name = self._transition_name(step.definition.declaration.name, f"activity at {address}")
        out = self.place(step.out)
        self.nodes.append(
            KernelTransition(
                name=name,
                arcs=(consume(entry), produce(out)),
                work=ActivityWork(step.definition),
                label=f"activity {name!r}",
                address=address,
                origin=str(step.origin) if step.origin else None,
            )
        )
        return out

    def _scatter(self, node: Scatter, address: str, entry: str) -> None:
        name = self._transition_name(node.transform.__name__, f"scatter at {address}")
        hydrate = _hydrator(node.input_model)
        item_root = node.item_model.__name__
        lane_names = [self.place(entry_lane.port) for entry_lane in node.lanes]
        routes = tuple(
            (entry_lane.where, NetPath(entry_lane.port.name), entry_lane.port.name) for entry_lane in node.lanes
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

        self.nodes.append(
            KernelTransition(
                name=name,
                arcs=(consume(entry), *(produce(lane_name) for lane_name in lane_names)),
                work=PetriWork(scatter_handler),
                label=f"scatter {name!r} (rest=DROP)",
                address=address,
                origin=str(node.origin) if node.origin else None,
            )
        )
        for entry_lane in node.lanes:
            self._lane(entry_lane, f"{address}/lanes/{entry_lane.port.name}")

    def _lane(self, entry_lane: Lane, address: str) -> None:
        if not isinstance(entry_lane.then, Choice):
            return  # EXIT: the lane place is the fragment boundary — no structure
        node = entry_lane.then
        resolved = self._resolvable(entry_lane.port)
        predecessors: list[Predicate] = []
        for index, current_case in enumerate(node.cases):
            self._case(current_case, entry_lane.port, resolved, tuple(predecessors), f"{address}/cases/{index}")
            predecessors.append(current_case.when)
        if isinstance(node.otherwise, Retire):
            self._otherwise(entry_lane.port, resolved, tuple(predecessors), f"{address}/otherwise")
        # WAIT: deliberately no structure — unmatched tokens park (AX11 policy)

    # -- cases (identical scope/guard/handler decisions) -------------------

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
                consumed[color] = target
            else:
                read[color] = target
                if color not in own and color not in parameter_colors:
                    widened.add(color)
        return consumed, read, widened

    def _case(
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
        outputs: list[str] = []
        if isinstance(body, (Fold, Update)):
            outputs.append(self.place(body.state))
        if isinstance(body, Update):
            outputs.extend(self.place(port) for port in body.emits)
        work = PetriWork(_step_handler(body)) if function is not None else None
        widening = f" (scope widened by read arcs on {sorted(widened)})" if widened else ""
        kind = "retire" if function is None else f"{type(body).__name__.lower()} {function.__name__!r}"
        self.nodes.append(
            KernelTransition(
                name=name,
                arcs=(
                    *(read_arc(port.name) for port in read.values()),
                    *(consume(port.name) for port in consumed.values()),
                    *(produce(out) for out in outputs),
                ),
                guard=guard,
                work=work,
                label=f"{kind} on lane {lane_port.name!r}{widening}",
                address=address,
                origin=str(node.origin) if node.origin else None,
            )
        )

    def _otherwise(
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
        widening = f" (scope widened by read arcs on {sorted(widened)})" if widened else ""
        self.nodes.append(
            KernelTransition(
                name=name,
                arcs=(
                    *(read_arc(port.name) for port in read.values()),
                    *(consume(port.name) for port in consumed.values()),
                ),
                guard=guard,
                label=f"otherwise-retire on lane {lane_port.name!r}{widening}",
                address=address,
            )
        )


def _step_handler(body: Fold | Update):
    """The AX11 step handler, addressed by root-scope place *names*."""
    parameters, _ = _hints(body.function, "step")
    hydrators = {name: (_hydrator(annotation), annotation.__name__) for name, annotation in parameters.items()}
    targets = (body.state, *(body.emits if isinstance(body, Update) else ()))
    place_paths = {port.name: NetPath(port.name) for port in targets}
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


def desugar_fragment(fragment: Fragment) -> KernelNet:
    return _Desugar(fragment).desugar()


def compile_via_kernel(fragment: Fragment) -> LoweredKernel:
    return lower_kernel(desugar_fragment(fragment))
