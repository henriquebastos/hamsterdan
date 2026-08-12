"""AX24 — parallel in the block algebra: split, total branches, join policies.

The Composable Functions comparison exposed the completed algebra's one
structural gap: no AND-parallelism. It also carried the insight that
makes the gap hard *and* the insight that dissolves it:

    In a Petri net an AND-join waits for one token per branch; a branch
    that can fail into a side place leaves the join dangling forever.
    Their design never dangles because every composable is TOTAL — it
    always returns exactly one Result — so the join always has
    something to consume. Totalized branches make the AND-join sound.

Two combinators, two policies, both explicit (the join policy is
visible net structure, never an engine accident):

- ``par`` — the 'all' policy (their ``all``/``collect``): split copies
  the input token to every branch, every branch runs to completion,
  the join consumes exactly one token per branch and aggregates a
  named dict. **Precondition: every branch is total** (exactly one
  exit). A branch with meaningful variant exits totalizes first —
  route each variant into one common result color, merge — and a
  downstream ``classify`` splits the aggregate again. Effectful
  branches are fine: everything completes, nothing is abandoned.
- ``par_fail_fast`` — the policy their library *refused to ship*
  (``first`` was removed because losing branches' effects still
  happen). Here it exists exactly where it is admissible: **pure,
  context-free branches only** — abandonment is the AX20 discard, and
  only disposable-eligible work may be discarded. Branches expose
  ``ok``/``failed`` exits; an ``armed`` token (the AX20 once-only
  claim) guarantees exactly one outcome; late tokens from abandoned
  branches drain into a declared ``abandoned`` exit — debris is
  visible, never vanished. The construction is LINEAR in the branch
  count (one abort + two drains per branch), not the exponential
  complement blowup a naive multi-exit join would need.

One authoring-rule extension, stated honestly: fan-out and fan-in
handlers here address their arcs **positionally** (the declared arc
order, which every algebra rename preserves), not by color — a split
produces the same data into N same-colored places, which color
addressing cannot express. Color addressing remains the rule for
routing leaves (``classify``); position is the rule for structural
fan-out/fan-in. Both survive composition renames.
"""

from __future__ import annotations

from collections.abc import Mapping

from ax19_kernel import BoundaryTransition, KernelPlace, PetriWork, consume, produce
from ax23_blocks import Block, CompositionError, Port
from petrus.impetus.petrinet import Token

type KernelNode = KernelPlace | BoundaryTransition

#: Marker colors for the fail-fast machinery. Safe even if a branch
#: reuses them: every transition touching these places has a handler
#: that addresses arcs positionally, so no color routing can confuse.
ARMED = "Armed"
EXPECT = "Expect"


def _merged_contexts(branches: Mapping[str, Block]) -> dict[str, Port]:
    """Contexts union across branches by explicit shared name (the
    AX14 rule); a shared name must agree on color. Concurrent read
    arcs on one shared place do not conflict (contextual nets)."""
    contexts: dict[str, Port] = {}
    owners: dict[str, str] = {}
    for branch_name, block in branches.items():
        for context, port in block.contexts.items():
            if context in contexts and contexts[context].color != port.color:
                raise CompositionError(
                    f"context {context!r} is {contexts[context].color} in branch {owners[context]!r} "
                    f"but {port.color} in branch {branch_name!r}"
                )
            contexts.setdefault(context, port)
            owners.setdefault(context, branch_name)
    return contexts


def _collected_nodes(branches: Mapping[str, Block], contexts: Mapping[str, Port]) -> tuple[KernelNode, ...]:
    """Concatenate branch nodes; a shared context place appears once;
    any other name collision is refused with both branches named."""
    nodes: list[KernelNode] = []
    owners: dict[str, str] = {}
    for branch_name, block in branches.items():
        for node in block.nodes:
            if isinstance(node, KernelPlace) and node.name in contexts:
                if node.name not in owners:
                    owners[node.name] = branch_name
                    nodes.append(node)
                continue
            if node.name in owners:
                raise CompositionError(
                    f"parallel branches {owners[node.name]!r} and {branch_name!r} share node name "
                    f"{node.name!r}: leaf names must be unique"
                )
            owners[node.name] = branch_name
            nodes.append(node)
    return tuple(nodes)


def _common_entry_color(branches: Mapping[str, Block]) -> str:
    entry_colors = {block.entry.color for block in branches.values()}
    if len(entry_colors) != 1:
        raise CompositionError(
            f"parallel branches must accept one common color, got {sorted(entry_colors)}: "
            f"the split copies one token to every branch — recolor inside the branch if needed"
        )
    [accepts] = entry_colors
    return accepts


