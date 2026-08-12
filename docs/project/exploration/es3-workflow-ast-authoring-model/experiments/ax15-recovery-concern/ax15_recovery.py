"""AX15 — production's hardest guard as a composed hand-off concern.

`_recoverable_publication` (`topology.py` ~998–1035) is the densest
routing decision in the net: five tokens (Authority, three publication
states, the Intent), open-map arguments (`target`, `operation`), and a
nested *optional* recovery request whose identity must match the current
authority exactly. Production expresses it as one generic Python
predicate shared by three `recover_publication.{target}` transitions
(each reading **all three** states, because the shared closure needs all
its parameters) plus a `reject_recovery` retire guarded by the
hand-built complement.

The authored form specializes the predicate per target, so each case
binds only the state it actually judges — and the complement retire is
not authored at all: it is AX11's mandatory `otherwise`, generated
mechanically as the conjunction of case negations (exactly what
production wrote by hand).

The predicate vocabulary is stretched to its edges here, deliberately:

- map-key presence + map-key-to-field comparison, in the validated
  direction (map ref left, guarded by `.present()` earlier in the
  conjunction — the AX11 null-safety rule);
- nested access *through an optional parent*
  (`conversation_recovery.epoch`): sound only because a
  `.present()` conjunct precedes it and CEL `&&` short-circuits.
  `validate_null_safety` does NOT currently enforce this — child refs
  do not inherit parent optionality — so ordering is the author's
  obligation. The test module demonstrates the hole; the refinement
  (inherit parent optionality) is recorded, not retrofitted into the
  committed AX11 module.
"""

from __future__ import annotations

from ax11_ast import Fragment, case, choice, port, retire, state_port, update
from ax11_fragment import (
    AUTHORITY,
    AUTHORIZED,
    CURRENT,
    PUBLICATION_STATE,
    RECOVERY_BASIS,
    REPLY_WORK,
    _authority,
    _intent,
    conversation_intents,
)
from ax11_predicates import Predicate, on
from ax14_compose import ComposedNet, compose, handoff_fragment
from ax14_fragments import change_concern

from hamsterdan.contracts.readiness import (
    ConversationPublicationRequest,
    ConversationPublicationState,
    DashboardPublicationRequest,
    DashboardPublicationState,
    ReadinessCommand,
    ReadinessPublicationState,
)

# -- ports the recovery concern adds (shared ones imported from AX11) --------

DASHBOARD_STATE = state_port("dashboard_publication_state", DashboardPublicationState)
READINESS_STATE = state_port("readiness_publication_state", ReadinessPublicationState)
DASHBOARD_WORK = port("work_dashboard", DashboardPublicationRequest)
READINESS_COMMAND = port("command_readiness", ReadinessCommand)

# -- predicates: production `_recoverable_publication`, specialized per target

#: The shared prelude: a current, authorized recover_publication intent
#: whose open-map arguments are present. The two `.present()` conjuncts
#: also *secure* every later map-key comparison (null-safety rule).
RECOVERY_INTENT: Predicate = (
    CURRENT
    & AUTHORIZED
    & (_intent.kind == "recover_publication")
    & _intent.arguments["target"].present()
    & _intent.arguments["operation"].present()
)


def _recoverable(target: str, state_root, prefix: str) -> Predicate:
    """One target's slice of `_recoverable_publication`: the concern is
    blocked, owns the operation named by the intent, and holds a parked
    recovery request minted under the *current* authority.

    Ordering obligation: `recovery.present()` must precede every nested
    `recovery.*` access — CEL `&&` short-circuit is what makes the
    nested reads safe, and validation cannot enforce this today.
    """
    blocked = getattr(state_root, f"{prefix}_capability_blocking")
    owned = getattr(state_root, f"{prefix}_operation")
    recovery = getattr(state_root, f"{prefix}_recovery")
    return (
        RECOVERY_INTENT
        & (_intent.arguments["target"] == target)
        & (blocked == True)
        & owned.present()
        & (_intent.arguments["operation"] == owned)
        & recovery.present()
        & (_intent.arguments["operation"] == recovery.operation)
        & (recovery.epoch == _authority.epoch)
        & (recovery.head == _authority.head)
        & (recovery.base_head == _authority.base_head)
        & (recovery.policy_digest == _authority.policy_digest)
    )


CONVERSATION_RECOVERABLE = _recoverable("conversation", on(ConversationPublicationState), "conversation")
DASHBOARD_RECOVERABLE = _recoverable("dashboard", on(DashboardPublicationState), "dashboard")
READINESS_RECOVERABLE = _recoverable("readiness", on(ReadinessPublicationState), "readiness")

# -- pure updates: production `_recover_publication`, one function per target


def recover_conversation(
    state: ConversationPublicationState,
) -> tuple[ConversationPublicationState, ConversationPublicationRequest]:
    request = state.conversation_recovery
    if request is None:
        raise ValueError("guard proved conversation_recovery present")
    return state.validated_update(conversation_capability_blocking=False), request


def recover_dashboard(
    state: DashboardPublicationState,
) -> tuple[DashboardPublicationState, DashboardPublicationRequest]:
    request = state.dashboard_recovery
    if request is None:
        raise ValueError("guard proved dashboard_recovery present")
    return state.validated_update(dashboard_capability_blocking=False), request


def recover_readiness(state: ReadinessPublicationState) -> tuple[ReadinessPublicationState, ReadinessCommand]:
    request = state.readiness_recovery
    if request is None:
        raise ValueError("guard proved readiness_recovery present")
    return state.validated_update(readiness_capability_blocking=False), request


# -- the concern: cases per target, complement retire generated --------------

RECOVERY_LANE_BODY = choice(
    case(
        when=CONVERSATION_RECOVERABLE,
        then=update(recover_conversation, state=PUBLICATION_STATE, emits=(REPLY_WORK,)),
    ),
    case(when=DASHBOARD_RECOVERABLE, then=update(recover_dashboard, state=DASHBOARD_STATE, emits=(DASHBOARD_WORK,))),
    case(when=READINESS_RECOVERABLE, then=update(recover_readiness, state=READINESS_STATE, emits=(READINESS_COMMAND,))),
    otherwise=retire(),  # production reject_recovery: the mechanical complement
)


def recovery_concern() -> Fragment:
    """The recovery concern as an independent value. Its composition
    surface: `recovery_basis` (hand-off from the base scatter),
    `authority` (shared read), `conversation_publication_state` (a state
    SHARED with the base's reply concern), and `work_conversation_reply`
    (an emit port shared with the base's `authorize_reply` — two
    producers, one place)."""
    return handoff_fragment(
        "recovery-intents",
        entry=RECOVERY_BASIS,
        reads=(AUTHORITY,),
        states=(PUBLICATION_STATE, DASHBOARD_STATE, READINESS_STATE),
        body=RECOVERY_LANE_BODY,
    )


def composed_full() -> ComposedNet:
    """Three concerns, one assembly point: the AX11 base untouched, the
    AX14 change concern, and the recovery concern."""
    return compose("conversation-intents-full", conversation_intents(), change_concern(), recovery_concern())
