"""AX5 focused tests — switch shape, exhaustiveness, dispatch, native routing."""

from dataclasses import asdict, dataclass

import pytest
from ax5_compiler import (
    VariantPayloadConverter,
    VariantRoutingActivityHandler,
    compile_workflow,
)
from ax5_workflow_ast import WorkflowShapeError, case, sequence, step, switch
from petrus.engine import Engine
from petrus.impetus.binding import passthrough
from petrus.impetus.dsl import NetSpec, arc, petri_handler
from petrus.impetus.history import ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import DataclassPayloadConverter
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch, InMemoryDispatch


@dataclass(frozen=True)
class Application:
    score: int


@dataclass(frozen=True)
class Approved:
    score: int


@dataclass(frozen=True)
class Rejected:
    reason: str


@dataclass(frozen=True)
class Outcome:
    summary: str


@dataclass(frozen=True)
class Receipt:
    summary: str


@motus_activity(converter=VariantPayloadConverter())
def evaluate(application: Application) -> Approved | Rejected:
    if application.score > 700:
        return Approved(score=application.score)
    return Rejected(reason="low score")


@motus_activity(converter=DataclassPayloadConverter())
def provision(approved: Approved) -> Outcome:
    return Outcome(summary=f"provisioned:{approved.score}")


@motus_activity(converter=DataclassPayloadConverter())
def notify(rejected: Rejected) -> Outcome:
    return Outcome(summary=f"notified:{rejected.reason}")


@motus_activity(converter=DataclassPayloadConverter())
def archive(outcome: Outcome) -> Receipt:
    return Receipt(summary=outcome.summary)


DEFINITIONS = (evaluate, provision, notify, archive)


def application_workflow():
    return sequence(
        switch(
            evaluate,
            case(Approved, then=step(provision)),
            case(Rejected, then=step(notify)),
        ),
        step(archive),
    )


def drive_bounded(subject: Engine, limit: int = 100) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def make_engine(compiled, dispatch, score: int, instance: str = "ax5", history=None):
    return Engine.create(
        compiled.built.net,
        instance,
        history=history if history is not None else InMemoryHistoryStore(),
        dispatch=dispatch,
        marking=Marking({compiled.entry: (Token("Application", asdict(Application(score=score))),)}),
        handlers=dict(compiled.handlers),
        activities=compiled.activities,
    )


def inline() -> InlineDispatch:
    return InlineDispatch({d.declaration.name: d for d in DEFINITIONS})


def requested(subject: Engine) -> list[str]:
    return [r.activity for r in subject.records if isinstance(r, ActivityRequested)]


