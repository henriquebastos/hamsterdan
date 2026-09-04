"""Executable contract tests for the V5 lifecycle (admission) loop.

The lifecycle loop is the single admission hub of the V5 actor-loop
topology: it owns the LifeState baton, absorbs every host-normalized
observation through ingress doors, and mails typed facts to sibling
loop mailboxes. No guards, no read arcs — every decision is a pure
fold on token data (the ES-007 discipline, now first-class).
"""

from harness import (
    comment_held,
    deliver,
    deliver_held,
    one,
    projection,
    see_head,
    see_run,
    spawn,
    spawn_held,
    tokens,
    world_of,
)

from hamsterdan.readiness.net_v5 import build_net_v5


def land_repair(engine) -> None:
    """A REAL landed repair: the first failing attempt burns the rerun,
    the second opens escalation's repair rung, whose push lands and
    installs the provisional expectation `h1+repair:L1:fp1`."""
    for attempt in (1, 2):
        see_run(engine, head="h1", run_id=1, attempt=attempt, conclusion="failure", fingerprint="fp1")


def settle_reminder_close(engine) -> None:
    arm = one(engine, "rem.commands")
    deliver(
        engine,
        "on_timer_command_applied",
        "TimerCommandApplied",
        {
            "operation": arm["operation"],
            "result": {
                "kind": "armed",
                "timer": arm["command"]["timer"],
                "due_at": "2026-08-16T00:00:00Z",
            },
        },
    )
    cancel = one(engine, "rem.commands")
    deliver(
        engine,
        "on_timer_command_applied",
        "TimerCommandApplied",
        {
            "operation": cancel["operation"],
            "result": {"kind": "cancelled", "timer": cancel["command"]["timer"]},
        },
    )


# -- admission relations ---------------------------------------------------


