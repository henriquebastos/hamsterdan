# Copyright (c) 2026 Henrique Bastos

"""Finite immutable values reconstructed from readiness ingress custody."""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler, model_validator
from pydantic_core import core_schema

from hamsterdan2.github_app.models import (  # noqa: TC001 -- Pydantic resolves custody fields at runtime.
    DeliveryId,
    NormalizedPullRequestWebhook,
    ProviderRouteId,
)
from hamsterdan2.workflow.observations import HeadObservation  # noqa: TC001 -- Pydantic resolves at runtime.
from hamsterdan2.workflow.values import PullRequestSubject  # noqa: TC001 -- Pydantic resolves at runtime.


MAX_ACQUISITION_BYTES = 16_768
MAX_CANONICAL_OBSERVATION_BYTES = 8_192
MAX_ENTRIES_PER_MANIFEST = 8
MAX_MANIFEST_BYTES = 65_536
MAX_MANIFESTS = 10_000
MAX_SQLITE_PAGES = 131_072
Disposition = Literal[
    "exact_duplicate",
    "acquisition_collision",
    "novel",
    "corroborating",
    "stale",
    "semantic_collision",
    "conflicting",
    "incomparable",
]
DecisionReason = Literal[
    "first_observation",
    "same_acquisition",
    "quarantined_acquisition",
    "same_semantics",
    "key_bytes_mismatch",
    "ordered_before",
    "contradictory_head",
    "unordered_head",
]
DECISION_SHAPES = {
    ("exact_duplicate", "same_acquisition", False, False),
    ("acquisition_collision", "quarantined_acquisition", True, False),
    ("novel", "first_observation", False, False),
    ("corroborating", "same_semantics", False, False),
    ("stale", "ordered_before", False, False),
    ("semantic_collision", "key_bytes_mismatch", True, False),
    ("conflicting", "contradictory_head", True, False),
    ("incomparable", "unordered_head", False, True),
}


class PolicyRevision(str):
    """Configured readiness policy identity recorded outside observation equality."""

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


