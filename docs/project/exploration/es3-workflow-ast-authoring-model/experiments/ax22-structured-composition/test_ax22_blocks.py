"""AX22 focused tests — blocks compose like functions; the net follows.

The claim under test: with combinators as the only control flow and
function-like blocks as the only operands, the composite is sound by
construction (and a static checker proves it), purity propagates, the
AX20 disposable rule is enforced at composition time, and the frozen
engine runs the compiled result with no glue transitions.
"""

from __future__ import annotations

import pytest
from ax22_blocks import (
    Block,
    CompositionError,
    KernelPlace,
    Port,
    check_sound,
    classify,
    compile_block,
    disposable,
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

# -- the example: a fenced change pipeline built from four leaves -------------------


def validate() -> Block:
    return transform(
        "validate",
        lambda intent: {**intent, "payload": f"change:{intent['kind']}"},
        accepts="Intent",
        returns="Draft",
    )


def apply_at(world: dict) -> Block:
    """The commit boundary: the only leaf that touches the world."""

    def commit(draft: dict) -> tuple[str, dict]:
        if draft["base"] != world["base"]:
            return "stale", draft
        world["applied"].append(draft["op"])
        return "applied", draft

    return classify("apply", commit, accepts="Draft", outcomes={"applied": "Applied", "stale": "Stale"})


def finish() -> Block:
    return transform("finish", lambda done: {**done, "mode": "applied"}, accepts="Applied", returns="Done")


def record() -> Block:
    return transform("record", lambda husk: {**husk, "mode": "discarded"}, accepts="Stale", returns="Rejected")


def pipeline(world: dict) -> Block:
    flow = then(disposable(validate()), apply_at(world), on="out")
    flow = rename_exit(then(flow, finish(), on="applied"), "out", "done")
    flow = rename_exit(then(flow, record(), on="stale"), "out", "rejected")
    return check_sound(flow)


def intent(op: str, base: str = "e1", kind: str = "update") -> Token:
    return Token("Intent", {"op": op, "base": base, "kind": kind})


def run(block: Block, seed: Token, *, instance: str = "ax22") -> Engine:
    lowered = compile_block("ax22-pipeline", block)
    engine = Engine.create(
        lowered.built.net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking({NetPath(block.entry.place): (seed,)}),
        handlers=dict(lowered.handlers),
        guards=dict(lowered.built.guards),
        activities=(),
    )
    drive_bounded(engine)
    return engine


# -- behavior on the frozen engine ---------------------------------------------------


class TestPipeline:
    def test_a_current_intent_flows_to_the_done_exit(self) -> None:
        world = {"base": "e1", "applied": []}
        flow = pipeline(world)
        engine = run(flow, intent("op-1"))
        assert place_data(engine, flow.exits["done"].place) == [
            {"op": "op-1", "base": "e1", "kind": "update", "payload": "change:update", "mode": "applied"}
        ]
        assert world["applied"] == ["op-1"]

    def test_a_stale_intent_flows_to_the_rejected_exit_without_touching_the_world(self) -> None:
        world = {"base": "e2", "applied": []}
        flow = pipeline(world)
        engine = run(flow, intent("op-1", base="e1"))
        assert [d["mode"] for d in place_data(engine, flow.exits["rejected"].place)] == ["discarded"]
        assert world["applied"] == []

    def test_terminal_paths_leave_no_interior_marking(self) -> None:
        # The dynamic half of soundness (AX20's test), on a composed net.
        world = {"base": "e1", "applied": []}
        flow = pipeline(world)
        engine = run(flow, intent("op-1"))
        exit_places = {port.place for port in flow.exits.values()}
        for node in flow.nodes:
            if isinstance(node, KernelPlace) and node.name not in exit_places:
                assert place_data(engine, node.name) == [], f"{node.name} leaked marking"


# -- composition mechanics -------------------------------------------------------------


class TestFusion:
    def test_then_fuses_ports_no_glue_no_new_state(self) -> None:
        composed = then(validate(), apply_at({"base": "e1", "applied": []}), on="out")
        places = [node for node in composed.nodes if isinstance(node, KernelPlace)]
        assert len(places) == 2 + 3 - 1  # b's entry place absorbed
        assert composed.entry == Port("validate_in", "Intent")
        assert {name: port.place for name, port in composed.exits.items()} == {
            "applied": "apply_applied",
            "stale": "apply_stale",
        }

    def test_the_full_pipeline_is_six_places_four_transitions_nine_arcs(self) -> None:
        net = compile_block("ax22-shape", pipeline({"base": "e1", "applied": []})).built.net
        arcs = sum(len(net.inputs(t)) + len(net.outputs(t)) for t in net.transitions)
        assert (len(tuple(net.places)), len(tuple(net.transitions)), arcs) == (6, 4, 9)

    def test_lowering_is_deterministic(self) -> None:
        def rendered() -> bytes:
            built = compile_block("ax22-det", pipeline({"base": "e1", "applied": []})).built
            return serialize_net_definition(project_net_definition(built.net))

        assert rendered() == rendered()


class TestRefusals:
    def test_an_unknown_exit_is_named_with_the_alternatives(self) -> None:
        with pytest.raises(CompositionError, match=r"no exit 'oops'.*\['out'\]"):
            then(validate(), finish(), on="oops")

    def test_a_color_mismatch_names_both_ports(self) -> None:
        with pytest.raises(CompositionError, match=r"'out' \(Draft\) into 'record' entry \(Stale\)"):
            then(validate(), record(), on="out")

    def test_duplicate_exit_names_demand_an_explicit_rename(self) -> None:
        with pytest.raises(CompositionError, match="rename_exit"):
            two_outs = then(validate(), apply_at({"base": "e1", "applied": []}), on="out")
            two_outs = then(two_outs, finish(), on="applied")
            then(two_outs, transform("also_out", dict, accepts="Stale", returns="Rejected"), on="stale")

    def test_reused_leaf_names_are_refused(self) -> None:
        with pytest.raises(CompositionError, match="leaf names must be unique"):
            then(validate(), transform("validate", dict, accepts="Draft", returns="Draft"), on="out")

    def test_rename_exit_refuses_unknown_and_colliding_names(self) -> None:
        with pytest.raises(CompositionError, match="no exit 'done'"):
            rename_exit(validate(), "done", "out2")
        flow = then(validate(), apply_at({"base": "e1", "applied": []}), on="out")
        with pytest.raises(CompositionError, match="already has an exit 'stale'"):
            rename_exit(flow, "applied", "stale")


# -- purity and the disposable rule ------------------------------------------------------


class TestPurity:
    def test_purity_propagates_through_composition(self) -> None:
        touch_up = transform("touch_up", dict, accepts="Draft", returns="Draft")
        assert then(validate(), touch_up, on="out").pure
        assert not then(validate(), apply_at({"base": "e1", "applied": []}), on="out").pure

    def test_disposable_admits_pure_and_refuses_effectful_blocks(self) -> None:
        assert disposable(validate()) is not None
        with pytest.raises(CompositionError, match="the commit boundary is the only effect-emitting point"):
            disposable(then(validate(), apply_at({"base": "e1", "applied": []}), on="out"))

    def test_value_only_branching_may_declare_itself_pure(self) -> None:
        # AX5's type branching as a pure classify leaf: no world, so it
        # may live inside a disposable interior.
        split = classify(
            "split",
            lambda d: ("high", d) if d["score"] > 700 else ("low", d),
            accepts="Draft",
            outcomes={"high": "High", "low": "Low"},
            pure=True,
        )
        assert disposable(split).pure


# -- static soundness ---------------------------------------------------------------------


class TestSoundness:
    def test_composed_blocks_are_sound_by_construction(self) -> None:
        assert check_sound(pipeline({"base": "e1", "applied": []})) is not None

    def test_a_stranded_node_is_named(self) -> None:
        broken = Block(
            name="broken",
            nodes=(*validate().nodes, KernelPlace("orphan", "Nowhere")),
            entry=Port("validate_in", "Intent"),
            exits={"out": Port("validate_out", "Draft")},
            pure=True,
        )
        with pytest.raises(CompositionError, match=r"not sound.*\['orphan'\]"):
            check_sound(broken)

    def test_classify_refuses_indistinct_outcome_colors(self) -> None:
        # Color is how handlers address exits, so two same-colored
        # outcomes would be indistinguishable at the boundary.
        with pytest.raises(CompositionError, match="outcome colors must be distinct"):
            classify("dup", lambda d: ("a", d), accepts="X", outcomes={"a": "Same", "b": "Same"})
