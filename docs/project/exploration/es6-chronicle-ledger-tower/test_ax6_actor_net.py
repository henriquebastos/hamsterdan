"""AX6 — the actor variant (V4): one LONG-LIVED net per concern per PR.

The Navigator's generator hunch, measured: instead of killing a work
instance on every new head (V2), the review concern is ONE durable net
for the PR's whole life. New heads are *delivered* into the living
instance (``Engine.deliver``); the net loops — receive, review,
judge, publish-or-hold, fold, wait — accumulating its own memory; it
ends only when the PR closes or merges.

Why this does NOT reintroduce production's guards (the trap AX4
measured at 94 reads / 48 guards):

1. **Sequential rounds by token conservation.** The single
   ``memory`` token doubles as the idle baton: ``start`` consumes it,
   the fold returns it. While a round is in flight the baton is
   absent, so a second round *cannot* start — queued heads simply
   wait in the mailbox. Mutual exclusion with zero guards.
2. **Staleness absorbed at the CAS boundary, not tested per token.**
   No transition ever asks "am I current?". The round runs to its
   publish gate; the world's own compare-and-swap answers. ``moved``
   folds the findings back into memory as provisional work for the
   next round — the Navigator's "do the work, decide later".

The round is a durable generator: ``deliver`` is ``send()``, the
publication effect is ``yield``, and the coroutine frame is the
marking + chronicle — replayable, restartable, never a Python frame.

Every structural and behavioral claim in ``ax6-actor-net.md`` is
asserted here on the frozen engine.
"""

from dataclasses import dataclass, field

from ax5_compiler import VariantPayloadConverter, VariantRoutingActivityHandler
from petrus.engine import Engine
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.dsl import BuiltNet, NetSpec
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch

# -- colors ------------------------------------------------------------------


@dataclass(frozen=True)
class HeadArrived:
    sha: str


@dataclass(frozen=True)
class ReviewMemory:
    """The actor's cumulative state: one token, conserved for the PR's life."""

    reviewed: list[str] = field(default_factory=list)
    provisional: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoundOpen:
    sha: str
    reviewed: list[str]
    provisional: list[str]


@dataclass(frozen=True)
class AgentReview:
    sha: str
    findings: list[str]
    reviewed: list[str]


@dataclass(frozen=True)
class Findings:
    sha: str
    findings: list[str]
    reviewed: list[str]


@dataclass(frozen=True)
class Rejected:
    sha: str
    reviewed: list[str]


@dataclass(frozen=True)
class Landed:
    sha: str
    findings: list[str]
    reviewed: list[str]


@dataclass(frozen=True)
class Moved:
    sha: str
    findings: list[str]
    reviewed: list[str]
    observed: str


@dataclass(frozen=True)
class Fault:
    reason: str


@dataclass(frozen=True)
class CloseArrived:
    reason: str


@dataclass(frozen=True)
class Ended:
    reviewed: list[str]
    provisional: list[str]
    reason: str


# -- the net -------------------------------------------------------------------


def build_review_actor() -> BuiltNet:
    """The whole review concern for a PR's whole life: 11 places, 10 transitions."""
    net = NetSpec("review_actor")
    p, t = net.p, net.t

    # mailbox, baton, and terminal signals
    p.heads(HeadArrived)  # ingress mailbox: heads accumulate here
    p.memory(ReviewMemory)  # the baton: exactly one token, PR lifetime
    p.closed(CloseArrived)  # ingress: PR closed or merged
    p.done(Ended)

    # ingress doors: source transitions are what ``Engine.deliver`` fires
    t.on_head >> p.heads
    t.on_close >> p.closed

    # the round loop
    (p.heads, p.memory) >> t.start(handler="start_round") >> p.round(RoundOpen)
    p.round >> t.review(handler="review_agent") >> p.output(AgentReview)
    (
        p.output
        >> t.judge(handler="validate_review")
        >> (p.findings(Findings), p.rejected(Rejected))
    )
    (
        p.findings
        >> t.publish(handler="comment_gate")
        >> (p.landed(Landed), p.moved(Moved), p.fault(Fault))
    )
    p.landed >> t.fold_landed(handler="fold_landed") >> p.memory
    p.moved >> t.fold_moved(handler="fold_moved") >> p.memory
    p.rejected >> t.fold_rejected(handler="fold_rejected") >> p.memory

    # termination consumes the baton: no further round can ever start
    (p.closed, p.memory) >> t.end(handler="end_review") >> p.done
    return net.build()


