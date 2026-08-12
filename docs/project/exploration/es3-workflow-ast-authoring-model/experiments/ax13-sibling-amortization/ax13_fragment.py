"""AX13 — the sibling change-intent concern, authored as marginal material
over AX11's vocabulary.

Production original: `src/hamsterdan/readiness/net/topology.py` —
`_mutation` (~line 944), `_authorize_change` (~954), the
`authorize_change` wiring (~1402–1414), and the `change_basis` retire
(~1657–1659).

Everything above the `MARGINAL` markers is imported unchanged from AX11:
ports, predicates (`CURRENT`, `AUTHORIZED`, `VALID_REPLY`, `REPLYABLE`),
activities, and kind constants. The only new authoring is what the change
concern itself demands — two ports, one predicate, one pure function, and
the lane body that replaces AX11's `then=EXIT` hand-off.

Production semantics note, preserved verbatim: the change retire guard is
the exact complement of the authorize guard (`not _mutation`), so a valid
change intent whose mutation concern is *busy* is **retired**, not parked
— unlike the reply lane, where a valid-but-busy intent waits. The
authored `choice` states both cases explicitly, and its mandatory
`otherwise=WAIT` is unreachable by construction of the complement.
"""

from __future__ import annotations

from ax11_ast import (
    DROP,
    EXIT,
    WAIT,
    Fragment,
    activity_step,
    case,
    choice,
    fold,
    fragment,
    lane,
    port,
    retire,
    scatter,
    state_port,
    update,
)
from ax11_fragment import (
    AUTHORITY,
    AUTHORIZED,
    CHANGE_BASIS,
    CHANGE_KINDS,
    CURRENT,
    ENTRY,
    FINDING_KINDS,
    HUMAN_STATE,
    INTENT_BATCH,
    INTENT_RESULT,
    PUBLICATION_STATE,
    RECOVERY_BASIS,
    REMINDER_KINDS,
    REPLY_BASIS,
    REPLY_WORK,
    REPLYABLE,
    REVIEW_STATE,
    VALID_REPLY,
    _intent,
    accept_finding_intent,
    accept_reminder_intent,
    authorize_reply,
    classify_conversation,
    unpack_intents,
)
from ax11_predicates import Predicate, on

from hamsterdan.contracts.readiness import Authority, ChangeRequest, Intent, MutationState
from hamsterdan.readiness.net.topology import effect_payload, operation

# -- MARGINAL: ports the change concern adds --------------------------------

MUTATION_STATE = state_port("mutation_state", MutationState)
CHANGE_WORK = port("work_change", ChangeRequest)

# -- MARGINAL: the change predicate (production `_mutation`, verbatim) ------

_mutation_state = on(MutationState)

#: Production `_mutation`: current, authorized, blocking, a change kind,
#: and the mutation concern idle (no provisional head, nothing in flight).
MUTATION: Predicate = (
    CURRENT
    & AUTHORIZED
    & (_intent.blocking == True)
    & _intent.kind.one_of(*CHANGE_KINDS)
    & (_mutation_state.provisional == False)
    & (_mutation_state.change_in_flight == False)
    & (_mutation_state.repair_in_flight == False)
)

# -- MARGINAL: the change update (production `_authorize_change`, verbatim) -


def authorize_change(authority: Authority, state: MutationState, value: Intent) -> tuple[MutationState, ChangeRequest]:
    payload = effect_payload(authority, {"intent": value.dump()})
    op = operation("change", authority, payload=payload)
    state = state.validated_update(change_in_flight=True, mutation_operation=op)
    work = ChangeRequest(
        epoch=value.epoch,
        head=value.head,
        operation=op,
        base_head=authority.base_head,
        policy_digest=authority.policy_digest,
        intent=value,
    )
    return state, work


# -- MARGINAL: the change lane body (replaces AX11's `then=EXIT`) -----------

CHANGE_LANE_BODY = choice(
    case(when=MUTATION, then=update(authorize_change, state=MUTATION_STATE, emits=(CHANGE_WORK,))),
    case(when=~MUTATION, then=retire()),
    otherwise=WAIT,  # unreachable: the two cases are complements — stated, not implied
)


# -- the extended fragment: AX11's body with the change lane grown ----------


def conversation_intents_with_change() -> Fragment:
    return fragment(
        "conversation-intents-change",
        entry=ENTRY,
        reads=(AUTHORITY,),
        states=(REVIEW_STATE, HUMAN_STATE, PUBLICATION_STATE, MUTATION_STATE),
        body=(
            activity_step(classify_conversation, out=INTENT_BATCH),
            scatter(
                unpack_intents,
                lane(
                    INTENT_RESULT,
                    where=_intent.kind.one_of(*FINDING_KINDS, *REMINDER_KINDS),
                    then=choice(
                        case(
                            when=CURRENT & AUTHORIZED & _intent.kind.one_of(*FINDING_KINDS),
                            then=fold(accept_finding_intent, state=REVIEW_STATE),
                        ),
                        case(
                            when=CURRENT & AUTHORIZED & _intent.kind.one_of(*REMINDER_KINDS),
                            then=fold(accept_reminder_intent, state=HUMAN_STATE),
                        ),
                        otherwise=WAIT,
                    ),
                ),
                lane(
                    REPLY_BASIS,
                    where=_intent.kind == "reply",
                    then=choice(
                        case(
                            when=REPLYABLE,
                            then=update(authorize_reply, state=PUBLICATION_STATE, emits=(REPLY_WORK,)),
                        ),
                        case(when=~VALID_REPLY, then=retire()),
                        otherwise=WAIT,
                    ),
                ),
                lane(CHANGE_BASIS, where=_intent.kind.one_of(*CHANGE_KINDS), then=CHANGE_LANE_BODY),
                lane(RECOVERY_BASIS, where=_intent.kind == "recover_publication", then=EXIT),
                rest=DROP,
            ),
        ),
    )
