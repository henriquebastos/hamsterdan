# Copyright (c) 2026 Henrique Bastos

"""Strict source-neutral observations accepted by the readiness workflow boundary."""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, GetCoreSchemaHandler
from pydantic_core import core_schema

from hamsterdan2.workflow.values import (  # noqa: TC001 -- Pydantic resolves boundary fields at runtime.
    PositiveIdentifier,
    PullRequestIdentity,
)


MAX_BRANCH_REF_BYTES = 255
ASCII_CONTROL_LIMIT = 32
ASCII_DELETE = 127


class BranchRef(str):
    """Exact bounded branch reference without provider provenance."""

    __slots__ = ()

    def __new__(cls, value: str) -> Self:
        if (
            not isinstance(value, str)
            or not value
            or len(value.encode()) > MAX_BRANCH_REF_BYTES
            or any(ord(character) < ASCII_CONTROL_LIMIT or ord(character) == ASCII_DELETE for character in value)
        ):
            raise ValueError("branch ref must be 1-255 UTF-8 bytes without control characters")
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


class CommitSha(str):
    """Exact lowercase Git SHA-1 identity without acquisition metadata."""

    __slots__ = ()

    PATTERN = re.compile(r"^[0-9a-f]{40}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError("commit SHA must be exactly 40 lowercase hexadecimal characters")
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


class BranchTip(BaseModel):
    """One exact repository branch tip in focused workflow semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    repository_id: PositiveIdentifier
    ref: BranchRef
    sha: CommitSha


class HeadObservation(BaseModel):
    """Head evidence without policy, provenance, time, or currentness claims."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal[1] = 1
    family: Literal["head"] = "head"
    pr_identity: PullRequestIdentity
    generation: Literal[1] = 1
    head: BranchTip
    base: BranchTip
    lifecycle_state: Literal["open", "closed"]
    draft: bool
    merged: bool
    mergeable: bool | None
