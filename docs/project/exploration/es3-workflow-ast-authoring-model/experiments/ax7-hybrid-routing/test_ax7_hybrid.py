"""AX7 focused tests — hybrid arcs, narrowed guards, per-variant totality."""

import warnings
from dataclasses import asdict, dataclass

import pytest
from ax7_compiler import VariantPayloadConverter, compile_workflow, hybrid_filters
from ax7_predicates import PredicateTypeError, on
from ax7_workflow_ast import WorkflowShapeError, case, hybrid, sequence, step
from petrus.engine import Engine
from petrus.impetus.history import ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import FilterEvaluationWarning, Marking, NetPath, Token
from petrus.motus.activity import DataclassPayloadConverter
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch


@dataclass(frozen=True)
class Application:
    score: int


@dataclass(frozen=True)
class Approved:
    risk: int
    score: int


@dataclass(frozen=True)
class Rejected:
    reason: str


@dataclass(frozen=True)
class Decision:
    route: str


@dataclass(frozen=True)
class Receipt:
    summary: str


@motus_activity(converter=VariantPayloadConverter())
def evaluate(application: Application) -> Approved | Rejected:
    if application.score > 700:
        return Approved(risk=max(0, 900 - application.score), score=application.score)
    return Rejected(reason="low score")


@motus_activity(converter=DataclassPayloadConverter())
def auto_processing(approved: Approved) -> Decision:
    return Decision(route=f"auto:{approved.risk}")


@motus_activity(converter=DataclassPayloadConverter())
def senior_approval(approved: Approved) -> Decision:
    return Decision(route=f"senior:{approved.risk}")


@motus_activity(converter=DataclassPayloadConverter())
def manual_processing(rejected: Rejected) -> Decision:
    return Decision(route=f"manual:{rejected.reason}")


@motus_activity(converter=DataclassPayloadConverter())
def archive(decision: Decision) -> Receipt:
    return Receipt(summary=decision.route)


DEFINITIONS = (evaluate, auto_processing, senior_approval, manual_processing, archive)

approved = on(Approved)


def application_workflow():
    return sequence(
        hybrid(
            evaluate,
            case(Approved, when=approved.risk < 20, then=step(auto_processing)),
            case(Approved, then=step(senior_approval)),
            case(Rejected, then=step(manual_processing)),
        ),
        step(archive),
    )


def drive_bounded(subject: Engine, limit: int = 100) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def make_engine(compiled, score: int, instance: str = "ax7", history=None) -> Engine:
    return Engine.create(
        compiled.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=InlineDispatch({d.declaration.name: d for d in DEFINITIONS}),
        marking=Marking({compiled.entry: (Token("Application", asdict(Application(score=score))),)}),
        handlers=dict(compiled.handlers),
        activities=compiled.activities,
    )


def requested(subject: Engine) -> list[str]:
    return [r.activity for r in subject.records if isinstance(r, ActivityRequested)]


class TestShapeValidation:
    def test_guard_must_read_the_case_variant(self) -> None:
        rejected = on(Rejected)
        with pytest.raises(WorkflowShapeError, match="case Approved guard must read Approved .* \\['Rejected'\\]"):
            case(Approved, when=rejected.reason == "low score", then=step(auto_processing))

    def test_unknown_field_on_the_narrowed_type_fails_at_the_proxy(self) -> None:
        # The AX7 requirement: a guard for risk_score fails early when the
        # selected type cannot have that field.
        with pytest.raises(PredicateTypeError, match="Approved has no field 'risk_score'"):
            approved.risk_score  # noqa: B018

    def test_every_variant_needs_a_case(self) -> None:
        with pytest.raises(WorkflowShapeError, match="covers no case for variant Rejected"):
            hybrid(evaluate, case(Approved, then=step(auto_processing)))

    def test_a_variant_with_only_guarded_cases_is_refused(self) -> None:
        with pytest.raises(WorkflowShapeError, match="variant Approved has only guarded"):
            hybrid(
                evaluate,
                case(Approved, when=approved.risk < 20, then=step(auto_processing)),
                case(Rejected, then=step(manual_processing)),
            )

    def test_a_case_after_the_unguarded_default_is_unreachable(self) -> None:
        with pytest.raises(WorkflowShapeError, match="unguarded case and it must come last"):
            hybrid(
                evaluate,
                case(Approved, then=step(senior_approval)),
                case(Approved, when=approved.risk < 20, then=step(auto_processing)),
                case(Rejected, then=step(manual_processing)),
            )

    def test_duplicate_guard_within_a_variant_is_refused(self) -> None:
        with pytest.raises(WorkflowShapeError, match="repeats predicate"):
            hybrid(
                evaluate,
                case(Approved, when=approved.risk < 20, then=step(auto_processing)),
                case(Approved, when=approved.risk < 20, then=step(senior_approval)),
                case(Approved, then=step(senior_approval)),
                case(Rejected, then=step(manual_processing)),
            )

    def test_hybrid_refuses_single_result_activities(self) -> None:
        with pytest.raises(WorkflowShapeError, match="use step\\(\\) or branch\\(\\)"):
            hybrid(auto_processing, case(Decision, then=step(archive)))


