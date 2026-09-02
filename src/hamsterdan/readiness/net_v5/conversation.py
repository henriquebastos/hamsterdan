"""The conversation loop: the human talks to the PR in ANY phase.

Owns the ConvMemory baton and NEVER ends — close retires the workflow
loops, not the human's ability to ask questions. Lifecycle admits every
comment as an IntentFact carrying the authority claim frozen at
admission; `classify` grades it and routes the side facts:

- pure (reply, status): answered from current state, any phase;
- note (dismiss, snooze, resume, defer, recover_publication, ...):
  acknowledged and mailed to the owning loop — declined in terminal;
- committing (change, update_base, resolve_conflict): a full-claim
  MutationRequest under the comment's identity — declined outside
  `running` and while lifecycle expects our own provisional head
  (A4.3), BEFORE any gate attempt.

Every classified intent is answered through the reply gate under the
stable effect identity `reply:{comment_id}`. Replies are deliberately
CONCURRENT: custody is per-id data in the baton (pending / blocked /
faulted), not a held baton — blocked and faulted replies retain their
exact text and recover under the SAME identity, lookup-first (A2).
"""

from __future__ import annotations

from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import NetPath, Token

from hamsterdan.contracts.readiness_v5 import (
    ConvMemory,
    DismissFact,
    GateFact,
    IntentFact,
    MutationRequest,
    RecoverFact,
    Replied,
    ReplyBlocked,
    ReplyFault,
    ReplyReq,
    SnoozeFact,
)
from hamsterdan.readiness.net_v5.folding import route, values

GATES = {"conv.reply": ("reply_gate", ("Replied", "ReplyBlocked", "ReplyFault"))}

# intent kind -> grade; unknown kinds change nothing and say so
_GRADES = {
    "reply": "pure",
    "status": "pure",
    "acknowledge": "note",
    "dismiss": "note",
    "defer": "note",
    "snooze": "note",
    "resume": "note",
    "reassign": "note",
    "recover_publication": "note",
    "change": "committing",
    "update_base": "committing",
    "resolve_conflict": "committing",
}

# recover_publication: the operation prefix names the owning loop's
# recovery mailbox and the target the loop's own defense re-checks
_RECOVER_ROUTES = {
    "rerun": ("esc.recover", "esc"),
    "findings": ("review.recover", "review"),
    "reply": ("conv.recover", "conversation"),
    "reminder": ("rem.recover", "reminder"),
    "dash": ("dash.recover", "dashboard"),
    "ready": ("ready.recover", "readiness"),
    "push": ("mut.recover", "mutation"),
}

# reply vocabulary: every deterministic answer is a plain sentence in
# Dan's register — internal grade/kind tokens never reach the human. A
# pure intent publishes the agent-composed message itself.
_NO_CHANGE_TEXT = "I can't act on that — nothing in the workflow changed."
_PURE_FALLBACK_TEXT = "Nothing new to report — the summary comment is current."
_TERMINAL_TEXT = "This PR is closed — nothing changes here anymore."
_PROVISIONAL_TEXT = "My own update is still landing — ask again once it settles."
_QUIESCENT_TEXT = "This PR is a draft — I hold changes until it's ready for review."
_UNKNOWN_RECOVERY_TEXT = "I don't recognize that operation, so I can't recover it."
_NOTED_TEXT = {
    "acknowledge": "Noted.",
    "dismiss": "Noted — that finding is dismissed.",
    "defer": "Noted — that finding is set aside.",
    "snooze": "Noted — reminders are snoozed.",
    "resume": "Noted — reminders are back on.",
    "reassign": "Noted.",
    "recover_publication": "On it — I'm retrying that publication now.",
}
_STARTED_TEXT = {
    "change": "On it — I'm making that change and will push to this PR.",
    "update_base": "On it — I'm updating this branch from its base.",
    "resolve_conflict": "On it — I'm resolving the conflict and will push the result.",
}

# -- folds ---------------------------------------------------------------


