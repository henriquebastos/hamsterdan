"""Executable contract tests for the V5 escalation loop.

Escalation owns the Ladder baton: rerun once, then repair once, per
fingerprint PER LINEAGE, then surface for the human. An in-flight rerun
HOLDS the baton (no second decision can race it). Every consumed rung
records the run evidence it answered — only strictly newer evidence
advances the ladder, so duplicate mails never burn a rung. Moved burns
no budget and echoes CI; a faulted rerun is FAIL-CLOSED and the
recovery door reissues the EXACT retained operation (A2), reconciled
lookup-first by the gate.
"""

from harness import (
    comment,
    comment_held,
    deliver,
    deliver_held,
    one,
    projection,
    release_one,
    see_head,
    see_run,
    spawn,
    spawn_held,
    tokens,
    world_of,
)

HOLD = frozenset({"rerun_gate"})
GATE_HOLD = frozenset({"git_gate"})


def fail(engine, run_id: int = 1, attempt: int = 1, fingerprint: str = "fp1", head: str = "h1"):
    see_run(
        engine,
        head=head,
        run_id=run_id,
        attempt=attempt,
        conclusion="failure",
        fingerprint=fingerprint,
    )


def ladder(engine) -> dict:
    return one(engine, "esc.ladder")


def pushes(engine) -> list[str]:
    """Operations the provider's push ledger holds (LANDED effects)."""
    return [p["op"] for p in world_of(engine)["pushes"]]


def push_rounds(engine) -> list[dict]:
    """Every mutation round the loop ever opened (a landed, moved, or
    faulted round each left exactly one pending fact)."""
    return [f["body"] for f in projection(engine) if f["kind"] == "mutation_pending"]


def human_pages(engine) -> list[dict]:
    return [f for f in projection(engine) if f["kind"] == "human_needed"]


class TestRerunRung:
    def test_first_failure_requests_one_rerun_and_holds_the_baton(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "failure", "fingerprint": "fp1"},
            hold=HOLD,
        )
        [invocation] = dispatch.pending.values()
        assert invocation.activity == "rerun_gate"
        assert tokens(engine, "esc.ladder") == []  # the baton is HELD in flight
        # a second, DIFFERENT failure cannot race the held round: its
        # mail waits visibly in the mailbox until the baton returns
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 2, "attempt": 1, "conclusion": "failure", "fingerprint": "fp2"},
            hold=HOLD,
        )
        assert len(tokens(engine, "esc.failures")) == 1
        assert len(dispatch.pending) == 1
        release_one(engine, dispatch, definitions, "rerun_gate")  # both rounds settle
        assert world_of(engine)["reruns"] == ["L1:fp1", "L1:fp2"]
        # each rung records its EVIDENCE HORIZON — the newest run the
        # provider reported before that rerun issued (run 2 was already
        # visible when fp1's rerun went out), not merely the answered
        # evidence: everything at or below it predates the rerun
        assert ladder(engine)["reruns"] == {
            "L1:fp1": {"state": "done", "run_id": 2, "attempt": 1},
            "L1:fp2": {"state": "done", "run_id": 2, "attempt": 1},
        }

    def test_evidence_arriving_while_the_rerun_is_in_flight_cannot_indict_it(self) -> None:
        # a failure observed BEFORE the rerun request reached the
        # provider can never prove the rerun failed: the gate's
        # pre-request cut absorbs mail that queued while it flew
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "failure", "fingerprint": "fp1"},
            hold=HOLD,
        )
        # the SAME fingerprint fails again while the rerun is in flight
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 2, "conclusion": "failure", "fingerprint": "fp1"},
            hold=HOLD,
        )
        assert len(tokens(engine, "esc.failures")) == 1  # waiting on the baton
        release_one(engine, dispatch, definitions, "rerun_gate")
        # the cut (1,2) absorbed the queued pre-request evidence: no repair
        assert ladder(engine)["reruns"] == {"L1:fp1": {"state": "done", "run_id": 1, "attempt": 2}}
        assert push_rounds(engine) == []
        # the rerun's OWN outcome is strictly newer — the repair is earned
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 3, "conclusion": "failure", "fingerprint": "fp1"},
        )
        assert pushes(engine) == ["repair:L1:fp1"]  # the repair landed

    def test_landed_rerun_records_the_answered_evidence_on_the_rung(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine, run_id=7, attempt=2)
        assert world_of(engine)["reruns"] == ["L1:fp1"]
        assert ladder(engine)["reruns"] == {"L1:fp1": {"state": "done", "run_id": 7, "attempt": 2}}

    def test_budget_is_per_lineage_so_new_code_earns_a_fresh_rerun(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine, run_id=1)
        see_head(engine, "h2")  # superseded: fresh lineage L2
        fail(engine, run_id=2, head="h2")
        assert world_of(engine)["reruns"] == ["L1:fp1", "L2:fp1"]
        assert push_rounds(engine) == []  # neither rung escalated

    def test_confirmed_own_repair_keeps_the_lineage_and_the_burned_rungs(self) -> None:
        # the REAL repair sequence: rerun burned, repair requested and
        # PUSHED by the mutation loop, our push confirmed as the new
        # head — then the same flake failing on the repaired head must
        # not earn a second rerun OR a second push; the exhausted ladder
        # pages the human
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine, run_id=1, attempt=1)  # burns the L1:fp1 rerun rung
        fail(engine, run_id=1, attempt=2)  # burns the repair rung: the push LANDS
        assert pushes(engine) == ["repair:L1:fp1"]
        new_head = world_of(engine)["branch_head"]
        assert new_head == "h1+repair:L1:fp1"
        # the landed push noted the provisional expectation with lifecycle
        assert one(engine, "life.state")["expected"] == new_head
        see_head(engine, new_head)  # CONFIRMED: same lineage L1
        fail(engine, run_id=2, attempt=1, head=new_head)
        assert world_of(engine)["reruns"] == ["L1:fp1"]  # no second rerun
        assert pushes(engine) == ["repair:L1:fp1"]  # no second push
        [page] = human_pages(engine)  # the ladder is exhausted
        assert page["body"] == {"fingerprint": "fp1", "head": new_head}


