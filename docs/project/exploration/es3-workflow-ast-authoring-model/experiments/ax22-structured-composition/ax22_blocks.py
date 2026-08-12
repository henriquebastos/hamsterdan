"""AX22 — the structured-net constraint: combinators are the only
control flow, and what they combine are function-like blocks.

The Navigator's rule, made executable: *control statements may only
call functions*. A **Block** is a subnet value with one typed entry
port and named typed exit ports — the function signature AX20 and AX21
converged on (`apply : Work → Done | Rejected | Exhausted`). The only
control flow is composition:

    then(a, b, on="exit")   route a's named exit into b's entry
    rename_exit(a, old, new)  explicit names, because types are never
                              sufficient identity for topology (AX3)
    disposable(a)            declare a fenced interior — refused unless
                              the block is pure (the AX20 commit rule)

Composition is **port fusion**: b's entry place is renamed to a's exit
place — no glue transitions, no new state. The a-side name survives,
so a block's *output* places are never renamed; only entries are
absorbed. This is safe because of the one authoring rule the probe
proved on the frozen runtime: handlers address their outputs through
the ``outputs`` arcs **by color**, never by absolute place name — the
runtime hands every handler its output arcs, in declared order, each
carrying the target place's color.

Soundness is checked, not assumed: ``check_sound`` walks the block and
demands every node lie on an entry→exit path (the workflow-net
property AX20 tested dynamically, here decided statically). Blocks
built only from these leaves and combinators pass by construction —
the Böhm–Jacopini bargain: give up arbitrary arcs, get analyzability.

Purity is a *declaration* the composition layer propagates and
enforces (`pure ∘ pure = pure`; `disposable` refuses effects). It is
not verified against the handler body — effect typing is beyond a
spike; the layer trusts leaves and polices composition.

Everything stays at the kernel layer: nominal colors, plain-dict
tokens, no Python model types.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
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
    """A function-like subnet value: one entry, named typed exits."""

    name: str
    nodes: tuple[KernelNode, ...]
    entry: Port
    exits: Mapping[str, Port]
    pure: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "exits", MappingProxyType(dict(self.exits)))


# -- the one output-addressing rule ------------------------------------------------


def _target(outputs, color: str):
    """Address an output arc by color — never by place name. The frozen
    runtime hands handlers their output arcs carrying place colors, so
    handlers survive the renames composition performs."""
    matches = [arc for arc in outputs if arc.color == color]
    if len(matches) != 1:
        raise CompositionError(f"expected exactly one {color!r} output, got {len(matches)}")
    return matches[0].target


# -- leaves ------------------------------------------------------------------------


def transform(name: str, fn: Callable[[dict], dict], *, accepts: str, returns: str) -> Block:
    """A pure linear step: one in, one out, no world."""

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
    fn: Callable[[dict], tuple[str, dict]],
    *,
    accepts: str,
    outcomes: Mapping[str, str],
    pure: bool = False,
) -> Block:
    """A typed-outcome step (the AX21 shape): ``fn`` returns
    ``(exit_name, data)`` and the token routes to that exit's place.
    Defaults to impure — classification at a boundary usually touched
    the world; pass ``pure=True`` for value-only branching (AX5)."""

    if len(set(outcomes.values())) != len(outcomes):
        raise CompositionError(f"block {name!r}: outcome colors must be distinct — color is how handlers address exits")

    def handler(binding, outputs):
        [token] = binding.tokens
        exit_name, data = fn(dict(token.data))
        if exit_name not in outcomes:
            raise CompositionError(f"block {name!r} classified {exit_name!r}, not one of {sorted(outcomes)}")
        color = outcomes[exit_name]
        return {_target(outputs, color): (Token(color, data),)}

    entry = f"{name}_in"
    nodes = (
        KernelPlace(entry, accepts),
        *(KernelPlace(f"{name}_{exit_name}", color) for exit_name, color in outcomes.items()),
        BoundaryTransition(
            name=name,
            arcs=(consume(entry), *(produce(f"{name}_{exit_name}") for exit_name in outcomes)),
            work=PetriWork(handler),
        ),
    )
    exits = {exit_name: Port(f"{name}_{exit_name}", color) for exit_name, color in outcomes.items()}
    return Block(name, nodes, Port(entry, accepts), exits, pure=pure)


# -- combinators -------------------------------------------------------------------


def _rename(nodes: tuple[KernelNode, ...], mapping: Mapping[str, str]) -> tuple[KernelNode, ...]:
    renamed: list[KernelNode] = []
    for node in nodes:
        match node:
            case KernelPlace() if node.name in mapping:
                continue  # the fused entry place: a's exit place already exists
            case KernelPlace():
                renamed.append(node)
            case BoundaryTransition():
                arcs = tuple(replace(arc, place=mapping.get(arc.place, arc.place)) for arc in node.arcs)
                renamed.append(replace(node, arcs=arcs))
    return tuple(renamed)


def then(a: Block, b: Block, *, on: str) -> Block:
    """Route a's named exit into b's entry — the only sequencing form.
    The exit and entry places fuse (a's name survives); a's remaining
    exits and all of b's exits become the composite's exits."""

    if on not in a.exits:
        raise CompositionError(f"block {a.name!r} has no exit {on!r}; its exits are {sorted(a.exits)}")
    exit_port = a.exits[on]
    if exit_port.color != b.entry.color:
        raise CompositionError(
            f"cannot fuse {a.name!r} exit {on!r} ({exit_port.color}) "
            f"into {b.name!r} entry ({b.entry.color}): colors differ"
        )
    a_names = {node.name for node in a.nodes}
    b_names = {node.name for node in b.nodes} - {b.entry.place}
    if collisions := sorted(a_names & b_names):
        raise CompositionError(
            f"blocks {a.name!r} and {b.name!r} share node names {collisions}: leaf names must be unique"
        )
    if duplicate_exits := sorted((set(a.exits) - {on}) & set(b.exits)):
        raise CompositionError(
            f"composing {a.name!r} and {b.name!r} duplicates exit names {duplicate_exits}: rename_exit one side first"
        )
    exits = {name: port for name, port in a.exits.items() if name != on} | dict(b.exits)
    return Block(
        name=f"({a.name} >> {b.name})",
        nodes=a.nodes + _rename(b.nodes, {b.entry.place: exit_port.place}),
        entry=a.entry,
        exits=exits,
        pure=a.pure and b.pure,
    )


def rename_exit(block: Block, old: str, new: str) -> Block:
    """Explicit exit names — types are never sufficient identity."""
    if old not in block.exits:
        raise CompositionError(f"block {block.name!r} has no exit {old!r}; its exits are {sorted(block.exits)}")
    if new in block.exits:
        raise CompositionError(f"block {block.name!r} already has an exit {new!r}")
    exits = {new if name == old else name: port for name, port in block.exits.items()}
    return replace(block, exits=exits)


def disposable(block: Block) -> Block:
    """Declare a fenced interior. The AX20 commit rule, policed at
    composition time: a run that may be discarded wholesale must not
    have touched the world on the way."""
    if not block.pure:
        raise CompositionError(
            f"block {block.name!r} is not pure: a disposable interior may not contain effects — "
            f"the commit boundary is the only effect-emitting point (AX20)"
        )
    return block


# -- soundness, decided statically ----------------------------------------------------


def check_sound(block: Block) -> Block:
    """The workflow-net property (van der Aalst): every node lies on an
    entry→exit path. AX20 tested it dynamically (no leaked marking);
    blocks decide it statically. Inhibitor arcs are out of this spike's
    block scope — they gate on absence, which has no path meaning here."""

    places = {node.name for node in block.nodes if isinstance(node, KernelPlace)}
    transitions = [node for node in block.nodes if isinstance(node, BoundaryTransition)]
    if block.entry.place not in places:
        raise CompositionError(f"block {block.name!r}: entry place {block.entry.place!r} is not among its places")
    for name, port in block.exits.items():
        if port.place not in places:
            raise CompositionError(f"block {block.name!r}: exit {name!r} place {port.place!r} is not among its places")

    forward: dict[str, set[str]] = {}
    backward: dict[str, set[str]] = {}
    for node in transitions:
        for arc in node.arcs:
            if arc.mode is Mode.INHIBIT:
                raise CompositionError(
                    f"block {block.name!r}: inhibitor arcs are outside the block algebra (transition {node.name!r})"
                )
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

    nodes = places | {node.name for node in transitions}
    from_entry = reach({block.entry.place}, forward)
    to_exit = reach({port.place for port in block.exits.values()}, backward)
    if stranded := sorted(nodes - (from_entry & to_exit)):
        raise CompositionError(f"block {block.name!r} is not sound: nodes {stranded} lie on no entry→exit path")
    return block


# -- lowering ---------------------------------------------------------------------------


def compile_block(net_name: str, block: Block) -> LoweredBoundary:
    """Places first, then transitions — the kernel's declaration order —
    and from there the AX19 lowering owns everything."""
    check_sound(block)
    places = tuple(node for node in block.nodes if isinstance(node, KernelPlace))
    transitions = tuple(node for node in block.nodes if isinstance(node, BoundaryTransition))
    return lower_boundary(boundary_net(net_name, *places, *transitions))
