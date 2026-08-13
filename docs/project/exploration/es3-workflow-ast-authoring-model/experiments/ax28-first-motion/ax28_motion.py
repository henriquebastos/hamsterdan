"""AX28 — ``first_motion``: the smallest honest general harness.

One call takes any Block and one entry datum to a quiescent instance
on the frozen engine. The harness is general by construction — nothing
in this module knows any particular workflow — and it hides no durable
artifact: the returned ``Motion`` exposes the canonical serialized
definition, the History records, every place's tokens, and proves
replay on demand by reloading the same History over a fresh compile.

The store is a visible choice, not a hidden default: ``history=``
accepts any History Store; when omitted, motion runs on an in-memory
store and ``Motion.store_defaulted`` says so. Nothing here fakes
durability — which store a first-motion experience should default to
is a tabled Navigator decision this harness deliberately surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ax23_blocks import Block, KernelPlace, compile_block
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch


class MotionError(RuntimeError):
    """The instance did not quiesce within the advance budget."""


def _drive(engine: Engine, limit: int) -> None:
    for _ in range(limit):
        if not engine.advance().ready:
            return
    raise MotionError(
        f"instance did not quiesce within {limit} advances — "
        f"a data-driven loop may lack a terminating classification; "
        f"raise limit= only if the workflow legitimately needs more steps"
    )


@dataclass(frozen=True)
class Motion:
    """A quiescent instance plus every artifact an author may inspect."""

    block: Block
    net_name: str
    instance: str
    engine: Engine
    lowered: Any
    history: Any
    store_defaulted: bool

    @property
    def definition(self) -> str:
        """The canonical serialized net — the replay contract's subject."""
        return serialize_net_definition(project_net_definition(self.lowered.built.net))

    @property
    def records(self) -> tuple:
        """The History records behind this motion — the event log is real."""
        return tuple(self.engine.records)

    def place(self, name: str) -> list[dict]:
        """Token data at any place of the net, by its final name."""
        return [token.data for token in self.engine.marking.place(NetPath(name))]

    @property
    def settled(self) -> dict[str, list[dict]]:
        """Token data at every named exit of the authored block."""
        return {name: self.place(port.place) for name, port in self.block.exits.items()}

    def replay(self) -> Motion:
        """Recompile the same block, reload the same History, and prove
        the rebuilt marking matches this one place by place."""
        recompiled = compile_block(self.net_name, self.block)
        resumed = Engine.load(
            recompiled.built.net,
            self.instance,
            history=self.history,
            dispatch=InlineDispatch({}),
            handlers=dict(recompiled.handlers),
            guards=dict(recompiled.built.guards),
            activities=(),
        )
        replayed = Motion(
            self.block, self.net_name, self.instance, resumed, recompiled, self.history, self.store_defaulted
        )
        for node in self.block.nodes:
            if isinstance(node, KernelPlace) and replayed.place(node.name) != self.place(node.name):
                raise MotionError(f"replay diverged at place {node.name!r}")
        return replayed


def first_motion(
    block: Block,
    data: dict,
    *,
    net_name: str = "first-motion",
    instance: str = "motion-1",
    history: Any = None,
    limit: int = 200,
) -> Motion:
    """Compile, compose, seed one entry token, and drive to quiescence.

    Validation is not weakened: ``compile_block`` enforces
    ``check_sound`` before anything runs. The entry token's color comes
    from the block's own entry port, so a wrongly-colored injection is
    unrepresentable through this surface.
    """
    lowered = compile_block(net_name, block)
    store = history if history is not None else InMemoryHistoryStore()
    engine = Engine.create(
        lowered.built.net,
        instance,
        history=store,
        dispatch=InlineDispatch({}),
        marking=Marking({NetPath(block.entry.place): (Token(block.entry.color, dict(data)),)}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )
    _drive(engine, limit)
    return Motion(block, net_name, instance, engine, lowered, store, store_defaulted=history is None)
