"""Executable contract tests for the V5 mutation loop.

Mutation owns the MutState baton — the baton IS the one-at-a-time
serialization: a request consumes it into the round and only a terminal
fold returns it, so a second request waits visibly in its mailbox. The
git gate fences the head by server-side CAS and base/policy/grant by a
fresh read (A1.5), under the stable operation identity
`push:{rid}:{head}:i{inc}` — keyed by the producer's REQUEST identity,
not the semantic op — reconciled lookup-first (A2). A landed push
mails MutationSettled to escalation AND ProvisionalHead to lifecycle; a
faulted round retains the exact operation, declines all further
requests fail-closed, and the recovery door reissues the SAME identity.

Human requests arrive as PRODUCT comments: lifecycle admits each with
the claim frozen at admission, conversation classifies the committing
intent and mints the MutationRequest under the comment's identity
(`comment:{id}`). Stale-claim races are therefore STAGED, not forged —
hold the gate, move the world, release — exactly the shape the race has
in production.
"""

from harness import (
    comment,
    comment_held,
    deliver,
    deliver_held,
    one,
    projection,
    pump,
    release_one,
    see_head,
    see_run,
    spawn,
    spawn_held,
    tokens,
    world_of,
)

HOLD = frozenset({"git_gate"})


def see_head_held(engine, dispatch, definitions, head: str = "h1", hold=HOLD):
    deliver_held(
        engine,
        dispatch,
        definitions,
        "on_head",
        "HeadSeen",
        {"head": head, "base": "b1", "mergeable": True, "policy": "p1"},
        hold=hold,
    )


def settled_facts(engine) -> list[dict]:
    return [f["body"] for f in projection(engine) if f["kind"] == "mutation_settled"]


def pending_facts(engine) -> list[dict]:
    return [f["body"] for f in projection(engine) if f["kind"] == "mutation_pending"]


def pushes(engine) -> list[tuple]:
    return [e for e in world_of(engine)["log"] if e[0] == "push"]


