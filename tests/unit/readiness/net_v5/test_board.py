"""The board spec: what a human must learn from the summary comment.

The rendered board answers exactly three questions, in order: can this
merge (the verdict line), who acts next (named in the verdict), and
which head the answer refers to (the short sha in the verdict). Latest
fact per concern wins; transient CI states fold away; the readiness
announcement belongs to the advisory comment — an all-clear board only
points at it. Each boundary state below is one scenario a reader can
actually be in.
"""

from __future__ import annotations

from hamsterdan.readiness.net_v5.board import render_board

HEAD = "3ff7d1067d8437340e39d2ad38c06ab4631a7c4f"
BASE = "a83e9223f7ffc6b0af919b0b8261fa2578261b41"
POLICY = "196b38f86f32afff0e606bcb9a3e36647bc0bdd1b82a3818fe412c38a2ccc25b"


def state(**overrides) -> str:
    body = {
        "phase": "running",
        "head": HEAD,
        "base": BASE,
        "mergeable": True,
        "policy": POLICY,
        "strict_base": True,
        "base_current": True,
    }
    body.update(overrides)
    return f"state:{body}"


def human(approval: bool = False, changes_requested: bool = False, unresolved: int = 0) -> str:
    return f"human:{ {'approval': approval, 'changes_requested': changes_requested, 'unresolved': unresolved} }"


def checks(status: str) -> str:
    return f"checks:{ {'status': status} }"


def row(board: str, gate: str) -> str:
    [line] = [line for line in board.splitlines() if line.startswith(f"| {gate} |")]
    return line


class TestVerdictBoundaries:
    """Every boundary state leads with the decision and the next actor."""

    def test_a_just_opened_pr_shows_nothing_started_and_no_actor(self) -> None:
        board = render_board([state()])
        assert f"⏳ waiting on CI for `{HEAD[:7]}`" in board
        assert "Nothing for you to do" in board
        assert row(board, "CI checks") == "| CI checks | ⏳ not started |"

    def test_running_ci_folds_transient_states_into_one_waiting_row(self) -> None:
        board = render_board([state(), human(), checks("pending"), checks("queued"), checks("in_progress")])
        assert "⏳ waiting on CI" in board
        assert row(board, "CI checks") == "| CI checks | ⏳ in progress |"
        assert "queued" not in board

    def test_a_ci_failure_names_the_author_as_next_actor(self) -> None:
        board = render_board([state(), checks("failure")])
        assert f"❌ CI failed for `{HEAD[:7]}`" in board
        assert "**Author:**" in board
        assert row(board, "CI checks") == "| CI checks | ❌ failing |"

    def test_blocking_findings_outrank_green_checks(self) -> None:
        entries = [
            state(),
            checks("success"),
            f"findings:{ {'head': HEAD, 'blocking': 2, 'count': 3} }",
            f"review:{ {'head': HEAD, 'status': 'blocking'} }",
        ]
        board = render_board(entries)
        assert "❌ 2 blocking finding(s) of 3" in board
        assert row(board, "Dan's review") == "| Dan's review | ❌ blocking · 2 blocking of 3 finding(s) |"

    def test_requested_changes_hand_the_turn_to_the_author(self) -> None:
        board = render_board([state(), checks("success"), human(changes_requested=True, unresolved=2)])
        assert "waiting on author — a reviewer requested changes" in board
        assert row(board, "Human review") == "| Human review | ❌ changes requested · 2 unresolved thread(s) |"

    def test_unresolved_threads_alone_wait_on_humans(self) -> None:
        board = render_board([state(), checks("success"), human(approval=True, unresolved=1)])
        assert "waiting on humans — 1 unresolved review thread(s)" in board

    def test_a_stale_base_asks_the_author_to_update_the_branch(self) -> None:
        board = render_board([state(base_current=False), checks("success")])
        assert f"⚠️ base is stale — the target branch moved past `{BASE[:7]}`" in board
        assert row(board, "Base") == f"| Base | ⚠️ behind `{BASE[:7]}` |"

    def test_a_merge_conflict_asks_the_author_to_resolve(self) -> None:
        board = render_board([state(mergeable=False), checks("success")])
        assert "❌ merge conflict" in board
        assert row(board, "Conflicts") == "| Conflicts | ❌ merge conflict |"

    def test_all_clear_points_at_the_advisory_and_never_announces(self) -> None:
        entries = [
            state(),
            human(approval=True),
            checks("success"),
            f"findings:{ {'head': HEAD, 'blocking': 0, 'count': 0} }",
            f"review:{ {'head': HEAD, 'status': 'clear'} }",
            f"announced:{ {'head': HEAD} }",
        ]
        board = render_board(entries)
        assert f"✅ all gates clear for `{HEAD[:7]}` — see the readiness advisory. Merging stays yours." in board
        assert "ready" not in board.casefold().replace("readiness advisory", "")
        assert row(board, "Dan's review") == "| Dan's review | ✅ clear · 0 findings |"

    def test_a_draft_pr_reads_paused(self) -> None:
        board = render_board([state(phase="quiescent")])
        assert "paused — draft PR" in board

    def test_a_closed_pr_reads_frozen(self) -> None:
        board = render_board([state(phase="terminal")])
        assert "closed — this board is frozen." in board


class TestAttentionStates:
    """Faults, exhausted escalation, and pushes in flight are the states
    where silence would strand the PR: the board must say how to act."""

    def test_a_raised_fault_offers_the_recovery_ask(self) -> None:
        entries = [state(), f"fault:{ {'where': 'review', 'op': 'op-1', 'status': 'faulted', 'reason': 'timeout'} }"]
        board = render_board(entries)
        assert "⚠️ needs attention — operation `op-1` faulted: timeout" in board
        assert "ask me to recover it" in board.casefold()

    def test_a_cleared_fault_leaves_no_attention_row(self) -> None:
        entries = [
            state(),
            f"fault:{ {'where': 'review', 'op': 'op-1', 'status': 'faulted', 'reason': 'timeout'} }",
            f"fault:{ {'where': 'review', 'op': 'op-1', 'status': 'resolved'} }",
        ]
        assert "faulted" not in render_board(entries)

    def test_exhausted_reruns_escalate_to_a_human(self) -> None:
        entries = [state(), checks("failure"), f"human_needed:{ {'fingerprint': 'deadbeef99', 'head': HEAD} }"]
        board = render_board(entries)
        assert "**A human needs to look.**" in board

    def test_fresh_ci_evidence_retires_the_escalation(self) -> None:
        entries = [
            state(),
            checks("failure"),
            f"human_needed:{ {'fingerprint': 'deadbeef99', 'head': HEAD} }",
            checks("success"),
        ]
        assert "human needs to look" not in render_board(entries)

    def test_a_push_in_flight_reads_working(self) -> None:
        entries = [state(), f"mutation_pending:{ {'op': 'repair', 'op_key': 'k1'} }"]
        board = render_board(entries)
        assert "🔧 working — I'm pushing an update" in board

    def test_a_settled_push_clears_the_working_state(self) -> None:
        entries = [
            state(),
            f"mutation_pending:{ {'op': 'repair', 'op_key': 'k1'} }",
            f"mutation_settled:{ {'op': 'repair', 'op_key': 'k1'} }",
        ]
        assert "pushing an update" not in render_board(entries)

    def test_an_unparseable_entry_surfaces_instead_of_wedging_the_board(self) -> None:
        board = render_board([state(), "garbage-without-structure"])
        assert "⚠️ unrecognized: `garbage-without-structure`" in board
        assert "| CI checks |" in board
