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

Requests arrive through the `on_mutation` scaffold door, standing in
for the conversation loop's committing intents until it lands.
"""

from harness import (
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

HOLD = frozenset({"git_gate"})


def request(
    engine,
    op: str = "change",
    head: str = "h1",
    base: str = "b1",
    policy: str = "p1",
    incarnation: int = 1,
    rid: str | None = None,
):
    deliver(
        engine,
        "on_mutation",
        "MutationRequest",
        {
            "op": op,
            "rid": rid if rid is not None else op,
            "head": head,
            "base": base,
            "policy": policy,
            "incarnation": incarnation,
            "source": "conversation",
        },
    )


def request_held(
    engine, dispatch, definitions, *, op: str = "change", head: str = "h1", rid: str | None = None, hold=HOLD
):
    deliver_held(
        engine,
        dispatch,
        definitions,
        "on_mutation",
        "MutationRequest",
        {
            "op": op,
            "rid": rid if rid is not None else op,
            "head": head,
            "base": "b1",
            "policy": "p1",
            "incarnation": 1,
            "source": "conversation",
        },
        hold=hold,
    )


def settled_facts(engine) -> list[dict]:
    return [f["body"] for f in tokens(engine, "dash.facts") if f["kind"] == "mutation_settled"]


def pending_facts(engine) -> list[dict]:
    return [f["body"] for f in tokens(engine, "dash.facts") if f["kind"] == "mutation_pending"]


def pushes(engine) -> list[tuple]:
    return [e for e in world_of(engine)["log"] if e[0] == "push"]


class TestLandedPush:
    def test_a_request_pushes_under_a_stable_operation_identity(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        request(engine, op="change")
        world = world_of(engine)
        assert world["branch_head"] == "h1+change"
        assert world["pushes"] == [{"key": "push:change:h1:i1", "op": "change", "from": "h1", "to": "h1+change"}]
        assert one(engine, "mut.state")["state"] == "idle"  # the baton returned
        assert pending_facts(engine) == [{"op": "change"}]
        assert settled_facts(engine) == [{"op": "change", "outcome": "landed", "incarnation": 1, "fingerprint": ""}]

    def test_a_landed_push_notes_the_provisional_head_with_lifecycle(self) -> None:
        # the expected-head note is what later admits OUR OWN push as
        # `confirmed` (keeping the budget lineage) instead of `superseded`
        engine, _ = spawn()
        see_head(engine, "h1")
        request(engine, op="repair:L1:fp1")
        state = one(engine, "life.state")
        assert state["expected"] == "h1+repair:L1:fp1"
        assert state["expected_op"] == "repair:L1:fp1"
        assert state["lineage"] == "L1"  # derived from the repair's budget key
        # the settlement carries the escalation budget key
        assert settled_facts(engine)[-1]["fingerprint"] == "L1:fp1"

    def test_the_baton_serializes_requests_one_at_a_time(self) -> None:
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
        request_held(engine, dispatch, definitions, op="change")
        [invocation] = [i for i in dispatch.pending.values() if i.activity == "git_gate"]
        assert invocation.input["work"]["op_key"] == "push:change:h1:i1"
        assert tokens(engine, "mut.state") == []  # the baton is HELD in flight
        # a second request cannot race the held round: it waits visibly
        request_held(engine, dispatch, definitions, op="update_base")
        assert len(tokens(engine, "mut.requests")) == 1
        assert len([i for i in dispatch.pending.values() if i.activity == "git_gate"]) == 1
        release_one(engine, dispatch, definitions, "git_gate")  # first lands
        pump(engine, dispatch, definitions)  # the queued round runs next
        # the first push moved the head, so the queued op classifies MOVED
        # at ITS OWN gate — serialized, fenced, never lost
        assert [s["outcome"] for s in settled_facts(engine)] == ["landed", "moved"]
        assert pushes(engine) == [("push", "push:change:h1:i1")]

    def test_two_distinct_requests_of_the_same_kind_never_share_an_identity(self) -> None:
        # two humans command a `change` at the same head: distinct rids
        # give distinct operation identities, so the SECOND request must
        # reach its OWN CAS refusal instead of lookup-reconciling onto
        # the first push's landed effect and lying `landed`
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
        request_held(engine, dispatch, definitions, op="change", rid="c1")
        request_held(engine, dispatch, definitions, op="change", rid="c2")  # queued
        release_one(engine, dispatch, definitions, "git_gate")  # c1 lands
        pump(engine, dispatch, definitions)  # c2's round runs next
        assert pushes(engine) == [("push", "push:c1:h1:i1")]  # ONE effect
        assert [s["outcome"] for s in settled_facts(engine)] == ["landed", "moved"]


class TestAuthorityFencing:
    def test_cas_conflict_a_stale_head_claim_classifies_moved(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        request(engine, op="change", head="h0")  # authored under a stale head
        assert pushes(engine) == []
        assert settled_facts(engine) == [{"op": "change", "outcome": "moved", "incarnation": 1, "fingerprint": ""}]
        assert one(engine, "mut.state")["state"] == "idle"

    def test_a_moved_base_is_fenced_by_the_fresh_read_not_the_cas(self) -> None:
        # the provider's base moved but the webhook has not arrived yet:
        # the net still believes b1 — the gate's fresh read refuses
        engine, _ = spawn()
        see_head(engine, "h1", base="b1")
        world_of(engine)["base_head"] = "b2"
        request(engine, op="change", base="b1")
        assert pushes(engine) == []
        assert settled_facts(engine)[-1]["outcome"] == "moved"

    def test_a_non_running_grant_refuses_the_push(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_draft", "DraftSeen", {})  # quiescent grant
        request(engine, op="change")
        assert pushes(engine) == []
        assert settled_facts(engine)[-1]["outcome"] == "moved"

    def test_a_previous_incarnations_claim_is_fenced_by_the_grant(self) -> None:
        # draft then resume: identical head/base/policy, but the grant
        # incarnation moved — an op authored under the old grant refuses
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_draft", "DraftSeen", {})
        deliver(engine, "on_ready", "ReadySeen", {})  # incarnation 2
        request(engine, op="change", incarnation=1)
        assert pushes(engine) == []
        assert settled_facts(engine)[-1]["outcome"] == "moved"
        request(engine, op="change", incarnation=2)  # the current grant lands
        assert pushes(engine) == [("push", "push:change:h1:i2")]


class TestLookupFirst:
    def test_an_already_landed_operation_reconciles_without_a_second_push(self) -> None:
        # the crash-recovery world: a previous life of this host pushed
        # and died before the acknowledgment was recorded
        engine, _ = spawn()
        see_head(engine, "h1")
        world = world_of(engine)
        world["pushes"].append({"key": "push:change:h1:i1", "op": "change", "from": "h1", "to": "h1+change"})
        world["branch_head"] = "h1+change"
        request(engine, op="change")
        assert pushes(engine) == []  # NO new effect
        assert settled_facts(engine)[-1]["outcome"] == "landed"
        assert one(engine, "life.state")["expected"] == "h1+change"


class TestFaultAndRecovery:
    def spawn_faulted(self):
        """A push whose terminal is unknown (never proven landed)."""
        engine, built = spawn()
        world_of(engine)["git_mode"] = "fault"
        see_head(engine, "h1")
        request(engine, op="change")
        return engine, built

    def test_a_fault_retains_the_exact_operation_fail_closed(self) -> None:
        engine, _ = self.spawn_faulted()
        state = one(engine, "mut.state")
        assert state == {
            "state": "faulted",
            "op_key": "push:change:h1:i1",
            "op": "change",
            "head": "h1",
            "base": "b1",
            "policy": "p1",
            "incarnation": 1,
            "reason": "unknown provider terminal",
        }
        faults = [f for f in tokens(engine, "dash.facts") if f["kind"] == "fault"]
        assert faults[-1]["body"] == {
            "where": "mutation",
            "op": "push:change:h1:i1",
            "reason": "unknown provider terminal",
        }
        # readiness hears the same fail-closed fact
        assert any(f["kind"] == "fault" for f in tokens(engine, "ready.facts"))

    def test_further_requests_are_declined_before_any_gate_attempt(self) -> None:
        engine, _ = self.spawn_faulted()
        world_of(engine)["git_mode"] = None  # the provider healed — irrelevant:
        request(engine, op="update_base")  # the baton is still faulted
        assert pushes(engine) == []
        assert settled_facts(engine)[-1] == {
            "op": "update_base",
            "outcome": "declined",
            "incarnation": 1,
            "fingerprint": "",
        }
        assert one(engine, "mut.state")["state"] == "faulted"

    def test_recovery_reissues_when_the_provider_never_held_it(self) -> None:
        engine, _ = self.spawn_faulted()
        world_of(engine)["git_mode"] = None
        deliver(engine, "on_recover", "RecoverFact", {"target": "mutation", "op": "push:change:h1:i1"})
        assert pushes(engine) == [("push", "push:change:h1:i1")]  # issued NOW
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
        request(engine, op="change")
        assert one(engine, "mut.state")["state"] == "faulted"
        assert len(pushes(engine)) == 1  # it DID land
        world["git_mode"] = None
        deliver(engine, "on_recover", "RecoverFact", {"target": "mutation", "op": "push:change:h1:i1"})
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
        request(engine, op="change")
        assert one(engine, "mut.state")["state"] == "faulted"
        see_head(engine, "h1+change")  # the webhook wins the race
        assert one(engine, "life.state")["incarnation"] == 2  # superseded
        world["git_mode"] = None
        deliver(engine, "on_recover", "RecoverFact", {"target": "mutation", "op": "push:change:h1:i1"})
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
        deliver(engine, "on_recover", "RecoverFact", {"target": "esc", "op": "push:change:h1:i1"})
        deliver(engine, "on_recover", "RecoverFact", {"target": "mutation", "op": "push:other:h1:i1"})
        assert one(engine, "mut.state") == before

    def test_recovery_while_idle_is_inert(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_recover", "RecoverFact", {"target": "mutation", "op": "push:change:h1:i1"})
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
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=HOLD,
        )
        request_held(engine, dispatch, definitions, op="change")
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=HOLD)
        assert tokens(engine, "mut.done") == []  # the round must settle first
        release_one(engine, dispatch, definitions, "git_gate")
        # the close moved the grant to terminal BEFORE the gate read it:
        # the fresh read classified MOVED — no orphan write after close
        assert pushes(engine) == []
        assert one(engine, "mut.done") == {"state": "idle", "reason": "merged"}

    def test_a_request_after_close_settles_declined(self) -> None:
        # the drain: a request that lost the race with close must still
        # SETTLE — escalation's closing ladder waits on exactly these
        # settlements, so silent parking would strand it forever
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        request(engine, op="change")
        assert pushes(engine) == []
        assert tokens(engine, "mut.requests") == []  # drained, not parked
        assert settled_facts(engine)[-1]["outcome"] == "declined"
        assert one(engine, "mut.done") == {"state": "idle", "reason": "merged"}

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
