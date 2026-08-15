"""The V5 review actor loop: one durable review memory per PR.

Owns the ReviewMemory baton. Each admitted head opens ONE agent round
(the agent gate sees only its work token — no GitHub credential enters
agent territory); the judge filters dismissed findings; the publish
gate posts under one stable effect identity `findings:{head}:i{inc}`
with A1.5 authority fencing and A2 lookup-first reconciliation. A moved
publication retains its findings provisionally — the next refreshed
authority republishes them under the SAME identity without a new agent
round. The baton is HELD through every in-flight round, so no second
decision can race it.
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    AgentReview,
    CloseFact,
    DismissFact,
    EmptyReview,
    GateFact,
    HeadWork,
    Publishable,
    RecoverFact,
    ReviewBlocked,
    ReviewEnded,
    ReviewFault,
    ReviewLanded,
    ReviewMemory,
    ReviewMoved,
    RoundOpen,
)
from hamsterdan.readiness.net_v5.folding import revive, route, values

GATES = {
    "review.publish": (
        "publish_gate",
        ("ReviewLanded", "ReviewMoved", "ReviewBlocked", "ReviewFault"),
    )
}
DERIVED = {"review.agent": "review_agent"}

# -- folds ---------------------------------------------------------------


def _live(findings, dismissed) -> list[dict]:
    return [f for f in findings if f["id"] not in dismissed]


def _publishable(head: str, base: str, policy: str, incarnation: int, findings, mem: ReviewMemory) -> Publishable:
    """One publication request with a durable Pending record in its mem (A2).

    The publication takes EXCLUSIVE custody of the findings: `provisional`
    is cleared so no refresh can republish a diverging subset while a
    blocked/faulted descriptor retains the exact attempted content. A
    MOVED terminal restores the complete attempted list to provisional.
    """
    op = f"findings:{head}:i{incarnation}"
    pending = {
        "phase": "pending",
        "effect": op,
        "op": op,
        "head": head,
        "base": base,
        "policy": policy,
        "incarnation": incarnation,
        "findings": list(findings),
    }
    return Publishable(
        head=head,
        base=base,
        policy=policy,
        incarnation=incarnation,
        findings=list(findings),
        effect=op,
        op=op,
        mem=mem.validated_update(provisional=[], pub=pending).dump(),
    )


def _start(binding, outputs):
    work, mem = values(binding, HeadWork, ReviewMemory)
    if work.relation == "refreshed":
        # no new agent round — but provisional findings retained by an
        # earlier MOVED publication republish under the fresh authority
        # with the SAME effect identity (incarnation did not bump)
        live = _live(mem.provisional, mem.dismissed)
        if not live:
            return route(outputs, {"review.memory": (mem,)})
        return route(
            outputs,
            {"review.publishable": (_publishable(work.head, work.base, work.policy, work.incarnation, live, mem),)},
        )
    opened = RoundOpen(
        head=work.head,
        base=work.base,
        policy=work.policy,
        incarnation=work.incarnation,
        mem=mem.dump(),  # the baton is HELD through the round
    )
    return route(outputs, {"review.round": (opened,)})


def _judge(binding, outputs):
    (out,) = values(binding, AgentReview)
    mem = revive(ReviewMemory, out.mem)
    # the round is COMPLETE here: `reviewed` records agent rounds, not
    # publication settlements (a resumed round on the same head does not
    # duplicate the entry)
    if out.head not in mem.reviewed:
        mem = mem.validated_update(reviewed=[*mem.reviewed, out.head])
    live = _live(out.findings, mem.dismissed)
    if not live:
        empty = EmptyReview(head=out.head, incarnation=out.incarnation, mem=mem.dump())
        return route(outputs, {"review.empty": (empty,)})
    return route(
        outputs,
        {"review.publishable": (_publishable(out.head, out.base, out.policy, out.incarnation, live, mem),)},
    )


def _findings_fact(head: str, incarnation: int, findings, dismissed) -> GateFact:
    blocking = sum(1 for f in findings if f["blocking"] and f["id"] not in dismissed)
    return GateFact(
        kind="findings",
        incarnation=incarnation,
        body={"head": head, "blocking": blocking, "count": len(findings)},
    )


def _resolution(pub: dict) -> GateFact | None:
    """An operation-keyed resolution for a recovered faulted publication:
    the settle clears the fault so readiness never stays fail-closed
    after the human's recovery actually succeeded."""
    if pub.get("was") != "faulted":
        return None
    return GateFact(kind="fault", incarnation=0, body={"where": "review", "op": pub["op"], "status": "resolved"})


