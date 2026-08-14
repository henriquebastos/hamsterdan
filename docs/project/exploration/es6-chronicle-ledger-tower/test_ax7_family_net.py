"""AX7 — the cohabitation variant (V5): ALL concern actors in ONE instance.

The Navigator's asyncio hunch, measured: a Petri net is natively
concurrent — the net is the event loop, each concern's baton loop is
a coroutine, and several loops cohabiting one instance is the *normal*
reading of a net, not a trick. So instead of one engine instance per
concern (the V4 family), the whole PR gets ONE instance containing
three actor loops:

- **review** — the AX6 loop verbatim: CAS-gated publication,
  ``moved`` findings fold back as the next round's provisional input;
- **ci** — observe checks per head; a flaky assessment faults the
  loop (fail closed, baton lost);
- **dashboard** — publishes an upsert whenever any sibling emits a
  fact.

What cohabitation buys over V4-as-separate-instances:

1. **Broadcast is topology.** ``on_head`` is one source transition
   whose output arcs fan the delivered token into every interested
   mailbox — the router *disappears into arcs*.
2. **Cross-concern dataflow is an arc.** A fold is a pure
   ``petri_handler`` that returns its own baton AND a ``DashFact``
   into the dashboard's mailbox — no cross-instance messaging
   machinery at all.
3. **One chronicle tells the whole PR's story** across all concerns,
   interleaved, replayable.

What must stay disciplined (asserted structurally below): concern
loops share NOTHING except the ingress broadcast and declared
mailbox-to-mailbox fact arcs. Batons are private. That discipline is
what keeps cohabitation from regrowing production's braid.

Fault isolation is behavioral, not architectural: when CI's loop
loses its baton to a fault, the review and dashboard loops keep
running in the same instance, because enabledness is local to each
transition.
"""

from dataclasses import dataclass, field

from ax5_compiler import VariantPayloadConverter, VariantRoutingActivityHandler
from petrus.engine import Engine
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.dsl import BuiltNet, NetSpec, petri_handler
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch

# -- shared ingress colors ---------------------------------------------------


@dataclass(frozen=True)
class HeadArrived:
    sha: str


@dataclass(frozen=True)
class CloseArrived:
    reason: str


# -- review colors (AX6 verbatim) ---------------------------------------------


@dataclass(frozen=True)
class ReviewMemory:
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
class ReviewFault:
    reason: str


@dataclass(frozen=True)
class Ended:
    reviewed: list[str]
    provisional: list[str]
    reason: str


# -- ci colors -----------------------------------------------------------------


@dataclass(frozen=True)
class CiMemory:
    seen: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CiRound:
    sha: str
    seen: list[str]


@dataclass(frozen=True)
class Assessment:
    sha: str
    seen: list[str]
    status: str


@dataclass(frozen=True)
class CiFault:
    sha: str
    reason: str


@dataclass(frozen=True)
class CiEnded:
    seen: list[str]
    reason: str


# -- dashboard colors ------------------------------------------------------------


@dataclass(frozen=True)
class DashFact:
    kind: str
    sha: str
    summary: str


@dataclass(frozen=True)
class DashMemory:
    entries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DashLanded:
    entries: list[str]


@dataclass(frozen=True)
class DashEnded:
    entries: list[str]
    reason: str


# -- pure folds as petri handlers (multi-color output: baton + fact) --------------


def _one_consumed(binding) -> dict:
    [(_, (token,))] = list(binding.consumed)
    return token.data


def _route(outputs, by_color: dict[str, dict]):
    return {out.target: (Token(out.color, by_color[out.color]),) for out in outputs}


def _fold_review_landed(binding, outputs):
    data = _one_consumed(binding)
    return _route(
        outputs,
        {
            "ReviewMemory": {"reviewed": [*data["reviewed"], data["sha"]], "provisional": []},
            "DashFact": {
                "kind": "review",
                "sha": data["sha"],
                "summary": f"{len(data['findings'])} findings",
            },
        },
    )


def _fold_ci_assessed(binding, outputs):
    data = _one_consumed(binding)
    return _route(
        outputs,
        {
            "CiMemory": {"seen": [*data["seen"], data["sha"]]},
            "DashFact": {"kind": "ci", "sha": data["sha"], "summary": data["status"]},
        },
    )


# -- the net: three loops, one instance --------------------------------------------