class TestLandedPush:
    def test_a_comment_pushes_under_the_comments_stable_identity(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "change")
        world = world_of(engine)
        assert world["branch_head"] == "h1+change"
        assert world["pushes"] == [{"key": "push:comment:c1:h1:i1", "op": "change", "from": "h1", "to": "h1+change"}]
        assert one(engine, "mut.state")["state"] == "idle"  # the baton returned
        assert pending_facts(engine) == [{"op": "change", "op_key": "push:comment:c1:h1:i1"}]
        assert settled_facts(engine) == [
            {
                "op": "change",
                "op_key": "push:comment:c1:h1:i1",
                "outcome": "landed",
                "incarnation": 1,
                "fingerprint": "",
            }
        ]

    def test_a_landed_human_push_notes_the_provisional_head_with_lifecycle(self) -> None:
        # the expected-head note is what later admits OUR OWN push as
        # `confirmed` instead of `superseded`
        engine, _ = spawn()
        see_head(engine, "h1")
        comment(engine, "c1", "change")
        state = one(engine, "life.state")
        assert state["expected"] == "h1+change"
        assert state["expected_op"] == "change"
        assert state["lineage"] == ""  # human ops start no budget lineage

    def test_a_landed_repair_notes_the_provisional_head_with_its_lineage(self) -> None:
        # a REAL repair (escalation's rung after the rerun burns) keeps
        # the budget lineage through the provisional note
        engine, _ = spawn()
        see_head(engine, "h1")
        for attempt in (1, 2):  # rerun burns, then the repair pushes
            see_run(engine, head="h1", run_id=1, attempt=attempt, conclusion="failure", fingerprint="fp1")
        state = one(engine, "life.state")
        assert state["expected"] == "h1+repair:L1:fp1"
        assert state["expected_op"] == "repair:L1:fp1"
        assert state["lineage"] == "L1"  # derived from the repair's budget key
        # the settlement carries the escalation budget key
        assert settled_facts(engine)[-1]["fingerprint"] == "L1:fp1"

    def test_the_baton_serializes_requests_one_at_a_time(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", hold=HOLD)
        [invocation] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        assert invocation.input["work"]["op_key"] == "push:comment:c1:h1:i1"
        assert tokens(engine, "mut.state") == []  # the baton is HELD in flight
        # a second request cannot race the held round: it waits visibly
        comment_held(engine, dispatch, definitions, "c2", "update_base", hold=HOLD)
        assert len(tokens(engine, "mut.requests")) == 1
        assert len([i for i in dispatch.pending.values() if i.activity == "git_gate"]) == 1
        release_one(engine, dispatch, definitions, "git_gate")  # first lands
        pump(engine, dispatch, definitions)  # the queued round runs next
        # the first push moved the head, so the queued op classifies MOVED
        # at ITS OWN gate — serialized, fenced, never lost
        assert [s["outcome"] for s in settled_facts(engine)] == ["landed", "moved"]
        assert pushes(engine) == [("push", "push:comment:c1:h1:i1")]

    def test_two_distinct_requests_of_the_same_kind_never_share_an_identity(self) -> None:
        # two humans command a `change` at the same head: distinct
        # comment identities give distinct operation identities, so the
        # SECOND request must reach its OWN CAS refusal instead of
        # lookup-reconciling onto the first push's landed effect and
        # lying `landed`
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", hold=HOLD)
        comment_held(engine, dispatch, definitions, "c2", "change", hold=HOLD)  # queued
        release_one(engine, dispatch, definitions, "git_gate")  # c1 lands
        pump(engine, dispatch, definitions)  # c2's round runs next
        assert pushes(engine) == [("push", "push:comment:c1:h1:i1")]  # ONE effect
        assert [s["outcome"] for s in settled_facts(engine)] == ["landed", "moved"]


class TestAuthorityFencing:
    def test_cas_conflict_a_stale_head_claim_classifies_moved(self) -> None:
        # the head moves WHILE the push is in flight (webhook not yet
        # arrived): the claim was current at admission, the server-side
        # CAS is what refuses it
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", hold=HOLD)
        world_of(engine)["branch_head"] = "h2"  # someone else pushed
        release_one(engine, dispatch, definitions, "git_gate")
        assert pushes(engine) == []
        assert settled_facts(engine) == [
            {
                "op": "change",
                "op_key": "push:comment:c1:h1:i1",
                "outcome": "moved",
                "incarnation": 1,
                "fingerprint": "",
            }
        ]
        assert one(engine, "mut.state")["state"] == "idle"

    def test_a_moved_base_is_fenced_by_the_fresh_read_not_the_cas(self) -> None:
        # the provider's base moved but the webhook has not arrived yet:
        # the net still believes b1 — the gate's fresh read refuses
        engine, _ = spawn()
        see_head(engine, "h1", base="b1")
        world_of(engine)["base_head"] = "b2"
        comment(engine, "c1", "change")
        assert pushes(engine) == []
        assert settled_facts(engine)[-1]["outcome"] == "moved"

    def test_a_grant_moved_to_quiescent_in_flight_refuses_the_push(self) -> None:
        # the PR goes draft while the push is in flight: the gate's
        # fresh read of the HOST grant refuses — no write under a
        # quiescent grant, even though the claim was current at admission
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", hold=HOLD)
        deliver_held(engine, dispatch, definitions, "on_draft", "DraftSeen", {}, hold=HOLD)
        release_one(engine, dispatch, definitions, "git_gate")
        assert pushes(engine) == []
        assert settled_facts(engine)[-1]["outcome"] == "moved"

    def test_a_previous_incarnations_claim_is_fenced_by_the_grant(self) -> None:
        # draft then resume WHILE the push is in flight: identical
        # head/base/policy, but the grant incarnation moved — the op
        # authored under the old grant refuses
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", hold=HOLD)  # claim i1
        deliver_held(engine, dispatch, definitions, "on_draft", "DraftSeen", {}, hold=HOLD)
        deliver_held(engine, dispatch, definitions, "on_ready", "ReadySeen", {}, hold=HOLD)  # i2
        release_one(engine, dispatch, definitions, "git_gate")
        assert pushes(engine) == []
        assert settled_facts(engine)[-1]["outcome"] == "moved"
        # a fresh command under the CURRENT grant lands
        comment_held(engine, dispatch, definitions, "c2", "change")
        assert pushes(engine) == [("push", "push:comment:c2:h1:i2")]


class TestLookupFirst:
    def test_an_already_landed_operation_reconciles_without_a_second_push(self) -> None:
        # the crash-recovery world: a previous life of this host pushed
        # and died before the acknowledgment was recorded
        engine, _ = spawn()
        see_head(engine, "h1")
        world = world_of(engine)
        world["pushes"].append({"key": "push:comment:c1:h1:i1", "op": "change", "from": "h1", "to": "h1+change"})
        world["branch_head"] = "h1+change"
        comment(engine, "c1", "change")
        assert pushes(engine) == []  # NO new effect
        assert settled_facts(engine)[-1]["outcome"] == "landed"
        assert one(engine, "life.state")["expected"] == "h1+change"


class TestFaultAndRecovery:
    OP_KEY = "push:comment:c1:h1:i1"

    def spawn_faulted(self):
        """A push whose terminal is unknown (never proven landed)."""
        engine, built = spawn()
        world_of(engine)["git_mode"] = "fault"
        see_head(engine, "h1")
        comment(engine, "c1", "change")
        return engine, built

    def recover(self, engine, op: str, id: str = "r1") -> None:
        """The PRODUCT recovery door: a human `recover_publication`
        comment whose operation prefix routes to the owning loop."""
        comment(engine, id, "recover_publication", arg=op)

    def test_a_fault_retains_the_exact_operation_fail_closed(self) -> None:
        engine, _ = self.spawn_faulted()
        state = one(engine, "mut.state")
        assert state == {
            "state": "faulted",
            "op_key": self.OP_KEY,
            "op": "change",
            "head": "h1",
            "base": "b1",
            "policy": "p1",
            "incarnation": 1,
            "reason": "unknown provider terminal",
            "kind": "change",
            "instruction": "",
            "run_id": 0,
            "attempt": 0,
        }
        faults = [f for f in projection(engine) if f["kind"] == "fault"]
        assert faults[-1]["body"] == {
            "where": "mutation",
            "op": self.OP_KEY,
            "reason": "unknown provider terminal",
        }
        # readiness heard the same fail-closed fact
        assert one(engine, "ready.snap")["faults"] == {
            f"mutation:{self.OP_KEY}": "unknown provider terminal",
        }

    def test_further_requests_are_declined_before_any_gate_attempt(self) -> None:
        engine, _ = self.spawn_faulted()
        world_of(engine)["git_mode"] = None  # the provider healed — irrelevant:
        comment(engine, "c2", "update_base")  # the baton is still faulted
        assert pushes(engine) == []
        assert settled_facts(engine)[-1] == {
            "op": "update_base",
            "op_key": "push:comment:c2:h1:i1",
            "outcome": "declined",
            "incarnation": 1,
            "fingerprint": "",
        }
        assert one(engine, "mut.state")["state"] == "faulted"

    def test_recovery_reissues_when_the_provider_never_held_it(self) -> None:
        engine, _ = self.spawn_faulted()
        world_of(engine)["git_mode"] = None
        self.recover(engine, self.OP_KEY)
        assert pushes(engine) == [("push", self.OP_KEY)]  # issued NOW
        assert one(engine, "mut.state")["state"] == "idle"
        assert settled_facts(engine)[-1]["outcome"] == "landed"
        assert one(engine, "life.state")["expected"] == "h1+change"

    def test_recovery_after_a_crash_reconciles_lookup_first(self) -> None:
        # the push LANDED but the terminal was lost: recovery reissues
        # the SAME operation identity and the gate finds it — no
        # duplicate push, the settle is landed
        engine, _ = spawn()
        world = world_of(engine)
        world["git_mode"] = "crash"
        see_head(engine, "h1")
        comment(engine, "c1", "change")
        assert one(engine, "mut.state")["state"] == "faulted"
        assert len(pushes(engine)) == 1  # it DID land
        world["git_mode"] = None
        self.recover(engine, self.OP_KEY)
        assert len(pushes(engine)) == 1  # STILL exactly one effect
        assert one(engine, "mut.state")["state"] == "idle"
        assert settled_facts(engine)[-1]["outcome"] == "landed"
        assert one(engine, "life.state")["expected"] == "h1+change"

    def test_a_late_recovery_note_cannot_wedge_lifecycle(self) -> None:
        # the sharpest recovery race: the push LANDED but its ack was
        # lost; the pushed head's OWN webhook arrives (admitted
        # `superseded`) BEFORE recovery reconciles. The late provisional
        # note must be inert — without the from_head fence it would
        # install expected == current head, which no future observation
        # clears, wedging every later committing intent
        engine, _ = spawn()
        world = world_of(engine)
        world["git_mode"] = "crash"
        see_head(engine, "h1")
        comment(engine, "c1", "change")
        assert one(engine, "mut.state")["state"] == "faulted"
        see_head(engine, "h1+change")  # the webhook wins the race
        assert one(engine, "life.state")["incarnation"] == 2  # superseded
        world["git_mode"] = None
        self.recover(engine, self.OP_KEY)
        assert len(pushes(engine)) == 1  # reconciled, no duplicate
        assert one(engine, "mut.state")["state"] == "idle"
        state = one(engine, "life.state")
        assert state["expected"] == ""  # the late note was inert
        # lifecycle still admits the NEXT head normally
        see_head(engine, "h3")
        assert one(engine, "life.state")["incarnation"] == 3

    def test_recovery_for_another_loop_or_operation_is_inert(self) -> None:
        engine, _ = self.spawn_faulted()
        before = one(engine, "mut.state")
        self.recover(engine, "rerun:fp1", id="r1")  # another loop's target
        self.recover(engine, "push:other:h1:i1", id="r2")  # another operation
        assert one(engine, "mut.state") == before

    def test_recovery_while_idle_is_inert(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        self.recover(engine, self.OP_KEY)
        assert one(engine, "mut.state")["state"] == "idle"
        assert pushes(engine) == []


class TestClose:
    def test_close_retires_the_baton_with_its_state(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        assert one(engine, "mut.done") == {"state": "idle", "reason": "merged"}

    def test_close_while_a_push_is_in_flight_waits_for_the_terminal(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", hold=HOLD)
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=HOLD)
        assert tokens(engine, "mut.done") == []  # the round must settle first
        release_one(engine, dispatch, definitions, "git_gate")
        # the close moved the grant to terminal BEFORE the gate read it:
        # the fresh read classified MOVED — no orphan write after close
        assert pushes(engine) == []
        assert one(engine, "mut.done") == {"state": "idle", "reason": "merged"}

    def test_a_request_that_lost_the_race_with_close_settles_declined(self) -> None:
        # the drain: a QUEUED request (its comment was admitted while
        # running, then the close won the race) must still SETTLE —
        # escalation's closing ladder waits on exactly these
        # settlements, so silent parking would strand it forever
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", hold=HOLD)  # in flight
        comment_held(engine, dispatch, definitions, "c2", "change", hold=HOLD)  # queued
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=HOLD)
        release_one(engine, dispatch, definitions, "git_gate")
        assert pushes(engine) == []  # the in-flight round classified moved
        assert tokens(engine, "mut.requests") == []  # drained, not parked
        assert [s["outcome"] for s in settled_facts(engine)] == ["moved", "declined"]
        assert one(engine, "mut.done") == {"state": "idle", "reason": "merged"}

    def test_a_recovery_that_lost_the_race_with_close_is_never_stranded(self) -> None:
        # the recovery note was ADMITTED while running, but its apply
        # waits on the state baton a held push carries in flight; close
        # arrives during the wait. Whichever wins the returned baton,
        # no token may strand in the mailbox
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", hold=HOLD)  # in flight
        assert tokens(engine, "mut.state") == []  # baton in flight
        comment_held(engine, dispatch, definitions, "r1", "recover_publication", arg="push:comment:c1:h1:i1", hold=HOLD)
        assert len(tokens(engine, "mut.recover")) == 1  # parked, waiting
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=HOLD)
        release_one(engine, dispatch, definitions, "git_gate")
        assert tokens(engine, "mut.recover") == []  # applied or drained
        assert one(engine, "mut.done")["reason"] == "merged"

    def test_close_waits_for_a_pending_repair_settlement(self) -> None:
        # escalation opened a repair (mutation custody) and the PR closes
        # while the push is in flight: escalation must NOT retire with
        # the rung recorded `pending` — it holds in `closing` until the
        # settlement folds, and no settlement token is left stranded
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
        for attempt in (1, 2):  # rerun burns, then the repair pushes
            deliver_held(
                engine,
                dispatch,
                definitions,
                "on_runs",
                "RunSeen",
                {"head": "h1", "run_id": 1, "attempt": attempt, "conclusion": "failure", "fingerprint": "fp1"},
                hold=HOLD,
            )
        [invocation] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        assert invocation.input["work"]["op"] == "repair:L1:fp1"
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "closed"}, hold=HOLD)
        assert tokens(engine, "esc.done") == []  # holding, not lying
        release_one(engine, dispatch, definitions, "git_gate")
        # the close moved the grant before the gate read it: moved. The
        # closing ladder folded the refund and retired truthfully.
        [ended] = tokens(engine, "esc.done")
        assert ended["reason"] == "closed"
        assert ended["repairs"] == {}  # refunded, no `pending` lie
        assert tokens(engine, "esc.settled") == []  # nothing stranded
        assert tokens(engine, "esc.ladder") == []  # the baton retired
        assert one(engine, "mut.done")["reason"] == "closed"

    def test_close_with_an_empty_reason_still_retires_a_waiting_ladder(self) -> None:
        # a close reason may be ANY string, including "": the closing
        # sentinel must be distinct (None), or an empty reason would
        # park the ladder in a state no settlement can ever retire
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
        for attempt in (1, 2):
            deliver_held(
                engine,
                dispatch,
                definitions,
                "on_runs",
                "RunSeen",
                {"head": "h1", "run_id": 1, "attempt": attempt, "conclusion": "failure", "fingerprint": "fp1"},
                hold=HOLD,
            )
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": ""}, hold=HOLD)
        release_one(engine, dispatch, definitions, "git_gate")
        [ended] = tokens(engine, "esc.done")
        assert ended["reason"] == ""
        assert tokens(engine, "esc.ladder") == []  # retired, not parked


