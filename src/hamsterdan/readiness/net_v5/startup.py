"""Release effect execution after the initial summary lands.

Intake and pure folds can accumulate observations and route recovery while
startup waits. The pending token is consumed once; later dashboard updates
cannot suspend the workflow. Existing Histories have no pending token and
retain their already-started workflow.
"""

from petrus.impetus.dsl import arc, petri_handler
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import SummaryPending, SummaryPublished


def _settled(binding, outputs):
    return {}


def declare(s) -> None:
    s.startup.p.pending(SummaryPending)
    s.startup.p.published(SummaryPublished)


def wire(net, gates) -> None:
    startup = net.s.startup
    (startup.p.pending, startup.p.published) >> startup.t.finish(handler=petri_handler(_settled))
    startup.p.published >> startup.t.absorb_update(handler=petri_handler(_settled))
    startup.p.pending >> arc.inhibit() >> startup.t.absorb_update
    for path, (activity, _) in gates.items():
        if activity == "dash_gate":
            continue
        owner, name = path.split(".")
        transition = getattr(getattr(net.s, owner).t, name)
        startup.p.pending >> arc.inhibit() >> transition


def seed() -> dict:
    return {NetPath("startup.pending"): (Token("SummaryPending", SummaryPending().dump()),)}