def build_family_net() -> BuiltNet:
    net = NetSpec("pr_family")
    s = net.s
    r, c, d = s.review, s.ci, s.dash

    # mailboxes, batons, terminals
    r.p.heads(HeadArrived)
    r.p.memory(ReviewMemory)
    r.p.closed(CloseArrived)
    r.p.done(Ended)
    c.p.heads(HeadArrived)
    c.p.memory(CiMemory)
    c.p.closed(CloseArrived)
    c.p.done(CiEnded)
    d.p.facts(DashFact)
    d.p.memory(DashMemory)
    d.p.closed(CloseArrived)
    d.p.done(DashEnded)

    # ingress doors: broadcast IS the fan-out arcs
    net.t.on_head >> (r.p.heads, c.p.heads)
    net.t.on_close >> (r.p.closed, c.p.closed, d.p.closed)

    # review loop (AX6, with the landed fold emitting a dashboard fact)
    (r.p.heads, r.p.memory) >> r.t.start(handler="start_round") >> r.p.round(RoundOpen)
    r.p.round >> r.t.review(handler="review_agent") >> r.p.output(AgentReview)
    (
        r.p.output
        >> r.t.judge(handler="validate_review")
        >> (r.p.findings(Findings), r.p.rejected(Rejected))
    )
    (
        r.p.findings
        >> r.t.publish(handler="comment_gate")
        >> (r.p.landed(Landed), r.p.moved(Moved), r.p.fault(ReviewFault))
    )
    r.p.landed >> r.t.fold_landed(handler=petri_handler(_fold_review_landed)) >> (
        r.p.memory,
        d.p.facts,
    )
    r.p.moved >> r.t.fold_moved(handler="fold_moved") >> r.p.memory
    r.p.rejected >> r.t.fold_rejected(handler="fold_rejected") >> r.p.memory
    (r.p.closed, r.p.memory) >> r.t.end(handler="end_review") >> r.p.done

    # ci loop (a fault swallows the baton: fail closed, loop stalls)
    (c.p.heads, c.p.memory) >> c.t.start(handler="ci_start") >> c.p.round(CiRound)
    (
        c.p.round
        >> c.t.observe(handler="assess_checks")
        >> (c.p.assessed(Assessment), c.p.fault(CiFault))
    )
    c.p.assessed >> c.t.fold(handler=petri_handler(_fold_ci_assessed)) >> (
        c.p.memory,
        d.p.facts,
    )
    (c.p.closed, c.p.memory) >> c.t.end(handler="end_ci") >> c.p.done

    # dashboard loop (upsert per fact from any sibling)
    (d.p.facts, d.p.memory) >> d.t.publish(handler="dash_gate") >> d.p.landed(DashLanded)
    d.p.landed >> d.t.fold(handler="fold_dash") >> d.p.memory
    (d.p.closed, d.p.memory) >> d.t.end(handler="end_dash") >> d.p.done
    return net.build()


# -- activities --------------------------------------------------------------------


def make_activities(world: dict):
    converter = VariantPayloadConverter()

    @motus_activity(converter=converter)
    def start_round(head: HeadArrived, memory: ReviewMemory) -> RoundOpen:
        return RoundOpen(sha=head.sha, reviewed=memory.reviewed, provisional=memory.provisional)

    @motus_activity(converter=converter)
    def review_agent(work: RoundOpen) -> AgentReview:
        findings = [*work.provisional, f"finding:{work.sha}"]
        return AgentReview(sha=work.sha, findings=findings, reviewed=work.reviewed)

    @motus_activity(converter=converter)
    def validate_review(output: AgentReview) -> Findings | Rejected:
        if not output.findings:
            return Rejected(sha=output.sha, reviewed=output.reviewed)
        return Findings(sha=output.sha, findings=output.findings, reviewed=output.reviewed)

    @motus_activity(converter=converter)
    def comment_gate(work: Findings) -> Landed | Moved | ReviewFault:
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
    def fold_moved(outcome: Moved) -> ReviewMemory:
        return ReviewMemory(reviewed=outcome.reviewed, provisional=outcome.findings)

    @motus_activity(converter=converter)
    def fold_rejected(outcome: Rejected) -> ReviewMemory:
        return ReviewMemory(reviewed=outcome.reviewed, provisional=[])

    @motus_activity(converter=converter)
    def end_review(close: CloseArrived, memory: ReviewMemory) -> Ended:
        return Ended(reviewed=memory.reviewed, provisional=memory.provisional, reason=close.reason)

    @motus_activity(converter=converter)
    def ci_start(head: HeadArrived, memory: CiMemory) -> CiRound:
        return CiRound(sha=head.sha, seen=memory.seen)

    @motus_activity(converter=converter)
    def assess_checks(work: CiRound) -> Assessment | CiFault:
        status = world["checks"].get(work.sha, "ok")
        if status == "flaky":
            return CiFault(sha=work.sha, reason="assessment crashed")
        return Assessment(sha=work.sha, seen=work.seen, status=status)

    @motus_activity(converter=converter)
    def end_ci(close: CloseArrived, memory: CiMemory) -> CiEnded:
        return CiEnded(seen=memory.seen, reason=close.reason)

    @motus_activity(converter=converter)
    def dash_gate(fact: DashFact, memory: DashMemory) -> DashLanded:
        entry = f"{fact.kind}:{fact.sha}:{fact.summary}"
        entries = [*memory.entries, entry]
        world["dashboard"] = entries  # lookup-first upsert: idempotent overwrite
        return DashLanded(entries=entries)

    @motus_activity(converter=converter)
    def fold_dash(outcome: DashLanded) -> DashMemory:
        return DashMemory(entries=outcome.entries)

    @motus_activity(converter=converter)
    def end_dash(close: CloseArrived, memory: DashMemory) -> DashEnded:
        return DashEnded(entries=memory.entries, reason=close.reason)

    return (
        start_round,
        review_agent,
        validate_review,
        comment_gate,
        fold_moved,
        fold_rejected,
        end_review,
        ci_start,
        assess_checks,
        end_ci,
        dash_gate,
        fold_dash,
        end_dash,
    )