def _fold_landed(binding, outputs):
    (out,) = values(binding, ReviewLanded)
    prior = revive(ReviewMemory, out.mem)
    mem = prior.validated_update(
        provisional=[],
        findings=list(out.findings),
        pub={"phase": "idle"},
    )
    facts = (_findings_fact(out.head, out.incarnation, out.findings, mem.dismissed),)
    resolved = _resolution(prior.pub)
    if resolved is not None:
        facts = (*facts, resolved)
    return route(outputs, {"review.memory": (mem,), "ready.facts": facts, "dash.facts": facts})


def _fold_moved(binding, outputs):
    (out,) = values(binding, ReviewMoved)
    # authority moved under the post: keep the COMPLETE attempted list
    # PROVISIONALLY — the refreshed admission republishes it, a
    # superseding head's fresh agent round carries it forward
    prior = revive(ReviewMemory, out.mem)
    mem = prior.validated_update(provisional=list(out.findings), pub={"phase": "idle"})
    routes: dict = {"review.memory": (mem,)}
    resolved = _resolution(prior.pub)
    if resolved is not None:
        routes["ready.facts"] = (resolved,)
        routes["dash.facts"] = (resolved,)
    return route(outputs, routes)


def _fold_blocked(binding, outputs):
    (out,) = values(binding, ReviewBlocked)
    prior = revive(ReviewMemory, out.mem)
    mem = prior.validated_update(
        findings=list(out.findings),
        pub={
            "phase": "blocked",
            "effect": out.effect,
            "op": out.op,
            "head": out.head,
            "base": out.base,
            "policy": out.policy,
            "incarnation": out.incarnation,
            "findings": list(out.findings),
        },
    )
    facts = (_findings_fact(out.head, out.incarnation, out.findings, mem.dismissed),)
    resolved = _resolution(prior.pub)
    if resolved is not None:
        facts = (*facts, resolved)
    return route(outputs, {"review.memory": (mem,), "ready.facts": facts, "dash.facts": facts})


def _fold_fault(binding, outputs):
    (out,) = values(binding, ReviewFault)
    prior = revive(ReviewMemory, out.mem)
    # A2: Faulted retains the operation (the pending descriptor set at
    # publish time) plus the reason, so the human can rule
    mem = prior.validated_update(pub={**prior.pub, "phase": "faulted", "reason": out.reason})
    fact = GateFact(
        kind="fault",
        incarnation=0,
        body={"where": "review", "op": prior.pub.get("op", ""), "status": "faulted", "reason": out.reason},
    )
    return route(outputs, {"review.memory": (mem,), "ready.facts": (fact,), "dash.facts": (fact,)})


def _fold_empty(binding, outputs):
    (out,) = values(binding, EmptyReview)
    prior = revive(ReviewMemory, out.mem)
    mem = prior.validated_update(
        provisional=[],
        findings=[],
        pub={"phase": "idle"},
    )
    fact = _findings_fact(out.head, out.incarnation, (), mem.dismissed)
    return route(outputs, {"review.memory": (mem,), "ready.facts": (fact,), "dash.facts": (fact,)})


def _recover(binding, outputs):
    fact, mem = values(binding, RecoverFact, ReviewMemory)
    pub = mem.pub
    if fact.target != "review" or pub.get("phase") not in ("blocked", "faulted") or fact.op != pub.get("op"):
        return route(outputs, {"review.memory": (mem,)})
    # ONE fresh occurrence reusing the SAME effect identity; the baton
    # is HELD through the reopened publication round (A2). The gate's
    # lookup-first read reconciles a crash after the provider accepted.
    # `was` remembers a faulted origin so the settle can emit the
    # operation-keyed resolution.
    pending = {key: value for key, value in pub.items() if key != "reason"}
    reopened = Publishable(
        head=pub["head"],
        base=pub["base"],
        policy=pub["policy"],
        incarnation=pub["incarnation"],
        findings=list(pub["findings"]),
        effect=pub["effect"],
        op=pub["op"],
        mem=mem.validated_update(pub={**pending, "phase": "pending", "was": pub["phase"]}).dump(),
    )
    return route(outputs, {"review.publishable": (reopened,)})


