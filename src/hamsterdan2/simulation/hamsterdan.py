# Copyright (c) 2026 Henrique Bastos

"""Root deterministic execution of the first bridged Hamsterdan lifecycle."""

from __future__ import annotations

from contextlib import closing
import sqlite3
from typing import TYPE_CHECKING, cast

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
from pydantic import BaseModel, ConfigDict

from hamsterdan2.host.composition import build_hamsterdan
from hamsterdan2.host.values import ActionIdentity, HostRecord, OpenPullRequestCommand, RegisteredPullRequest
from hamsterdan2.readiness.simulation.lifecycle import (
    EXPECTED_BRIDGE_IDENTITY,
    INSTANCE_ID,
    SUBJECT,
    ReadinessChecker,
    ReadinessState,
    pending_dispatch_tasks,
    readiness_state,
)
from hamsterdan2.readiness.simulation.lifecycle import (
    RESOURCE_LIMITS as READINESS_RESOURCE_LIMITS,
)
from hamsterdan2.workflow.values import AwaitingObservation, PullRequestSubject


if TYPE_CHECKING:
    from pathlib import Path

    from petrus.testing.dst import ScenarioProfile
    from pydantic import JsonValue

    from hamsterdan2.host.application import Hamsterdan


OPEN_PULL_REQUEST_COMMAND = OpenPullRequestCommand(
    action_identity=ActionIdentity("trace:open:1"),
    subject=SUBJECT,
)
EXPECTED_REGISTRATION = RegisteredPullRequest(
    subject=SUBJECT,
    instance_id=INSTANCE_ID,
    readiness_root="instances/44/31/7",
)
EXPECTED_RECORD = HostRecord(
    action_identity=OPEN_PULL_REQUEST_COMMAND.action_identity,
    posture=AwaitingObservation(subject=SUBJECT),
)


class HostState(BaseModel):
    """Detached host-catalog observation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    subjects: list[RegisteredPullRequest]
    records: list[HostRecord]


class HamsterdanState(BaseModel):
    """Detached cross-owner observation for the first root tracer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    host: HostState
    readiness: ReadinessState


PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.ds1",
    version=1,
    digest=digest_json(
        {
            "command": OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            "observation": "hamsterdan.state",
            "cut": "host_recorded",
            "owners": ["host", "readiness", "workflow_bridge"],
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="hamsterdan2.ds1.root-checker",
    version=1,
    digest=digest_json(
        {
            "subject": SUBJECT.model_dump(mode="json"),
            "action_identity": str(OPEN_PULL_REQUEST_COMMAND.action_identity),
            "instance_identity": INSTANCE_ID,
            "bridge_identity": EXPECTED_BRIDGE_IDENTITY,
            "phases": ["empty", "registered", "readiness_durable", "host_recorded"],
            "relationships": "every retained phase identifies one PR",
        }
    ),
)
RESOURCE_LIMITS = {
    "pending.motus.tasks": 0,
    "retained.host.records": 1,
    "retained.host.subjects": 1,
    "retained.readiness.history_records": READINESS_RESOURCE_LIMITS["retained.readiness.history_records"],
    "retained.state.bytes": 393_216,
    "retained.state.files": 5,
}
DEFAULT_BUDGET = BudgetV4(
    actions=12,
    queued_commands=1,
    timer_advances=0,
    logical_instant=0,
    reloads=2,
    predicate_polls=1,
    artifact_bytes=262_144,
    profile_resources=RESOURCE_LIMITS,
)


def start_hamsterdan(root: Path) -> GenerationStart[Hamsterdan]:
    return GenerationStart(build_hamsterdan(state_root=root))


def host_state(root: Path) -> HostState:
    path = root / "catalog.sqlite3"
    if not path.is_file():
        return HostState(subjects=[], records=[])
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        subject_rows = connection.execute(
            """
            SELECT installation_id, repository_id, pull_request_number, instance_id, readiness_root
            FROM subject_roots
            ORDER BY installation_id, repository_id, pull_request_number
            """
        ).fetchall()
        record_rows = connection.execute(
            """
            SELECT action_identity, installation_id, repository_id, pull_request_number, action, posture, cut
            FROM host_records
            ORDER BY action_identity
            """
        ).fetchall()
    subjects = [
        RegisteredPullRequest(
            subject=PullRequestSubject(
                installation_id=row["installation_id"],
                repository_id=row["repository_id"],
                pull_request_number=row["pull_request_number"],
            ),
            instance_id=row["instance_id"],
            readiness_root=row["readiness_root"],
        )
        for row in subject_rows
    ]
    records = [
        HostRecord(
            action_identity=ActionIdentity(row["action_identity"]),
            action=row["action"],
            posture=AwaitingObservation(
                subject=PullRequestSubject(
                    installation_id=row["installation_id"],
                    repository_id=row["repository_id"],
                    pull_request_number=row["pull_request_number"],
                ),
                posture=row["posture"],
            ),
            cut=row["cut"],
        )
        for row in record_rows
    ]
    return HostState(subjects=subjects, records=records)


def observe_hamsterdan(root: Path) -> HamsterdanState:
    return HamsterdanState(
        host=host_state(root),
        readiness=readiness_state(root / EXPECTED_REGISTRATION.readiness_root),
    )


def action_was_recorded(root: Path, action_identity: ActionIdentity) -> bool:
    path = root / "catalog.sqlite3"
    if not path.is_file():
        return False
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            "SELECT 1 FROM host_records WHERE action_identity = ?",
            (action_identity,),
        ).fetchone()
    return row is not None