_DERIVED = {
    "review.start": "start_round",
    "review.review": "review_agent",
    "review.fold_moved": "fold_moved",
    "review.fold_rejected": "fold_rejected",
    "review.end": "end_review",
    "ci.start": "ci_start",
    "ci.end": "end_ci",
    "dash.publish": "dash_gate",
    "dash.fold": "fold_dash",
    "dash.end": "end_dash",
}
_VARIANT = {
    "review.judge": ("validate_review", ("Findings", "Rejected")),
    "review.publish": ("comment_gate", ("Landed", "Moved", "ReviewFault")),
    "ci.observe": ("assess_checks", ("Assessment", "CiFault")),
}


def spawn_family(world: dict, *, instance: str = "pr7"):
    """ONE spawn for the PR's whole life — all concerns cohabit."""
    built = build_family_net()
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
            {
                NetPath("review.memory"): (
                    Token("ReviewMemory", {"reviewed": [], "provisional": []}),
                ),
                NetPath("ci.memory"): (Token("CiMemory", {"seen": []}),),
                NetPath("dash.memory"): (Token("DashMemory", {"entries": []}),),
            }
        ),
        handlers=handlers,
        guards=dict(built.guards),
        activities=tuple(d.declaration for d in definitions.values()),
    )
    return engine, history, built


def drive_bounded(subject: Engine, limit: int = 200) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def tokens(engine: Engine, place: str) -> list[dict]:
    return [token.data for token in engine.marking.place(NetPath(place))]


# -- the timeline: one PR, three heads, a mid-life CI fault, one chronicle ---------


def pr_lifetime_timeline():
    world = {
        "branch_head": "h1",
        "comments": [],
        "dashboard": [],
        "checks": {"h1": "ok", "h2": "flaky", "h3": "ok"},
    }
    engine, chronicle, built = spawn_family(world)

    engine.deliver("on_head", Token("HeadArrived", {"sha": "h1"}), identity="head-h1")
    drive_bounded(engine)

    world["branch_head"] = "h2"
    engine.deliver("on_head", Token("HeadArrived", {"sha": "h2"}), identity="head-h2")
    world["branch_head"] = "h3"
    engine.deliver("on_head", Token("HeadArrived", {"sha": "h3"}), identity="head-h3")
    drive_bounded(engine)

    engine.deliver("on_close", Token("CloseArrived", {"reason": "merged"}), identity="close")
    drive_bounded(engine)
    return world, engine, chronicle, built


# -- structural claims ---------------------------------------------------------------


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


def components(built: BuiltNet, *, without_nodes: set[str], without_arcs: set[tuple[str, str]]) -> int:
    """Weakly connected components after removing named nodes and arcs."""
    net = built.net
    kept = [str(n) for n in (*net.places, *net.transitions) if str(n) not in without_nodes]
    parent = {n: n for n in kept}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in net.arcs:
        source, target = str(a.source), str(a.target)
        if source in without_nodes or target in without_nodes:
            continue
        if (source, target) in without_arcs:
            continue
        parent[find(source)] = find(target)
    return len({find(n) for n in kept})


