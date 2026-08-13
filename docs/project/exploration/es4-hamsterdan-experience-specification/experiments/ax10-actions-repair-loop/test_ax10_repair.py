"""ES-004 AX10 focused tests — the rerun → repair escalation ladder.

Claims under test:

- GitHub's attempt counter is the loop variable: first failure wants
  one rerun; a second failure of the same run is a reproduction; a
  post-rerun success is flaky-green. No rerun_requested/rerun_attempt
  flags.
- The fold's monotonic fence makes duplicate, stale-attempt, and
  stale-generation observations inert — replacing the actions_basis
  place, the basis_retire transition, and its three read arcs.
- The ladder is structurally bounded: one rerun operation and at most
  one repair operation per generation; the same fingerprint is never
  repaired twice, even across confirmed resumes (lineage carried).
- Repair outcomes route the control layer: ok → Quiesce(expected=
  provisional_head); CAS moved → discard and Quiesce(expected=None);
  agent failure → the human rung, generation still running.
- Replay is a refold: no clock, no coroutine, values only.
"""

from __future__ import annotations

from ax10_repair import (
    Actions,
    ActionsObserved,
    Quiesce,
    RepairSettled,
    RepairWork,
    RerunWork,
    control_move,
    decide,
    fold,
    needs_human,
    resume,
)

START = Actions(epoch=3, head="h2")


def obs(attempt: int, conclusion: str, fingerprint: str = "", run: str = "run-9") -> ActionsObserved:
    return ActionsObserved(3, "h2", run, attempt, conclusion, fingerprint)


def reproduced(base: Actions = START) -> Actions:
    state = fold(base, obs(1, "failure", "fp-A"))
    return fold(state, obs(2, "failure", "fp-A"))


# -- the ladder's rungs -------------------------------------------------------------------


def test_green_run_never_enters_the_loop():
    state = fold(START, obs(1, "success"))
    assert state.phase == "green" and decide(state) == ()


def test_first_failure_wants_exactly_one_rerun():
    state = fold(START, obs(1, "failure", "fp-A"))
    assert decide(state) == (RerunWork("actions-rerun:3:h2:run-9:1"),)
    assert decide(state) == decide(state)  # identity dedups, no flag


def test_rerun_success_exits_the_loop_as_flaky_green():
    state = fold(fold(START, obs(1, "failure", "fp-A")), obs(2, "success"))
    assert state.phase == "flaky_green" and decide(state) == ()


def test_reproduced_failure_wants_exactly_one_repair():
    state = reproduced()
    assert decide(state) == (RepairWork("repair:3:h2:fp-A", "fp-A"),)
    assert not needs_human(state)


def test_progress_conclusions_evolve_within_one_attempt():
    state = START
    for conclusion in ("queued", "in_progress"):
        state = fold(state, obs(1, conclusion))
        assert state.phase == "running"
    assert fold(state, obs(1, "failure", "fp-A")).phase == "failed"


def test_non_retryable_conclusion_exits_without_rerun():
    state = fold(START, obs(1, "canceled"))
    assert state.phase == "halted:canceled" and decide(state) == ()


# -- the monotonic fence replaces the basis place -------------------------------------------


def test_duplicate_and_stale_observations_are_inert():
    state = reproduced()
    assert fold(state, obs(2, "failure", "fp-A")) == state  # duplicate delivery
    assert fold(state, obs(1, "failure", "fp-A")) == state  # stale attempt
    assert fold(state, ActionsObserved(2, "h1", "run-9", 3, "failure", "fp-B")) == state  # stale generation


# -- the budget fences: once per fingerprint, once per lineage --------------------------------


def test_same_fingerprint_is_never_repaired_twice():
    state = reproduced(Actions(epoch=3, head="h2", repair_fingerprint="fp-A"))
    assert decide(state) == () and needs_human(state)


def test_repair_budget_is_burned_for_the_whole_lineage():
    state = reproduced(Actions(epoch=3, head="h2", repair_used=True))
    assert decide(state) == () and needs_human(state)  # even though fp-A is new


def test_lineage_survives_a_confirmed_resume():
    settled = fold(reproduced(), RepairSettled(3, "h2", "repair:3:h2:fp-A", ok=True, provisional_head="h3"))
    fresh = resume(settled, epoch=4, head="h3")
    assert (fresh.repair_used, fresh.repair_fingerprint) == (True, "fp-A")
    again = fold(fold(fresh, ActionsObserved(4, "h3", "run-10", 1, "failure", "fp-A")),
                 ActionsObserved(4, "h3", "run-10", 2, "failure", "fp-A"))
    assert decide(again) == () and needs_human(again)  # the repair did not fix it: human


# -- repair outcomes route the control layer ---------------------------------------------------


def test_successful_repair_quiesces_expecting_our_head():
    settled = fold(reproduced(), RepairSettled(3, "h2", "repair:3:h2:fp-A", ok=True, provisional_head="h3"))
    assert settled.phase == "awaiting_confirm"
    assert control_move(settled) == Quiesce(expected="h3")
    assert decide(settled) == ()
    # the generation is over: late observations are inert
    assert fold(settled, obs(3, "failure", "fp-B")) == settled


def test_cas_moved_discards_and_waits_for_the_new_head():
    settled = fold(reproduced(), RepairSettled(3, "h2", "repair:3:h2:fp-A", ok=False, category="cas_moved"))
    assert settled.phase == "discarded"
    assert control_move(settled) == Quiesce(expected=None)
    assert settled.repair_used  # production parity; refund is the named OPEN


def test_agent_failure_reaches_the_human_rung_with_the_generation_running():
    settled = fold(reproduced(), RepairSettled(3, "h2", "repair:3:h2:fp-A", ok=False))
    assert settled.phase == "repair_faulted" and needs_human(settled)
    assert control_move(settled) is None  # still Running: dashboard shows the escalation


def test_foreign_or_mistimed_repair_results_are_inert():
    state = reproduced()
    assert fold(state, RepairSettled(3, "h2", "repair:3:h2:fp-OTHER", ok=True)) == state  # wrong operation
    early = fold(START, obs(1, "failure", "fp-A"))
    assert fold(early, RepairSettled(3, "h2", "repair:3:h2:fp-A", ok=True)) == early  # wrong phase


# -- boundedness and replay ---------------------------------------------------------------------


def test_worst_case_ladder_emits_exactly_two_operations():
    operations, state = set(), START
    events = [
        obs(1, "failure", "fp-A"),
        obs(1, "failure", "fp-A"),  # duplicate
        obs(2, "failure", "fp-A"),
        RepairSettled(3, "h2", "repair:3:h2:fp-A", ok=False),  # agent fault
        obs(2, "failure", "fp-A"),  # duplicate after fault
    ]
    for event in events:
        state = fold(state, event)
        operations.update(work.operation for work in decide(state))
    assert operations == {"actions-rerun:3:h2:run-9:1", "repair:3:h2:fp-A"}
    assert needs_human(state)  # the ladder ends at the human, never cycles


def test_replay_is_a_refold():
    events = [
        obs(1, "failure", "fp-A"),
        obs(2, "failure", "fp-A"),
        RepairSettled(3, "h2", "repair:3:h2:fp-A", ok=True, provisional_head="h3"),
    ]

    def run():
        state = START
        return [(state := fold(state, event), decide(state), control_move(state)) for event in events]

    assert run() == run()