class TestLoweredShape:
    def test_one_typed_place_and_arc_per_variant(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        net = compiled.built.net
        assert sorted(str(t) for t in net.transitions) == [
            "w.0.evaluate",
            "w.0.merge_0",
            "w.0.merge_1",
            "w.0_0.provision",
            "w.0_1.notify",
            "w.1.archive",
        ]
        assert sorted(str(p) for p in net.places) == [
            "w.0.on_approved",
            "w.0.on_rejected",
            "w.0.out",
            "w.0_0.out",
            "w.0_1.out",
            "w.1.out",
            "w.entry",
        ]
        # The branch is visible as typed arcs: one per union member.
        outputs = sorted((str(a.target), a.color) for a in net.outputs(NetPath("w.0.evaluate")))
        assert outputs == [("w.0.on_approved", "Approved"), ("w.0.on_rejected", "Rejected")]
        # The XOR merge is explicit: two passthroughs into one shared place.
        merged = sorted(
            (str(a.source), str(a.target)) for t in ("w.0.merge_0", "w.0.merge_1") for a in net.outputs(NetPath(t))
        )
        assert merged == [("w.0.merge_0", "w.0.out"), ("w.0.merge_1", "w.0.out")]

    def test_source_map_covers_switch_and_cases(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        assert compiled.source_map["/0"].node == "switch 'evaluate'"
        assert compiled.source_map["/0"].transition == "w.0.evaluate"
        assert compiled.source_map["/0"].exit_places == ("w.0.out",)
        assert compiled.generated_by["w.0.merge_0"] == "/0/0"
        assert compiled.generated_by["w.0_1.notify"] == "/0/1"


class TestShapeErrors:
    def test_missing_case_is_unrepresentable(self) -> None:
        with pytest.raises(WorkflowShapeError, match=r"missing \['Rejected'\]"):
            switch(evaluate, case(Approved, then=step(provision)))

    def test_unknown_case_is_unrepresentable(self) -> None:
        with pytest.raises(WorkflowShapeError, match=r"unknown \['Outcome'\]"):
            switch(
                evaluate,
                case(Approved, then=step(provision)),
                case(Rejected, then=step(notify)),
                case(Outcome, then=step(archive)),
            )

    def test_switch_refuses_single_result_activities(self) -> None:
        with pytest.raises(WorkflowShapeError, match="use step\\(\\) for single-result"):
            switch(provision, case(Outcome, then=step(archive)))

    def test_step_still_refuses_unions(self) -> None:
        with pytest.raises(WorkflowShapeError, match="unions mean branching"):
            step(evaluate)


class TestConverter:
    def test_variant_is_stamped_durably(self) -> None:
        encoded = VariantPayloadConverter().encode(Approved(score=800), Approved | Rejected)
        assert encoded == {"$variant": "Approved", "score": 800}

    def test_subclass_is_refused_at_the_worker_boundary(self) -> None:
        @dataclass(frozen=True)
        class PremiumApproved(Approved):
            tier: str = "gold"

        with pytest.raises(ValueError, match="got PremiumApproved — subclasses"):
            VariantPayloadConverter().encode(PremiumApproved(score=990), Approved | Rejected)

    def test_unlisted_type_is_refused(self) -> None:
        with pytest.raises(ValueError, match="got Outcome"):
            VariantPayloadConverter().encode(Outcome(summary="x"), Approved | Rejected)


class TestExecution:
    def test_approved_path_runs_provision_only(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        subject = make_engine(compiled, inline(), score=800)
        drive_bounded(subject)

        [exit_place] = compiled.exits
        final = [t.data for t in subject.marking.place(exit_place)]
        assert final == [{"summary": "provisioned:800"}]
        names = requested(subject)
        assert "provision" in names and "notify" not in names
        assert not tuple(subject.marking.place(NetPath("w.0.on_rejected")))

    def test_rejected_path_runs_notify_only(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        subject = make_engine(compiled, inline(), score=300)
        drive_bounded(subject)

        [exit_place] = compiled.exits
        final = [t.data for t in subject.marking.place(exit_place)]
        assert final == [{"summary": "notified:low score"}]
        names = requested(subject)
        assert "notify" in names and "provision" not in names

    def test_forged_unknown_variant_fails_loud_not_dropped(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        dispatch = InMemoryDispatch()
        subject = make_engine(compiled, dispatch, score=800)
        drive_bounded(subject)

        [(occurrence, _)] = list(dispatch.pending.items())
        dispatch.complete(occurrence, {"$variant": "Weird", "score": 1})
        with pytest.raises(ValueError, match="'Weird' is not one of .* refusing"):
            drive_bounded(subject)

    def test_result_without_discriminator_fails_loud(self) -> None:
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        dispatch = InMemoryDispatch()
        subject = make_engine(compiled, dispatch, score=800)
        drive_bounded(subject)

        [(occurrence, _)] = list(dispatch.pending.items())
        dispatch.complete(occurrence, {"score": 800})
        with pytest.raises(ValueError, match="lacks\\s+the '\\$variant' discriminator"):
            drive_bounded(subject)

    def test_replay_over_recompiled_net_reaches_same_state(self) -> None:
        history = InMemoryHistoryStore()
        compiled = compile_workflow(application_workflow(), DEFINITIONS)
        subject = make_engine(compiled, inline(), score=800, instance="ax5-replay", history=history)
        drive_bounded(subject)

        recompiled = compile_workflow(application_workflow(), DEFINITIONS)
        resumed = Engine.load(
            recompiled.built.net,
            "ax5-replay",
            history=history,
            dispatch=inline(),
            handlers=dict(recompiled.handlers),
            activities=recompiled.activities,
        )
        [exit_place] = recompiled.exits
        assert [t.data for t in resumed.marking.place(exit_place)] == [{"summary": "provisioned:800"}]


class TestNativeRuntimeRouting:
    """What the frozen runtime does by itself with typed arcs — honesty tests."""

    def pure_engine(self, built, seeds: dict[NetPath, tuple[Token, ...]]) -> Engine:
        return Engine.create(
            built.net,
            "ax5-native",
            history=InMemoryHistoryStore(),
            dispatch=InlineDispatch({}),
            marking=Marking(seeds),
            handlers=dict(built.handlers),
        )

    def output_router(self, *, with_untyped_audit: bool):
        spec = NetSpec("native")
        pool = spec.s["n"].p.pool(None)
        classify = spec.s["n"].t.classify(handler=petri_handler(passthrough))
        approved = spec.s["n"].p.approved("Approved")
        rejected = spec.s["n"].p.rejected("Rejected")
        targets = [approved, rejected]
        if with_untyped_audit:
            targets.append(spec.s["n"].p.audit(None))
        pool >> classify >> tuple(targets)
        return spec.build(), pool

    def test_output_arcs_route_by_token_color(self) -> None:
        built, pool = self.output_router(with_untyped_audit=False)
        subject = self.pure_engine(built, {abs(pool): (Token("Approved", {"score": 9}),)})
        drive_bounded(subject)
        assert [t.color for t in subject.marking.place(NetPath("n.approved"))] == ["Approved"]
        assert not tuple(subject.marking.place(NetPath("n.rejected")))

    def test_unmatched_token_is_silently_dropped(self) -> None:
        """The transition fires and the token vanishes — no error, no parking.
        This is why exhaustiveness must be compile-time and projection loud."""
        built, pool = self.output_router(with_untyped_audit=False)
        subject = self.pure_engine(built, {abs(pool): (Token("Mystery", {"x": 1}),)})
        drive_bounded(subject)
        for place in ("n.pool", "n.approved", "n.rejected"):
            assert not tuple(subject.marking.place(NetPath(place)))

    def test_one_token_deposits_on_every_admitting_arc(self) -> None:
        built, pool = self.output_router(with_untyped_audit=True)
        subject = self.pure_engine(built, {abs(pool): (Token("Approved", {"score": 9}),)})
        drive_bounded(subject)
        # Typed arc and untyped audit arc BOTH admit it: the token duplicates.
        assert [t.color for t in subject.marking.place(NetPath("n.approved"))] == ["Approved"]
        assert [t.color for t in subject.marking.place(NetPath("n.audit"))] == ["Approved"]

    def test_input_arcs_gate_enabledness_by_token_color(self) -> None:
        """The XOR can also live on input arcs: two consumers on one untyped
        place, each admitted by color. Works today — but only after something
        stamped the concrete color, which is exactly the converter's job."""
        spec = NetSpec("native")
        pool = spec.s["n"].p.pool(None)
        to_a = spec.s["n"].t.to_approved(handler=petri_handler(passthrough))
        to_r = spec.s["n"].t.to_rejected(handler=petri_handler(passthrough))
        pool >> arc(color="Approved") >> to_a
        pool >> arc(color="Rejected") >> to_r
        out_a = spec.s["n"].p.out_approved("Approved")
        out_r = spec.s["n"].p.out_rejected("Rejected")
        to_a >> out_a
        to_r >> out_r
        built = spec.build()

        subject = self.pure_engine(built, {abs(pool): (Token("Rejected", {"reason": "no"}),)})
        drive_bounded(subject)
        assert not tuple(subject.marking.place(NetPath("n.out_approved")))
        assert [t.color for t in subject.marking.place(NetPath("n.out_rejected"))] == ["Rejected"]


class TestHandlerConstruction:
    def test_handler_refuses_topology_missing_a_variant_arc(self) -> None:
        spec = NetSpec("broken")
        entry = spec.s["w"].p.entry("Application")
        transition = spec.s["w"].t.evaluate(handler="evaluate")
        only = spec.s["w"].p.on_approved("Approved")
        entry >> transition >> only
        built = spec.build()
        with pytest.raises(ValueError, match=r"no output arc for \['Rejected'\]"):
            VariantRoutingActivityHandler(built.net, NetPath("w.evaluate"), evaluate, ("Approved", "Rejected"))
