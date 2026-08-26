from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import pairwise
from typing import cast

import pytest
from prototype import (
    MAX_DRIVER_BUDGET,
    CutRef,
    Disposition,
    DriverKind,
    StepResult,
    World,
    make_driver,
)

DRIVER_KINDS = tuple(DriverKind)

EXPECTED_CUTS = {
    ("workflow", "history_page_replayed"),
    ("workflow", "occurrence_repaired"),
    ("workflow", "observation_accepted"),
    ("workflow", "observation_folded"),
    ("workflow", "workflow_action_committed"),
    ("readiness", "runtime_reconstructed"),
    ("readiness", "ingress_staged"),
    ("readiness", "ingress_entry_accepted"),
    ("readiness", "ingress_entry_folded"),
    ("readiness", "workflow_advanced"),
    ("readiness", "activity_attempt_claimed"),
    ("readiness", "activity_effect_observed"),
    ("readiness", "activity_terminal_recorded"),
    ("readiness", "timer_command_applied"),
    ("readiness", "timer_ack_accepted"),
    ("readiness", "timer_ack_marked"),
    ("readiness", "timer_maturity_claimed"),
    ("readiness", "timer_maturity_accepted"),
    ("readiness", "timer_maturity_marked"),
    ("readiness", "deferred_wake_accepted"),
    ("readiness", "agent_route_settled"),
    ("host", "catalog_page_inspected"),
    ("host", "custody_item_disposed"),
    ("host", "subject_selected"),
    ("host", "instance_opened"),
    ("host", "readiness_step_returned"),
    ("host", "delivery_acknowledged"),
    ("host", "posture_recorded"),
    ("host", "agent_route_recorded"),
    ("host", "subject_requeued"),
    ("host", "instance_closed"),
}


def _fingerprint(result: StepResult) -> tuple[object, ...]:
    return (
        result.disposition,
        tuple((cut.owner, cut.kind, cut.subject, cut.identity) for cut in result.cuts),
        result.rows,
        result.external_calls,
        result.effect_source,
        result.admission,
    )


def _complete(kind: DriverKind, world: World) -> tuple[StepResult, ...]:
    report = make_driver(kind, world).run(10_000)
    assert not report.budget_exhausted
    assert not report.cancelled
    assert report.results[-1].disposition is Disposition.TERMINAL
    return report.results


def _semantic_snapshot(snapshot: tuple[str, str]) -> tuple[dict[str, object], str]:
    retained = json.loads(snapshot[0])
    retained.pop("turn")
    return retained, snapshot[1]


@pytest.mark.parametrize("kind", DRIVER_KINDS)
def test_all_mechanisms_expose_the_same_cut_vocabulary(kind: DriverKind) -> None:
    explicit = _complete(DriverKind.EXPLICIT, World.fresh())
    candidate_world = World.fresh()
    candidate = _complete(kind, candidate_world)

    assert tuple(map(_fingerprint, candidate)) == tuple(map(_fingerprint, explicit))
    assert len(candidate) == 207
    assert sum(result.cut is not None for result in candidate) == 206
    observed = {(cut.owner, cut.kind) for result in candidate for cut in result.cuts}
    assert observed == EXPECTED_CUTS
    assert all(result.rows <= World.history_records_per_page for result in candidate)
    assert all(result.external_calls <= 1 for result in candidate)
    effect_calls = json.loads(candidate_world.snapshot()[1])["effect_calls"]
    assert len(effect_calls) == 2
    assert set(effect_calls.values()) == {1}


@pytest.mark.parametrize("kind", DRIVER_KINDS)
def test_every_returned_cut_reconstructs_from_serialized_state(kind: DriverKind) -> None:
    baseline = World.fresh()
    baseline_results = _complete(kind, baseline)
    baseline_state = baseline.snapshot()
    cut_positions = [index for index, result in enumerate(baseline_results) if result.cut is not None]

    for crash_after in cut_positions:
        world = World.fresh()
        driver = make_driver(kind, world)
        prefix = tuple(driver.one() for _ in range(crash_after + 1))
        crashed_result = prefix[-1]

        retained, effects = world.snapshot()
        world = World.restore(retained, effects)
        remainder = _complete(kind, world)

        recovered_state = world.snapshot()
        assert _semantic_snapshot(recovered_state) == _semantic_snapshot(baseline_state)
        assert json.loads(recovered_state[0])["turn"] >= json.loads(baseline_state[0])["turn"]
        effect_calls = json.loads(recovered_state[1])["effect_calls"]
        assert len(effect_calls) == 2
        assert set(effect_calls.values()) == {1}
        if any(cut.kind == "activity_effect_observed" for cut in crashed_result.cuts):
            crashed_cut = crashed_result.cut
            assert crashed_cut is not None
            replay = next(
                result
                for result in remainder
                if any(cut.kind == "activity_effect_observed" for cut in result.cuts)
                and any(cut.subject == crashed_cut.subject for cut in result.cuts)
            )
            assert replay.effect_source == "lookup"
            assert replay.external_calls == 0


@pytest.mark.parametrize("kind", DRIVER_KINDS)
def test_driver_cancellation_and_budget_stop_between_cuts(kind: DriverKind) -> None:
    world = World.fresh()
    driver = make_driver(kind, world)

    first = driver.run(7)
    assert first.budget_exhausted
    assert len(first.results) == 7
    before_cancel = world.snapshot()

    driver.cancel()
    cancelled = driver.run(100)
    assert cancelled.cancelled
    assert cancelled.results == ()
    assert world.snapshot() == before_cancel

    restored = World.restore(*before_cancel)
    results = _complete(kind, restored)
    assert results[-1].disposition is Disposition.TERMINAL


@pytest.mark.parametrize("kind", DRIVER_KINDS)
def test_host_selection_is_weakly_fair(kind: DriverKind) -> None:
    results = _complete(kind, World.fresh())
    selected = [
        result.cut.subject for result in results if result.cut is not None and result.cut.kind == "subject_selected"
    ]

    assert selected
    assert len(selected) == 40
    assert all(left != right for left, right in pairwise(selected))
    assert set(selected) == {"pr-1", "pr-2"}

    readiness_calls = 0
    for result in results:
        if result.cut is not None and result.cut.kind == "subject_selected":
            readiness_calls = 0
        elif result.cut is not None and result.cut.kind == "readiness_step_returned":
            readiness_calls += 1
            assert readiness_calls == 1


@dataclass
class _LongStepper:
    remaining: int

    def step(self) -> StepResult:
        if self.remaining == 0:
            return StepResult(Disposition.QUIESCENT)
        self.remaining -= 1
        return StepResult(Disposition.PROGRESSED, CutRef("probe", "counted"))


@pytest.mark.parametrize("kind", DRIVER_KINDS)
def test_long_drives_do_not_grow_the_python_stack(kind: DriverKind) -> None:
    report = make_driver(kind, _LongStepper(10_000)).run(10_001)

    assert not report.budget_exhausted
    assert len(report.results) == 10_001
    assert report.results[-1].disposition is Disposition.QUIESCENT


@pytest.mark.parametrize("budget", [-1, True, 1.5, MAX_DRIVER_BUDGET + 1])
def test_driver_budget_is_a_bounded_integer(budget: object) -> None:
    with pytest.raises(ValueError, match="integer from 0 through"):
        make_driver(DriverKind.EXPLICIT, _LongStepper(1)).run(cast(int, budget))