class TestLoweredShape:
    def test_per_case_filters_are_exclusive_within_a_variant_only(self) -> None:
        expressions = hybrid_filters(application_workflow().steps[0])
        assert expressions == (
            "(risk < 20)",  # Approved, guarded
            "!(risk < 20)",  # Approved default: negations only
            None,  # Rejected: single case, no filter at all
        )

    def test_arcs_carry_both_color_and_filter(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        net = compiled.built.net
        pool = NetPath("w.0.pool")
        assert net.places[pool].color is None  # untyped pool, colored tokens
        hybrid_arcs = sorted(
            (str(a.target), a.color, a.filter.expression if a.filter else None) for a in net.arcs if a.source == pool
        )
        assert hybrid_arcs == [
            ("w.0.case_0", "Approved", "(risk < 20)"),
            ("w.0.case_1", "Approved", "!(risk < 20)"),
            ("w.0.case_2", "Rejected", None),
        ]

    def test_source_map_names_the_hybrid_cases(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        assert compiled.source_map["/0/0"].node == "case Approved when (risk < 20)"
        assert compiled.source_map["/0/1"].node == "case Approved"
        assert compiled.source_map["/0/2"].node == "case Rejected"
        assert compiled.generated_by["w.0_2_0.manual_processing"] == "/0/2/0"


class TestExecution:
    def route(self, score: int) -> tuple[list[str], list[dict]]:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        subject = make_engine(compiled, score=score)
        drive_bounded(subject)
        [exit_place] = compiled.exits
        return requested(subject), [t.data for t in subject.marking.place(exit_place)]

    def test_low_risk_approved_goes_auto(self) -> None:
        names, final = self.route(score=890)  # risk 10
        assert final == [{"summary": "auto:10"}]
        assert "auto_processing" in names
        assert "senior_approval" not in names and "manual_processing" not in names

    def test_high_risk_approved_goes_senior(self) -> None:
        names, final = self.route(score=750)  # risk 150
        assert final == [{"summary": "senior:150"}]
        assert "auto_processing" not in names

    def test_rejected_goes_manual(self) -> None:
        names, final = self.route(score=300)
        assert final == [{"summary": "manual:low score"}]
        assert names == ["evaluate", "manual_processing", "archive"]

    def test_color_gates_before_the_filter_ever_runs(self) -> None:
        """A Rejected token flows past two Approved arcs whose filters read
        `risk` — a field Rejected lacks. No FilterEvaluationWarning: the
        frozen runtime short-circuits on the color, so narrowed guards are
        sound by construction, not by luck."""
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        subject = make_engine(compiled, score=300)
        with warnings.catch_warnings():
            warnings.simplefilter("error", FilterEvaluationWarning)
            drive_bounded(subject)
        [exit_place] = compiled.exits
        assert [t.data for t in subject.marking.place(exit_place)] == [{"summary": "manual:low score"}]

    def test_replay_over_recompiled_net_reaches_same_state(self) -> None:
        history = InMemoryHistoryStore()
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        subject = make_engine(compiled, score=890, instance="ax7-replay", history=history)
        drive_bounded(subject)

        recompiled = compile_workflow(application_workflow(), DEFINITIONS)
        resumed = Engine.load(
            recompiled.built.net,
            "ax7-replay",
            history=history,
            dispatch=InlineDispatch({d.declaration.name: d for d in DEFINITIONS}),
            handlers=dict(recompiled.handlers),
            activities=recompiled.activities,
        )
        [exit_place] = recompiled.exits
        assert [t.data for t in resumed.marking.place(exit_place)] == [{"summary": "auto:10"}]
