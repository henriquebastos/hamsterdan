"""AX2 — the V2 case net: the meta cell whose world is engine instances.

One case net per PR, long-lived. It owns lifecycle (active / dormant /
terminal) and epoch management (spawn, abandon, seed). To this net,
killing a work-net instance is an ordinary activity — exactly what
posting a comment is to the work net.

Ingress: every admitted webhook reads live PR state (the webhook
action is never trusted — ES-005 ch. 17) and becomes ONE typed
observation: ``ObservedOpen(head)``, ``ObservedDraft``, or
``ObservedClosed``. Classification is stateless; routing is the
(case-state × observation-type) grid, so the net needs no guards and
no CEL filters.

Birth is the initial marking: host admission seeds the correct state
token (plus a spawn request when active) — no birth transition, so no
conflict between "open a case" and "reconcile an observation".

Two variants:

- **grid** — one transition per (state × observation) cell; the
  topology IS the state-machine table, History names lifecycle moves.
- **reconcile** — one transition per state; a pure handler routes via
  colored fan-out; smallest topology, routing hidden in the handler.

Epoch numbering (epoch+1 on supersede/resume), head comparison, and
seed synthesis are token DATA maintained by pure handlers, not
topology. Every claim in ``ax2-case-net.md`` is asserted here.
"""

from petrus.impetus.dsl import BuiltNet, NetSpec

# -- colors ---------------------------------------------------------------


class ObservedOpen: ...     # live PR state: open, non-draft, at some head


class ObservedDraft: ...    # live PR state: draft


class ObservedClosed: ...   # live PR state: closed or merged


class CaseActive: ...       # (epoch, head, instance handle)


class CaseDormant: ...      # (last_epoch, last_head)


class CaseTerminal: ...     # closed/merged; absorbing


class SpawnRequest: ...     # start a work-net instance for (epoch, head)


class Seed: ...             # typed birth payload: union of concerns' resume()


class InstanceHandle: ...


class AbandonRequest: ...   # stop feeding events; mark dead; advisory cancel


class Abandoned: ...


class Fault: ...


STATE_PLACES = ("active", "dormant", "terminal")


# -- shared effect pipelines (both variants) ------------------------------


def instance_pipelines(net: NetSpec) -> None:
    """Spawn and abandon are ordinary linear activity pipelines."""
    p, t = net.p, net.t
    (
        p.spawn_request(SpawnRequest)
        >> t.synthesize_seed(handler="synthesize_seed")
        >> p.seed(Seed)
        >> t.spawn(handler="spawn_instance")
        >> (p.spawned(InstanceHandle), p.spawn_fault(Fault))
    )
    (
        p.abandon_request(AbandonRequest)
        >> t.abandon(handler="abandon_instance")
        >> (p.abandoned(Abandoned), p.abandon_fault(Fault))
    )


# -- variant: grid ---------------------------------------------------------


def build_case_net_grid() -> BuiltNet:
    """One transition per (state x observation) cell. Pure direct handlers."""
    net = NetSpec("case")
    p, t = net.p, net.t

    p.active(CaseActive)
    p.dormant(CaseDormant)
    p.terminal(CaseTerminal)
    p.observed_open(ObservedOpen)
    p.observed_draft(ObservedDraft)
    p.observed_closed(ObservedClosed)

    # active row: same head -> no commands; new head -> abandon + spawn (epoch+1)
    (
        (p.active, p.observed_open)
        >> t.head_check(handler="head_check")
        >> (p.active, p.abandon_request(AbandonRequest), p.spawn_request(SpawnRequest))
    )
    (p.active, p.observed_draft) >> t.suspend(handler="suspend") >> (p.dormant, p.abandon_request)
    (p.active, p.observed_closed) >> t.close(handler="close") >> (p.terminal, p.abandon_request)

    # dormant row: resume spawns with epoch = last+1; drafts just update last_head
    (p.dormant, p.observed_open) >> t.resume(handler="resume") >> (p.active, p.spawn_request)
    (p.dormant, p.observed_draft) >> t.note_draft(handler="note_draft") >> p.dormant
    (p.dormant, p.observed_closed) >> t.close_dormant(handler="close_dormant") >> p.terminal

    # terminal row: absorbing — admission drops observations for closed cases

    instance_pipelines(net)
    return net.build()


# -- variant: reconcile ----------------------------------------------------


class Observed: ...  # one color; open/draft/closed + head in the data


def build_case_net_reconcile() -> BuiltNet:
    """One transition per state; the handler is the state-machine row."""
    net = NetSpec("case")
    p, t = net.p, net.t

    p.active(CaseActive)
    p.dormant(CaseDormant)
    p.terminal(CaseTerminal)
    p.observed(Observed)

    (
        (p.active, p.observed)
        >> t.reconcile_active(handler="reconcile_active")
        >> (
            p.active,
            p.dormant,
            p.terminal,
            p.abandon_request(AbandonRequest),
            p.spawn_request(SpawnRequest),
        )
    )
    (
        (p.dormant, p.observed)
        >> t.reconcile_dormant(handler="reconcile_dormant")
        >> (p.active, p.dormant, p.terminal, p.spawn_request)
    )

    instance_pipelines(net)
    return net.build()


