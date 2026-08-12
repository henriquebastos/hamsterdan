"""AX23 — the completed block algebra: merge, loop, and context ports.

AX22 closed with three shaped gaps. This module restates its algebra
(the AX19-restates-AX18 precedent) with exactly the missing pieces:

- ``merge`` — explicit convergence: two same-colored exits fuse into
  one (the AX5 later-merge, previously refused). Never silent: the
  author names the exits and the merged name.
- ``loop`` — a cycle at composition level: a named exit fuses back
  into the block's *own* entry. The authoring expression stays a tree
  (the AX8 hypothesis); the net becomes cyclic. Boundedness remains
  the classifier's responsibility, data-driven, as AX21 bounded its
  retries.
- **Context ports** — declared ambient state, exempt from the
  entry→exit path rule *because* declared:
  - ``classify(..., reads=...)`` reads a context place through a read
    arc (the AX20 fence, as a data-driven classification — the read
    happens atomically in the firing, the handler routes on it);
  - ``holding(block, context=...)`` is the AX20 claim bracket, built
    from handler-less passthrough transitions exactly like AX20's own
    claim: a claim transition consumes the outer entry token *and* the
    context token, parks the claim in a held place, and one release
    transition per exit returns the context token — the structural
    mutex, visible in the net, never hidden (the AX20 doctrine).

Everything else — port fusion, color-addressed handlers, purity
propagation, static soundness — carries over from AX22 unchanged. Two
disciplines tighten:

- a context-reading step can never be ``pure`` (the fence-once rule:
  reads of shared state belong at boundaries, so they can never sit
  inside a disposable interior);
- ``disposable`` refuses any block with contexts, pure or not.

Context places are shared **by name** across composition (the AX14
rule: only explicit same-named ports merge) and are the one declared
exception to bounded hub degree — the hubs are still there, but now
they are contracts, not smear.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from ax19_kernel import (
    BoundaryTransition,
    KernelPlace,
    LoweredBoundary,
    Mode,
    PetriWork,
    boundary_net,
    consume,
    lower_boundary,
    produce,
    read,
)
from petrus.impetus.petrinet import Token

type KernelNode = KernelPlace | BoundaryTransition


class CompositionError(ValueError):
    """A block composition that cannot mean anything."""


@dataclass(frozen=True)
class Port:
    place: str
    color: str


@dataclass(frozen=True)
class Block:
    """A function-like subnet value: one entry, named typed exits, and
    declared context ports for ambient state."""

    name: str
    nodes: tuple[KernelNode, ...]
    entry: Port
    exits: Mapping[str, Port]
    pure: bool
    contexts: Mapping[str, Port] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "exits", MappingProxyType(dict(self.exits)))
        object.__setattr__(self, "contexts", MappingProxyType(dict(self.contexts)))


# -- the one output-addressing rule -------------------------------------------------


def _target(outputs, color: str):
    """Address an output arc by color — never by place name — so
    handlers survive every rename the algebra performs."""
    matches = [arc for arc in outputs if arc.color == color]
    if len(matches) != 1:
        raise CompositionError(f"expected exactly one {color!r} output, got {len(matches)}")
    return matches[0].target


# -- leaves --------------------------------------------------------------------------


def transform(name: str, fn: Callable[[dict], dict], *, accepts: str, returns: str) -> Block:
    """A pure linear step: one in, one out, no world, no contexts."""

    def handler(binding, outputs):
        [token] = binding.tokens
        return {_target(outputs, returns): (Token(returns, fn(dict(token.data))),)}

    entry, out = f"{name}_in", f"{name}_out"
    nodes = (
        KernelPlace(entry, accepts),
        KernelPlace(out, returns),
        BoundaryTransition(name=name, arcs=(consume(entry), produce(out)), work=PetriWork(handler)),
    )
    return Block(name, nodes, Port(entry, accepts), {"out": Port(out, returns)}, pure=True)


def classify(
    name: str,
    fn: Callable[..., tuple[str, dict]],
    *,
    accepts: str,
    outcomes: Mapping[str, str],
    pure: bool = False,
    reads: tuple[tuple[str, str], ...] = (),
) -> Block:
    """A typed-outcome step. With ``reads``, the transition reads the
    named context places and ``fn(data, contexts)`` sees their token
    data — the AX20 fence as data-driven classification. A reading
    step can never be pure: reads of shared state belong at
    boundaries, never inside a disposable interior."""

    if len(set(outcomes.values())) != len(outcomes):
        raise CompositionError(f"block {name!r}: outcome colors must be distinct — color is how handlers address exits")
    if reads and pure:
        raise CompositionError(
            f"block {name!r} reads contexts {sorted(n for n, _ in reads)} and cannot be pure — "
            f"the fence-once rule (AX20): shared-state reads belong at boundaries"
        )

    def handler(binding, outputs):
        [(_, selected)] = list(binding.consumed)
        [token] = selected
        if reads:
            contexts = {str(path): one.data for path, chosen in binding.read for one in chosen}
            exit_name, data = fn(dict(token.data), contexts)
        else:
            exit_name, data = fn(dict(token.data))
        if exit_name not in outcomes:
            raise CompositionError(f"block {name!r} classified {exit_name!r}, not one of {sorted(outcomes)}")
        color = outcomes[exit_name]
        return {_target(outputs, color): (Token(color, data),)}

    entry = f"{name}_in"
    nodes = (
        KernelPlace(entry, accepts),
        *(KernelPlace(context, color) for context, color in reads),
        *(KernelPlace(f"{name}_{exit_name}", color) for exit_name, color in outcomes.items()),
        BoundaryTransition(
            name=name,
            arcs=(
                consume(entry),
                *(read(context) for context, _ in reads),
                *(produce(f"{name}_{exit_name}") for exit_name in outcomes),
            ),
            work=PetriWork(handler),
        ),
    )
    exits = {exit_name: Port(f"{name}_{exit_name}", color) for exit_name, color in outcomes.items()}
    contexts = {context: Port(context, color) for context, color in reads}
    return Block(name, nodes, Port(entry, accepts), exits, pure=pure, contexts=contexts)


# -- renaming machinery ----------------------------------------------------------------


def _rename(nodes: tuple[KernelNode, ...], mapping: Mapping[str, str]) -> tuple[KernelNode, ...]:
    """Substitute place names in arcs; drop the place nodes being
    absorbed (a mapping entry ``name -> name`` just deduplicates)."""
    renamed: list[KernelNode] = []
    for node in nodes:
        match node:
            case KernelPlace() if node.name in mapping:
                continue
            case KernelPlace():
                renamed.append(node)
            case BoundaryTransition():
                arcs = tuple(replace(arc, place=mapping.get(arc.place, arc.place)) for arc in node.arcs)
                renamed.append(replace(node, arcs=arcs))
    return tuple(renamed)


def _refuse_double_produce(nodes: tuple[KernelNode, ...], doing: str) -> None:
    for node in nodes:
        if isinstance(node, BoundaryTransition):
            targets = [arc.place for arc in node.arcs if arc.mode is Mode.PRODUCE]
            if len(targets) != len(set(targets)):
                raise CompositionError(f"{doing} would make transition {node.name!r} produce twice into one place")


# -- combinators -------------------------------------------------------------------------


def then(a: Block, b: Block, *, on: str) -> Block:
    """Route a's named exit into b's entry by port fusion. Contexts
    union by explicit shared name (the AX14 rule); a shared name must
    agree on color."""

    if on not in a.exits:
        raise CompositionError(f"block {a.name!r} has no exit {on!r}; its exits are {sorted(a.exits)}")
    exit_port = a.exits[on]
    if exit_port.color != b.entry.color:
        raise CompositionError(
            f"cannot fuse {a.name!r} exit {on!r} ({exit_port.color}) "
            f"into {b.name!r} entry ({b.entry.color}): colors differ"
        )
    shared = set(a.contexts) & set(b.contexts)
    for context in sorted(shared):
        if a.contexts[context].color != b.contexts[context].color:
            raise CompositionError(
                f"context {context!r} is {a.contexts[context].color} in {a.name!r} "
                f"but {b.contexts[context].color} in {b.name!r}"
            )
    a_names = {node.name for node in a.nodes}
    b_names = {node.name for node in b.nodes} - {b.entry.place}
    if collisions := sorted((a_names & b_names) - shared):
        raise CompositionError(
            f"blocks {a.name!r} and {b.name!r} share node names {collisions}: leaf names must be unique"
        )
    if duplicate_exits := sorted((set(a.exits) - {on}) & set(b.exits)):
        raise CompositionError(
            f"composing {a.name!r} and {b.name!r} duplicates exit names {duplicate_exits}: rename_exit one side first"
        )
    mapping = {b.entry.place: exit_port.place} | {context: context for context in shared}
    return Block(
        name=f"({a.name} >> {b.name})",
        nodes=a.nodes + _rename(b.nodes, mapping),
        entry=a.entry,
        exits={name: port for name, port in a.exits.items() if name != on} | dict(b.exits),
        pure=a.pure and b.pure,
        contexts=dict(a.contexts) | dict(b.contexts),
    )


def rename_exit(block: Block, old: str, new: str) -> Block:
    if old not in block.exits:
        raise CompositionError(f"block {block.name!r} has no exit {old!r}; its exits are {sorted(block.exits)}")
    if new != old and new in block.exits:
        raise CompositionError(f"block {block.name!r} already has an exit {new!r}")
    exits = {new if name == old else name: port for name, port in block.exits.items()}
    return replace(block, exits=exits)


def merge(block: Block, *names: str, into: str) -> Block:
    """Explicit convergence: the named same-colored exits fuse into
    one exit called ``into`` — the AX5 later-merge, by declaration."""

    if len(names) < 2:
        raise CompositionError(f"merge needs at least two exits, got {list(names)}")
    for name in names:
        if name not in block.exits:
            raise CompositionError(f"block {block.name!r} has no exit {name!r}; its exits are {sorted(block.exits)}")
    colors = {block.exits[name].color for name in names}
    if len(colors) != 1:
        raise CompositionError(f"cannot merge exits {sorted(names)}: colors differ ({sorted(colors)})")
    remaining = set(block.exits) - set(names)
    if into in remaining:
        raise CompositionError(f"block {block.name!r} already has an exit {into!r}")
    survivor = block.exits[names[0]]
    mapping = {block.exits[name].place: survivor.place for name in names[1:]}
    nodes = _rename(block.nodes, mapping)
    _refuse_double_produce(nodes, f"merging {sorted(names)}")
    exits = {name: port for name, port in block.exits.items() if name not in names} | {into: survivor}
    return replace(block, nodes=nodes, exits=exits)


def loop(block: Block, *, on: str) -> Block:
    """A cycle at composition level: the named exit fuses back into
    the block's own entry. The tree expression compiles to a cyclic
    net; boundedness stays data-driven in the routing classifier."""

    if on not in block.exits:
        raise CompositionError(f"block {block.name!r} has no exit {on!r}; its exits are {sorted(block.exits)}")
    exit_port = block.exits[on]
    if exit_port.color != block.entry.color:
        raise CompositionError(
            f"cannot loop {block.name!r} exit {on!r} ({exit_port.color}) "
            f"into its entry ({block.entry.color}): colors differ"
        )
    if len(block.exits) == 1:
        raise CompositionError(f"looping {block.name!r}'s only exit {on!r} would leave no way out")
    nodes = _rename(block.nodes, {exit_port.place: block.entry.place})
    _refuse_double_produce(nodes, f"looping {on!r}")
    return replace(block, nodes=nodes, exits={name: port for name, port in block.exits.items() if name != on})


def holding(block: Block, *, context: str, color: str) -> Block:
    """The AX20 claim bracket: consume the context token at entry,
    hold it beside the run, return it at every exit — a structural
    mutex made of handler-less passthrough transitions, exactly like
    AX20's own claim and discard. Visible, never hidden."""

    if context in block.contexts:
        raise CompositionError(f"block {block.name!r} already declares context {context!r}")
    if not block.exits:
        raise CompositionError(f"block {block.name!r} has no exits to release {context!r} through")
    boundary_colors = {block.entry.color} | {port.color for port in block.exits.values()}
    if color in boundary_colors:
        raise CompositionError(
            f"context {context!r} color {color!r} collides with an entry/exit color: "
            f"passthrough claim/release routes by color and could not tell them apart"
        )
    gate = f"{context}_gate"
    held = f"{context}_held"
    taken = {node.name for node in block.nodes}
    for name in (context, gate, held):
        if name in taken:
            raise CompositionError(f"holding {context!r} needs place name {name!r}, already used in {block.name!r}")

    claim = BoundaryTransition(
        name=f"claim_{context}",
        arcs=(consume(gate), consume(context), produce(block.entry.place), produce(held)),
        label=f"take {context!r}: the structural mutex — an empty {context!r} place blocks every rival entry",
    )
    releases = []
    exits = {}
    for exit_name, port in block.exits.items():
        outer = f"{exit_name}_exit"
        if outer in taken:
            raise CompositionError(f"holding {context!r} needs place name {outer!r}, already used in {block.name!r}")
        releases.append(KernelPlace(outer, port.color))
        releases.append(
            BoundaryTransition(
                name=f"release_{exit_name}",
                arcs=(consume(port.place), consume(held), produce(outer), produce(context)),
                label=f"return {context!r} on the {exit_name!r} path",
            )
        )
        exits[exit_name] = Port(outer, port.color)

    return Block(
        name=f"holding[{context}]({block.name})",
        nodes=(
            KernelPlace(gate, block.entry.color),
            KernelPlace(context, color),
            KernelPlace(held, color),
            *block.nodes,
            claim,
            *releases,
        ),
        entry=Port(gate, block.entry.color),
        exits=exits,
        pure=block.pure,
        contexts=dict(block.contexts) | {context: Port(context, color)},
    )