class ManifestId(str):
    """Stable readiness identity of one acquired delivery's immutable manifest."""

    __slots__ = ()

    PATTERN = re.compile(r"^manifest:v1:sha256:[0-9a-f]{64}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError("manifest identity must use manifest:v1:sha256 with 64 lowercase hexadecimal digits")
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


class AdmissionGrantId(str):
    """Stable identity of authority over one exact immutable manifest."""

    __slots__ = ()

    PATTERN = re.compile(r"^grant:v1:sha256:[0-9a-f]{64}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError("grant identity must use grant:v1:sha256 with 64 lowercase hexadecimal digits")
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
    """Versioned identity of one exact manifest entry offered to History."""

    __slots__ = ()

    PATTERN = re.compile(r"^history-delivery:v1:sha256:[0-9a-f]{64}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or cls.PATTERN.fullmatch(value) is None:
            raise ValueError(
                "History delivery identity must use history-delivery:v1:sha256 with 64 lowercase hexadecimal digits"
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
    """Finite deterministic bytes that define one focused observation exactly."""

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


class AcquisitionIdentity(BaseModel):
    """Source-specific identity of one acquired delivery."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_route_id: ProviderRouteId
    delivery_id: DeliveryId


class StagingAcquisition(BaseModel):
    """Bounded acquisition evidence retained separately from focused semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    identity: AcquisitionIdentity
    custody_generation: int = Field(strict=True, gt=0)
    webhook: NormalizedPullRequestWebhook
    quarantined: bool


class IngressEntry(BaseModel):
    """One ordered immutable focused observation inside a manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    order: int = Field(strict=True, ge=0, lt=MAX_ENTRIES_PER_MANIFEST)
    observation_key: ObservationKey
    canonical_bytes: CanonicalObservation
    observation: HeadObservation


class IngressManifest(BaseModel):
    """Immutable ordered projection retained once for one acquisition."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    manifest_id: ManifestId
    acquisition: AcquisitionIdentity
    policy_revision: PolicyRevision
    entries: tuple[IngressEntry, ...] = Field(max_length=MAX_ENTRIES_PER_MANIFEST)

    @model_validator(mode="after")
    def has_ordered_unique_entries(self) -> IngressManifest:
        if tuple(entry.order for entry in self.entries) != tuple(range(len(self.entries))):
            raise ValueError("manifest entry order must be contiguous from zero")
        keys = tuple(entry.observation_key for entry in self.entries)
        if len(keys) != len(set(keys)):
            raise ValueError("manifest observation keys must be unique")
        return self


class AdmissionGrant(BaseModel):
    """Authority to offer only the exact manifest named by its digest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    grant_id: AdmissionGrantId
    manifest_id: ManifestId
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class AdmissionDecision(BaseModel):
    """Finite reconstructible classification retained with one manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entry_order: int | None = Field(default=None, strict=True, ge=0, lt=MAX_ENTRIES_PER_MANIFEST)
    observation_key: ObservationKey | None
    disposition: Disposition
    reason: DecisionReason
    fatal: bool
    refresh_required: bool

    @model_validator(mode="after")
    def has_ruled_shape(self) -> AdmissionDecision:
        shape = (self.disposition, self.reason, self.fatal, self.refresh_required)
        if shape not in DECISION_SHAPES:
            raise ValueError("disposition, reason, fatality, and refresh posture must use one ruled decision shape")
        if (self.entry_order is None) != (self.observation_key is None):
            raise ValueError("entry order and observation key must both identify an entry or both be absent")
        return self


class StagingPosture(BaseModel):
    """Detached result of one authority-side staging turn."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    disposition: Disposition
    manifest: IngressManifest
    grant: AdmissionGrant
    decisions: tuple[AdmissionDecision, ...] = Field(max_length=MAX_ENTRIES_PER_MANIFEST)


class HistoryAcceptancePosture(BaseModel):
    """Detached new-facing result of one exact History acceptance attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    subject: PullRequestSubject
    disposition: Literal["accepted", "refused"]
    reason: Literal[
        "accepted_unfinished",
        "staging_not_novel",
        "occurrence_already_ended",
        "unexpected_scoped_acknowledgement",
    ]
    staging_disposition: Disposition
    bridge_identity: str = Field(min_length=1, max_length=128)
    manifest_id: ManifestId
    grant_id: AdmissionGrantId
    entry_order: int | None = Field(default=None, strict=True, ge=0, lt=MAX_ENTRIES_PER_MANIFEST)
    observation_key: ObservationKey | None
    delivery_identity: HistoryDeliveryIdentity | None
    occurrence: int | None = Field(default=None, strict=True, gt=0)
    finished: bool
    folded: bool

    @model_validator(mode="after")
    def has_ruled_acceptance_shape(self) -> HistoryAcceptancePosture:
        missing_entry = (self.entry_order is None, self.observation_key is None)
        if missing_entry not in {(True, True), (False, False)}:
            raise ValueError("History acceptance entry order and observation key must both be present or absent")
        shape = (
            self.disposition,
            self.reason,
            missing_entry == (False, False),
            self.delivery_identity is not None,
            self.occurrence is not None,
            self.finished,
            self.folded,
        )
        allowed = {
            ("accepted", "accepted_unfinished", True, True, True, False, False),
            ("refused", "staging_not_novel", False, False, False, False, False),
            ("refused", "staging_not_novel", True, False, False, False, False),
            ("refused", "occurrence_already_ended", True, True, True, True, False),
            ("refused", "occurrence_already_ended", True, True, True, True, True),
            ("refused", "unexpected_scoped_acknowledgement", True, True, False, False, False),
        }
        if shape not in allowed:
            raise ValueError("History acceptance posture does not use a ruled field shape")
        if (self.reason == "staging_not_novel") == (self.staging_disposition == "novel"):
            raise ValueError("only non-novel staging may produce the non-admission posture")
        return self


class IngressResources(BaseModel):
    """Finite retained staging usage and its configured hard ceilings."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    manifests: int = Field(strict=True, ge=0)
    entries: int = Field(strict=True, ge=0)
    grants: int = Field(strict=True, ge=0)
    decisions: int = Field(strict=True, ge=0)
    acquisition_bytes: int = Field(strict=True, ge=0)
    canonical_bytes: int = Field(strict=True, ge=0)
    database_pages: int = Field(strict=True, ge=0)
    maximum_manifests: int = Field(strict=True, gt=0, le=MAX_MANIFESTS)
    maximum_acquisition_bytes: int = Field(strict=True, gt=0)
    maximum_database_pages: int = Field(strict=True, gt=0, le=MAX_SQLITE_PAGES)
