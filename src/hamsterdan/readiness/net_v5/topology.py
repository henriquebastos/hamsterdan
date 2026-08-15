"""V5 actor-loop executable topology for one PR-readiness Instance.

The V5 discipline (ES-007, CV17): one concern = one loop = one memory
baton plus mailbox places; cross-loop influence is mailed facts only;
zero guards, zero read arcs, zero CEL filters, zero unowned places.
Every decision is a pure fold on token data. Ingress doors are the only
no-input transitions; the engine's identified delivery is the only
deduplication anywhere.

This module currently ships the lifecycle (admission) loop; sibling
loops arrive slice by slice under CV17.DS1. The `on_provisional` door is
scaffolding for the not-yet-present mutation loop, which will mail
`ProvisionalHead` facts internally.
"""

from __future__ import annotations

import json

from petrus.impetus.dsl import BuiltNet, NetSpec, petri_handler
from petrus.impetus.petrinet import Marking, NetPath, Token
from pydantic import TypeAdapter

from hamsterdan.contracts.readiness_v5 import (
    CloseFact,
    CloseSeen,
    CommentSeen,
    DraftSeen,
    GateFact,
    HeadSeen,
    HeadWork,
    HumanSeen,
    IntentFact,
    LifeState,
    ProvisionalHead,
    ReadySeen,
    RunSeen,
    RunWork,
)

_COLORS = (
    HeadSeen,
    DraftSeen,
    ReadySeen,
    CloseSeen,
    CommentSeen,
    HumanSeen,
    RunSeen,
    LifeState,
    HeadWork,
    IntentFact,
    CloseFact,
    RunWork,
    ProvisionalHead,
    GateFact,
)
_TOKEN_ADAPTERS = {color.__name__: TypeAdapter(color) for color in _COLORS}


def _values(binding, *types):
    """Hydrate the bound tokens and select one strict value per type."""
    hydrated = []
    for _, selected in (*binding.read, *binding.consumed):
        for token in selected:
            hydrated.append(
                _TOKEN_ADAPTERS[token.color].validate_json(
                    json.dumps(token.data, sort_keys=True, separators=(",", ":"))
                )
            )
    return tuple(next(value for value in hydrated if isinstance(value, kind)) for kind in types)


def _route(outputs, mapping):
    """Emit strict values only on the targets named in mapping."""
    return {
        out.target: tuple(Token(out.color, value.dump()) for value in mapping[str(out.target)])
        for out in outputs
        if str(out.target) in mapping
    }


def _state_fact(state: LifeState) -> GateFact:
    return GateFact(
        kind="state",
        incarnation=state.incarnation,
        body={
            "phase": state.phase,
            "head": state.head,
            "base": state.base,
            "mergeable": state.mergeable,
            "policy": state.policy,
        },
    )


# -- lifecycle folds: the admission hub (all pure) ---------------------------


def _admitted_state_outputs(state: LifeState, work: HeadWork) -> dict:
    fact = _state_fact(state)
    return {
        "life.state": (state,),
        "review.heads": (work,),
        "ci.heads": (work,),
        "ready.facts": (fact,),
        "dash.facts": (fact,),
    }


