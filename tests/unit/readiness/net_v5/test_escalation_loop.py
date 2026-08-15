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


def see_settled(engine, op: str, outcome: str, fingerprint: str, incarnation: int = 1):
    deliver(
        engine,
        "on_settled",
        "MutationSettled",
        {"op": op, "outcome": outcome, "incarnation": incarnation, "fingerprint": fingerprint},
    )


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


def repair_requests(engine) -> list[dict]:
    return tokens(engine, "mut.requests")


def human_pages(engine) -> list[dict]:
    return [f for f in tokens(engine, "dash.facts") if f["kind"] == "human_needed"]


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
        assert tokens(engine, "mut.requests") == []
        # the rerun's OWN outcome is strictly newer — the repair is earned
        deliver(
            engine,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 3, "conclusion": "failure", "fingerprint": "fp1"},
        )
        [request] = tokens(engine, "mut.requests")
        assert request["op"] == "repair:L1:fp1"

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
        assert repair_requests(engine) == []  # neither rung escalated

    def test_confirmed_own_repair_keeps_the_lineage_and_the_burned_rungs(self) -> None:
        # the REAL repair sequence: rerun burned, repair requested and
        # pushed, our push confirmed as the new head — then the same
        # flake failing on the repaired head must not earn a second
        # rerun OR a second push; the exhausted ladder pages the human
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine, run_id=1, attempt=1)  # burns the L1:fp1 rerun rung
        fail(engine, run_id=1, attempt=2)  # burns the repair rung
        [request] = repair_requests(engine)
        assert request["op"] == "repair:L1:fp1"
        # the (future) mutation loop pushes: provisional note, settle
        deliver(
            engine,
            "on_provisional",
            "ProvisionalHead",
            {"expected": "h2", "op": "repair:L1:fp1", "lineage": "L1"},
        )
        see_settled(engine, op="repair:L1:fp1", outcome="landed", fingerprint="L1:fp1")
        see_head(engine, "h2")  # CONFIRMED: same lineage L1
        fail(engine, run_id=2, attempt=1, head="h2")
        assert world_of(engine)["reruns"] == ["L1:fp1"]  # no second rerun
        assert len(repair_requests(engine)) == 1  # no second push
        [page] = human_pages(engine)  # the ladder is exhausted
        assert page["body"] == {"fingerprint": "fp1", "head": "h2"}


