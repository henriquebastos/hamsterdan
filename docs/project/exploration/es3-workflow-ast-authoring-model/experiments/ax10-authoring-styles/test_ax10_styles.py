"""AX10 focused tests — four spellings, one AST, and each style's failure mode."""

import pytest
from ax10_ast import Activity, Parallel, Retry, Sequence, parallel, render, retry, sequence
from ax10_styles import (
    BuilderError,
    Flow,
    WorkflowBuilder,
    build_workflow,
)

# The comparison workflow — deep enough that a five-line demo cannot hide
# a style's nesting behavior: a parallel with a multi-step branch, a retry,
# and a tail step.

EXPECTED = Sequence(
    (
        Activity("receive_order"),
        Parallel(
            (
                Sequence((Activity("reserve_inventory"), Activity("confirm_reservation"))),
                Activity("calculate_taxes"),
            )
        ),
        Retry(Activity("charge_customer"), 3),
        Activity("notify_customer"),
    )
)


def nested_combinators():
    return sequence(
        "receive_order",
        parallel(
            sequence("reserve_inventory", "confirm_reservation"),
            "calculate_taxes",
        ),
        retry("charge_customer", limit=3),
        "notify_customer",
    )


def fluent():
    return (
        Flow.start("receive_order")
        .parallel(
            Flow.start("reserve_inventory").then("confirm_reservation"),
            "calculate_taxes",
        )
        .retry("charge_customer", limit=3)
        .then("notify_customer")
        .build()
    )


def context_manager():
    flow = WorkflowBuilder()
    flow.do("receive_order")
    with flow.parallel():
        with flow.branch():
            flow.do("reserve_inventory")
            flow.do("confirm_reservation")
        with flow.branch():
            flow.do("calculate_taxes")
    with flow.retry(limit=3):
        flow.do("charge_customer")
    flow.do("notify_customer")
    return flow.build()


def generator():
    def order_process():
        yield "receive_order"
        yield parallel(
            sequence("reserve_inventory", "confirm_reservation"),
            "calculate_taxes",
        )
        yield retry("charge_customer", limit=3)
        yield "notify_customer"

    return build_workflow(order_process)


class TestOneAst:
    @pytest.mark.parametrize("style", [nested_combinators, fluent, context_manager, generator])
    def test_every_style_produces_the_same_canonical_ast(self, style) -> None:
        assert style() == EXPECTED

    def test_the_tree_is_printable(self) -> None:
        printed = render(EXPECTED)
        assert "parallel" in printed
        assert "retry limit=3" in printed
        assert printed.splitlines()[0] == "sequence"


class TestFluent:
    def test_prefix_reuse_is_safe_because_flows_are_immutable(self) -> None:
        prefix = Flow.start("receive_order").then("validate")
        one = prefix.then("ship").build()
        two = prefix.then("cancel").build()
        assert one == Sequence((Activity("receive_order"), Activity("validate"), Activity("ship")))
        assert two == Sequence((Activity("receive_order"), Activity("validate"), Activity("cancel")))

    def test_nesting_forces_a_style_break(self) -> None:
        """A multi-step parallel branch cannot stay in the chain: it becomes a
        nested Flow expression — the fluent style degenerates to combinators
        exactly where workflows get interesting."""
        built = Flow.start("a").parallel(Flow.start("b").then("c"), "d").build()
        assert built == Sequence(
            (
                Activity("a"),
                Parallel((Sequence((Activity("b"), Activity("c"))), Activity("d"))),
            )
        )


class TestContextManager:
    def test_builder_is_single_use(self) -> None:
        flow = WorkflowBuilder()
        flow.do("a")
        flow.do("b")
        flow.build()
        with pytest.raises(BuilderError, match="already built"):
            flow.do("c")

    def test_branch_outside_parallel_is_refused(self) -> None:
        flow = WorkflowBuilder()
        with pytest.raises(BuilderError, match="only meaningful inside a parallel"), flow.branch():
            flow.do("a")

    def test_single_branch_parallel_is_refused(self) -> None:
        flow = WorkflowBuilder()
        with pytest.raises(BuilderError, match="at least two branches"), flow.parallel():
            flow.do("only")


class TestGenerator:
    def test_static_python_loop_unrolls_into_repeated_nodes(self) -> None:
        """A Python `for` over a static range is compile-time unrolling, not a
        workflow loop — durable cycles still require the retry/loop combinator
        (AX8)."""

        def polling():
            for attempt in range(2):
                yield f"poll_{attempt}"
            yield "done"

        built = build_workflow(polling)
        assert built == Sequence((Activity("poll_0"), Activity("poll_1"), Activity("done")))

    def test_branching_on_a_step_result_is_refused(self) -> None:
        def branching():
            approved = yield "evaluate"
            if approved:
                yield "ship"

        with pytest.raises(TypeError, match="symbolic at authoring time"):
            build_workflow(branching)


class TestErrorLocality:
    def test_combinator_names_the_offending_position(self) -> None:
        with pytest.raises(TypeError, match=r"sequence step 1: expected an activity"):
            sequence("ok", 42)

    def test_fluent_names_the_offending_call(self) -> None:
        with pytest.raises(TypeError, match=r"Flow\.then: expected an activity"):
            Flow.start("ok").then(42)

    def test_builder_names_the_offending_call(self) -> None:
        flow = WorkflowBuilder()
        with pytest.raises(TypeError, match=r"WorkflowBuilder\.do: expected an activity"):
            flow.do(42)

    def test_generator_names_the_offending_yield(self) -> None:
        def broken():
            yield "ok"
            yield 42

        with pytest.raises(TypeError, match=r"workflow yield 1: expected an activity"):
            build_workflow(broken)
