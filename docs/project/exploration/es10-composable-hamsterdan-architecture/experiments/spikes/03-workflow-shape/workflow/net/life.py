"""Mini lifecycle loop (spike): admits observations, mails work to CI.

Provenance: drastically reduced from src/hamsterdan/readiness/net_v5/life.py
at 0686067 — admission-only, no draft/close/comment protocol.
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from workflow.facts import HeadWork, RunWork
from workflow.net.folding import route, values
from workflow.observations import HeadSeen, RunSeen
from workflow.values import WorkflowModel

GATES: dict[str, str] = {}


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class LifeState(WorkflowModel):
    head: str
    base: str
    policy: str
    incarnation: int


# -- folds ---------------------------------------------------------------


def _admit(binding, outputs):
    seen, state = values(binding, HeadSeen, LifeState)
    admitted = state.validated_update(
        head=seen.head, base=seen.base, policy=seen.policy, incarnation=seen.incarnation
    )
    work = HeadWork(head=seen.head, base=seen.base, policy=seen.policy, incarnation=seen.incarnation)
    return route(outputs, {"life.state": (admitted,), "ci.heads": (work,)})


def _observe_run(binding, outputs):
    run, state = values(binding, RunSeen, LifeState)
    work = RunWork(
        head=run.head, run_id=run.run_id, attempt=run.attempt, conclusion=run.conclusion, fingerprint=run.fingerprint
    )
    return route(outputs, {"life.state": (state,), "ci.runs": (work,)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    life = s.life
    life.p.heads_seen(HeadSeen)
    life.p.runs_seen(RunSeen)
    life.p.state(LifeState)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    life, ci = net.s.life, net.s.ci
    net.t.on_head >> life.p.heads_seen
    net.t.on_runs >> life.p.runs_seen
    ((life.p.heads_seen, life.p.state) >> life.t.admit(handler=petri_handler(_admit)) >> (life.p.state, ci.p.heads))
    (
        (life.p.runs_seen, life.p.state)
        >> life.t.observe_run(handler=petri_handler(_observe_run))
        >> (life.p.state, ci.p.runs)
    )


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = LifeState(head="", base="", policy="", incarnation=0)
    return {NetPath("life.state"): (Token("LifeState", baton.dump()),)}


TOKENS: tuple[type, ...] = (LifeState,)
