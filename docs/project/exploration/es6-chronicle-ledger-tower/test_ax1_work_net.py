"""AX1 — the V2 work net: Hamsterdan's domain under ONE fixed authority.

Greenfield expression of the ES-005 chapter 17 contract, written with
the shipped spec DSL only. Production ``topology.py`` was not opened
(ES-006 method rule 4). The net is the epoch cell of the tower: it
contains NO epoch, NO staleness, NO drain, NO dormancy — when
authority moves, the meta net abandons this instance entirely.

The topology contains only the *effect pipelines*. Ingress admission,
per-concern folds over settled exits, and ``decide(snapshot)`` are
pure control-layer functions (chapter 17 target shape: "CONTROL —
pure functions, no places"); ``decide`` seeds the entry places below
with identity-carrying work tokens.

Two variants measure the same behavior:

- **explicit** — one scope per concern *instance* (4 mutation kinds,
  5 publication kinds each get their own pipeline).
- **collapsed** — identical shapes share ONE pipeline; the kind
  travels in the token (`MutationRequest.kind`, `PublishRequest.kind`).

Every structural claim in ``ax1-work-net.md`` is asserted here.
"""

from petrus.impetus.dsl import BuiltNet, NetSpec

# -- colors: decided work in, settled outcomes out ----------------------


class ReviewHead: ...        # review this head (seeded at birth)


class AgentReview: ...       # raw agent output, unvalidated


class Findings: ...          # host-validated findings (completed)


class ActionsRun: ...        # observe CI for this head


class ChecksAssessment: ...  # newest exact-head run, required jobs assessed


class RerunRequest: ...      # rerun this run (budget spent by decide)


class RerunRequested: ...


class MutationRequest: ...   # repair / change / update_base / resolve_conflict


class AgentPatch: ...        # raw agent patch, unvalidated


class ValidPatch: ...        # host-validated, trailers stamped


class ProvisionalHead: ...   # CAS push landed; next generation observes it


class PublishRequest: ...    # dashboard / findings / reply / reminder / readiness


class Published: ...


class Discarded: ...         # normal outcome: preconditions changed / output rejected


class Blocked: ...           # classified recoverable retries exhausted; awaits recover intent


class Fault: ...             # unknown terminal; fail closed


MUTATION_KINDS = ("repair", "change", "update_base", "resolve_conflict")
PUBLICATION_KINDS = ("dashboard", "findings", "reply", "reminder", "readiness")


# -- the three shapes ----------------------------------------------------


def review_pipeline(s) -> None:
    """Agent shape without a gate: agent -> host validation."""
    r = s.review
    r.p.head(ReviewHead) >> r.t.agent(handler="review_agent") >> r.p.output(AgentReview)
    (
        r.p.output
        >> r.t.validate(handler="validate_review")
        >> (r.p.findings(Findings), r.p.discarded(Discarded))
    )


def observe_pipeline(s) -> None:
    """Read-effect shape: one transition, one settled assessment."""
    c = s.ci
    (
        c.p.run(ActionsRun)
        >> c.t.assess(handler="assess_checks")
        >> (c.p.assessed(ChecksAssessment), c.p.fault(Fault))
    )


def rerun_pipeline(s) -> None:
    """Single-gate shape: attempt first, classify the outcome."""
    rr = s.rerun
    (
        rr.p.request(RerunRequest)
        >> rr.t.attempt(handler="rerun_gate")
        >> (rr.p.requested(RerunRequested), rr.p.gone(Discarded), rr.p.fault(Fault))
    )


def mutation_pipeline(m, *, agent_handler: str) -> None:
    """Shape M: agent -> host validation -> git CAS gate.

    ``moved`` is an outcome meaning "preconditions changed, discard" —
    never an error, never forced, inputs never restored.
    """
    m.p.request(MutationRequest) >> m.t.agent(handler=agent_handler) >> m.p.output(AgentPatch)
    (
        m.p.output
        >> m.t.validate(handler="validate_patch")
        >> (m.p.valid(ValidPatch), m.p.discarded(Discarded))
    )
    (
        m.p.valid
        >> m.t.commit(handler="git_gate")
        >> (m.p.committed(ProvisionalHead), m.p.moved(Discarded), m.p.fault(Fault))
    )


def publication_pipeline(q) -> None:
    """Shape P: one comment-gate transition (lookup-first inside the gate)."""
    (
        q.p.request(PublishRequest)
        >> q.t.publish(handler="comment_gate")
        >> (q.p.published(Published), q.p.blocked(Blocked), q.p.fault(Fault))
    )


# -- the two variants ----------------------------------------------------


def build_work_net_explicit() -> BuiltNet:
    """One pipeline per concern INSTANCE: kinds are topology."""
    net = NetSpec("work")
    s = net.s
    review_pipeline(s)
    observe_pipeline(s)
    rerun_pipeline(s)
    for kind in MUTATION_KINDS:
        mutation_pipeline(s.mutate[kind], agent_handler=f"{kind}_agent")
    for kind in PUBLICATION_KINDS:
        publication_pipeline(s.publish[kind])
    return net.build()


def build_work_net_collapsed() -> BuiltNet:
    """One pipeline per SHAPE: kinds travel in the token data."""
    net = NetSpec("work")
    s = net.s
    review_pipeline(s)
    observe_pipeline(s)
    rerun_pipeline(s)
    mutation_pipeline(s.mutate, agent_handler="mutation_agent")
    publication_pipeline(s.publish)
    return net.build()


