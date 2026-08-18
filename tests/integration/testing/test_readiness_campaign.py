from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pytest
from hypothesis import HealthCheck, event, example, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,
)
from petrus.testing.dst import (
    BudgetExhausted,
    ChoiceAuthority,
    Disposition,
    InvariantViolation,
    encode_artifact,
    load_artifact,
)
from pydantic import JsonValue

from hamsterdan.host.testing.readiness_world import (
    BASE,
    HEAD,
    READINESS_POLICY_DIGEST,
    ReadinessTimeline,
    ReadinessWorld,
    replay_readiness,
)

_AUTHORITY_HEAD = "c" * 40
_GENERATED_ACTIONS = ("step", "restart", "redeliver-old", "redeliver-current")


def _start_clean_green(timeline: ReadinessTimeline, *, response_lost: bool) -> str:
    timeline.set_pull_request(
        head=HEAD,
        base=BASE,
        policy=READINESS_POLICY_DIGEST,
        lifecycle="active",
        strict_base=True,
        base_current=True,
        mergeable=True,
    )
    timeline.set_ci(head=HEAD, required_checks=("build",), checks={"build": "success"})
    timeline.set_review(head=HEAD, status="clear")
    delivery = timeline.emit_webhook("pull_request", action="synchronize")
    if response_lost:
        timeline.lose_effect_response("readiness")
    timeline.deliver_webhook(delivery)
    return delivery


def _retain_failure_artifact(
    world: ReadinessWorld,
    *,
    scenario_id: str,
    failure_path: Path,
    replay_root: Path,
    primary: BaseException,
) -> bool:
    if world.world.disposition not in {
        Disposition.BUDGET_EXHAUSTED,
        Disposition.INVARIANT_FAILURE,
    }:
        return False
    try:
        artifact = world.artifact(scenario_id)
        encoded = encode_artifact(artifact) + b"\n"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_bytes(encoded)
        replayed = replay_readiness(artifact, replay_root)
        if (
            replayed.outcome != "pass"
            or replayed.disposition != world.world.disposition.value
            or replayed.failure is None
        ):
            raise AssertionError("retained readiness counterexample did not replay its exact failure")
        primary.add_note(
            f"retained exact readiness DST counterexample at {failure_path} ({artifact.expected.journal_digest})"
        )
    except Exception as retention_error:  # noqa: BLE001 - preserve the primary counterexample
        primary.add_note(
            f"secondary readiness counterexample retention failure: {type(retention_error).__name__}: {retention_error}"
        )
        return False
    return True


def test_timeline_steps_one_disclosed_host_action(tmp_path: Path) -> None:
    world = ReadinessWorld(tmp_path)
    timeline = world.timeline()
    delivery = _start_clean_green(timeline, response_lost=False)
    try:
        assert timeline.pending()

        result = timeline.step()

        assert result.value == {"custody": {"delivery": delivery, "disposition": "completed"}}
    finally:
        world.close()


