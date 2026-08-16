"""Fail-closed composition descriptors for PR-readiness topologies."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

from petrus.motus.activity import ActivityDefinition, ActivityError, ActivityInvocation

from hamsterdan.contracts.readiness import (
    ConversationPublicationRequest,
    ConversationPublicationResult,
    DashboardPublicationRequest,
    DashboardPublicationResult,
    ReadinessCommand,
    ReadinessPublicationResult,
)
from hamsterdan.contracts.readiness_v5 import (
    ABlocked,
    AnnounceReq,
    DashBlocked,
    DashReq,
    ReplyBlocked,
    ReplyReq,
)
from hamsterdan.readiness.payloads import PydanticPayloadConverter

from .application import PrReadinessApplication
from .binding import TopologyIdentity
from .protocol import ReadinessApplication
from .v5.application import PrReadinessV5Application

ApplicationFactory = Callable[..., ReadinessApplication]
InactiveResultAdapter = Callable[[str, ActivityInvocation, ActivityDefinition | None], object]


@dataclass(frozen=True)
class ReadinessComposition:
    topology: TopologyIdentity
    application_factory: ApplicationFactory
    durable_activity_names: frozenset[str]
    has_unresolved: Callable[[ReadinessApplication], bool]
    inactive_result: InactiveResultAdapter


def _has_unresolved(application: ReadinessApplication) -> bool:
    return application.has_unresolved_publication()


def _production_inactive_result(
    name: str,
    invocation: ActivityInvocation,
    definition: ActivityDefinition | None,
) -> object:
    del definition
    try:
        converter = PydanticPayloadConverter()
        payload = invocation.input
        request_name = "command" if name == "readiness_publish" else "work"
        request_type = {
            "conversation_publish": ConversationPublicationRequest,
            "dashboard_publish": DashboardPublicationRequest,
            "readiness_publish": ReadinessCommand,
        }.get(name)
        result_type = {
            "conversation_publish": ConversationPublicationResult,
            "dashboard_publish": DashboardPublicationResult,
            "readiness_publish": ReadinessPublicationResult,
        }.get(name)
        if (
            request_type is None
            or result_type is None
            or not isinstance(payload, Mapping)
            or request_name not in payload
        ):
            raise ValueError("production publication invocation has no recognized request")
        encoded_request = cast(Mapping[str, object], payload)[request_name]
        request = cast(
            ConversationPublicationRequest | DashboardPublicationRequest | ReadinessCommand,
            converter.decode(encoded_request, request_type),
        )
        result = result_type(request.epoch, request.head, False, request.operation, True)
        return converter.encode(result, result_type)
    except Exception as error:
        raise ActivityError(
            "publication scope is unavailable", kind="PublicationScopeError", retryable=False
        ) from error


def _v5_inactive_result(
    name: str,
    invocation: ActivityInvocation,
    definition: ActivityDefinition | None,
) -> object:
    if definition is None or definition.declaration.name != name or invocation.activity != name:
        raise ValueError("V5 publication invocation has no matching Activity definition")
    if not isinstance(invocation.input, Mapping) or set(invocation.input) != set(definition.parameters):
        raise ValueError("V5 publication invocation has malformed parameters")
    [(parameter, annotation)] = definition.parameters.items()
    encoded_work = cast(Mapping[str, object], invocation.input)[parameter]
    work = definition.converter.decode(encoded_work, annotation)
    if name == "reply_gate" and isinstance(work, ReplyReq):
        result: object = ReplyBlocked(id=work.id, text=work.text)
    elif name == "dash_gate" and isinstance(work, DashReq):
        result = DashBlocked(
            entries=work.entries,
            digest=work.digest,
            desired_entries=work.desired_entries,
            desired_digest=work.desired_digest,
        )
    elif name == "announce_gate" and isinstance(work, AnnounceReq):
        result = ABlocked(
            incarnation=work.incarnation,
            head=work.head,
            base=work.base,
            policy=work.policy,
        )
    else:
        raise ValueError("V5 publication invocation has no inactive result")
    return definition.converter.encode(result, definition.result)


PRODUCTION = ReadinessComposition(
    topology="production",
    application_factory=PrReadinessApplication,
    durable_activity_names=frozenset({"conversation_publish", "dashboard_publish", "readiness_publish"}),
    has_unresolved=_has_unresolved,
    inactive_result=_production_inactive_result,
)

V5 = ReadinessComposition(
    topology="v5",
    application_factory=PrReadinessV5Application,
    durable_activity_names=frozenset({"reply_gate", "dash_gate", "announce_gate"}),
    has_unresolved=_has_unresolved,
    inactive_result=_v5_inactive_result,
)


def select_readiness_composition(value: str | None) -> ReadinessComposition:
    if value is None or value == "production":
        return PRODUCTION
    if value == "v5":
        return V5
    raise ValueError("readiness topology must be 'production' or 'v5'")


__all__ = [
    "PRODUCTION",
    "V5",
    "ApplicationFactory",
    "InactiveResultAdapter",
    "ReadinessComposition",
    "select_readiness_composition",
]
