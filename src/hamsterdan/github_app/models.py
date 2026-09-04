"""Frozen GitHub provider snapshots, results, and transport protocols."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

MAX_LOG_BYTES = 2_097_152


ProviderFailureClass = Literal[
    "transport_ambiguity",
    "transient_http_rejection",
    "capability_denial",
    "payload_rejection",
    "provider_rejection",
]


class GitHubBoundaryError(RuntimeError):
    """A secret-safe provider boundary failure with bounded diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: ProviderFailureClass = "transport_ambiguity",
        provider_status: int | None = None,
        provider_detail: str = "none",
    ) -> None:
        if provider_status is not None and not 100 <= provider_status <= 599:
            raise ValueError("provider status must be an HTTP status")
        if not provider_detail or len(provider_detail) > 96 or re.fullmatch(r"[a-z0-9_.:-]+", provider_detail) is None:
            raise ValueError("provider detail must use the bounded diagnostic vocabulary")
        self.failure_class = failure_class
        self.provider_status = provider_status
        self.provider_detail = provider_detail
        super().__init__(message)


class RerunRefusedError(RuntimeError):
    """Proven pre-effect movement: the broker verified currency and
    refused BEFORE any effect was issued. Nothing landed and nothing is
    ambiguous — deliberately NOT a GitHubBoundaryError, so a caller can
    classify moved instead of fail-closed fault."""


@dataclass(frozen=True)
class InstallationInventory:
    installation_id: int
    account_id: int
    repositories: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class RegistrationInventory:
    installations: tuple[InstallationInventory, ...]


@dataclass(frozen=True)
class WireResponse:
    status: int
    body: object
    next_path: str | None = None


class Transport(Protocol):
    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> WireResponse: ...
    def pages(self, path: str) -> tuple[dict[str, Any], ...]: ...


class BinaryTransport(Protocol):
    def download(self, path: str, limit: int = MAX_LOG_BYTES) -> bytes: ...


class GraphQLTransport(Protocol):
    def review_threads(self, owner: str, repository: str, pr_number: int) -> Sequence[Mapping[str, Any]]: ...
    def resolve_review_thread(self, thread_id: str) -> None: ...
    def compare_and_swap_ref(self, repository: str, ref: str, expected_head: str, commit: str) -> None: ...


@dataclass(frozen=True)
class PullRequestSnapshot:
    repository: str
    number: int
    state: str
    draft: bool
    head: str
    base: str
    head_ref: str
    base_ref: str
    mergeable: bool | None
    merged: bool
    closed: bool
    author: str
    mergeable_state: str
    url: str
    head_repository: str


@dataclass(frozen=True)
class RepositoryPolicy:
    strict: bool
    update_required: bool
    required_checks: tuple[str, ...]
    required_approvals: int
    conversation_resolution: bool
    source: str
    digest: str


@dataclass(frozen=True)
class ActionsJobSnapshot:
    id: int
    name: str
    status: str
    conclusion: str | None
    required: bool


@dataclass(frozen=True)
class ActionsRunSnapshot:
    id: int
    head: str
    workflow: str
    attempt: int
    status: str
    conclusion: str | None
    jobs: tuple[ActionsJobSnapshot, ...] = ()


@dataclass(frozen=True)
class ActionsEvidence:
    run: ActionsRunSnapshot
    conclusion: Literal["queued", "in_progress", "success", "failure"]
    failed_required_jobs: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class HumanReviewSnapshot:
    requested_reviewers: tuple[str, ...]
    latest_reviews: tuple[tuple[str, str], ...]
    approvals: tuple[str, ...]
    changes_requested: tuple[str, ...]
    unresolved_threads: int | None
    threads_capability: str


@dataclass(frozen=True)
class CommentReference:
    id: int
    url: str


@dataclass(frozen=True)
class PublicationResult:
    status: str
    reference: CommentReference | None = None
    capability_available: bool = True
    inline: bool = False


@dataclass(frozen=True)
class FindingPublication:
    operation: str
    text: str
    path: str
    line: int
    related_locations: tuple[tuple[str, int], ...] = ()
    suggestion: str = ""
    link: str = ""


@dataclass(frozen=True)
class RerunIssue:
    """One rerun issuance plus the pre-request evidence cut: the newest
    (run_id, attempt) the provider reported for the head in the FINAL
    read immediately before the POST, so no run can appear between the
    cut and the effect."""

    result: PublicationResult
    cut_run_id: int
    cut_attempt: int
