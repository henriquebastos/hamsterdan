"""Executable contract tests for the V5 conversation loop.

The conversation loop owns the ConvMemory baton and NEVER ends: a human
may talk to the PR in any lifecycle phase, including after close. Each
comment arrives as an IntentFact carrying the authority claim frozen at
admission; `classify` grades it (pure / note / committing), routes the
side facts to the owning loops, and always answers through the reply
gate under the stable effect identity `reply:{comment_id}` — replies
are deliberately concurrent (per-id custody), lookup-first reconciled
(A2), with blocked/faulted text retained for exact recovery.
"""

from harness import (
    comment,
    comment_held,
    deliver,
    one,
    see_head,
    spawn,
    spawn_held,
    tokens,
    world_of,
)


def memory(engine) -> dict:
    return one(engine, "conv.memory")


def replies(world: dict) -> list[dict]:
    return [c for c in world["comments"] if c["kind"] == "reply"]


def reply_texts(world: dict) -> dict[str, str]:
    return {c["key"]: c["body"] for c in replies(world)}


# -- classification -----------------------------------------------------------


class TestClassification:
    def test_a_pure_intent_is_answered_and_served_once(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "status")
        world = world_of(engine)
        assert reply_texts(world) == {"reply:c1": "answer:status"}
        state = memory(engine)
        assert state["served"] == ["c1"]
        assert state["pending"] == {}  # custody returned

    def test_a_duplicate_comment_identity_is_served_once(self) -> None:
        # an edited comment redelivers the SAME id: one reply, ever
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "status")
        comment(engine, "c1", "status")
        world = world_of(engine)
        assert len(replies(world)) == 1
        assert memory(engine)["served"] == ["c1"]

    def test_an_unauthorized_command_routes_no_side_effect(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "change", authorized=False)
        world = world_of(engine)
        assert world["pushes"] == []
        assert tokens(engine, "mut.requests") == []
        assert reply_texts(world) == {"reply:c1": "no workflow change"}

    def test_an_unknown_kind_gets_the_no_change_reply(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "make-coffee")
        assert reply_texts(world_of(engine)) == {"reply:c1": "no workflow change"}

    def test_a_pure_intent_is_answered_even_after_close(self) -> None:
        # the conversation loop NEVER ends: close retires the workflow
        # loops, not the human's ability to ask questions
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        comment(engine, "c1", "reply")
        assert reply_texts(world_of(engine)) == {"reply:c1": "answer:reply"}


# -- note intents (routed facts) ----------------------------------------------