def root_resource_usage(root: Path) -> ResourceUsage:
    files = [path for path in root.rglob("*") if path.is_file()] if root.exists() else []
    readiness_root = root / EXPECTED_REGISTRATION.readiness_root
    state = readiness_state(readiness_root)
    return ResourceUsage(
        values={
            "pending.motus.tasks": pending_dispatch_tasks(root / "dispatch.sqlite3"),
            "retained.host.records": len(host_state(root).records),
            "retained.host.subjects": len(host_state(root).subjects),
            "retained.readiness.history_records": state.history_records,
            "retained.state.bytes": sum(path.stat().st_size for path in files),
            "retained.state.files": len(files),
        }
    )


def validate_open_pull_request(command: Command) -> Command:
    if command.name != "hamsterdan.open_pull_request":
        raise ValueError("DS1 root accepts only 'hamsterdan.open_pull_request'")
    parsed = OpenPullRequestCommand.model_validate(command.payload, strict=True)
    if parsed != OPEN_PULL_REQUEST_COMMAND or parsed.model_dump(mode="json") != command.payload:
        raise ValueError("DS1 root command must name the exact admitted action, subject, and fields")
    return command


class HamsterdanScenarioProfile:
    """Petrus profile over the real replacement host composition."""

    identity = PROFILE_IDENTITY

    def __init__(self, root: Path) -> None:
        self._root = root

    def validate(self, command: Command) -> Command:
        return validate_open_pull_request(command)

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"DS1 root admits no faults; remove {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[Hamsterdan]:
        del context
        return start_hamsterdan(self._root)

    def load(self, context: ScenarioContext) -> GenerationStart[Hamsterdan]:
        del context
        return start_hamsterdan(self._root)

    def apply(
        self,
        generation: Hamsterdan,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del command, context
        replayed = action_was_recorded(self._root, OPEN_PULL_REQUEST_COMMAND.action_identity)
        record = generation.open_pull_request(OPEN_PULL_REQUEST_COMMAND)
        return ApplyResult(
            disposition="idempotent" if replayed else "applied",
            value=record.model_dump(mode="json"),
            scheduled=[],
        )

    def observe(
        self,
        generation: Hamsterdan,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del generation, context
        if request.name != "hamsterdan.state" or request.payload != {}:
            raise ValueError("DS1 root exposes only the parameterless 'hamsterdan.state' observation")
        return cast("JsonValue", observe_hamsterdan(self._root).model_dump(mode="json"))

    def resource_usage(self, generation: Hamsterdan | None) -> ResourceUsage:
        del generation
        return root_resource_usage(self._root)

    def drop(self, generation: Hamsterdan) -> None:
        del generation

    def close(self, generation: Hamsterdan) -> None:
        del generation


class HamsterdanChecker:
    """Check cross-owner identity without decoding Petrus runtime state."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="hamsterdan.state", payload={})

    def check(self, observation: Observation) -> CheckResult:
        state = HamsterdanState.model_validate(observation.value, strict=True)
        empty = state == HamsterdanState(
            host=HostState(subjects=[], records=[]),
            readiness=ReadinessState(binding=None, history_records=0),
        )
        subject_binding = state.host.subjects in ([], [EXPECTED_REGISTRATION])
        action_identity = state.host.records in ([], [EXPECTED_RECORD])
        readiness_result = ReadinessChecker().check(
            Observation(
                name="readiness.state",
                value=state.readiness.model_dump(mode="json"),
                instant=observation.instant,
                generation=observation.generation,
                sequence=observation.sequence,
            )
        )
        registered = state.host == HostState(
            subjects=[EXPECTED_REGISTRATION], records=[]
        ) and state.readiness == ReadinessState(binding=None, history_records=0)
        readiness_durable = (
            state.host == HostState(subjects=[EXPECTED_REGISTRATION], records=[])
            and state.readiness.binding is not None
            and state.readiness.history_records > 0
        )
        opened = (
            state.host == HostState(subjects=[EXPECTED_REGISTRATION], records=[EXPECTED_RECORD])
            and state.readiness.binding is not None
            and state.readiness.history_records > 0
        )
        return CheckResult(
            passed=(empty or registered or readiness_durable or opened)
            and subject_binding
            and action_identity
            and readiness_result.passed,
            detail={
                "empty": empty,
                "registered": registered,
                "readiness_durable": readiness_durable,
                "opened": opened,
                "subject_binding": subject_binding,
                "action_identity": action_identity,
                "readiness": readiness_result.passed,
            },
        )


def build_hamsterdan_world(*, root: Path, budget: BudgetV4 = DEFAULT_BUDGET) -> World:
    profile = cast("ScenarioProfile[object]", HamsterdanScenarioProfile(root))
    return World(profile, budget, checkers=(HamsterdanChecker(),))


def replay_hamsterdan(artifact: ScenarioArtifactV3 | ScenarioArtifact, *, root: Path) -> ReplayResult:
    if not isinstance(artifact, ScenarioArtifact):
        raise TypeError("DS1 root replay requires a version-4 resource artifact")
    registry = ScenarioRegistry()
    registry.register_profile(HamsterdanScenarioProfile(root))
    registry.register_checker(HamsterdanChecker())
    return cast("ReplayResult", replay(artifact, registry))
