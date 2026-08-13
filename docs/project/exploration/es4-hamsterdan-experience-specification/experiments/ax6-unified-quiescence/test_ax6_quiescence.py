"""ES-004 AX6 focused tests — every AX0-verified lifecycle scenario,
plus the three unifications, through ONE transition function.

Claims under test:

- All AX0 lifecycle scenarios (draft dormancy, resume at epoch+1,
  supersession, close/merge terminality) hold unchanged.
- Provisional head is expressible as Quiescent(expected=...) with
  confirmed-relation resume — no separate MutationState machinery.
- A CAS 'moved' exit can quiesce the instance BEFORE the webhook —
  early discard, impossible in today's model.
- Terminal absorbs; quiescent conversations are held, not
  reinterpreted; stale-ordered webhooks during expectation are inert.
"""

from __future__ import annotations

from ax6_quiescence import (
    CommitGateFired,
    admit,
    ConversationArrived,
    Drain,
    Hold,
    Ignore,
    ObservedClosed,
    ObservedOpen,
    Quiescent,
    Resume,
    Running,
    StaleSignal,
    Terminal,
    step,
)

RUN = Running(epoch=3, head="h2")


# -- AX0 scenarios, unchanged ----------------------------------------------------------


def test_draft_quiesces_and_nondraft_resumes_at_epoch_plus_one():
    quiet, actions = step(RUN, ObservedOpen("h2", draft=True))
    assert quiet == Quiescent(3, "h2")
    assert actions == (Drain(),)
    resumed, actions = step(quiet, ObservedOpen("h2", draft=False))
    assert resumed == Running(4, "h2")
    assert actions == (Resume(4, "h2", "resumed"),)


def test_supersession_is_quiesce_plus_resume_in_one_step():
    state, actions = step(RUN, ObservedOpen("h3"))
    assert state == Running(4, "h3")
    assert actions == (Drain(), Resume(4, "h3", "superseded"))


def test_same_head_observation_stays_in_generation():
    assert step(RUN, ObservedOpen("h2")) == (RUN, (Ignore(),))


def test_close_and_merge_are_terminal_from_any_live_state():
    assert step(RUN, ObservedClosed(merged=True))[0] == Terminal("merged", 3, "h2")
    quiet = Quiescent(3, "h2")
    assert step(quiet, ObservedClosed(merged=False))[0] == Terminal("closed", 3, "h2")


def test_terminal_absorbs_everything():
    dead = Terminal("merged", 3, "h2")
    for event in (ObservedOpen("h9"), CommitGateFired("h9"), StaleSignal(), ConversationArrived()):
        assert step(dead, event) == (dead, (Ignore(),))


# -- unification 1: provisional head is an expectation --------------------------------


def test_commit_gate_quiesces_with_expectation():
    quiet, actions = step(RUN, CommitGateFired("commit-of-op-7"))
    assert quiet == Quiescent(3, "h2", expected="commit-of-op-7")
    assert actions == (Drain(),)  # effects frozen because nothing is running


def test_observing_our_own_commit_confirms_lineage():
    quiet = Quiescent(3, "h2", expected="commit-of-op-7")
    state, actions = step(quiet, ObservedOpen("commit-of-op-7"))
    assert state == Running(4, "commit-of-op-7")
    assert actions == (Resume(4, "commit-of-op-7", "confirmed"),)


def test_someone_elses_push_during_expectation_supersedes():
    quiet = Quiescent(3, "h2", expected="commit-of-op-7")
    state, actions = step(quiet, ObservedOpen("h3-rival"))
    assert state == Running(4, "h3-rival")
    assert actions == (Resume(4, "h3-rival", "superseded"),)  # lineage NOT preserved


def test_stale_ordered_webhook_during_expectation_is_inert():
    """A webhook still reporting the pre-push head must not resume us
    onto our own past."""
    quiet = Quiescent(3, "h2", expected="commit-of-op-7")
    assert step(quiet, ObservedOpen("h2")) == (quiet, (Ignore(),))


# -- unification 2: early discard on known staleness -----------------------------------


def test_cas_moved_exit_quiesces_before_any_webhook():
    quiet, actions = step(RUN, StaleSignal())
    assert quiet == Quiescent(3, "h2")
    assert actions == (Drain(),)
    # ...and the eventual webhook resumes normally:
    state, actions = step(quiet, ObservedOpen("h3-their-push"))
    assert state == Running(4, "h3-their-push")
    assert actions == (Resume(4, "h3-their-push", "superseded"),)


# -- quiescent ingress discipline -------------------------------------------------------


def test_quiescent_conversation_is_held_not_reinterpreted():
    quiet = Quiescent(3, "h2")
    assert step(quiet, ConversationArrived()) == (quiet, (Hold(),))


def test_late_terminals_of_drained_work_change_nothing():
    quiet = Quiescent(3, "h2")
    for event in (CommitGateFired("ghost"), StaleSignal()):
        assert step(quiet, event) == (quiet, (Ignore(),))


def test_draft_observation_while_quiescent_stays_quiescent():
    quiet = Quiescent(3, "h2")
    assert step(quiet, ObservedOpen("h5", draft=True)) == (quiet, (Ignore(),))


# -- unification 3: born-draft PRs enter the same machine -------------------------------


def test_born_draft_pr_is_admitted_as_quiescent():
    assert admit(ObservedOpen("h1", draft=True)) == (Quiescent(0, "h1"), ())


def test_born_draft_pr_marked_ready_resumes_like_any_quiescent_instance():
    quiet, _ = admit(ObservedOpen("h1", draft=True))
    state, actions = step(quiet, ObservedOpen("h1", draft=False))
    assert state == Running(1, "h1")
    assert actions == (Resume(1, "h1", "resumed"),)


def test_born_ready_pr_is_the_only_new_relation():
    assert admit(ObservedOpen("h1")) == (Running(1, "h1"), (Resume(1, "h1", "new"),))


def test_closed_pr_is_never_admitted():
    assert admit(ObservedClosed(merged=True)) is None


# -- liveness: waiting only when the next authority is unknown --------------------------


def test_quiesce_never_waits_when_newer_authority_is_already_in_hand():
    """The two staleness discoveries differ ONLY in what we know:

    - supersession (webhook carried the new head): quiesce + resume in
      the same step — no waiting, no lost liveness;
    - CAS 'moved' (we know the world changed but not to what): quiesce
      and wait for ingress — there is nothing to resume onto yet.
    """
    _, on_supersession = step(RUN, ObservedOpen("h3"))
    assert any(isinstance(action, Resume) for action in on_supersession)
    _, on_cas_moved = step(RUN, StaleSignal())
    assert not any(isinstance(action, Resume) for action in on_cas_moved)