class TestRepairRung:
    def test_newer_failing_evidence_after_a_landed_rerun_requests_repair_once(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=GATE_HOLD,
        )
        for attempt in (1, 2):  # the rerun's own attempt still fails
            deliver_held(
                engine,
                dispatch,
                definitions,
                "on_runs",
                "RunSeen",
                {"head": "h1", "run_id": 1, "attempt": attempt, "conclusion": "failure", "fingerprint": "fp1"},
                hold=GATE_HOLD,
            )
        # the repair is IN FLIGHT: one gate invocation, full claim,
        # stable operation identity
        [invocation] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        assert invocation.input["work"] == {
            "op": "repair:L1:fp1",
            "op_key": "push:repair:L1:fp1:h1:i1",
            "head": "h1",
            "base": "b1",
            "policy": "p1",
            "incarnation": 1,
            "lineage": "L1",
        }
        assert ladder(engine)["repairs"]["L1:fp1"]["state"] == "pending"
        # a third failure while the repair is in flight is the same
        # breakage, not grounds for a second push
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 3, "conclusion": "failure", "fingerprint": "fp1"},
            hold=GATE_HOLD,
        )
        assert len([i for i in dispatch.pending.values() if i.activity == "git_gate"]) == 1
        assert human_pages(engine) == []
        release_one(engine, dispatch, definitions, "git_gate")
        assert pushes(engine) == ["repair:L1:fp1"]

    def test_landed_repair_then_strictly_newer_failure_pages_the_human(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine, run_id=1, attempt=1)
        fail(engine, run_id=1, attempt=2)  # -> the repair pushes and LANDS
        assert pushes(engine) == ["repair:L1:fp1"]
        assert ladder(engine)["repairs"]["L1:fp1"]["state"] == "done"
        assert human_pages(engine) == []
        fail(engine, run_id=1, attempt=3)  # the ladder is exhausted
        [page] = human_pages(engine)
        assert page["body"] == {"fingerprint": "fp1", "head": "h1"}

    def test_declined_repair_consumes_the_rung_with_a_known_terminal(self) -> None:
        # a faulted mutation baton declines every further push BEFORE
        # any gate attempt — the rung is consumed with a KNOWN terminal
        engine, _ = spawn()
        world_of(engine)["git_mode"] = "fault"
        see_head(engine, "h1")
        fail(engine, run_id=1, attempt=1)
        fail(engine, run_id=1, attempt=2)  # this repair FAULTS the baton
        assert ladder(engine)["repairs"]["L1:fp1"]["state"] == "fault"
        # a second fingerprint climbs its own ladder; its repair is declined
        fail(engine, run_id=2, attempt=1, fingerprint="fp2")
        fail(engine, run_id=2, attempt=2, fingerprint="fp2")
        assert ladder(engine)["repairs"]["L1:fp2"]["state"] == "declined"
        fail(engine, run_id=2, attempt=3, fingerprint="fp2")  # straight to the human
        assert len(human_pages(engine)) == 1
        assert pushes(engine) == []  # never a push landed

    def test_moved_repair_refunds_the_budget_and_converges_through_ci(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=GATE_HOLD,
        )
        for attempt in (1, 2):
            deliver_held(
                engine,
                dispatch,
                definitions,
                "on_runs",
                "RunSeen",
                {"head": "h1", "run_id": 1, "attempt": attempt, "conclusion": "failure", "fingerprint": "fp1"},
                hold=GATE_HOLD,
            )
        # the repair flies under b1; the provider's base moves BEFORE the
        # webhook arrives — the gate's fresh read classifies MOVED
        world_of(engine)["base_head"] = "b2"
        release_one(engine, dispatch, definitions, "git_gate")
        # budget refunded; the recheck echoed to CI — the attempted tuple
        # is still what CI holds (no webhook yet), so CI parks
        assert "L1:fp1" not in ladder(engine)["repairs"]
        assert one(engine, "ci.state")["parked"] == ["fp1"]
        assert pushes(engine) == []
        # the webhook lands: the refresh reissues, the refunded REPAIR is
        # re-requested under b2 and this time the push LANDS
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b2", "mergeable": True, "policy": "p1"},
        )
        assert pushes(engine) == ["repair:L1:fp1"]
        entry = ladder(engine)["repairs"]["L1:fp1"]
        assert entry["state"] == "done"
        assert entry["base"] == "b2"  # the fresh claim, not the stale one

    def test_faulted_repair_retains_the_entry_for_recovery_time_echoes(self) -> None:
        engine, _ = spawn()
        world_of(engine)["git_mode"] = "fault"
        see_head(engine, "h1", base="b1", policy="p1")
        fail(engine, run_id=1, attempt=1)
        fail(engine, run_id=1, attempt=2)  # the repair's gate terminal is unknown
        entry = ladder(engine)["repairs"]["L1:fp1"]
        assert entry["state"] == "fault"
        # the retained entry keeps the raw fp, attempted authority, and
        # evidence: a later moved settle can still echo a recheck
        assert (entry["fp"], entry["head"], entry["base"]) == ("fp1", "h1", "b1")
        assert (entry["run_id"], entry["attempt"]) == (1, 2)
        fail(engine, run_id=1, attempt=3)  # newer evidence: page, no push
        assert len(human_pages(engine)) == 1
        assert pushes(engine) == []

    def test_a_settle_the_ladder_never_requested_is_inert(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine)
        before = ladder(engine)
        # a human-commanded push the ladder never requested lands and
        # settles (fingerprint ""); the foreign settle is absorbed
        comment(engine, "c1", "change")
        assert pushes(engine) == ["change"]  # it DID land
        assert ladder(engine) == before  # but burned no rung


