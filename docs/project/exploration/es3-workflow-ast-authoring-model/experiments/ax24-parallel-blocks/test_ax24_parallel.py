"""AX24 focused tests — total branches make the AND-join sound.

The claims under test:

- ``par`` (the 'all' policy) copies one input to every branch, waits
  for all of them, aggregates ``{branch: data}`` — and its totality
  precondition (exactly one exit per branch) is what guarantees the
  join can never dangle.
- A branch with meaningful variant exits totalizes first (route every
  variant into one result color, merge) and a downstream classify
  splits the aggregate — the composable-functions pattern, on a net.
- ``par_fail_fast`` is admissible only over pure, context-free
  branches; one ``armed`` token makes the outcome once-only; losing
  branches' late tokens drain into a visible ``abandoned`` exit; the
  construction is linear in the branch count.
- The ES-003 inquiry example — receive, parallel(reserve, taxes),
  charge — runs end to end on the frozen engine.
"""

from __future__ import annotations

import pytest
from ax23_blocks import (
    Block,
    KernelPlace,
    check_sound,
    classify,
    compile_block,
    merge,
    rename_exit,
    then,
    transform,
)
from ax23_blocks import (
    CompositionError as Composition23Error,
)
from ax24_parallel import CompositionError, par, par_fail_fast
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data

assert CompositionError is Composition23Error  # one error vocabulary across the algebra


def run(block: Block, marking: dict[str, tuple[Token, ...]], *, instance: str = "ax24") -> Engine:
    lowered = compile_block("ax24-net", block)
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


# -- the 'all' policy -------------------------------------------------------------------


def reserve() -> Block:
    return transform(
        "reserve",
        lambda order: {"sku": order["sku"], "reserved": True},
        accepts="Order",
        returns="Reservation",
    )


def taxes() -> Block:
    return transform(
        "taxes",
        lambda order: {"sku": order["sku"], "tax": round(order["amount"] * 0.2, 2)},
        accepts="Order",
        returns="Taxes",
    )


def gather() -> Block:
    return par("gather", {"inventory": reserve(), "taxes": taxes()}, returns="Quote")


class TestParAll:
    def test_the_join_aggregates_by_branch_name(self) -> None:
        block = check_sound(gather())
        engine = run(block, {block.entry.place: (Token("Order", {"sku": "sku-1", "amount": 10.0}),)})
        assert place_data(engine, block.exits["out"].place) == [
            {
                "inventory": {"sku": "sku-1", "reserved": True},
                "taxes": {"sku": "sku-1", "tax": 2.0},
            }
        ]

    def test_the_inquiry_example_runs_end_to_end(self) -> None:
        # ES-003's very first example: receive, parallel(reserve, taxes), charge.
        receive = transform(
            "receive",
            lambda intent: {"sku": intent["sku"], "amount": intent["amount"]},
            accepts="Intent",
            returns="Order",
        )
        charge = transform(
            "charge",
            lambda quote: {"total": quote["taxes"]["tax"] + 10.0, "sku": quote["inventory"]["sku"]},
            accepts="Quote",
            returns="Receipt",
        )
        flow = check_sound(then(then(receive, gather(), on="out"), charge, on="out"))
        engine = run(flow, {flow.entry.place: (Token("Intent", {"sku": "sku-1", "amount": 10.0}),)})
        assert place_data(engine, flow.exits["out"].place) == [{"total": 12.0, "sku": "sku-1"}]

    def test_totality_is_a_precondition_with_the_remedy_in_the_error(self) -> None:
        two_exits = classify(
            "risky",
            lambda d: ("ok", d),
            accepts="Order",
            outcomes={"ok": "Fine", "failed": "Broken"},
            pure=True,
        )
        with pytest.raises(CompositionError, match="must be total.*merge before joining"):
            par("gather", {"risky": two_exits, "taxes": taxes()}, returns="Quote")

    def test_branches_must_share_one_entry_color(self) -> None:
        other = transform("other", dict, accepts="Different", returns="Thing")
        with pytest.raises(CompositionError, match=r"one common color.*\['Different', 'Order'\]"):
            par("gather", {"inventory": reserve(), "other": other}, returns="Quote")

    def test_colliding_leaf_names_across_branches_are_refused(self) -> None:
        with pytest.raises(CompositionError, match="share node name.*leaf names must be unique"):
            par("gather", {"a": reserve(), "b": reserve()}, returns="Quote")

    def test_fewer_than_two_branches_is_refused(self) -> None:
        with pytest.raises(CompositionError, match="at least two branches"):
            par("gather", {"inventory": reserve()}, returns="Quote")

    def test_purity_propagates_and_effectful_branches_are_allowed(self) -> None:
        assert gather().pure
        world: list[str] = []

        def record(order: dict) -> dict:
            world.append(order["sku"])
            return {"logged": True}

        effectful = classify("audit", lambda d: ("out", record(d)), accepts="Order", outcomes={"out": "Audit"})
        effectful = rename_exit(effectful, "out", "out")
        block = par("gather", {"inventory": reserve(), "audit": effectful}, returns="Quote")
        assert not block.pure  # the 'all' policy tolerates effects: nothing is abandoned
        engine = run(block, {block.entry.place: (Token("Order", {"sku": "sku-1", "amount": 1.0}),)})
        assert world == ["sku-1"]
        [aggregate] = place_data(engine, block.exits["out"].place)
        assert aggregate["audit"] == {"logged": True}

    def test_a_shared_read_context_is_fused_once_and_read_concurrently(self) -> None:
        # Two branches read the same declared context place — read arcs
        # do not conflict (contextual nets), and the place appears once.
        left = classify(
            "left",
            lambda d, ctx: ("out", {"limit": ctx["cfg"]["limit"]}),
            accepts="Order",
            outcomes={"out": "Left"},
            reads=(("cfg", "Config"),),
        )
        right = classify(
            "right",
            lambda d, ctx: ("out", {"floor": ctx["cfg"]["floor"]}),
            accepts="Order",
            outcomes={"out": "Right"},
            reads=(("cfg", "Config"),),
        )
        block = par("both", {"left": left, "right": right}, returns="Quote")
        assert [n.name for n in block.nodes if isinstance(n, KernelPlace)].count("cfg") == 1
        assert sorted(block.contexts) == ["cfg"]
        engine = run(
            block,
            {
                block.entry.place: (Token("Order", {"sku": "s"}),),
                "cfg": (Token("Config", {"limit": 9, "floor": 1}),),
            },
        )
        assert place_data(engine, block.exits["out"].place) == [{"left": {"limit": 9}, "right": {"floor": 1}}]
        assert place_data(engine, "cfg") == [{"limit": 9, "floor": 1}]  # read, never consumed

    def test_no_interior_marking_survives(self) -> None:
        block = gather()
        engine = run(block, {block.entry.place: (Token("Order", {"sku": "s", "amount": 1.0}),)})
        for node in block.nodes:
            if isinstance(node, KernelPlace) and node.name != block.exits["out"].place:
                assert place_data(engine, node.name) == [], f"{node.name} leaked marking"

    def test_lowering_is_deterministic(self) -> None:
        def rendered() -> bytes:
            built = compile_block("ax24-det", gather()).built
            return serialize_net_definition(project_net_definition(built.net))

        assert rendered() == rendered()


