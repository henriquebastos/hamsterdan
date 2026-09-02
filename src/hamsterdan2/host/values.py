# Copyright (c) 2026 Henrique Bastos

"""Strict values at the replacement host and application-storage boundary."""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler, model_validator
from pydantic_core import core_schema

from hamsterdan2.github_app.models import (  # noqa: TC001 -- Pydantic resolves boundary fields at runtime.
    DeliveryId,
    NormalizedPullRequestWebhook,
    PositiveIdentifier,
    ProviderRouteId,
    RepositoryFullName,
    VerifiedWebhookDelivery,
    WebhookEvent,
)
from hamsterdan2.readiness.intake_values import (  # noqa: TC001 -- Pydantic resolves boundary fields at runtime.
    PreparedIntake,
)
from hamsterdan2.workflow.values import (  # noqa: TC001 -- Pydantic resolves boundary fields at runtime.
    PullRequestIdentity,
)


class ActionIdentity(str):
    """Stable identity of one deterministic host action."""

    __slots__ = ()

    PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError(
                "action identity must be 1-128 ASCII letters, digits, dots, underscores, colons, or hyphens"
            )
        return super().__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: object,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        del source_type, handler
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(strict=True),
            serialization=core_schema.to_string_ser_schema(),
        )


class OpenPullRequestCommand(BaseModel):
    """Request one bounded opening action for an immutable PR identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_identity: ActionIdentity
    pr_identity: PullRequestIdentity
    action: Literal["open_pull_request"] = "open_pull_request"


class PullRequestWorkflow(BaseModel):
    """Durable application binding for one PR workflow in shared History."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_identity: ActionIdentity
    pr_identity: PullRequestIdentity
    workflow_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^github:[1-9][0-9]*:[1-9][0-9]*:pr:[1-9][0-9]*$",
    )
    bridge_identity: Literal["workflow-bridge/head-seen-intake@4"]
    generation: Literal[1] = 1
    stage: Literal["awaiting_observation"] = "awaiting_observation"
    checkpoint: Literal["pr_workflow_opened"] = "pr_workflow_opened"

    @model_validator(mode="after")
    def matches_pr_identity(self) -> PullRequestWorkflow:
        expected = (
            f"github:{self.pr_identity.installation_id}:{self.pr_identity.repository_id}:"
            f"pr:{self.pr_identity.pull_request_number}"
        )
        if self.workflow_id != expected:
            raise ValueError("workflow identity must match its exact PR identity")
        return self


class ConfiguredProviderRoute(BaseModel):
    """One active host binding for exact provider route evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_route_id: ProviderRouteId
    installation_id: PositiveIdentifier
    repository_id: PositiveIdentifier
    repository_full_name: RepositoryFullName


class InboxReceipt(BaseModel):
    """Bounded HTTP acknowledgement of durable raw inbox evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    inbox: Literal["durable"] = "durable"
    delivery_id: DeliveryId
    inbox_sequence: int = Field(strict=True, gt=0)
    disposition: Literal["received", "duplicate", "collision"]


class InboxDelivery(BaseModel):
    """Detached original raw evidence and its Intake-local state."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    inbox_sequence: int = Field(strict=True, gt=0)
    verified: VerifiedWebhookDelivery
    body_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    collision_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    normalized: NormalizedPullRequestWebhook | None = None
    provider_route_id: ProviderRouteId | None = None
    prepared: PreparedIntake | None = None
    intake_authorized: bool
    intake_outcome: Literal["recorded", "duplicate", "rejected"] | None = None
    intake_reason: str | None = Field(default=None, min_length=1, max_length=128)
    duplicate_of_delivery_id: DeliveryId | None = None


class InboxAuthorization(BaseModel):
    """Exact application-storage input for one source-neutral Intake decision."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    delivery_id: DeliveryId
    body_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_route_id: ProviderRouteId
    normalized: NormalizedPullRequestWebhook
    prepared: PreparedIntake


class InboxResourceUsage(BaseModel):
    """Finite application-storage counters exposed without raw evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    workflows: int = Field(strict=True, ge=0)
    deliveries: int = Field(strict=True, ge=0)
    pages: int = Field(strict=True, ge=0)
    maximum_deliveries: int = Field(strict=True, gt=0)
    maximum_pages: int = Field(strict=True, gt=0)


def webhook_event(delivery: InboxDelivery) -> WebhookEvent:
    """Expose the bounded event name without opening the raw body."""
    return delivery.verified.event
