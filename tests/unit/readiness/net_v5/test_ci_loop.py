"""Executable contract tests for the V5 CI loop.

CI is pure observation: it owns the CiState baton, adopts each admitted
head with a budget lineage, keeps only the newest exact-head run
verdict, mails ChecksFailure facts to escalation, and answers
escalation MOVED echoes by reissuing under a fresher authority or
parking until the refresh folds (order-independence). No guards, no
read arcs — every decision is a pure fold on token data.

Echo timelines drive the REAL internal path: a failure escalates to the
rerun gate, the gate is HELD in flight while the world (or the net)
moves, and the released gate classifies MOVED — escalation's fold then
echoes the attempted tuple back into ci.echo.
"""

from harness import (
    deliver,
    deliver_held,
    one,
    release_one,
    see_head,
    see_run,
    spawn,
    spawn_held,
    tokens,
    world_of,
)

HOLD = frozenset({"rerun_gate"})


def failures(engine) -> list[dict]:
    return tokens(engine, "esc.failures")


def held_failure(head: str = "h1", base: str = "b1", policy: str = "p1"):
    """A failing head whose rerun escalation is HELD in flight."""
    engine, _, dispatch, definitions = spawn_held()
    deliver_held(
        engine,
        dispatch,
        definitions,
        "on_head",
        "HeadSeen",
        {"head": head, "base": base, "mergeable": True, "policy": policy},
        hold=HOLD,
    )
    deliver_held(
        engine,
        dispatch,
        definitions,
        "on_runs",
        "RunSeen",
        {"head": head, "run_id": 1, "attempt": 1, "conclusion": "failure", "fingerprint": "fp1"},
        hold=HOLD,
    )
    return engine, dispatch, definitions