# -- totalize, join, classify: failure as data through the 'all' policy --------------------


def total_branch(name: str, flag: str) -> Block:
    """A branch with meaningful ok/failed variants, totalized: every
    variant routed into one common result color, then merged — the
    Result-shaped token that makes the branch joinable."""
    split = classify(
        f"{name}_try",
        lambda d: ("ok", d) if d[flag] else ("failed", {"reason": f"{name} refused"}),
        accepts="Order",
        outcomes={"ok": f"{name}_fine", "failed": f"{name}_broken"},
        pure=True,
    )
    good = transform(f"{name}_good", lambda d: {"ok": True, "value": d}, accepts=f"{name}_fine", returns="BranchResult")
    bad = transform(
        f"{name}_bad", lambda d: {"ok": False, "error": d}, accepts=f"{name}_broken", returns="BranchResult"
    )
    block = rename_exit(then(split, good, on="ok"), "out", "good_done")
    block = rename_exit(then(block, bad, on="failed"), "out", "bad_done")
    return merge(block, "good_done", "bad_done", into="out")


def gather_results() -> Block:
    both = par(
        "attempt",
        {"left": total_branch("left", "left_ok"), "right": total_branch("right", "right_ok")},
        returns="Results",
    )
    verdict = classify(
        "verdict",
        lambda results: (
            ("settled", {name: r["value"] for name, r in results.items()})
            if all(r["ok"] for r in results.values())
            else ("problem", {"errors": [r["error"] for r in results.values() if not r["ok"]]})
        ),
        accepts="Results",
        outcomes={"settled": "Settled", "problem": "Problem"},
        pure=True,
    )
    return check_sound(then(both, verdict, on="out"))


class TestTotalizedFailure:
    def test_all_branches_ok_settles(self) -> None:
        block = gather_results()
        engine = run(block, {block.entry.place: (Token("Order", {"left_ok": True, "right_ok": True}),)})
        [settled] = place_data(engine, block.exits["settled"].place)
        assert set(settled) == {"left", "right"}

    def test_one_failed_branch_still_joins_and_the_verdict_carries_its_error(self) -> None:
        block = gather_results()
        engine = run(block, {block.entry.place: (Token("Order", {"left_ok": True, "right_ok": False}),)})
        assert place_data(engine, block.exits["problem"].place) == [{"errors": [{"reason": "right refused"}]}]

    def test_both_failures_accumulate_like_a_validation_applicative(self) -> None:
        block = gather_results()
        engine = run(block, {block.entry.place: (Token("Order", {"left_ok": False, "right_ok": False}),)})
        [problem] = place_data(engine, block.exits["problem"].place)
        assert problem["errors"] == [{"reason": "left refused"}, {"reason": "right refused"}]


