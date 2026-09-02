# Copyright (c) 2026 Henrique Bastos

"""One bounded Petrus execution for one PR identity in shared History."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import TYPE_CHECKING, Literal, Never, cast

from petrus.engine.sqlite import create_engine, load_engine
from petrus.impetus.history_store import SqliteHistoryStore
from petrus.impetus.instance import AcceptedDelivery, PriorAcknowledgement, ScopedDeliveryAcknowledgement
from petrus.motus.dispatch import LocalDispatch

from hamsterdan2.readiness.intake_values import ObservationCompletion, PolicyRevision, PreparedIntake
from hamsterdan2.readiness.projection import project_head
from hamsterdan2.readiness.workflow_bridge import (
    BRIDGE_IDENTITY,
    BridgedDelivery,
    BridgedWorkflow,
    WorkflowBridgeError,
    bridge_head_delivery,
    bridged_delivery_from_history,
    build_workflow,
    prepare_head_intake,
    project_awaiting_observation,
    validate_firing_outcome,
)


if TYPE_CHECKING:
    from pathlib import Path

    from petrus.engine import Engine

    from hamsterdan2.github_app.models import NormalizedPullRequestWebhook
    from hamsterdan2.host.values import PullRequestWorkflow
    from hamsterdan2.workflow.values import AwaitingObservation, PullRequestIdentity


MAX_HISTORY_BYTES = 134_217_728
MAX_HISTORY_RECORDS_PER_WORKFLOW = 4_096
MAX_HISTORY_WRITE_HEADROOM = 1_048_576


class ReadinessRuntimeError(Exception):
    """Readiness cannot safely open or drive one canonical workflow."""


class HistoryCapacityError(ReadinessRuntimeError):
    """Shared History crossed its finite byte or per-workflow record bound."""


class HistoryCorruptionError(ReadinessRuntimeError):
    """One workflow's canonical History cannot be reconstructed exactly."""


class ObservationNotAcceptedError(ReadinessRuntimeError):
    """A PR authority turn found no accepted observation in History."""


@dataclass(frozen=True)
class HistoryAcceptance:
    """Internal correlation from public Engine acceptance back to Intake."""

    occurrence: int
    finished: bool


@dataclass(frozen=True)
class HistoryObservation:
    """One exact bridge delivery reconstructed from canonical History."""

    bridged: BridgedDelivery
    occurrence: int
    finished: bool


def prepare_intake(
    webhook: NormalizedPullRequestWebhook,
    *,
    policy_revision: PolicyRevision,
) -> PreparedIntake:
    return prepare_head_intake(
        project_head(webhook.snapshot),
        policy_revision=policy_revision,
    )


def history_storage_bytes(path: Path) -> int:
    files = (path, path.with_name(f"{path.name}-wal"), path.with_name(f"{path.name}-shm"))
    return sum(candidate.stat().st_size for candidate in files if candidate.is_file())


def require_history_capacity(path: Path, *, reserved_bytes: int = 0) -> None:
    used = history_storage_bytes(path)
    if used + reserved_bytes > MAX_HISTORY_BYTES:
        raise HistoryCapacityError("history_byte_capacity_exhausted", used, MAX_HISTORY_BYTES)


def workflow_has_history(path: Path, workflow_id: str) -> bool:
    history = SqliteHistoryStore(path, workflow_id)
    try:
        return len(history) > 0
    finally:
        history.close()


def engine_options(workflow: BridgedWorkflow, dispatch: LocalDispatch) -> dict[str, object]:
    return {
        "dispatch": dispatch,
        "handlers": workflow.handlers,
        "guards": workflow.guards,
        "activities": workflow.activities,
    }


def create_history_engine(
    path: Path,
    workflow_id: str,
    workflow: BridgedWorkflow,
    dispatch: LocalDispatch,
) -> Engine:
    require_history_capacity(path, reserved_bytes=MAX_HISTORY_WRITE_HEADROOM)
    return create_engine(
        path=path,
        net=workflow.net,
        instance=workflow_id,
        marking=workflow.marking,
        **engine_options(workflow, dispatch),
    )


