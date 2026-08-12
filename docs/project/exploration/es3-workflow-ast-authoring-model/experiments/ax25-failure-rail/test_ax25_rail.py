"""AX25 focused tests — the rail is a place, not a channel.

The claims under test:

- ``attempt`` is total: an exception becomes a wire-safe envelope on
  the ``failed`` exit; nothing escapes, nothing is hidden.
- ``rail_then`` fuses rails through an ordinary merge — after a chain,
  exactly ONE failure place exists, visible and on-path; downstream
  steps after a failure never run.
- ``recover`` rejoins the success track and receives the envelope.
- Domain outcomes stay typed exits; the sugar refuses to swallow them
  into the rail.
- The envelope survives JSON exactly (the composable-functions
  ``SerializableError`` caveat, answered by construction).
"""

from __future__ import annotations

import json

import pytest
from ax23_blocks import (
    Block,
    CompositionError,
    KernelPlace,
    check_sound,
    classify,
    compile_block,
    disposable,
    transform,
)
from ax25_rail import FAILURE, attempt, failure_data, rail_then, recover
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch
from test_ax11_fragment import drive_bounded, place_data


def run(block: Block, seed: Token, *, instance: str = "ax25") -> Engine:
    lowered = compile_block("ax25-net", block)
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


class Outage(Exception):
    """A transient infrastructure error for retryable classification."""


# -- the example: a three-step chain where the middle step can blow up ------------------


def parse() -> Block:
    return attempt("parse", lambda d: {**d, "parsed": True}, accepts="Raw", returns="Parsed", pure=True)


def enrich(world: dict) -> Block:
    def lookup(parsed: dict) -> dict:
        if parsed.get("boom"):
            raise ValueError("upstream returned garbage")
        world["lookups"] += 1
        return {**parsed, "enriched": True}

    return attempt("enrich", lookup, accepts="Parsed", returns="Enriched", retryable=(Outage,))


def store(world: dict) -> Block:
    def write(enriched: dict) -> dict:
        world["stored"].append(enriched)
        return {"id": len(world["stored"])}

    return attempt("store", write, accepts="Enriched", returns="StoreReceipt")


def chain(world: dict) -> Block:
    return check_sound(rail_then(rail_then(parse(), enrich(world)), store(world)))


def fresh_world() -> dict:
    return {"lookups": 0, "stored": []}


# -- totality and the envelope -----------------------------------------------------------


class TestAttempt:
    def test_success_routes_to_the_ok_exit(self) -> None:
        block = parse()
        engine = run(block, Token("Raw", {"payload": "x"}))
        assert place_data(engine, block.exits["out"].place) == [{"payload": "x", "parsed": True}]
        assert place_data(engine, block.exits["failed"].place) == []

    def test_an_exception_becomes_an_envelope_not_a_crash(self) -> None:
        world = fresh_world()
        block = enrich(world)
        engine = run(block, Token("Parsed", {"boom": True}))
        [envelope] = place_data(engine, block.exits["failed"].place)
        assert envelope == {
            "kind": "ValueError",
            "message": "upstream returned garbage",
            "source": "enrich",
            "retryable": False,
            "cause": [],
        }

    def test_a_declared_retryable_exception_sets_the_flag(self) -> None:
        def flaky(_: dict) -> dict:
            raise Outage("connection reset")

        block = attempt("flaky", flaky, accepts="Raw", returns="Never", retryable=(Outage,))
        engine = run(block, Token("Raw", {}))
        [envelope] = place_data(engine, block.exits["failed"].place)
        assert envelope["retryable"] is True
        assert envelope["kind"] == "Outage"

    def test_the_envelope_survives_json_exactly(self) -> None:
        # The composable-functions caveat: their SerializableError still
        # carries a live Error whose fields evaporate under JSON. This
        # envelope is plain data by construction — a full round-trip
        # loses nothing.
        envelope = failure_data(
            "ValueError",
            "bad input",
            source="enrich",
            retryable=True,
            cause=(failure_data("Outage", "reset", source="fetch"),),
        )
        assert json.loads(json.dumps(envelope)) == envelope


# -- the rail through composition ---------------------------------------------------------


