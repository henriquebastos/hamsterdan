"""Executable contract tests for the V5 readiness loop.

The readiness loop owns the Snapshot baton — the sole all-gates
projection — and consumes every sibling-mailed GateFact. It announces
exactly once per incarnation on the not-ready -> ready edge through an
authority-fenced gate under the stable identity `ready:{head}:i{n}`.
A stale state fact never rolls the projection back; mismatched
incarnations are inert (A1.4); announce-once is recorded on
ACKNOWLEDGMENT (A1.6). Faults are a keyed ledger: a faulted sibling
publication fail-closes readiness until its owner mails an
operation-keyed resolution. Blocked announcements recover under the
same identity; faulted announcements stay fail-closed by settled
terminal policy. Close defers while the gate is out (A3).
"""

from harness import (
    comment,
    deliver,
    deliver_held,
    one,
    pump,
    release_one,
    see_head,
    see_run,
    spawn,
    spawn_held,
    tokens,
    world_of,
)


def snap(engine) -> dict:
    return one(engine, "ready.snap")


def announcements(world: dict) -> list[str]:
    return [c["key"] for c in world["comments"] if c["kind"] == "ready"]


def see_human(engine, approval: bool = True, changes: bool = False, unresolved: int = 0) -> None:
    deliver(
        engine,
        "on_human",
        "HumanSeen",
        {"approval": approval, "changes_requested": changes, "unresolved": unresolved},
    )


def go_ready(engine, world: dict, head: str = "h1", run_id: int = 1) -> None:
    """Drive every gate green for one head: empty review, green checks,
    approving human review."""
    world["agent_findings"][head] = []
    see_head(engine, head)
    see_run(engine, head=head, run_id=run_id)
    see_human(engine)


# -- the projection and the not-ready -> ready edge ------------------------


class TestAnnounce:
    def test_announces_exactly_once_when_every_gate_passes(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        go_ready(engine, world)
        assert announcements(world) == ["ready:h1:i1"]
        st = snap(engine)
        assert st["announced"] == [1]  # recorded on acknowledgment (A1.6)
        assert st["announcing"] == {}  # custody returned

    def test_no_announce_before_every_predicate_component(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        assert announcements(world) == []  # checks pending
        see_run(engine, head="h1")
        assert announcements(world) == []  # no approval yet
        see_human(engine)
        assert announcements(world) == ["ready:h1:i1"]

    def test_blocking_findings_hold_readiness_until_dismissed(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        see_head(engine, "h1")  # default agent output: ONE blocker
        see_run(engine, head="h1")
        see_human(engine)
        assert announcements(world) == []
        assert snap(engine)["findings_blocking"] == 1
        comment(engine, "c1", "dismiss", "f-h1")  # the human waves it off
        assert snap(engine)["findings_blocking"] == 0
        assert announcements(world) == ["ready:h1:i1"]

    def test_changes_requested_and_unresolved_hold_readiness(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        see_run(engine, head="h1")
        see_human(engine, approval=True, changes=True)
        assert announcements(world) == []
        see_human(engine, approval=True, unresolved=2)
        assert announcements(world) == []
        see_human(engine)
        assert announcements(world) == ["ready:h1:i1"]

    def test_unmergeable_holds_readiness(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1", mergeable=False)
        see_run(engine, head="h1")
        see_human(engine)
        assert announcements(world) == []
        # a mergeable-only refresh flips the last gate
        see_head(engine, "h1", mergeable=True)
        assert announcements(world) == ["ready:h1:i1"]

    def test_repeated_ready_preserving_facts_never_reannounce(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        go_ready(engine, world)
        see_human(engine)  # a duplicate approval observation
        see_run(engine, head="h1", run_id=1)  # a duplicate run observation
        assert announcements(world) == ["ready:h1:i1"]  # announce-once
        assert snap(engine)["announced"] == [1]

    def test_pending_mutation_holds_readiness_until_settled(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        hold = frozenset({"git_gate"})
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "success", "fingerprint": ""},
            hold=hold,
        )
        # a committing intent goes in flight and holds readiness
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_comment",
            "CommentSeen",
            {"id": "c1", "kind": "change", "arg": "", "authorized": True},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_human",
            "HumanSeen",
            {"approval": True, "changes_requested": False, "unresolved": 0},
            hold=hold,
        )
        assert snap(engine)["pending"] == ["change"]
        assert announcements(world) == []  # ready in every OTHER gate
        release_one(engine, dispatch, definitions, "git_gate")
        assert snap(engine)["pending"] == []
        # the push moved the head: the OLD head's readiness never lands
        assert announcements(world) == []

    def test_a_queued_second_mutation_never_slips_a_false_announce(self) -> None:
        # the pinned interleaving: mutation A in flight under base b1,
        # the base refreshes (same lifetime, same incarnation), mutation
        # B queues behind the baton under b2, A settles MOVED, B starts
        # and FAULTS — the facts sit in readiness's mailbox FIFO as
        # [settled(A), pending(B), fault(B)]. Folding settled(A) alone
        # sees no pending operation; authorization must therefore fold
        # EVERY mailed fact before the gate begins, or a stale ready
        # decision announces while B's push terminal is unknown.
        engine, _, dispatch, definitions = spawn_held()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        hold = frozenset({"git_gate"})
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "success", "fingerprint": ""},
            hold=hold,
        )
        # mutation A goes in flight under base b1 BEFORE the last gate
        # turns green: readiness is ready in every OTHER gate
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_comment",
            "CommentSeen",
            {"id": "c1", "kind": "change", "arg": "", "authorized": True},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_human",
            "HumanSeen",
            {"approval": True, "changes_requested": False, "unresolved": 0},
            hold=hold,
        )
        # the base refreshes: same lifetime, no incarnation bump
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b2", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        # mutation B, authored under b2, queues behind the held baton
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_comment",
            "CommentSeen",
            {"id": "c2", "kind": "change", "arg": "", "authorized": True},
            hold=hold,
        )
        # A settles MOVED (its b1 claim is stale); B starts and faults
        world["git_mode"] = "fault"
        release_one(engine, dispatch, definitions, "git_gate")
        pump(engine, dispatch, definitions)
        st = snap(engine)
        assert any(k.startswith("mutation:") for k in st["faults"])
        assert announcements(world) == []  # B's true head is unknown


