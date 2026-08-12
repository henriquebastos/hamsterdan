"""AX17 focused tests — evolving one durable history across compositions.

Every scenario runs real engines over one InMemoryHistoryStore: record
under one composition, resume under another, and observe what the
frozen resume door accepts, refuses, and silently permits.
"""

from __future__ import annotations

import pytest
from ax17_evolution import NET_NAME, full, narrow, renamed_full
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from test_ax11_fragment import (
    AUTHORITY_VALUE,
    REVIEW_SEED,
    classification_request,
    dispatch,
    drive_bounded,
    intent,
    place_data,
)
from test_ax15_recovery import parked_conversation, parked_dashboard, recover

from hamsterdan.contracts.readiness import (
    ConversationPublicationState,
    HumanState,
    MutationState,
)

# -- harness ------------------------------------------------------------------


def seed_marking(composed, request, *, cp=None, dp=None, rp=None) -> Marking:
    """Seed only the places this composition has; dp/rp only when given."""
    values = {
        "authority": AUTHORITY_VALUE,
        "review_state": REVIEW_SEED,
        "human_state": HumanState(),
        "conversation_publication_state": cp or ConversationPublicationState(),
        "mutation_state": MutationState(),
        "work_conversation": request,
    }
    if dp is not None:
        values["dashboard_publication_state"] = dp
    if rp is not None:
        values["readiness_publication_state"] = rp
    return Marking({composed.places[name]: (Token(type(v).__name__, v.dump()),) for name, v in values.items()})


def create(composed, request, history, *, cp=None, dp=None, rp=None, instance="ax17") -> Engine:
    engine = Engine.create(
        composed.built.net,
        instance,
        history=history,
        dispatch=dispatch(),
        marking=seed_marking(composed, request, cp=cp, dp=dp, rp=rp),
        handlers=dict(composed.handlers),
        guards=dict(composed.built.guards),
        activities=composed.activities,
    )
    drive_bounded(engine)
    return engine


def resume(composed, history, *, instance="ax17") -> Engine:
    return Engine.load(
        composed.built.net,
        instance,
        history=history,
        dispatch=dispatch(),
        handlers=dict(composed.handlers),
        guards=dict(composed.built.guards),
        activities=composed.activities,
    )


def data(engine: Engine, composed, name: str) -> list[dict]:
    return place_data(engine, str(composed.places[name]))


# -- rule 1: the net name is the instance's process identity --------------------


class TestNameIdentity:
    def test_resume_under_another_name_is_a_foreign_trace(self) -> None:
        history = InMemoryHistoryStore()
        create(narrow(), classification_request([intent("update_base")]), history)
        with pytest.raises(ValueError, match="foreign trace"):
            resume(renamed_full(), history)

    def test_the_name_carries_no_version(self) -> None:
        # Both compositions answer to the same name — versioning must live
        # outside it (NetUri, metadata, or the definition boundary).
        assert narrow().built.net.name == full().built.net.name == NET_NAME


# -- rule 2 and 3: superset resume; a parked hand-off feeds the new concern -----


class TestConcernAddition:
    def test_parked_handoff_token_is_consumed_by_the_added_concern(self) -> None:
        # Under the narrow net the recovery intent has NO consumer: the
        # scatter parks it on recovery_basis and it survives the run.
        history = InMemoryHistoryStore()
        request = classification_request([{**intent("update_base"), "blocking": True}, recover("conversation", "op-r")])
        old = create(narrow(), request, history, cp=parked_conversation("op-r"))
        old_composed = narrow()
        assert len(data(old, old_composed, "work_change")) == 1  # change processed
        [parked] = data(old, old_composed, "recovery_basis")
        assert parked["kind"] == "recover_publication"
        assert data(old, old_composed, "work_conversation_reply") == []

        # Evolution: same name, superset structure. Resume replays the
        # recorded live state onto the wider net...
        new_composed = full()
        resumed = resume(new_composed, history)
        for name in old_composed.places:
            assert data(resumed, new_composed, name) == data(old, old_composed, name)
        assert data(resumed, new_composed, "dashboard_publication_state") == []  # new places arrive empty

        # ...and driving lets the added concern consume the token that
        # parked before the concern existed. WAIT semantics plus
        # composition equals deferred capability.
        drive_bounded(resumed)
        assert data(resumed, new_composed, "recovery_basis") == []
        [reissued] = data(resumed, new_composed, "work_conversation_reply")
        assert reissued["operation"] == "op-r"
        [state] = data(resumed, new_composed, "conversation_publication_state")
        assert state["conversation_capability_blocking"] is False

    def test_replay_then_extension_is_one_load_not_two_steps(self) -> None:
        # The same evolution driven immediately: nothing about the old
        # history needs rewriting, migrating, or re-recording.
        history = InMemoryHistoryStore()
        create(
            narrow(), classification_request([recover("conversation", "op-r")]), history, cp=parked_conversation("op-r")
        )
        resumed = resume(full(), history)
        drive_bounded(resumed)
        composed = full()
        assert data(resumed, composed, "recovery_basis") == []


