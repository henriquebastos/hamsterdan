"""Executable contract tests for the V5 dashboard loop.

The dashboard owns the DashMemory baton: a mutable singleton projection
of everything the sibling loops mail as GateFacts. The board
republishes on digest drift ONLY, is authority-orthogonal by design
(A5: a stale row is corrected by the next upsert, never fenced), and
custody is a held baton — one upsert in flight at a time. Blocked and
faulted upserts retain the EXACT attempted request while the desired
state keeps accumulating fail-closed; recovery reissues the retained
request verbatim under the same digest identity, and the landed fold
self-heals any drift with a follow-up upsert (A2).
"""

from harness import (
    comment,
    comment_held,
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


def memory(engine) -> dict:
    return one(engine, "dash.memory")


def board(world: dict) -> list[str]:
    return world["dashboard"]


def upserts(world: dict) -> list[str]:
    return [digest for kind, digest in world["log"] if kind == "dash"]


def attempts(world: dict) -> list[dict]:
    """EVERY upsert the gate ever saw — landed, blocked, or faulted."""
    return world["dash_requests"]


def see_human(engine) -> None:
    deliver(
        engine,
        "on_human",
        "HumanSeen",
        {"approval": True, "changes_requested": False, "unresolved": 0},
    )


# -- the live board -----------------------------------------------------------


class TestBoard:
    def test_facts_land_on_the_board_as_one_projection(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        world = world_of(engine)
        state = memory(engine)
        assert state["entries"]  # the projection log accumulated
        assert board(world) == state["entries"]  # and the board shows it
        assert state["digest"] == state["landed"]  # desired == shown
        assert state["blocked"] == {} and state["faulted"] == {}

    def test_an_identical_consecutive_fact_republishes_nothing(self) -> None:
        # two successive passing runs mail two checks facts with the
        # SAME body: drift is the decision — the second is inert
        engine, _ = spawn()
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, conclusion="success")
        world = world_of(engine)
        seen = len(upserts(world))
        log = list(memory(engine)["entries"])
        see_run(engine, head="h1", run_id=2, conclusion="success")
        assert len(upserts(world)) == seen  # no republish
        assert memory(engine)["entries"] == log  # no duplicate entry

    def test_the_board_is_serialized_by_the_held_baton(self) -> None:
        # while an upsert is in flight the baton is HELD: facts wait in
        # the mailbox, and exactly one publication exists at a time
        engine, _, dispatch, definitions = spawn_held()
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=frozenset({"dash_gate"}),
        )
        assert tokens(engine, "dash.memory") == []  # held through the round
        pending = [i for i in dispatch.pending.values() if i.activity == "dash_gate"]
        assert len(pending) == 1
        release_one(engine, dispatch, definitions, "dash_gate")
        state = memory(engine)  # the baton returned
        assert state["digest"] == state["landed"]
        assert board(world_of(engine)) == state["entries"]


# -- blocked / faulted custody and exact recovery -----------------------------


