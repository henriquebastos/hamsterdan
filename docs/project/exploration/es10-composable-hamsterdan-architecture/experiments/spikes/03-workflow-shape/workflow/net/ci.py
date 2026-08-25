"""Mini CI loop (spike): adopts heads, assesses runs, mails failures.

Provenance: drastically reduced from src/hamsterdan/readiness/net_v5/ci.py at
0686067 — no lineage budgets, park/reissue protocol, or close protocol.
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from workflow.facts import ChecksFailure, HeadWork, RunWork
from workflow.net.folding import route, values
from workflow.values import WorkflowModel

GATES: dict[str, str] = {}


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CiState(WorkflowModel):
    head: str
    base: str
    policy: str
    incarnation: int
    status: str


# -- folds ---------------------------------------------------------------


def _admit_head(binding, outputs):
    work, state = values(binding, HeadWork, CiState)
    admitted = state.validated_update(
        head=work.head, base=work.base, policy=work.policy, incarnation=work.incarnation, status="pending"
    )
    return route(outputs, {"ci.state": (admitted,)})


def _assess(binding, outputs):
    run, state = values(binding, RunWork, CiState)
    if run.head != state.head:
        return route(outputs, {"ci.state": (state,)})  # not the exact head: inert
    updated = state.validated_update(status=run.conclusion)
    routes = {"ci.state": (updated,)}
    if run.conclusion == "failure":
        routes["esc.failures"] = (
            ChecksFailure(
                fingerprint=run.fingerprint,
                head=state.head,
                base=state.base,
                policy=state.policy,
                incarnation=state.incarnation,
                run_id=run.run_id,
                attempt=run.attempt,
            ),
        )
    return route(outputs, routes)


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    ci = s.ci
    ci.p.heads(HeadWork)
    ci.p.runs(RunWork)
    ci.p.state(CiState)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    ci, esc = net.s.ci, net.s.esc
    ((ci.p.heads, ci.p.state) >> ci.t.admit_head(handler=petri_handler(_admit_head)) >> ci.p.state)
    ((ci.p.runs, ci.p.state) >> ci.t.assess(handler=petri_handler(_assess)) >> (ci.p.state, esc.p.failures))


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = CiState(head="", base="", policy="", incarnation=0, status="pending")
    return {NetPath("ci.state"): (Token("CiState", baton.dump()),)}


TOKENS: tuple[type, ...] = (CiState,)
