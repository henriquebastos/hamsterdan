# Copyright (c) 2026 Henrique Bastos

"""Strict commands and durable records at the replacement host boundary."""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler
from pydantic_core import core_schema

from hamsterdan2.workflow.values import (  # noqa: TC001 -- Pydantic resolves boundary fields at runtime.
    AwaitingObservation,
    PullRequestSubject,
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
    """Request one bounded opening action for an immutable PR subject."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_identity: ActionIdentity
    subject: PullRequestSubject
    action: Literal["open_pull_request"] = "open_pull_request"


class RegisteredPullRequest(BaseModel):
    """Durable host binding between one PR subject and its fresh readiness root."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    subject: PullRequestSubject
    instance_id: str = Field(min_length=1)
    readiness_root: str = Field(pattern=r"^instances/[1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*$")


class HostRecord(BaseModel):
    """Detached result durably retained after the bounded host cut."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_identity: ActionIdentity
    action: Literal["open_pull_request"] = "open_pull_request"
    posture: AwaitingObservation
    cut: Literal["host_recorded"] = "host_recorded"