class TestBlockedAndRecovery:
    def test_retryable_exhaustion_blocks_and_accumulates_fail_closed(self) -> None:
        # entries accumulated while the board is blocked are all carried
        # by the recovery upsert — nothing is lost to the race the
        # held-baton custody closes
        engine, _ = spawn()
        world = world_of(engine)
        world["dash_mode"] = "retryable"
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        see_run(engine, head="h1", run_id=1, conclusion="success")
        see_human(engine)
        state = memory(engine)
        assert state["blocked"]  # fail-closed, the exact request retained
        assert state["landed"] == ""  # nothing ever landed
        accumulated = list(state["entries"])
        assert len(accumulated) >= 3  # head + checks + human at least
        assert len(state["blocked"]["entries"]) < len(accumulated)  # real drift
        assert board(world) == []
        retained = dict(state["blocked"])
        world["dash_mode"] = None
        comment(engine, "c1", "recover_publication", arg=f"dash:{retained['digest']}")
        state = memory(engine)
        assert state["blocked"] == {} and state["faulted"] == {}
        # the recovery reissued the retained request VERBATIM, then the
        # self-heal published the full accumulated state
        assert attempts(world)[-2] == retained
        assert attempts(world)[-1] == {"entries": accumulated, "digest": state["digest"]}
        assert board(world) == accumulated

    def test_unknown_terminal_retains_exact_effect_and_recovers_once(self) -> None:
        # an unknown terminal folds Faulted with the EXACT effect
        # (entries + digest) and reason; recovery reissues the upsert
        # once under the same digest identity
        engine, _ = spawn()
        world = world_of(engine)
        world["dash_mode"] = "unknown"
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        state = memory(engine)
        assert state["faulted"]["reason"] == "unknown provider terminal"
        digest = state["faulted"]["digest"]
        assert digest  # the exact attempted effect identity is retained
        desired = list(state["entries"])
        assert board(world) == []  # nothing landed
        world["dash_mode"] = None
        comment(engine, "c1", "recover_publication", arg=f"dash:{digest}")
        state = memory(engine)
        assert state["faulted"] == {} and state["blocked"] == {}
        assert board(world) == desired  # the full desired state landed
        assert upserts(world).count(digest) == 1  # the exact digest, once

    def test_recovery_reissues_the_exact_request_then_self_heals(self) -> None:
        # the faulted upsert is retained EXACTLY; while the fault is
        # held, more facts accumulate — the desired state drifts.
        # Recovery reissues the retained request verbatim (the operation
        # the human was told about), and the landed fold self-heals the
        # drift with a follow-up upsert of the desired state.
        engine, _ = spawn()
        world = world_of(engine)
        world["dash_mode"] = "unknown"
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        state = memory(engine)
        exact = state["faulted"]
        assert exact["entries"] and exact["digest"]
        desired_before = list(state["entries"])
        assert len(desired_before) > len(exact["entries"])  # real drift
        world["dash_mode"] = None
        comment(engine, "c1", "recover_publication", arg=f"dash:{exact['digest']}")
        landed = upserts(world)
        assert landed[0] == exact["digest"]  # the EXACT request, first
        assert landed.count(exact["digest"]) == 1  # and only once
        # the recovery replayed the retained request VERBATIM before the
        # self-heal published the drifted desired state
        assert attempts(world)[-2] == {"entries": exact["entries"], "digest": exact["digest"]}
        assert attempts(world)[-1]["entries"] == desired_before
        # the drift healed: the board shows exactly the desired state,
        # and memory agrees with what actually landed
        assert board(world) == desired_before
        state = memory(engine)
        assert state["faulted"] == {} and state["blocked"] == {}
        assert state["digest"] == state["landed"]

    def test_cyclic_drift_back_to_the_retained_digest_still_heals(self) -> None:
        # A→B→A: while the fault is held the desired state drifts THROUGH
        # other facts and back to the retained digest. The digest alone
        # cannot see the difference — the heal decision compares the full
        # snapshot, so the accumulated entries still reach the board.
        engine, _ = spawn()
        world = world_of(engine)
        see_head(engine, "h1")  # a healthy board first
        world["dash_mode"] = "unknown"
        deliver(engine, "on_draft", "DraftSeen", {})  # fact A faults, retained
        exact = dict(memory(engine)["faulted"])
        assert exact["digest"]
        deliver(engine, "on_ready", "ReadySeen", {})  # fact B accumulates
        deliver(engine, "on_draft", "DraftSeen", {})  # fact A again: the cycle closes
        state = memory(engine)
        assert state["digest"] == exact["digest"]  # desired digest == retained digest
        desired = list(state["entries"])
        assert len(desired) > len(exact["entries"])  # yet MORE entries are desired
        world["dash_mode"] = None
        comment(engine, "c1", "recover_publication", arg=f"dash:{exact['digest']}")
        # TWO landings under the SAME digest: the exact retained request
        # first, then the self-heal with the full desired state
        assert attempts(world)[-2] == {"entries": exact["entries"], "digest": exact["digest"]}
        assert attempts(world)[-1] == {"entries": desired, "digest": exact["digest"]}
        assert board(world) == desired
        state = memory(engine)
        assert state["faulted"] == {} and state["blocked"] == {}
        assert state["digest"] == state["landed"]

    def test_a_wrong_recovery_op_is_inert(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["dash_mode"] = "unknown"
        see_head(engine, "h1")
        held = memory(engine)["faulted"]
        world["dash_mode"] = None
        comment(engine, "c1", "recover_publication", arg="dash:not-the-digest")
        assert memory(engine)["faulted"] == held  # still fail-closed
        assert board(world) == []

    def test_recovery_with_nothing_held_is_inert(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        see_head(engine, "h1")
        before = len(upserts(world))
        comment(engine, "c1", "recover_publication", arg="dash:anything")
        state = memory(engine)
        assert state["blocked"] == {} and state["faulted"] == {}
        assert len(upserts(world)) == before  # no fresh occurrence


# -- close --------------------------------------------------------------------


class TestClose:
    def test_close_retires_the_board_with_the_final_record(self) -> None:
        engine, _ = spawn()
        see_head(engine, "h1")
        final = list(memory(engine)["entries"])
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        assert tokens(engine, "dash.memory") == []  # the baton retired
        done = one(engine, "dash.done")
        assert done["reason"] == "merged"
        # the record holds everything through the close fan-out itself
        assert list(done["entries"])[: len(final)] == final

    def test_post_close_mail_is_recorded_never_published(self) -> None:
        # the conversation loop NEVER ends: a reply fault after close
        # still mails the dashboard. The EXTERNAL board froze at close;
        # the terminal record keeps the fact, the token never strands.
        engine, _ = spawn()
        see_head(engine, "h1")
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        world = world_of(engine)
        frozen = list(board(world))
        recorded = len(one(engine, "dash.done")["entries"])
        world["comments_mode"] = "unknown"
        comment(engine, "c9", "status")  # the reply faults → a dash fact
        assert board(world) == frozen  # no publication after close
        done = one(engine, "dash.done")
        assert len(done["entries"]) > recorded  # the fact is recorded
        assert any(e.startswith("fault:") for e in done["entries"])
        assert tokens(engine, "dash.facts") == []  # absorbed, not stranded

    def test_close_waits_for_the_inflight_upsert_and_settles_once(self) -> None:
        # close needs the baton; an in-flight upsert holds it — the
        # publication settles first, then close retires the loop exactly
        # once, and nothing strands
        engine, _, dispatch, definitions = spawn_held()
        hold = frozenset({"dash_gate"})
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=hold)
        assert tokens(engine, "dash.done") == []  # close waits on custody
        release_one(engine, dispatch, definitions, "dash_gate")
        [done] = tokens(engine, "dash.done")
        assert done["reason"] == "merged"
        assert tokens(engine, "dash.memory") == []
        assert tokens(engine, "dash.facts") == []  # drained or folded
        assert tokens(engine, "dash.heal") == []  # never stranded
        # the held upsert LANDED before the loop retired
        assert board(world_of(engine))

    def test_close_racing_the_self_heal_strands_nothing(self) -> None:
        # a recovery lands an exact-but-drifted request, which pokes the
        # self-heal — while close is ALREADY waiting on the baton. Close
        # and self-heal race for custody; whichever wins, no token
        # strands and the terminal record preserves the drifted desired
        # entries (close semantics are never weakened for the heal).
        engine, _, dispatch, definitions = spawn_held()
        world = world_of(engine)
        hold = frozenset({"dash_gate"})
        world["agent_findings"]["h1"] = []
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        release_one(engine, dispatch, definitions, "dash_gate")  # healthy board
        world["dash_mode"] = "unknown"
        deliver_held(engine, dispatch, definitions, "on_draft", "DraftSeen", {}, hold=hold)
        release_one(engine, dispatch, definitions, "dash_gate")  # the fault retains
        exact = dict(memory(engine)["faulted"])
        assert exact["digest"]
        # desired drifts while the fault is held
        deliver_held(engine, dispatch, definitions, "on_ready", "ReadySeen", {}, hold=hold)
        desired = list(memory(engine)["entries"])
        assert len(desired) > len(exact["entries"])  # real drift
        world["dash_mode"] = None
        # recovery reissues the exact request and HOLDS the baton...
        comment_held(
            engine,
            dispatch,
            definitions,
            "c1",
            "recover_publication",
            arg=f"dash:{exact['digest']}",
            hold=hold,
        )
        # ...so close arrives while custody is in flight and must wait
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "closed"}, hold=hold)
        assert tokens(engine, "dash.done") == []  # close waits on custody
        # the landing pokes the self-heal — and the race resolves
        release_one(engine, dispatch, definitions, "dash_gate")
        [done] = tokens(engine, "dash.done")
        assert done["reason"] == "closed"
        assert tokens(engine, "dash.memory") == []  # the baton retired
        assert tokens(engine, "dash.heal") == []  # the poke never strands
        assert tokens(engine, "dash.pub_req") == []
        assert tokens(engine, "dash.facts") == []
        assert tokens(engine, "dash.recover") == []
        # the exact retained request landed before close settled
        assert {"entries": exact["entries"], "digest": exact["digest"]} in attempts(world)
        # settled history survives the race: every desired entry that
        # accumulated during the fault is in the terminal record
        assert list(done["entries"])[: len(desired)] == desired