def disposable(block: Block) -> Block:
    """Declare a fenced interior (AX20). Refused for effectful blocks
    *and* for context-touching blocks: a run that may be discarded
    wholesale must neither have touched the world nor read shared
    state on the way."""
    if block.contexts:
        raise CompositionError(
            f"block {block.name!r} touches contexts {sorted(block.contexts)}: a disposable interior "
            f"may not depend on shared state — fence once, at the exit (AX20)"
        )
    if not block.pure:
        raise CompositionError(
            f"block {block.name!r} is not pure: a disposable interior may not contain effects — "
            f"the commit boundary is the only effect-emitting point (AX20)"
        )
    return block


# -- soundness, decided statically ----------------------------------------------------------


def check_sound(block: Block) -> Block:
    """Every non-context node must lie on an entry→exit path. Context
    places are the declared exemption — that declaration is exactly
    what makes ambient state a contract instead of smear."""

    places = {node.name for node in block.nodes if isinstance(node, KernelPlace)}
    transitions = [node for node in block.nodes if isinstance(node, BoundaryTransition)]
    if block.entry.place not in places:
        raise CompositionError(f"block {block.name!r}: entry place {block.entry.place!r} is not among its places")
    for name, port in block.exits.items():
        if port.place not in places:
            raise CompositionError(f"block {block.name!r}: exit {name!r} place {port.place!r} is not among its places")
    for name, port in block.contexts.items():
        if port.place not in places:
            raise CompositionError(
                f"block {block.name!r}: context {name!r} place {port.place!r} is not among its places"
            )

    ambient = {port.place for port in block.contexts.values()}
    forward: dict[str, set[str]] = {}
    backward: dict[str, set[str]] = {}
    for node in transitions:
        for arc in node.arcs:
            if arc.mode is Mode.INHIBIT:
                raise CompositionError(
                    f"block {block.name!r}: inhibitor arcs are outside the block algebra (transition {node.name!r})"
                )
            if arc.place in ambient:
                continue
            source, target = (arc.place, node.name) if arc.mode is not Mode.PRODUCE else (node.name, arc.place)
            forward.setdefault(source, set()).add(target)
            backward.setdefault(target, set()).add(source)

    def reach(start: set[str], edges: dict[str, set[str]]) -> set[str]:
        seen, frontier = set(start), list(start)
        while frontier:
            for successor in edges.get(frontier.pop(), ()):
                if successor not in seen:
                    seen.add(successor)
                    frontier.append(successor)
        return seen

    nodes = (places - ambient) | {node.name for node in transitions}
    from_entry = reach({block.entry.place}, forward)
    to_exit = reach({port.place for port in block.exits.values()}, backward)
    if stranded := sorted(nodes - (from_entry & to_exit)):
        raise CompositionError(f"block {block.name!r} is not sound: nodes {stranded} lie on no entry→exit path")
    return block


# -- lowering ----------------------------------------------------------------------------------


def compile_block(net_name: str, block: Block) -> LoweredBoundary:
    check_sound(block)
    places = tuple(node for node in block.nodes if isinstance(node, KernelPlace))
    transitions = tuple(node for node in block.nodes if isinstance(node, BoundaryTransition))
    return lower_boundary(boundary_net(net_name, *places, *transitions))