def _admit_head(binding, outputs):
    seen, state = _values(binding, HeadSeen, LifeState)
    if state.phase == "terminal":
        return _route(outputs, {"life.state": (state,)})
    if state.phase == "quiescent":
        # dormancy absorbs every head observation with no work emission;
        # resume re-admits under a fresh incarnation
        recorded = state.validated_update(head=seen.head, base=seen.base, mergeable=seen.mergeable, policy=seen.policy)
        return _route(outputs, {"life.state": (recorded,)})
    if seen.head == state.head:
        refreshed = seen.base != state.base or seen.mergeable != state.mergeable or seen.policy != state.policy
        if not refreshed:
            return _route(outputs, {"life.state": (state,)})
        # base/policy refresh: same lifetime, no incarnation bump, no new
        # agent round — review republishes provisionals under the fresh
        # authority through the `refreshed` relation
        current = state.validated_update(base=seen.base, mergeable=seen.mergeable, policy=seen.policy)
        work = HeadWork(
            incarnation=current.incarnation,
            head=current.head,
            base=current.base,
            policy=current.policy,
            relation="refreshed",
            lineage=current.lineage,
        )
        return _route(outputs, _admitted_state_outputs(current, work))
    confirmed = state.expected != "" and state.expected == seen.head
    relation = "confirmed" if confirmed else ("new" if state.head == "" else "superseded")
    lineage = state.lineage if confirmed else ""
    admitted = LifeState(
        phase="running",
        incarnation=state.incarnation + 1,
        head=seen.head,
        base=seen.base,
        mergeable=seen.mergeable,
        policy=seen.policy,
        expected="",
        expected_op="",
        lineage=lineage,
    )
    work = HeadWork(
        incarnation=admitted.incarnation,
        head=seen.head,
        base=seen.base,
        policy=seen.policy,
        relation=relation,
        lineage=lineage,
    )
    return _route(outputs, _admitted_state_outputs(admitted, work))


