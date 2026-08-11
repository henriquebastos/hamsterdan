"""AX2 focused tests — lowering, equivalence, determinism, execution, replay.

The toy domain mirrors the baseline's shape (typed request/result pairs
per activity) without touching production contracts.
"""

from dataclasses import asdict, dataclass

import pytest
from ax2_compiler import LoweringError, compile_workflow
from ax2_workflow_ast import activity, sequence
from petrus.engine import Engine
from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition, serialize_net_definition
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import DataclassPayloadConverter
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch


@dataclass(frozen=True)
class Draft:
    text: str


@dataclass(frozen=True)
class Review:
    text: str
    ok: bool


@dataclass(frozen=True)
class Publication:
    url: str


@motus_activity(converter=DataclassPayloadConverter())
def review(work: Draft) -> Review:
    return Review(text=work.text, ok=True)


@motus_activity(converter=DataclassPayloadConverter())
def publish(work: Review) -> Publication:
    return Publication(url=f"https://example.test/{work.text}")


DEFINITIONS = (review, publish)


def review_then_publish():
    return sequence(
        activity("review", request=Draft, result=Review),
        activity("publish", request=Review, result=Publication),
    )


def definition_bytes(net) -> bytes:
    return serialize_net_definition(project_net_definition(net))


def engine_for(compiled, *, history=None, load=False) -> Engine:
    door = Engine.load if load else Engine.create
    kwargs = {} if load else {"marking": Marking({compiled.entry: (Token("Draft", asdict(Draft(text="hello"))),)})}
    return door(
        compiled.built.net,
        "ax2-instance",
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=InlineDispatch({d.declaration.name: d for d in DEFINITIONS}),
        handlers=dict(compiled.handlers),
        guards=dict(compiled.built.guards),
        activities=compiled.activities,
        **kwargs,
    )


def drive_bounded(subject: Engine, limit: int = 50) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


class TestLoweredShape:
    def test_single_activity_fragment(self) -> None:
        compiled = compile_workflow(activity("review", request=Draft, result=Review), DEFINITIONS)
        net = compiled.built.net
        assert sorted(str(p) for p in net.places) == ["w.entry", "w.out"]
        assert [str(t) for t in net.transitions] == ["w.review"]
        assert [(str(a.source), str(a.target), a.color) for a in net.arcs] == [
            ("w.entry", "w.review", "Draft"),
            ("w.review", "w.out", "Review"),
        ]
        assert str(compiled.entry) == "w.entry"
        assert str(compiled.exit) == "w.out"

    def test_sequence_shares_intermediate_places_without_glue(self) -> None:
        compiled = compile_workflow(review_then_publish(), DEFINITIONS)
        net = compiled.built.net
        # N activities -> N transitions, N+1 places, 2N arcs. No glue.
        assert sorted(str(p) for p in net.places) == ["w.0.out", "w.1.out", "w.entry"]
        assert sorted(str(t) for t in net.transitions) == ["w.0.review", "w.1.publish"]
        assert [(str(a.source), str(a.target), a.color) for a in net.arcs] == [
            ("w.entry", "w.0.review", "Draft"),
            ("w.0.review", "w.0.out", "Review"),
            ("w.0.out", "w.1.publish", "Review"),
            ("w.1.publish", "w.1.out", "Publication"),
        ]

    def test_matches_manually_authored_equivalent(self) -> None:
        """The compiled net is byte-identical to today's DSL writing the same shape."""
        from petrus.impetus.dsl import NetSpec

        manual = NetSpec("workflow")
        entry = manual.s["w"].p.entry(Draft)
        first = manual.s["w"]["0"].t.review(handler="review")
        first_out = manual.s["w"]["0"].p.out(Review)
        second = manual.s["w"]["1"].t.publish(handler="publish")
        second_out = manual.s["w"]["1"].p.out(Publication)
        entry >> first >> first_out >> second >> second_out

        compiled = compile_workflow(review_then_publish(), DEFINITIONS)
        assert definition_bytes(compiled.built.net) == definition_bytes(manual.build().net)

    def test_source_map_links_both_directions(self) -> None:
        compiled = compile_workflow(review_then_publish(), DEFINITIONS)
        entry = compiled.source_map["/1"]
        assert entry.node == "activity 'publish'"
        assert entry.transition == "w.1.publish"
        assert entry.origin is not None and "test_ax2_compiler.py" in entry.origin
        assert compiled.generated_by["w.1.publish"] == "/1"
        assert compiled.generated_by["w.0.out"] == "/0"


class TestDeterminism:
    def test_recompilation_is_byte_identical(self) -> None:
        first = compile_workflow(review_then_publish(), DEFINITIONS)
        second = compile_workflow(review_then_publish(), DEFINITIONS)
        assert definition_bytes(first.built.net) == definition_bytes(second.built.net)


class TestLoweringErrors:
    def test_color_mismatch_names_both_ast_nodes(self) -> None:
        broken = sequence(
            activity("review", request=Draft, result=Review),
            activity("publish", request=Draft, result=Publication),  # wrong request
        )
        with pytest.raises(LoweringError) as caught:
            compile_workflow(broken, DEFINITIONS)
        message = str(caught.value)
        assert "activity 'review' at /0" in message
        assert "produces Review" in message
        assert "activity 'publish' at /1" in message
        assert "consumes Draft" in message
        assert "test_ax2_compiler.py" in message  # authoring origin is present

    def test_unknown_activity_name_lists_known_definitions(self) -> None:
        unknown = activity("reivew", request=Draft, result=Review)  # typo
        with pytest.raises(LoweringError, match="no activity definition named 'reivew'.*known: publish, review"):
            compile_workflow(unknown, DEFINITIONS)


class TestExecution:
    def test_sequence_executes_end_to_end_through_dispatch(self) -> None:
        compiled = compile_workflow(review_then_publish(), DEFINITIONS)
        subject = engine_for(compiled)
        drive_bounded(subject)

        final = [token.data for token in subject.marking.place(compiled.exit)]
        assert final == [{"url": "https://example.test/hello"}]
        # Intermediate places drained; entry consumed.
        assert not tuple(subject.marking.place(compiled.entry))
        assert not tuple(subject.marking.place(NetPath("w.0.out")))

        requested = [r.activity for r in subject.records if isinstance(r, ActivityRequested)]
        completed = [r for r in subject.records if isinstance(r, ActivityCompleted)]
        assert requested == ["review", "publish"]
        assert len(completed) == 2

    def test_replay_over_recompiled_net_reaches_same_state(self) -> None:
        history = InMemoryHistoryStore()
        original = compile_workflow(review_then_publish(), DEFINITIONS)
        subject = engine_for(original, history=history)
        drive_bounded(subject)

        recompiled = compile_workflow(review_then_publish(), DEFINITIONS)
        resumed = engine_for(recompiled, history=history, load=True)
        assert [token.data for token in resumed.marking.place(recompiled.exit)] == [
            {"url": "https://example.test/hello"}
        ]

    def test_replay_against_divergent_compilation_fails_loudly(self) -> None:
        """Nondeterministic path generation would break replay — prove it."""
        history = InMemoryHistoryStore()
        original = compile_workflow(review_then_publish(), DEFINITIONS)
        drive_bounded(engine_for(original, history=history))

        # A different AST lowers to different paths; the recorded history
        # references places this net does not have, so load must reject it.
        divergent = compile_workflow(activity("review", request=Draft, result=Review), DEFINITIONS)
        with pytest.raises(ValueError, match="not a place of this net"):
            engine_for(divergent, history=history, load=True)
