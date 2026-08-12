"""AX6 focused tests — predicate DSL, CEL compilation, guard routing, parking."""

from dataclasses import asdict, dataclass

import pytest
from ax6_compiler import case_filters, compile_workflow
from ax6_predicates import PredicateTypeError, on, trace
from ax6_workflow_ast import WorkflowShapeError, branch, sequence, step, when
from petrus.engine import Engine
from petrus.impetus.binding import passthrough
from petrus.impetus.dsl import NetSpec, arc, petri_handler
from petrus.impetus.history import ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Cel, FilterEvaluationWarning, Marking, NetPath, Token
from petrus.motus.activity import DataclassPayloadConverter
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch


@dataclass(frozen=True)
class Applicant:
    age: int
    country: str


@dataclass(frozen=True)
class Application:
    score: int
    applicant: Applicant
    note: str | None = None


@dataclass(frozen=True)
class Decision:
    route: str


@dataclass(frozen=True)
class Receipt:
    summary: str


@motus_activity(converter=DataclassPayloadConverter())
def fast_track(application: Application) -> Decision:
    return Decision(route=f"fast:{application.score}")


@motus_activity(converter=DataclassPayloadConverter())
def senior_review(application: Application) -> Decision:
    return Decision(route=f"senior:{application.score}")


@motus_activity(converter=DataclassPayloadConverter())
def manual_review(application: Application) -> Decision:
    return Decision(route=f"manual:{application.score}")


@motus_activity(converter=DataclassPayloadConverter())
def archive(decision: Decision) -> Receipt:
    return Receipt(summary=decision.route)


DEFINITIONS = (fast_track, senior_review, manual_review, archive)

app = on(Application)
FAST = (app.score > 700) & (app.applicant.age >= 18)


def application_workflow():
    """Every branch consumes the same Application — routing is pure value.

    The two guards deliberately *overlap* (score=800 matches both raw
    predicates): declaration order is the semantics under test.
    """
    return sequence(
        branch(
            when(FAST, then=step(fast_track)),
            when(app.score > 500, then=step(senior_review)),
            otherwise=step(manual_review),
        ),
        step(archive),
    )


def drive_bounded(subject: Engine, limit: int = 100) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def make_engine(compiled, application: Application, instance: str = "ax6", history=None) -> Engine:
    return Engine.create(
        compiled.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=InlineDispatch({d.declaration.name: d for d in DEFINITIONS}),
        marking=Marking({compiled.entry: (Token("Application", asdict(application)),)}),
        handlers=dict(compiled.handlers),
        activities=compiled.activities,
    )


def applicant(score: int, age: int = 30) -> Application:
    return Application(score=score, applicant=Applicant(age=age, country="US"))


def requested(subject: Engine) -> list[str]:
    return [r.activity for r in subject.records if isinstance(r, ActivityRequested)]


class TestPredicateRendering:
    def test_comparison_elides_the_root_variable(self) -> None:
        # Petrus filters see token data fields as bare variables.
        assert (app.score > 700).cel() == "(score > 700)"

    def test_nested_field_path(self) -> None:
        assert (app.applicant.age >= 18).cel() == "(applicant.age >= 18)"

    def test_string_constants_render_as_cel_strings(self) -> None:
        assert (app.applicant.country == "US").cel() == '(applicant.country == "US")'

    def test_conjunction_disjunction_negation(self) -> None:
        assert FAST.cel() == "((score > 700) && (applicant.age >= 18))"
        either = (app.score > 700) | (app.score < 100)
        assert either.cel() == "((score > 700) || (score < 100))"
        assert (~(app.score > 700)).cel() == "!(score > 700)"

    def test_membership(self) -> None:
        member = app.applicant.country.one_of("US", "BR")
        assert member.cel() == '(applicant.country in ["US", "BR"])'

    def test_null_checks(self) -> None:
        assert app.note.is_not_null().cel() == "(note != null)"
        assert app.note.is_null().cel() == "(note == null)"

    def test_structural_equality_is_deterministic(self) -> None:
        again = (app.score > 700) & (app.applicant.age >= 18)
        assert again == FAST
        assert again.cel() == FAST.cel()