class TestIncarnations:
    def test_draft_resume_announces_again_under_the_new_incarnation(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        go_ready(engine, world)
        deliver(engine, "on_draft", "DraftSeen", {})
        assert snap(engine)["phase"] == "quiescent"
        deliver(engine, "on_ready", "ReadySeen", {})
        st = snap(engine)
        assert st["incarnation"] == 2
        assert st["checks"] == "pending"  # per-incarnation gates reset
        assert st["approval"] is True  # human review state persists
        see_run(engine, head="h1", run_id=2)
        assert announcements(world) == ["ready:h1:i1", "ready:h1:i2"]

    def test_a_new_head_resets_the_per_incarnation_gates(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        go_ready(engine, world)
        world["agent_findings"]["h2"] = []
        see_head(engine, "h2")
        st = snap(engine)
        assert st["incarnation"] == 2
        assert st["head"] == "h2"
        assert st["checks"] == "pending"
        assert announcements(world) == ["ready:h1:i1"]  # nothing new yet
        see_run(engine, head="h2", run_id=2)
        assert announcements(world) == ["ready:h1:i1", "ready:h2:i2"]

    def test_a_mismatched_incarnation_settle_is_inert(self) -> None:
        # a mutation starts under i1; a new head supersedes it while the
        # gate is in flight; the late settle carries i1 and must not
        # touch the i2 projection
        engine, _, dispatch, definitions = spawn_held()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        world["agent_findings"]["h2"] = []
        hold = frozenset({"git_gate"})
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_comment",
            "CommentSeen",
            {"id": "c1", "kind": "change", "arg": "", "authorized": True},
            hold=hold,
        )
        assert snap(engine)["pending"] == ["change"]
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h2", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        assert snap(engine)["pending"] == []  # new authority reset it
        release_one(engine, dispatch, definitions, "git_gate")  # moved: i1
        st = snap(engine)
        assert st["pending"] == []
        assert st["incarnation"] == 2


class TestBlockedRecovery:
    def test_a_blocked_announce_recovers_under_the_same_identity(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        see_run(engine, head="h1")
        world["comments_mode"] = "retryable"
        see_human(engine)
        st = snap(engine)
        assert st["blocked"]["op"] == "ready:h1:i1"  # the EXACT request
        assert st["announcing"] == {}
        assert announcements(world) == []
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", "ready:h1:i1")
        assert announcements(world) == ["ready:h1:i1"]
        st = snap(engine)
        assert st["blocked"] == {}
        assert st["announced"] == [1]

    def test_recovery_with_the_wrong_operation_is_inert(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        see_run(engine, head="h1")
        world["comments_mode"] = "retryable"
        see_human(engine)
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", "ready:h9:i9")
        assert announcements(world) == []
        assert snap(engine)["blocked"]["op"] == "ready:h1:i1"  # retained

    def test_a_faulted_announce_is_fail_closed_and_never_reissued(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        see_run(engine, head="h1")
        world["comments_mode"] = "unknown"
        see_human(engine)
        st = snap(engine)
        assert st["faults"] == {"announce:ready:h1:i1": "unknown provider terminal"}
        world["comments_mode"] = None
        comment(engine, "c1", "recover_publication", "ready:h1:i1")
        assert announcements(world) == []  # settled terminal policy
        assert snap(engine)["faults"] != {}


class TestMovedAuthority:
    def test_moved_with_the_displacing_observation_unfolded_parks(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        world["agent_findings"]["h2"] = []
        hold = frozenset({"announce_gate"})
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "success", "fingerprint": ""},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_human",
            "HumanSeen",
            {"approval": True, "changes_requested": False, "unresolved": 0},
            hold=hold,
        )
        assert snap(engine)["announcing"]["op"] == "ready:h1:i1"
        # the WORLD moves while the gate is out; the webhook lags
        world["branch_head"] = "h2"
        release_one(engine, dispatch, definitions, "announce_gate")
        st = snap(engine)
        assert st["announcing"] == {}
        assert announcements(world) == []  # parked: no reissue livelock
        # the displacing observation folds and reopens the decision
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h2", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=frozenset(),
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h2", "run_id": 2, "attempt": 1, "conclusion": "success", "fingerprint": ""},
            hold=frozenset(),
        )
        assert announcements(world) == ["ready:h2:i2"]

    def test_moved_with_the_displacing_observation_folded_reevaluates(self) -> None:
        # draft -> resume with an IDENTICAL head/base/policy tuple: only
        # the grant incarnation exposes the stale announce (A1.5)
        engine, _, dispatch, definitions = spawn_held()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        hold = frozenset({"announce_gate"})
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "success", "fingerprint": ""},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_human",
            "HumanSeen",
            {"approval": True, "changes_requested": False, "unresolved": 0},
            hold=hold,
        )
        # the i1 announce is in flight; the PR drafts and resumes as i2
        deliver_held(engine, dispatch, definitions, "on_draft", "DraftSeen", {}, hold=hold)
        deliver_held(engine, dispatch, definitions, "on_ready", "ReadySeen", {}, hold=hold)
        assert snap(engine)["incarnation"] == 2
        release_one(engine, dispatch, definitions, "announce_gate")  # moved: i1
        pump(engine, dispatch, definitions)
        assert announcements(world) == []  # i2 checks are pending again
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 2, "attempt": 1, "conclusion": "success", "fingerprint": ""},
            hold=frozenset(),
        )
        assert announcements(world) == ["ready:h1:i2"]
        assert snap(engine)["announced"] == [2]  # i1 never landed


