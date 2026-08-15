"""Executable contract tests for the V5 review loop.

The review loop owns the ReviewMemory baton: one durable review memory
per PR. Each admitted head opens ONE credential-less agent round; live
findings publish under the stable effect identity `findings:{head}:i{inc}`
with full authority fencing (A1.5) and lookup-first reconciliation (A2).
A MOVED publication retains its findings provisionally: the next
refreshed authority republishes them under the SAME identity without a
new agent round; a superseding head feeds them into its fresh round.
The baton is HELD through every in-flight round.
"""

from harness import (
    comment,
    comment_held,
    deliver,
    deliver_held,
    one,
    pump,
    release_one,
    see_head,
    spawn,
    spawn_held,
    tokens,
    world_of,
)

HOLD_AGENT = frozenset({"review_agent"})
HOLD_PUBLISH = frozenset({"publish_gate"})

FINDING_H1 = {"id": "f-h1", "note": "finding:h1", "blocking": True}


def memory(engine) -> dict:
    return one(engine, "review.memory")


def findings_facts(engine) -> list[dict]:
    return [f for f in tokens(engine, "ready.facts") if f["kind"] == "findings"]


def findings_comments(world: dict) -> list[dict]:
    """The provider's FINDINGS posts (the conversation loop's replies
    share the same comment store)."""
    return [c for c in world["comments"] if c["kind"] == "findings"]


def comment_keys(world: dict) -> list[str]:
    return [c["key"] for c in findings_comments(world)]


# -- the agent round --------------------------------------------------------