# -- rule 4: an unseeded state place starves the joined concern ------------------


class TestUnseededState:
    def test_dashboard_recovery_starves_without_its_state_token(self) -> None:
        # The dashboard case needs a DashboardPublicationState token that
        # no pre-evolution marking ever seeded — and the generated
        # `otherwise` retire reads ALL the concern's states, so it starves
        # too: the intent parks forever, visibly, on recovery_basis.
        history = InMemoryHistoryStore()
        create(narrow(), classification_request([recover("dashboard", "op-d")]), history)
        resumed = resume(full(), history)
        drive_bounded(resumed)
        composed = full()
        [parked] = data(resumed, composed, "recovery_basis")
        assert parked["arguments"]["target"] == "dashboard"
        assert data(resumed, composed, "work_dashboard") == []

    def test_minimal_guard_scope_decides_what_survives_evolution(self) -> None:
        # The asymmetry with TestConcernAddition is structural, not lucky:
        # the conversation case binds only places the narrow net already
        # had (authority, conversation state, the lane); the dashboard
        # case binds a place only the new concern brings. AX15's
        # per-target predicate specialization is what makes the first
        # recovery target evolution-safe with zero seeding.
        composed = full()
        narrow_places = {str(path) for path in narrow().places.values()}
        conversation_inputs = {str(a.source) for a in composed.built.net.inputs(NetPath("recover_conversation"))}
        assert conversation_inputs <= narrow_places
        dashboard_inputs = {str(a.source) for a in composed.built.net.inputs(NetPath("recover_dashboard"))}
        assert not dashboard_inputs <= narrow_places


# -- rule 5: narrowing audits live state only -------------------------------------


class TestConcernRemoval:
    def test_live_tokens_on_removed_places_refuse_the_narrow_net(self) -> None:
        history = InMemoryHistoryStore()
        request = classification_request([recover("conversation", "op-r")])
        create(full(), request, history, cp=parked_conversation("op-r"), dp=parked_dashboard("op-d"))
        with pytest.raises(ValueError, match="not a place of this net"):
            resume(narrow(), history)

    def test_ended_firings_of_removed_transitions_resume_silently(self) -> None:
        # The full run fires recover_conversation — a transition the
        # narrow net does not have — but leaves no live state on any
        # removed node (dp/rp were never seeded; the conversation case
        # reads neither). The narrow resume SUCCEEDS: the door audits
        # live state, not the trace. Whole-trace validation is a separate
        # layer by Petrus's own design; concern removal therefore needs a
        # deliberate check above the resume door, not silence.
        history = InMemoryHistoryStore()
        request = classification_request([recover("conversation", "op-r")])
        old_composed = full()
        old = create(old_composed, request, history, cp=parked_conversation("op-r"))
        [reissued] = data(old, old_composed, "work_conversation_reply")
        assert reissued["operation"] == "op-r"  # the removed-in-narrow transition really fired

        narrow_composed = narrow()
        resumed = resume(narrow_composed, history)
        for name in narrow_composed.places:
            assert data(resumed, narrow_composed, name) == data(old, old_composed, name)