class TestFaultAndRecovery:
    def spawn_faulted(self):
        """A failing head whose rerun gate faulted (unknown terminal)."""
        engine, built = spawn()
        world_of(engine)["reruns_mode"] = "unknown"
        see_head(engine, "h1", base="b1", policy="p1")
        fail(engine, run_id=1, attempt=1)
        return engine, built

    def test_rerun_fault_is_fail_closed_and_retains_the_exact_request(self) -> None:
        engine, _ = self.spawn_faulted()
        state = ladder(engine)
        assert state["reruns"] == {"L1:fp1": {"state": "fault"}}
        assert state["rerun_faults"]["L1:fp1"] == {
            "op": "rerun:L1:fp1",
            "reason": "unknown provider terminal",
            "fp": "fp1",
            "head": "h1",
            "base": "b1",
            "policy": "p1",
            "incarnation": 1,
            "run_id": 1,
            "attempt": 1,
            "blocked": None,
        }
        assert world_of(engine)["reruns"] == []  # no proven effect
        faults = [f for f in projection(engine) if f["kind"] == "fault"]
        assert faults and faults[0]["body"]["where"] == "rerun"

    def test_a_faulted_rung_never_authorizes_the_repair_rung(self) -> None:
        engine, _ = self.spawn_faulted()
        fail(engine, run_id=1, attempt=2)  # newer evidence, rung unproven
        assert push_rounds(engine) == []  # FAIL-CLOSED: no mutation
        [page] = human_pages(engine)
        assert page["body"]["why"] == "rerun-fault"

    def test_recovery_reissues_the_exact_operation_and_lookup_first_reconciles(self) -> None:
        # the provider DID hold the rerun: the crash hit after acceptance
        engine, _ = self.spawn_faulted()
        world = world_of(engine)
        world["reruns_mode"] = None
        world["reruns"].append("L1:fp1")
        comment(engine, "rec1", "recover_publication", arg="rerun:L1:fp1")
        state = ladder(engine)
        assert state["reruns"] == {"L1:fp1": {"state": "done", "run_id": 1, "attempt": 1}}
        assert state["rerun_faults"] == {}
        # lookup-first: NO duplicate rerun effect (the review loop's own
        # comment effects share the world log; only reruns matter here)
        assert [e for e in world["log"] if e[0] == "rerun"] == []

    def test_recovery_reissues_when_the_provider_never_held_it(self) -> None:
        engine, _ = self.spawn_faulted()
        world = world_of(engine)
        world["reruns_mode"] = None
        comment(engine, "rec2", "recover_publication", arg="rerun:L1:fp1")
        assert world["reruns"] == ["L1:fp1"]  # the reissue landed for real
        assert ladder(engine)["reruns"]["L1:fp1"]["state"] == "done"

    def test_recovery_replays_evidence_blocked_by_an_already_held_rerun(self) -> None:
        # a NEWER failure arrived while faulted (fail-closed consumed
        # it); recovery then proves the provider held the rerun all
        # along — the blocked failure may BE the rerun's own outcome, so
        # it must come back and advance the ladder to repair
        engine, _ = self.spawn_faulted()
        fail(engine, run_id=1, attempt=2)  # blocked by the fault
        assert push_rounds(engine) == []  # fail-closed: nothing yet
        world = world_of(engine)
        world["reruns_mode"] = None
        world["reruns"].append("L1:fp1")  # the provider held it
        comment(engine, "rec3", "recover_publication", arg="rerun:L1:fp1")
        state = ladder(engine)
        assert state["reruns"]["L1:fp1"] == {"state": "done", "run_id": 1, "attempt": 1}
        assert state["rerun_faults"] == {}
        # the replayed evidence escalated: the repair pushed and landed
        assert pushes(engine) == ["repair:L1:fp1"]
        # and still no duplicate rerun effect
        assert [e for e in world["log"] if e[0] == "rerun"] == []

    def test_recovery_that_issues_the_rerun_now_absorbs_older_blocked_evidence(self) -> None:
        # the provider NEVER held the rerun: evidence observed before
        # this fresh rerun cannot prove it failed — no spurious repair;
        # the new rerun's own outcome arrives later as fresh evidence
        engine, _ = self.spawn_faulted()
        fail(engine, run_id=1, attempt=2)  # blocked by the fault
        world = world_of(engine)
        world["reruns_mode"] = None
        comment(engine, "rec4", "recover_publication", arg="rerun:L1:fp1")
        state = ladder(engine)
        assert world["reruns"] == ["L1:fp1"]  # issued NOW
        # the rung watermark advanced to the blocked evidence: absorbed
        assert state["reruns"]["L1:fp1"] == {"state": "done", "run_id": 1, "attempt": 2}
        assert pushes(engine) == []  # no push on stale evidence
        fail(engine, run_id=1, attempt=3)  # the fresh rerun still fails
        assert pushes(engine) == ["repair:L1:fp1"]  # NOW the repair is earned

    def test_evidence_arriving_while_recovery_is_in_flight_cannot_indict_the_fresh_rerun(self) -> None:
        # the sharpest race: recovery's reissue is IN FLIGHT when new
        # evidence arrives — it queues in the mailbox (the baton is
        # held), so no fault entry retains it. The gate's pre-request
        # cut is the only thing that can absorb it.
        engine, _, dispatch, definitions = spawn_held()
        world = world_of(engine)
        world["reruns_mode"] = "unknown"
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=frozenset(),
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "failure", "fingerprint": "fp1"},
            hold=frozenset(),
        )
        assert ladder(engine)["reruns"] == {"L1:fp1": {"state": "fault"}}
        world["reruns_mode"] = None  # the provider heals
        # begin recovery and HOLD its reissue in flight
        comment_held(engine, dispatch, definitions, "rec1", "recover_publication", arg="rerun:L1:fp1", hold=HOLD)
        # attempt 2 fails while the reissue flies: it queues in the mailbox
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 2, "conclusion": "failure", "fingerprint": "fp1"},
            hold=HOLD,
        )
        assert len(tokens(engine, "esc.failures")) == 1
        release_one(engine, dispatch, definitions, "rerun_gate")
        # the cut (1,2) absorbed the pre-request evidence: no repair yet
        assert ladder(engine)["reruns"] == {"L1:fp1": {"state": "done", "run_id": 1, "attempt": 2}}
        assert pushes(engine) == []
        # only the fresh rerun's own failure earns the repair
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 3, "conclusion": "failure", "fingerprint": "fp1"},
        )
        assert pushes(engine) == ["repair:L1:fp1"]

    def test_a_refaulted_recovery_round_keeps_the_blocked_evidence(self) -> None:
        engine, _ = self.spawn_faulted()
        fail(engine, run_id=1, attempt=2)  # blocked by the fault
        comment(engine, "rec5", "recover_publication", arg="rerun:L1:fp1")
        # reruns_mode is still "unknown": the recovery round re-faults
        blocked = ladder(engine)["rerun_faults"]["L1:fp1"]["blocked"]
        assert (blocked["run_id"], blocked["attempt"]) == (1, 2)
        # a second recovery with a now-healthy provider that held the
        # rerun still replays the retained evidence
        world = world_of(engine)
        world["reruns_mode"] = None
        world["reruns"].append("L1:fp1")
        comment(engine, "rec6", "recover_publication", arg="rerun:L1:fp1")
        assert pushes(engine) == ["repair:L1:fp1"]

    def test_recovery_for_an_unknown_operation_is_inert(self) -> None:
        engine, _ = self.spawn_faulted()
        before = ladder(engine)
        comment(engine, "rec7", "recover_publication", arg="rerun:L9:zz")
        assert ladder(engine) == before

    def test_recovery_routed_to_another_loop_is_inert_here(self) -> None:
        # the operation prefix routes to mutation: the ladder never sees it
        engine, _ = self.spawn_faulted()
        before = ladder(engine)
        comment(engine, "rec8", "recover_publication", arg="push:zz:h1:i1")
        assert ladder(engine) == before