def _admit_draft(binding, outputs):
    _, state = _values(binding, DraftSeen, LifeState)
    if state.phase != "running":
        return _route(outputs, {"life.state": (state,)})
    quiescent = state.validated_update(phase="quiescent")
    fact = _state_fact(quiescent)
    return _route(
        outputs,
        {"life.state": (quiescent,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _admit_ready(binding, outputs):
    _, state = _values(binding, ReadySeen, LifeState)
    if state.phase != "quiescent":
        return _route(outputs, {"life.state": (state,)})
    resumed = state.validated_update(phase="running", incarnation=state.incarnation + 1)
    work = HeadWork(
        incarnation=resumed.incarnation,
        head=resumed.head,
        base=resumed.base,
        policy=resumed.policy,
        relation="resumed",
        lineage="",
    )
    return _route(outputs, _admitted_state_outputs(resumed, work))


def _admit_close(binding, outputs):
    seen, state = _values(binding, CloseSeen, LifeState)
    if state.phase == "terminal":
        return _route(outputs, {"life.state": (state,)})
    terminal = state.validated_update(phase="terminal")
    close = CloseFact(reason=seen.reason)
    return _route(
        outputs,
        {
            "life.state": (terminal,),
            "review.closed": (close,),
            "ci.closed": (close,),
            "esc.closed": (close,),
            "mut.closed": (close,),
            "dash.closed": (close,),
            "rem.closed": (close,),
            "ready.closed": (close,),
        },
    )


def _admit_comment(binding, outputs):
    seen, state = _values(binding, CommentSeen, LifeState)
    intent = IntentFact(
        id=seen.id,
        kind=seen.kind,
        arg=seen.arg,
        authorized=seen.authorized,
        phase=state.phase,
        provisional=state.expected != "",
        incarnation=state.incarnation,
        head=state.head,
        base=state.base,
        policy=state.policy,
    )
    return _route(outputs, {"life.state": (state,), "conv.intents": (intent,)})


def _admit_human(binding, outputs):
    seen, state = _values(binding, HumanSeen, LifeState)
    if state.phase == "terminal":
        return _route(outputs, {"life.state": (state,)})
    fact = GateFact(
        kind="human",
        incarnation=state.incarnation,
        body={
            "approval": seen.approval,
            "changes_requested": seen.changes_requested,
            "unresolved": seen.unresolved,
        },
    )
    return _route(
        outputs,
        {"life.state": (state,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _admit_runs(binding, outputs):
    seen, state = _values(binding, RunSeen, LifeState)
    if state.phase != "running":
        return _route(outputs, {"life.state": (state,)})
    work = RunWork(
        incarnation=state.incarnation,
        head=seen.head,
        run_id=seen.run_id,
        attempt=seen.attempt,
        conclusion=seen.conclusion,
        fingerprint=seen.fingerprint,
    )
    return _route(outputs, {"life.state": (state,), "ci.runs": (work,)})


def _note_provisional(binding, outputs):
    note, state = _values(binding, ProvisionalHead, LifeState)
    noted = state.validated_update(expected=note.expected, expected_op=note.op, lineage=note.lineage)
    return _route(outputs, {"life.state": (noted,)})


# -- topology -----------------------------------------------------------------


def build_net_v5() -> BuiltNet:
    net = NetSpec("pr_v5")
    s = net.s
    life, review, ci, esc = s.life, s.review, s.ci, s.esc
    conv, mut, dash, rem, ready = s.conv, s.mut, s.dash, s.rem, s.ready

    # -- lifecycle: mailboxes and the baton
    life.p.heads(HeadSeen)
    life.p.drafts(DraftSeen)
    life.p.readies(ReadySeen)
    life.p.closes(CloseSeen)
    life.p.comments(CommentSeen)
    life.p.humans(HumanSeen)
    life.p.runs(RunSeen)
    life.p.provisional(ProvisionalHead)
    life.p.state(LifeState)

    # -- ingress doors: the host delivers normalized observations
    net.t.on_head >> life.p.heads
    net.t.on_draft >> life.p.drafts
    net.t.on_ready >> life.p.readies
    net.t.on_close >> life.p.closes
    net.t.on_comment >> life.p.comments
    net.t.on_human >> life.p.humans
    net.t.on_runs >> life.p.runs
    # scaffolding: the mutation loop will mail ProvisionalHead internally
    net.t.on_provisional >> life.p.provisional

    # -- sibling mailboxes the admission hub feeds
    review.p.heads(HeadWork)
    review.p.closed(CloseFact)
    ci.p.heads(HeadWork)
    ci.p.runs(RunWork)
    ci.p.closed(CloseFact)
    esc.p.closed(CloseFact)
    conv.p.intents(IntentFact)
    mut.p.closed(CloseFact)
    dash.p.facts(GateFact)
    dash.p.closed(CloseFact)
    rem.p.closed(CloseFact)
    ready.p.facts(GateFact)
    ready.p.closed(CloseFact)

    # -- lifecycle admission (each fold: one mailbox + the state baton)
    (
        (life.p.heads, life.p.state)
        >> life.t.admit_head(handler=petri_handler(_admit_head))
        >> (life.p.state, review.p.heads, ci.p.heads, ready.p.facts, dash.p.facts)
    )
    (
        (life.p.drafts, life.p.state)
        >> life.t.admit_draft(handler=petri_handler(_admit_draft))
        >> (life.p.state, ready.p.facts, dash.p.facts)
    )
    (
        (life.p.readies, life.p.state)
        >> life.t.admit_ready(handler=petri_handler(_admit_ready))
        >> (life.p.state, review.p.heads, ci.p.heads, ready.p.facts, dash.p.facts)
    )
    (
        (life.p.closes, life.p.state)
        >> life.t.admit_close(handler=petri_handler(_admit_close))
        >> (
            life.p.state,
            review.p.closed,
            ci.p.closed,
            esc.p.closed,
            mut.p.closed,
            dash.p.closed,
            rem.p.closed,
            ready.p.closed,
        )
    )
    (
        (life.p.comments, life.p.state)
        >> life.t.admit_comment(handler=petri_handler(_admit_comment))
        >> (life.p.state, conv.p.intents)
    )
    (
        (life.p.humans, life.p.state)
        >> life.t.admit_human(handler=petri_handler(_admit_human))
        >> (life.p.state, ready.p.facts, dash.p.facts)
    )
    (life.p.runs, life.p.state) >> life.t.admit_runs(handler=petri_handler(_admit_runs)) >> (life.p.state, ci.p.runs)
    (
        (life.p.provisional, life.p.state)
        >> life.t.note_provisional(handler=petri_handler(_note_provisional))
        >> life.p.state
    )

    return net.build()


def seed_marking() -> Marking:
    """The newborn Instance: every loop starts with its baton in place."""
    seed = LifeState(
        phase="running",
        incarnation=0,
        head="",
        base="",
        mergeable=False,
        policy="",
        expected="",
        expected_op="",
        lineage="",
    )
    return Marking({NetPath("life.state"): (Token("LifeState", seed.dump()),)})