class TestTheFamilyShape:
    def test_inventory(self) -> None:
        """Three concerns, the PR's WHOLE life, ONE instance — and the
        whole thing is still a third of production's node count."""
        assert metrics(build_family_net()) == {
            "P": 23,
            "T": 17,
            "A": 47,
            "ratio": 1.175,
            "read_arcs": 0,
            "inhibit_arcs": 0,
            "filters": 0,
            "guards": 0,
        }

    def test_cohabitation_costs_no_staleness_constructs(self) -> None:
        m = metrics(build_family_net())
        assert m["read_arcs"] == m["guards"] == m["filters"] == m["inhibit_arcs"] == 0

    def test_all_cycles_pass_through_the_three_batons(self) -> None:
        """Each loop's cyclicity is confined to its own private axle."""
        built = build_family_net()
        assert not cycles_removed_by(built, set())
        assert cycles_removed_by(built, {"review.memory", "ci.memory", "dash.memory"})

    def test_concerns_touch_only_at_declared_seams(self) -> None:
        """The anti-braid discipline, structurally: remove the two
        ingress doors and the two declared fact arcs, and the net falls
        apart into exactly three independent concern subgraphs."""
        built = build_family_net()
        assert (
            components(
                built,
                without_nodes={"on_head", "on_close"},
                without_arcs={
                    ("review.fold_landed", "dash.facts"),
                    ("ci.fold", "dash.facts"),
                },
            )
            == 3
        )

    def test_batons_are_private(self) -> None:
        """No transition of one concern ever touches a sibling's baton
        or mailbox, except the declared fact arcs into dash.facts."""
        net = build_family_net().net
        allowed_foreign = {
            ("review.fold_landed", "dash.facts"),
            ("ci.fold", "dash.facts"),
        }
        for a in net.arcs:
            source, target = str(a.source), str(a.target)
            owners = {source.split(".")[0], target.split(".")[0]}
            if "on_head" in owners or "on_close" in owners:
                continue  # ingress broadcast
            if len(owners) > 1:
                assert (source, target) in allowed_foreign


# -- behavioral claims -----------------------------------------------------------------


class TestOneInstanceManyLoops:
    def test_review_keeps_its_ax6_behavior_unchanged(self) -> None:
        """Cohabitation changed nothing for the review loop: h1 lands,
        h2 moves, h3 lands carrying h2's provisional findings."""
        world, _, _, _ = pr_lifetime_timeline()
        assert [c["head"] for c in world["comments"]] == ["h1", "h3"]
        assert world["comments"][-1]["findings"] == ["finding:h2", "finding:h3"]

    def test_a_fault_stalls_one_loop_and_only_that_loop(self) -> None:
        """CI faults on h2 and loses its baton; review and dashboard
        keep working in the SAME instance — enabledness is local."""
        _, engine, _, _ = pr_lifetime_timeline()
        assert tokens(engine, "ci.fault") == [{"sha": "h2", "reason": "assessment crashed"}]
        assert tokens(engine, "ci.memory") == []  # baton lost: fail closed
        assert tokens(engine, "ci.heads") == [{"sha": "h3"}]  # never processed
        assert tokens(engine, "review.done") == [
            {"reviewed": ["h1", "h3"], "provisional": [], "reason": "merged"}
        ]

    def test_the_stalled_loop_cannot_end_and_says_so_in_the_marking(self) -> None:
        """Honest fail-closed residue: ci.closed rests unconsumed —
        visible, replayable, never an exception."""
        _, engine, _, _ = pr_lifetime_timeline()
        assert tokens(engine, "ci.closed") == [{"reason": "merged"}]
        assert tokens(engine, "ci.done") == []

    def test_cross_concern_facts_flow_as_arcs(self) -> None:
        """review and ci folds fed the dashboard through plain arcs:
        no router, no messaging machinery, no shared state."""
        world, engine, _, _ = pr_lifetime_timeline()
        assert world["dashboard"] == ["ci:h1:ok", "review:h1:1 findings", "review:h3:2 findings"]
        assert tokens(engine, "dash.done") == [
            {
                "entries": ["ci:h1:ok", "review:h1:1 findings", "review:h3:2 findings"],
                "reason": "merged",
            }
        ]

    def test_one_chronicle_interleaves_all_concerns(self) -> None:
        _, _, chronicle, _ = pr_lifetime_timeline()
        story = repr(chronicle.records)
        for identity in ("head-h1", "head-h2", "head-h3", "close"):
            assert identity in story
        for name in ("review_agent", "assess_checks", "dash_gate"):
            assert name in story


class TestReplayIsTheSameLife:
    def test_the_resurrected_family_holds_the_final_marking(self) -> None:
        world, _, chronicle, built = pr_lifetime_timeline()
        effects_before = (list(world["comments"]), list(world["dashboard"]))

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
            "pr7",
            history=chronicle,
            dispatch=InlineDispatch(definitions),
            handlers=handlers,
            guards=dict(built.guards),
            activities=tuple(d.declaration for d in definitions.values()),
        )
        assert tokens(resurrected, "review.done") == [
            {"reviewed": ["h1", "h3"], "provisional": [], "reason": "merged"}
        ]
        assert tokens(resurrected, "ci.fault") == [{"sha": "h2", "reason": "assessment crashed"}]
        assert tokens(resurrected, "ci.closed") == [{"reason": "merged"}]
        assert not resurrected.advance().ready
        assert (world["comments"], world["dashboard"]) == effects_before