def load_history_engine(
    path: Path,
    workflow_id: str,
    workflow: BridgedWorkflow,
    dispatch: LocalDispatch,
) -> Engine:
    require_history_capacity(path)
    try:
        return load_engine(
            path=path,
            net=workflow.net,
            instance=workflow_id,
            **engine_options(workflow, dispatch),
        )
    except sqlite3.DatabaseError, RecursionError, TypeError, ValueError:
        raise HistoryCorruptionError(
            "malformed_canonical_history",
            workflow_id,
            "use a fresh state root",
        ) from None


def bounded_history_page(engine: Engine, workflow_id: str, *, reserved_records: int = 0) -> dict[str, object]:
    page = engine.history_page(0, MAX_HISTORY_RECORDS_PER_WORKFLOW)
    frontier = page.get("frontier")
    records = page.get("records")
    valid = (
        page.get("protocol") == 1
        and page.get("instance") == workflow_id
        and page.get("after") == 0
        and isinstance(frontier, int)
        and not isinstance(frontier, bool)
        and page.get("next") == frontier
        and isinstance(records, list)
        and len(records) == frontier
        and frontier + reserved_records <= MAX_HISTORY_RECORDS_PER_WORKFLOW
    )
    if not valid:
        raise HistoryCapacityError(
            "history_record_capacity_or_page_shape_mismatch",
            workflow_id,
            MAX_HISTORY_RECORDS_PER_WORKFLOW,
        )
    return page


def history_payloads(page: dict[str, object]) -> list[dict[str, object]]:
    records = cast("list[object]", page["records"])
    payloads: list[dict[str, object]] = []
    for position, item in enumerate(records):
        if not isinstance(item, dict) or set(item) != {"position", "record"} or item.get("position") != position:
            raise HistoryCorruptionError("malformed_history_record_envelope")
        payload = item.get("record")
        if not isinstance(payload, dict):
            raise HistoryCorruptionError("malformed_history_record_payload")
        payloads.append(cast("dict[str, object]", payload))
    return payloads


def bridge_history_observations(page: dict[str, object]) -> tuple[HistoryObservation, ...]:
    payloads = history_payloads(page)
    positions = (position for position, payload in enumerate(payloads) if is_bridge_history_delivery(payload))
    observations = tuple(history_observation(payloads, position) for position in positions)
    identities = tuple(str(observation.bridged.identity) for observation in observations)
    if len(identities) != len(set(identities)):
        raise HistoryCorruptionError("duplicate_intake_history_identity")
    return observations


def is_bridge_history_delivery(payload: dict[str, object]) -> bool:
    identity = payload.get("identity")
    return (
        payload.get("record") == "ExternalEventDelivered"
        and isinstance(identity, str)
        and identity.startswith("history-delivery:v2:sha256:")
    )


def history_occurrence(payload: dict[str, object]) -> int:
    occurrence = payload.get("occurrence")
    if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence <= 0:
        raise HistoryCorruptionError("malformed_intake_history")
    return occurrence


def require_firing_begun(
    payloads: list[dict[str, object]],
    position: int,
    bridged: BridgedDelivery,
    occurrence: int,
) -> None:
    begun = payloads[position + 1] if position + 1 < len(payloads) else None
    expected = {
        "record": "FiringBegun",
        "schema": 5,
        "transition": bridged.source,
        "occurrence": occurrence,
        "scope": None,
        "instant": payloads[position].get("instant"),
    }
    if begun != expected:
        raise HistoryCorruptionError("malformed_intake_history")


def require_terminal_status(
    terminals: list[dict[str, object]],
    products: list[dict[str, object]],
) -> bool:
    if len(terminals) > 1 or (terminals and terminals[0].get("record") == "FiringFailed"):
        raise HistoryCorruptionError("failed_or_duplicate_intake_terminal")
    if not terminals and products:
        raise HistoryCorruptionError("partial_intake_terminal")
    return bool(terminals)


