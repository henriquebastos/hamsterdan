"""ES-004 AX12 focused tests — human observation folding.

Claims under test:

- HumanObserved is a full snapshot: last-write-wins, so order WITHIN
  the concern matters by design (AX8's commutativity caveat made
  concrete), while refold stays deterministic.
- Notes layer over snapshots with production's exact asymmetry:
  snooze survives the next observation; a reassignment is clobbered
  by it (topology.py:359) — mirrored, and flagged OPEN, not fixed.
- Capability blocking folds as a provider fact and clears on the
  next available observation.
- Dispositions rewrite findings and recompute blocking verbatim:
  dismissing the only blocking finding clears the review; an
  "unable" review is never upgraded; unauthorized intents are inert.
- The concern exits bridge into AX8's snapshot unchanged.
"""

from __future__ import annotations

from ax12_human import (
    Disposed,
    Finding,
    Human,
    HumanObserved,
    HumanSettled,
    Noted,
    Review,
    fold_disposition,
    fold_human,
    review_settled,
    settled,
)

APPROVED = HumanObserved(approved=True, reviewer="alice", author="bob")
CHANGES = HumanObserved(changes_requested=True, reviewer="alice", author="bob")


def folded(*events, base=Human()):
    state = base
    for event in events:
        state = fold_human(state, event)
    return state


# -- snapshots: last-write-wins, order is the concern's own ------------------------------------


def test_observation_replaces_the_whole_surface():
    state = folded(APPROVED, CHANGES)
    assert (state.approved, state.changes_requested) == (False, True)
    assert state.observation_sequence == 2


def test_order_within_the_concern_matters_by_design():
    """AX8's commutativity is ACROSS concerns only; within one concern
    the log's order is the truth — and refolding the same order is
    deterministic."""
    assert folded(APPROVED, CHANGES) != folded(CHANGES, APPROVED)
    assert folded(APPROVED, CHANGES) == folded(APPROVED, CHANGES)


# -- notes over snapshots: production's exact asymmetry -----------------------------------------


def test_snooze_survives_the_next_observation():
    state = folded(Noted("snooze"), APPROVED)
    assert state.snoozed and state.approved


def test_reassignment_is_clobbered_by_the_next_observation():
    """Production parity (topology.py:359): fold_human writes
    reminder_recipient from the observation's reviewer, so a human's
    reassignment silently lasts only until GitHub next reports the
    PR. Mirrored here; flagged OPEN in the experiment doc."""
    state = folded(Noted("reassign", "carol"), APPROVED)
    assert state.reviewer == "alice"  # carol is gone


def test_resume_reverses_snooze_and_unknown_notes_are_inert():
    assert not folded(Noted("snooze"), Noted("resume")).snoozed
    assert folded(Noted("escalate")) == Human()


# -- capability: a provider fact, not a flag place -----------------------------------------------


def test_capability_blocks_and_clears_with_observations():
    blocked = folded(HumanObserved(capability_available=False))
    assert blocked.capability_blocking
    assert not folded(HumanObserved(capability_available=False), APPROVED).capability_blocking


# -- dispositions: fold_intent for ReviewState, verbatim ------------------------------------------


BLOCKING_REVIEW = Review(
    status="blocking",
    findings=(Finding("f1", blocking=True), Finding("f2", blocking=False)),
)


def test_dismissing_the_only_blocking_finding_clears_the_review():
    cleared = fold_disposition(BLOCKING_REVIEW, Disposed("dismiss", frozenset({"f1"})))
    assert cleared.status == "clear"
    assert review_settled(cleared) == ("clear", 0)


def test_disposing_a_nonblocking_finding_changes_nothing_that_gates():
    still = fold_disposition(BLOCKING_REVIEW, Disposed("acknowledge", frozenset({"f2"})))
    assert still.status == "blocking"
    assert review_settled(still) == ("blocking", 1)


def test_unable_review_is_never_upgraded_by_dispositions():
    unable = Review(status="unable", findings=(Finding("f1", blocking=True),))
    assert fold_disposition(unable, Disposed("dismiss", frozenset({"f1"}))).status == "unable"


def test_unauthorized_intents_are_inert():
    assert fold_disposition(BLOCKING_REVIEW, Disposed("dismiss", frozenset({"f1"}), authorized=False)) == BLOCKING_REVIEW


def test_duplicate_dispositions_are_idempotent():
    once = fold_disposition(BLOCKING_REVIEW, Disposed("defer", frozenset({"f1"})))
    assert fold_disposition(once, Disposed("defer", frozenset({"f1"}))) == once


# -- the bridges into AX8 --------------------------------------------------------------------------


def test_concern_exits_feed_ax8_unchanged():
    state = folded(HumanObserved(approved=True, unresolved_conversations=2))
    assert settled(state) == HumanSettled(approved=True, changes_requested=False, unresolved_conversations=2)