class TestAgentRound:
    def test_first_head_opens_one_round_and_lands_one_publication(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        world = world_of(engine)
        assert world["agent_calls"] == 1
        assert comment_keys(world) == ["findings:h1:i1"]
        assert findings_comments(world)[0]["body"] == [FINDING_H1]
        state = memory(engine)
        assert state["reviewed"] == ["h1"]
        assert state["findings"] == [FINDING_H1]
        assert state["provisional"] == []
        assert state["pub"] == {"phase": "idle"}
        fact = findings_facts(engine)[-1]
        assert fact["incarnation"] == 1
        assert fact["body"] == {"head": "h1", "blocking": 1, "count": 1}

    def test_empty_review_settles_without_publication(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        assert findings_comments(world) == []
        state = memory(engine)
        assert state["reviewed"] == ["h1"]
        assert state["findings"] == []
        fact = findings_facts(engine)[-1]
        assert fact["body"] == {"head": "h1", "blocking": 0, "count": 0}

    def test_dismissed_findings_are_filtered_before_publication(self) -> None:
        engine, _ = spawn()
        comment(engine, "dis1", "dismiss", arg="f-h1")
        see_head(engine, "h1")
        world = world_of(engine)
        assert world["agent_calls"] == 1
        assert findings_comments(world) == []  # every finding filtered: nothing to post
        state = memory(engine)
        assert state["reviewed"] == ["h1"]
        assert state["dismissed"] == ["f-h1"]

    def test_agent_sees_only_its_work_token(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD_AGENT,
        )
        [invocation] = [i for i in dispatch.pending.values() if i.activity == "review_agent"]
        assert set(invocation.input) == {"work"}
        # the claim plus the HELD baton — no credential, no world handle
        assert set(invocation.input["work"]) == {"head", "base", "policy", "incarnation", "mem"}
        release_one(engine, dispatch, definitions, "review_agent")
        assert memory(engine)["reviewed"] == ["h1"]


# -- publication identity and terminals --------------------------------------


class TestPublication:
    def test_lookup_first_reconciles_an_already_landed_publication(self) -> None:
        # the crash hit after the provider accepted the comment: the
        # reissued round must reconcile as landed, never post twice
        engine, _ = spawn()
        world = world_of(engine)
        world["comments"].append({"key": "findings:h1:i1", "kind": "findings", "head": "h1", "body": [FINDING_H1]})
        see_head(engine, "h1")
        assert comment_keys(world) == ["findings:h1:i1"]  # still exactly one
        assert [e for e in world["log"] if e[0] == "comment"] == []  # no new effect
        assert memory(engine)["reviewed"] == ["h1"]

    def test_effect_identity_collision_fails_closed(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments"].append({"key": "findings:h1:i1", "kind": "findings", "head": "h1", "body": [{"id": "x"}]})
        see_head(engine, "h1")
        state = memory(engine)
        assert state["pub"]["phase"] == "faulted"
        assert "collision" in state["pub"]["reason"]
        assert state["pub"]["op"] == "findings:h1:i1"  # the EXACT operation retained
        assert state["reviewed"] == ["h1"]  # the ROUND completed; the publication did not
        [fault] = [f for f in tokens(engine, "dash.facts") if f["kind"] == "fault"]
        assert fault["body"]["where"] == "review"
        assert fault["body"]["op"] == "findings:h1:i1"  # operation-keyed
        assert fault["body"]["status"] == "faulted"

    def test_retryable_exhaustion_blocks_and_recovery_reissues_the_same_operation(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        see_head(engine, "h1")
        state = memory(engine)
        assert state["pub"]["phase"] == "blocked"
        assert state["pub"]["op"] == "findings:h1:i1"
        assert world["comment_attempts"] == 3  # bounded retry, ONE occurrence
        assert state["reviewed"] == ["h1"]  # the round completed
        # the blocked findings still reach readiness/dashboard honestly
        assert findings_facts(engine)[-1]["body"]["blocking"] == 1
        world["comments_mode"] = None
        comment(engine, "rec1", "recover_publication", arg="findings:h1:i1")
        assert comment_keys(world) == ["findings:h1:i1"]  # SAME identity, once
        assert world_of(engine)["agent_calls"] == 1  # recovery reruns NO agent
        state = memory(engine)
        assert state["pub"] == {"phase": "idle"}
        assert state["reviewed"] == ["h1"]

    def test_unknown_terminal_faults_closed_and_recovery_reissues(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        see_head(engine, "h1")
        state = memory(engine)
        assert state["pub"]["phase"] == "faulted"
        assert state["pub"]["findings"] == [FINDING_H1]  # the EXACT request (A2)
        assert findings_comments(world) == []
        world["comments_mode"] = None
        comment(engine, "rec2", "recover_publication", arg="findings:h1:i1")
        assert comment_keys(world) == ["findings:h1:i1"]
        state = memory(engine)
        assert state["pub"] == {"phase": "idle"}
        assert "reason" not in state["pub"]
        assert state["reviewed"] == ["h1"]

    def test_fault_recovery_emits_an_operation_keyed_resolution(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        see_head(engine, "h1")
        world["comments_mode"] = None
        comment(engine, "rec3", "recover_publication", arg="findings:h1:i1")
        # the settle CLEARS the fault: readiness never stays fail-closed
        # after the human's recovery actually succeeded
        faults = [f["body"] for f in tokens(engine, "ready.facts") if f["kind"] == "fault"]
        assert faults[-1] == {"where": "review", "op": "findings:h1:i1", "status": "resolved"}
        assert comment_keys(world) == ["findings:h1:i1"]

    def test_recovery_for_another_loop_or_operation_is_inert(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        see_head(engine, "h1")
        world["comments_mode"] = None
        # the operation prefix routes to escalation: review never sees it
        comment(engine, "rec4", "recover_publication", arg="rerun:L1:fp1")
        comment(engine, "rec5", "recover_publication", arg="findings:h9:i9")
        state = memory(engine)
        assert state["pub"]["phase"] == "blocked"  # untouched
        assert findings_comments(world) == []
        assert world["comment_attempts"] == 3  # no reissue happened


# -- authority movement and provisional findings ------------------------------


class TestAuthorityMovement:
    def test_moved_publication_feeds_provisionals_into_the_superseding_round(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD_PUBLISH,
        )
        # the head moves WHILE h1's publication is in flight
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h2", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD_PUBLISH,
        )
        world = world_of(engine)
        assert findings_comments(world) == []  # nothing landed while held
        # release h1's publish: the gate observes h2 → MOVED; the fold
        # retains the findings provisionally; the queued superseding
        # admission then opens h2's round, which carries them forward
        release_one(engine, dispatch, definitions, "publish_gate")
        assert world["agent_calls"] == 2
        assert comment_keys(world) == ["findings:h2:i2"]  # NO stale h1 comment
        [comment] = world["comments"]
        assert [f["id"] for f in comment["body"]] == ["f-h1", "f-h2"]
        state = memory(engine)
        assert state["reviewed"] == ["h1", "h2"]  # BOTH rounds completed
        assert state["provisional"] == []

    def test_base_refresh_republishes_provisionals_without_a_new_agent_round(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD_PUBLISH,
        )
        # the BASE moves while h1's publication is in flight: same head,
        # same incarnation, refreshed authority
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b2", "mergeable": True, "policy": "p1"},
            hold=HOLD_PUBLISH,
        )
        release_one(engine, dispatch, definitions, "publish_gate")
        world = world_of(engine)
        assert world["agent_calls"] == 1  # refresh reran NO agent
        assert comment_keys(world) == ["findings:h1:i1"]  # SAME identity, once
        state = memory(engine)
        assert state["reviewed"] == ["h1"]
        assert state["provisional"] == []
        assert state["pub"] == {"phase": "idle"}

    def test_a_blocked_publication_holds_exclusive_custody_of_its_findings(self) -> None:
        # provisional findings folded into a round belong to THAT round's
        # publication: while its blocked descriptor retains them, no
        # refresh may republish a diverging subset under the same identity
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD_PUBLISH,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h2", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD_PUBLISH,
        )
        world = world_of(engine)
        # settle ONLY h1's publish (MOVED, retaining f-h1); h2's round
        # runs and its own publication stays held
        [(occurrence, invocation)] = [(o, i) for o, i in dispatch.pending.items() if i.activity == "publish_gate"]
        dispatch.complete(occurrence, definitions["publish_gate"](invocation, context=None))
        pump(engine, dispatch, definitions, hold=HOLD_PUBLISH)
        # h2's merged publication [f-h1, f-h2] exhausts its retries
        world["comments_mode"] = "retryable"
        release_one(engine, dispatch, definitions, "publish_gate")
        state = memory(engine)
        assert state["pub"]["phase"] == "blocked"
        assert [f["id"] for f in state["pub"]["findings"]] == ["f-h1", "f-h2"]
        assert state["provisional"] == []  # custody is EXCLUSIVE
        # a refresh republishes NOTHING while the descriptor owns them
        world["comments_mode"] = None
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h2", "base": "b2", "mergeable": True, "policy": "p1"},
        )
        assert findings_comments(world) == []
        assert memory(engine)["pub"]["phase"] == "blocked"
        # recovery reissues the EXACT operation; its stale base claim
        # MOVES, restoring the COMPLETE findings to provisional custody
        comment_held(engine, dispatch, definitions, "rec1", "recover_publication", arg="findings:h2:i2")
        state = memory(engine)
        assert state["pub"] == {"phase": "idle"}
        assert [f["id"] for f in state["provisional"]] == ["f-h1", "f-h2"]
        # the next refresh republishes the complete list, SAME identity
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h2", "base": "b3", "mergeable": True, "policy": "p1"},
        )
        assert comment_keys(world) == ["findings:h2:i2"]
        assert [f["id"] for f in findings_comments(world)[0]["body"]] == ["f-h1", "f-h2"]
        assert world["agent_calls"] == 2  # recovery and refresh reran NO agent

    def test_refresh_with_nothing_provisional_republishes_nothing(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1", base="b1")
        see_head(engine, "h1", base="b2")
        world = world_of(engine)
        assert world["agent_calls"] == 1
        assert comment_keys(world) == ["findings:h1:i1"]

    def test_dismissed_provisional_findings_never_republish(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD_PUBLISH,
        )
        # the PR goes draft while publishing: MOVED, findings retained
        deliver_held(engine, dispatch, definitions, "on_draft", "DraftSeen", {}, hold=HOLD_PUBLISH)
        release_one(engine, dispatch, definitions, "publish_gate")
        assert memory(engine)["provisional"] == [FINDING_H1]
        # the human waves the finding off during dormancy
        comment_held(engine, dispatch, definitions, "dis1", "dismiss", arg="f-h1")
        # resume opens a fresh round; the agent echoes the provisional
        # PLUS its fresh duplicate — the judge filters both
        deliver_held(engine, dispatch, definitions, "on_ready", "ReadySeen", {})
        world = world_of(engine)
        assert world["agent_calls"] == 2
        assert findings_comments(world) == []
        assert memory(engine)["reviewed"] == ["h1"]


# -- dismissal facts and close ------------------------------------------------


class TestDismissalAndClose:
    def test_a_dismiss_that_lost_the_race_with_close_is_never_stranded(self) -> None:
        # the dismiss was ADMITTED while running, but its apply waits on
        # the memory baton a held publication carries in flight; close
        # arrives during the wait. Whichever wins the returned baton —
        # the apply or the retire — no token may strand in the mailbox
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD_PUBLISH,
        )
        assert tokens(engine, "review.memory") == []  # baton in flight
        comment_held(engine, dispatch, definitions, "d1", "dismiss", arg="f-h1", hold=HOLD_PUBLISH)
        assert len(tokens(engine, "review.dismiss")) == 1  # parked, waiting
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=HOLD_PUBLISH)
        release_one(engine, dispatch, definitions, "publish_gate")
        assert tokens(engine, "review.dismiss") == []  # applied or drained
        [ended] = tokens(engine, "review.done")
        assert ended["reason"] == "merged"

    def test_dismissal_cancels_a_retained_blocked_operation(self) -> None:
        # the human waved off a finding the blocked operation carries:
        # the operation is CANCELLED — recovery must never republish it
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        see_head(engine, "h1")
        assert memory(engine)["pub"]["phase"] == "blocked"
        comment(engine, "dis2", "dismiss", arg="f-h1")
        state = memory(engine)
        assert state["pub"]["phase"] == "cancelled"
        assert state["pub"]["op"] == "findings:h1:i1"  # retained for audit
        world["comments_mode"] = None
        comment(engine, "rec5", "recover_publication", arg="findings:h1:i1")
        assert findings_comments(world) == []  # recovery is INERT
        assert world["comment_attempts"] == 3  # no reissue happened
        assert memory(engine)["pub"]["phase"] == "cancelled"

    def test_dismissal_cancels_a_faulted_operation_and_clears_its_fault(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        see_head(engine, "h1")
        comment(engine, "dis3", "dismiss", arg="f-h1")
        state = memory(engine)
        assert state["pub"]["phase"] == "cancelled"
        faults = [f["body"] for f in tokens(engine, "ready.facts") if f["kind"] == "fault"]
        assert faults[-1] == {"where": "review", "op": "findings:h1:i1", "status": "cancelled"}
        world["comments_mode"] = None
        comment(engine, "rec6", "recover_publication", arg="findings:h1:i1")
        assert findings_comments(world) == []  # the cancelled operation never posts

    def test_dismissal_recounts_blocking_findings_for_readiness(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        assert findings_facts(engine)[-1]["body"]["blocking"] == 1
        comment(engine, "dis4", "dismiss", arg="f-h1")
        fact = findings_facts(engine)[-1]
        assert fact["body"]["blocking"] == 0
        assert fact["body"]["count"] == 1  # the finding remains, waved off

    def test_resume_after_landing_reviews_again_without_duplicating_reviewed(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_draft", "DraftSeen", {})
        deliver(engine, "on_ready", "ReadySeen", {})
        world = world_of(engine)
        assert world["agent_calls"] == 2  # resume opened a fresh round
        # each incarnation publishes under its OWN identity
        assert comment_keys(world) == ["findings:h1:i1", "findings:h1:i2"]
        assert memory(engine)["reviewed"] == ["h1"]  # membership, not a tally

    def test_close_retires_the_loop_with_its_terminal_record(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        [done] = tokens(engine, "review.done")
        assert done == {"reviewed": ["h1"], "pub_phase": "blocked", "reason": "merged"}
        assert tokens(engine, "review.memory") == []  # the baton retired

    def test_close_while_the_agent_is_in_flight_settles_cleanly(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD_AGENT,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_close",
            "CloseSeen",
            {"reason": "closed"},
            hold=HOLD_AGENT,
        )
        # the round completes against a terminal world: the publication
        # gate classifies MOVED (no stale comment lands), the baton
        # returns, and only then does close retire the loop
        release_one(engine, dispatch, definitions, "review_agent")
        world = world_of(engine)
        assert findings_comments(world) == []
        [done] = tokens(engine, "review.done")
        assert done["reason"] == "closed"
        assert done["reviewed"] == ["h1"]  # the round DID complete
        assert tokens(engine, "review.memory") == []