# -- activities (the world plays GitHub; CAS is server-side) -------------------


def make_activities(world: dict):
    converter = VariantPayloadConverter()

    @motus_activity(converter=converter)
    def start_round(head: HeadArrived, memory: ReviewMemory) -> RoundOpen:
        return RoundOpen(sha=head.sha, reviewed=memory.reviewed, provisional=memory.provisional)

    @motus_activity(converter=converter)
    def review_agent(work: RoundOpen) -> AgentReview:
        # Incremental review, the Navigator's semantics: consider what
        # was pending (provisional) PLUS do more with the new head.
        findings = [*work.provisional, f"finding:{work.sha}"]
        return AgentReview(sha=work.sha, findings=findings, reviewed=work.reviewed)

    @motus_activity(converter=converter)
    def validate_review(output: AgentReview) -> Findings | Rejected:
        if not output.findings:
            return Rejected(sha=output.sha, reviewed=output.reviewed)
        return Findings(sha=output.sha, findings=output.findings, reviewed=output.reviewed)

    @motus_activity(converter=converter)
    def comment_gate(work: Findings) -> Landed | Moved | Fault:
        if world["branch_head"] != work.sha:
            return Moved(
                sha=work.sha,
                findings=work.findings,
                reviewed=work.reviewed,
                observed=world["branch_head"],
            )
        world["comments"].append({"head": work.sha, "findings": work.findings})
        return Landed(sha=work.sha, findings=work.findings, reviewed=work.reviewed)

    @motus_activity(converter=converter)
    def fold_landed(outcome: Landed) -> ReviewMemory:
        return ReviewMemory(reviewed=[*outcome.reviewed, outcome.sha], provisional=[])

    @motus_activity(converter=converter)
    def fold_moved(outcome: Moved) -> ReviewMemory:
        return ReviewMemory(reviewed=outcome.reviewed, provisional=outcome.findings)

    @motus_activity(converter=converter)
    def fold_rejected(outcome: Rejected) -> ReviewMemory:
        return ReviewMemory(reviewed=outcome.reviewed, provisional=[])

    @motus_activity(converter=converter)
    def end_review(close: CloseArrived, memory: ReviewMemory) -> Ended:
        return Ended(reviewed=memory.reviewed, provisional=memory.provisional, reason=close.reason)

    return (
        start_round,
        review_agent,
        validate_review,
        comment_gate,
        fold_landed,
        fold_moved,
        fold_rejected,
        end_review,
    )


_DERIVED = {
    "start": "start_round",
    "review": "review_agent",
    "fold_landed": "fold_landed",
    "fold_moved": "fold_moved",
    "fold_rejected": "fold_rejected",
    "end": "end_review",
}
_VARIANT = {
    "judge": ("validate_review", ("Findings", "Rejected")),
    "publish": ("comment_gate", ("Landed", "Moved", "Fault")),
}


def spawn_actor(world: dict, *, instance: str = "pr7-review"):
    """ONE spawn per PR per concern — this is the only instance review gets."""
    built = build_review_actor()
    definitions = {d.declaration.name: d for d in make_activities(world)}
    handlers = dict(built.handlers)
    for transition, name in _DERIVED.items():
        uri = built.net.handler_uri(NetPath(transition))
        handlers[uri] = DerivedActivityHandler(built.net, NetPath(transition), definitions[name])
    for transition, (name, variants) in _VARIANT.items():
        uri = built.net.handler_uri(NetPath(transition))
        handlers[uri] = VariantRoutingActivityHandler(
            built.net, NetPath(transition), definitions[name], variants=variants
        )
    history = InMemoryHistoryStore()
    engine = Engine.create(
        built.net,
        instance,
        history=history,
        dispatch=InlineDispatch(definitions),
        marking=Marking(
            {NetPath("memory"): (Token("ReviewMemory", {"reviewed": [], "provisional": []}),)}
        ),
        handlers=handlers,
        guards=dict(built.guards),
        activities=tuple(d.declaration for d in definitions.values()),
    )
    return engine, history, built


