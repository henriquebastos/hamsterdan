"""ES-004 AX7 focused tests — conversations never touch the head machine.

Claims under test:

- read_only intents are answered in EVERY control state, Terminal
  included — the orthogonality in its purest form.
- durable_note intents need a live instance, not a current head:
  serviced while Quiescent (draft, superseded, or awaiting our push).
- Only head_bound intents require Running, and only Execute carries an
  epoch/head stamp — where production stamps all twelve kinds.
- Nothing is ever parked: a head_bound request that cannot run gets an
  immediate explanatory Decline (attempt-first reply), dissolving
  AX6's Hold and its replay-or-expire open question.
- The grade table covers the full production intent vocabulary.
- service() is control-state-pure: it returns an outcome and never a
  new state.
"""

from __future__ import annotations

from ax6_quiescence import ConversationArrived, Hold, Quiescent, Running, Terminal, step
from ax7_conversations import GRADE, Answer, Apply, Decline, Execute, service

RUNNING = Running(epoch=3, head="h2")
DRAFT = Quiescent(3, "h2")
AWAITING = Quiescent(3, "h2", expected="commit-of-op-7")
MERGED = Terminal("merged", 3, "h2")

ALL_STATES = (RUNNING, DRAFT, AWAITING, MERGED)

# the production vocabulary, verbatim (contracts/readiness.py:421-434)
PRODUCTION_KINDS = {
    "reply",
    "status",
    "acknowledge",
    "dismiss",
    "defer",
    "snooze",
    "resume",
    "reassign",
    "change",
    "update_base",
    "resolve_conflict",
    "recover_publication",
}


# -- orthogonality: read_only works everywhere ------------------------------------------


def test_questions_are_answered_in_every_state_including_terminal():
    for state in ALL_STATES:
        assert service(state, "reply") == Answer("reply")
        assert service(state, "status") == Answer("status")


# -- durable notes: live instance, not current head --------------------------------------


def test_dispositions_apply_while_quiescent():
    """Dismissing a finding is about its lineage — which production
    already carries across generations — not about the head."""
    for state in (RUNNING, DRAFT, AWAITING):
        assert service(state, "dismiss") == Apply("dismiss")
        assert service(state, "snooze") == Apply("snooze")


def test_dispositions_decline_after_terminal():
    outcome = service(MERGED, "dismiss")
    assert outcome == Decline("dismiss", "the pull request is merged")


# -- head_bound: the only grade that enters the machine ----------------------------------


def test_change_executes_only_while_running_and_carries_its_authority():
    assert service(RUNNING, "change") == Execute("change", epoch=3, head="h2")


def test_change_while_quiescent_is_declined_with_a_specific_reason():
    draft = service(DRAFT, "change")
    assert isinstance(draft, Decline) and "draft or its head was superseded" in draft.reason
    awaiting = service(AWAITING, "change")
    assert isinstance(awaiting, Decline) and "awaits observation" in awaiting.reason


def test_change_after_terminal_is_declined():
    assert service(MERGED, "change") == Decline("change", "the pull request is merged")


# -- nothing is ever parked --------------------------------------------------------------


def test_no_outcome_is_a_hold_and_state_is_never_returned():
    """AX6's open question dissolves: every (state, kind) pair yields
    an immediate outcome; none is a Hold, none is a control state."""
    for state in ALL_STATES:
        for kind in PRODUCTION_KINDS:
            outcome = service(state, kind)
            assert isinstance(outcome, (Answer, Apply, Execute, Decline))


def test_only_execute_carries_an_authority_stamp():
    """Production stamps epoch/head on all 12 kinds; here exactly one
    grade needs it."""
    stamped = {
        kind
        for state in ALL_STATES
        for kind in PRODUCTION_KINDS
        if isinstance(service(state, kind), Execute)
    }
    assert stamped == {kind for kind, grade in GRADE.items() if grade == "head_bound"}


# -- coverage and the AX6 seam ------------------------------------------------------------


def test_grade_table_covers_the_full_production_vocabulary():
    assert set(GRADE) == PRODUCTION_KINDS


def test_ax6_hold_is_the_superseded_seam():
    """The AX6 machine parks a quiescent conversation because it only
    sees an opaque ConversationArrived. AX7 shows the event should
    never reach that machine: classification by grade routes it first,
    and only head_bound Execute enters. Recorded here as the exact
    seam AX7 supersedes."""
    state, actions = step(DRAFT, ConversationArrived())
    assert state == DRAFT and actions == (Hold(),)  # AX6, superseded by AX7 routing
