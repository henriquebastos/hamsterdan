# Copyright (c) 2026 Henrique Bastos

"""One bounded Petrus execution for one replacement readiness lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import TYPE_CHECKING, cast

from petrus.engine.sqlite import create_engine, load_engine
from petrus.impetus.instance import AcceptedDelivery, PriorAcknowledgement, ScopedDeliveryAcknowledgement
from petrus.motus.dispatch import LocalDispatch

from hamsterdan2.readiness.ingress import IngressCustody
from hamsterdan2.readiness.ingress_values import MAX_MANIFESTS, HistoryAcceptancePosture, IngressEntry, StagingPosture
from hamsterdan2.readiness.root import ReadinessRoot
from hamsterdan2.readiness.workflow_bridge import (
    BridgedDelivery,
    BridgedWorkflow,
    bridge_head_delivery,
    build_workflow,
    project_awaiting_observation,
)
from hamsterdan2.workflow.values import PullRequestSubject


if TYPE_CHECKING:
    from pathlib import Path

    from petrus.engine import Engine

    from hamsterdan2.github_app.models import DeliveryId, ProviderRouteId
    from hamsterdan2.workflow.values import AwaitingObservation


MAX_HISTORY_BYTES = 2_097_152
MAX_HISTORY_RECORDS = 4_096
MAX_HISTORY_ENGINE_LOAD_HEADROOM = 131_072
MAX_HISTORY_ACCEPTANCE_HEADROOM = 1_048_576
DELIVERY_ACCEPTANCE_RECORDS = frozenset(
    {"ExternalEventDelivered", "ScopedDeliveryDropped", "ScopedDeliveryQuarantined"}
)


class HistoryAcceptanceError(Exception):
    """Readiness could not safely offer one staged observation to History."""


class StagedObservationNotFoundError(HistoryAcceptanceError):
    """The selected task-2 acquisition has no durable staging authority."""


class HistoryAcceptanceSubjectError(HistoryAcceptanceError):
    """Staging authority identifies a subject other than the bound PR root."""


class CanonicalHistoryMissingError(HistoryAcceptanceError):
    """History acceptance was requested before the registered root was opened."""


class HistoryCapacityError(HistoryAcceptanceError):
    """Canonical History exceeds the finite readiness storage boundary."""


class HistoryCorruptionError(HistoryAcceptanceError):
    """Canonical History cannot be reconstructed through the public Engine."""


@dataclass(frozen=True)
class AcceptanceContext:
    subject: PullRequestSubject
    staging: StagingPosture
    entry: IngressEntry
    bridged: BridgedDelivery


def history_storage_bytes(path: Path) -> int:
    candidates = (path, path.with_name(f"{path.name}-wal"), path.with_name(f"{path.name}-shm"))
    return sum(candidate.stat().st_size for candidate in candidates if candidate.is_file())


def require_history_file_capacity(path: Path, *, reserved_bytes: int = 0) -> None:
    retained_bytes = history_storage_bytes(path)
    if retained_bytes + reserved_bytes > MAX_HISTORY_BYTES:
        raise HistoryCapacityError(
            "history_capacity_exceeded",
            "bytes",
            retained_bytes,
            MAX_HISTORY_BYTES,
        )


def reconstruct_staged_authority(
    ingress: IngressCustody,
    *,
    provider_route_id: ProviderRouteId,
    delivery_id: DeliveryId,
    subject: PullRequestSubject,
) -> tuple[StagingPosture, IngressEntry | None]:
    reconstructed = ingress.reconstructed_staging(
        provider_route_id=provider_route_id,
        delivery_id=delivery_id,
    )
    if reconstructed is None:
        raise StagedObservationNotFoundError(
            provider_route_id,
            delivery_id,
            "stage this acquired delivery before requesting History acceptance",
        )
    acquisition, staging = reconstructed
    staged_subject = PullRequestSubject(
        installation_id=acquisition.webhook.snapshot.subject.installation_id,
        repository_id=acquisition.webhook.snapshot.subject.repository_id,
        pull_request_number=acquisition.webhook.snapshot.subject.pull_request_number,
    )
    if staged_subject != subject:
        raise HistoryAcceptanceSubjectError(
            (subject.installation_id, subject.repository_id, subject.pull_request_number),
            (staged_subject.installation_id, staged_subject.repository_id, staged_subject.pull_request_number),
            "use the readiness root registered for the staged subject",
        )
    entry = staging.manifest.entries[0] if len(staging.manifest.entries) == 1 else None
    return staging, entry


def non_novel_acceptance_posture(
    subject: PullRequestSubject,
    staging: StagingPosture,
    entry: IngressEntry | None,
    *,
    bridge_identity: str,
) -> HistoryAcceptancePosture:
    return HistoryAcceptancePosture(
        subject=subject,
        disposition="refused",
        reason="staging_not_novel",
        staging_disposition=staging.disposition,
        bridge_identity=bridge_identity,
        manifest_id=staging.manifest.manifest_id,
        grant_id=staging.grant.grant_id,
        entry_order=None if entry is None else entry.order,
        observation_key=None if entry is None else entry.observation_key,
        delivery_identity=None,
        occurrence=None,
        finished=False,
        folded=False,
    )


def prepare_history_acceptance(
    subject: PullRequestSubject,
    staging: StagingPosture,
    entry: IngressEntry | None,
) -> AcceptanceContext:
    if entry is None or len(staging.decisions) != 1:
        raise HistoryAcceptanceError("novel_staging_authority_shape_mismatch")
    decision_shape = (
        staging.decisions[0].disposition,
        staging.decisions[0].entry_order,
        staging.decisions[0].observation_key,
        entry.observation.subject,
    )
    expected_shape = ("novel", entry.order, entry.observation_key, subject)
    if decision_shape != expected_shape:
        raise HistoryAcceptanceError("novel_staging_authority_shape_mismatch")
    return AcceptanceContext(
        subject=subject,
        staging=staging,
        entry=entry,
        bridged=bridge_head_delivery(
            manifest=staging.manifest,
            grant=staging.grant,
            entry=entry,
        ),
    )


def require_canonical_history(path: Path, instance_id: str) -> None:
    if not path.is_file():
        raise CanonicalHistoryMissingError(
            instance_id,
            "open the registered readiness root before requesting History acceptance",
        )


def require_history_record_capacity(page: dict[str, object], *, reserved_records: int) -> None:
    frontier = cast("int", page["frontier"])
    if frontier + reserved_records > MAX_HISTORY_RECORDS:
        raise HistoryCapacityError(
            "history_capacity_exceeded",
            "records",
            frontier,
            MAX_HISTORY_RECORDS,
        )


def bounded_history_page(engine: Engine, *, reserved_records: int = 0) -> dict[str, object]:
    page = engine.history_page(0, MAX_HISTORY_RECORDS)
    require_history_record_capacity(page, reserved_records=reserved_records)
    return page


def history_contains_delivery_identity(page: dict[str, object], identity: str) -> bool:
    records = cast("list[dict[str, object]]", page["records"])
    return any(
        cast("dict[str, object]", item["record"]).get("record") in DELIVERY_ACCEPTANCE_RECORDS
        and cast("dict[str, object]", item["record"]).get("identity") == identity
        for item in records
    )


def load_history_engine(
    path: Path,
    instance_id: str,
    workflow: BridgedWorkflow,
    dispatch: LocalDispatch,
) -> Engine:
    require_history_file_capacity(path, reserved_bytes=MAX_HISTORY_ENGINE_LOAD_HEADROOM)
    try:
        return load_engine(
            path=path,
            net=workflow.net,
            instance=instance_id,
            dispatch=dispatch,
            handlers=workflow.handlers,
            guards=workflow.guards,
            activities=workflow.activities,
        )
    except sqlite3.DatabaseError, RecursionError, TypeError, ValueError:
        pass
    raise HistoryCorruptionError(
        "malformed_canonical_history",
        instance_id,
        "replace the malformed History before requesting readiness authority",
    )


def inspect_history_page(
    path: Path,
    dispatch_path: Path,
    instance_id: str,
) -> dict[str, object]:
    """Read one finite neutral page through the public Engine boundary."""
    workflow = build_workflow(instance_id)
    engine = load_history_engine(
        path,
        instance_id,
        workflow,
        LocalDispatch(dispatch_path, instance=instance_id),
    )
    try:
        return bounded_history_page(engine)
    finally:
        engine.close()


def accepted_history_posture(
    context: AcceptanceContext,
    result: AcceptedDelivery,
    *,
    instance_id: str,
    bridge_identity: str,
) -> HistoryAcceptancePosture:
    correlation = (str(result.instance), str(result.source), str(result.identity))
    expected = (instance_id, context.bridged.source, str(context.bridged.identity))
    if correlation != expected:
        raise HistoryAcceptanceError("accepted_delivery_correlation_mismatch")
    return HistoryAcceptancePosture(
        subject=context.subject,
        disposition="accepted",
        reason="accepted_unfinished",
        staging_disposition=context.staging.disposition,
        bridge_identity=bridge_identity,
        manifest_id=context.staging.manifest.manifest_id,
        grant_id=context.staging.grant.grant_id,
        entry_order=context.entry.order,
        observation_key=context.entry.observation_key,
        delivery_identity=context.bridged.identity,
        occurrence=int(result.occurrence),
        finished=False,
        folded=False,
    )


def prior_history_posture(
    history_page: dict[str, object],
    context: AcceptanceContext,
    result: PriorAcknowledgement,
    *,
    bridge_identity: str,
) -> HistoryAcceptancePosture:
    if result.identity != context.bridged.identity:
        raise HistoryAcceptanceError("prior_acknowledgement_correlation_mismatch")
    records = cast("list[dict[str, object]]", history_page["records"])
    folded = any(
        cast("dict[str, object]", item["record"]).get("record") == "FiringCompleted"
        and cast("dict[str, object]", item["record"]).get("occurrence") == result.occurrence
        for item in records
    )
    return HistoryAcceptancePosture(
        subject=context.subject,
        disposition="refused",
        reason="occurrence_already_ended",
        staging_disposition=context.staging.disposition,
        bridge_identity=bridge_identity,
        manifest_id=context.staging.manifest.manifest_id,
        grant_id=context.staging.grant.grant_id,
        entry_order=context.entry.order,
        observation_key=context.entry.observation_key,
        delivery_identity=context.bridged.identity,
        occurrence=result.occurrence,
        finished=True,
        folded=folded,
    )


def scoped_history_posture(
    context: AcceptanceContext,
    result: ScopedDeliveryAcknowledgement,
    *,
    bridge_identity: str,
) -> HistoryAcceptancePosture:
    if result.identity != context.bridged.identity:
        raise HistoryAcceptanceError("scoped_acknowledgement_correlation_mismatch")
    return HistoryAcceptancePosture(
        subject=context.subject,
        disposition="refused",
        reason="unexpected_scoped_acknowledgement",
        staging_disposition=context.staging.disposition,
        bridge_identity=bridge_identity,
        manifest_id=context.staging.manifest.manifest_id,
        grant_id=context.staging.grant.grant_id,
        entry_order=context.entry.order,
        observation_key=context.entry.observation_key,
        delivery_identity=context.bridged.identity,
        occurrence=None,
        finished=False,
        folded=False,
    )


def translate_history_acceptance(
    history_page: dict[str, object],
    context: AcceptanceContext,
    result: AcceptedDelivery | PriorAcknowledgement | ScopedDeliveryAcknowledgement,
    *,
    instance_id: str,
    bridge_identity: str,
) -> HistoryAcceptancePosture:
    if type(result) is AcceptedDelivery:
        return accepted_history_posture(
            context,
            result,
            instance_id=instance_id,
            bridge_identity=bridge_identity,
        )
    if type(result) is PriorAcknowledgement:
        return prior_history_posture(history_page, context, result, bridge_identity=bridge_identity)
    if type(result) is ScopedDeliveryAcknowledgement:
        return scoped_history_posture(context, result, bridge_identity=bridge_identity)
    raise TypeError("Engine.accept_delivery returned an unsupported result")


class ReadinessRuntime:
    """Open one PR lifecycle without exposing its Petrus collaborators."""

    def __init__(
        self,
        *,
        root: ReadinessRoot,
        history_path: Path,
        instance_id: str,
        workflow: BridgedWorkflow,
        dispatch: LocalDispatch,
    ) -> None:
        self._root = root
        self._history_path = history_path
        self._instance_id = instance_id
        self._workflow = workflow
        self._dispatch = dispatch

    def open(self, subject: PullRequestSubject) -> AwaitingObservation:
        self._root.bind(instance_id=self._instance_id, bridge_identity=self._workflow.identity)
        options = {
            "dispatch": self._dispatch,
            "handlers": self._workflow.handlers,
            "guards": self._workflow.guards,
            "activities": self._workflow.activities,
        }
        if self._history_path.is_file():
            engine = load_history_engine(
                self._history_path,
                self._instance_id,
                self._workflow,
                self._dispatch,
            )
        else:
            engine = create_engine(
                path=self._history_path,
                net=self._workflow.net,
                instance=self._instance_id,
                marking=self._workflow.marking,
                **options,
            )
        try:
            bounded_history_page(engine)
            return project_awaiting_observation(
                snapshot=engine.snapshot(),
                subject=subject,
                instance_id=self._instance_id,
            )
        finally:
            engine.close()


class HistoryAcceptanceRuntime:
    """Accept one reconstructed manifest entry without completing its occurrence."""

    def __init__(
        self,
        *,
        root: ReadinessRoot,
        history_path: Path,
        instance_id: str,
        workflow: BridgedWorkflow,
        dispatch: LocalDispatch,
        ingress: IngressCustody,
    ) -> None:
        self._root = root
        self._history_path = history_path
        self._instance_id = instance_id
        self._workflow = workflow
        self._dispatch = dispatch
        self._ingress = ingress

    def accept_staged_observation(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
        subject: PullRequestSubject,
    ) -> HistoryAcceptancePosture:
        self._root.require_bound(instance_id=self._instance_id, bridge_identity=self._workflow.identity)
        staging, entry = reconstruct_staged_authority(
            self._ingress,
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
            subject=subject,
        )
        if staging.disposition != "novel":
            return non_novel_acceptance_posture(
                subject,
                staging,
                entry,
                bridge_identity=self._workflow.identity,
            )
        context = prepare_history_acceptance(subject, staging, entry)
        require_canonical_history(self._history_path, self._instance_id)
        engine = load_history_engine(
            self._history_path,
            self._instance_id,
            self._workflow,
            self._dispatch,
        )
        try:
            history_page = bounded_history_page(engine)
            delivery_identity = str(context.bridged.identity)
            reoffered = history_contains_delivery_identity(history_page, delivery_identity)
            reserved_records = 0 if reoffered else 2
            require_history_record_capacity(history_page, reserved_records=reserved_records)
            require_history_file_capacity(
                self._history_path,
                reserved_bytes=0 if reoffered else MAX_HISTORY_ACCEPTANCE_HEADROOM,
            )
            result = engine.accept_delivery(
                context.bridged.source,
                context.bridged.token,
                identity=delivery_identity,
            )
            return translate_history_acceptance(
                history_page,
                context,
                result,
                instance_id=self._instance_id,
                bridge_identity=self._workflow.identity,
            )
        finally:
            engine.close()


def build_readiness_runtime(
    *,
    root_path: Path,
    dispatch_path: Path,
    instance_id: str,
) -> ReadinessRuntime:
    return ReadinessRuntime(
        root=ReadinessRoot(root_path / "readiness.sqlite3"),
        history_path=root_path / "history.sqlite3",
        instance_id=instance_id,
        workflow=build_workflow(instance_id),
        dispatch=LocalDispatch(dispatch_path, instance=instance_id),
    )


def build_history_acceptance_runtime(
    *,
    root_path: Path,
    dispatch_path: Path,
    ingress_path: Path,
    instance_id: str,
    maximum_manifests: int = MAX_MANIFESTS,
) -> HistoryAcceptanceRuntime:
    return HistoryAcceptanceRuntime(
        root=ReadinessRoot(root_path / "readiness.sqlite3"),
        history_path=root_path / "history.sqlite3",
        instance_id=instance_id,
        workflow=build_workflow(instance_id),
        dispatch=LocalDispatch(dispatch_path, instance=instance_id),
        ingress=IngressCustody.for_reconstruction(
            path=ingress_path,
            maximum_manifests=maximum_manifests,
        ),
    )
