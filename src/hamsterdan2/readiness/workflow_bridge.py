# Copyright (c) 2026 Henrique Bastos

"""The sole adapter from CV21 readiness into the retained V5 workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Never

from petrus.motus.activity import ActivityDeclaration, ActivityDefinition

from hamsterdan.contracts.readiness_v5 import (
    ABlocked,
    ADeferred,
    AFault,
    ALanded,
    AMoved,
    AgentReview,
    AnnounceReq,
    DashBlocked,
    DashDeferred,
    DashFault,
    DashLanded,
    DashReq,
    DeclinedM,
    FaultM,
    MovedM,
    MutWork,
    Publishable,
    Pushed,
    RemBlocked,
    RemFault,
    RemLanded,
    RemReq,
    Replied,
    ReplyBlocked,
    ReplyFault,
    ReplyReq,
    RerunFault,
    RerunLanded,
    RerunMoved,
    RerunReq,
    ReviewBlocked,
    ReviewFault,
    ReviewLanded,
    ReviewMoved,
    RoundDeferred,
    RoundMoved,
    RoundOpen,
    RoundUnable,
)
from hamsterdan.readiness.net_v5.gating import VariantPayloadConverter, wire_gates
from hamsterdan.readiness.net_v5.topology import DERIVED, GATES, build_net_v5, seed_marking
from hamsterdan2.workflow.values import AwaitingObservation, PullRequestSubject


BRIDGE_IDENTITY = "workflow-bridge/subject-seed-posture@1"


if TYPE_CHECKING:
    from petrus.impetus.binding import ActivityHandler, Handler
    from petrus.impetus.petrinet import Guard, Marking, Net, NetUri


class WorkflowBridgeError(Exception):
    """A retained V5 value could not cross into the CV21 workflow language."""


class RetainedSnapshotRejectedError(WorkflowBridgeError):
    """The retained snapshot does not map to an admitted CV21 posture."""


def activity_execution_requires_a_worker(**arguments: object) -> Never:
    """Fill ActivityDefinition's callable slot without granting authority-side execution."""
    del arguments
    raise RuntimeError("readiness Activity declarations cannot execute without a Motus Worker")


def activity_definition(*, name: str, request: type, result: object) -> ActivityDefinition:
    return ActivityDefinition(
        function=activity_execution_requires_a_worker,
        declaration=ActivityDeclaration(name),
        converter=VariantPayloadConverter(),
        parameters={"work": request},
        result=result,
    )


def activity_definitions() -> dict[str, ActivityDefinition]:
    return {
        "rerun_gate": activity_definition(
            name="rerun_gate",
            request=RerunReq,
            result=RerunLanded | RerunMoved | RerunFault,
        ),
        "review_agent": activity_definition(
            name="review_agent",
            request=RoundOpen,
            result=AgentReview | RoundDeferred | RoundMoved | RoundUnable,
        ),
        "publish_gate": activity_definition(
            name="publish_gate",
            request=Publishable,
            result=ReviewLanded | ReviewMoved | ReviewBlocked | ReviewFault,
        ),
        "git_gate": activity_definition(
            name="git_gate",
            request=MutWork,
            result=Pushed | MovedM | FaultM | DeclinedM,
        ),
        "reply_gate": activity_definition(
            name="reply_gate",
            request=ReplyReq,
            result=Replied | ReplyBlocked | ReplyFault,
        ),
        "reminder_gate": activity_definition(
            name="reminder_gate",
            request=RemReq,
            result=RemLanded | RemBlocked | RemFault,
        ),
        "announce_gate": activity_definition(
            name="announce_gate",
            request=AnnounceReq,
            result=ALanded | ADeferred | ABlocked | AMoved | AFault,
        ),
        "dash_gate": activity_definition(
            name="dash_gate",
            request=DashReq,
            result=DashLanded | DashDeferred | DashBlocked | DashFault,
        ),
    }


@dataclass(frozen=True)
class BridgedWorkflow:
    """Retained workflow construction visible only to readiness runtime."""

    identity: str
    net: Net
    marking: Marking
    handlers: Mapping[NetUri | str, Handler | ActivityHandler]
    guards: Mapping[NetUri, Guard]
    activities: tuple[ActivityDeclaration, ...]


def build_workflow(instance_id: str) -> BridgedWorkflow:
    built = build_net_v5()
    definitions = activity_definitions()
    return BridgedWorkflow(
        identity=BRIDGE_IDENTITY,
        net=built.net,
        marking=seed_marking(instance_id),
        handlers=wire_gates(
            built=built,
            gates=GATES,
            definitions=definitions,
            derived=DERIVED,
        ),
        guards=built.guards,
        activities=tuple(definition.declaration for definition in definitions.values()),
    )


def project_awaiting_observation(
    snapshot: Mapping[str, object], subject: PullRequestSubject, instance_id: str
) -> AwaitingObservation:
    current = snapshot.get("current")
    if snapshot.get("protocol") != 1 or snapshot.get("instance") != instance_id or not isinstance(current, Mapping):
        raise RetainedSnapshotRejectedError(
            instance_id,
            "expected retained protocol 1 for the requested instance with a mapping-valued current posture",
        )
    if current.get("status") != "awaiting" or current.get("in_flight") != []:
        raise RetainedSnapshotRejectedError(
            instance_id,
            "expected retained status 'awaiting' with no in-flight work",
        )
    return AwaitingObservation(subject=subject)