def history_finished(
    payloads: list[dict[str, object]],
    position: int,
    bridged: BridgedDelivery,
    occurrence: int,
) -> bool:
    trailing = payloads[position + 2 :]
    terminals = [
        record
        for record in trailing
        if record.get("transition") == bridged.source
        and record.get("occurrence") == occurrence
        and record.get("record") in {"FiringCompleted", "FiringFailed"}
    ]
    products = [
        record
        for record in trailing
        if record.get("record") == "TokensProduced"
        and record.get("place") == "life.heads"
        and record.get("occurrence") == occurrence
    ]
    if not require_terminal_status(terminals, products):
        return False
    instant = payloads[position].get("instant")
    expected_product = {
        "record": "TokensProduced",
        "schema": 5,
        "place": "life.heads",
        "tokens": [{"color": bridged.token.color, "data": bridged.token.data}],
        "occurrence": occurrence,
        "entries": [],
        "scope": None,
        "instant": instant,
    }
    expected_terminal = {
        "record": "FiringCompleted",
        "schema": 5,
        "transition": bridged.source,
        "occurrence": occurrence,
        "instant": instant,
    }
    if products != [expected_product] or terminals != [expected_terminal]:
        raise HistoryCorruptionError("malformed_intake_terminal")
    return True


def history_observation(
    payloads: list[dict[str, object]],
    position: int,
) -> HistoryObservation:
    payload = payloads[position]
    try:
        bridged = bridged_delivery_from_history(payload)
    except WorkflowBridgeError:
        raise HistoryCorruptionError("malformed_intake_history") from None
    occurrence = history_occurrence(payload)
    require_firing_begun(payloads, position, bridged, occurrence)
    return HistoryObservation(
        bridged=bridged,
        occurrence=occurrence,
        finished=history_finished(payloads, position, bridged, occurrence),
    )


def correlate_acceptance(
    result: AcceptedDelivery | PriorAcknowledgement | ScopedDeliveryAcknowledgement,
    *,
    bridged: BridgedDelivery,
    workflow_id: str,
) -> HistoryAcceptance:
    if type(result) is AcceptedDelivery:
        return correlate_accepted_delivery(result, bridged=bridged, workflow_id=workflow_id)
    if type(result) is PriorAcknowledgement:
        return correlate_prior_acknowledgement(result, bridged=bridged)
    return reject_acceptance_result(result)


def correlate_accepted_delivery(
    result: AcceptedDelivery,
    *,
    bridged: BridgedDelivery,
    workflow_id: str,
) -> HistoryAcceptance:
    correlation = (str(result.instance), str(result.source), str(result.identity))
    if correlation != (workflow_id, bridged.source, str(bridged.identity)):
        raise HistoryCorruptionError("accepted_delivery_correlation_mismatch")
    return HistoryAcceptance(occurrence=int(result.occurrence), finished=False)


def correlate_prior_acknowledgement(
    result: PriorAcknowledgement,
    *,
    bridged: BridgedDelivery,
) -> HistoryAcceptance:
    if result.identity != bridged.identity:
        raise HistoryCorruptionError("prior_acknowledgement_correlation_mismatch")
    return HistoryAcceptance(occurrence=result.occurrence, finished=True)


def reject_acceptance_result(
    result: AcceptedDelivery | PriorAcknowledgement | ScopedDeliveryAcknowledgement,
) -> Never:
    if type(result) is ScopedDeliveryAcknowledgement:
        raise HistoryCorruptionError("unexpected_scoped_acknowledgement")
    raise TypeError("Engine.accept_delivery returned an unsupported result")


def select_history_observation(observations: tuple[HistoryObservation, ...]) -> HistoryObservation:
    unfinished = tuple(item for item in observations if not item.finished)
    if unfinished:
        return min(unfinished, key=lambda item: item.occurrence)
    if observations:
        return max(observations, key=lambda item: item.occurrence)
    raise ObservationNotAcceptedError("record one Intake in History before requesting completion")