def drive_bounded(subject: Engine, limit: int = 100) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def tokens(engine: Engine, place: str) -> list[dict]:
    return [token.data for token in engine.marking.place(NetPath(place))]


# -- the timeline: one PR, three heads, one chronicle ---------------------------


def pr_lifetime_timeline():
    world = {"branch_head": "h1", "comments": []}
    engine, chronicle, built = spawn_actor(world)

    # Round 1: the PR opens at h1; the world is still at h1 when the
    # round reaches its gate — the publication lands.
    engine.deliver("on_head", Token("HeadArrived", {"sha": "h1"}), identity="head-h1")
    drive_bounded(engine)

    # The author pushes twice in quick succession. Both facts are
    # delivered into the SAME living instance — no kill, no respawn.
    world["branch_head"] = "h2"
    engine.deliver("on_head", Token("HeadArrived", {"sha": "h2"}), identity="head-h2")
    world["branch_head"] = "h3"
    engine.deliver("on_head", Token("HeadArrived", {"sha": "h3"}), identity="head-h3")
    drive_bounded(engine)

    # The PR merges; the router delivers the close.
    engine.deliver("on_close", Token("CloseArrived", {"reason": "merged"}), identity="close")
    drive_bounded(engine)
    return world, engine, chronicle, built


# -- structural claims -----------------------------------------------------------


def metrics(built: BuiltNet) -> dict[str, float]:
    net = built.net
    places, transitions, arcs = len(net.places), len(net.transitions), len(net.arcs)
    return {
        "P": places,
        "T": transitions,
        "A": arcs,
        "ratio": round(arcs / (places + transitions), 3),
        "read_arcs": sum(1 for a in net.arcs if a.is_read),
        "inhibit_arcs": sum(1 for a in net.arcs if a.is_inhibit),
        "filters": sum(1 for a in net.arcs if a.filter is not None),
        "guards": sum(len(net.guard_uris(t)) for t in net.transitions),
    }


def cycles_removed_by(built: BuiltNet, removed: set[str]) -> bool:
    """True if deleting ``removed`` places makes the net acyclic."""
    net = built.net
    out: dict[str, list[str]] = {}
    for a in net.arcs:
        source, target = str(a.source), str(a.target)
        if source in removed or target in removed:
            continue
        out.setdefault(source, []).append(target)
    seen: dict[str, int] = {}

    def visit(node: str) -> bool:
        seen[node] = 1
        for nxt in out.get(node, ()):
            state = seen.get(nxt)
            if state == 1 or (state is None and not visit(nxt)):
                return False
        seen[node] = 2
        return True

    return all(seen.get(str(n)) == 2 or visit(str(n)) for n in (*net.places, *net.transitions))


class TestTheActorShape:
    def test_inventory(self) -> None:
        """The WHOLE review concern for a PR's WHOLE life, in 19 nodes."""
        assert metrics(build_review_actor()) == {
            "P": 11,
            "T": 10,
            "A": 23,
            "ratio": 1.095,
            "read_arcs": 0,
            "inhibit_arcs": 0,
            "filters": 0,
            "guards": 0,
        }

    def test_long_lived_yet_zero_staleness_constructs(self) -> None:
        """The trap did not spring: living across heads cost no guard,
        no read arc, no filter — staleness is the CAS gate's verdict
        (an output arc), not a per-transition question."""
        m = metrics(build_review_actor())
        assert m["read_arcs"] == m["guards"] == m["filters"] == m["inhibit_arcs"] == 0

    def test_all_cycles_pass_through_the_memory_baton(self) -> None:
        """Cyclicity is confined to the state cell, the AX2 rule: the
        loop IS the actor's mainloop, and memory is its only axle."""
        built = build_review_actor()
        assert not cycles_removed_by(built, set())
        assert cycles_removed_by(built, {"memory"})

    def test_sequential_rounds_are_token_conservation_not_guards(self) -> None:
        """``start`` needs the baton; every fold returns it; ``end``
        consumes it forever. Mutual exclusion and termination are both
        plain arcs."""
        net = build_review_actor().net
        memory = NetPath("memory")
        consumers = {str(a.target) for a in net.arcs if a.source == memory}
        producers = {str(a.source) for a in net.arcs if a.target == memory}
        assert consumers == {"start", "end"}
        assert producers == {"fold_landed", "fold_moved", "fold_rejected"}