class TestCiAdmission:
    def test_first_head_seeds_pending_with_fresh_lineage(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        state = one(engine, "ci.state")
        assert state["head"] == "h1"
        assert state["lineage"] == "L1"
        assert state["status"] == "pending"
        assert state["best"] == []
        facts = [f for f in tokens(engine, "ready.facts") if f["kind"] == "checks"]
        assert facts[-1]["body"]["status"] == "pending"

    def test_superseded_head_resets_evidence_and_budget_lineage(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        see_head(engine, "h2")
        state = one(engine, "ci.state")
        assert state["head"] == "h2"
        assert state["lineage"] == "L2"
        assert state["status"] == "pending"
        assert state["best"] == []
        assert state["fingerprint"] == ""

    def test_resume_keeps_the_budget_lineage(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_draft", "DraftSeen", {})
        deliver(engine, "on_ready", "ReadySeen", {})
        state = one(engine, "ci.state")
        assert state["incarnation"] == 2
        assert state["lineage"] == "L1"  # resume is not new code

    def test_base_refresh_adopts_authority_without_churning_evidence(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1")
        see_run(engine, head="h1", run_id=1, conclusion="failure", fingerprint="fp1")
        checks_before = [f for f in tokens(engine, "ready.facts") if f["kind"] == "checks"]
        see_head(engine, "h1", base="b2")
        state = one(engine, "ci.state")
        assert state["base"] == "b2"
        assert state["status"] == "failure"
        assert state["best"] == [1, 1]
        checks_after = [f for f in tokens(engine, "ready.facts") if f["kind"] == "checks"]
        assert len(checks_after) == len(checks_before)  # no new round, no churn


class TestCiAssessment:
    def test_newest_exact_head_run_wins(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, conclusion="failure", fingerprint="fp1")
        see_run(engine, head="h1", run_id=2, conclusion="success", fingerprint="")
        state = one(engine, "ci.state")
        assert state["status"] == "success"
        assert state["best"] == [2, 1]

    def test_run_for_another_head_is_inert(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h0", run_id=9, conclusion="failure", fingerprint="fpX")
        state = one(engine, "ci.state")
        assert state["status"] == "pending"
        assert failures(engine) == []

    def test_older_run_is_inert(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=2, conclusion="success")
        see_run(engine, head="h1", run_id=1, conclusion="failure", fingerprint="fp1")
        state = one(engine, "ci.state")
        assert state["status"] == "success"
        assert failures(engine) == []

    def test_same_run_id_higher_attempt_wins(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="failure", fingerprint="fp1")
        see_run(engine, head="h1", run_id=1, attempt=2, conclusion="success")
        state = one(engine, "ci.state")
        assert state["status"] == "success"
        assert state["best"] == [1, 2]

    def test_same_identity_progresses_from_in_progress_to_failure(self) -> None:
        # ONE run attempt reports twice as it advances toward its
        # terminal conclusion — the terminal failure must escalate even
        # though its (run_id, attempt) identity equals the recorded best
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="in_progress")
        assert one(engine, "ci.state")["status"] == "in_progress"
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="failure", fingerprint="fp1")
        assert one(engine, "ci.state")["status"] == "failure"
        # the escalation loop consumed the mail and burned the rerun rung
        assert world_of(engine)["reruns"] == ["L1:fp1"]

    def test_same_identity_advances_from_queued_to_in_progress(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="queued")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="in_progress")
        assert one(engine, "ci.state")["status"] == "in_progress"

    def test_same_identity_never_steps_back_from_in_progress_to_queued(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="in_progress")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="queued")
        assert one(engine, "ci.state")["status"] == "in_progress"

    def test_same_identity_never_regresses_from_terminal_to_nonterminal(self) -> None:
        # an out-of-order nonterminal observation arriving after the
        # terminal one must not resurrect a settled conclusion
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="success")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="in_progress")
        assert one(engine, "ci.state")["status"] == "success"

    def test_equal_run_evidence_is_inert_and_mails_no_duplicate(self) -> None:
        # the first failure's escalation is HELD in flight, so a second
        # mail would sit visibly in esc.failures (decide has no baton)
        engine, dispatch, definitions = held_failure()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "failure", "fingerprint": "fp1"},
            hold=HOLD,
        )
        assert failures(engine) == []  # no duplicate mail queued
        assert len(dispatch.pending) == 1  # and only the one escalation

    def test_failure_mails_escalation_with_lineage_and_authority(self) -> None:
        _engine, dispatch, _ = held_failure(head="h1", base="b1", policy="p1")
        [invocation] = dispatch.pending.values()
        assert invocation.activity == "rerun_gate"
        claim = dict(invocation.input["work"])
        assert claim.pop("mem") == {"reruns": {}, "repairs": {}, "rerun_faults": {}, "closing": None}
        assert claim == {
            "fingerprint": "L1:fp1",
            "fp": "fp1",
            "op": "rerun:L1:fp1",
            "head": "h1",
            "base": "b1",
            "policy": "p1",
            "incarnation": 1,
            "run_id": 1,
            "attempt": 1,
        }