def _note_routes(intent: IntentFact) -> tuple[str, dict, tuple] | None:
    """The routed fact for a note intent, or None for pure notes."""
    if intent.kind == "dismiss":
        return ("review.dismiss", {}, (DismissFact(finding_id=intent.arg),))
    if intent.kind == "snooze":
        return ("rem.snoozes", {}, (SnoozeFact(mode="snooze", arg=intent.arg),))
    if intent.kind == "resume":
        return ("rem.snoozes", {}, (SnoozeFact(mode="clear", arg=intent.arg),))
    if intent.kind == "defer":
        # Defer names a finding, not a duration. Review owns the
        # disposition; it is deliberately not a reminder clock command.
        return ("review.dismiss", {}, (DismissFact(finding_id=intent.arg),))
    return None


def _classify(binding, outputs):
    intent, mem = values(binding, IntentFact, ConvMemory)
    if intent.id in mem.served:
        return route(outputs, {"conv.memory": (mem,)})
    served = mem.validated_update(served=(*mem.served, intent.id))
    routes: dict = {}
    grade = _GRADES.get(intent.kind)

    if grade is None or not intent.authorized:
        text = _NO_CHANGE_TEXT
    elif grade == "pure":
        text = intent.arg or _PURE_FALLBACK_TEXT
    elif grade == "note":
        if intent.phase == "terminal":
            text = _TERMINAL_TEXT
        else:
            text = _NOTED_TEXT[intent.kind]
            if intent.kind == "recover_publication":
                prefix = intent.arg.split(":", 1)[0]
                found = _RECOVER_ROUTES.get(prefix)
                if found is None:
                    text = _UNKNOWN_RECOVERY_TEXT
                else:
                    target_place, target_name = found
                    routes[target_place] = (RecoverFact(target=target_name, op=intent.arg),)
            else:
                noted = _note_routes(intent)
                if noted is not None:
                    routes[noted[0]] = noted[2]
    else:  # committing
        if intent.phase != "running":
            text = _TERMINAL_TEXT if intent.phase == "terminal" else _QUIESCENT_TEXT
        elif intent.provisional:
            # A4.3: our own push is between the land and its webhook —
            # further mutations are declined BEFORE any gate attempt
            text = _PROVISIONAL_TEXT
        else:
            text = _STARTED_TEXT[intent.kind]
            routes["mut.requests"] = (
                MutationRequest(
                    op=intent.kind,
                    rid=f"comment:{intent.id}",  # producer-stable identity
                    head=intent.head,
                    base=intent.base,
                    policy=intent.policy,
                    incarnation=intent.incarnation,
                    source="conversation",
                    kind=intent.kind,  # committing grades ARE coding kinds
                    instruction=intent.arg,  # the human's exact words
                    run_id=0,
                    attempt=0,
                ),
            )

    # A2: the reply effect goes in flight — record per-id Pending
    # custody as data (replies are deliberately concurrent)
    routes["conv.memory"] = (served.validated_update(pending={**served.pending, intent.id: text}),)
    routes["conv.reply_req"] = (ReplyReq(id=intent.id, text=text),)
    return route(outputs, routes)


def _fold_replied(binding, outputs):
    out, mem = values(binding, Replied, ConvMemory)
    updated = mem.validated_update(
        pending={k: v for k, v in mem.pending.items() if k != out.id},
        blocked={k: v for k, v in mem.blocked.items() if k != out.id},
        faulted={k: v for k, v in mem.faulted.items() if k != out.id},
    )
    facts: tuple[GateFact, ...] = ()
    if out.id in mem.faulted:
        # the settle CLEARS the fault: the dashboard never keeps showing
        # a fault the human's recovery actually resolved
        facts = (
            GateFact(
                kind="fault",
                incarnation=0,
                body={"where": "conversation", "op": f"reply:{out.id}", "status": "resolved"},
            ),
        )
    routes: dict = {"conv.memory": (updated,)}
    if facts:
        routes["dash.facts"] = facts
    return route(outputs, routes)


def _fold_blocked(binding, outputs):
    out, mem = values(binding, ReplyBlocked, ConvMemory)
    updated = mem.validated_update(
        pending={k: v for k, v in mem.pending.items() if k != out.id},
        blocked={**mem.blocked, out.id: out.text},
    )
    return route(outputs, {"conv.memory": (updated,)})