# -- behavioral claims: the durable generator ------------------------------------


class TestThePrLifetime:
    def test_only_current_heads_ever_reach_the_world(self) -> None:
        """h1 lands (world at h1); h2's round completes but its gate
        classifies ``moved``; h3 lands. Whichever order the mailbox is
        drained, the CAS gate lets exactly the current head publish."""
        world, _, _, _ = pr_lifetime_timeline()
        assert [c["head"] for c in world["comments"]] == ["h1", "h3"]

    def test_the_moved_round_becomes_the_next_rounds_input(self) -> None:
        """Incremental review, no seed machinery: h2's findings were
        never published, so they fold back as provisional and the h3
        round's agent receives them — pending work plus the new head."""
        world, _, _, _ = pr_lifetime_timeline()
        assert world["comments"][-1] == {
            "head": "h3",
            "findings": ["finding:h2", "finding:h3"],
        }

    def test_close_consumes_the_baton_and_summarizes_the_life(self) -> None:
        _, engine, _, _ = pr_lifetime_timeline()
        assert tokens(engine, "done") == [
            {"reviewed": ["h1", "h3"], "provisional": [], "reason": "merged"}
        ]
        assert tokens(engine, "memory") == []  # the baton is gone
        assert tokens(engine, "heads") == []  # the mailbox was drained

    def test_a_head_after_close_is_a_dead_letter_not_an_error(self) -> None:
        """No graveyard needed while the actor lives; after ``end`` the
        baton is consumed, so a late head simply rests in the mailbox —
        recorded, visible, never advanced."""
        _, engine, _, _ = pr_lifetime_timeline()
        engine.deliver("on_head", Token("HeadArrived", {"sha": "h4"}), identity="head-h4")
        drive_bounded(engine)
        assert tokens(engine, "heads") == [{"sha": "h4"}]
        assert tokens(engine, "done") != []  # still terminal

    def test_one_chronicle_tells_the_whole_story(self) -> None:
        """The V2 contrast: three heads, one close — ONE replayable
        history, not three dead epoch chronicles plus a case chronicle."""
        _, _, chronicle, _ = pr_lifetime_timeline()
        story = repr(chronicle.records)
        for identity in ("head-h1", "head-h2", "head-h3", "close"):
            assert identity in story


class TestReplayIsTheSameLife:
    def test_the_resurrected_actor_holds_the_final_marking(self) -> None:
        world, engine, chronicle, built = pr_lifetime_timeline()
        engine.deliver("on_head", Token("HeadArrived", {"sha": "h4"}), identity="head-h4")
        drive_bounded(engine)
        comments_before = list(world["comments"])

        definitions = {d.declaration.name: d for d in make_activities(world)}
        handlers = dict(built.handlers)
        for transition, name in _DERIVED.items():
            uri = built.net.handler_uri(NetPath(transition))
            handlers[uri] = DerivedActivityHandler(built.net, NetPath(transition), definitions[name])
        for transition, (name, variants) in _VARIANT.items():
            uri = built.net.handler_uri(NetPath(transition))
            handlers[uri] = VariantRoutingActivityHandler(
                built.net, NetPath(transition), definitions[name], variants=variants
            )
        resurrected = Engine.load(
            built.net,
            "pr7-review",
            history=chronicle,
            dispatch=InlineDispatch(definitions),
            handlers=handlers,
            guards=dict(built.guards),
            activities=tuple(d.declaration for d in definitions.values()),
        )
        assert tokens(resurrected, "done") == [
            {"reviewed": ["h1", "h3"], "provisional": [], "reason": "merged"}
        ]
        assert tokens(resurrected, "heads") == [{"sha": "h4"}]
        assert not resurrected.advance().ready
        assert world["comments"] == comments_before  # replay re-fired nothing
