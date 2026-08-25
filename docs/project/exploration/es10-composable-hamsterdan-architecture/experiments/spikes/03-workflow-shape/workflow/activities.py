"""The work the workflow requests and the only terminals that may answer it
(spike, one family), plus the gate manifest.

The manifest is the experiment-3 design move: today the operation-identity
derivation and blocked synthesis live as `isinstance` chains inside handler
subclasses in `net_v5/gating.py`. Here each gate family declares them next to
its values, so the workflow states — declaratively — what work exists, which
typed terminals may answer, on which execution lane, under which stable
operation identity, and what a durable-lane exhaustion synthesizes.

Provenance: rerun family reduced from src/hamsterdan/contracts/readiness_v5.py
at 0686067; identity policy transcribed from net_v5/gating.py.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any, Literal

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from workflow.values import WorkflowModel

# -- rerun family ----------------------------------------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RerunReq(WorkflowModel):
    """Escalation work: rerun the failed run on the exact head."""

    fingerprint: str
    op: str
    head: str
    run_id: int
    attempt: int
    incarnation: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RerunLanded(WorkflowModel):
    fingerprint: str
    op: str
    run_id: int
    attempt: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RerunMoved(WorkflowModel):
    fingerprint: str
    op: str
    head: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RerunFault(WorkflowModel):
    fingerprint: str
    op: str
    reason: str


# -- gate manifest -----------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class GateDeclaration:
    """One gate the workflow requests through the world.

    `operation` derives the stable operation identity every attempt of one
    occurrence must share (the lookup-first key). `blocked` synthesizes the
    typed exhaustion terminal on the durable-publication lane; identified
    inline gates carry None.
    """

    activity: str
    request: type
    results: tuple[type, ...]
    lane: Literal["identified_inline", "durable_publication"]
    operation: Callable[[Any], str]
    blocked: Callable[[Any], WorkflowModel] | None = None

    @property
    def variants(self) -> tuple[str, ...]:
        return tuple(result.__name__ for result in self.results)


MANIFEST: dict[str, GateDeclaration] = {
    "rerun_gate": GateDeclaration(
        activity="rerun_gate",
        request=RerunReq,
        results=(RerunLanded, RerunMoved, RerunFault),
        lane="identified_inline",
        operation=lambda request: request.op,
    ),
}

TOKENS: tuple[type, ...] = (RerunReq, RerunLanded, RerunMoved, RerunFault)
