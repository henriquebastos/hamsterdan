"""AX23 focused tests — merge, loop, and context ports complete the algebra.

The claims under test:

- ``merge`` is *convergence*, never synchronization: two same-colored
  named exits fuse into one place; two tokens stay two tokens.
- ``loop`` keeps the authoring expression a tree while the compiled
  net is cyclic; boundedness is data-driven in the classifier, and the
  static soundness check handles the cycle.
- Context ports make ambient state a declared contract: ``reads``
  wires a read arc (the AX20 fence as data-driven classification) and
  ``holding`` builds the AX20 claim bracket from handler-less
  passthrough transitions — the resource is consumed at entry and
  returned on every terminal path, neither lost nor duplicated.
- The capstone composes the AX20 + AX21 story from the algebra alone:
  claim, disposable interior, fence-once, typed effect outcomes with a
  bounded transient loop, explicit merge — on the frozen engine.
"""

from __future__ import annotations

import pytest
from ax23_blocks import (
    Block,
    BoundaryTransition,
    CompositionError,
    KernelPlace,
    Mode,
    Port,
    check_sound,
    classify,
    compile_block,
    consume,
    disposable,
    holding,
    loop,
    merge,
    produce,
    rename_exit,
    then,
    transform,
)
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data


def run(block: Block, marking: dict[str, tuple[Token, ...]], *, instance: str = "ax23") -> Engine:
    lowered = compile_block("ax23-net", block)
    engine = Engine.create(
        lowered.built.net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking({NetPath(place): tokens for place, tokens in marking.items()}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )
    drive_bounded(engine)
    return engine


# -- merge: explicit convergence, never synchronization ------------------------------


def split_then_reunite() -> Block:
    """Classify high/low, transform each branch to the same color, and
    merge the two exits — the AX5 later-merge, now by declaration."""
    split = classify(
        "split",
        lambda d: ("high", d) if d["score"] > 700 else ("low", d),
        accepts="Application",
        outcomes={"high": "High", "low": "Low"},
        pure=True,
    )
    fast = transform("fast", lambda d: {**d, "lane": "fast"}, accepts="High", returns="Routed")
    slow = transform("slow", lambda d: {**d, "lane": "slow"}, accepts="Low", returns="Routed")
    flow = rename_exit(then(split, fast, on="high"), "out", "fast_done")
    flow = rename_exit(then(flow, slow, on="low"), "out", "slow_done")
    return merge(flow, "fast_done", "slow_done", into="routed")


class TestMerge:
    def test_merge_fuses_places_without_glue(self) -> None:
        before = rename_exit(
            then(
                rename_exit(
                    then(
                        classify(
                            "split",
                            lambda d: ("high", d),
                            accepts="Application",
                            outcomes={"high": "High", "low": "Low"},
                            pure=True,
                        ),
                        transform("fast", dict, accepts="High", returns="Routed"),
                        on="high",
                    ),
                    "out",
                    "fast_done",
                ),
                transform("slow", dict, accepts="Low", returns="Routed"),
                on="low",
            ),
            "out",
            "slow_done",
        )
        after = merge(before, "fast_done", "slow_done", into="routed")
        count = lambda block: len([node for node in block.nodes if isinstance(node, KernelPlace)])
        assert count(after) == count(before) - 1  # one place absorbed
        assert len([n for n in after.nodes if isinstance(n, BoundaryTransition)]) == len(
            [n for n in before.nodes if isinstance(n, BoundaryTransition)]
        )  # and no glue transition
        assert sorted(after.exits) == ["routed"]

    def test_merge_is_convergence_two_tokens_stay_two_tokens(self) -> None:
        flow = check_sound(split_then_reunite())
        engine = run(
            flow,
            {
                flow.entry.place: (
                    Token("Application", {"score": 800}),
                    Token("Application", {"score": 500}),
                )
            },
        )
        lanes = sorted(d["lane"] for d in place_data(engine, flow.exits["routed"].place))
        assert lanes == ["fast", "slow"]  # no pairing, no waiting, no combining

    def test_merge_needs_at_least_two_named_exits(self) -> None:
        with pytest.raises(CompositionError, match="at least two exits"):
            merge(split_then_reunite(), "routed", into="again")

    def test_merge_refuses_unknown_exits_with_the_alternatives(self) -> None:
        block = transform("one", dict, accepts="A", returns="B")
        with pytest.raises(CompositionError, match=r"no exit 'nope'.*\['out'\]"):
            merge(block, "out", "nope", into="all")

    def test_merge_refuses_differing_colors(self) -> None:
        split = classify(
            "split",
            lambda d: ("high", d),
            accepts="Application",
            outcomes={"high": "High", "low": "Low"},
            pure=True,
        )
        with pytest.raises(CompositionError, match=r"colors differ.*High.*Low"):
            merge(split, "high", "low", into="either")

    def test_merge_never_merges_by_color_alone(self) -> None:
        # Two same-colored exits stay separate until the author names
        # them — composition would raise on the duplicate name instead
        # of silently converging (the AX3/AX14 rule).
        split = classify(
            "split",
            lambda d: ("high", d),
            accepts="Application",
            outcomes={"high": "High", "low": "Low"},
            pure=True,
        )
        fast = transform("fast", dict, accepts="High", returns="Routed")
        slow = transform("slow", dict, accepts="Low", returns="Routed")
        step = rename_exit(then(split, fast, on="high"), "out", "fast_done")
        step = rename_exit(then(step, slow, on="low"), "out", "slow_done")
        assert step.exits["fast_done"].place != step.exits["slow_done"].place
        assert step.exits["fast_done"].color == step.exits["slow_done"].color

    def test_merge_refuses_a_colliding_result_name(self) -> None:
        fan = then(
            classify(
                "fan",
                lambda d: ("a", d),
                accepts="X",
                outcomes={"a": "Y", "b": "Z", "c": "W"},
                pure=True,
            ),
            transform("ya", dict, accepts="Y", returns="Common"),
            on="a",
        )
        fan = rename_exit(fan, "out", "left")
        fan = then(fan, transform("zb", dict, accepts="Z", returns="Common"), on="b")
        fan = rename_exit(fan, "out", "right")
        with pytest.raises(CompositionError, match="already has an exit 'c'"):
            merge(fan, "left", "right", into="c")

    def test_merge_refuses_a_double_produce(self) -> None:
        # A transition already producing into both merged places would
        # silently halve its output — refuse at composition time.
        fan = Block(
            name="fan",
            nodes=(
                KernelPlace("fan_in", "X"),
                KernelPlace("copy_a", "Y"),
                KernelPlace("copy_b", "Y"),
                BoundaryTransition(name="fan", arcs=(consume("fan_in"), produce("copy_a"), produce("copy_b"))),
            ),
            entry=Port("fan_in", "X"),
            exits={"a": Port("copy_a", "Y"), "b": Port("copy_b", "Y")},
            pure=True,
        )
        with pytest.raises(CompositionError, match="produce twice"):
            merge(fan, "a", "b", into="one")


# -- loop: a tree expression, a cyclic net --------------------------------------------


def bounded_retry() -> Block:
    """Bump a counter, classify: under three tries loop back, at three
    exit — the data-driven bound (AX21's discipline, AX8's shape)."""
    bump = transform("bump", lambda d: {**d, "tries": d["tries"] + 1}, accepts="Job", returns="Attempt")
    judge = classify(
        "judge",
        lambda d: ("done", d) if d["tries"] >= 3 else ("again", d),
        accepts="Attempt",
        outcomes={"done": "Done", "again": "Job"},
        pure=True,
    )
    return loop(then(bump, judge, on="out"), on="again")


class TestLoop:
    def test_the_expression_is_a_tree_but_the_net_is_cyclic(self) -> None:
        block = bounded_retry()
        entry = block.entry.place
        producers_into_entry = [
            node
            for node in block.nodes
            if isinstance(node, BoundaryTransition)
            and any(arc.place == entry and arc.mode is Mode.PRODUCE for arc in node.arcs)
        ]
        assert [node.name for node in producers_into_entry] == ["judge"]  # the cycle, visible
        assert sorted(block.exits) == ["done"]

    def test_a_data_driven_loop_terminates_on_the_frozen_engine(self) -> None:
        block = check_sound(bounded_retry())
        engine = run(block, {block.entry.place: (Token("Job", {"op": "op-1", "tries": 0}),)})
        assert place_data(engine, block.exits["done"].place) == [{"op": "op-1", "tries": 3}]

    def test_check_sound_accepts_the_cycle(self) -> None:
        assert check_sound(bounded_retry()) is not None

    def test_loop_refuses_an_unknown_exit(self) -> None:
        with pytest.raises(CompositionError, match=r"no exit 'nope'"):
            loop(bounded_retry(), on="nope")

    def test_loop_refuses_a_color_mismatch(self) -> None:
        block = transform("one", dict, accepts="A", returns="B")
        block = then(block, classify("j", lambda d: ("x", d), accepts="B", outcomes={"x": "X", "y": "Y"}), on="out")
        with pytest.raises(CompositionError, match=r"loop.*'x' \(X\) into its entry \(A\): colors differ"):
            loop(block, on="x")

    def test_loop_refuses_to_swallow_the_only_exit(self) -> None:
        pipe = transform("echo", dict, accepts="A", returns="A")
        with pytest.raises(CompositionError, match="would leave no way out"):
            loop(pipe, on="out")


# -- read contexts: the fence as data-driven classification ---------------------------


def fence() -> Block:
    return classify(
        "fence",
        lambda draft, contexts: (
            ("fresh", draft) if draft["epoch"] == contexts["authority"]["epoch"] else ("stale", draft)
        ),
        accepts="Draft",
        outcomes={"fresh": "Fresh", "stale": "StaleDraft"},
        reads=(("authority", "Authority"),),
    )


class TestReadContext:
    def test_the_read_context_routes_and_stays_in_place(self) -> None:
        block = check_sound(fence())
        engine = run(
            block,
            {
                block.entry.place: (Token("Draft", {"op": "op-1", "epoch": "e1"}),),
                "authority": (Token("Authority", {"epoch": "e1"}),),
            },
        )
        assert [d["op"] for d in place_data(engine, block.exits["fresh"].place)] == ["op-1"]
        assert place_data(engine, "authority") == [{"epoch": "e1"}]  # read, never consumed

    def test_a_moved_authority_routes_to_stale(self) -> None:
        block = fence()
        engine = run(
            block,
            {
                block.entry.place: (Token("Draft", {"op": "op-1", "epoch": "e1"}),),
                "authority": (Token("Authority", {"epoch": "e2"}),),
            },
        )
        assert [d["op"] for d in place_data(engine, block.exits["stale"].place)] == ["op-1"]

    def test_context_ports_are_declared_not_discovered(self) -> None:
        assert {name: port.place for name, port in fence().contexts.items()} == {"authority": "authority"}

    def test_a_reading_step_can_never_be_pure(self) -> None:
        with pytest.raises(CompositionError, match="cannot be pure.*fence-once"):
            classify(
                "peek",
                lambda d, ctx: ("out", d),
                accepts="X",
                outcomes={"out": "Y"},
                pure=True,
                reads=(("authority", "Authority"),),
            )

    def test_disposable_refuses_context_touching_blocks(self) -> None:
        with pytest.raises(CompositionError, match="may not depend on shared state"):
            disposable(fence())
        # holding preserves purity but adds a context — still refused:
        # a discardable run may not have held a shared resource either.
        held = holding(transform("pure_step", dict, accepts="A", returns="B"), context="mutex", color="Mutex")
        assert held.pure
        with pytest.raises(CompositionError, match="may not depend on shared state"):
            disposable(held)

    def test_check_sound_exempts_declared_contexts_only(self) -> None:
        check_sound(fence())  # the authority place is off-path but declared
        undeclared = Block(
            name="undeclared",
            nodes=fence().nodes,
            entry=fence().entry,
            exits=dict(fence().exits),
            pure=False,
            contexts={},  # same net, declaration dropped
        )
        with pytest.raises(CompositionError, match=r"not sound.*\['authority'\]"):
            check_sound(undeclared)

    def test_shared_context_names_must_agree_on_color(self) -> None:
        left = classify("l", lambda d, c: ("out", d), accepts="A", outcomes={"out": "B"}, reads=(("cfg", "Config"),))
        right = classify("r", lambda d, c: ("out", d), accepts="B", outcomes={"out": "C"}, reads=(("cfg", "Settings"),))
        with pytest.raises(CompositionError, match="context 'cfg' is Config in 'l' but Settings in 'r'"):
            then(left, right, on="out")

    def test_a_shared_context_place_is_fused_once(self) -> None:
        left = classify("l", lambda d, c: ("out", d), accepts="A", outcomes={"out": "B"}, reads=(("cfg", "Config"),))
        right = classify("r", lambda d, c: ("out", d), accepts="B", outcomes={"out": "C"}, reads=(("cfg", "Config"),))
        both = then(left, right, on="out")
        assert [node.name for node in both.nodes if isinstance(node, KernelPlace)].count("cfg") == 1
        assert sorted(both.contexts) == ["cfg"]


# -- holding: the AX20 claim bracket as a combinator -----------------------------------


def guarded_pipe() -> Block:
    work = transform("work", lambda d: {**d, "done": True}, accepts="Intent", returns="Done")
    return holding(rename_exit(work, "out", "done"), context="state", color="State")


class TestHolding:
    def test_the_bracket_shape_claim_held_release(self) -> None:
        block = guarded_pipe()
        names = {node.name for node in block.nodes if isinstance(node, BoundaryTransition)}
        assert {"claim_state", "release_done"} <= names
        assert block.entry.place == "state_gate"
        assert sorted(block.contexts) == ["state"]

    def test_the_resource_is_returned_neither_lost_nor_duplicated(self) -> None:
        block = check_sound(guarded_pipe())
        engine = run(
            block,
            {
                block.entry.place: (Token("Intent", {"op": "op-1"}),),
                "state": (Token("State", {"committed": 0}),),
            },
        )
        assert [d["op"] for d in place_data(engine, block.exits["done"].place)] == ["op-1"]
        assert len(place_data(engine, "state")) == 1  # exactly one, back where it started

    def test_without_the_context_token_nothing_enters(self) -> None:
        block = guarded_pipe()
        engine = run(block, {block.entry.place: (Token("Intent", {"op": "op-1"}),)})
        assert [d["op"] for d in place_data(engine, block.entry.place)] == ["op-1"]  # waiting at the gate
        assert place_data(engine, block.exits["done"].place) == []

    def test_two_entrants_serialize_through_one_resource(self) -> None:
        block = guarded_pipe()
        engine = run(
            block,
            {
                block.entry.place: (Token("Intent", {"op": "op-1"}), Token("Intent", {"op": "op-2"})),
                "state": (Token("State", {"committed": 0}),),
            },
        )
        assert sorted(d["op"] for d in place_data(engine, block.exits["done"].place)) == ["op-1", "op-2"]
        assert len(place_data(engine, "state")) == 1

    def test_holding_refuses_a_boundary_color_collision(self) -> None:
        pipe = transform("work", dict, accepts="Intent", returns="Done")
        with pytest.raises(CompositionError, match="collides with an entry/exit color"):
            holding(pipe, context="state", color="Intent")

    def test_holding_refuses_a_context_declared_twice(self) -> None:
        with pytest.raises(CompositionError, match="already declares context 'state'"):
            holding(guarded_pipe(), context="state", color="State2")

    def test_holding_refuses_a_block_with_no_exits(self) -> None:
        dead_end = Block(
            name="dead_end",
            nodes=(KernelPlace("sink", "X"),),
            entry=Port("sink", "X"),
            exits={},
            pure=True,
        )
        with pytest.raises(CompositionError, match="has no exits to release"):
            holding(dead_end, context="state", color="State")


# -- the capstone: AX20 + AX21, from the algebra alone ----------------------------------


def capstone(world: dict) -> Block:
    """Claim the concern state, prepare a disposable draft, fence once
    against current authority, run the effect with typed outcomes and a
    bounded transient loop, merge the settled paths, release the state
    on every exit."""

    prepare = disposable(
        transform(
            "prepare",
            lambda intent: {"op": intent["op"], "epoch": intent["epoch"], "attempts": 0},
            accepts="Intent",
            returns="Draft",
        )
    )

    def attempt(fresh: dict) -> tuple[str, dict]:
        if world["outages"] > 0:
            world["outages"] -= 1
            if fresh["attempts"] >= 2:
                return "gave_up", fresh
            return "transient", {**fresh, "attempts": fresh["attempts"] + 1}
        if fresh["op"] in world["applied"]:
            return "already", fresh  # lookup-first: an ambiguous repeat, not an error (AX21)
        world["applied"].append(fresh["op"])
        return "applied", fresh

    effect = classify(
        "apply",
        attempt,
        accepts="Fresh",
        outcomes={"applied": "Applied", "already": "Already", "transient": "Fresh", "gave_up": "Failed"},
    )

    flow = then(prepare, fence(), on="out")
    flow = then(flow, loop(effect, on="transient"), on="fresh")
    flow = rename_exit(
        then(
            flow,
            transform("finish", lambda d: {**d, "mode": "applied"}, accepts="Applied", returns="Settled"),
            on="applied",
        ),
        "out",
        "first_time",
    )
    flow = rename_exit(
        then(
            flow,
            transform("note", lambda d: {**d, "mode": "duplicate"}, accepts="Already", returns="Settled"),
            on="already",
        ),
        "out",
        "repeat",
    )
    flow = merge(flow, "first_time", "repeat", into="done")
    flow = rename_exit(
        then(
            flow,
            transform("record", lambda d: {**d, "mode": "discarded"}, accepts="StaleDraft", returns="Rejected"),
            on="stale",
        ),
        "out",
        "rejected",
    )
    flow = rename_exit(flow, "gave_up", "failed")
    return check_sound(holding(flow, context="state", color="State"))


def seed(block: Block, *intents: Token, authority: str = "e1") -> dict[str, tuple[Token, ...]]:
    return {
        block.entry.place: intents,
        "authority": (Token("Authority", {"epoch": authority}),),
        "state": (Token("State", {"committed": 0}),),
    }


def intent(op: str, epoch: str = "e1") -> Token:
    return Token("Intent", {"op": op, "epoch": epoch})


class TestCapstone:
    def test_a_current_intent_settles_and_returns_the_state(self) -> None:
        world = {"outages": 0, "applied": []}
        block = capstone(world)
        engine = run(block, seed(block, intent("op-1")))
        assert [d["mode"] for d in place_data(engine, block.exits["done"].place)] == ["applied"]
        assert world["applied"] == ["op-1"]
        assert len(place_data(engine, "state")) == 1

    def test_a_stale_intent_discards_without_touching_the_world(self) -> None:
        world = {"outages": 0, "applied": []}
        block = capstone(world)
        engine = run(block, seed(block, intent("op-1", epoch="e0")))
        assert [d["mode"] for d in place_data(engine, block.exits["rejected"].place)] == ["discarded"]
        assert world["applied"] == []
        assert len(place_data(engine, "state")) == 1

    def test_a_transient_outage_loops_bounded_then_applies(self) -> None:
        world = {"outages": 2, "applied": []}
        block = capstone(world)
        engine = run(block, seed(block, intent("op-1")))
        [settled] = place_data(engine, block.exits["done"].place)
        assert settled["mode"] == "applied"
        assert settled["attempts"] == 2  # two transient laps, visible in the data
        assert world["applied"] == ["op-1"]

    def test_a_persistent_outage_exits_through_failed_still_releasing_the_state(self) -> None:
        world = {"outages": 99, "applied": []}
        block = capstone(world)
        engine = run(block, seed(block, intent("op-1")))
        assert [d["attempts"] for d in place_data(engine, block.exits["failed"].place)] == [2]
        assert world["applied"] == []
        assert len(place_data(engine, "state")) == 1  # released on the failure path too

    def test_an_ambiguous_repeat_converges_through_the_merge(self) -> None:
        world = {"outages": 0, "applied": ["op-1"]}  # the world already did it (AX21 lookup-first)
        block = capstone(world)
        engine = run(block, seed(block, intent("op-1")))
        assert [d["mode"] for d in place_data(engine, block.exits["done"].place)] == ["duplicate"]
        assert world["applied"] == ["op-1"]  # not reapplied

    def test_terminal_paths_leave_no_interior_marking(self) -> None:
        world = {"outages": 0, "applied": []}
        block = capstone(world)
        engine = run(block, seed(block, intent("op-1")))
        keep = {port.place for port in block.exits.values()} | {port.place for port in block.contexts.values()}
        for node in block.nodes:
            if isinstance(node, KernelPlace) and node.name not in keep:
                assert place_data(engine, node.name) == [], f"{node.name} leaked marking"

    def test_the_composed_net_lowers_deterministically(self) -> None:
        def rendered() -> bytes:
            built = compile_block("ax23-det", capstone({"outages": 0, "applied": []})).built
            return serialize_net_definition(project_net_definition(built.net))

        assert rendered() == rendered()
