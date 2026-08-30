# Copyright (c) 2026 Henrique Bastos

"""Fresh-process death and reconstruction evidence around the first host cut."""

from __future__ import annotations

from functools import partial
import os
from pathlib import Path
import signal
import socket
from typing import TYPE_CHECKING, Never, cast

from petrus.testing.dst import (
    Disposition,
    GenerationStart,
    ObservationRequest,
    ProcessSession,
    ProfileIdentity,
    ResourceUsage,
    ScenarioArtifact,
    digest_json,
)
from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from hamsterdan2.host.catalog import HostCatalog
from hamsterdan2.host.composition import open_readiness
from hamsterdan2.simulation.hamsterdan import (
    DEFAULT_BUDGET,
    OPEN_PULL_REQUEST_COMMAND,
    HamsterdanChecker,
    HamsterdanScenarioProfile,
    observe_hamsterdan,
    root_resource_usage,
    validate_open_pull_request,
)


if TYPE_CHECKING:
    from collections.abc import Callable

    from petrus.testing.dst import ApplyResult, Command, Fault, ScenarioContext
    from pydantic import JsonValue

    from hamsterdan2.host.values import RegisteredPullRequest
    from hamsterdan2.workflow.values import AwaitingObservation


BEFORE_DEATH_SCENARIO = "ds1.process.before-host-recorded.death"
BEFORE_RECOVERY_SCENARIO = "ds1.process.before-host-recorded.recovery"
AFTER_DEATH_SCENARIO = "ds1.process.after-host-recorded.death"
AFTER_RECOVERY_SCENARIO = "ds1.process.after-host-recorded.recovery"
LOCK_HOLDER_SCENARIO = "ds1.process.before-host-recorded.lock-holder"
BEFORE_PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.ds1.before-host-recorded-process",
    version=1,
    digest=digest_json(
        {
            "command": OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            "death_cut": "readiness durable, host record uncommitted",
        }
    ),
)
LOCK_HOLDER_PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.ds1.before-host-recorded-lock-holder",
    version=1,
    digest=digest_json(
        {
            "command": OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
            "hold_cut": "readiness durable, host record uncommitted",
        }
    ),
)


class StateRootPayload(BaseModel):
    """Strict detached location passed into a fresh process."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state_root: str

    @field_validator("state_root")
    @classmethod
    def absolute_path(cls, value: str) -> str:
        if not value or not Path(value).is_absolute():
            raise ValueError("state_root must be a non-empty absolute path")
        return value


class LockHolderPayload(BaseModel):
    """Strict process location plus its local synchronization socket."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state_root: str
    ready_socket: str

    @field_validator("state_root", "ready_socket")
    @classmethod
    def absolute_process_path(cls, value: str, info: ValidationInfo) -> str:
        if not value or not Path(value).is_absolute():
            raise ValueError(f"{info.field_name} must be a non-empty absolute path")
        return value


def state_root(payload: JsonValue) -> Path:
    parsed = StateRootPayload.model_validate(payload, strict=True)
    if parsed.model_dump(mode="json") != payload:
        raise ValueError("process payload must contain exactly the admitted state_root")
    return Path(parsed.state_root)


def terminate_child() -> Never:
    os.kill(os.getpid(), signal.SIGKILL)
    raise AssertionError("SIGKILL unexpectedly returned")


def open_readiness_then_die(
    registered: RegisteredPullRequest,
    *,
    root: Path,
) -> AwaitingObservation:
    open_readiness(
        registered,
        state_root=root,
        dispatch_path=root / "dispatch.sqlite3",
    )
    terminate_child()


def open_readiness_then_hold(
    registered: RegisteredPullRequest,
    *,
    root: Path,
    ready_socket: Path,
) -> AwaitingObservation:
    open_readiness(
        registered,
        state_root=root,
        dispatch_path=root / "dispatch.sqlite3",
    )
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as notification:
        notification.connect(str(ready_socket))
        notification.sendall(b"readiness-opened")
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.pause()
    raise AssertionError("the lock holder unexpectedly resumed")