def _claim_names(taken: set[str], *names: str) -> None:
    for name in names:
        if name in taken:
            raise CompositionError(f"parallel combinator needs place name {name!r}, already used by a branch")


# -- the 'all' policy ------------------------------------------------------------------


def par(name: str, branches: Mapping[str, Block], *, returns: str) -> Block:
    """AND-split, independent branch flow, AND-join with named-dict
    aggregation — the 'all' policy: every branch completes, the join
    waits for all of them, and the aggregate token carries
    ``{branch_name: branch_data}``. Every branch must be TOTAL."""

    if len(branches) < 2:
        raise CompositionError(f"par needs at least two branches, got {sorted(branches)}")
    accepts = _common_entry_color(branches)
    for branch_name, block in branches.items():
        if len(block.exits) != 1:
            raise CompositionError(
                f"branch {branch_name!r} ({block.name!r}) has exits {sorted(block.exits)}: a parallel "
                f"branch must be total — exactly one exit, so the join never waits on a token that "
                f"cannot come. Route every variant into one result color and merge before joining."
            )
    contexts = _merged_contexts(branches)
    branch_nodes = _collected_nodes(branches, contexts)
    taken = {node.name for node in branch_nodes}
    entry, out = f"{name}_in", f"{name}_out"
    _claim_names(taken, entry, out, name, f"{name}_join")

    def split_handler(binding, outputs):
        [token] = binding.tokens
        return {arc.target: (Token(arc.color, dict(token.data)),) for arc in outputs}

    order = list(branches)

    def join_handler(binding, outputs):
        aggregate = {}
        for branch_name, (_, selected) in zip(order, binding.consumed, strict=True):
            [token] = selected
            aggregate[branch_name] = dict(token.data)
        [target] = outputs
        return {target.target: (Token(target.color, aggregate),)}

    split = BoundaryTransition(
        name=name,
        arcs=(consume(entry), *(produce(block.entry.place) for block in branches.values())),
        work=PetriWork(split_handler),
        label=f"AND-split: copy the input to {len(branches)} branches",
    )
    exit_places = [next(iter(block.exits.values())).place for block in branches.values()]
    join = BoundaryTransition(
        name=f"{name}_join",
        arcs=(*(consume(place) for place in exit_places), produce(out)),
        work=PetriWork(join_handler),
        label="AND-join: one token per branch, aggregated by branch name",
    )
    return Block(
        name=f"par[{name}]({', '.join(order)})",
        nodes=(KernelPlace(entry, accepts), KernelPlace(out, returns), *branch_nodes, split, join),
        entry=Port(entry, accepts),
        exits={"out": Port(out, returns)},
        pure=all(block.pure for block in branches.values()),
        contexts=contexts,
    )


# -- the fail-fast policy --------------------------------------------------------------


