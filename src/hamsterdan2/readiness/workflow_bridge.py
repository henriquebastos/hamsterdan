# Copyright (c) 2026 Henrique Bastos

"""The sole adapter from source-neutral Intake into the retained V5 workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import TYPE_CHECKING, Never, cast

from petrus.impetus.history import FiringBegun, FiringCompleted, TokensProduced
from petrus.impetus.petrinet import NetPath, Token
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
    HeadSeen,
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
from hamsterdan2.readiness.intake_values import (
    HistoryDeliveryIdentity,
    ObservationKey,
    PolicyRevision,
    PreparedIntake,
)
from hamsterdan2.readiness.projection import canonical_observation_for, observation_key_for
from hamsterdan2.workflow.values import AwaitingObservation


BRIDGE_IDENTITY = "workflow-bridge/head-seen-intake@4"


if TYPE_CHECKING:
    from petrus.impetus.binding import ActivityHandler, Handler
    from petrus.impetus.instance import FiringOutcome
    from petrus.impetus.petrinet import Guard, Marking, Net, NetUri

    from hamsterdan2.workflow.observations import HeadObservation
    from hamsterdan2.workflow.values import PullRequestIdentity


class WorkflowBridgeError(Exception):
    """A value could not cross the retained workflow boundary exactly."""


class UnsupportedHeadObservationError(WorkflowBridgeError):
    """A Head observation is outside the implemented retained mapping."""


@dataclass(frozen=True)
class BridgedDelivery:
    """Private retained representation of one exact source-neutral Intake."""

    source: str
    token: Token
    identity: HistoryDeliveryIdentity


def history_delivery_identity(
    observation_key: ObservationKey,
    policy_revision: PolicyRevision,
) -> HistoryDeliveryIdentity:
    material = json.dumps(
        {
            "bridge_identity": BRIDGE_IDENTITY,
            "observation_key": str(observation_key),
            "policy_revision": str(policy_revision),
            "version": 2,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return HistoryDeliveryIdentity(f"history-delivery:v2:sha256:{sha256(material).hexdigest()}")


def prepare_head_intake(
    observation: HeadObservation,
    *,
    policy_revision: PolicyRevision,
) -> PreparedIntake:
    canonical = canonical_observation_for(observation)
    key = observation_key_for(canonical)
    prepared = PreparedIntake(
        observation=observation,
        observation_key=key,
        canonical_observation=canonical,
        policy_revision=policy_revision,
        bridge_identity=BRIDGE_IDENTITY,
        delivery_identity=history_delivery_identity(key, policy_revision),
    )
    bridge_head_delivery(prepared)
    return prepared


def bridge_head_delivery(prepared: PreparedIntake) -> BridgedDelivery:
    observation = prepared.observation
    lifecycle_shape = (
        observation.generation,
        observation.lifecycle_state,
        observation.draft,
        observation.merged,
    )
    if lifecycle_shape != (1, "open", False, False):
        raise UnsupportedHeadObservationError("unsupported_head_lifecycle", lifecycle_shape)
    canonical = canonical_observation_for(observation)
    key = observation_key_for(canonical)
    identity = history_delivery_identity(key, prepared.policy_revision)
    if (
        prepared.bridge_identity != BRIDGE_IDENTITY
        or prepared.canonical_observation != canonical
        or prepared.observation_key != key
        or prepared.delivery_identity != identity
    ):
        raise WorkflowBridgeError("prepared_intake_correlation_mismatch")
    retained = HeadSeen(
        head=str(observation.head.sha),
        base=str(observation.base.sha),
        mergeable=observation.mergeable is True,
        policy=str(prepared.policy_revision),
        strict_base=True,
        base_current=False,
    )
    return BridgedDelivery(
        source="on_head",
        token=Token("HeadSeen", retained.dump()),
        identity=identity,
    )


def head_seen_data(tokens: object) -> dict[str, object]:
    if not isinstance(tokens, list) or len(tokens) != 1:
        raise WorkflowBridgeError("malformed_intake_history")
    token = tokens[0]
    if not isinstance(token, dict) or token.get("color") != "HeadSeen":
        raise WorkflowBridgeError("malformed_intake_history")
    raw_data = token.get("data")
    if not isinstance(raw_data, dict):
        raise WorkflowBridgeError("malformed_intake_history")
    return cast("dict[str, object]", raw_data)


def retained_head_seen(data: dict[str, object]) -> HeadSeen:
    try:
        return HeadSeen(
            head=cast("str", data.get("head")),
            base=cast("str", data.get("base")),
            mergeable=cast("bool", data.get("mergeable")),
            policy=cast("str", data.get("policy")),
            strict_base=cast("bool", data.get("strict_base")),
            base_current=cast("bool", data.get("base_current")),
        )
    except TypeError, ValueError:
        raise WorkflowBridgeError("malformed_intake_history") from None


def bridged_delivery_from_history(record: Mapping[str, object]) -> BridgedDelivery:
    identity = record.get("identity")
    if (
        record.get("record") != "ExternalEventDelivered"
        or record.get("source") != "on_head"
        or record.get("scope") is not None
        or not isinstance(identity, str)
    ):
        raise WorkflowBridgeError("malformed_intake_history")
    try:
        delivery_identity = HistoryDeliveryIdentity(identity)
    except ValueError:
        raise WorkflowBridgeError("malformed_intake_history") from None
    retained = retained_head_seen(head_seen_data(record.get("tokens")))
    return BridgedDelivery(
        source="on_head",
        token=Token("HeadSeen", retained.dump()),
        identity=delivery_identity,
    )


def validate_firing_outcome(outcome: FiringOutcome, *, bridged: BridgedDelivery, occurrence: int) -> None:
    expected_records = (
        FiringBegun(NetPath(bridged.source), occurrence=occurrence),
        TokensProduced(NetPath("life.heads"), (bridged.token,), occurrence=occurrence),
        FiringCompleted(NetPath(bridged.source), occurrence=occurrence),
    )
    observed = (
        str(outcome.transition),
        outcome.occurrence,
        outcome.consumed,
        outcome.produced,
        outcome.records,
    )
    expected = (
        bridged.source,
        occurrence,
        (),
        ((NetPath("life.heads"), bridged.token),),
        expected_records,
    )
    if observed != expected:
        raise WorkflowBridgeError("firing_outcome_correlation_mismatch")


def project_awaiting_observation(
    snapshot: Mapping[str, object],
    pr_identity: PullRequestIdentity,
    workflow_id: str,
) -> AwaitingObservation:
    current = snapshot.get("current")
    if snapshot.get("protocol") != 1 or snapshot.get("instance") != workflow_id or not isinstance(current, Mapping):
        raise WorkflowBridgeError("malformed_open_workflow_snapshot")
    if current.get("status") != "awaiting" or current.get("in_flight") != []:
        raise WorkflowBridgeError("malformed_open_workflow_snapshot")
    return AwaitingObservation(pr_identity=pr_identity)


def activity_execution_requires_a_worker(**arguments: object) -> Never:
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


def build_workflow(workflow_id: str) -> BridgedWorkflow:
    built = build_net_v5()
    definitions = activity_definitions()
    return BridgedWorkflow(
        identity=BRIDGE_IDENTITY,
        net=built.net,
        marking=seed_marking(workflow_id),
        handlers=wire_gates(
            built=built,
            gates=GATES,
            definitions=definitions,
            derived=DERIVED,
        ),
        guards=built.guards,
        activities=tuple(definition.declaration for definition in definitions.values()),
    )
