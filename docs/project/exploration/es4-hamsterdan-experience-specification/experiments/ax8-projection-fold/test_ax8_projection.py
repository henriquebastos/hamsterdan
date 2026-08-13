"""ES-004 AX8 focused tests — the projection is a fold, not a join.

Claims under test:

- The fold replaces 25 read arcs: every input the three join
  transitions read arrives as a typed subnet exit, and the derived
  decisions are pure functions of the folded value.
- Fold order does not matter across independent concerns
  (commutativity), so no arrival-order coupling replaces the join.
- The dashboard republishes exactly on projection drift and settles
  once acknowledged — production's `dashboard_requested` flag
  replaced by operation identity.
- Announcement happens once per generation basis: identical folded
  state emits an identical operation (gate dedups lookup-first);
  a post-announce regression flips readiness off; a fresh AX6 resume
  announces again without any reset logic.
- The in-flight guards of `workflow_gates_ready` have no counterpart:
  while work is in flight its exit simply has not folded, and while
  Quiescent no decisions run at all.
"""

from __future__ import annotations

from ax8_projection import (
    ActionsSettled,
    AnnouncementAcknowledged,
    AnnounceWork,
    DashboardAcknowledged,
    DashboardWork,
    FindingsPublished,
    HumanSettled,
    ReviewSettled,
    Snapshot,
    decide,
    fold,
    is_ready,
    projection,
    wants_dashboard,
)

START = Snapshot(epoch=3, head="h2")

GREEN_EXITS = (
    ActionsSettled("green"),
    ReviewSettled("clear", 0),
    FindingsPublished(),
    HumanSettled(approved=True, changes_requested=False, unresolved_conversations=0),
)


def folded(*exits, base=START):
    snapshot = base
    for exit_value in exits:
        snapshot = fold(snapshot, exit_value)
    return snapshot


# -- the fold replaces the join ------------------------------------------------------------


def test_fold_is_commutative_across_independent_concerns():
    import itertools

    orders = {folded(*order) for order in itertools.permutations(GREEN_EXITS)}
    assert len(orders) == 1  # any arrival order, one truth


def test_nothing_is_ready_until_every_gate_has_folded():
    for cut in range(len(GREEN_EXITS)):
        partial = folded(*GREEN_EXITS[:cut])
        assert not is_ready(partial)


# -- dashboard: drift in, acknowledgment out --------------------------------------------------


def test_dashboard_requested_on_drift_and_settled_on_ack():
    snapshot = folded(*GREEN_EXITS)
    [dashboard, *_] = decide(snapshot)
    assert isinstance(dashboard, DashboardWork)
    settled = fold(snapshot, DashboardAcknowledged(dashboard.projection))
    assert not wants_dashboard(settled)
    # a new blocking finding drifts the projection again:
    regressed = fold(settled, ReviewSettled("blocking", 1))
    assert wants_dashboard(regressed)
    assert projection(regressed) != dashboard.projection


def test_same_state_emits_the_same_operation_not_a_flag():
    """Production dedups with dashboard_requested/readiness_requested
    flags; here identical folded state can only emit identical
    operation ids — the AX3 gate absorbs the replay lookup-first."""
    snapshot = folded(*GREEN_EXITS)
    assert decide(snapshot) == decide(snapshot)
    [work, *_] = decide(snapshot)
    assert work.operation == f"dashboard:3:h2:{projection(snapshot)}"


# -- announcement: once per basis, no reset machinery -------------------------------------------


def announced_green():
    snapshot = folded(*GREEN_EXITS)
    [dashboard] = [w for w in decide(snapshot) if isinstance(w, DashboardWork)]
    snapshot = fold(snapshot, DashboardAcknowledged(dashboard.projection))
    [announce] = decide(snapshot)
    assert isinstance(announce, AnnounceWork)
    return fold(snapshot, AnnouncementAcknowledged())


def test_ready_only_when_dashboard_is_current_then_announce_once():
    snapshot = folded(*GREEN_EXITS)
    assert not is_ready(snapshot)  # gates hold but the dashboard is stale
    done = announced_green()
    assert decide(done) == ()  # announced: nothing more to emit


def test_regression_after_announce_flips_ready_off_and_updates_dashboard():
    regressed = fold(announced_green(), ActionsSettled("failed"))
    assert not is_ready(regressed)
    work = decide(regressed)
    assert any(isinstance(w, DashboardWork) for w in work)  # the red dashboard still publishes
    assert not any(isinstance(w, AnnounceWork) for w in work)


def test_fresh_generation_announces_again_without_reset_logic():
    """Production resets `announced` by rebuilding the cohort at
    generation start; here the AX6 resume simply starts a fresh
    Snapshot(epoch+1) — announced is not carried, so nothing resets."""
    next_generation = Snapshot(epoch=4, head="h3")
    snapshot = folded(*GREEN_EXITS, base=next_generation)
    [dashboard] = [w for w in decide(snapshot) if isinstance(w, DashboardWork)]
    snapshot = fold(snapshot, DashboardAcknowledged(dashboard.projection))
    assert any(isinstance(w, AnnounceWork) for w in decide(snapshot))


# -- the in-flight guards have nothing left to guard ---------------------------------------------


def test_in_flight_work_is_simply_an_unfolded_exit():
    """During a repair, production guards readiness with
    repair_in_flight. Here the actions exit that a repair will
    eventually produce has not folded yet — actions is still
    'failed' — so readiness is already false with no flag."""
    failing = folded(
        ActionsSettled("failed"),
        ReviewSettled("clear", 0),
        FindingsPublished(),
        HumanSettled(approved=True, changes_requested=False, unresolved_conversations=0),
    )
    assert not is_ready(failing)  # while the repair runs, nothing to suppress
    repaired = fold(failing, ActionsSettled("green"))  # the repair's eventual exit
    [dashboard] = [w for w in decide(repaired) if isinstance(w, DashboardWork)]
    assert is_ready(fold(repaired, DashboardAcknowledged(dashboard.projection)))