class TestFaultLedger:
    def test_a_review_fault_fail_closes_and_its_recovery_resolves(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["comments_mode"] = "unknown"
        see_head(engine, "h1")  # one blocking finding -> publication faults
        [key] = [k for k in snap(engine)["faults"] if k.startswith("review:")]
        world["comments_mode"] = None
        op = key.removeprefix("review:")
        comment(engine, "c1", "recover_publication", op)
        assert snap(engine)["faults"] == {}  # the settle cleared it

    def test_a_mutation_fault_fail_closes_and_its_recovery_resolves(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        world["git_mode"] = "fault"
        comment(engine, "c1", "change")
        st = snap(engine)
        [key] = [k for k in st["faults"] if k.startswith("mutation:")]
        assert st["pending"] == ["change"]  # the settle never reached ready
        world["git_mode"] = None
        op = key.removeprefix("mutation:")
        comment(engine, "c2", "recover_publication", op)
        st = snap(engine)
        assert st["faults"] == {}  # resolved on the human's ruling
        assert st["pending"] == []  # the reopened round settled

    def test_a_rerun_fault_fail_closes_and_its_recovery_resolves(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        world["reruns_mode"] = "unknown"
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        [key] = [k for k in snap(engine)["faults"] if k.startswith("rerun:")]
        world["reruns_mode"] = None
        op = key.removeprefix("rerun:")
        comment(engine, "c1", "recover_publication", op)
        assert snap(engine)["faults"] == {}  # the landed settle cleared it

    def test_a_moved_rerun_recovery_resolves_instead_of_stranding(self) -> None:
        # the rerun faults under base b1; the base refreshes AND a newer
        # run turns CI green BEFORE the human recovers. Recovery
        # reissues the retained b1 claim; lookup-first finds no existing
        # rerun and the gate refuses MOVED — the operation provably
        # issued no effect. The moved settle must consume the retained
        # fault and mail the resolution, or readiness stays fail-closed
        # forever: the echo is inert (CI is green) and no later landed
        # fold will ever consume the entry.
        engine, _ = spawn()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        world["reruns_mode"] = "unknown"
        see_run(engine, head="h1", conclusion="failure", fingerprint="fp1")
        [key] = [k for k in snap(engine)["faults"] if k.startswith("rerun:")]
        world["reruns_mode"] = None
        # the world moves on while the fault waits for the human
        see_head(engine, "h1", base="b2")
        see_run(engine, head="h1", run_id=2, conclusion="success")
        op = key.removeprefix("rerun:")
        comment(engine, "c1", "recover_publication", op)
        assert snap(engine)["faults"] == {}  # the moved settle cleared it
        assert world["reruns"] == []  # no effect was ever issued


class TestClose:
    def test_close_retires_the_loop_with_the_reason(self) -> None:
        engine, _ = spawn()
        world = world_of(engine)
        go_ready(engine, world)
        deliver(engine, "on_close", "CloseSeen", {"reason": "merged"})
        assert tokens(engine, "ready.snap") == []
        done = one(engine, "ready.done")
        assert done["reason"] == "merged"
        assert done["announced"] == [1]

    def test_an_empty_close_reason_still_closes(self) -> None:
        engine, _ = spawn()
        deliver(engine, "on_head", "HeadSeen", {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"})
        deliver(engine, "on_close", "CloseSeen", {"reason": ""})
        assert tokens(engine, "ready.snap") == []
        assert one(engine, "ready.done")["reason"] == ""

    def test_close_defers_while_the_announce_terminal_is_outstanding(self) -> None:
        engine, _, dispatch, definitions = spawn_held()
        world = world_of(engine)
        world["agent_findings"]["h1"] = []
        hold = frozenset({"announce_gate"})
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_head",
            "HeadSeen",
            {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_runs",
            "RunSeen",
            {"head": "h1", "run_id": 1, "attempt": 1, "conclusion": "success", "fingerprint": ""},
            hold=hold,
        )
        deliver_held(
            engine,
            dispatch,
            definitions,
            "on_human",
            "HumanSeen",
            {"approval": True, "changes_requested": False, "unresolved": 0},
            hold=hold,
        )
        deliver_held(engine, dispatch, definitions, "on_close", "CloseSeen", {"reason": "merged"}, hold=hold)
        assert snap(engine)["closing"] == "merged"  # deferred (A3)
        assert tokens(engine, "ready.done") == []
        release_one(engine, dispatch, definitions, "announce_gate")
        pump(engine, dispatch, definitions)
        assert tokens(engine, "ready.snap") == []
        assert one(engine, "ready.done")["reason"] == "merged"

    def test_post_close_mail_drains_and_never_strands(self) -> None:
        engine, _ = spawn()
        deliver(engine, "on_head", "HeadSeen", {"head": "h1", "base": "b1", "mergeable": True, "policy": "p1"})
        deliver(engine, "on_close", "CloseSeen", {"reason": "closed"})
        # a committing intent after close: mutation drains it declined
        # and mails the settle — readiness must absorb, never strand
        comment(engine, "c1", "change")
        comment(engine, "c2", "recover_publication", "ready:h1:i1")
        assert tokens(engine, "ready.facts") == []
        assert tokens(engine, "ready.recover") == []
        assert one(engine, "ready.done")["reason"] == "closed"