# -- measurement helpers -------------------------------------------------


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


def fragments(built: BuiltNet) -> int:
    """Weakly connected components — how many independent pieces."""
    net = built.net
    parent: dict[str, str] = {str(n): str(n) for n in (*net.places, *net.transitions)}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in net.arcs:
        parent[find(str(a.source))] = find(str(a.target))
    return len({find(x) for x in parent})


def is_acyclic(built: BuiltNet) -> bool:
    net = built.net
    out: dict[str, list[str]] = {}
    for a in net.arcs:
        out.setdefault(str(a.source), []).append(str(a.target))
    seen: dict[str, int] = {}  # 1 = on stack, 2 = done

    def visit(node: str) -> bool:
        seen[node] = 1
        for nxt in out.get(node, ()):
            state = seen.get(nxt)
            if state == 1 or (state is None and not visit(nxt)):
                return False
        seen[node] = 2
        return True

    return all(visit(str(n)) for n in (*net.places, *net.transitions) if str(n) not in seen)


# -- the asserted facts ---------------------------------------------------


class TestShapeExemplars:
    """One exemplar of each shape, by exact labels."""

    def test_shape_m_is_agent_validate_gate(self) -> None:
        net = build_work_net_explicit().net
        repair = sorted(
            (str(a.source), str(a.target))
            for a in net.arcs
            if str(a.source).startswith("mutate.repair") or str(a.target).startswith("mutate.repair")
        )
        assert repair == [
            ("mutate.repair.agent", "mutate.repair.output"),
            ("mutate.repair.commit", "mutate.repair.committed"),
            ("mutate.repair.commit", "mutate.repair.fault"),
            ("mutate.repair.commit", "mutate.repair.moved"),
            ("mutate.repair.output", "mutate.repair.validate"),
            ("mutate.repair.request", "mutate.repair.agent"),
            ("mutate.repair.valid", "mutate.repair.commit"),
            ("mutate.repair.validate", "mutate.repair.discarded"),
            ("mutate.repair.validate", "mutate.repair.valid"),
        ]

    def test_shape_p_is_one_gate_with_typed_exits(self) -> None:
        net = build_work_net_explicit().net
        dashboard = sorted(
            (str(a.source), str(a.target), a.color)
            for a in net.arcs
            if str(a.source).startswith("publish.dashboard")
            or str(a.target).startswith("publish.dashboard")
        )
        assert dashboard == [
            ("publish.dashboard.publish", "publish.dashboard.blocked", "Blocked"),
            ("publish.dashboard.publish", "publish.dashboard.fault", "Fault"),
            ("publish.dashboard.publish", "publish.dashboard.published", "Published"),
            ("publish.dashboard.request", "publish.dashboard.publish", "PublishRequest"),
        ]


class TestMeasuredShape:
    def test_explicit_variant_inventory(self) -> None:
        assert metrics(build_work_net_explicit()) == {
            "P": 59,
            "T": 21,
            "A": 68,
            "ratio": 0.85,
            "read_arcs": 0,
            "inhibit_arcs": 0,
            "filters": 0,
            "guards": 0,
        }

    def test_collapsed_variant_inventory(self) -> None:
        assert metrics(build_work_net_collapsed()) == {
            "P": 22,
            "T": 8,
            "A": 25,
            "ratio": 0.833,
            "read_arcs": 0,
            "inhibit_arcs": 0,
            "filters": 0,
            "guards": 0,
        }

    def test_pipelines_are_isolated_fragments(self) -> None:
        assert fragments(build_work_net_explicit()) == 12
        assert fragments(build_work_net_collapsed()) == 5

    def test_no_cycles_iteration_is_the_next_generation(self) -> None:
        assert is_acyclic(build_work_net_explicit())
        assert is_acyclic(build_work_net_collapsed())


class TestLinearityDoctrine:
    """The structural facts that make the net readable as pipelines."""

    def test_every_transition_has_exactly_one_input(self) -> None:
        for build in (build_work_net_explicit, build_work_net_collapsed):
            net = build().net
            inputs: dict[str, int] = {}
            targets = {str(t) for t in net.transitions}
            for a in net.arcs:
                if str(a.target) in targets:
                    inputs[str(a.target)] = inputs.get(str(a.target), 0) + 1
            assert set(inputs.values()) == {1}, "fan-in nowhere: joins belong to the fold"

    def test_no_place_feeds_more_than_one_transition(self) -> None:
        for build in (build_work_net_explicit, build_work_net_collapsed):
            net = build().net
            sources = {str(p) for p in net.places}
            outs: dict[str, int] = {}
            for a in net.arcs:
                if str(a.source) in sources:
                    outs[str(a.source)] = outs.get(str(a.source), 0) + 1
            assert all(n == 1 for n in outs.values()), (
                "no place-level choice: all branching is typed fan-out at transitions"
            )

    def test_staleness_is_unexpressible(self) -> None:
        """No node even NAMES the bookkeeping the tower removed."""
        forbidden = ("epoch", "stale", "drain", "dormant", "fence", "seed", "flight")
        for build in (build_work_net_explicit, build_work_net_collapsed):
            net = build().net
            for node in (*net.places, *net.transitions):
                assert not any(word in str(node) for word in forbidden), str(node)
