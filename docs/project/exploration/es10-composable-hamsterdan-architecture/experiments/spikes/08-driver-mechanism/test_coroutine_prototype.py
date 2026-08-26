from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from functools import partial
from itertools import pairwise
from typing import Any

import pytest
from coroutine_prototype import CoroutineStepper, LayeredWorld, calls, perform
from prototype import CutRef, Disposition, StepResult


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def _has_cut(result: StepResult, owner: str, kind: str) -> bool:
    return any(cut.owner == owner and cut.kind == kind for cut in result.cuts)


def _semantic_snapshot(snapshot: tuple[str, str]) -> tuple[dict[str, object], str]:
    retained = json.loads(snapshot[0])
    retained.pop("turn")
    return retained, snapshot[1]


async def _complete(world: LayeredWorld) -> tuple[StepResult, ...]:
    report = await world.timeline().run(500)

    assert not report.budget_exhausted
    assert not report.cancelled
    assert report.results[-1].disposition is Disposition.TERMINAL
    return report.results


def test_nested_owner_code_yields_the_actual_leaf_callable() -> None:
    async def scenario() -> None:
        world = LayeredWorld.fresh(("pr-1",))
        stepper = world.stepper()

        selected = await stepper.step()
        offered = stepper.offer()

        assert _has_cut(selected, "host", "subject_selected")
        assert callable(offered)
        assert calls(offered, LayeredWorld.claim_activity)

        operation, leaf = await stepper.execute_pending()
        returned = stepper.finish_step()

        assert operation is offered
        assert isinstance(leaf, StepResult)
        assert _has_cut(leaf, "readiness", "activity_attempt_claimed")
        assert _has_cut(returned, "host", "readiness_step_returned")
        assert _has_cut(returned, "readiness", "activity_attempt_claimed")

    _run(scenario())


def test_debugger_stops_before_leaf_after_leaf_and_after_owner_return() -> None:
    async def scenario() -> None:
        world = LayeredWorld.fresh(("pr-1",))
        timeline = world.timeline()

        operation = await timeline.run_until_before(LayeredWorld.observe_or_execute_activity)
        before_retained, before_effects = world.snapshot()

        assert calls(operation, LayeredWorld.observe_or_execute_activity)
        assert json.loads(before_effects)["outcomes"] == {}

        executed, observation = await timeline.execute_pending()
        after_leaf_retained, after_leaf_effects = world.snapshot()

        assert executed is operation
        assert observation == ("accepted:pr-1:publication", "effect", 1)
        assert after_leaf_retained == before_retained
        assert json.loads(after_leaf_effects)["effect_calls"] == {"pr-1:publication": 1}

        returned = timeline.finish_step()

        assert _has_cut(returned, "host", "readiness_step_returned")
        assert _has_cut(returned, "readiness", "activity_effect_observed")
        assert returned.effect_source == "effect"
        assert returned.external_calls == 1

    _run(scenario())


@pytest.mark.parametrize("crash", ["before_leaf", "after_leaf", "after_return"])
def test_effect_cut_reconstructs_without_a_coroutine_frame(crash: str) -> None:
    async def scenario() -> None:
        world = LayeredWorld.fresh(("pr-1",))
        timeline = world.timeline()
        await timeline.run_until_before(LayeredWorld.observe_or_execute_activity)

        expected_source = "effect"
        if crash != "before_leaf":
            await timeline.execute_pending()
            expected_source = "lookup"
        if crash == "after_return":
            returned = timeline.finish_step()
            assert _has_cut(returned, "readiness", "activity_effect_observed")

        snapshot = world.snapshot()
        timeline.close()
        recovered = LayeredWorld.restore(*snapshot)
        recovered_timeline = recovered.timeline()

        operation, observation = await recovered_timeline.run_until_after(LayeredWorld.observe_or_execute_activity)

        assert calls(operation, LayeredWorld.observe_or_execute_activity)
        assert observation[1] == expected_source
        assert observation[2] == (1 if expected_source == "effect" else 0)

        returned = recovered_timeline.finish_step()
        assert _has_cut(returned, "readiness", "activity_effect_observed")
        await _complete(recovered)

        effects = json.loads(recovered.snapshot()[1])
        assert effects["effect_calls"] == {"pr-1:publication": 1}

    _run(scenario())


def test_every_returned_result_reconstructs_to_the_same_durable_state() -> None:
    async def scenario() -> None:
        baseline = LayeredWorld.fresh()
        baseline_results = await _complete(baseline)
        baseline_state = baseline.snapshot()

        for crash_after in range(len(baseline_results) - 1):
            world = LayeredWorld.fresh()
            timeline = world.timeline()
            for _ in range(crash_after + 1):
                await timeline.step()

            snapshot = world.snapshot()
            timeline.close()
            recovered = LayeredWorld.restore(*snapshot)
            await _complete(recovered)

            assert _semantic_snapshot(recovered.snapshot()) == _semantic_snapshot(baseline_state)
            effects = json.loads(recovered.snapshot()[1])
            assert effects["effect_calls"] == {
                "pr-1:publication": 1,
                "pr-2:publication": 1,
            }

    _run(scenario())


def test_production_shaped_drain_preserves_bounds_and_host_fairness() -> None:
    async def scenario() -> None:
        world = LayeredWorld.fresh()
        report = await world.stepper().run(500)
        results = report.results
        selections = [result.cut.subject for result in results if _has_cut(result, "host", "subject_selected")]

        assert not report.budget_exhausted
        assert results[-1].disposition is Disposition.TERMINAL
        assert selections
        assert all(left != right for left, right in pairwise(selections))
        assert set(selections) == {"pr-1", "pr-2"}
        assert all(result.external_calls <= 1 for result in results)

        readiness_calls = 0
        for result in results:
            if _has_cut(result, "host", "subject_selected"):
                readiness_calls = 0
            elif _has_cut(result, "host", "readiness_step_returned"):
                readiness_calls += 1
                assert readiness_calls == 1

    _run(scenario())


def test_budget_and_cancellation_stop_between_leaf_calls() -> None:
    async def scenario() -> None:
        world = LayeredWorld.fresh()
        stepper = world.stepper()

        report = await stepper.run(7)
        assert report.budget_exhausted
        assert len(report.results) == 7
        before_cancel = world.snapshot()

        stepper.cancel()
        cancelled = await stepper.run(100)

        assert cancelled.cancelled
        assert cancelled.results == ()
        assert world.snapshot() == before_cancel

        restored = LayeredWorld.restore(*before_cancel)
        await _complete(restored)

    _run(scenario())


def test_one_owner_step_cannot_hide_a_second_leaf_operation() -> None:
    async def first() -> StepResult:
        return StepResult(Disposition.PROGRESSED, CutRef("probe", "first"))

    async def second() -> StepResult:
        return StepResult(Disposition.PROGRESSED, CutRef("probe", "second"))

    async def invalid_entry() -> StepResult:
        await perform(partial(first))
        return await perform(partial(second))

    async def scenario() -> None:
        stepper = CoroutineStepper(invalid_entry)

        with pytest.raises(RuntimeError, match="awaited more than one operation"):
            await stepper.step()

    _run(scenario())
