"""Executable contract tests for the V5 lifecycle (admission) loop.

The lifecycle loop is the single admission hub of the V5 actor-loop
topology: it owns the LifeState baton, absorbs every host-normalized
observation through ingress doors, and mails typed facts to sibling
loop mailboxes. No guards, no read arcs — every decision is a pure
fold on token data (the ES-007 discipline, now first-class).
"""

from harness import deliver, one, see_head, spawn, tokens

from hamsterdan.readiness.net_v5 import build_net_v5

# -- admission relations ---------------------------------------------------


class TestHeadAdmission:
    def test_first_head_admits_as_new_with_incarnation_one(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        state = one(engine, "life.state")
        assert state["phase"] == "running"
        assert state["incarnation"] == 1
        assert state["head"] == "h1"
        work = one(engine, "review.heads")
        assert work["relation"] == "new"
        assert work["incarnation"] == 1
        # the CI loop consumed its copy of the admission mail
        assert one(engine, "ci.state")["incarnation"] == 1

    def test_same_head_reobservation_is_absorbed(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_head(engine, "h1")
        assert one(engine, "life.state")["incarnation"] == 1
        assert len(tokens(engine, "review.heads")) == 1

    def test_base_refresh_keeps_incarnation_and_mails_refreshed(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1")
        see_head(engine, "h1", base="b2")
        state = one(engine, "life.state")
        assert state["incarnation"] == 1
        assert state["base"] == "b2"
        relations = [w["relation"] for w in tokens(engine, "review.heads")]
        assert relations == ["new", "refreshed"]

    def test_new_head_supersedes_with_fresh_lineage(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_head(engine, "h2")
        state = one(engine, "life.state")
        assert state["incarnation"] == 2
        assert state["head"] == "h2"
        last = tokens(engine, "review.heads")[-1]
        assert last["relation"] == "superseded"
        assert last["lineage"] == ""

    def test_expected_head_admits_as_confirmed_keeping_lineage(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(
            engine,
            "on_provisional",
            "ProvisionalHead",
            {"expected": "h2", "op": "repair", "lineage": "lin1"},
        )
        see_head(engine, "h2")
        state = one(engine, "life.state")
        assert state["incarnation"] == 2
        assert state["expected"] == ""
        last = tokens(engine, "review.heads")[-1]
        assert last["relation"] == "confirmed"
        assert last["lineage"] == "lin1"


class TestDormancy:
    def test_draft_quiesces_and_absorbs_heads_until_resume(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_draft", "DraftSeen", {})
        assert one(engine, "life.state")["phase"] == "quiescent"
        see_head(engine, "h2")  # absorbed: recorded, no work mailed
        state = one(engine, "life.state")
        assert state["phase"] == "quiescent"
        assert state["head"] == "h2"
        assert len(tokens(engine, "review.heads")) == 1
        deliver(engine, "on_ready", "ReadySeen", {})
        state = one(engine, "life.state")
        assert state["phase"] == "running"
        assert state["incarnation"] == 2
        assert tokens(engine, "review.heads")[-1]["relation"] == "resumed"

    def test_ready_without_quiescence_is_absorbed(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_ready", "ReadySeen", {})
        assert one(engine, "life.state")["incarnation"] == 1


class TestClose:
    def test_close_goes_terminal_and_fans_out_to_every_loop(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        assert one(engine, "life.state")["phase"] == "terminal"
        for mailbox in (
            "review.closed",
            "esc.closed",
            "mut.closed",
            "dash.closed",
            "rem.closed",
            "ready.closed",
        ):
            assert one(engine, mailbox)["reason"] == "merged"
        # the CI loop consumed its close mail and retired
        assert one(engine, "ci.done")["reason"] == "merged"

    def test_terminal_absorbs_every_later_observation(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        see_head(engine, "h2")
        deliver(engine, "on_close", "CloseSeen", {"reason": "closed"})
        state = one(engine, "life.state")
        assert state["phase"] == "terminal"
        assert state["head"] == "h1"
        assert len(tokens(engine, "review.closed")) == 1


class TestObservationRouting:
    def test_comment_mails_an_intent_carrying_the_authority_claim(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1", policy="p1")
        deliver(
            engine,
            "on_comment",
            "CommentSeen",
            {"id": "c1", "kind": "reply", "arg": "", "authorized": True},
        )
        intent = one(engine, "conv.intents")
        assert intent["id"] == "c1"
        assert intent["head"] == "h1"
        assert intent["base"] == "b1"
        assert intent["incarnation"] == 1
        assert intent["provisional"] is False

    def test_human_review_becomes_a_gate_fact_for_ready_and_dash(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(
            engine,
            "on_human",
            "HumanSeen",
            {"approval": True, "changes_requested": False, "unresolved": 0},
        )
        facts = [f for f in tokens(engine, "ready.facts") if f["kind"] == "human"]
        assert facts[-1]["body"]["approval"] is True
        assert [f for f in tokens(engine, "dash.facts") if f["kind"] == "human"]

    def test_runs_are_mailed_to_ci_only_while_running(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(
            engine,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "failure", "fingerprint": "fp1"},
        )
        assert one(engine, "ci.state")["fingerprint"] == "fp1"
        deliver(engine, "on_draft", "DraftSeen", {})
        deliver(
            engine,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 2, "attempt": 1, "conclusion": "success", "fingerprint": ""},
        )
        # dormancy absorbed the run: CI evidence is untouched
        assert one(engine, "ci.state")["status"] == "failure"

    def test_admission_mails_state_facts_to_ready_and_dash(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        [fact] = [f for f in tokens(engine, "ready.facts") if f["kind"] == "state"]
        assert fact["body"]["head"] == "h1"
        assert fact["body"]["phase"] == "running"


# -- the structural census (the V5 discipline, machine-checked) -----------


class TestCensus:
    def test_no_guards_no_reads_no_filters_every_place_owned(self) -> None:
        built = build_net_v5()
        assert built.guards == {}
        assert all(str(a.mode) == "consume" for a in built.net.arcs)
        assert all(getattr(a, "filter", None) is None for a in built.net.arcs)
        for place in built.net.places:
            owner = str(place).split(".", 1)
            assert len(owner) == 2 and owner[0], f"unowned place {place}"

    def test_ingress_doors_are_the_only_no_input_transitions(self) -> None:
        built = build_net_v5()
        doors = {str(t) for t in built.net.transitions if not any(str(a.target) == str(t) for a in built.net.arcs)}
        assert doors == {
            "on_head",
            "on_draft",
            "on_ready",
            "on_close",
            "on_comment",
            "on_human",
            "on_runs",
            "on_provisional",
            "on_echo",
        }
