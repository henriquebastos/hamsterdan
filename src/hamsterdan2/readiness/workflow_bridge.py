# Copyright (c) 2026 Henrique Bastos

"""The sole adapter from CV21 readiness into the retained V5 workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import TYPE_CHECKING, Never

from petrus.impetus.petrinet import Token
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
from hamsterdan2.readiness.ingress_values import (
    AdmissionGrant,
    HistoryDeliveryIdentity,
    IngressEntry,
    IngressManifest,
)
from hamsterdan2.workflow.values import AwaitingObservation, PullRequestSubject


BRIDGE_IDENTITY = "workflow-bridge/head-seen-history-acceptance@2"


if TYPE_CHECKING:
    from petrus.impetus.binding import ActivityHandler, Handler
    from petrus.impetus.petrinet import Guard, Marking, Net, NetUri


class WorkflowBridgeError(Exception):
    """A retained V5 value could not cross into the CV21 workflow language."""


class RetainedSnapshotRejectedError(WorkflowBridgeError):
    """The retained snapshot does not map to an admitted CV21 posture."""


class UnsupportedHeadObservationError(WorkflowBridgeError):
    """A Head observation requires a bridge family not implemented in this cut."""


@dataclass(frozen=True)
class BridgedDelivery:
    """Private retained representation of one exact source-neutral entry."""

    source: str
    token: Token
    identity: HistoryDeliveryIdentity


def history_delivery_identity(
    *,
    manifest: IngressManifest,
    grant: AdmissionGrant,
    entry: IngressEntry,
) -> HistoryDeliveryIdentity:
    """Bind the exact manifest-scoped grant and entry to this bridge contract."""
    material = json.dumps(
        {
            "bridge_identity": BRIDGE_IDENTITY,
            "entry_order": entry.order,
            "grant_id": str(grant.grant_id),
            "manifest_digest": grant.manifest_digest,
            "manifest_id": str(manifest.manifest_id),
            "observation_key": str(entry.observation_key),
            "version": 1,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return HistoryDeliveryIdentity(f"history-delivery:v1:sha256:{sha256(material).hexdigest()}")


def bridge_head_delivery(
    *,
    manifest: IngressManifest,
    grant: AdmissionGrant,
    entry: IngressEntry,
) -> BridgedDelivery:
    """Convert the one admitted Head family without making a workflow decision."""
    if grant.manifest_id != manifest.manifest_id or entry not in manifest.entries:
        raise WorkflowBridgeError("manifest_entry_authority_mismatch")
    observation = entry.observation
    lifecycle_shape = (
        observation.local_incarnation,
        observation.lifecycle_state,
        observation.draft,
        observation.merged,
    )
    if lifecycle_shape != (1, "open", False, False):
        raise UnsupportedHeadObservationError("unsupported_head_lifecycle", lifecycle_shape)
    retained = HeadSeen(
        head=str(observation.head.sha),
        base=str(observation.base.sha),
        mergeable=observation.mergeable is True,
        policy=str(manifest.policy_revision),
        strict_base=True,
        base_current=False,
    )
    return BridgedDelivery(
        source="on_head",
        token=Token("HeadSeen", retained.dump()),
        identity=history_delivery_identity(manifest=manifest, grant=grant, entry=entry),
    )


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