class TestNoteIntents:
    def test_dismiss_routes_the_finding_to_review(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")  # the agent posts finding f-h1
        comment(engine, "c1", "dismiss", arg="f-h1")
        assert reply_texts(world_of(engine))["reply:c1"] == "noted:dismiss"
        assert one(engine, "review.memory")["dismissed"] == ["f-h1"]

    def test_snooze_resume_and_defer_mail_the_reminder_loop(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "snooze", arg="t1")
        comment(engine, "c2", "resume", arg="t1")
        comment(engine, "c3", "defer", arg="t2")
        assert tokens(engine, "rem.snoozes") == [
            {"mode": "snooze", "arg": "t1"},
            {"mode": "clear", "arg": "t1"},
            {"mode": "defer", "arg": "t2"},
        ]

    def test_a_note_intent_in_terminal_phase_is_declined(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        comment(engine, "c1", "dismiss", arg="f-h1")
        assert reply_texts(world_of(engine))["reply:c1"] == "declined:dismiss:terminal"
        assert tokens(engine, "review.dismiss") == []

    def test_recover_publication_routes_by_operation_prefix(self) -> None:
        # a blocked review publication recovers through the conversation
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        see_head(engine, "h1")
        assert one(engine, "review.memory")["pub"]["phase"] == "blocked"
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", arg="findings:h1:i1")
        assert one(engine, "review.memory")["pub"] == {"phase": "idle"}
        findings = [c for c in world["comments"] if c["kind"] == "findings"]
        assert [c["key"] for c in findings] == ["findings:h1:i1"]
        assert reply_texts(world)["reply:c1"] == "noted:recover_publication"

    def test_recover_publication_with_an_unknown_prefix_is_declined(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "recover_publication", arg="bogus:xyz")
        assert reply_texts(world_of(engine))["reply:c1"] == "declined:recover_publication:unknown-target"


# -- committing intents --------------------------------------------------------


class TestCommittingIntents:
    def test_change_mails_a_full_claim_under_the_comment_identity(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "change")
        world = world_of(engine)
        # rid = comment identity: the operation key is producer-stable
        assert world["pushes"] == [{"key": "push:comment:c1:h1:i1", "op": "change", "from": "h1", "to": "h1+change"}]
        assert reply_texts(world)["reply:c1"] == "started:change"

    def test_a_committing_intent_outside_running_is_declined(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_draft", "DraftSeen", {})
        comment(engine, "c1", "change")
        world = world_of(engine)
        assert world["pushes"] == []
        assert tokens(engine, "mut.requests") == []
        assert reply_texts(world)["reply:c1"] == "declined:change:quiescent"

    def test_a_committing_intent_under_a_provisional_head_is_declined(self) -> None:
        # our own push is in flight between the land and its webhook:
        # further mutations are declined BEFORE any gate attempt (A4.3)
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "change")  # lands; lifecycle expects h1+change
        assert one(engine, "life.state")["expected"] == "h1+change"
        comment(engine, "c2", "update_base")
        world = world_of(engine)
        assert reply_texts(world)["reply:c2"] == "declined:update_base:provisional"
        assert len(world["pushes"]) == 1
        # the expected webhook arrives: committing intents flow again
        see_head(engine, "h1+change")
        comment(engine, "c3", "update_base")
        assert reply_texts(world)["reply:c3"] == "started:update_base"
        assert len(world["pushes"]) == 2

    def test_a_committing_intent_after_close_is_declined(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        comment(engine, "c1", "change")
        world = world_of(engine)
        assert world["pushes"] == []
        assert reply_texts(world)["reply:c1"] == "declined:change:terminal"


# -- the reply gate ------------------------------------------------------------


class TestReplyGate:
    def test_lookup_first_a_reply_already_held_never_posts_twice(self) -> None:
        # a previous life posted the reply and died before the ack
        engine, _ = spawn()
        see_head(engine, "h1")
        world = world_of(engine)
        world["comments"].append({"key": "reply:c1", "kind": "reply", "head": "", "body": "answer:status"})
        comment(engine, "c1", "status")
        assert len(replies(world)) == 1  # NO duplicate post
        assert memory(engine)["pending"] == {}

    def test_retryable_exhaustion_blocks_and_retains_the_text(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        world = world_of(engine)
        world["comments_mode"] = "retryable"
        comment(engine, "c1", "status")
        state = memory(engine)
        assert state["blocked"] == {"c1": "answer:status"}
        assert state["pending"] == {}
        assert replies(world) == []
        # recovery reissues the SAME identity with the retained text
        world["comments_mode"] = None
        comment(engine, "c2", "recover_publication", arg="reply:c1")
        assert reply_texts(world)["reply:c1"] == "answer:status"
        state = memory(engine)
        assert state["blocked"] == {}
        assert state["pending"] == {}

    def test_unknown_terminal_faults_and_recovery_reconciles_lookup_first(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        comment(engine, "c1", "status")
        state = memory(engine)
        assert state["faulted"] == {"c1": {"text": "answer:status", "reason": "unknown provider terminal"}}
        [fault] = [f for f in tokens(engine, "dash.facts") if f["kind"] == "fault"]
        assert fault["body"] == {
            "where": "conversation",
            "op": "reply:c1",
            "status": "faulted",
            "reason": "unknown provider terminal",
        }
        # the provider DID hold it: recovery must not post a second copy
        world["comments_mode"] = None
        world["comments"].append({"key": "reply:c1", "kind": "reply", "head": "", "body": "answer:status"})
        comment(engine, "c2", "recover_publication", arg="reply:c1")
        assert len(replies(world)) == 2  # c1 reconciled + c2's own reply
        state = memory(engine)
        assert state["faulted"] == {}
        # the settle emits the operation-keyed resolution for the dashboard
        resolutions = [f["body"] for f in tokens(engine, "dash.facts") if f["kind"] == "fault"]
        assert resolutions[-1] == {"where": "conversation", "op": "reply:c1", "status": "resolved"}

    def test_recovery_is_single_flight_per_identity(self) -> None:
        # two humans command recovery of the same faulted reply while
        # the first reissue is still in flight: a second concurrent
        # occurrence could double-post (both gate calls would observe
        # "absent") — the second recovery must be inert
        engine, _, dispatch, definitions = spawn_held()
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        comment_held(engine, dispatch, definitions, "c1", "status")
        assert "c1" in memory(engine)["faulted"]
        world["comments_mode"] = None
        hold = frozenset({"reply_gate"})
        comment_held(engine, dispatch, definitions, "r1", "recover_publication", arg="reply:c1", hold=hold)
        comment_held(engine, dispatch, definitions, "r2", "recover_publication", arg="reply:c1", hold=hold)
        reissues = [
            i for i in dispatch.pending.values() if i.activity == "reply_gate" and i.input["work"]["id"] == "c1"
        ]
        assert len(reissues) == 1  # ONE occurrence in flight, ever

    def test_a_reply_identity_collision_with_different_text_fails_closed(self) -> None:
        # the identity exists but holds DIFFERENT content: lookup-first
        # must not claim this text landed — the gate faults instead of
        # lying `resolved`
        engine, _ = spawn()
        see_head(engine, "h1")
        world = world_of(engine)
        world["comments"].append({"key": "reply:c1", "kind": "reply", "head": "", "body": "something else"})
        comment(engine, "c1", "status")  # would answer "answer:status"
        state = memory(engine)
        assert state["faulted"]["c1"]["reason"] == "effect identity collision: reply:c1"
        assert reply_texts(world)["reply:c1"] == "something else"  # untouched

    def test_recovery_for_an_unknown_reply_is_inert(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        before_served = memory(engine)["served"]
        comment(engine, "c1", "recover_publication", arg="reply:zz")
        state = memory(engine)
        assert state["blocked"] == {}
        assert state["faulted"] == {}
        assert state["served"] == [*before_served, "c1"]

    def test_replies_are_concurrent_per_id_custody(self) -> None:
        # two questions in flight at once: neither holds the other's
        # custody — pending is per-id, unlike the one-at-a-time batons
        engine, _, dispatch, definitions = spawn_held()
        comment_held(engine, dispatch, definitions, "c1", "status", hold=frozenset({"reply_gate"}))
        comment_held(engine, dispatch, definitions, "c2", "reply", hold=frozenset({"reply_gate"}))
        assert memory(engine)["pending"] == {"c1": "answer:status", "c2": "answer:reply"}
        pending = [i for i in dispatch.pending.values() if i.activity == "reply_gate"]
        assert len(pending) == 2