class TestRepairRung:
    def test_newer_failing_evidence_after_a_landed_rerun_requests_repair_once(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1", policy="p1")
        fail(engine, run_id=1, attempt=1)
        fail(engine, run_id=1, attempt=2)  # the rerun's own attempt still fails
        [request] = repair_requests(engine)
        assert request == {
            "op": "repair:L1:fp1",
            "head": "h1",
            "base": "b1",
            "policy": "p1",
            "incarnation": 1,
            "source": "escalation",
        }
        assert ladder(engine)["repairs"]["L1:fp1"]["state"] == "pending"
        # a third failure while the repair is in flight is the same
        # breakage, not grounds for a second push
        fail(engine, run_id=1, attempt=3)
        assert len(repair_requests(engine)) == 1
        assert human_pages(engine) == []

    def test_landed_repair_then_strictly_newer_failure_pages_the_human(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine, run_id=1, attempt=1)
        fail(engine, run_id=1, attempt=2)  # -> repair requested
        see_settled(engine, op="repair:L1:fp1", outcome="landed", fingerprint="L1:fp1")
        assert ladder(engine)["repairs"]["L1:fp1"]["state"] == "done"
        assert human_pages(engine) == []
        fail(engine, run_id=1, attempt=3)  # the ladder is exhausted
        [page] = human_pages(engine)
        assert page["body"] == {"fingerprint": "fp1", "head": "h1"}

    def test_declined_repair_consumes_the_rung_with_a_known_terminal(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine, run_id=1, attempt=1)
        fail(engine, run_id=1, attempt=2)
        see_settled(engine, op="repair:L1:fp1", outcome="declined", fingerprint="L1:fp1")
        assert ladder(engine)["repairs"]["L1:fp1"]["state"] == "declined"
        fail(engine, run_id=1, attempt=3)  # newer evidence: straight to the human
        assert len(human_pages(engine)) == 1
        assert len(repair_requests(engine)) == 1  # never a second push

    def test_moved_repair_refunds_the_budget_and_converges_through_ci(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1")
        fail(engine, run_id=1, attempt=1)
        fail(engine, run_id=1, attempt=2)  # -> repair pending under b1
        # the repair settle says MOVED: budget refunded, recheck echoed
        # to CI — the attempted tuple is still current, so CI parks
        see_settled(engine, op="repair:L1:fp1", outcome="moved", fingerprint="L1:fp1")
        assert "L1:fp1" not in ladder(engine)["repairs"]
        assert one(engine, "ci.state")["parked"] == ["fp1"]
        # the base refresh reissues; the rerun rung already answered
        # (1,2), so the refunded REPAIR is re-requested under b2
        see_head(engine, "h1", base="b2")
        assert [r["base"] for r in repair_requests(engine)] == ["b1", "b2"]

    def test_faulted_repair_retains_the_entry_for_recovery_time_echoes(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1", policy="p1")
        fail(engine, run_id=1, attempt=1)
        fail(engine, run_id=1, attempt=2)
        see_settled(engine, op="repair:L1:fp1", outcome="faulted", fingerprint="L1:fp1")
        entry = ladder(engine)["repairs"]["L1:fp1"]
        assert entry["state"] == "fault"
        # the retained entry keeps the raw fp, attempted authority, and
        # evidence: a later moved settle can still echo a recheck
        assert (entry["fp"], entry["head"], entry["base"]) == ("fp1", "h1", "b1")
        assert (entry["run_id"], entry["attempt"]) == (1, 2)
        fail(engine, run_id=1, attempt=3)  # newer evidence: page, no push
        assert len(human_pages(engine)) == 1
        assert len(repair_requests(engine)) == 1

    def test_settle_for_an_unknown_key_is_inert(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine)
        before = ladder(engine)
        see_settled(engine, op="repair:L9:zz", outcome="landed", fingerprint="L9:zz")
        assert ladder(engine) == before


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
        faults = [f for f in tokens(engine, "dash.facts") if f["kind"] == "fault"]
        assert faults and faults[0]["body"]["where"] == "rerun"

    def test_a_faulted_rung_never_authorizes_the_repair_rung(self) -> None:
        engine, _ = self.spawn_faulted()
        fail(engine, run_id=1, attempt=2)  # newer evidence, rung unproven
        assert repair_requests(engine) == []  # FAIL-CLOSED: no mutation
        [page] = human_pages(engine)
        assert page["body"]["why"] == "rerun-fault"

    def test_recovery_reissues_the_exact_operation_and_lookup_first_reconciles(self) -> None:
        # the provider DID hold the rerun: the crash hit after acceptance
        engine, _ = self.spawn_faulted()
        world = world_of(engine)
        world["reruns_mode"] = None
        world["reruns"].append("L1:fp1")
        deliver(engine, "on_recover", "RecoverFact", {"target": "esc", "op": "rerun:L1:fp1"})
        state = ladder(engine)
        assert state["reruns"] == {"L1:fp1": {"state": "done", "run_id": 1, "attempt": 1}}
        assert state["rerun_faults"] == {}
        assert world["log"] == []  # lookup-first: NO duplicate effect

    def test_recovery_reissues_when_the_provider_never_held_it(self) -> None:
        engine, _ = self.spawn_faulted()
        world = world_of(engine)
        world["reruns_mode"] = None
        deliver(engine, "on_recover", "RecoverFact", {"target": "esc", "op": "rerun:L1:fp1"})
        assert world["reruns"] == ["L1:fp1"]  # the reissue landed for real
        assert ladder(engine)["reruns"]["L1:fp1"]["state"] == "done"

    def test_recovery_replays_evidence_blocked_by_an_already_held_rerun(self) -> None:
        # a NEWER failure arrived while faulted (fail-closed consumed
        # it); recovery then proves the provider held the rerun all
        # along — the blocked failure may BE the rerun's own outcome, so
        # it must come back and advance the ladder to repair
        engine, _ = self.spawn_faulted()
        fail(engine, run_id=1, attempt=2)  # blocked by the fault
        assert repair_requests(engine) == []  # fail-closed: nothing yet
        world = world_of(engine)
        world["reruns_mode"] = None
        world["reruns"].append("L1:fp1")  # the provider held it
        deliver(engine, "on_recover", "RecoverFact", {"target": "esc", "op": "rerun:L1:fp1"})
        state = ladder(engine)
        assert state["reruns"]["L1:fp1"] == {"state": "done", "run_id": 1, "attempt": 1}
        assert state["rerun_faults"] == {}
        [request] = repair_requests(engine)  # the replayed evidence escalated
        assert request["op"] == "repair:L1:fp1"
        assert world["log"] == []  # and still no duplicate effect

    def test_recovery_that_issues_the_rerun_now_absorbs_older_blocked_evidence(self) -> None:
        # the provider NEVER held the rerun: evidence observed before
        # this fresh rerun cannot prove it failed — no spurious repair;
        # the new rerun's own outcome arrives later as fresh evidence
        engine, _ = self.spawn_faulted()
        fail(engine, run_id=1, attempt=2)  # blocked by the fault
        world = world_of(engine)
        world["reruns_mode"] = None
        deliver(engine, "on_recover", "RecoverFact", {"target": "esc", "op": "rerun:L1:fp1"})
        state = ladder(engine)
        assert world["reruns"] == ["L1:fp1"]  # issued NOW
        # the rung watermark advanced to the blocked evidence: absorbed
        assert state["reruns"]["L1:fp1"] == {"state": "done", "run_id": 1, "attempt": 2}
        assert repair_requests(engine) == []  # no push on stale evidence
        fail(engine, run_id=1, attempt=3)  # the fresh rerun still fails
        [request] = repair_requests(engine)  # NOW the repair is earned
        assert request["op"] == "repair:L1:fp1"

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
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_recover",
            "RecoverFact",
            {"target": "esc", "op": "rerun:L1:fp1"},
            hold=HOLD,
        )
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
        assert tokens(engine, "mut.requests") == []
        # only the fresh rerun's own failure earns the repair
        deliver(
            engine,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 3, "conclusion": "failure", "fingerprint": "fp1"},
        )
        [request] = tokens(engine, "mut.requests")
        assert request["op"] == "repair:L1:fp1"

    def test_a_refaulted_recovery_round_keeps_the_blocked_evidence(self) -> None:
        engine, _ = self.spawn_faulted()
        fail(engine, run_id=1, attempt=2)  # blocked by the fault
        deliver(engine, "on_recover", "RecoverFact", {"target": "esc", "op": "rerun:L1:fp1"})
        # reruns_mode is still "unknown": the recovery round re-faults
        blocked = ladder(engine)["rerun_faults"]["L1:fp1"]["blocked"]
        assert (blocked["run_id"], blocked["attempt"]) == (1, 2)
        # a second recovery with a now-healthy provider that held the
        # rerun still replays the retained evidence
        world = world_of(engine)
        world["reruns_mode"] = None
        world["reruns"].append("L1:fp1")
        deliver(engine, "on_recover", "RecoverFact", {"target": "esc", "op": "rerun:L1:fp1"})
        [request] = repair_requests(engine)
        assert request["op"] == "repair:L1:fp1"

    def test_recovery_for_an_unknown_operation_is_inert(self) -> None:
        engine, _ = self.spawn_faulted()
        before = ladder(engine)
        deliver(engine, "on_recover", "RecoverFact", {"target": "esc", "op": "rerun:L9:zz"})
        assert ladder(engine) == before

    def test_recovery_for_another_loop_is_inert(self) -> None:
        engine, _ = self.spawn_faulted()
        before = ladder(engine)
        deliver(engine, "on_recover", "RecoverFact", {"target": "mut", "op": "rerun:L1:fp1"})
        assert ladder(engine) == before


class TestClose:
    def test_close_retires_the_ladder_with_its_budgets(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        fail(engine)
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        ended = one(engine, "esc.done")
        assert ended["reason"] == "merged"
        assert ended["reruns"] == {"L1:fp1": {"state": "done", "run_id": 1, "attempt": 1}}
        assert tokens(engine, "esc.ladder") == []