class TestPredicateValidation:
    def test_unknown_field_lists_the_available_ones(self) -> None:
        with pytest.raises(PredicateTypeError, match=r"no field 'points'.*applicant.*note.*score"):
            app.points  # noqa: B018

    def test_scalar_fields_have_no_nested_fields(self) -> None:
        with pytest.raises(PredicateTypeError, match="'score' .* has no nested fields"):
            app.score.digits  # noqa: B018

    def test_constant_type_mismatch(self) -> None:
        with pytest.raises(PredicateTypeError, match="'score' is int, but .* '700' is str"):
            app.score > "700"  # noqa: B015

    def test_ordering_on_a_dataclass_field(self) -> None:
        with pytest.raises(PredicateTypeError, match="does not support ordering"):
            app.applicant > 5  # noqa: B015

    def test_field_to_field_comparison_is_refused(self) -> None:
        with pytest.raises(PredicateTypeError, match="field-to-field"):
            app.score > app.applicant.age  # noqa: B015

    def test_python_and_keyword_fails_with_a_remedy(self) -> None:
        with pytest.raises(PredicateTypeError, match="use `&`, `\\|`, `~`"):
            _ = (app.score > 700) and (app.score < 900)

    def test_bare_field_is_not_a_predicate(self) -> None:
        with pytest.raises(PredicateTypeError, match="not a predicate by itself"):
            bool(app.score)

    def test_optional_field_requires_a_null_guard(self) -> None:
        with pytest.raises(PredicateTypeError, match="'note' is optional; guard it first"):
            when(app.note == "vip", then=step(manual_review))

    def test_null_guard_secures_the_conjunction(self) -> None:
        guarded = when(app.note.is_not_null() & (app.note == "vip"), then=step(manual_review))
        assert guarded.predicate.cel() == '((note != null) && (note == "vip"))'


class TestLambdaTracing:
    def test_traced_lambda_builds_the_same_predicate(self) -> None:
        traced = trace(Application, lambda a: (a.score > 700) & (a.applicant.age >= 18))
        assert traced == FAST

    def test_boolean_keywords_cannot_be_traced(self) -> None:
        with pytest.raises(PredicateTypeError, match="`and`/`or`/`not`"):
            trace(Application, lambda a: a.score > 700 and a.applicant.age >= 18)

    def test_lambda_must_return_a_predicate(self) -> None:
        with pytest.raises(PredicateTypeError, match="must return a predicate, got bool"):
            trace(Application, lambda a: True)


class TestBranchShape:
    def test_branch_requires_at_least_one_case(self) -> None:
        with pytest.raises(WorkflowShapeError, match="at least one when"):
            branch(otherwise=step(manual_review))

    def test_predicates_must_share_one_subject_type(self) -> None:
        decision = on(Decision)
        with pytest.raises(WorkflowShapeError, match="exactly one subject type"):
            branch(
                when(app.score > 700, then=step(fast_track)),
                when(decision.route == "fast", then=step(manual_review)),
                otherwise=step(manual_review),
            )

    def test_duplicate_predicate_is_unreachable_and_refused(self) -> None:
        with pytest.raises(WorkflowShapeError, match="repeats an earlier predicate"):
            branch(
                when(app.score > 700, then=step(fast_track)),
                when(app.score > 700, then=step(senior_review)),
                otherwise=step(manual_review),
            )

    def test_when_requires_an_expression_object(self) -> None:
        with pytest.raises(WorkflowShapeError, match="needs a predicate expression object"):
            when(True, then=step(fast_track))


