"""Mini escalation loop (spike): one rerun gate with typed terminals.

Provenance: drastically reduced from src/hamsterdan/readiness/net_v5/esc.py
at 0686067 — one rung, no ladder budget, repair escalation, or close
protocol.
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from workflow.activities import RerunFault, RerunLanded, RerunMoved, RerunReq
from workflow.facts import ChecksFailure
from workflow.net.folding import route, values
from workflow.values import WorkflowModel

GATES: dict[str, str] = {"esc.rerun_gate": "rerun_gate"}


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class Ladder(WorkflowModel):
    fingerprint: str
    rungs: int
    settled: str


# -- folds ---------------------------------------------------------------


def _escalate(binding, outputs):
    failure, ladder = values(binding, ChecksFailure, Ladder)
    request = RerunReq(
        fingerprint=failure.fingerprint,
        op=f"rerun:{failure.fingerprint}:{failure.run_id}:{failure.attempt}",
        head=failure.head,
        run_id=failure.run_id,
        attempt=failure.attempt,
        incarnation=failure.incarnation,
    )
    advanced = ladder.validated_update(fingerprint=failure.fingerprint, rungs=ladder.rungs + 1)
    return route(outputs, {"esc.ladder": (advanced,), "esc.rerun_req": (request,)})


def _fold_landed(binding, outputs):
    _, ladder = values(binding, RerunLanded, Ladder)
    return route(outputs, {"esc.ladder": (ladder.validated_update(settled="landed"),)})


def _fold_moved(binding, outputs):
    _, ladder = values(binding, RerunMoved, Ladder)
    return route(outputs, {"esc.ladder": (ladder.validated_update(settled="moved"),)})


def _fold_fault(binding, outputs):
    _, ladder = values(binding, RerunFault, Ladder)
    return route(outputs, {"esc.ladder": (ladder.validated_update(settled="faulted"),)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    esc = s.esc
    esc.p.failures(ChecksFailure)
    esc.p.ladder(Ladder)
    esc.p.rerun_req(RerunReq)
    esc.p.landed(RerunLanded)
    esc.p.moved(RerunMoved)
    esc.p.fault(RerunFault)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    esc = net.s.esc
    (
        (esc.p.failures, esc.p.ladder)
        >> esc.t.escalate(handler=petri_handler(_escalate))
        >> (esc.p.ladder, esc.p.rerun_req)
    )
    # the gate: a named handler declaration, bound by the host through the manifest
    (esc.p.rerun_req >> esc.t.rerun_gate(handler="rerun_gate") >> (esc.p.landed, esc.p.moved, esc.p.fault))
    ((esc.p.landed, esc.p.ladder) >> esc.t.fold_landed(handler=petri_handler(_fold_landed)) >> esc.p.ladder)
    ((esc.p.moved, esc.p.ladder) >> esc.t.fold_moved(handler=petri_handler(_fold_moved)) >> esc.p.ladder)
    ((esc.p.fault, esc.p.ladder) >> esc.t.fold_fault(handler=petri_handler(_fold_fault)) >> esc.p.ladder)


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = Ladder(fingerprint="", rungs=0, settled="")
    return {NetPath("esc.ladder"): (Token("Ladder", baton.dump()),)}


TOKENS: tuple[type, ...] = (Ladder,)
