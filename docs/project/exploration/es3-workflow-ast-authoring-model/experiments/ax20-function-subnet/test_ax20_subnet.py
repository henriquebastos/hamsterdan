"""AX20 focused tests — the function-like subnet, exercised end to end.

The claim under test: *entry claims structurally, the interior is
disposable linear work, one exit fences the moving authority* — and
that shape removes the ``change_in_flight`` flag and the authority
smear that AX13 measured, while the frozen engine runs it unchanged.

Every test drives the frozen ``Engine`` over the AX19 boundary kernel's
lowering; structural tests read the kernel IR and the frozen ``Net``.
"""

from __future__ import annotations

from ax19_kernel import BoundaryTransition, Mode, lower_boundary
from ax20_subnet import FENCE, authority, change_subnet, intent, state
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, NetPath
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data

# -- harness ------------------------------------------------------------------

PLACES = ("intents", "state", "authority", "accepted", "claimed", "draft", "work", "rejected")


def engine_for(seeds: dict[str, tuple], *, history=None, instance: str = "ax20") -> Engine:
    lowered = lower_boundary(change_subnet())
    return Engine.create(
        lowered.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking({NetPath(name): tokens for name, tokens in seeds.items()}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )


def state_tokens(engine: Engine) -> list[dict]:
    """Every State-colored token anywhere — conservation's witness."""
    return [token.data for name in PLACES for token in engine.marking.place(NetPath(name)) if token.color == "State"]


# -- the happy path: authority never moved ---------------------------------------


class TestCommit:
    def test_a_current_run_commits_and_releases_the_state_updated(self) -> None:
        engine = engine_for({"state": (state(),), "authority": (authority("e1", "h1"),)})
        engine.deliver("submit", intent("e1", "h1"), identity="op-1")
        drive_bounded(engine)
        assert place_data(engine, "work") == [{"operation": "change:update_base", "epoch": "e1", "head": "h1"}]
        assert place_data(engine, "state") == [{"committed": 1}]
        assert place_data(engine, "rejected") == []

    def test_the_subnet_is_sound_no_interior_marking_survives_the_run(self) -> None:
        # "Sound" made concrete: after a terminal path, every place
        # between entry and exit is empty — the run left no residue.
        engine = engine_for({"state": (state(),), "authority": (authority("e1", "h1"),)})
        engine.deliver("submit", intent("e1", "h1"), identity="op-1")
        drive_bounded(engine)
        for interior in ("intents", "accepted", "claimed", "draft"):
            assert place_data(engine, interior) == [], f"{interior} leaked marking"


# -- the stale path: authority moved, throw the run away ---------------------------


class TestDiscard:
    def test_a_mid_flight_run_whose_authority_moved_is_discarded_wholesale(self) -> None:
        # The marking IS the run's state, so a run caught between
        # prepare and the exit is just this marking: draft built against
        # e1, state token held in claimed, authority now at e2.
        from ax20_subnet import draft

        engine = engine_for(
            {
                "draft": (draft("e1", "h1"),),
                "claimed": (state(),),
                "authority": (authority("e2", "h2"),),
            }
        )
        drive_bounded(engine)
        assert place_data(engine, "work") == []  # no effect escaped
        assert place_data(engine, "rejected") == [{"epoch": "e1", "head": "h1", "payload": "change:update_base"}]
        assert place_data(engine, "state") == [{"committed": 0}]  # released unchanged

    def test_entry_blindness_makes_stale_at_entry_identical_to_moved_mid_flight(self) -> None:
        # Entry never reads authority, so the net cannot distinguish "the
        # intent was stale when it arrived" from "authority moved while we
        # worked" — both are one case, judged once, at the fence.
        engine = engine_for({"state": (state(),), "authority": (authority("e2", "h2"),)})
        engine.deliver("submit", intent("e1", "h1"), identity="op-1")
        drive_bounded(engine)
        assert place_data(engine, "work") == []
        assert len(place_data(engine, "rejected")) == 1
        assert place_data(engine, "state") == [{"committed": 0}]

    def test_restart_is_a_fresh_submit_after_the_discard(self) -> None:
        # The restart policy the Navigator asked for: don't save work —
        # discard, then re-enter through the same door with fresh inputs.
        engine = engine_for({"state": (state(),), "authority": (authority("e2", "h2"),)})
        engine.deliver("submit", intent("e1", "h1"), identity="op-1")
        drive_bounded(engine)
        engine.deliver("submit", intent("e2", "h2"), identity="op-2")
        drive_bounded(engine)
        assert place_data(engine, "work") == [{"operation": "change:update_base", "epoch": "e2", "head": "h2"}]
        assert place_data(engine, "state") == [{"committed": 1}]
        assert len(place_data(engine, "rejected")) == 1  # the stale husk remains, inert


# -- the structural mutex: the state token IS the lock ------------------------------


class TestClaim:
    def test_an_absent_state_token_blocks_entry_entirely(self) -> None:
        engine = engine_for({"state": (), "authority": (authority("e1", "h1"),)})
        engine.deliver("submit", intent("e1", "h1"), identity="op-1")
        drive_bounded(engine)
        assert place_data(engine, "intents") == [{"epoch": "e1", "head": "h1", "kind": "update_base"}]
        assert place_data(engine, "draft") == []

    def test_two_intents_serialize_through_the_one_state_token(self) -> None:
        engine = engine_for({"state": (state(),), "authority": (authority("e1", "h1"),)})
        engine.deliver("submit", intent("e1", "h1"), identity="op-1")
        engine.deliver("submit", intent("e1", "h1"), identity="op-2")
        drive_bounded(engine)
        assert place_data(engine, "state") == [{"committed": 2}]
        assert len(place_data(engine, "work")) == 2

    def test_the_state_token_is_conserved_on_both_terminal_paths(self) -> None:
        committed = engine_for({"state": (state(),), "authority": (authority("e1", "h1"),)})
        committed.deliver("submit", intent("e1", "h1"), identity="op-1")
        drive_bounded(committed)
        assert state_tokens(committed) == [{"committed": 1}]

        discarded = engine_for({"state": (state(),), "authority": (authority("e2", "h2"),)})
        discarded.deliver("submit", intent("e1", "h1"), identity="op-1")
        drive_bounded(discarded)
        assert state_tokens(discarded) == [{"committed": 0}]


# -- routing: the entry filter parks non-matching intents without blocking ----------


class TestRouting:
    def test_a_non_matching_intent_parks_and_a_later_match_still_binds(self) -> None:
        engine = engine_for({"state": (state(),), "authority": (authority("e1", "h1"),)})
        engine.deliver("submit", intent("e1", "h1", kind="noise"), identity="op-1")
        engine.deliver("submit", intent("e1", "h1"), identity="op-2")
        drive_bounded(engine)
        assert place_data(engine, "intents") == [{"epoch": "e1", "head": "h1", "kind": "noise"}]
        assert place_data(engine, "state") == [{"committed": 1}]  # the match got through


# -- the shape itself: what the pattern removed, verified structurally ---------------


class TestShape:
    def transitions(self) -> dict[str, BoundaryTransition]:
        return {node.name: node for node in change_subnet().nodes if isinstance(node, BoundaryTransition)}

    def test_exactly_the_two_exits_read_authority(self) -> None:
        readers = {
            name for name, node in self.transitions().items() if any(arc.place == "authority" for arc in node.arcs)
        }
        assert readers == {"commit", "discard"}
        for name in readers:
            [arc] = [a for a in self.transitions()[name].arcs if a.place == "authority"]
            assert arc.mode is Mode.READ  # the fence observes; it never consumes

    def test_entry_and_interior_are_guardless_and_the_exits_are_complements(self) -> None:
        transitions = self.transitions()
        assert transitions["submit"].guard is None
        assert transitions["claim"].guard is None
        assert transitions["prepare"].guard is None
        assert transitions["commit"].guard == FENCE
        assert transitions["discard"].guard == f"!({FENCE})"

    def test_no_in_flight_flag_exists_anywhere_in_the_serialized_net(self) -> None:
        lowered = lower_boundary(change_subnet())
        definition = serialize_net_definition(project_net_definition(lowered.built.net)).decode()
        assert "in_flight" not in definition
        assert "provisional" not in definition

    def test_the_whole_pattern_costs_eight_places_five_transitions_seventeen_arcs(self) -> None:
        lowered = lower_boundary(change_subnet())
        net = lowered.built.net
        arcs = sum(len(net.inputs(t)) + len(net.outputs(t)) for t in net.transitions)
        assert (len(tuple(net.places)), len(tuple(net.transitions)), arcs) == (8, 5, 17)

    def test_lowering_is_deterministic(self) -> None:
        first = serialize_net_definition(project_net_definition(lower_boundary(change_subnet()).built.net))
        second = serialize_net_definition(project_net_definition(lower_boundary(change_subnet()).built.net))
        assert first == second


# -- replay: history is the state, the claim held mid-run included -------------------


class TestReplay:
    def test_replay_over_a_recompiled_net_reaches_the_same_marking(self) -> None:
        history = InMemoryHistoryStore()
        original = engine_for(
            {"state": (state(),), "authority": (authority("e1", "h1"),)},
            history=history,
            instance="ax20-replay",
        )
        original.deliver("submit", intent("e1", "h1"), identity="op-1")
        drive_bounded(original)

        recompiled = lower_boundary(change_subnet())
        resumed = Engine.load(
            recompiled.built.net,
            "ax20-replay",
            history=history,
            dispatch=InlineDispatch({}),
            handlers=dict(recompiled.handlers),
            guards=dict(recompiled.built.guards),
            activities=(),
        )
        for name in PLACES:
            assert place_data(resumed, name) == place_data(original, name)
