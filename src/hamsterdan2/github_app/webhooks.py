# Copyright (c) 2026 Henrique Bastos

"""GitHubKit-confined verification and pull-request webhook normalization."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from githubkit.webhooks import verify
from pydantic import BaseModel, ConfigDict, ValidationError

from hamsterdan2.github_app.models import (
    BranchRef,
    BranchTip,
    CommitSha,
    DeliveryId,
    NormalizedPullRequestWebhook,
    ObservationProvenance,
    PositiveIdentifier,
    ProviderRoute,
    ProviderUpdatedAt,
    PullRequestAction,
    PullRequestIdentity,
    PullRequestSnapshot,
    RepositoryFullName,
    VerifiedWebhookDelivery,
    WebhookEvent,
)


if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


MAX_BODY_BYTES = 1_048_576
MAX_HEADER_BYTES = 32_768
MAX_HEADER_ENTRIES = 100
MAX_SECURITY_HEADER_BYTES = 256
MAX_SECRET_BYTES = 65_536
RefusalReason = Literal[
    "body_too_large",
    "duplicate_security_header",
    "headers_too_large",
    "invalid_content_length",
    "invalid_delivery_id",
    "invalid_signature",
    "invalid_signature_header",
    "malformed_envelope",
    "security_header_too_large",
    "unsupported_content_type",
    "unsupported_event",
    "unsupported_transfer_encoding",
]
PROTECTED_HEADERS = frozenset(
    {
        b"content-length",
        b"content-type",
        b"transfer-encoding",
        b"x-github-delivery",
        b"x-github-event",
        b"x-hub-signature-256",
    }
)
SIGNATURE = re.compile(r"^sha256=[0-9a-f]{64}$")


class WebhookRefusalError(Exception):
    """A raw webhook failed one closed GitHub boundary check."""

    def __init__(self, reason: RefusalReason) -> None:
        self.reason = reason
        super().__init__(reason)


class GitHubInstallation(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    id: PositiveIdentifier


class GitHubRepository(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    id: PositiveIdentifier
    full_name: RepositoryFullName


class GitHubTipRepository(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    id: PositiveIdentifier


class GitHubBranchTip(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    repo: GitHubTipRepository
    ref: BranchRef
    sha: CommitSha


class GitHubPullRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    number: PositiveIdentifier
    state: Literal["open", "closed"]
    draft: bool
    merged: bool
    mergeable: bool | None
    updated_at: ProviderUpdatedAt
    head: GitHubBranchTip
    base: GitHubBranchTip


class GitHubPullRequestEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    action: PullRequestAction
    number: PositiveIdentifier
    installation: GitHubInstallation
    repository: GitHubRepository
    pull_request: GitHubPullRequest


def add_security_header(projected: dict[bytes, bytes], name: bytes, raw_value: bytes) -> None:
    if name in projected:
        raise WebhookRefusalError("duplicate_security_header")
    if len(raw_value) > MAX_SECURITY_HEADER_BYTES:
        raise WebhookRefusalError("security_header_too_large")
    projected[name] = raw_value.strip()


def bounded_headers(entries: Iterable[tuple[bytes, bytes]]) -> Iterator[tuple[bytes, bytes]]:
    header_bytes = 0
    for entry_count, (raw_name, raw_value) in enumerate(entries, start=1):
        header_bytes += len(raw_name) + len(raw_value)
        if entry_count > MAX_HEADER_ENTRIES or header_bytes > MAX_HEADER_BYTES:
            raise WebhookRefusalError("headers_too_large")
        yield raw_name, raw_value


def security_headers(entries: Iterable[tuple[bytes, bytes]]) -> dict[bytes, bytes]:
    projected: dict[bytes, bytes] = {}
    for raw_name, raw_value in bounded_headers(entries):
        name = raw_name.lower()
        if name in PROTECTED_HEADERS:
            add_security_header(projected, name, raw_value)
    if b"transfer-encoding" in projected:
        raise WebhookRefusalError("unsupported_transfer_encoding")
    return projected


def header_text(headers: dict[bytes, bytes], name: bytes) -> str:
    try:
        return headers.get(name, b"").decode("ascii")
    except UnicodeDecodeError:
        raise WebhookRefusalError("security_header_too_large") from None


def validated_content_length(headers: dict[bytes, bytes], body: bytes) -> None:
    content_length = header_text(headers, b"content-length")
    if not content_length.isdecimal() or int(content_length) != len(body):
        raise WebhookRefusalError("invalid_content_length")


def validated_signature(headers: dict[bytes, bytes]) -> str:
    signature = header_text(headers, b"x-hub-signature-256")
    if SIGNATURE.fullmatch(signature) is None:
        raise WebhookRefusalError("invalid_signature_header")
    return signature


def validated_delivery_id(headers: dict[bytes, bytes]) -> DeliveryId:
    try:
        return DeliveryId(header_text(headers, b"x-github-delivery"))
    except ValueError:
        raise WebhookRefusalError("invalid_delivery_id") from None


def validate_media_type(headers: dict[bytes, bytes]) -> None:
    if headers.get(b"content-type") != b"application/json":
        raise WebhookRefusalError("unsupported_content_type")


def validated_event(headers: dict[bytes, bytes]) -> WebhookEvent:
    try:
        return WebhookEvent(header_text(headers, b"x-github-event"))
    except ValueError:
        raise WebhookRefusalError("unsupported_event") from None


def verify_body(secret: str, body: bytes, signature: str) -> None:
    if not verify(secret, body, signature):
        raise WebhookRefusalError("invalid_signature")


def parse_envelope(body: bytes) -> GitHubPullRequestEnvelope:
    try:
        return GitHubPullRequestEnvelope.model_validate_json(body, strict=True)
    except ValidationError, ValueError:
        raise WebhookRefusalError("malformed_envelope") from None


def normalized_webhook(
    envelope: GitHubPullRequestEnvelope,
    *,
    delivery_id: DeliveryId,
) -> NormalizedPullRequestWebhook:
    pull = envelope.pull_request
    if envelope.number != pull.number or envelope.repository.id != pull.base.repo.id:
        raise WebhookRefusalError("malformed_envelope")
    if pull.merged and pull.state != "closed":
        raise WebhookRefusalError("malformed_envelope")
    return NormalizedPullRequestWebhook(
        route=ProviderRoute(
            installation_id=envelope.installation.id,
            repository_id=envelope.repository.id,
            repository_full_name=envelope.repository.full_name,
        ),
        snapshot=PullRequestSnapshot(
            pr_identity=PullRequestIdentity(
                installation_id=envelope.installation.id,
                repository_id=envelope.repository.id,
                pull_request_number=pull.number,
            ),
            head=BranchTip(repository_id=pull.head.repo.id, ref=pull.head.ref, sha=pull.head.sha),
            base=BranchTip(repository_id=pull.base.repo.id, ref=pull.base.ref, sha=pull.base.sha),
            state=pull.state,
            draft=pull.draft,
            merged=pull.merged,
            mergeable=pull.mergeable,
            provider_updated_at=pull.updated_at,
        ),
        provenance=ObservationProvenance(delivery_id=delivery_id, action=envelope.action),
    )


class GitHubWebhook:
    """Verify exact bytes at HTTP intake without parsing their envelope."""

    def __init__(self, *, webhook_secret: str, maximum_body_bytes: int = MAX_BODY_BYTES) -> None:
        if not webhook_secret or len(webhook_secret.encode()) > MAX_SECRET_BYTES:
            raise ValueError("webhook secret must contain 1-65536 UTF-8 bytes")
        if not 1 <= maximum_body_bytes <= MAX_BODY_BYTES:
            raise ValueError(f"maximum body bytes must be between 1 and {MAX_BODY_BYTES}")
        self._webhook_secret = webhook_secret
        self.maximum_body_bytes = maximum_body_bytes

    def verify(
        self,
        headers: Iterable[tuple[bytes, bytes]],
        body: bytes,
    ) -> VerifiedWebhookDelivery:
        projected = security_headers(headers)
        if len(body) > self.maximum_body_bytes:
            raise WebhookRefusalError("body_too_large")
        validated_content_length(projected, body)
        validate_media_type(projected)
        signature = validated_signature(projected)
        delivery_id = validated_delivery_id(projected)
        event = validated_event(projected)
        verify_body(self._webhook_secret, body, signature)
        return VerifiedWebhookDelivery(delivery_id=delivery_id, event=event, body=body)


class GitHubWebhookNormalizer:
    """Parse verified raw evidence on a later host-owned Inbox turn."""

    def normalize(self, delivery: VerifiedWebhookDelivery) -> NormalizedPullRequestWebhook:
        if delivery.event != "pull_request":
            raise WebhookRefusalError("unsupported_event")
        envelope = parse_envelope(delivery.body)
        return normalized_webhook(envelope, delivery_id=delivery.delivery_id)
