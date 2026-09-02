# Copyright (c) 2026 Henrique Bastos

"""Finite values at the source-neutral Intake and History boundaries."""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler
from pydantic_core import core_schema

from hamsterdan2.github_app.models import DeliveryId  # noqa: TC001 -- Pydantic resolves boundary fields at runtime.
from hamsterdan2.workflow.observations import (  # noqa: TC001 -- Pydantic resolves boundary fields at runtime.
    HeadObservation,
)
from hamsterdan2.workflow.values import (  # noqa: TC001 -- Pydantic resolves boundary fields at runtime.
    PullRequestIdentity,
)


MAX_CANONICAL_OBSERVATION_BYTES = 8_192


class PolicyRevision(str):
    """Configured policy identity excluded from observation equality."""

    __slots__ = ()

    PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError(
                "policy revision must be 1-128 ASCII letters, digits, dots, underscores, colons, or hyphens"
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


class ObservationKey(str):
    """Versioned semantic identity of one complete focused observation."""

    __slots__ = ()

    PATTERN = re.compile(r"^obs:v1:sha256:[0-9a-f]{64}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError("observation key must use obs:v1:sha256 with 64 lowercase hexadecimal digits")
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


class HistoryDeliveryIdentity(str):
    """Stable identity of one exact focused observation offered to History."""

    __slots__ = ()

    PATTERN = re.compile(r"^history-delivery:v2:sha256:[0-9a-f]{64}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError(
                "History delivery identity must use history-delivery:v2:sha256 with 64 lowercase hexadecimal digits"
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


class CanonicalObservation(bytes):
    """Finite deterministic bytes defining one focused observation exactly."""

    __slots__ = ()

    def __new__(cls, value: bytes) -> Self:
        if not isinstance(value, bytes) or not 1 <= len(value) <= MAX_CANONICAL_OBSERVATION_BYTES:
            raise ValueError(f"canonical observation must contain 1-{MAX_CANONICAL_OBSERVATION_BYTES} bytes")
        return super().__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: object,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        del source_type, handler
        return core_schema.no_info_after_validator_function(cls, core_schema.bytes_schema(strict=True))


class PreparedIntake(BaseModel):
    """One exact source-neutral observation authorized before History."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    observation: HeadObservation
    observation_key: ObservationKey
    canonical_observation: CanonicalObservation
    policy_revision: PolicyRevision
    bridge_identity: str = Field(min_length=1, max_length=128)
    delivery_identity: HistoryDeliveryIdentity


class IntakeResult(BaseModel):
    """Detached outcome of one host-owned Webhook Inbox Worker turn."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    delivery_id: DeliveryId
    outcome: Literal["recorded", "duplicate", "rejected"]
    reason: str = Field(min_length=1, max_length=128)
    pr_identity: PullRequestIdentity | None = None
    observation_key: ObservationKey | None = None
    delivery_identity: HistoryDeliveryIdentity | None = None
    occurrence: int | None = Field(default=None, strict=True, gt=0)


class ObservationCompletion(BaseModel):
    """Detached result of completing one History-owned observation occurrence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pr_identity: PullRequestIdentity
    workflow_id: str = Field(min_length=1, max_length=128)
    delivery_identity: HistoryDeliveryIdentity
    occurrence: int = Field(strict=True, gt=0)
    disposition: Literal["completed", "already_completed"]
    checkpoint: Literal["observation_folded"] = "observation_folded"