class TestClose:
    def test_a_recovery_that_lost_the_race_with_close_is_never_stranded(self) -> None:
        # the recovery note was ADMITTED while running, but its apply
        # waits on the ladder baton a held rerun carries in flight;
        # close arrives during the wait. Whichever wins the returned
        # baton, no token may strand in the mailbox
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "failure", "fingerprint": "fp1"},
            hold=HOLD,
        )
        assert tokens(engine, "esc.ladder") == []  # baton in flight
        comment_held(engine, dispatch, definitions, "r1", "recover_publication", arg="rerun:fp1", hold=HOLD)
        assert len(tokens(engine, "esc.recover")) == 1  # parked, waiting
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=HOLD)
        release_one(engine, dispatch, definitions, "rerun_gate")
        assert tokens(engine, "esc.recover") == []  # applied or drained
        [ended] = tokens(engine, "esc.done")
        assert ended["reason"] == "merged"
        # the late round settled MOVED (terminal authority) and echoed a
        # recheck — CI already retired, so the echo must DRAIN, never
        # strand in the mailbox of a closed loop
        assert tokens(engine, "ci.echo") == []

    def test_close_retires_the_ladder_with_its_budgets(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine)
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        ended = one(engine, "esc.done")
        assert ended["reason"] == "merged"
        assert ended["reruns"] == {"L1:fp1": {"state": "done", "run_id": 1, "attempt": 1}}
        assert tokens(engine, "esc.ladder") == []
