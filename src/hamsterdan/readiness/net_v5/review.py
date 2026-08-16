"""The V5 review actor loop: one durable review memory per PR.

Owns the ReviewMemory baton. Each admitted head opens ONE agent round
(the agent gate sees only its work token — no GitHub credential enters
agent territory); a clean unable result mails fail-closed review status
without becoming an effect fault. The judge replaces retained findings
and lineage with the validated agent result, then filters dismissals;
the publish gate posts under one stable effect identity
`findings:{head}:i{inc}`
with A1.5 authority fencing and A2 lookup-first reconciliation. A moved
publication retains its findings provisionally — the next refreshed
authority republishes them under the SAME identity without a new agent
round. The baton is HELD through every in-flight round, so no second
decision can race it.
"""

from __future__ import annotations

import re
from hashlib import sha256

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
    ReviewStatus,
    RoundMoved,
    RoundOpen,
    RoundUnable,
)
from hamsterdan.readiness.net_v5.folding import revive, route, values

GATES = {
    "review.agent": ("review_agent", ("AgentReview", "RoundMoved", "RoundUnable")),
    "review.publish": (
        "publish_gate",
        ("ReviewLanded", "ReviewMoved", "ReviewBlocked", "ReviewFault"),
    ),
}
_MARKER_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")

# -- folds ---------------------------------------------------------------


def _live(findings, dismissed) -> list[dict]:
    return [f for f in findings if f["id"] not in dismissed]


def _status(findings, dismissed) -> ReviewStatus:
    return "blocking" if any(f["blocking"] for f in _live(findings, dismissed)) else "clear"


def _review_fact(head: str, incarnation: int, status: ReviewStatus) -> GateFact:
    return GateFact(kind="review", incarnation=incarnation, body={"head": head, "status": status})


def _operation(subject: str, head: str, incarnation: int) -> str:
    operation = f"review:{subject}:{head}:i{incarnation}"
    if len(operation.encode()) > 1024:
        raise ValueError("V5 review operation exceeds the Agenticus identity bound")
    return operation


def _publishable(head: str, base: str, policy: str, incarnation: int, findings, mem: ReviewMemory) -> Publishable:
    """One publication request with a durable Pending record in its mem (A2).

    The publication takes EXCLUSIVE custody of the findings: `provisional`
    is cleared so no refresh can republish a diverging subset while a
    blocked/faulted descriptor retains the exact attempted content. A
    MOVED terminal restores the complete attempted list to provisional.
    """
    op = f"findings:{head}:i{incarnation}"
    if _MARKER_OPERATION.fullmatch(op) is None:
        digest = sha256(f"{head}\0{incarnation}".encode()).hexdigest()
        op = f"findings:sha256:{digest}:i{incarnation}"
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
    prior_findings = list(mem.provisional) if mem.provisional else list(mem.findings)
    opened_mem = mem.validated_update(head=work.head, incarnation=work.incarnation, status="pending")
    opened = RoundOpen(
        operation=_operation(mem.subject, work.head, work.incarnation),
        head=work.head,
        base=work.base,
        policy=work.policy,
        incarnation=work.incarnation,
        prior_findings=prior_findings,
        prior_lineage=list(mem.lineage),
        mem=opened_mem.dump(),  # the baton is HELD through the round
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
    mem = mem.validated_update(
        findings=list(out.findings),
        lineage=list(out.lineage),
        status=_status(out.findings, mem.dismissed),
    )
    live = _live(out.findings, mem.dismissed)
    if not live:
        empty = EmptyReview(head=out.head, incarnation=out.incarnation, mem=mem.dump())
        return route(outputs, {"review.empty": (empty,)})
    return route(
        outputs,
        {"review.publishable": (_publishable(out.head, out.base, out.policy, out.incarnation, live, mem),)},
    )


def _unable(binding, outputs):
    (out,) = values(binding, RoundUnable)
    mem = revive(ReviewMemory, out.mem)
    if out.head not in mem.reviewed:
        mem = mem.validated_update(reviewed=[*mem.reviewed, out.head])
    mem = mem.validated_update(status="unable")
    fact = GateFact(
        kind="review",
        incarnation=out.incarnation,
        body={"head": out.head, "status": "unable", "category": out.category},
    )
    return route(outputs, {"review.memory": (mem,), "ready.facts": (fact,), "dash.facts": (fact,)})


def _round_moved(binding, outputs):
    (out,) = values(binding, RoundMoved)
    # Authority moved before agent custody. Restore the held baton without
    # claiming an agent round or mailing inability as current evidence; the
    # lifecycle actor's queued current HeadWork opens the replacement round.
    return route(outputs, {"review.memory": (revive(ReviewMemory, out.mem),)})


def _findings_fact(head: str, incarnation: int, findings, dismissed) -> GateFact:
    blocking = sum(1 for f in findings if f["blocking"] and f["id"] not in dismissed)
    return GateFact(
        kind="findings",
        incarnation=incarnation,
        body={"head": head, "blocking": blocking, "count": len(findings)},
    )


def _settlement_facts(mem: ReviewMemory, head: str, incarnation: int) -> tuple[GateFact, ...]:
    facts = (_findings_fact(head, incarnation, mem.findings, mem.dismissed),)
    if mem.status in ("clear", "blocking"):
        return (*facts, _review_fact(head, incarnation, mem.status))
    return facts


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
        pub={"phase": "idle"},
    )
    facts = _settlement_facts(mem, out.head, out.incarnation)
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
    facts = _settlement_facts(mem, out.head, out.incarnation)
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
        pub={"phase": "idle"},
    )
    facts = _settlement_facts(mem, out.head, out.incarnation)
    return route(outputs, {"review.memory": (mem,), "ready.facts": facts, "dash.facts": facts})


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
    fault_facts: tuple[GateFact, ...] = ()
    if pub.get("phase") in ("blocked", "faulted") and any(f["id"] == fact.finding_id for f in pub.get("findings", ())):
        # the human waved off a finding the retained operation carries:
        # CANCEL the operation (recovery goes inert) rather than rewrite
        # its content under the same effect identity — the descriptor
        # stays for audit
        if pub["phase"] == "faulted":
            fault_facts = (
                GateFact(kind="fault", incarnation=0, body={"where": "review", "op": pub["op"], "status": "cancelled"}),
            )
        pub = {**pub, "phase": "cancelled"}
    dismissed = list(mem.dismissed) if fact.finding_id in mem.dismissed else [*mem.dismissed, fact.finding_id]
    updated = mem.validated_update(dismissed=dismissed, pub=pub)
    current = any(finding["id"] == fact.finding_id for finding in updated.findings)
    facts: tuple[GateFact, ...] = fault_facts
    if current:
        facts = (_findings_fact(updated.head, updated.incarnation, updated.findings, updated.dismissed), *facts)
        if updated.status in ("clear", "blocking"):
            updated = updated.validated_update(status=_status(updated.findings, updated.dismissed))
            facts = (facts[0], _review_fact(updated.head, updated.incarnation, updated.status), *facts[1:])
    return route(outputs, {"review.memory": (updated,), "ready.facts": facts, "dash.facts": facts})


