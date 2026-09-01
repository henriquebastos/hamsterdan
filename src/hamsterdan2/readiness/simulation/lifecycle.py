# Copyright (c) 2026 Henrique Bastos

"""Owner-local deterministic execution of the first bridged lifecycle."""

from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from typing import TYPE_CHECKING, Literal, cast

from petrus.testing.dst import (
    ApplyResult,
    BudgetV4,
    CheckResult,
    CheckerIdentity,
    Command,
    Fault,
    GenerationStart,
    Observation,
    ObservationRequest,
    ProfileIdentity,
    ReplayResult,
    ResourceUsage,
    ScenarioArtifact,
    ScenarioArtifactV3,
    ScenarioContext,
    ScenarioRegistry,
    World,
    digest_json,
    replay,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from hamsterdan2.readiness.ingress import IngressCustody
from hamsterdan2.readiness.ingress_values import (  # Pydantic resolves at runtime.
    ObservationFoldPosture,
    StagingPosture,
)
from hamsterdan2.readiness.runtime import (
    ReadinessRuntime,
    build_history_acceptance_runtime,
    build_readiness_runtime,
    inspect_history_page,
)
from hamsterdan2.readiness.simulation.ingress import (
    EXPECTED_ACQUISITION,
    EXPECTED_CANONICAL_BYTES,
    EXPECTED_COLLISION_GRANT_DIGEST,
    EXPECTED_COLLISION_GRANT_ID,
    EXPECTED_GRANT_DIGEST,
    EXPECTED_GRANT_ID,
    EXPECTED_KEY,
    EXPECTED_MANIFEST_ID,
    POLICY_REVISION,
    STAGE_ACQUISITION_COMMAND,
    StageAcquisitionCommand,
)
from hamsterdan2.workflow.observations import HeadObservation
from hamsterdan2.workflow.values import PullRequestSubject


if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from petrus.testing.dst import ScenarioProfile


EXPECTED_BRIDGE_IDENTITY = "workflow-bridge/head-seen-history-fold@3"
EXPECTED_HISTORY_DELIVERY_IDENTITY = (
    "history-delivery:v1:sha256:8c3e5786eea3374b8cfb2003d96b9546e89b2b4562524ec649bc2823ae84d151"
)
EXPECTED_HEAD_SEEN_COLOR = "HeadSeen"
OPEN_HISTORY_RECORDS = 21
ACCEPTED_HISTORY_RECORDS = 23
FOLDED_HISTORY_RECORDS = 25
FOLD_TERMINAL_RECORDS = 2
SUBJECT = PullRequestSubject(installation_id=44, repository_id=31, pull_request_number=7)
INSTANCE_ID = "github:44:31:pr:7"
EXPECTED_HEAD_OBSERVATION = HeadObservation.model_validate_json(EXPECTED_CANONICAL_BYTES, strict=True)


class SimulationCapacityError(RuntimeError):
    """A simulation observation crossed its fixed materialization boundary."""


def bounded_state_storage(root: Path, *, maximum_files: int, maximum_bytes: int) -> tuple[int, int]:
    file_count = 0
    retained_bytes = 0
    files = (path for path in root.rglob("*") if path.is_file())
    for path in files:
        file_count += 1
        if file_count > maximum_files:
            raise SimulationCapacityError("state_file_capacity_exceeded", maximum_files)
        retained_bytes += path.stat().st_size
        if retained_bytes > maximum_bytes:
            raise SimulationCapacityError("state_byte_capacity_exceeded", maximum_bytes)
    return file_count, retained_bytes


class OpenReadinessCommand(BaseModel):
    """Strict owner-local command for the first readiness cut."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    subject: PullRequestSubject
    action: Literal["open_lifecycle"] = "open_lifecycle"


class AcceptStagedObservationCommand(BaseModel):
    """Choose one staged acquisition for exact History acceptance."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["accept_staged_observation"] = "accept_staged_observation"


class FoldAcceptedObservationCommand(BaseModel):
    """Complete only the exact unfinished source occurrence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["fold_accepted_observation"] = "fold_accepted_observation"


class ReadinessBinding(BaseModel):
    """Detached readiness-owned root identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    instance_id: str = Field(min_length=1, max_length=128)
    bridge_identity: str = Field(min_length=1, max_length=128)


class HistoryDeliveryFact(BaseModel):
    """Neutral bounded evidence for one unfinished History acceptance."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source: str = Field(min_length=1, max_length=64)
    token_color: str = Field(min_length=1, max_length=64)
    token_payload: dict[str, JsonValue] = Field(max_length=16)
    delivery_identity: str = Field(min_length=1, max_length=128)
    occurrence: int = Field(strict=True, gt=0)
    record_order: tuple[str, ...] = Field(min_length=2, max_length=4)
    produced_place: str | None = Field(default=None, min_length=1, max_length=64)
    produced_entries: tuple[JsonValue, ...] | None = Field(default=None, max_length=0)
    produced_tokens: tuple[HistoryToken, ...] | None = Field(default=None, min_length=1, max_length=1)
    completed_transition: str | None = Field(default=None, min_length=1, max_length=64)
    folded: bool


class HistoryPageRecord(BaseModel):
    """One bounded neutral record from the public Petrus History page."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    position: int = Field(strict=True, ge=0)
    record: dict[str, JsonValue] = Field(max_length=32)


class HistoryToken(BaseModel):
    """The sole bounded token carried by the first accepted delivery."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    color: str = Field(min_length=1, max_length=64)
    data: dict[str, JsonValue] = Field(max_length=16)


class DeliveredHistoryRecord(BaseModel):
    """Strict neutral shape of the first public delivery fact."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record: Literal["ExternalEventDelivered"]
    schema_version: Literal[5] = Field(alias="schema")
    source: str = Field(min_length=1, max_length=64)
    tokens: list[HistoryToken] = Field(min_length=1, max_length=1)
    identity: str = Field(min_length=1, max_length=128)
    occurrence: int = Field(strict=True, gt=0)
    scope: None
    instant: int = Field(strict=True, ge=0)


class BegunHistoryRecord(BaseModel):
    """Strict neutral shape of the matching unfinished occurrence fact."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record: Literal["FiringBegun"]
    schema_version: Literal[5] = Field(alias="schema")
    transition: str = Field(min_length=1, max_length=64)
    occurrence: int = Field(strict=True, gt=0)
    scope: None
    instant: int = Field(strict=True, ge=0)


class TokensProducedHistoryRecord(BaseModel):
    """Strict neutral shape of the exact retained fold output."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record: Literal["TokensProduced"]
    schema_version: Literal[5] = Field(alias="schema")
    place: Literal["life.heads"]
    tokens: list[HistoryToken] = Field(min_length=1, max_length=1)
    entries: list[JsonValue] = Field(max_length=0)
    occurrence: int = Field(strict=True, gt=0)
    scope: None
    instant: int = Field(strict=True, ge=0)


class CompletedHistoryRecord(BaseModel):
    """Strict neutral shape of the exact source terminal fact."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record: Literal["FiringCompleted"]
    schema_version: Literal[5] = Field(alias="schema")
    transition: str = Field(min_length=1, max_length=64)
    occurrence: int = Field(strict=True, gt=0)
    instant: int = Field(strict=True, ge=0)


class ReadinessState(BaseModel):
    """Detached local observation used by readiness and root checkers."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    binding: ReadinessBinding | None
    history_records: int = Field(strict=True, ge=0)
    in_flight_occurrences: int = Field(strict=True, ge=0)
    staging: StagingPosture | None = None
    delivery: HistoryDeliveryFact | None = None
    fold_posture: ObservationFoldPosture | None = None
    accepted: bool = False
    folded: bool = False


OPEN_READINESS_COMMAND = OpenReadinessCommand(subject=SUBJECT)
ACCEPT_STAGED_OBSERVATION_COMMAND = AcceptStagedObservationCommand()
FOLD_ACCEPTED_OBSERVATION_COMMAND = FoldAcceptedObservationCommand()
PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.readiness.ds1",
    version=4,
    digest=digest_json(
        {
            "commands": [
                OPEN_READINESS_COMMAND.model_dump(mode="json"),
                STAGE_ACQUISITION_COMMAND.model_dump(mode="json"),
                ACCEPT_STAGED_OBSERVATION_COMMAND.model_dump(mode="json"),
                FOLD_ACCEPTED_OBSERVATION_COMMAND.model_dump(mode="json"),
            ],
            "observation": "readiness.state",
            "resources": [
                "pending.motus.tasks",
                "retained.readiness.bindings",
                "retained.readiness.history_records",
                "retained.readiness.in_flight_occurrences",
                "retained.state.bytes",
                "retained.state.files",
            ],
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="hamsterdan2.readiness.ds1.identity-checker",
    version=5,
    digest=digest_json(
        {
            "empty": "no binding and no History",
            "opened": {
                "instance": INSTANCE_ID,
                "bridge": EXPECTED_BRIDGE_IDENTITY,
                "history_records": OPEN_HISTORY_RECORDS,
                "in_flight_occurrences": 0,
            },
            "accepted": {
                "source": "on_head",
                "token_color": EXPECTED_HEAD_SEEN_COLOR,
                "token_payload": {
                    "head": "a" * 40,
                    "base": "b" * 40,
                    "mergeable": False,
                    "policy": str(POLICY_REVISION),
                    "strict_base": True,
                    "base_current": False,
                },
                "record_order": ["ExternalEventDelivered", "FiringBegun"],
                "delivery_identity": EXPECTED_HISTORY_DELIVERY_IDENTITY,
                "occurrence": 1,
                "history_records": ACCEPTED_HISTORY_RECORDS,
                "in_flight_occurrences": 1,
                "folded": False,
                "staging": {
                    "manifest_id": EXPECTED_MANIFEST_ID,
                    "grant_id": EXPECTED_GRANT_ID,
                    "entry_order": 0,
                    "observation_key": EXPECTED_KEY,
                    "observation": EXPECTED_HEAD_OBSERVATION.model_dump(mode="json"),
                },
            },
            "folded": {
                "history_records": FOLDED_HISTORY_RECORDS,
                "in_flight_occurrences": 0,
                "record_order": [
                    "ExternalEventDelivered",
                    "FiringBegun",
                    "TokensProduced",
                    "FiringCompleted",
                ],
                "produced_place": "life.heads",
                "phase": "running",
                "local_incarnation": 1,
                "cut": "observation_folded",
            },
        }
    ),
)
RESOURCE_LIMITS = {
    "pending.motus.tasks": 0,
    "retained.readiness.bindings": 1,
    "retained.readiness.history_records": FOLDED_HISTORY_RECORDS,
    "retained.readiness.in_flight_occurrences": 1,
    "retained.state.bytes": 262_144,
    "retained.state.files": 5,
}
DEFAULT_BUDGET = BudgetV4(
    actions=8,
    queued_commands=1,
    timer_advances=0,
    logical_instant=0,
    reloads=2,
    predicate_polls=1,
    artifact_bytes=131_072,
    profile_resources=RESOURCE_LIMITS,
)


def start_readiness(root: Path) -> GenerationStart[ReadinessRuntime]:
    root.mkdir(parents=True, exist_ok=True)
    return GenerationStart(
        build_readiness_runtime(
            root_path=root / "instance",
            dispatch_path=root / "dispatch.sqlite3",
            instance_id=INSTANCE_ID,
        )
    )


def pending_dispatch_tasks(path: Path) -> int:
    if not path.is_file():
        return 0
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute("SELECT COUNT(*) FROM impetus_local_dispatch_tasks").fetchone()
    return cast("int", row[0])


def load_history_records(instance_root: Path, *, dispatch_path: Path) -> tuple[HistoryPageRecord, ...]:
    path = instance_root / "history.sqlite3"
    if not path.is_file():
        return ()
    page = inspect_history_page(path, dispatch_path, INSTANCE_ID)
    records = tuple(
        HistoryPageRecord.model_validate(item, strict=True) for item in cast("list[dict[str, object]]", page["records"])
    )
    if len(records) != cast("int", page["frontier"]):
        raise ValueError("bounded History page does not cover its complete frontier")
    if any(record.position != position for position, record in enumerate(records)):
        raise ValueError("bounded History page positions are not contiguous from zero")
    return records


def history_records(instance_root: Path, *, dispatch_path: Path) -> int:
    return len(load_history_records(instance_root, dispatch_path=dispatch_path))


def required_delivery_pair(
    records: Sequence[HistoryPageRecord],
) -> tuple[int, DeliveredHistoryRecord, BegunHistoryRecord] | None:
    deliveries = tuple(
        (index, item) for index, item in enumerate(records) if item.record.get("record") == "ExternalEventDelivered"
    )
    if not deliveries:
        return None
    if len(deliveries) != 1:
        raise ValueError("DS2 readiness observation admits at most one History delivery")
    index, delivered = deliveries[0]
    begun = next(iter(records[index + 1 : index + 2]), None)
    if begun is None or begun.record.get("record") != "FiringBegun":
        raise TypeError("DS2 readiness History delivery is not followed by FiringBegun")
    return (
        index,
        DeliveredHistoryRecord.model_validate(delivered.record, strict=True),
        BegunHistoryRecord.model_validate(begun.record, strict=True),
    )


def history_delivery_fact(records: Sequence[HistoryPageRecord]) -> HistoryDeliveryFact | None:
    delivery_pair = required_delivery_pair(records)
    if delivery_pair is None:
        return None
    index, delivered, begun = delivery_pair
    if delivered.occurrence != begun.occurrence or delivered.source != begun.transition:
        raise ValueError("DS2 readiness History acceptance correlation is malformed")
    terminal_records = records[index + 2 :]
    if not terminal_records:
        return unfinished_history_delivery_fact(delivered)
    return folded_history_delivery_fact(delivered, terminal_records)


def unfinished_history_delivery_fact(delivered: DeliveredHistoryRecord) -> HistoryDeliveryFact:
    token = delivered.tokens[0]
    return HistoryDeliveryFact(
        source=delivered.source,
        token_color=token.color,
        token_payload=token.data,
        delivery_identity=delivered.identity,
        occurrence=delivered.occurrence,
        record_order=("ExternalEventDelivered", "FiringBegun"),
        folded=False,
    )


def folded_history_delivery_fact(
    delivered: DeliveredHistoryRecord,
    terminal_records: Sequence[HistoryPageRecord],
) -> HistoryDeliveryFact:
    if len(terminal_records) != FOLD_TERMINAL_RECORDS:
        raise ValueError("DS2 readiness History terminal batch has the wrong size")
    produced = TokensProducedHistoryRecord.model_validate(terminal_records[0].record, strict=True)
    completed = CompletedHistoryRecord.model_validate(terminal_records[1].record, strict=True)
    if (
        produced.occurrence != delivered.occurrence
        or completed.occurrence != delivered.occurrence
        or completed.transition != delivered.source
        or produced.tokens != delivered.tokens
    ):
        raise ValueError("DS2 readiness History terminal correlation is malformed")
    token = delivered.tokens[0]
    return HistoryDeliveryFact(
        source=delivered.source,
        token_color=token.color,
        token_payload=token.data,
        delivery_identity=delivered.identity,
        occurrence=delivered.occurrence,
        record_order=(
            "ExternalEventDelivered",
            "FiringBegun",
            "TokensProduced",
            "FiringCompleted",
        ),
        produced_place=produced.place,
        produced_entries=tuple(produced.entries),
        produced_tokens=tuple(produced.tokens),
        completed_transition=completed.transition,
        folded=True,
    )


def history_occurrences(records: Sequence[HistoryPageRecord], names: set[str]) -> set[int]:
    occurrences: set[int] = set()
    for record in records:
        if record.record.get("record") not in names:
            continue
        occurrence = record.record.get("occurrence")
        if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence <= 0:
            raise ValueError("bounded History occurrence is not a positive integer")
        occurrences.add(occurrence)
    return occurrences


def in_flight_occurrence_count(records: Sequence[HistoryPageRecord]) -> int:
    begun = history_occurrences(records, {"FiringBegun"})
    ended = history_occurrences(records, {"FiringCompleted", "FiringFailed"})
    return len(begun - ended)


def staged_posture(path: Path) -> StagingPosture | None:
    if not path.is_file():
        return None
    return IngressCustody.for_reconstruction(path=path).staging_posture(
        provider_route_id=EXPECTED_ACQUISITION.identity.provider_route_id,
        delivery_id=EXPECTED_ACQUISITION.identity.delivery_id,
    )


def readiness_binding(path: Path) -> ReadinessBinding | None:
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            """
            SELECT CASE WHEN typeof(singleton) = 'integer' AND singleton = 1
                        THEN singleton END AS singleton,
                   CASE WHEN typeof(instance_id) = 'text'
                              AND length(CAST(instance_id AS BLOB)) BETWEEN 1 AND 128
                        THEN instance_id END AS instance_id,
                   CASE WHEN typeof(bridge_identity) = 'text'
                              AND length(CAST(bridge_identity AS BLOB)) BETWEEN 1 AND 128
                        THEN bridge_identity END AS bridge_identity
            FROM root_binding
            LIMIT 2
            """
        ).fetchall()
    if len(rows) > 1:
        raise SimulationCapacityError("duplicate_root_binding_observation", 1)
    if not rows:
        return None
    singleton, instance_id, bridge_identity = rows[0]
    if singleton is None or instance_id is None or bridge_identity is None:
        raise SimulationCapacityError("invalid_root_binding_observation")
    return ReadinessBinding(instance_id=instance_id, bridge_identity=bridge_identity)


def readiness_state(
    instance_root: Path,
    *,
    dispatch_path: Path,
    ingress_path: Path | None = None,
) -> ReadinessState:
    records = load_history_records(instance_root, dispatch_path=dispatch_path)
    delivery = history_delivery_fact(records)
    fold_posture = None
    if delivery is not None and delivery.folded:
        if ingress_path is None:
            raise ValueError("folded readiness observation requires its immutable ingress authority")
        projected = build_history_acceptance_runtime(
            root_path=instance_root,
            dispatch_path=dispatch_path,
            ingress_path=ingress_path,
            instance_id=INSTANCE_ID,
        ).verify_folded_observation(
            provider_route_id=EXPECTED_ACQUISITION.identity.provider_route_id,
            delivery_id=EXPECTED_ACQUISITION.identity.delivery_id,
            subject=SUBJECT,
        )
        if not isinstance(projected, ObservationFoldPosture):
            raise ValueError("folded History did not reconstruct its exact detached posture")
        fold_posture = projected
    binding_path = instance_root / "readiness.sqlite3"
    return ReadinessState(
        binding=readiness_binding(binding_path) if binding_path.is_file() else None,
        history_records=len(records),
        in_flight_occurrences=in_flight_occurrence_count(records),
        staging=None if ingress_path is None else staged_posture(ingress_path),
        delivery=delivery,
        fold_posture=fold_posture,
        accepted=delivery is not None,
        folded=False if delivery is None else delivery.folded,
    )


def observe_readiness(root: Path) -> ReadinessState:
    return readiness_state(
        root / "instance",
        dispatch_path=root / "dispatch.sqlite3",
        ingress_path=root / "readiness-ingress.sqlite3",
    )


def readiness_resource_usage(root: Path) -> ResourceUsage:
    file_count, retained_bytes = bounded_state_storage(
        root,
        maximum_files=RESOURCE_LIMITS["retained.state.files"],
        maximum_bytes=RESOURCE_LIMITS["retained.state.bytes"],
    )
    state = observe_readiness(root)
    return ResourceUsage(
        values={
            "pending.motus.tasks": pending_dispatch_tasks(root / "dispatch.sqlite3"),
            "retained.readiness.bindings": 0 if state.binding is None else 1,
            "retained.readiness.history_records": state.history_records,
            "retained.readiness.in_flight_occurrences": state.in_flight_occurrences,
            "retained.state.bytes": retained_bytes,
            "retained.state.files": file_count,
        }
    )


class ReadinessScenarioProfile:
    """Petrus profile over one real replacement readiness runtime."""

    identity = PROFILE_IDENTITY

    def __init__(self, root: Path) -> None:
        self._root = root

    def validate(self, command: Command) -> Command:
        contracts: dict[str, tuple[type[BaseModel], BaseModel]] = {
            "readiness.open_lifecycle": (OpenReadinessCommand, OPEN_READINESS_COMMAND),
            "readiness.stage_acquisition": (StageAcquisitionCommand, STAGE_ACQUISITION_COMMAND),
            "readiness.accept_staged_observation": (
                AcceptStagedObservationCommand,
                ACCEPT_STAGED_OBSERVATION_COMMAND,
            ),
            "readiness.fold_accepted_observation": (
                FoldAcceptedObservationCommand,
                FOLD_ACCEPTED_OBSERVATION_COMMAND,
            ),
        }
        contract = contracts.get(command.name)
        if contract is None:
            raise ValueError("DS2 readiness accepts only open, stage, acceptance, and fold commands")
        model, expected = contract
        parsed = model.model_validate(command.payload, strict=True)
        if parsed != expected or parsed.model_dump(mode="json") != command.payload:
            raise ValueError("DS2 readiness command must contain exactly the admitted fields")
        return command

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"DS1 readiness admits no faults; remove {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[ReadinessRuntime]:
        del context
        return start_readiness(self._root)

    def load(self, context: ScenarioContext) -> GenerationStart[ReadinessRuntime]:
        del context
        return start_readiness(self._root)

    def apply(
        self,
        generation: ReadinessRuntime,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del context
        if command.name == "readiness.stage_acquisition":
            return self.apply_staging()
        if command.name == "readiness.accept_staged_observation":
            return self.apply_acceptance()
        if command.name == "readiness.fold_accepted_observation":
            return self.apply_fold()
        posture = generation.open(SUBJECT)
        return ApplyResult(disposition="applied", value=posture.model_dump(mode="json"), scheduled=[])

    def apply_staging(self) -> ApplyResult:
        posture = IngressCustody.from_path(
            path=self._root / "readiness-ingress.sqlite3",
            policy_revision=POLICY_REVISION,
        ).stage(
            provider_route_id=EXPECTED_ACQUISITION.identity.provider_route_id,
            custody_generation=EXPECTED_ACQUISITION.custody_generation,
            webhook=EXPECTED_ACQUISITION.webhook,
            quarantined=EXPECTED_ACQUISITION.quarantined,
        )
        return ApplyResult(disposition="applied", value=posture.model_dump(mode="json"), scheduled=[])

    def apply_acceptance(self) -> ApplyResult:
        before = history_records(
            self._root / "instance",
            dispatch_path=self._root / "dispatch.sqlite3",
        )
        accepted = build_history_acceptance_runtime(
            root_path=self._root / "instance",
            dispatch_path=self._root / "dispatch.sqlite3",
            ingress_path=self._root / "readiness-ingress.sqlite3",
            instance_id=INSTANCE_ID,
        ).accept_staged_observation(
            provider_route_id=EXPECTED_ACQUISITION.identity.provider_route_id,
            delivery_id=EXPECTED_ACQUISITION.identity.delivery_id,
            subject=SUBJECT,
        )
        after = history_records(
            self._root / "instance",
            dispatch_path=self._root / "dispatch.sqlite3",
        )
        return ApplyResult(
            disposition="idempotent" if after == before else "applied",
            value=accepted.model_dump(mode="json"),
            scheduled=[],
        )

    def apply_fold(self) -> ApplyResult:
        before = history_records(
            self._root / "instance",
            dispatch_path=self._root / "dispatch.sqlite3",
        )
        folded = build_history_acceptance_runtime(
            root_path=self._root / "instance",
            dispatch_path=self._root / "dispatch.sqlite3",
            ingress_path=self._root / "readiness-ingress.sqlite3",
            instance_id=INSTANCE_ID,
        ).fold_accepted_observation(
            provider_route_id=EXPECTED_ACQUISITION.identity.provider_route_id,
            delivery_id=EXPECTED_ACQUISITION.identity.delivery_id,
            subject=SUBJECT,
        )
        if not isinstance(folded, ObservationFoldPosture):
            raise TypeError("the admitted novel staging did not produce a fold posture")
        after = history_records(
            self._root / "instance",
            dispatch_path=self._root / "dispatch.sqlite3",
        )
        return ApplyResult(
            disposition="idempotent" if after == before else "applied",
            value=folded.model_dump(mode="json"),
            scheduled=[],
        )

    def observe(
        self,
        generation: ReadinessRuntime,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del generation, context
        if request.name != "readiness.state" or request.payload != {}:
            raise ValueError("DS1 readiness exposes only the parameterless 'readiness.state' observation")
        return cast("JsonValue", observe_readiness(self._root).model_dump(mode="json"))

    def resource_usage(self, generation: ReadinessRuntime | None) -> ResourceUsage:
        del generation
        return readiness_resource_usage(self._root)

    def drop(self, generation: ReadinessRuntime) -> None:
        del generation

    def close(self, generation: ReadinessRuntime) -> None:
        del generation


class ReadinessChecker:
    """Derive the allowed root binding independently of the production bridge."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="readiness.state", payload={})

    def check(self, observation: Observation) -> CheckResult:
        state = ReadinessState.model_validate_json(json.dumps(observation.value), strict=True)
        empty = (
            state.binding is None
            and state.history_records == 0
            and state.in_flight_occurrences == 0
            and state.staging is None
            and state.delivery is None
            and state.fold_posture is None
            and not state.accepted
            and not state.folded
        )
        opened = state.binding == ReadinessBinding(
            instance_id=INSTANCE_ID,
            bridge_identity=EXPECTED_BRIDGE_IDENTITY,
        ) and state.history_records in (OPEN_HISTORY_RECORDS, ACCEPTED_HISTORY_RECORDS, FOLDED_HISTORY_RECORDS)
        delivery = state.delivery
        staging = state.staging
        entry = None if staging is None or len(staging.manifest.entries) != 1 else staging.manifest.entries[0]
        decision = None if staging is None or len(staging.decisions) != 1 else staging.decisions[0]
        exact_staging = (
            staging is not None
            and staging.disposition == "novel"
            and str(staging.manifest.manifest_id) == EXPECTED_MANIFEST_ID
            and staging.manifest.acquisition == EXPECTED_ACQUISITION.identity
            and staging.manifest.policy_revision == POLICY_REVISION
            and entry is not None
            and entry.order == 0
            and str(entry.observation_key) == EXPECTED_KEY
            and bytes(entry.canonical_bytes) == EXPECTED_CANONICAL_BYTES
            and entry.observation == EXPECTED_HEAD_OBSERVATION
            and str(staging.grant.grant_id) == EXPECTED_GRANT_ID
            and staging.grant.manifest_id == staging.manifest.manifest_id
            and staging.grant.manifest_digest == EXPECTED_GRANT_DIGEST
            and decision is not None
            and decision.entry_order == entry.order
            and decision.observation_key == entry.observation_key
            and decision.disposition == "novel"
            and decision.reason == "first_observation"
            and not decision.fatal
            and not decision.refresh_required
        )
        exact_collision = (
            staging is not None
            and staging.disposition == "acquisition_collision"
            and str(staging.manifest.manifest_id) == EXPECTED_MANIFEST_ID
            and staging.manifest.acquisition == EXPECTED_ACQUISITION.identity
            and staging.manifest.policy_revision == POLICY_REVISION
            and staging.manifest.entries == ()
            and str(staging.grant.grant_id) == EXPECTED_COLLISION_GRANT_ID
            and staging.grant.manifest_id == staging.manifest.manifest_id
            and staging.grant.manifest_digest == EXPECTED_COLLISION_GRANT_DIGEST
            and decision is not None
            and decision.entry_order is None
            and decision.observation_key is None
            and decision.disposition == "acquisition_collision"
            and decision.reason == "quarantined_acquisition"
            and decision.fatal
            and not decision.refresh_required
        )
        known_staging = exact_staging or exact_collision
        staging_authority = (state.staging is None and not state.accepted) or known_staging
        expected_delivery = (
            delivery is not None
            and delivery.source == "on_head"
            and delivery.token_color == EXPECTED_HEAD_SEEN_COLOR
            and delivery.token_payload
            == {
                "head": "a" * 40,
                "base": "b" * 40,
                "mergeable": False,
                "policy": str(POLICY_REVISION),
                "strict_base": True,
                "base_current": False,
            }
            and delivery.delivery_identity == EXPECTED_HISTORY_DELIVERY_IDENTITY
            and delivery.occurrence == 1
            and delivery.record_order == ("ExternalEventDelivered", "FiringBegun")
            and delivery.produced_place is None
            and delivery.produced_entries is None
            and delivery.produced_tokens is None
            and delivery.completed_transition is None
            and not delivery.folded
        )
        accepted = (
            opened
            and exact_staging
            and state.history_records == ACCEPTED_HISTORY_RECORDS
            and state.in_flight_occurrences == 1
            and state.accepted
            and not state.folded
            and expected_delivery
            and state.fold_posture is None
        )
        fold_posture = state.fold_posture
        expected_fold_posture = (
            fold_posture is not None
            and fold_posture.subject == SUBJECT
            and fold_posture.instance_id == INSTANCE_ID
            and fold_posture.bridge_identity == EXPECTED_BRIDGE_IDENTITY
            and str(fold_posture.manifest_id) == EXPECTED_MANIFEST_ID
            and str(fold_posture.grant_id) == EXPECTED_GRANT_ID
            and fold_posture.manifest_digest == EXPECTED_GRANT_DIGEST
            and fold_posture.entry_order == 0
            and str(fold_posture.observation_key) == EXPECTED_KEY
            and str(fold_posture.delivery_identity) == EXPECTED_HISTORY_DELIVERY_IDENTITY
            and fold_posture.occurrence == 1
            and fold_posture.phase == "running"
            and fold_posture.local_incarnation == 1
            and fold_posture.head == EXPECTED_HEAD_OBSERVATION.head
            and fold_posture.base == EXPECTED_HEAD_OBSERVATION.base
            and not fold_posture.mergeable
            and fold_posture.policy_revision == POLICY_REVISION
            and fold_posture.strict_base
            and not fold_posture.base_current
            and fold_posture.finished
            and fold_posture.folded
            and fold_posture.cut == "observation_folded"
        )
        folded_delivery = (
            delivery is not None
            and delivery.source == "on_head"
            and delivery.token_color == EXPECTED_HEAD_SEEN_COLOR
            and delivery.token_payload
            == {
                "head": "a" * 40,
                "base": "b" * 40,
                "mergeable": False,
                "policy": str(POLICY_REVISION),
                "strict_base": True,
                "base_current": False,
            }
            and delivery.delivery_identity == EXPECTED_HISTORY_DELIVERY_IDENTITY
            and delivery.occurrence == 1
            and delivery.record_order == ("ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted")
            and delivery.produced_place == "life.heads"
            and delivery.produced_entries == ()
            and delivery.produced_tokens == (HistoryToken(color=EXPECTED_HEAD_SEEN_COLOR, data=delivery.token_payload),)
            and delivery.completed_transition == "on_head"
            and delivery.folded
        )
        folded = (
            opened
            and exact_staging
            and state.history_records == FOLDED_HISTORY_RECORDS
            and state.in_flight_occurrences == 0
            and state.accepted
            and state.folded
            and folded_delivery
            and expected_fold_posture
        )
        plain_opened = (
            opened
            and state.history_records == OPEN_HISTORY_RECORDS
            and state.in_flight_occurrences == 0
            and state.staging is None
            and state.delivery is None
            and state.fold_posture is None
            and not state.accepted
            and not state.folded
        )
        staged = (
            opened
            and state.history_records == OPEN_HISTORY_RECORDS
            and state.in_flight_occurrences == 0
            and known_staging
            and state.delivery is None
            and state.fold_posture is None
            and not state.accepted
            and not state.folded
        )
        staged_without_lifecycle = (
            state.binding is None
            and state.history_records == 0
            and state.in_flight_occurrences == 0
            and known_staging
            and state.delivery is None
            and state.fold_posture is None
            and not state.accepted
            and not state.folded
        )
        return CheckResult(
            passed=empty or plain_opened or staged_without_lifecycle or staged or accepted or folded,
            detail={
                "empty": empty,
                "opened": opened,
                "plain_opened": plain_opened,
                "staged_without_lifecycle": staged_without_lifecycle,
                "staged": staged,
                "accepted": accepted,
                "folded_posture": folded,
                "instance_identity": state.binding is None or state.binding.instance_id == INSTANCE_ID,
                "bridge_identity": (state.binding is None or state.binding.bridge_identity == EXPECTED_BRIDGE_IDENTITY),
                "history_records": state.history_records,
                "in_flight_occurrences": state.in_flight_occurrences in (0, 1),
                "history_delivery": expected_delivery,
                "history_fold": folded_delivery,
                "fold_projection": expected_fold_posture,
                "staging_authority": staging_authority,
                "manifest": state.staging is None or str(state.staging.manifest.manifest_id) == EXPECTED_MANIFEST_ID,
                "grant": state.staging is None
                or str(state.staging.grant.grant_id) in (EXPECTED_GRANT_ID, EXPECTED_COLLISION_GRANT_ID),
                "entry_order": entry is None or entry.order == 0,
                "observation_key": entry is None or str(entry.observation_key) == EXPECTED_KEY,
                "delivery_identity": delivery is None
                or delivery.delivery_identity == EXPECTED_HISTORY_DELIVERY_IDENTITY,
                "occurrence": delivery is None or delivery.occurrence == 1,
                "folded": state.folded,
            },
        )


def build_readiness_world(*, root: Path, budget: BudgetV4 = DEFAULT_BUDGET) -> World:
    profile = cast("ScenarioProfile[object]", ReadinessScenarioProfile(root))
    return World(profile, budget, checkers=(ReadinessChecker(),))


def replay_readiness(artifact: ScenarioArtifactV3 | ScenarioArtifact, *, root: Path) -> ReplayResult:
    if not isinstance(artifact, ScenarioArtifact):
        raise TypeError("DS1 readiness replay requires a version-4 resource artifact")
    registry = ScenarioRegistry()
    registry.register_profile(ReadinessScenarioProfile(root))
    registry.register_checker(ReadinessChecker())
    return cast("ReplayResult", replay(artifact, registry))