class BeforeHostRecordedProfile:
    """Use real host custody while dying after readiness and before its host record."""

    def __init__(
        self,
        root: Path,
        *,
        identity: ProfileIdentity,
        readiness_action: Callable[[RegisteredPullRequest], AwaitingObservation],
    ) -> None:
        self._root = root
        self.identity = identity
        self._readiness_action = readiness_action

    def validate(self, command: Command) -> Command:
        return validate_open_pull_request(command)

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"DS1 process death admits no World faults; remove {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[HostCatalog]:
        del context
        return GenerationStart(HostCatalog.from_path(self._root / "catalog.sqlite3"))

    def load(self, context: ScenarioContext) -> GenerationStart[HostCatalog]:
        return self.create(context)

    def apply(
        self,
        generation: HostCatalog,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del command, context
        generation.register(OPEN_PULL_REQUEST_COMMAND)
        generation.step(
            OPEN_PULL_REQUEST_COMMAND,
            self._readiness_action,
        )
        raise AssertionError("the before-host-recorded death cut returned")

    def observe(
        self,
        generation: HostCatalog,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del generation, context
        if request.name != "hamsterdan.state" or request.payload != {}:
            raise ValueError("DS1 root exposes only the parameterless 'hamsterdan.state' observation")
        return cast("JsonValue", observe_hamsterdan(self._root).model_dump(mode="json"))

    def resource_usage(self, generation: HostCatalog | None) -> ResourceUsage:
        del generation
        return root_resource_usage(self._root)

    def drop(self, generation: HostCatalog) -> None:
        del generation

    def close(self, generation: HostCatalog) -> None:
        del generation


def die_before_host_recorded(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    root = state_root(payload)
    world = session.world(
        BeforeHostRecordedProfile(
            root,
            identity=BEFORE_PROFILE_IDENTITY,
            readiness_action=partial(open_readiness_then_die, root=root),
        ),
        DEFAULT_BUDGET,
        checkers=(HamsterdanChecker(),),
    )
    world.timeline().command(
        "hamsterdan.open_pull_request",
        OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
    )
    raise AssertionError("the before-host-recorded process survived")


def hold_before_host_recorded(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    parsed = LockHolderPayload.model_validate(payload, strict=True)
    root = Path(parsed.state_root)
    world = session.world(
        BeforeHostRecordedProfile(
            root,
            identity=LOCK_HOLDER_PROFILE_IDENTITY,
            readiness_action=partial(
                open_readiness_then_hold,
                root=root,
                ready_socket=Path(parsed.ready_socket),
            ),
        ),
        DEFAULT_BUDGET,
        checkers=(HamsterdanChecker(),),
    )
    world.timeline().command(
        "hamsterdan.open_pull_request",
        OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
    )
    raise AssertionError("the before-host-recorded lock holder returned")


def die_after_host_recorded(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    root = state_root(payload)
    world = session.world(
        HamsterdanScenarioProfile(root),
        DEFAULT_BUDGET,
        checkers=(HamsterdanChecker(),),
    )
    world.timeline().command(
        "hamsterdan.open_pull_request",
        OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
    )
    terminate_child()


def execute_recovery(
    session: ProcessSession,
    payload: JsonValue,
    *,
    scenario_id: str,
) -> ScenarioArtifact:
    root = state_root(payload)
    world = session.world(
        HamsterdanScenarioProfile(root),
        DEFAULT_BUDGET,
        checkers=(HamsterdanChecker(),),
    )
    world.timeline().command(
        "hamsterdan.open_pull_request",
        OPEN_PULL_REQUEST_COMMAND.model_dump(mode="json"),
    )
    world.timeline().finish(Disposition.QUIESCENT)
    artifact = world.artifact(scenario_id)
    if not isinstance(artifact, ScenarioArtifact):
        raise TypeError("DS1 process recovery requires a version-4 resource artifact")
    return artifact


def recover_before_host_recorded(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    return execute_recovery(
        session,
        payload,
        scenario_id=BEFORE_RECOVERY_SCENARIO,
    )


def recover_after_host_recorded(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    return execute_recovery(
        session,
        payload,
        scenario_id=AFTER_RECOVERY_SCENARIO,
    )
