# Copyright (c) 2026 Henrique Bastos

"""Bounded values produced by the GitHub webhook boundary."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Annotated, Literal, Self
import uuid

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, GetCoreSchemaHandler
from pydantic_core import core_schema


MAX_PROVIDER_IDENTIFIER = 9_223_372_036_854_775_807
UUID_TEXT_LENGTH = 36
MAX_REPOSITORY_FULL_NAME_CHARACTERS = 201
MAX_BRANCH_REF_BYTES = 255
ASCII_CONTROL_LIMIT = 32
ASCII_DELETE = 127
PullRequestAction = Literal[
    "assigned",
    "auto_merge_disabled",
    "auto_merge_enabled",
    "closed",
    "converted_to_draft",
    "dequeued",
    "demilestoned",
    "edited",
    "enqueued",
    "labeled",
    "locked",
    "milestoned",
    "opened",
    "ready_for_review",
    "reopened",
    "review_request_removed",
    "review_requested",
    "synchronize",
    "unassigned",
    "unlabeled",
    "unlocked",
]


def canonical_provider_timestamp(value: datetime) -> datetime:
    try:
        return value.astimezone(UTC)
    except OverflowError, ValueError:
        raise ValueError("provider timestamp must be representable as a UTC instant") from None


ProviderUpdatedAt = Annotated[AwareDatetime, AfterValidator(canonical_provider_timestamp)]


class PositiveIdentifier(int):
    """Positive provider identity bounded to SQLite's signed integer range."""

    __slots__ = ()

    def __new__(cls, value: int) -> Self:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_PROVIDER_IDENTIFIER:
            raise ValueError(f"provider identifier must be between 1 and {MAX_PROVIDER_IDENTIFIER}")
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
            core_schema.int_schema(strict=True, ge=1, le=MAX_PROVIDER_IDENTIFIER),
        )


class ProviderRouteId(str):
    """Configured identity of one provider route."""

    __slots__ = ()

    PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError(
                "provider route identity must be 1-128 ASCII letters, digits, dots, underscores, colons, or hyphens"
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


class DeliveryId(str):
    """Canonical GitHub webhook delivery UUID."""

    __slots__ = ()

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or len(value) != UUID_TEXT_LENGTH:
            raise ValueError("delivery identity must be a canonical UUID")
        try:
            canonical = str(uuid.UUID(value))
        except ValueError:
            raise ValueError("delivery identity must be a canonical UUID") from None
        if canonical != value.lower():
            raise ValueError("delivery identity must be a canonical UUID")
        return super().__new__(cls, canonical)

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


class WebhookEvent(str):
    """Bounded GitHub event name retained with raw inbox evidence."""

    __slots__ = ()

    PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError("webhook event must be 1-64 ASCII letters, digits, underscores, or hyphens")
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


class RepositoryFullName(str):
    """Canonical owner/name evidence from GitHub."""

    __slots__ = ()

    def __new__(cls, value: str) -> Self:
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= MAX_REPOSITORY_FULL_NAME_CHARACTERS
            or not value.isascii()
            or not value.isprintable()
            or value.count("/") != 1
            or any(not part or part.strip() != part for part in value.split("/"))
        ):
            raise ValueError("repository full name must be bounded printable ASCII in owner/name form")
        return super().__new__(cls, value.lower())

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


class BranchRef(str):
    """Bounded exact branch reference from one webhook tip."""

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
    """Exact lowercase GitHub SHA-1 object identity."""

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


class ProviderRoute(BaseModel):
    """Provider-owned route evidence carried by one verified envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    installation_id: PositiveIdentifier
    repository_id: PositiveIdentifier
    repository_full_name: RepositoryFullName


class PullRequestIdentity(BaseModel):
    """Immutable GitHub PR identity present in one webhook snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    installation_id: PositiveIdentifier
    repository_id: PositiveIdentifier
    pull_request_number: PositiveIdentifier


class BranchTip(BaseModel):
    """Exact repository, ref, and commit at one webhook branch tip."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    repository_id: PositiveIdentifier
    ref: BranchRef
    sha: CommitSha


class PullRequestSnapshot(BaseModel):
    """Immutable provider evidence present in a pull-request webhook."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pr_identity: PullRequestIdentity
    head: BranchTip
    base: BranchTip
    state: Literal["open", "closed"]
    draft: bool
    merged: bool
    mergeable: bool | None
    provider_updated_at: ProviderUpdatedAt


class ObservationProvenance(BaseModel):
    """Bounded acquisition context excluded from snapshot semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    delivery_id: DeliveryId
    event: Literal["pull_request"] = "pull_request"
    action: PullRequestAction


class NormalizedPullRequestWebhook(BaseModel):
    """The complete provider value allowed to leave the GitHub boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    route: ProviderRoute
    snapshot: PullRequestSnapshot
    provenance: ObservationProvenance


class VerifiedWebhookDelivery(BaseModel):
    """Exact bounded body and metadata after successful HMAC verification."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    delivery_id: DeliveryId
    event: WebhookEvent
    body: bytes
