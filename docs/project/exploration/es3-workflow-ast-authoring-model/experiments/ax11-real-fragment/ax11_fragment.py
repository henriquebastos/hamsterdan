"""AX11 — the real conversation-intent fragment authored in the leading design.

Production original: `src/hamsterdan/readiness/net/topology.py` —
classification activity bridge (~line 1229), ``unpack_intents``
(~lines 1489–1491, handler at 189–203), the ``accept_*_intent`` loop
(~lines 1492–1506, handler at 862–868), ``authorize_reply``
(~lines 1507–1517, handler at 978–996, predicates at 971–976), and the
``reply_basis`` retire (~lines 1651–1656).

Domain truth is **imported, not re-authored**: the same strict contracts
(`hamsterdan.contracts.readiness`), the same ``fold_intent`` fold, the
same ``operation``/``effect_payload`` identity derivation. What changes
is only how topology, routing, and guards are *expressed*:

- guards are typed predicate expressions compiled to CEL binding guards
  (production: Python ``typed_guard``/``_guard`` closures);
- routing multiplicity is a declared ``scatter`` with decidably disjoint
  lanes and an explicit ``rest=DROP`` (production: a hand-written
  binding handler with a routing table nobody checks);
- the park-until-state-changes gaps are written down (``otherwise=WAIT``;
  production: implied by the absence of any admitting transition);
- state folds and work emission are pure typed functions; the binding
  plumbing (hydration, `_route`, `_values`) is synthesized.
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
    read_port,
    retire,
    scatter,
    state_port,
    update,
)
from ax11_predicates import Predicate, on
from petrus.motus.activity import activity as motus_activity

from hamsterdan.contracts.readiness import (
    Authority,
    ConversationClassificationRequest,
    ConversationPublicationRequest,
    ConversationPublicationState,
    HumanState,
    Intent,
    IntentBatch,
    ReviewState,
)
from hamsterdan.readiness.net.topology import effect_payload, fold_intent, operation
from hamsterdan.readiness.payloads import PydanticPayloadConverter

# -- ports: every place is named by the author (types never identify places)

AUTHORITY = read_port("authority", Authority)
REVIEW_STATE = state_port("review_state", ReviewState)
HUMAN_STATE = state_port("human_state", HumanState)
PUBLICATION_STATE = state_port("conversation_publication_state", ConversationPublicationState)

ENTRY = port("work_conversation", ConversationClassificationRequest)
INTENT_BATCH = port("intent_batch", IntentBatch)
INTENT_RESULT = port("intent_result", Intent)
REPLY_BASIS = port("reply_basis", Intent)
CHANGE_BASIS = port("change_basis", Intent)
RECOVERY_BASIS = port("recovery_basis", Intent)
REPLY_WORK = port("work_conversation_reply", ConversationPublicationRequest)

FINDING_KINDS = ("acknowledge", "dismiss", "defer")
REMINDER_KINDS = ("snooze", "resume", "reassign")
CHANGE_KINDS = ("change", "update_base", "resolve_conflict")

# -- predicates: expression objects compiled to CEL binding guards

_authority = on(Authority)
_intent = on(Intent)
_publication = on(ConversationPublicationState)

#: Production `_current(a, value)` for Intent values, verbatim semantics.
CURRENT: Predicate = (
    (_intent.epoch == _authority.epoch)
    & (_intent.head == _authority.head)
    & ((_intent.base_head == "") | (_intent.base_head == _authority.base_head))
    & ((_intent.policy_digest == "") | (_intent.policy_digest == _authority.policy_digest))
)

AUTHORIZED: Predicate = _intent.authorized == True

#: Production `_valid_reply`: current, authorized, kind "reply", nonempty message.
VALID_REPLY: Predicate = (
    CURRENT
    & AUTHORIZED
    & (_intent.kind == "reply")
    & _intent.arguments["message"].present()
    & (_intent.arguments["message"] != "")
)

#: Production `_replyable`: valid and the publication concern is idle.
REPLYABLE: Predicate = (
    VALID_REPLY
    & (_publication.conversation_requested == False)
    & (_publication.conversation_capability_blocking == False)
)


# -- activities and pure steps: domain truth imported from production


@motus_activity(converter=PydanticPayloadConverter())
def classify_conversation(request: ConversationClassificationRequest) -> IntentBatch:
    """Stand-in for the agent-side classifier: the comment text carries the
    classified intents as JSON so tests choose scenarios deterministically."""
    import json

    intents = [Intent(**raw) for raw in json.loads(request.comment.text)]
    return IntentBatch(epoch=request.epoch, head=request.head, intents=intents)


def unpack_intents(batch: IntentBatch) -> tuple[Intent, ...]:
    return tuple(batch.intents)


def accept_finding_intent(authority: Authority, state: ReviewState, value: Intent) -> ReviewState:
    del authority  # guard context only; the fold owns no currency judgment
    return fold_intent.implementation(state, value)


def accept_reminder_intent(authority: Authority, state: HumanState, value: Intent) -> HumanState:
    del authority
    return fold_intent.implementation(state, value)


def authorize_reply(
    authority: Authority, state: ConversationPublicationState, value: Intent
) -> tuple[ConversationPublicationState, ConversationPublicationRequest]:
    payload = effect_payload(authority, {"intent": value.dump()})
    work = ConversationPublicationRequest(
        epoch=value.epoch,
        head=value.head,
        operation=operation("conversation-reply", authority, payload=payload),
        base_head=authority.base_head,
        policy_digest=authority.policy_digest,
        intent=value,
    )
    state = state.validated_update(
        conversation_requested=True,
        conversation_operation=work.operation,
        conversation_recovery=work,
        conversation_capability_blocking=False,
    )
    return state, work


# -- the fragment


def conversation_intents() -> Fragment:
    return fragment(
        "conversation-intents",
        entry=ENTRY,
        reads=(AUTHORITY,),
        states=(REVIEW_STATE, HUMAN_STATE, PUBLICATION_STATE),
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
                        otherwise=WAIT,  # stale/unauthorized intents park, as production implies
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
                        otherwise=WAIT,  # valid but the concern is busy: wait for it to clear
                    ),
                ),
                lane(CHANGE_BASIS, where=_intent.kind.one_of(*CHANGE_KINDS), then=EXIT),
                lane(RECOVERY_BASIS, where=_intent.kind == "recover_publication", then=EXIT),
                rest=DROP,  # e.g. kind "status": production drops it silently; here it is written
            ),
        ),
    )
