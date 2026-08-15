"""The CI loop: pure observation of check-run evidence.

Owns the CiState baton. Adopts each admitted head with a budget
lineage, keeps only the newest exact-head run verdict, mails
ChecksFailure facts to the escalation loop, and answers escalation
MOVED echoes with the park-or-reissue rule: if the attempted authority
tuple is already stale against the admitted one, reissue now; if the
attempt used the currently-held tuple, park the fingerprint and let the
refresh reissue it. Each reissue carries a strictly fresher tuple, so
the loop terminates.
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    ChecksFailure,
    CiEnded,
    CiState,
    CloseFact,
    EscMoved,
    GateFact,
    HeadWork,
    RunWork,
)
from hamsterdan.readiness.net_v5.folding import route, values

# -- folds ---------------------------------------------------------------


def _checks_fact(incarnation: int, status: str) -> GateFact:
    return GateFact(kind="checks", incarnation=incarnation, body={"status": status})


def _failure_mail(state: CiState, fingerprint: str, run_id: int, attempt: int) -> ChecksFailure:
    """The escalation mail always carries ONE state's complete authority
    plus the run EVIDENCE identity, so the ladder can absorb duplicates."""
    return ChecksFailure(
        fingerprint=fingerprint,
        head=state.head,
        base=state.base,
        policy=state.policy,
        lineage=state.lineage,
        incarnation=state.incarnation,
        run_id=run_id,
        attempt=attempt,
    )


def _admit_head(binding, outputs):
    work, state = values(binding, HeadWork, CiState)
    if work.relation == "refreshed":
        # refresh: adopt the fresh authority for future escalation
        # requests WITHOUT churning observed CI evidence — and REISSUE
        # any escalation that MOVED under the stale authority
        # (failure-then-refresh must converge with refresh-then-failure).
        # A mergeable-only refresh changes no authority field: parked
        # attempts stay parked, or a reissue would repeat the SAME tuple.
        authority_changed = (work.base, work.policy) != (state.base, state.policy)
        adopted = state.validated_update(
            base=work.base,
            policy=work.policy,
            parked=[] if authority_changed else state.parked,
        )
        routes: dict = {"ci.state": (adopted,)}
        if authority_changed and state.status == "failure" and state.fingerprint in state.parked:
            routes["esc.failures"] = (_failure_mail(adopted, state.fingerprint, state.best[0], state.best[1]),)
        return route(outputs, routes)
    # budget lineage: new code (new/superseded) gets a fresh ladder
    # budget; our own confirmed repair and a resume keep the lineage
    fresh = work.relation in ("new", "superseded") or state.lineage == ""
    admitted = CiState(
        head=work.head,
        base=work.base,
        policy=work.policy,
        lineage=f"L{work.incarnation}" if fresh else state.lineage,
        incarnation=work.incarnation,
        best=(),
        status="pending",
        fingerprint="",
        parked=(),
    )
    fact = _checks_fact(work.incarnation, "pending")
    return route(
        outputs,
        {"ci.state": (admitted,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


# a run may be observed repeatedly under ONE (run_id, attempt) identity
# as it progresses toward its terminal conclusion: queued → in_progress
# → success|failure, strictly forward, never sideways or back
_RANK = {"queued": 0, "in_progress": 1, "success": 2, "failure": 2}


def _assess(binding, outputs):
    run, state = values(binding, RunWork, CiState)
    if run.head != state.head:
        return route(outputs, {"ci.state": (state,)})  # not the exact head: inert
    if state.best:
        identity = (run.run_id, run.attempt)
        if identity < tuple(state.best):
            return route(outputs, {"ci.state": (state,)})  # older evidence: inert
        # (run_id, attempt) is identity, not the whole freshness order:
        # the SAME identity legitimately advances to a strictly higher
        # rank. Anything else — an exact duplicate, or an out-of-order
        # observation arriving after a later status — is inert.
        if identity == tuple(state.best) and _RANK[run.conclusion] <= _RANK[state.status]:
            return route(outputs, {"ci.state": (state,)})
    updated = state.validated_update(
        best=[run.run_id, run.attempt],
        status=run.conclusion,
        fingerprint=run.fingerprint,
        parked=[],  # fresh evidence obsoletes any parked escalation
    )
    fact = _checks_fact(state.incarnation, run.conclusion)
    routes = {"ci.state": (updated,), "ready.facts": (fact,), "dash.facts": (fact,)}
    if run.conclusion == "failure":
        routes["esc.failures"] = (_failure_mail(state, run.fingerprint, run.run_id, run.attempt),)
    return route(outputs, routes)


def _recheck(binding, outputs):
    echo, state = values(binding, EscMoved, CiState)
    if state.status != "failure" or state.fingerprint != echo.fp:
        return route(outputs, {"ci.state": (state,)})  # failure gone: inert
    # the attempted tuple includes the GRANT: a stale-incarnation echo
    # (draft→resume moved an identical head/base/policy) must reissue
    # under the current incarnation, not park forever
    attempted = (echo.head, echo.base, echo.policy, echo.incarnation)
    if attempted == (state.head, state.base, state.policy, state.incarnation):
        parked = state.parked if echo.fp in state.parked else [*state.parked, echo.fp]
        return route(outputs, {"ci.state": (state.validated_update(parked=parked),)})
    reissued = _failure_mail(state, echo.fp, state.best[0], state.best[1])
    return route(outputs, {"ci.state": (state,), "esc.failures": (reissued,)})


def _end(binding, outputs):
    close, state = values(binding, CloseFact, CiState)
    return route(outputs, {"ci.done": (CiEnded(status=state.status, reason=close.reason),)})


def _drain_echo(binding, outputs):
    # an escalation echo that lost the race with close (a held rerun
    # settling MOVED under terminal authority) is absorbed by the
    # retired loop's persistent record — never stranded
    _, ended = values(binding, EscMoved, CiEnded)
    return route(outputs, {"ci.done": (ended,)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    ci = s.ci
    ci.p.heads(HeadWork)
    ci.p.runs(RunWork)
    ci.p.echo(EscMoved)
    ci.p.closed(CloseFact)
    ci.p.state(CiState)
    ci.p.done(CiEnded)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    s = net.s
    ci, esc, dash, ready = s.ci, s.esc, s.dash, s.ready

    (
        (ci.p.heads, ci.p.state)
        >> ci.t.admit_head(handler=petri_handler(_admit_head))
        >> (
            ci.p.state,
            ready.p.facts,
            esc.p.failures,
            dash.p.facts,
        )
    )
    (
        (ci.p.runs, ci.p.state)
        >> ci.t.assess(handler=petri_handler(_assess))
        >> (
            ci.p.state,
            ready.p.facts,
            esc.p.failures,
            dash.p.facts,
        )
    )
    (
        (ci.p.echo, ci.p.state)
        >> ci.t.recheck(handler=petri_handler(_recheck))
        >> (
            ci.p.state,
            esc.p.failures,
        )
    )
    (ci.p.closed, ci.p.state) >> ci.t.end(handler=petri_handler(_end)) >> ci.p.done
    # post-close drain: a late escalation echo is absorbed, never stranded
    ((ci.p.echo, ci.p.done) >> ci.t.drain_echo(handler=petri_handler(_drain_echo)) >> ci.p.done)


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = CiState(
        head="",
        base="",
        policy="",
        lineage="",
        incarnation=0,
        best=(),
        status="pending",
        fingerprint="",
        parked=(),
    )
    return {NetPath("ci.state"): (Token("CiState", baton.dump()),)}