# -- the fail-fast policy ------------------------------------------------------------------


def racing_branch(name: str, flag: str) -> Block:
    block = classify(
        name,
        lambda d: ("ok", {"winner": name}) if d[flag] else ("failed", {"loser": name}),
        accepts="Order",
        outcomes={"ok": f"{name}_done", "failed": "Failure"},
        pure=True,
    )
    return block


def race() -> Block:
    return par_fail_fast(
        "race",
        {"a": racing_branch("a", "a_ok"), "b": racing_branch("b", "b_ok")},
        returns="Both",
        failure="Failure",
    )


class TestParFailFast:
    def test_all_ok_joins_and_nothing_is_abandoned(self) -> None:
        block = check_sound(race())
        engine = run(block, {block.entry.place: (Token("Order", {"a_ok": True, "b_ok": True}),)})
        assert place_data(engine, block.exits["done"].place) == [{"a": {"winner": "a"}, "b": {"winner": "b"}}]
        assert place_data(engine, block.exits["failed"].place) == []
        assert place_data(engine, block.exits["abandoned"].place) == []

    def test_one_failure_wins_and_the_others_late_token_is_visible_debris(self) -> None:
        block = race()
        engine = run(block, {block.entry.place: (Token("Order", {"a_ok": True, "b_ok": False}),)})
        assert place_data(engine, block.exits["failed"].place) == [{"loser": "b"}]
        assert place_data(engine, block.exits["abandoned"].place) == [
            {"branch": "a", "verdict": "ok", "data": {"winner": "a"}}
        ]
        assert place_data(engine, block.exits["done"].place) == []

    def test_two_failures_produce_exactly_one_failed_token(self) -> None:
        # The armed token is the once-only: one abort takes it, the
        # other branch's failure is drained as debris, never doubled.
        block = race()
        engine = run(block, {block.entry.place: (Token("Order", {"a_ok": False, "b_ok": False}),)})
        assert len(place_data(engine, block.exits["failed"].place)) == 1
        [debris] = place_data(engine, block.exits["abandoned"].place)
        assert debris["verdict"] == "failed"

    def test_no_interior_marking_survives_any_outcome(self) -> None:
        block = race()
        exit_places = {port.place for port in block.exits.values()}
        for seedings in ({"a_ok": True, "b_ok": True}, {"a_ok": False, "b_ok": True}, {"a_ok": False, "b_ok": False}):
            engine = run(block, {block.entry.place: (Token("Order", dict(seedings)),)})
            for node in block.nodes:
                if isinstance(node, KernelPlace) and node.name not in exit_places:
                    assert place_data(engine, node.name) == [], f"{node.name} leaked after {seedings}"

    def test_the_construction_is_linear_one_abort_two_drains_per_branch(self) -> None:
        from ax19_kernel import BoundaryTransition

        block = race()
        machinery = [
            node.name for node in block.nodes if isinstance(node, BoundaryTransition) and node.name.startswith("race")
        ]
        # split + join + per branch (abort + 2 drains) = 2 + 3n, here n=2
        assert len(machinery) == 2 + 3 * 2

    def test_effectful_branches_are_refused_with_the_first_removal_lesson(self) -> None:
        effectful = classify(
            "audit",
            lambda d: ("ok", d),
            accepts="Order",
            outcomes={"ok": "Audit", "failed": "Failure"},
        )
        with pytest.raises(CompositionError, match="composable-functions removed `first`"):
            par_fail_fast(
                "race", {"audit": effectful, "b": racing_branch("b", "b_ok")}, returns="Both", failure="Failure"
            )

    def test_context_holding_branches_are_refused_even_when_pure(self) -> None:
        from ax23_blocks import holding

        held = holding(racing_branch("a", "a_ok"), context="mutex", color="Mutex")
        assert held.pure
        with pytest.raises(CompositionError, match="not disposable-eligible"):
            par_fail_fast("race", {"a": held, "b": racing_branch("b", "b_ok")}, returns="Both", failure="Failure")

    def test_branches_must_expose_exactly_ok_and_failed(self) -> None:
        single = transform("single", dict, accepts="Order", returns="Thing")
        with pytest.raises(CompositionError, match="exactly 'ok' and 'failed'"):
            par_fail_fast(
                "race", {"single": single, "b": racing_branch("b", "b_ok")}, returns="Both", failure="Failure"
            )

    def test_failure_exits_must_share_the_declared_color(self) -> None:
        odd = classify(
            "odd",
            lambda d: ("ok", d),
            accepts="Order",
            outcomes={"ok": "OddDone", "failed": "OtherFailure"},
            pure=True,
        )
        with pytest.raises(CompositionError, match="'OtherFailure', expected 'Failure'"):
            par_fail_fast("race", {"odd": odd, "b": racing_branch("b", "b_ok")}, returns="Both", failure="Failure")

    def test_lowering_is_deterministic(self) -> None:
        def rendered() -> bytes:
            built = compile_block("ax24-race-det", race()).built
            return serialize_net_definition(project_net_definition(built.net))

        assert rendered() == rendered()