class TestRailThen:
    def test_a_mid_chain_failure_stops_the_chain_and_names_its_source(self) -> None:
        world = fresh_world()
        block = chain(world)
        engine = run(block, Token("Raw", {"boom": True}))
        [envelope] = place_data(engine, block.exits["failed"].place)
        assert envelope["source"] == "enrich"
        assert world["stored"] == []  # store never ran
        assert place_data(engine, block.exits["out"].place) == []

    def test_the_success_track_is_undisturbed(self) -> None:
        world = fresh_world()
        block = chain(world)
        engine = run(block, Token("Raw", {"payload": "x"}))
        assert place_data(engine, block.exits["out"].place) == [{"id": 1}]
        assert world["lookups"] == 1

    def test_the_rail_is_exactly_one_visible_place(self) -> None:
        block = chain(fresh_world())
        rail_places = [node.name for node in block.nodes if isinstance(node, KernelPlace) and node.color == FAILURE]
        assert len(rail_places) == 1  # three attempts, two merges, one rail
        assert block.exits["failed"].place in rail_places

    def test_a_side_without_a_rail_passes_the_rail_through(self) -> None:
        plain = transform("plain", lambda d: {**d, "note": 1}, accepts="StoreReceipt", returns="Done")
        block = rail_then(chain(fresh_world()), plain)
        assert sorted(block.exits) == ["failed", "out"]
        assert block.exits["failed"].color == FAILURE

    def test_domain_outcomes_are_not_swallowed_into_the_rail(self) -> None:
        # A classify with meaningful typed exits composes on the ok
        # track; its domain exits survive beside the rail, untouched.
        judge = classify(
            "judge",
            lambda d: ("approved", d) if d["id"] == 1 else ("rejected", d),
            accepts="StoreReceipt",
            outcomes={"approved": "Approved", "rejected": "Rejected"},
            pure=True,
        )
        block = rail_then(chain(fresh_world()), judge)
        assert sorted(block.exits) == ["approved", "failed", "rejected"]

    def test_a_domain_exit_named_failed_is_refused_not_fused(self) -> None:
        imposter = classify(
            "imposter",
            lambda d: ("out", d),
            accepts="StoreReceipt",
            outcomes={"out": "Done", "failed": "DomainRefusal"},
            pure=True,
        )
        with pytest.raises(CompositionError, match="does not belong on the failure rail"):
            rail_then(chain(fresh_world()), imposter)

    def test_purity_propagates_through_the_sugar(self) -> None:
        left = attempt("halve", lambda d: {"n": d["n"] // 2}, accepts="Num", returns="Half", pure=True)
        right = attempt("negate", lambda d: {"n": -d["n"]}, accepts="Half", returns="Neg", pure=True)
        assert disposable(rail_then(left, right)).pure


# -- recovery ------------------------------------------------------------------------------


def fallback() -> Block:
    return transform(
        "fallback",
        lambda envelope: {"id": 0, "degraded": True, "because": envelope["kind"]},
        accepts=FAILURE,
        returns="StoreReceipt",
    )


class TestRecover:
    def test_recovery_rejoins_the_success_track_with_the_envelope_in_hand(self) -> None:
        world = fresh_world()
        block = check_sound(recover(chain(world), fallback()))
        engine = run(block, Token("Raw", {"boom": True}))
        assert place_data(engine, block.exits["out"].place) == [{"id": 0, "degraded": True, "because": "ValueError"}]
        assert "failed" not in block.exits  # the rail was consumed by the recovery

    def test_success_bypasses_the_handler(self) -> None:
        world = fresh_world()
        block = recover(chain(world), fallback())
        engine = run(block, Token("Raw", {"payload": "x"}))
        assert place_data(engine, block.exits["out"].place) == [{"id": 1}]

    def test_a_partial_handler_is_refused(self) -> None:
        partial = classify(
            "partial",
            lambda d: ("out", d),
            accepts=FAILURE,
            outcomes={"out": "StoreReceipt", "failed": FAILURE},
            pure=True,
        )
        with pytest.raises(CompositionError, match="must be total"):
            recover(chain(fresh_world()), partial)

    def test_a_handler_off_the_success_track_is_refused(self) -> None:
        wrong = transform("wrong", dict, accepts=FAILURE, returns="SomethingElse")
        with pytest.raises(CompositionError, match="recovery rejoins the success track"):
            recover(chain(fresh_world()), wrong)

    def test_a_handler_not_accepting_the_envelope_is_refused(self) -> None:
        deaf = transform("deaf", dict, accepts="NotAnEnvelope", returns="StoreReceipt")
        with pytest.raises(CompositionError, match="must accept the 'Failure' envelope"):
            recover(chain(fresh_world()), deaf)


# -- statics -------------------------------------------------------------------------------


class TestStatics:
    def test_the_chain_is_sound_and_lowering_is_deterministic(self) -> None:
        check_sound(recover(chain(fresh_world()), fallback()))

        def rendered() -> bytes:
            built = compile_block("ax25-det", recover(chain(fresh_world()), fallback())).built
            return serialize_net_definition(project_net_definition(built.net))

        assert rendered() == rendered()