class TestLoweredShape:
    def test_ordered_exclusive_filters(self) -> None:
        cases, otherwise = case_filters(application_workflow().steps[0])
        assert cases == (
            "((score > 700) && (applicant.age >= 18))",
            "(score > 500) && !((score > 700) && (applicant.age >= 18))",
        )
        assert otherwise == "!((score > 700) && (applicant.age >= 18)) && !(score > 500)"

    def test_routers_places_and_merge_are_visible(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        net = compiled.built.net
        assert sorted(str(t) for t in net.transitions) == [
            "w.0.case_0",
            "w.0.case_1",
            "w.0.merge_0",
            "w.0.merge_1",
            "w.0.merge_2",
            "w.0.otherwise",
            "w.0_0_0.fast_track",
            "w.0_1_0.senior_review",
            "w.0_2_0.manual_review",
            "w.1.archive",
        ]
        assert sorted(str(p) for p in net.places) == [
            "w.0.out",
            "w.0.when_0",
            "w.0.when_1",
            "w.0.when_otherwise",
            "w.0_0_0.out",
            "w.0_1_0.out",
            "w.0_2_0.out",
            "w.1.out",
            "w.entry",
        ]

    def test_source_map_points_back_to_authoring_lines(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        first_case = compiled.source_map["/0/0"]
        assert first_case.node == "when ((score > 700) && (applicant.age >= 18))"
        assert first_case.transition == "w.0.case_0"
        assert first_case.origin and first_case.origin.endswith("test_ax6_guards.py" + f":{when_line()}")
        assert compiled.filters["w.0.otherwise"].startswith("!((score > 700)")

    def test_recompilation_is_deterministic(self) -> None:
        first = compile_workflow(application_workflow(), DEFINITIONS)
        second = compile_workflow(application_workflow(), DEFINITIONS)
        assert dict(first.filters) == dict(second.filters)
        assert sorted(map(str, first.built.net.transitions)) == sorted(map(str, second.built.net.transitions))


def when_line() -> int:
    """Line number of the first when() in application_workflow, kept honest."""
    import inspect

    source, start = inspect.getsourcelines(application_workflow)
    [offset] = [i for i, line in enumerate(source) if "when(FAST" in line]
    return start + offset


class TestExecution:
    def route(self, application: Application) -> tuple[list[str], list[dict]]:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        subject = make_engine(compiled, application)
        drive_bounded(subject)
        [exit_place] = compiled.exits
        return requested(subject), [t.data for t in subject.marking.place(exit_place)]

    def test_high_score_adult_goes_fast(self) -> None:
        names, final = self.route(applicant(score=800, age=30))
        assert final == [{"summary": "fast:800"}]
        assert "fast_track" in names and "senior_review" not in names and "manual_review" not in names

    def test_overlapping_guards_resolve_by_declaration_order(self) -> None:
        # score=800 matches both raw predicates; age=16 falsifies case 0,
        # so the ordered-exclusive filter routes it to case 1 — deterministically.
        names, final = self.route(applicant(score=800, age=16))
        assert final == [{"summary": "senior:800"}]
        assert "fast_track" not in names

    def test_mid_score_goes_senior(self) -> None:
        _, final = self.route(applicant(score=600))
        assert final == [{"summary": "senior:600"}]

    def test_low_score_goes_manual(self) -> None:
        names, final = self.route(applicant(score=300))
        assert final == [{"summary": "manual:300"}]
        assert names == ["manual_review", "archive"]

    def test_replay_over_recompiled_net_reaches_same_state(self) -> None:
        history = InMemoryHistoryStore()
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        subject = make_engine(compiled, applicant(score=800), instance="ax6-replay", history=history)
        drive_bounded(subject)

        recompiled = compile_workflow(application_workflow(), DEFINITIONS)
        resumed = Engine.load(
            recompiled.built.net,
            "ax6-replay",
            history=history,
            dispatch=InlineDispatch({d.declaration.name: d for d in DEFINITIONS}),
            handlers=dict(recompiled.handlers),
            activities=recompiled.activities,
        )
        [exit_place] = recompiled.exits
        assert [t.data for t in resumed.marking.place(exit_place)] == [{"summary": "fast:800"}]

    def test_raising_filter_parks_the_token_with_a_warning(self) -> None:
        """A forged token with score=null makes every filter raise: the
        token is admitted nowhere and *parks* in the entry place — visible
        as FilterEvaluationWarning, not silently dropped. This is exactly
        the failure the predicate layer's null-safety validation exists
        to keep unrepresentable from typed authoring."""
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        forged = {"score": None, "applicant": {"age": 30, "country": "US"}, "note": None}
        subject = Engine.create(
            compiled.built.net,
            "ax6-forged",
            history=InMemoryHistoryStore(),
            dispatch=InlineDispatch({d.declaration.name: d for d in DEFINITIONS}),
            marking=Marking({compiled.entry: (Token("Application", forged),)}),
            handlers=dict(compiled.handlers),
            activities=compiled.activities,
        )
        with pytest.warns(FilterEvaluationWarning):
            drive_bounded(subject)
        assert [t.data for t in subject.marking.place(NetPath("w.entry"))] == [forged]
        assert requested(subject) == []


class TestNativeRuntimeRouting:
    """What the frozen runtime does by itself with filtered input arcs."""

    def racing_consumers(self, low: str, high: str):
        spec = NetSpec("native")
        scope = spec.s["n"]
        pool = scope.p.pool("Application")
        to_a = scope.t.to_a(handler=petri_handler(passthrough))
        to_b = scope.t.to_b(handler=petri_handler(passthrough))
        pool >> arc(color="Application", filter=Cel(low)) >> to_a
        pool >> arc(color="Application", filter=Cel(high)) >> to_b
        out_a = scope.p.out_a("Application")
        out_b = scope.p.out_b("Application")
        to_a >> out_a
        to_b >> out_b
        return spec.build(), pool

    def pure_engine(self, built, pool, score: int) -> Engine:
        return Engine.create(
            built.net,
            "ax6-native",
            history=InMemoryHistoryStore(),
            dispatch=InlineDispatch({}),
            marking=Marking({abs(pool): (Token("Application", {"score": score}),)}),
            handlers=dict(built.handlers),
        )

    def test_overlapping_filters_are_competition_not_duplication(self) -> None:
        """Both filters admit the token: the transitions *race* and exactly
        one consumes it. Legal Petri nondeterminism — which is why the
        branch combinator compiles ordered-exclusive filters instead of
        leaving the choice to the scheduler."""
        built, pool = self.racing_consumers("score > 0", "score < 100")
        subject = self.pure_engine(built, pool, score=50)
        drive_bounded(subject)
        landed = [t.color for place in ("n.out_a", "n.out_b") for t in subject.marking.place(NetPath(place))]
        assert landed == ["Application"]
        assert not tuple(subject.marking.place(NetPath("n.pool")))

    def test_token_matching_no_filter_parks_quietly(self) -> None:
        """Filters that evaluate cleanly to false park the token with no
        warning at all — the strongest argument for a mandatory otherwise."""
        built, pool = self.racing_consumers("score > 100", "score < 0")
        subject = self.pure_engine(built, pool, score=50)
        drive_bounded(subject)
        assert [t.data for t in subject.marking.place(NetPath("n.pool"))] == [{"score": 50}]