def _dismiss(binding, outputs):
    fact, mem = values(binding, DismissFact, ReviewMemory)
    pub = mem.pub
    facts: tuple[GateFact, ...] = ()
    if pub.get("phase") in ("blocked", "faulted") and any(f["id"] == fact.finding_id for f in pub.get("findings", ())):
        # the human waved off a finding the retained operation carries:
        # CANCEL the operation (recovery goes inert) rather than rewrite
        # its content under the same effect identity — the descriptor
        # stays for audit
        if pub["phase"] == "faulted":
            facts = (
                GateFact(kind="fault", incarnation=0, body={"where": "review", "op": pub["op"], "status": "cancelled"}),
            )
        pub = {**pub, "phase": "cancelled"}
    updated = mem.validated_update(dismissed=[*mem.dismissed, fact.finding_id], pub=pub)
    facts = (_findings_fact("", 0, updated.findings, updated.dismissed), *facts)
    return route(outputs, {"review.memory": (updated,), "ready.facts": facts, "dash.facts": facts})


def _end(binding, outputs):
    close, mem = values(binding, CloseFact, ReviewMemory)
    ended = ReviewEnded(reviewed=mem.reviewed, pub_phase=mem.pub["phase"], reason=close.reason)
    return route(outputs, {"review.done": (ended,)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    review = s.review
    review.p.heads(HeadWork)
    review.p.closed(CloseFact)
    review.p.recover(RecoverFact)
    review.p.dismiss(DismissFact)
    review.p.memory(ReviewMemory)
    review.p.round(RoundOpen)
    review.p.output(AgentReview)
    review.p.publishable(Publishable)
    review.p.empty(EmptyReview)
    review.p.landed(ReviewLanded)
    review.p.moved(ReviewMoved)
    review.p.blocked(ReviewBlocked)
    review.p.fault(ReviewFault)
    review.p.done(ReviewEnded)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    s = net.s
    review, ready, dash = s.review, s.ready, s.dash

    # scaffolding: the conversation loop will mail RecoverFact and
    # DismissFact internally once it lands
    net.t.on_recover >> review.p.recover
    net.t.on_dismiss >> review.p.dismiss

    (
        (review.p.heads, review.p.memory)
        >> review.t.start(handler=petri_handler(_start))
        >> (
            review.p.memory,
            review.p.round,
            review.p.publishable,
        )
    )
    review.p.round >> review.t.agent(handler="review_agent") >> review.p.output
    (
        review.p.output
        >> review.t.judge(handler=petri_handler(_judge))
        >> (
            review.p.publishable,
            review.p.empty,
        )
    )
    (
        review.p.publishable
        >> review.t.publish(handler="publish_gate")
        >> (
            review.p.landed,
            review.p.moved,
            review.p.blocked,
            review.p.fault,
        )
    )
    (
        review.p.landed
        >> review.t.fold_landed(handler=petri_handler(_fold_landed))
        >> (
            review.p.memory,
            ready.p.facts,
            dash.p.facts,
        )
    )
    (
        review.p.moved
        >> review.t.fold_moved(handler=petri_handler(_fold_moved))
        >> (
            review.p.memory,
            ready.p.facts,
            dash.p.facts,
        )
    )
    (
        review.p.blocked
        >> review.t.fold_blocked(handler=petri_handler(_fold_blocked))
        >> (
            review.p.memory,
            ready.p.facts,
            dash.p.facts,
        )
    )
    (
        review.p.fault
        >> review.t.fold_fault(handler=petri_handler(_fold_fault))
        >> (
            review.p.memory,
            ready.p.facts,
            dash.p.facts,
        )
    )
    (
        review.p.empty
        >> review.t.fold_empty(handler=petri_handler(_fold_empty))
        >> (
            review.p.memory,
            ready.p.facts,
            dash.p.facts,
        )
    )
    # the exact-recovery door (A2): a blocked publication reissues under
    # the SAME operation identity; the baton is held through the round
    (
        (review.p.recover, review.p.memory)
        >> review.t.recovery(handler=petri_handler(_recover))
        >> (
            review.p.memory,
            review.p.publishable,
        )
    )
    (
        (review.p.dismiss, review.p.memory)
        >> review.t.dismissal(handler=petri_handler(_dismiss))
        >> (
            review.p.memory,
            ready.p.facts,
            dash.p.facts,
        )
    )
    ((review.p.closed, review.p.memory) >> review.t.end(handler=petri_handler(_end)) >> review.p.done)


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = ReviewMemory(reviewed=(), provisional=(), findings=(), dismissed=(), pub={"phase": "idle"})
    return {NetPath("review.memory"): (Token("ReviewMemory", baton.dump()),)}