def _fold_fault(binding, outputs):
    out, mem = values(binding, ReplyFault, ConvMemory)
    # A2: Faulted retains the exact text plus the reason so the human
    # can rule; a reply fault is conversation-local (dashboard only,
    # never fail-closed readiness)
    updated = mem.validated_update(
        pending={k: v for k, v in mem.pending.items() if k != out.id},
        faulted={**mem.faulted, out.id: {"text": out.text, "reason": out.reason}},
    )
    fact = GateFact(
        kind="fault",
        incarnation=0,
        body={"where": "conversation", "op": f"reply:{out.id}", "status": "faulted", "reason": out.reason},
    )
    return route(outputs, {"conv.memory": (updated,), "dash.facts": (fact,)})


def _recover(binding, outputs):
    fact, mem = values(binding, RecoverFact, ConvMemory)
    if fact.target != "conversation" or not fact.op.startswith("reply:"):
        return route(outputs, {"conv.memory": (mem,)})
    reply_id = fact.op.removeprefix("reply:")
    if reply_id in mem.pending:
        # SINGLE-FLIGHT: the identity is already in flight — a second
        # recovery must not issue a concurrent occurrence, or two gate
        # calls could both observe "absent" and post twice
        return route(outputs, {"conv.memory": (mem,)})
    if reply_id in mem.blocked:
        text = mem.blocked[reply_id]
    elif reply_id in mem.faulted:
        text = mem.faulted[reply_id]["text"]
    else:
        return route(outputs, {"conv.memory": (mem,)})
    # custody moves back in flight under the SAME identity; the gate's
    # lookup-first read reconciles a crash after the provider accepted
    # (A2). The blocked entry LEAVES with its custody; a faulted entry
    # REMAINS as the unresolved-fault marker `_fold_replied` reads to
    # publish the operation-keyed resolution.
    updated = mem.validated_update(
        pending={**mem.pending, reply_id: text},
        blocked={k: v for k, v in mem.blocked.items() if k != reply_id},
    )
    return route(outputs, {"conv.memory": (updated,), "conv.reply_req": (ReplyReq(id=reply_id, text=text),)})


# -- topology ------------------------------------------------------------


def declare(s) -> None:
    """Declare the places this loop owns."""
    conv = s.conv
    conv.p.intents(IntentFact)
    conv.p.recover(RecoverFact)
    conv.p.memory(ConvMemory)
    conv.p.reply_req(ReplyReq)
    conv.p.replied(Replied)
    conv.p.rblocked(ReplyBlocked)
    conv.p.rfault(ReplyFault)


def wire(net) -> None:
    """Wire this loop's transitions (sibling places must exist)."""
    s = net.s
    conv, review, esc, mut = s.conv, s.review, s.esc, s.mut
    rem, dash, ready = s.rem, s.dash, s.ready

    (
        (conv.p.intents, conv.p.memory)
        >> conv.t.classify(handler=petri_handler(_classify))
        >> (
            conv.p.memory,
            conv.p.reply_req,
            conv.p.recover,
            mut.p.requests,
            mut.p.recover,
            review.p.recover,
            review.p.dismiss,
            rem.p.snoozes,
            rem.p.recover,
            dash.p.recover,
            ready.p.recover,
            esc.p.recover,
        )
    )
    (
        conv.p.reply_req
        >> conv.t.reply(handler="reply_gate")
        >> (
            conv.p.replied,
            conv.p.rblocked,
            conv.p.rfault,
        )
    )
    (
        (conv.p.replied, conv.p.memory)
        >> conv.t.fold_replied(handler=petri_handler(_fold_replied))
        >> (
            conv.p.memory,
            dash.p.facts,
        )
    )
    ((conv.p.rblocked, conv.p.memory) >> conv.t.fold_rblocked(handler=petri_handler(_fold_blocked)) >> conv.p.memory)
    (
        (conv.p.rfault, conv.p.memory)
        >> conv.t.fold_rfault(handler=petri_handler(_fold_fault))
        >> (
            conv.p.memory,
            dash.p.facts,
        )
    )
    # the exact-recovery door (A2): a blocked or faulted reply reissues
    # under the SAME identity with the retained text
    (
        (conv.p.recover, conv.p.memory)
        >> conv.t.recovery(handler=petri_handler(_recover))
        >> (
            conv.p.memory,
            conv.p.reply_req,
        )
    )


def seed() -> dict:
    """This loop's contribution to the newborn Instance marking."""
    baton = ConvMemory(served=(), pending={}, blocked={}, faulted={})
    return {NetPath("conv.memory"): (Token("ConvMemory", baton.dump()),)}
