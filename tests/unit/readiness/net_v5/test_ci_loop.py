"""Executable contract tests for the V5 CI loop.

CI is pure observation: it owns the CiState baton, adopts each admitted
head with a budget lineage, keeps only the newest exact-head run
verdict, mails ChecksFailure facts to escalation, and answers
escalation MOVED echoes by reissuing under a fresher authority or
parking until the refresh folds (order-independence). No guards, no
read arcs — every decision is a pure fold on token data.
"""

from harness import deliver, one, see_head, see_run, spawn, tokens


def see_echo(engine, fp: str = "fp1", head: str = "h1", base: str = "b1", policy: str = "p1", incarnation: int = 1):
    deliver(
        engine,
        "on_echo",
        "EscMoved",
        {"fp": fp, "head": head, "base": base, "policy": policy, "incarnation": incarnation},
    )


def failures(engine) -> list[dict]:
    return tokens(engine, "esc.failures")


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

    def test_equal_run_evidence_is_inert_and_mails_no_duplicate(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="failure", fingerprint="fp1")
        see_run(engine, head="h1", run_id=1, attempt=1, conclusion="failure", fingerprint="fp1")
        assert len(failures(engine)) == 1

    def test_failure_mails_escalation_with_lineage_and_authority(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1", policy="p1")
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        [failure] = failures(engine)
        assert failure == {
            "fingerprint": "fp1",
            "head": "h1",
            "base": "b1",
            "policy": "p1",
            "lineage": "L1",
            "incarnation": 1,
        }


class TestEscalationEcho:
    def test_echo_of_the_current_tuple_parks_the_fingerprint(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1", policy="p1")
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        see_echo(engine, fp="fp1", head="h1", base="b1", policy="p1", incarnation=1)
        state = one(engine, "ci.state")
        assert state["parked"] == ["fp1"]
        assert len(failures(engine)) == 1  # only the original mail

    def test_refresh_reissues_a_parked_escalation_under_the_fresh_base(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1")
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        see_echo(engine, fp="fp1", head="h1", base="b1", incarnation=1)
        see_head(engine, "h1", base="b2")
        assert one(engine, "ci.state")["parked"] == []
        reissued = failures(engine)[-1]
        assert reissued["fingerprint"] == "fp1"
        assert reissued["base"] == "b2"

    def test_echo_of_a_stale_tuple_reissues_under_the_current_authority(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1")
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        see_head(engine, "h1", base="b2")  # refresh folds before the echo
        see_echo(engine, fp="fp1", head="h1", base="b1", incarnation=1)
        assert one(engine, "ci.state")["parked"] == []
        reissued = failures(engine)[-1]
        assert reissued["base"] == "b2"

    def test_mergeable_only_refresh_preserves_parked_and_mails_nothing(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1", mergeable=True)
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        see_echo(engine, fp="fp1", head="h1", base="b1", incarnation=1)
        see_head(engine, "h1", base="b1", mergeable=False)  # authority unchanged
        assert one(engine, "ci.state")["parked"] == ["fp1"]
        assert len(failures(engine)) == 1  # a reissue would repeat the SAME tuple
        see_head(engine, "h1", base="b2", mergeable=False)  # now authority moved
        assert one(engine, "ci.state")["parked"] == []
        assert failures(engine)[-1]["base"] == "b2"

    def test_stale_incarnation_echo_reissues_even_with_identical_authority_fields(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1", policy="p1")
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        deliver(engine, "on_draft", "DraftSeen", {})
        deliver(engine, "on_ready", "ReadySeen", {})  # incarnation 2, same tuple otherwise
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        # an escalation attempted under the OLD grant echoes MOVED
        see_echo(engine, fp="fp1", head="h1", base="b1", policy="p1", incarnation=1)
        assert one(engine, "ci.state")["parked"] == []
        reissued = failures(engine)[-1]
        assert reissued["incarnation"] == 2
        assert len(failures(engine)) == 3  # original, post-resume, reissue

    def test_echo_after_the_failure_is_gone_is_inert(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, conclusion="failure", fingerprint="fp1")
        see_run(engine, head="h1", run_id=2, conclusion="success")
        see_echo(engine, fp="fp1")
        state = one(engine, "ci.state")
        assert state["parked"] == []
        assert len(failures(engine)) == 1  # only the original mail


class TestCiClose:
    def test_close_records_the_final_verdict_and_retires_the_baton(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        assert one(engine, "ci.done") == {"status": "failure", "reason": "merged"}
        assert tokens(engine, "ci.state") == []
