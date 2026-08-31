# Copyright (c) 2026 Henrique Bastos

"""Owner-local deterministic execution of the first bridged lifecycle."""

from __future__ import annotations

from contextlib import closing
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
from pydantic import BaseModel, ConfigDict

from hamsterdan2.readiness.runtime import ReadinessRuntime, build_readiness_runtime, history_record_count
from hamsterdan2.workflow.values import PullRequestSubject


if TYPE_CHECKING:
    from pathlib import Path

    from petrus.testing.dst import ScenarioProfile
    from pydantic import JsonValue


EXPECTED_BRIDGE_IDENTITY = "workflow-bridge/subject-seed-posture@1"
SUBJECT = PullRequestSubject(installation_id=44, repository_id=31, pull_request_number=7)
INSTANCE_ID = "github:44:31:pr:7"


class OpenReadinessCommand(BaseModel):
    """Strict owner-local command for the first readiness cut."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    subject: PullRequestSubject
    action: Literal["open_lifecycle"] = "open_lifecycle"


class ReadinessBinding(BaseModel):
    """Detached readiness-owned root identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    instance_id: str
    bridge_identity: str


class ReadinessState(BaseModel):
    """Detached local observation used by readiness and root checkers."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    binding: ReadinessBinding | None
    history_records: int


OPEN_READINESS_COMMAND = OpenReadinessCommand(subject=SUBJECT)
PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.readiness.ds1",
    version=1,
    digest=digest_json(
        {
            "command": OPEN_READINESS_COMMAND.model_dump(mode="json"),
            "observation": "readiness.state",
            "resources": [
                "pending.motus.tasks",
                "retained.readiness.bindings",
                "retained.readiness.history_records",
                "retained.state.bytes",
                "retained.state.files",
            ],
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="hamsterdan2.readiness.ds1.identity-checker",
    version=1,
    digest=digest_json(
        {
            "empty": "no binding and no History",
            "opened": {
                "instance": INSTANCE_ID,
                "bridge": EXPECTED_BRIDGE_IDENTITY,
                "history_records": "positive",
            },
        }
    ),
)
RESOURCE_LIMITS = {
    "pending.motus.tasks": 0,
    "retained.readiness.bindings": 1,
    "retained.readiness.history_records": 21,
    "retained.state.bytes": 262_144,
    "retained.state.files": 4,
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


def history_records(instance_root: Path) -> int:
    path = instance_root / "history.sqlite3"
    if not path.is_file():
        return 0
    return history_record_count(path, INSTANCE_ID)


def readiness_state(instance_root: Path) -> ReadinessState:
    path = instance_root / "readiness.sqlite3"
    binding = None
    if path.is_file():
        with closing(sqlite3.connect(path)) as connection:
            row = connection.execute(
                "SELECT instance_id, bridge_identity FROM root_binding WHERE singleton = 1"
            ).fetchone()
        if row is not None:
            binding = ReadinessBinding(instance_id=row[0], bridge_identity=row[1])
    return ReadinessState(binding=binding, history_records=history_records(instance_root))


def observe_readiness(root: Path) -> ReadinessState:
    return readiness_state(root / "instance")


def readiness_resource_usage(root: Path) -> ResourceUsage:
    files = [path for path in root.rglob("*") if path.is_file()] if root.exists() else []
    state = observe_readiness(root)
    return ResourceUsage(
        values={
            "pending.motus.tasks": pending_dispatch_tasks(root / "dispatch.sqlite3"),
            "retained.readiness.bindings": 0 if state.binding is None else 1,
            "retained.readiness.history_records": state.history_records,
            "retained.state.bytes": sum(path.stat().st_size for path in files),
            "retained.state.files": len(files),
        }
    )


class ReadinessScenarioProfile:
    """Petrus profile over one real replacement readiness runtime."""

    identity = PROFILE_IDENTITY

    def __init__(self, root: Path) -> None:
        self._root = root

    def validate(self, command: Command) -> Command:
        if command.name != "readiness.open_lifecycle":
            raise ValueError("DS1 readiness accepts only 'readiness.open_lifecycle'")
        parsed = OpenReadinessCommand.model_validate(command.payload, strict=True)
        if parsed != OPEN_READINESS_COMMAND or parsed.model_dump(mode="json") != command.payload:
            raise ValueError("DS1 readiness command must name the exact admitted subject and fields")
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
        del command, context
        posture = generation.open(SUBJECT)
        return ApplyResult(disposition="applied", value=posture.model_dump(mode="json"), scheduled=[])

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
        state = ReadinessState.model_validate(observation.value, strict=True)
        empty = state.binding is None and state.history_records == 0
        opened = state.binding == ReadinessBinding(
            instance_id=INSTANCE_ID,
            bridge_identity=EXPECTED_BRIDGE_IDENTITY,
        ) and (0 < state.history_records <= RESOURCE_LIMITS["retained.readiness.history_records"])
        return CheckResult(
            passed=empty or opened,
            detail={
                "empty": empty,
                "opened": opened,
                "instance_identity": state.binding is None or state.binding.instance_id == INSTANCE_ID,
                "bridge_identity": (state.binding is None or state.binding.bridge_identity == EXPECTED_BRIDGE_IDENTITY),
                "history_records": state.history_records,
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