class TestMutationPayload:
    """CV17.DS2.0: the work token carries the CHANGE, not just its identity.

    A real git gate is coding-agent-plus-CAS-push as ONE classified
    activity (production's `_code` shape): it needs the request kind,
    the human's instruction, and the repair's evidence identity — all
    credential-free — INSIDE the token. An external host ledger keyed
    by rid would put canonical workflow state outside History.
    """

    def test_a_change_comment_carries_its_instruction_to_the_gate(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", arg="rename the config key", hold=HOLD)
        [invocation] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        work = invocation.input["work"]
        assert work["kind"] == "change"
        assert work["instruction"] == "rename the config key"
        assert (work["run_id"], work["attempt"]) == (0, 0)  # no CI evidence

    def test_a_repair_carries_its_evidence_identity_to_the_gate(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        see_head_held(engine, dispatch, definitions)
        for attempt in (1, 2):  # rerun burns, then the repair mints
            deliver_held(
                engine,
                dispatch,
                definitions,
                "on_runs",
                "RunSeen",
                {"head": "h1", "run_id": 1, "attempt": attempt, "conclusion": "failure", "fingerprint": "fp1"},
                hold=HOLD,
            )
        [invocation] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        work = invocation.input["work"]
        assert work["kind"] == "repair"
        assert work["instruction"] == ""  # the evidence, not a human, speaks
        assert (work["run_id"], work["attempt"]) == (1, 2)  # the indicting run

    def test_a_faulted_round_retains_the_instruction_for_exact_reissue(self) -> None:
        # A2: recovery reissues the EXACT operation — including the
        # change payload the original round attempted
        engine, _, dispatch, definitions = spawn_held()
        world_of(engine)["git_mode"] = "fault"
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", arg="rename the config key", hold=HOLD)
        release_one(engine, dispatch, definitions, "git_gate")
        pump(engine, dispatch, definitions)
        state = one(engine, "mut.state")
        assert state["state"] == "faulted"
        assert state["kind"] == "change"
        assert state["instruction"] == "rename the config key"
        world_of(engine)["git_mode"] = None
        comment_held(engine, dispatch, definitions, "r1", "recover_publication", arg="push:comment:c1:h1:i1", hold=HOLD)
        [invocation] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        assert invocation.input["work"]["instruction"] == "rename the config key"

    def test_recovery_reissues_the_exact_work_byte_for_byte(self) -> None:
        # A2's full proof: the recovered MutWork EQUALS the original —
        # every field, not just the instruction. The payload's exact
        # association with the operation identity survives the fault
        # round-trip through the retained MutState.
        engine, _, dispatch, definitions = spawn_held()
        world_of(engine)["git_mode"] = "fault"
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", arg="rename the config key", hold=HOLD)
        [first] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        original = dict(first.input["work"])
        release_one(engine, dispatch, definitions, "git_gate")
        pump(engine, dispatch, definitions)
        world_of(engine)["git_mode"] = None
        comment_held(engine, dispatch, definitions, "r1", "recover_publication", arg="push:comment:c1:h1:i1", hold=HOLD)
        [second] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        assert second.input["work"] == original

    def test_recovery_reissues_the_exact_repair_work_byte_for_byte(self) -> None:
        # the repair's indicting evidence identity (run_id, attempt)
        # survives the same round-trip
        engine, _, dispatch, definitions = spawn_held()
        world_of(engine)["git_mode"] = "fault"
        see_head_held(engine, dispatch, definitions)
        for attempt in (1, 2):  # rerun burns, then the repair mints
            deliver_held(
                engine,
                dispatch,
                definitions,
                "on_runs",
                "RunSeen",
                {"head": "h1", "run_id": 1, "attempt": attempt, "conclusion": "failure", "fingerprint": "fp1"},
                hold=HOLD,
            )
        [first] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        original = dict(first.input["work"])
        assert (original["kind"], original["run_id"], original["attempt"]) == ("repair", 1, 2)
        release_one(engine, dispatch, definitions, "git_gate")
        pump(engine, dispatch, definitions)
        world_of(engine)["git_mode"] = None
        comment_held(engine, dispatch, definitions, "r1", "recover_publication", arg=original["op_key"], hold=HOLD)
        [second] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        assert second.input["work"] == original


class TestDeclined:
    """CV17.DS2.0: a clean agent-unable is a DECLINED settlement, not a
    fault. The agent investigated and produced no change; nothing was
    pushed, the branch's true head is fully known — classifying this as
    FaultM would fail the baton closed and page a human for a
    non-incident, and MovedM would forge an authority move."""

    def test_agent_unable_settles_declined_and_returns_the_baton(self) -> None:
        engine, _ = spawn()
        world_of(engine)["git_mode"] = "unable"
        see_head(engine, "h1")
        comment(engine, "c1", "change")
        assert pushes(engine) == []  # nothing landed
        assert settled_facts(engine)[-1] == {
            "op": "change",
            "op_key": "push:comment:c1:h1:i1",
            "outcome": "declined",
            "incarnation": 1,
            "fingerprint": "",
        }
        assert one(engine, "mut.state")["state"] == "idle"  # NOT fail-closed

    def test_a_declined_round_does_not_block_the_next_request(self) -> None:
        engine, _ = spawn()
        world_of(engine)["git_mode"] = "unable"
        see_head(engine, "h1")
        comment(engine, "c1", "change")
        world_of(engine)["git_mode"] = None  # the next round is on its own
        comment(engine, "c2", "update_base")
        assert [s["outcome"] for s in settled_facts(engine)] == ["declined", "landed"]
        assert pushes(engine) == [("push", "push:comment:c2:h1:i1")]

    def test_a_declined_repair_consumes_the_rung(self) -> None:
        # the ladder already consumes `declined` settlements (a known
        # terminal): strictly newer failing evidence pages the human
        # instead of re-repairing
        engine, _ = spawn()
        world_of(engine)["git_mode"] = "unable"
        see_head(engine, "h1")
        for attempt in (1, 2):  # rerun burns, then the repair declines
            see_run(engine, head="h1", run_id=1, attempt=attempt, conclusion="failure", fingerprint="fp1")
        assert settled_facts(engine)[-1]["outcome"] == "declined"
        see_run(engine, head="h1", run_id=2, attempt=1, conclusion="failure", fingerprint="fp1")
        needed = [f for f in projection(engine) if f["kind"] == "human_needed"]
        assert needed and needed[-1]["body"]["fingerprint"] == "fp1"

    def test_close_before_the_gate_starts_classifies_moved_not_declined(self) -> None:
        # A3: close defers while the round is out — but this round never
        # STARTED: the gate fences authority BEFORE the coding agent
        # runs, and close already moved it to terminal. The agent never
        # investigates against authority known to be gone, so the round
        # settles MOVED (not declined), then the baton retires. A close
        # arriving MID-agent needs a controllable mid-activity seam
        # (DS2.1) to exercise the genuine late decline.
        engine, _, dispatch, definitions = spawn_held()
        world_of(engine)["git_mode"] = "unable"
        see_head_held(engine, dispatch, definitions)
        comment_held(engine, dispatch, definitions, "c1", "change", hold=HOLD)
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "closed"}, hold=HOLD)
        release_one(engine, dispatch, definitions, "git_gate")
        pump(engine, dispatch, definitions)
        assert settled_facts(engine)[-1]["outcome"] == "moved"
        [ended] = tokens(engine, "mut.done")
        assert ended["state"] == "idle"