# -- measurement helpers ---------------------------------------------------


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
    """True when deleting ``removed`` nodes leaves the graph acyclic."""
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

    nodes = [str(n) for n in (*net.places, *net.transitions) if str(n) not in removed]
    return all(visit(n) for n in nodes if n not in seen)


def lifecycle_transitions(built: BuiltNet) -> set[str]:
    """Transitions touching any state place."""
    net = built.net
    touching = set()
    for a in net.arcs:
        source, target = str(a.source), str(a.target)
        if source in STATE_PLACES:
            touching.add(target)
        if target in STATE_PLACES:
            touching.add(source)
    return touching


# -- the asserted facts ----------------------------------------------------


class TestMeasuredShape:
    def test_grid_variant_inventory(self) -> None:
        assert metrics(build_case_net_grid()) == {
            "P": 13,
            "T": 9,
            "A": 31,
            "ratio": 1.409,
            "read_arcs": 0,
            "inhibit_arcs": 0,
            "filters": 0,
            "guards": 0,
        }

    def test_reconcile_variant_inventory(self) -> None:
        assert metrics(build_case_net_reconcile()) == {
            "P": 11,
            "T": 5,
            "A": 21,
            "ratio": 1.312,
            "read_arcs": 0,
            "inhibit_arcs": 0,
            "filters": 0,
            "guards": 0,
        }

    def test_coordination_pays_in_arcs_not_in_constructs(self) -> None:
        """The state cell costs arc density (>1), never guards or reads."""
        for build in (build_case_net_grid, build_case_net_reconcile):
            m = metrics(build())
            assert m["ratio"] > 1.0
            assert m["read_arcs"] == m["filters"] == m["guards"] == 0


class TestStateCellDoctrine:
    def test_all_cycles_pass_through_state_places(self) -> None:
        for build in (build_case_net_grid, build_case_net_reconcile):
            built = build()
            assert not cycles_removed_by(built, set()), "the state machine must cycle"
            assert cycles_removed_by(built, set(STATE_PLACES)), (
                "cyclicity is confined to the state cell"
            )

    def test_lifecycle_conserves_exactly_one_state_token(self) -> None:
        """Every lifecycle transition consumes one live state and produces one state."""
        for build in (build_case_net_grid, build_case_net_reconcile):
            net = build().net
            names = {str(t) for t in net.transitions} & lifecycle_transitions(build())
            for name in names:
                consumed = [
                    str(a.source)
                    for a in net.arcs
                    if str(a.target) == name and str(a.source) in STATE_PLACES
                ]
                produced = [
                    str(a.target)
                    for a in net.arcs
                    if str(a.source) == name and str(a.target) in STATE_PLACES
                ]
                assert len(consumed) == 1, f"{name} must hold exactly one state"
                assert consumed[0] != "terminal", "terminal is absorbing"
                assert len(produced) >= 1, f"{name} must return a state"

    def test_effect_pipelines_never_touch_state(self) -> None:
        for build in (build_case_net_grid, build_case_net_reconcile):
            effect = {"synthesize_seed", "spawn", "abandon"}
            assert lifecycle_transitions(build()).isdisjoint(effect)

    def test_observation_competition_is_state_disambiguated(self) -> None:
        """A fact place may feed several transitions ONLY when each
        competing transition holds a different state place."""
        net = build_case_net_grid().net
        transition_names = {str(t) for t in net.transitions}
        fed: dict[str, list[str]] = {}
        for a in net.arcs:
            if str(a.source).startswith("observed_") and str(a.target) in transition_names:
                fed.setdefault(str(a.source), []).append(str(a.target))
        assert set(fed) == {"observed_open", "observed_draft", "observed_closed"}
        for competitors in fed.values():
            states = []
            for name in competitors:
                states += [
                    str(a.source)
                    for a in net.arcs
                    if str(a.target) == name and str(a.source) in STATE_PLACES
                ]
            assert len(states) == len(set(states)) == len(competitors)


class TestGridExemplar:
    def test_supersede_row_by_exact_labels(self) -> None:
        net = build_case_net_grid().net
        head_check = sorted(
            (str(a.source), str(a.target))
            for a in net.arcs
            if "head_check" in (str(a.source), str(a.target))
        )
        assert head_check == [
            ("active", "head_check"),
            ("head_check", "abandon_request"),
            ("head_check", "active"),
            ("head_check", "spawn_request"),
            ("observed_open", "head_check"),
        ]