class _DeliveryRecoveryMachine(RuleBasedStateMachine):
    def __init__(
        self,
        *,
        force_failure: bool = False,
        failure_path: Path = Path(".hypothesis/readiness-artifacts/readiness-counterexample-v4.json"),
    ) -> None:
        super().__init__()
        self._directory = TemporaryDirectory(prefix="hamsterdan-readiness-campaign-")
        self._world: ReadinessWorld | None = None
        self._timeline: ReadinessTimeline | None = None
        self._delivery = ""
        self._scenario_id = "readiness-generated-counterexample-v4"
        self._seed = 0
        self._response_lost = False
        self._redeliver_at_finish = False
        self._force_failure = force_failure
        self._failure_path = failure_path
        self._failure_retained = False
        self._closed = False

    @initialize(seed=st.integers(min_value=0, max_value=2**53 - 1))
    def start(self, seed: int) -> None:
        self._seed = seed
        self._world = ReadinessWorld(Path(self._directory.name) / "live", seed=seed)
        self._timeline = self._world.timeline()
        choices = self._world.world.choices
        self._response_lost = choices.index(ChoiceAuthority.FAULT, 2) == 1
        crash_before_first_step = choices.index(ChoiceAuthority.EVENT_ORDER, 2) == 1
        self._redeliver_at_finish = choices.index(ChoiceAuthority.WORKLOAD, 2) == 1
        self._scenario_id = choices.identifier("scenario")
        event(f"response_lost={self._response_lost}")
        event(f"crash_before_first_step={crash_before_first_step}")
        event(f"redeliver_at_finish={self._redeliver_at_finish}")
        if self._force_failure:
            self._delivery = self._active_timeline().emit_webhook("issue_comment", action="created")
            self._active_timeline().deliver_webhook(self._delivery)
            return
        self._delivery = _start_clean_green(self._timeline, response_lost=self._response_lost)
        if crash_before_first_step:
            self._capture_failure(lambda: self._restart("generated_before_first_host_step"))

    @precondition(lambda self: not self._force_failure and self._timeline is not None and self._timeline.pending())
    @rule()
    def execute_one_disclosed_action(self) -> None:
        event("generated_action=step")
        self._capture_failure(self._active_timeline().step)

    @precondition(lambda self: not self._force_failure and self._timeline is not None and not self._timeline.pending())
    @rule()
    def redeliver_after_quiescence(self) -> None:
        event("generated_action=redeliver")
        self._capture_failure(lambda: self._active_timeline().deliver_webhook(self._delivery))

    @precondition(lambda self: not self._force_failure)
    @rule()
    def restart_generation(self) -> None:
        event("generated_action=restart")
        self._capture_failure(lambda: self._restart("generated_between_host_steps"))

    @precondition(lambda self: self._force_failure and self._timeline is not None and self._timeline.pending())
    @rule()
    def trigger_replayable_checker_failure(self) -> None:
        self._capture_failure(self._active_timeline().step)

    @invariant()
    def independent_safety_holds_at_each_generated_boundary(self) -> None:
        observation = self._capture_failure(self._active_timeline().observe)
        state = cast(dict[str, JsonValue], observation.value)
        provider = cast(dict[str, JsonValue], state["provider"])
        accepted = cast(dict[str, JsonValue], provider["accepted_by_kind"])
        facts = cast(dict[str, JsonValue], state["facts"])
        expected = cast(dict[str, JsonValue], state["expected"])
        assert cast(int, accepted.get("readiness", 0)) <= 1
        assert len(cast(list[JsonValue], facts["admitted_observations"])) <= 1
        assert expected["violations"] == []

    def teardown(self) -> None:
        world = self._world
        if world is None:
            self._directory.cleanup()
            return
        primary = sys.exception()
        try:
            if primary is not None:
                if isinstance(primary, (BudgetExhausted, InvariantViolation)):
                    self._retain_failure(primary)
            elif self._force_failure:
                return
            elif world.world.disposition is None:
                timeline = self._active_timeline()
                while timeline.pending():
                    self._capture_failure(timeline.step)
                if self._redeliver_at_finish:
                    self._capture_failure(lambda: timeline.deliver_webhook(self._delivery))
                observation = self._capture_failure(timeline.converge)
                final = cast(dict[str, JsonValue], observation.value)
                expected = cast(dict[str, JsonValue], final["expected"])
                provider = cast(dict[str, JsonValue], final["provider"])
                accepted = cast(dict[str, JsonValue], provider["accepted_by_kind"])
                facts = cast(dict[str, JsonValue], final["facts"])
                assert expected["ready"] is True
                assert cast(dict[str, JsonValue], final["actual"])["readiness_published"] is True
                assert accepted["readiness"] == 1
                assert facts["admitted_observations"] == [f"github-delivery:{self._delivery}"]
                if self._response_lost:
                    assert cast(int, provider["lookup_recoveries"]) >= 1

                artifact = world.artifact(self._scenario_id)
                assert artifact.version == 4
                assert artifact.origin is not None
                assert artifact.origin.seed == self._seed
                assert artifact.origin.draws == {
                    "event_order": 1,
                    "fault": 1,
                    "identifier:scenario": 1,
                    "workload": 1,
                }
                operations = len(artifact.operations)
                world.close()
                self._closed = True

                replayed = replay_readiness(artifact, Path(self._directory.name) / "replay")
                assert replayed.outcome == "pass"
                assert replayed.disposition == Disposition.CONVERGED.value
                assert replayed.failure is None
                assert replayed.operations == operations
            else:
                raise AssertionError(f"generated World ended unexpectedly as {world.world.disposition.value}")
        except BaseException as teardown_error:
            if primary is not None:
                primary.add_note(
                    f"secondary readiness campaign teardown failure: {type(teardown_error).__name__}: {teardown_error}"
                )
            else:
                primary = teardown_error
                raise
        finally:
            try:
                if not self._closed:
                    world.close()
            except BaseException as close_error:
                if primary is not None:
                    primary.add_note(
                        f"secondary readiness campaign close failure: {type(close_error).__name__}: {close_error}"
                    )
                else:
                    primary = close_error
                    raise
            finally:
                try:
                    self._directory.cleanup()
                except BaseException as cleanup_error:
                    if primary is not None:
                        primary.add_note(
                            "secondary readiness campaign directory cleanup failure: "
                            f"{type(cleanup_error).__name__}: {cleanup_error}"
                        )
                    else:
                        raise

    def _active_timeline(self) -> ReadinessTimeline:
        if self._timeline is None:
            raise AssertionError("generated readiness timeline is not initialized")
        return self._timeline

    def _restart(self, cut: str) -> None:
        timeline = self._active_timeline()
        world = self._world
        if world is None:
            raise AssertionError("generated readiness world is not initialized")
        timeline.crash(cut)
        self._timeline = world.restart()

    def _capture_failure[T](self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except (BudgetExhausted, InvariantViolation) as error:
            self._retain_failure(error)
            raise

    def _retain_failure(self, primary: BaseException) -> None:
        if self._failure_retained:
            return
        world = self._world
        if world is None:
            return
        self._failure_retained = _retain_failure_artifact(
            world,
            scenario_id=self._scenario_id,
            failure_path=self._failure_path,
            replay_root=Path(self._directory.name) / "failure-replay",
            primary=primary,
        )


def _run_generated_actions(
    world: ReadinessWorld,
    timeline: ReadinessTimeline,
    *,
    old_delivery: str,
    current_delivery: str,
    actions: list[str],
) -> ReadinessTimeline:
    for action in actions:
        if action == "step":
            if timeline.pending():
                timeline.step()
        elif action == "restart":
            timeline.crash("generated_authority_lifecycle_cut")
            timeline = world.restart()
        elif action == "redeliver-old":
            if not timeline.pending():
                timeline.deliver_webhook(old_delivery)
        elif action == "redeliver-current":
            if not timeline.pending():
                timeline.deliver_webhook(current_delivery)
        else:
            raise AssertionError(f"unknown generated readiness action {action!r}")
    return timeline


def _drain(timeline: ReadinessTimeline) -> None:
    while timeline.pending():
        timeline.step()


@settings(
    max_examples=6,
    deadline=None,
    derandomize=True,
    suppress_health_check=(HealthCheck.too_slow,),
)
@example(seed=0, path="active", before=[], after=[])
@example(seed=0, path="draft_resume", before=[], after=[])
@example(seed=0, path="closed", before=[], after=[])
@given(
    seed=st.integers(min_value=0, max_value=2**53 - 1),
    path=st.sampled_from(("active", "draft_resume", "closed")),
    before=st.lists(st.sampled_from(_GENERATED_ACTIONS), max_size=1),
    after=st.lists(st.sampled_from(_GENERATED_ACTIONS), max_size=1),
)
def test_generated_authority_lifecycle_schedules_replay_exactly(
    seed: int,
    path: str,
    before: list[str],
    after: list[str],
) -> None:
    event(f"authority_path={path}")
    event(f"authority_before={','.join(before) or 'none'}")
    event(f"authority_after={','.join(after) or 'none'}")
    directory = TemporaryDirectory(prefix="hamsterdan-readiness-authority-")
    root = Path(directory.name)
    world = ReadinessWorld(root / "live", seed=seed)
    timeline = world.timeline()
    scenario_id = f"readiness-authority-lifecycle-{path}-v2"
    failure_path = Path(".hypothesis/readiness-artifacts/readiness-authority-lifecycle-v4.json")
    closed = False
    try:
        old_delivery = _start_clean_green(timeline, response_lost=False)
        _drain(timeline)
        initial = cast(dict[str, JsonValue], timeline.observe().value)
        assert cast(dict[str, JsonValue], initial["expected"])["ready"] is True

        initial_lifecycle = "draft" if path == "draft_resume" else path
        timeline.set_pull_request(
            head=_AUTHORITY_HEAD,
            base=BASE,
            policy=READINESS_POLICY_DIGEST,
            lifecycle=initial_lifecycle,
            strict_base=True,
            base_current=True,
            mergeable=True,
        )
        timeline.set_ci(
            head=_AUTHORITY_HEAD,
            required_checks=("build",),
            checks={"build": "success"},
        )
        timeline.set_review(head=_AUTHORITY_HEAD, status="clear")
        current_delivery = timeline.emit_webhook(
            "pull_request",
            action="closed" if path == "closed" else "synchronize",
        )
        timeline.deliver_webhook(current_delivery)
        timeline = _run_generated_actions(
            world,
            timeline,
            old_delivery=old_delivery,
            current_delivery=current_delivery,
            actions=before,
        )
        _drain(timeline)

        current = cast(dict[str, JsonValue], timeline.observe().value)
        expected = cast(dict[str, JsonValue], current["expected"])
        actual = cast(dict[str, JsonValue], current["actual"])
        if path == "active":
            assert expected["disposition"] == "ready"
            assert actual["readiness_published"] is True
        elif path == "closed":
            assert expected["disposition"] == "terminal"
            assert actual["readiness_published"] is False
        else:
            assert expected["disposition"] == "human_wait"
            assert expected["blockers"] == ["pull_request_draft"]
            assert actual["readiness_published"] is False
            timeline.set_pull_request(
                head=_AUTHORITY_HEAD,
                base=BASE,
                policy=READINESS_POLICY_DIGEST,
                lifecycle="active",
                strict_base=True,
                base_current=True,
                mergeable=True,
            )
            current_delivery = timeline.emit_webhook("pull_request", action="ready_for_review")
            timeline.deliver_webhook(current_delivery)

        timeline = _run_generated_actions(
            world,
            timeline,
            old_delivery=old_delivery,
            current_delivery=current_delivery,
            actions=after,
        )
        final_observation = timeline.converge()
        final = cast(dict[str, JsonValue], final_observation.value)
        final_expected = cast(dict[str, JsonValue], final["expected"])
        final_host = cast(dict[str, JsonValue], final["host"])
        final_actual = cast(dict[str, JsonValue], final["actual"])
        provider = cast(dict[str, JsonValue], final["provider"])
        effects = cast(list[dict[str, JsonValue]], provider["effects"])
        facts = cast(dict[str, JsonValue], final["facts"])

        assert final_expected["violations"] == []
        assert final_expected["generation"] == (3 if path == "draft_resume" else 2)
        assert all(
            effect["head"] == cast(dict[str, JsonValue], effect["provider_authority_at_acceptance"])["head"]
            for effect in effects
        )
        assert len({cast(str, effect["operation"]) for effect in effects}) == len(effects)
        assert len(cast(list[JsonValue], facts["admitted_observations"])) == (3 if path == "draft_resume" else 2)
        if path == "closed":
            assert final_expected["disposition"] == "terminal"
            assert final_actual["readiness_published"] is False
            assert cast(dict[str, JsonValue], final_host["snapshot"])["phase"] == "terminal"
            assert cast(dict[str, JsonValue], provider["accepted_by_kind"])["readiness"] == 1
        else:
            assert final_expected["disposition"] == "ready"
            assert final_actual["readiness_published"] is True
            assert cast(dict[str, JsonValue], final_host["snapshot"])["head"] == _AUTHORITY_HEAD
            assert cast(dict[str, JsonValue], provider["accepted_by_kind"])["readiness"] == 2

        artifact = world.artifact(scenario_id)
        assert artifact.version == 4
        assert artifact.origin is not None
        assert artifact.origin.seed == seed
        operations = len(artifact.operations)
        world.close()
        closed = True

        replayed = replay_readiness(artifact, root / "replay")
        assert replayed.outcome == "pass"
        assert replayed.disposition == Disposition.CONVERGED.value
        assert replayed.failure is None
        assert replayed.operations == operations
    except (BudgetExhausted, InvariantViolation) as error:
        _retain_failure_artifact(
            world,
            scenario_id=scenario_id,
            failure_path=failure_path,
            replay_root=root / "failure-replay",
            primary=error,
        )
        raise
    finally:
        primary = sys.exception()
        try:
            if not closed:
                world.close()
        except BaseException as close_error:
            if primary is not None:
                primary.add_note(
                    f"secondary readiness campaign close failure: {type(close_error).__name__}: {close_error}"
                )
            else:
                primary = close_error
                raise
        finally:
            try:
                directory.cleanup()
            except BaseException as cleanup_error:
                if primary is not None:
                    primary.add_note(
                        "secondary readiness campaign directory cleanup failure: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
                else:
                    raise


def test_generated_delivery_recovery_schedules_replay_exactly() -> None:
    run_state_machine_as_test(
        _DeliveryRecoveryMachine,
        settings=settings(
            max_examples=12,
            stateful_step_count=5,
            deadline=None,
            derandomize=True,
            suppress_health_check=(HealthCheck.too_slow,),
        ),
    )


def test_shrunk_checker_failure_retains_an_exact_replayable_artifact(tmp_path: Path) -> None:
    retained = tmp_path / "retained-counterexample.json"

    with pytest.raises(InvariantViolation, match="independent-model"):
        run_state_machine_as_test(
            lambda: _DeliveryRecoveryMachine(force_failure=True, failure_path=retained),
            settings=settings(
                max_examples=2,
                stateful_step_count=2,
                deadline=None,
                derandomize=True,
                report_multiple_bugs=False,
                suppress_health_check=(HealthCheck.too_slow,),
            ),
        )

    artifact = load_artifact(retained)
    assert artifact.version == 4
    assert artifact.expected.disposition == Disposition.INVARIANT_FAILURE.value
    replayed = replay_readiness(artifact, tmp_path / "retained-replay")
    assert replayed.outcome == "pass"
    assert replayed.disposition == Disposition.INVARIANT_FAILURE.value
    assert replayed.failure is not None
    assert replayed.failure.kind == "invariant_failure"