def _end(binding, outputs):
    close, mem = values(binding, CloseFact, ReviewMemory)
    ended = ReviewEnded(reviewed=mem.reviewed, pub_phase=mem.pub["phase"], reason=close.reason)
    return route(outputs, {"review.done": (ended,)})


def _drain_dismiss(binding, outputs):
    # a dismiss admitted while running can be applied AFTER the loop
    # retired (its transition waited on the baton a gate held in flight
    # while close won the race for it): close wins, the note is inert —
    # never a stranded token
    _, ended = values(binding, DismissFact, ReviewEnded)
    return route(outputs, {"review.done": (ended,)})


def _drain_recover(binding, outputs):
    _, ended = values(binding, RecoverFact, ReviewEnded)
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
    review.p.round_moved(RoundMoved)
    review.p.unable(RoundUnable)
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

    (
        (review.p.heads, review.p.memory)
        >> review.t.start(handler=petri_handler(_start))
        >> (
            review.p.memory,
            review.p.round,
            review.p.publishable,
        )
    )
    (
        review.p.round
        >> review.t.agent(handler="review_agent")
        >> (
            review.p.output,
            review.p.round_moved,
            review.p.unable,
        )
    )
    (review.p.round_moved >> review.t.fold_round_moved(handler=petri_handler(_round_moved)) >> review.p.memory)
    (
        review.p.output
        >> review.t.judge(handler=petri_handler(_judge))
        >> (
            review.p.publishable,
            review.p.empty,
        )
    )
    (
        review.p.unable
        >> review.t.fold_unable(handler=petri_handler(_unable))
        >> (
            review.p.memory,
            ready.p.facts,
            dash.p.facts,
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
    # post-close drains: a note whose apply lost the race with close is
    # absorbed by the retired loop's persistent done baton, never stranded
    (
        (review.p.dismiss, review.p.done)
        >> review.t.drain_dismiss(handler=petri_handler(_drain_dismiss))
        >> review.p.done
    )
    (
        (review.p.recover, review.p.done)
        >> review.t.drain_recover(handler=petri_handler(_drain_recover))
        >> review.p.done
    )


def seed(subject: str) -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = ReviewMemory(
        subject=subject,
        head="",
        incarnation=0,
        status="pending",
        reviewed=(),
        provisional=(),
        findings=(),
        lineage=(),
        dismissed=(),
        pub={"phase": "idle"},
    )
    return {NetPath("review.memory"): (Token("ReviewMemory", baton.dump()),)}