class TestHeadAdmission:
    def test_first_head_admits_as_new_with_incarnation_one(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        state = one(engine, "life.state")
        assert state["phase"] == "running"
        assert state["incarnation"] == 1
        assert state["head"] == "h1"
        # the review loop consumed its admission mail: relation "new"
        # opened ONE agent round under incarnation 1 (the effect identity
        # proves the claim the mail carried)
        world = world_of(engine)
        assert world["agent_calls"] == 1
        assert [c["key"] for c in world["comments"]] == ["findings:h1:i1"]
        # the CI loop consumed its copy of the admission mail
        assert one(engine, "ci.state")["incarnation"] == 1

    def test_same_head_reobservation_is_absorbed(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_head(engine, "h1")
        assert one(engine, "life.state")["incarnation"] == 1
        # absorbed: no second admission mail, so no second agent round
        assert world_of(engine)["agent_calls"] == 1

    def test_base_refresh_keeps_incarnation_and_mails_refreshed(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1")
        see_head(engine, "h1", base="b2")
        state = one(engine, "life.state")
        assert state["incarnation"] == 1
        assert state["base"] == "b2"
        # the refreshed relation opens NO new agent round (same head,
        # same lifetime); with nothing provisional there is nothing to
        # republish either
        world = world_of(engine)
        assert world["agent_calls"] == 1
        assert [c["key"] for c in world["comments"]] == ["findings:h1:i1"]

    def test_new_head_supersedes_with_fresh_lineage(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        see_head(engine, "h2")
        state = one(engine, "life.state")
        assert state["incarnation"] == 2
        assert state["head"] == "h2"
        # superseded: a fresh agent round under the new incarnation, and
        # a fresh CI budget lineage (superseded mails lineage "")
        world = world_of(engine)
        assert world["agent_calls"] == 2
        assert [c["key"] for c in world["comments"]][-1] == "findings:h2:i2"
        assert one(engine, "ci.state")["lineage"] == "L2"

    def test_expected_head_admits_as_confirmed_keeping_lineage(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        # the escalation/mutation loops push for real: the landed repair
        # mails the provisional expectation, the webhook later confirms
        land_repair(engine)
        assert one(engine, "life.state")["expected"] == "h1+repair:L1:fp1"
        see_head(engine, "h1+repair:L1:fp1")
        state = one(engine, "life.state")
        assert state["incarnation"] == 2
        assert state["expected"] == ""
        # confirmed: our own repair does NOT reset the CI budget lineage
        # (contrast supersession, which mints a fresh one)
        assert one(engine, "ci.state")["lineage"] == "L1"
        # and the confirmed head still opened its own agent round
        assert world_of(engine)["agent_calls"] == 2


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
        assert world_of(engine)["agent_calls"] == 1  # no round while dormant
        deliver(engine, "on_ready", "ReadySeen", {})
        state = one(engine, "life.state")
        assert state["phase"] == "running"
        assert state["incarnation"] == 2
        # resume re-admitted the recorded head: a fresh agent round under
        # the resumed incarnation
        world = world_of(engine)
        assert world["agent_calls"] == 2
        assert [c["key"] for c in world["comments"]][-1] == "findings:h2:i2"

    def test_ready_without_quiescence_is_absorbed(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_ready", "ReadySeen", {})
        assert one(engine, "life.state")["incarnation"] == 1

    def test_resume_clears_a_provisional_expectation(self) -> None:
        # a push lands, its expectation is installed, and the PR drafts
        # BEFORE the pushed head's webhook arrives: dormancy records the
        # head without admission (expected retained). Resume must clear
        # the expectation — running with `head == expected` would mark
        # every later committing intent provisional forever
        engine, _ = spawn()
        see_head(engine, "h1")
        land_repair(engine)
        assert one(engine, "life.state")["expected"] == "h1+repair:L1:fp1"
        deliver(engine, "on_draft", "DraftSeen", {})
        see_head(engine, "h1+repair:L1:fp1")  # recorded while dormant
        deliver(engine, "on_ready", "ReadySeen", {})
        state = one(engine, "life.state")
        assert state["phase"] == "running"
        assert state["expected"] == ""  # cleared at the resume boundary
        assert state["expected_op"] == ""
        assert state["lineage"] == ""  # accepted loss across the grant move


class TestClose:
    def test_close_goes_terminal_and_fans_out_to_every_loop(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        assert one(engine, "life.state")["phase"] == "terminal"
        # every loop consumed its close mail and retired
        assert one(engine, "ci.done")["reason"] == "merged"
        assert one(engine, "esc.done")["reason"] == "merged"
        assert one(engine, "review.done")["reason"] == "merged"
        assert one(engine, "mut.done")["reason"] == "merged"
        assert one(engine, "dash.done")["reason"] == "merged"
        settle_reminder_close(engine)
        assert one(engine, "rem.done")["reason"] == "merged"
        assert one(engine, "ready.done")["reason"] == "merged"

    def test_terminal_absorbs_every_later_observation(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        see_head(engine, "h2")
        deliver(engine, "on_close", "CloseSeen", {"reason": "closed"})
        state = one(engine, "life.state")
        assert state["phase"] == "terminal"
        assert state["head"] == "h1"
        assert len(tokens(engine, "review.done")) == 1


class TestObservationRouting:
    def test_comment_mails_an_intent_carrying_the_authority_claim(self) -> None:
        # the conversation loop consumes the intent, so the claim frozen
        # at admission is observed where it lands: a committing intent's
        # gate work carries the FULL claim of the moment the comment was
        # admitted — head, base, policy, incarnation — under the
        # comment's identity
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=frozenset({"git_gate"}),
        )
        comment_held(engine, dispatch, definitions, "c1", "change", hold=frozenset({"git_gate"}))
        [invocation] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        work = invocation.input["work"]
        assert work["op_key"] == "push:comment:c1:h1:i1"
        assert work["head"] == "h1"
        assert work["base"] == "b1"
        assert work["policy"] == "p1"
        assert work["incarnation"] == 1

    def test_human_review_becomes_a_gate_fact_for_ready_and_dash(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(
            engine,
            "on_human",
            "HumanSeen",
            {"approval": True, "changes_requested": False, "unresolved": 0},
        )
        facts = [f for f in projection(engine) if f["kind"] == "human"]
        assert facts[-1]["body"]["approval"] is True
        assert one(engine, "ready.snap")["approval"] is True

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
        [fact] = [f for f in projection(engine) if f["kind"] == "state"]
        assert fact["body"]["head"] == "h1"
        assert fact["body"]["phase"] == "running"
        st = one(engine, "ready.snap")
        assert st["head"] == "h1"
        assert st["phase"] == "running"


# -- the structural census (the V5 discipline, machine-checked) -----------


class TestCensus:
    def test_no_guards_no_reads_filters_only_legacy_migration_every_place_owned(self) -> None:
        built = build_net_v5()
        assert built.guards == {}
        # The deliberate exceptions to all-consume make readiness ordering
        # explicit: both authorization points require every typed mailbox
        # plus close to be quiet, and incarnation-scoped facts wait for
        # already-mailed state authority to fold first.
        exceptional = {(str(a.source), str(a.mode), str(a.target)) for a in built.net.arcs if str(a.mode) != "consume"}
        fact_mailboxes = {
            "state",
            "checks",
            "review",
            "findings",
            "human",
            "mutation_pending",
            "mutation_settled",
            "fault_raised",
            "fault_cleared",
        }
        authorization_points = {"authorize", "wake_deferred"}
        expected = (
            {
                (f"ready.{mailbox}_facts", "inhibit", f"ready.{transition}")
                for mailbox in fact_mailboxes
                for transition in authorization_points
            }
            | {
                (source, "inhibit", f"ready.{transition}")
                for source in ("ready.facts", "ready.closed")
                for transition in authorization_points
            }
            | {
                ("ready.state_facts", "inhibit", f"ready.fold_{mailbox}")
                for mailbox in fact_mailboxes
                if mailbox not in {"state", "fault_raised", "fault_cleared"}
            }
            | {
                ("ready.mutation_pending_facts", "inhibit", "ready.fold_mutation_settled"),
                ("ready.fault_cleared_facts", "inhibit", "ready.fold_fault_raised"),
            }
            | {
                ("ready.facts", "inhibit", f"ready.migrate_{mailbox}")
                for mailbox in fact_mailboxes
                if mailbox not in {"state", "fault_raised", "fault_cleared"}
            }
            | {
                ("ready.facts", "inhibit", "ready.migrate_mutation_settled"),
                ("ready.facts", "inhibit", "ready.migrate_fault_raised"),
            }
            | {
                ("startup.pending", "inhibit", transition)
                for transition in (
                    "startup.absorb_update",
                    "review.agent",
                    "review.publish",
                    "esc.rerun_gate",
                    "mut.git_gate",
                    "conv.reply",
                    "rem.gate",
                    "ready.gate",
                )
            }
        )
        assert exceptional == expected
        filtered_arcs = [arc for arc in built.net.arcs if arc.filter is not None]
        filtered = {(str(arc.source), str(arc.mode), str(arc.target)) for arc in filtered_arcs}
        assert len(filtered_arcs) == 17
        assert filtered == {
            *(("ready.facts", "consume", f"ready.migrate_{mailbox}") for mailbox in fact_mailboxes),
            *(("ready.facts", "inhibit", f"ready.migrate_{mailbox}") for mailbox in fact_mailboxes),
        } - {
            ("ready.facts", "inhibit", "ready.migrate_state"),
            ("ready.facts", "inhibit", "ready.migrate_fault_cleared"),
        }
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
            "on_announce_wake",
            "on_review_round_wake",
            "on_timer",
            "on_timer_command_applied",
        }