def par_fail_fast(
    name: str,
    branches: Mapping[str, Block],
    *,
    returns: str,
    failure: str,
    abandoned: str = "Abandoned",
) -> Block:
    """AND-split with eager failure: the first branch to fail wins the
    ``failed`` exit; the others' late tokens drain into ``abandoned``.

    Admissible only over pure, context-free branches — abandoning a
    branch discards its run wholesale, and only disposable-eligible
    work may be discarded (the AX20 rule; also the reason
    composable-functions removed ``first``: losing branches' effects
    still happen). Every branch exposes exactly ``ok`` and ``failed``
    exits; all ``failed`` exits share the ``failure`` color so one
    failure place can receive whichever branch loses.

    The once-only is structural: one ``armed`` token, consumed by the
    all-ok join or by exactly one abort — the AX20 claim discipline.
    """

    if len(branches) < 2:
        raise CompositionError(f"par_fail_fast needs at least two branches, got {sorted(branches)}")
    accepts = _common_entry_color(branches)
    for branch_name, block in branches.items():
        if not block.pure or block.contexts:
            raise CompositionError(
                f"branch {branch_name!r} ({block.name!r}) is not disposable-eligible "
                f"(pure={block.pure}, contexts={sorted(block.contexts)}): fail-fast abandons losing "
                f"branches wholesale, and only pure, context-free work may be discarded — the reason "
                f"composable-functions removed `first`. Use par (the 'all' policy) for effectful branches."
            )
        if set(block.exits) != {"ok", "failed"}:
            raise CompositionError(
                f"branch {branch_name!r} ({block.name!r}) has exits {sorted(block.exits)}: fail-fast "
                f"branches must expose exactly 'ok' and 'failed'"
            )
        failed_color = block.exits["failed"].color
        if failed_color != failure:
            raise CompositionError(
                f"branch {branch_name!r} 'failed' exit is {failed_color!r}, expected {failure!r}: "
                f"all failure exits converge on one place, so they must share one color"
            )

    branch_nodes = _collected_nodes(branches, {})
    taken = {node.name for node in branch_nodes}
    entry, armed, out = f"{name}_in", f"{name}_armed", f"{name}_out"
    failed_out, abandoned_out = f"{name}_failed", f"{name}_abandoned"
    expects = {branch_name: f"{name}_expect_{branch_name}" for branch_name in branches}
    _claim_names(taken, entry, armed, out, failed_out, abandoned_out, *expects.values())

    def split_handler(binding, outputs):
        [token] = binding.tokens
        marker, *entries = outputs  # positional: armed is declared first
        produced = {marker.target: (Token(marker.color, {}),)}
        for arc in entries:
            produced[arc.target] = (Token(arc.color, dict(token.data)),)
        return produced

    order = list(branches)

    def join_handler(binding, outputs):
        aggregate = {}
        for branch_name, (_, selected) in zip(order, binding.consumed[1:], strict=True):  # skip armed
            [token] = selected
            aggregate[branch_name] = dict(token.data)
        [target] = outputs
        return {target.target: (Token(target.color, aggregate),)}

    def abort_handler(binding, outputs):
        [_, (_, failed_tokens)] = list(binding.consumed)  # positional: armed, then the failure
        [token] = failed_tokens
        loser, *markers = outputs  # positional: failed exit first, then the expects
        produced = {loser.target: (Token(loser.color, dict(token.data)),)}
        for arc in markers:
            produced[arc.target] = (Token(arc.color, {}),)
        return produced

    def drain_handler(branch_name: str, verdict: str):
        def handler(binding, outputs):
            [_, (_, late)] = list(binding.consumed)  # positional: expect marker, then the late token
            [token] = late
            [target] = outputs
            return {
                target.target: (
                    Token(target.color, {"branch": branch_name, "verdict": verdict, "data": dict(token.data)}),
                )
            }

        return handler

    transitions: list[BoundaryTransition] = [
        BoundaryTransition(
            name=name,
            arcs=(consume(entry), produce(armed), *(produce(block.entry.place) for block in branches.values())),
            work=PetriWork(split_handler),
            label=f"AND-split: copy the input to {len(branches)} branches and arm the once-only",
        ),
        BoundaryTransition(
            name=f"{name}_join",
            arcs=(
                consume(armed),
                *(consume(block.exits["ok"].place) for block in branches.values()),
                produce(out),
            ),
            work=PetriWork(join_handler),
            label="all-ok join: consumes the armed token, so it races the aborts",
        ),
    ]
    for branch_name, block in branches.items():
        others = [other for other in order if other != branch_name]
        transitions.append(
            BoundaryTransition(
                name=f"{name}_abort_{branch_name}",
                arcs=(
                    consume(armed),
                    consume(block.exits["failed"].place),
                    produce(failed_out),
                    *(produce(expects[other]) for other in others),
                ),
                work=PetriWork(abort_handler),
                label=f"{branch_name!r} failed first: take the once-only, expect the others' late tokens",
            )
        )
        for verdict in ("ok", "failed"):
            transitions.append(
                BoundaryTransition(
                    name=f"{name}_drain_{branch_name}_{verdict}",
                    arcs=(
                        consume(expects[branch_name]),
                        consume(block.exits[verdict].place),
                        produce(abandoned_out),
                    ),
                    work=PetriWork(drain_handler(branch_name, verdict)),
                    label=f"abandoned {branch_name!r} finished late ({verdict}): visible debris, never vanished",
                )
            )

    ok_colors = {block.exits["ok"].color for block in branches.values()}
    del ok_colors  # ok colors may differ; the join aggregates into one dict token
    return Block(
        name=f"par_fail_fast[{name}]({', '.join(order)})",
        nodes=(
            KernelPlace(entry, accepts),
            KernelPlace(armed, ARMED),
            KernelPlace(out, returns),
            KernelPlace(failed_out, failure),
            KernelPlace(abandoned_out, abandoned),
            *(KernelPlace(expects[branch_name], EXPECT) for branch_name in branches),
            *branch_nodes,
            *transitions,
        ),
        entry=Port(entry, accepts),
        exits={
            "done": Port(out, returns),
            "failed": Port(failed_out, failure),
            "abandoned": Port(abandoned_out, abandoned),
        },
        pure=True,  # every branch was verified pure and context-free above
        contexts={},
    )
