# Copyright (c) 2026 Henrique Bastos

"""Fresh-process death and reconstruction evidence around the first host cut."""

from __future__ import annotations

import asyncio
from functools import partial
import json
import os
from pathlib import Path
import signal
import socket
from typing import TYPE_CHECKING, Never, cast

from petrus.testing.dst import (
    ApplyResult,
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
from starlette import status

from hamsterdan2.github_app.simulation.webhooks import (
    WEBHOOK_SIGNING_MATERIAL,
    signed_webhook_body,
    signed_webhook_headers,
)
from hamsterdan2.host.catalog import HostCatalog
from hamsterdan2.host.composition import build_staging_authority, build_webhook_app, open_readiness
from hamsterdan2.host.values import DeliveryReceipt
from hamsterdan2.simulation.hamsterdan import (
    DEFAULT_BUDGET,
    OPEN_PULL_REQUEST_COMMAND,
    PROVIDER_ROUTE,
    RECEIVE_WEBHOOK_COMMAND,
    STAGE_WEBHOOK_COMMAND,
    STAGING_POLICY_REVISION,
    HamsterdanChecker,
    HamsterdanScenarioProfile,
    observe_hamsterdan,
    root_resource_usage,
    validate_open_pull_request,
    validate_receive_webhook,
    validate_stage_webhook,
)


if TYPE_CHECKING:
    from collections.abc import Callable

    from petrus.testing.dst import Command, Fault, ScenarioContext
    from pydantic import JsonValue
    from starlette.types import ASGIApp, Message, Scope

    from hamsterdan2.host.application import StagingAuthority
    from hamsterdan2.host.values import RegisteredPullRequest
    from hamsterdan2.workflow.values import AwaitingObservation


BEFORE_DEATH_SCENARIO = "ds1.process.before-host-recorded.death"
BEFORE_RECOVERY_SCENARIO = "ds1.process.before-host-recorded.recovery"
AFTER_DEATH_SCENARIO = "ds1.process.after-host-recorded.death"
AFTER_RECOVERY_SCENARIO = "ds1.process.after-host-recorded.recovery"
LOCK_HOLDER_SCENARIO = "ds1.process.before-host-recorded.lock-holder"
CUSTODY_DEATH_SCENARIO = "ds2.process.after-delivery-custodied.death"
CUSTODY_RECOVERY_SCENARIO = "ds2.process.after-delivery-custodied.recovery"
STAGING_DEATH_SCENARIO = "ds2.process.after-staging-durable.death"
STAGING_RECOVERY_SCENARIO = "ds2.process.after-staging-durable.recovery"
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
CUSTODY_DEATH_PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.ds2.after-delivery-custodied-process",
    version=1,
    digest=digest_json(
        {
            "command": RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            "death_cut": "delivery committed, HTTP acknowledgement absent",
        }
    ),
)
CUSTODY_RECOVERY_PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.ds2.delivery-custody-recovery-process",
    version=1,
    digest=digest_json(
        {
            "command": RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
            "recovery": "fresh process classifies the signed redelivery",
        }
    ),
)
STAGING_DEATH_PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.ds2.after-staging-durable-process",
    version=1,
    digest=digest_json(
        {
            "command": STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            "death_cut": "manifest, grant, entry, and decision committed; caller acknowledgement absent",
        }
    ),
)
STAGING_RECOVERY_PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.ds2.staging-custody-recovery-process",
    version=1,
    digest=digest_json(
        {
            "command": STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
            "recovery": "fresh authority reconstructs and exactly reoffers staging",
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


class DeliveryCustodyProcessProfile:
    """Drive the real ASGI app around its pre-acknowledgement cut."""

    def __init__(
        self,
        root: Path,
        *,
        identity: ProfileIdentity,
        terminate_before_response: bool,
    ) -> None:
        self._root = root
        self.identity = identity
        self._terminate_before_response = terminate_before_response

    def validate(self, command: Command) -> Command:
        return validate_receive_webhook(command)

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"DS2 custody process admits no World faults; remove {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[ASGIApp]:
        del context
        return GenerationStart(
            build_webhook_app(
                state_root=self._root,
                webhook_secret=WEBHOOK_SIGNING_MATERIAL,
                provider_routes=(PROVIDER_ROUTE,),
            )
        )

    def load(self, context: ScenarioContext) -> GenerationStart[ASGIApp]:
        return self.create(context)

    def apply(
        self,
        generation: ASGIApp,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del command, context
        receipt = asyncio.run(
            execute_webhook_request(
                generation,
                terminate_before_response=self._terminate_before_response,
            )
        )
        return ApplyResult(
            disposition="idempotent" if receipt.disposition == "exact_duplicate" else "applied",
            value=receipt.model_dump(mode="json"),
            scheduled=[],
        )

    def observe(
        self,
        generation: ASGIApp,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del generation, context
        if request.name != "hamsterdan.state" or request.payload != {}:
            raise ValueError("CV21 root exposes only the parameterless 'hamsterdan.state' observation")
        return cast("JsonValue", observe_hamsterdan(self._root).model_dump(mode="json"))

    def resource_usage(self, generation: ASGIApp | None) -> ResourceUsage:
        del generation
        return root_resource_usage(self._root)

    def drop(self, generation: ASGIApp) -> None:
        del generation

    def close(self, generation: ASGIApp) -> None:
        del generation


class StagingCustodyProcessProfile:
    """Drive the host-composed staging authority around caller acknowledgement loss."""

    def __init__(
        self,
        root: Path,
        *,
        identity: ProfileIdentity,
        terminate_after_staging: bool,
    ) -> None:
        self._root = root
        self.identity = identity
        self._terminate_after_staging = terminate_after_staging

    def validate(self, command: Command) -> Command:
        return validate_stage_webhook(command)

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"DS2 staging process admits no World faults; remove {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[StagingAuthority]:
        del context
        return GenerationStart(
            build_staging_authority(
                state_root=self._root,
                provider_routes=(PROVIDER_ROUTE,),
                policy_revision=STAGING_POLICY_REVISION,
            )
        )

    def load(self, context: ScenarioContext) -> GenerationStart[StagingAuthority]:
        return self.create(context)

    def apply(
        self,
        generation: StagingAuthority,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del command, context
        posture = generation.stage_delivery(
            provider_route_id=STAGE_WEBHOOK_COMMAND.provider_route_id,
            delivery_id=STAGE_WEBHOOK_COMMAND.delivery_id,
        )
        if self._terminate_after_staging:
            terminate_child()
        return ApplyResult(
            disposition="idempotent" if posture.disposition == "exact_duplicate" else "applied",
            value=posture.model_dump(mode="json"),
            scheduled=[],
        )

    def observe(
        self,
        generation: StagingAuthority,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del generation, context
        if request.name != "hamsterdan.state" or request.payload != {}:
            raise ValueError("CV21 root exposes only the parameterless 'hamsterdan.state' observation")
        return cast("JsonValue", observe_hamsterdan(self._root).model_dump(mode="json"))

    def resource_usage(self, generation: StagingAuthority | None) -> ResourceUsage:
        del generation
        return root_resource_usage(self._root)

    def drop(self, generation: StagingAuthority) -> None:
        del generation

    def close(self, generation: StagingAuthority) -> None:
        del generation


async def execute_webhook_request(
    app: ASGIApp,
    *,
    terminate_before_response: bool,
) -> DeliveryReceipt:
    body = signed_webhook_body()
    request_messages: list[Message] = [
        {"type": "http.request", "body": body, "more_body": False},
        {"type": "http.disconnect"},
    ]
    response_messages: list[Message] = []
    scope = cast(
        "Scope",
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/github/webhooks",
            "raw_path": b"/github/webhooks",
            "query_string": b"",
            "root_path": "",
            "headers": signed_webhook_headers(body),
            "client": ("127.0.0.1", 1),
            "server": ("testserver", 80),
            "state": {},
        },
    )

    async def receive() -> Message:
        return request_messages.pop(0)

    async def send(message: Message) -> None:
        if terminate_before_response and message["type"] == "http.response.start":
            terminate_child()
        response_messages.append(message)

    await app(scope, receive, send)
    return receipt_from_response(response_messages)


def receipt_from_response(response_messages: list[Message]) -> DeliveryReceipt:
    try:
        response_start, response_body = response_messages
    except ValueError:
        raise RuntimeError("composed webhook app did not emit one response start and body") from None
    if response_start["type"] != "http.response.start" or response_body["type"] != "http.response.body":
        raise RuntimeError("composed webhook app emitted an invalid ASGI response sequence")
    if response_start["status"] != status.HTTP_202_ACCEPTED:
        raise RuntimeError(f"admitted DS2 fixture was refused with HTTP {response_start['status']}")
    payload = json.loads(response_body["body"])
    return DeliveryReceipt.model_validate(payload, strict=True)


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


def die_after_delivery_custodied(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    root = state_root(payload)
    world = session.world(
        DeliveryCustodyProcessProfile(
            root,
            identity=CUSTODY_DEATH_PROFILE_IDENTITY,
            terminate_before_response=True,
        ),
        DEFAULT_BUDGET,
        checkers=(HamsterdanChecker(),),
    )
    world.timeline().command(
        "hamsterdan.receive_webhook",
        RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
    )
    raise AssertionError("the post-custody process survived before acknowledgement")


def recover_delivery_custody(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    root = state_root(payload)
    world = session.world(
        DeliveryCustodyProcessProfile(
            root,
            identity=CUSTODY_RECOVERY_PROFILE_IDENTITY,
            terminate_before_response=False,
        ),
        DEFAULT_BUDGET,
        checkers=(HamsterdanChecker(),),
    )
    world.timeline().command(
        "hamsterdan.receive_webhook",
        RECEIVE_WEBHOOK_COMMAND.model_dump(mode="json"),
    )
    world.timeline().finish(Disposition.QUIESCENT)
    artifact = world.artifact(CUSTODY_RECOVERY_SCENARIO)
    if not isinstance(artifact, ScenarioArtifact):
        raise TypeError("DS2 custody process recovery requires a version-4 resource artifact")
    return artifact


def die_after_staging_durable(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    root = state_root(payload)
    world = session.world(
        StagingCustodyProcessProfile(
            root,
            identity=STAGING_DEATH_PROFILE_IDENTITY,
            terminate_after_staging=True,
        ),
        DEFAULT_BUDGET,
        checkers=(HamsterdanChecker(),),
    )
    world.timeline().command(
        "hamsterdan.stage_webhook",
        STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
    )
    raise AssertionError("the post-staging process survived before acknowledgement")


def recover_staging_custody(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    root = state_root(payload)
    world = session.world(
        StagingCustodyProcessProfile(
            root,
            identity=STAGING_RECOVERY_PROFILE_IDENTITY,
            terminate_after_staging=False,
        ),
        DEFAULT_BUDGET,
        checkers=(HamsterdanChecker(),),
    )
    world.timeline().command(
        "hamsterdan.stage_webhook",
        STAGE_WEBHOOK_COMMAND.model_dump(mode="json"),
    )
    world.timeline().finish(Disposition.QUIESCENT)
    artifact = world.artifact(STAGING_RECOVERY_SCENARIO)
    if not isinstance(artifact, ScenarioArtifact):
        raise TypeError("DS2 staging process recovery requires a version-4 resource artifact")
    return artifact


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