def complete_history_observation(
    engine: Engine,
    selected: HistoryObservation,
    *,
    history_path: Path,
    workflow_id: str,
) -> Literal["completed", "already_completed"]:
    result = engine.accept_delivery(
        selected.bridged.source,
        selected.bridged.token,
        identity=str(selected.bridged.identity),
    )
    accepted = correlate_acceptance(
        result,
        bridged=selected.bridged,
        workflow_id=workflow_id,
    )
    if accepted.occurrence != selected.occurrence or accepted.finished != selected.finished:
        raise HistoryCorruptionError("completion_acceptance_correlation_mismatch")
    if type(result) is not AcceptedDelivery:
        return "already_completed"
    bounded_history_page(engine, workflow_id, reserved_records=2)
    require_history_capacity(history_path, reserved_bytes=MAX_HISTORY_WRITE_HEADROOM)
    outcome = engine.complete_delivery(result)
    validate_firing_outcome(
        outcome,
        bridged=selected.bridged,
        occurrence=selected.occurrence,
    )
    return "completed"


class ReadinessRuntime:
    """Open and drive one workflow identity without owning application intake."""

    def __init__(
        self,
        *,
        history_path: Path,
        dispatch_path: Path,
        workflow_id: str,
    ) -> None:
        self._history_path = history_path
        self._workflow_id = workflow_id
        self._workflow = build_workflow(workflow_id)
        self._dispatch = LocalDispatch(dispatch_path, instance=workflow_id)

    def open(self, pr_identity: PullRequestIdentity) -> AwaitingObservation:
        if workflow_has_history(self._history_path, self._workflow_id):
            engine = load_history_engine(
                self._history_path,
                self._workflow_id,
                self._workflow,
                self._dispatch,
            )
        else:
            engine = create_history_engine(
                self._history_path,
                self._workflow_id,
                self._workflow,
                self._dispatch,
            )
        try:
            bounded_history_page(engine, self._workflow_id)
            return project_awaiting_observation(
                engine.snapshot(),
                pr_identity,
                self._workflow_id,
            )
        finally:
            engine.close()

    def accept(self, workflow: PullRequestWorkflow, prepared: PreparedIntake) -> HistoryAcceptance:
        if (
            workflow.workflow_id != self._workflow_id
            or workflow.bridge_identity != BRIDGE_IDENTITY
            or prepared.bridge_identity != BRIDGE_IDENTITY
            or prepared.observation.pr_identity != workflow.pr_identity
        ):
            raise ReadinessRuntimeError("intake_workflow_correlation_mismatch")
        bridged = bridge_head_delivery(prepared)
        engine = load_history_engine(
            self._history_path,
            self._workflow_id,
            self._workflow,
            self._dispatch,
        )
        try:
            page = bounded_history_page(engine, self._workflow_id)
            prior = any(
                observation.bridged.identity == bridged.identity for observation in bridge_history_observations(page)
            )
            bounded_history_page(engine, self._workflow_id, reserved_records=0 if prior else 2)
            require_history_capacity(
                self._history_path,
                reserved_bytes=0 if prior else MAX_HISTORY_WRITE_HEADROOM,
            )
            result = engine.accept_delivery(
                bridged.source,
                bridged.token,
                identity=str(bridged.identity),
            )
            return correlate_acceptance(result, bridged=bridged, workflow_id=self._workflow_id)
        finally:
            engine.close()

    def complete_next(self, workflow: PullRequestWorkflow) -> ObservationCompletion:
        if workflow.workflow_id != self._workflow_id or workflow.bridge_identity != BRIDGE_IDENTITY:
            raise ReadinessRuntimeError("completion_workflow_correlation_mismatch")
        engine = load_history_engine(
            self._history_path,
            self._workflow_id,
            self._workflow,
            self._dispatch,
        )
        try:
            page = bounded_history_page(engine, self._workflow_id)
            selected = select_history_observation(bridge_history_observations(page))
            disposition = complete_history_observation(
                engine,
                selected,
                history_path=self._history_path,
                workflow_id=self._workflow_id,
            )
            return ObservationCompletion(
                pr_identity=workflow.pr_identity,
                workflow_id=workflow.workflow_id,
                delivery_identity=selected.bridged.identity,
                occurrence=selected.occurrence,
                disposition=disposition,
            )
        finally:
            engine.close()


def build_readiness_runtime(
    *,
    history_path: Path,
    dispatch_path: Path,
    workflow_id: str,
) -> ReadinessRuntime:
    return ReadinessRuntime(
        history_path=history_path,
        dispatch_path=dispatch_path,
        workflow_id=workflow_id,
    )
