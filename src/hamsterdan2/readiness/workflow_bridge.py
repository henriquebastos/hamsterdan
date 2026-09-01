# Copyright (c) 2026 Henrique Bastos

"""The sole adapter from CV21 readiness into the retained V5 workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import TYPE_CHECKING, Never, cast

from petrus.impetus.history import FiringBegun, FiringCompleted, TokensProduced
from petrus.impetus.petrinet import NetPath, Token
from petrus.motus.activity import ActivityDeclaration, ActivityDefinition
from pydantic import TypeAdapter, ValidationError

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
    LifeState,
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
    ObservationFoldPosture,
)
from hamsterdan2.workflow.values import AwaitingObservation, PullRequestSubject


BRIDGE_IDENTITY = "workflow-bridge/head-seen-history-fold@3"
MAX_PROJECTED_MARKING_PLACES = 64
MAX_PROJECTED_MARKING_TOKENS = 128


if TYPE_CHECKING:
    from petrus.impetus.binding import ActivityHandler, Handler
    from petrus.impetus.instance import FiringOutcome
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


def validate_firing_outcome(outcome: FiringOutcome, *, bridged: BridgedDelivery, occurrence: int) -> None:
    """Require the exact retained source completion and no downstream firing."""
    expected_records = (
        FiringBegun(NetPath(bridged.source), occurrence=occurrence),
        TokensProduced(
            NetPath("life.heads"),
            (bridged.token,),
            occurrence=occurrence,
        ),
        FiringCompleted(NetPath(bridged.source), occurrence=occurrence),
    )
    correlation = (
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
    if correlation != expected:
        raise WorkflowBridgeError("firing_outcome_correlation_mismatch")


def complete_history_payloads(
    history_page: Mapping[str, object],
    *,
    instance_id: str,
) -> list[dict[str, object]]:
    records = complete_history_records(history_page, instance_id=instance_id)
    payloads: list[dict[str, object]] = []
    for position, item in enumerate(records):
        record = item.get("record") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or set(item) != {"position", "record"}
            or item.get("position") != position
            or not isinstance(record, dict)
        ):
            raise RetainedSnapshotRejectedError("malformed_complete_history_page")
        payloads.append(cast("dict[str, object]", record))
    return payloads


def complete_history_records(
    history_page: Mapping[str, object],
    *,
    instance_id: str,
) -> list[object]:
    records = history_page.get("records")
    frontier = history_page.get("frontier")
    complete_page = (
        history_page.get("protocol") == 1
        and history_page.get("instance") == instance_id
        and history_page.get("after") == 0
        and isinstance(frontier, int)
        and not isinstance(frontier, bool)
        and history_page.get("next") == frontier
        and isinstance(records, list)
        and len(records) == frontier
    )
    if not complete_page:
        raise RetainedSnapshotRejectedError("malformed_complete_history_page")
    if not isinstance(records, list):
        raise RetainedSnapshotRejectedError("malformed_complete_history_page")
    return cast("list[object]", records)


def complete_history_tail(
    history_page: Mapping[str, object],
    *,
    bridged: BridgedDelivery,
    instance_id: str,
    occurrence: int,
) -> None:
    payloads = complete_history_payloads(history_page, instance_id=instance_id)
    expected_token = {"color": bridged.token.color, "data": bridged.token.data}
    expected_tail = [
        {
            "record": "ExternalEventDelivered",
            "schema": 5,
            "source": bridged.source,
            "tokens": [expected_token],
            "identity": str(bridged.identity),
            "occurrence": occurrence,
            "scope": None,
            "instant": 0,
        },
        {
            "record": "FiringBegun",
            "schema": 5,
            "transition": bridged.source,
            "occurrence": occurrence,
            "scope": None,
            "instant": 0,
        },
        {
            "record": "TokensProduced",
            "schema": 5,
            "place": "life.heads",
            "tokens": [expected_token],
            "occurrence": occurrence,
            "entries": [],
            "scope": None,
            "instant": 0,
        },
        {
            "record": "FiringCompleted",
            "schema": 5,
            "transition": bridged.source,
            "occurrence": occurrence,
            "instant": 0,
        },
    ]
    starts = [
        position
        for position, record in enumerate(payloads)
        if record.get("record") == "ExternalEventDelivered" and record.get("identity") == str(bridged.identity)
    ]
    if len(starts) != 1 or payloads[starts[0] :] != expected_tail:
        raise RetainedSnapshotRejectedError("malformed_observation_terminal_history")
    if any(record.get("record") == "FiringFailed" for record in payloads):
        raise RetainedSnapshotRejectedError("failed_observation_occurrence")


def retained_runtime_current(
    snapshot: Mapping[str, object],
    *,
    instance_id: str,
    history_frontier: int,
) -> Mapping[str, object]:
    current = snapshot.get("current")
    if (
        snapshot.get("protocol") != 1
        or snapshot.get("instance") != instance_id
        or snapshot.get("frontier") != history_frontier
        or not isinstance(current, Mapping)
        or current.get("status") != "running"
        or current.get("in_flight") != []
    ):
        raise RetainedSnapshotRejectedError("malformed_post_fold_runtime")
    return cast("Mapping[str, object]", current)


def bounded_retained_places(current: Mapping[str, object]) -> dict[str, list[object]]:
    marking = retained_marking(current)
    places: dict[str, list[object]] = {}
    total_tokens = 0
    for item in marking:
        place, tokens = retained_marking_item(item)
        if place in places:
            raise RetainedSnapshotRejectedError("malformed_post_fold_marking")
        total_tokens += len(tokens)
        if total_tokens > MAX_PROJECTED_MARKING_TOKENS:
            raise RetainedSnapshotRejectedError("post_fold_marking_capacity_exceeded")
        places[place] = tokens
    return places


def retained_marking_item(item: object) -> tuple[str, list[object]]:
    if not isinstance(item, dict):
        raise RetainedSnapshotRejectedError("malformed_post_fold_marking")
    item = cast("dict[str, object]", item)
    place = item.get("place")
    tokens = item.get("tokens")
    if set(item) != {"place", "tokens"} or not isinstance(place, str) or not isinstance(tokens, list):
        raise RetainedSnapshotRejectedError("malformed_post_fold_marking")
    return place, cast("list[object]", tokens)


def retained_marking(current: Mapping[str, object]) -> list[object]:
    marking = current.get("marking")
    if not isinstance(marking, list) or len(marking) > MAX_PROJECTED_MARKING_PLACES:
        raise RetainedSnapshotRejectedError("post_fold_marking_capacity_exceeded")
    return cast("list[object]", marking)


def retained_state_payload(state_token: object) -> dict[str, object]:
    if (
        not isinstance(state_token, dict)
        or set(state_token) != {"color", "data"}
        or state_token.get("color") != "LifeState"
        or not isinstance(state_token.get("data"), dict)
    ):
        raise RetainedSnapshotRejectedError("retained_life_state_mismatch")
    state_token = cast("dict[str, object]", state_token)
    return cast("dict[str, object]", state_token["data"])


def retained_life_state(places: Mapping[str, list[object]]) -> LifeState:
    state_tokens = places.get("life.state")
    if not isinstance(state_tokens, list) or len(state_tokens) != 1:
        raise RetainedSnapshotRejectedError("retained_life_state_mismatch")
    payload = retained_state_payload(state_tokens[0])
    try:
        state = TypeAdapter(LifeState).validate_json(json.dumps(payload, separators=(",", ":")))
    except ValidationError, ValueError:
        raise RetainedSnapshotRejectedError("retained_life_state_mismatch") from None
    if state.phase != "running" or state.incarnation != 0:
        raise RetainedSnapshotRejectedError("retained_life_state_mismatch")
    return state


def retained_fold_state(
    snapshot: Mapping[str, object],
    *,
    bridged: BridgedDelivery,
    instance_id: str,
    history_frontier: int,
) -> LifeState:
    current = retained_runtime_current(
        snapshot,
        instance_id=instance_id,
        history_frontier=history_frontier,
    )
    places = bounded_retained_places(current)
    expected_token = {"color": bridged.token.color, "data": bridged.token.data}
    if places.get("life.heads") != [expected_token]:
        raise RetainedSnapshotRejectedError("folded_head_token_mismatch")
    return retained_life_state(places)


def project_observation_fold(
    *,
    snapshot: Mapping[str, object],
    history_page: Mapping[str, object],
    subject: PullRequestSubject,
    instance_id: str,
    manifest: IngressManifest,
    grant: AdmissionGrant,
    entry: IngressEntry,
    occurrence: int,
) -> ObservationFoldPosture:
    """Project one exact completed source occurrence without advancing its enabled fold."""
    if occurrence != 1:
        raise RetainedSnapshotRejectedError("folded_observation_occurrence_mismatch")
    bridged = bridge_head_delivery(manifest=manifest, grant=grant, entry=entry)
    complete_history_tail(
        history_page,
        bridged=bridged,
        instance_id=instance_id,
        occurrence=1,
    )
    frontier = history_page.get("frontier")
    if isinstance(frontier, bool) or not isinstance(frontier, int):
        raise RetainedSnapshotRejectedError("malformed_complete_history_page")
    retained_fold_state(
        snapshot,
        bridged=bridged,
        instance_id=instance_id,
        history_frontier=frontier,
    )
    observation = entry.observation
    retained = HeadSeen(**bridged.token.data)
    return ObservationFoldPosture(
        subject=subject,
        instance_id=instance_id,
        bridge_identity=BRIDGE_IDENTITY,
        manifest_id=manifest.manifest_id,
        grant_id=grant.grant_id,
        manifest_digest=grant.manifest_digest,
        entry_order=entry.order,
        observation_key=entry.observation_key,
        delivery_identity=bridged.identity,
        occurrence=1,
        phase="running",
        local_incarnation=observation.local_incarnation,
        head=observation.head,
        base=observation.base,
        mergeable=retained.mergeable,
        policy_revision=manifest.policy_revision,
        strict_base=True,
        base_current=False,
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