class TestEscalationEcho:
    def test_moved_gate_echo_of_the_current_tuple_parks_the_fingerprint(self) -> None:
        engine, dispatch, definitions = held_failure(base="b1")
        # the base moves at the provider BEFORE its webhook arrives: the
        # in-flight gate sees the fresher world, CI still holds b1
        world = world_of(engine)
        world["base_head"] = "b2"
        world["authority"]["base"] = "b2"
        release_one(engine, dispatch, definitions, "rerun_gate")  # MOVED
        state = one(engine, "ci.state")
        assert state["parked"] == ["fp1"]
        assert dispatch.pending == {}  # parked means NO blind retry
        assert one(engine, "esc.ladder")["reruns"] == {}  # no budget burned

    def test_refresh_reissues_a_parked_escalation_under_the_fresh_base(self) -> None:
        engine, dispatch, definitions = held_failure(base="b1")
        world = world_of(engine)
        world["base_head"] = "b2"
        world["authority"]["base"] = "b2"
        release_one(engine, dispatch, definitions, "rerun_gate")  # MOVED -> park
        # the delayed webhook lands: the refresh reissues under b2 and
        # this time the gate's world comparison holds — the rerun LANDS
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b2", "mergeable": True, "policy": "p1"},
        )
        assert one(engine, "ci.state")["parked"] == []
        assert world["reruns"] == ["L1:fp1"]  # exactly one landed rerun
        assert one(engine, "esc.ladder")["reruns"]["L1:fp1"]["state"] == "done"

    def test_echo_of_a_stale_tuple_reissues_under_the_current_authority(self) -> None:
        engine, dispatch, definitions = held_failure(base="b1")
        # the refresh webhook folds while the b1 escalation is in flight
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b2", "mergeable": True, "policy": "p1"},
            hold=HOLD,
        )
        release_one(engine, dispatch, definitions, "rerun_gate")  # MOVED
        # the echo's b1 tuple is already stale against the admitted b2:
        # reissue NOW (park would wait for a refresh that already came)
        assert one(engine, "ci.state")["parked"] == []
        assert world_of(engine)["reruns"] == ["L1:fp1"]
        assert one(engine, "esc.ladder")["reruns"]["L1:fp1"]["state"] == "done"

    def test_mergeable_only_refresh_preserves_parked_and_mails_nothing(self) -> None:
        engine, dispatch, definitions = held_failure(base="b1")
        # the PR goes draft at the provider before the webhook arrives:
        # the grant moves (phase), head/base/policy are untouched
        world = world_of(engine)
        world["pr_state"] = "draft"
        world["authority"]["phase"] = "quiescent"
        release_one(engine, dispatch, definitions, "rerun_gate")  # MOVED
        assert one(engine, "ci.state")["parked"] == ["fp1"]
        # a mergeable-only recompute changes no authority field: a
        # reissue would repeat the SAME tuple, so the park is preserved
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": False, "policy": "p1"},
        )
        assert one(engine, "ci.state")["parked"] == ["fp1"]
        assert failures(engine) == []
        assert dispatch.pending == {}
        assert one(engine, "esc.ladder")["reruns"] == {}

    def test_stale_incarnation_echo_reissues_once_and_the_duplicate_is_absorbed(self) -> None:
        # the marquee interleaving: draft -> resume mints incarnation 2
        # over an IDENTICAL head/base/policy while the incarnation-1
        # escalation is still in flight; the re-observed failure and the
        # moved-echo reissue then race as two mails for the SAME
        # evidence — exactly one rerun may land and NO repair may fire
        engine, dispatch, definitions = held_failure()
        deliver_held(engine, dispatch, definitions, "on_draft", "DraftSeen", {}, hold=HOLD)
        deliver_held(engine, dispatch, definitions, "on_ready", "ReadySeen", {}, hold=HOLD)
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "failure", "fingerprint": "fp1"},
            hold=HOLD,
        )
        release_one(engine, dispatch, definitions, "rerun_gate")  # MOVED (grant)
        state = one(engine, "ci.state")
        assert state["parked"] == []
        assert state["incarnation"] == 2
        assert world_of(engine)["reruns"] == ["L1:fp1"]  # ONE rerun landed
        ladder = one(engine, "esc.ladder")
        assert ladder["reruns"]["L1:fp1"] == {"state": "done", "run_id": 1, "attempt": 1}
        assert ladder["repairs"] == {}  # the duplicate mail burned NOTHING
        assert tokens(engine, "mut.requests") == []  # and pushed NOTHING

    def test_echo_after_the_failure_is_gone_is_inert(self) -> None:
        engine, dispatch, definitions = held_failure()
        # newer evidence goes green while the escalation is in flight
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 2, "attempt": 1, "conclusion": "success", "fingerprint": ""},
            hold=HOLD,
        )
        world = world_of(engine)
        world["base_head"] = "b2"  # and the world moved: the gate says MOVED
        world["authority"]["base"] = "b2"
        release_one(engine, dispatch, definitions, "rerun_gate")
        state = one(engine, "ci.state")
        assert state["parked"] == []
        assert failures(engine) == []
        assert world["reruns"] == []  # nothing rerun, nothing parked
        assert one(engine, "esc.ladder")["reruns"] == {}


class TestCiClose:
    def test_close_records_the_final_verdict_and_retires_the_baton(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        assert one(engine, "ci.done") == {"status": "failure", "reason": "merged"}
        assert tokens(engine, "ci.state") == []
