"""Frozen GitHub provider snapshots, results, and transport protocols."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

MAX_LOG_BYTES = 2_097_152


class GitHubBoundaryError(RuntimeError):
    """A secret-safe provider boundary failure."""


@dataclass(frozen=True)
class RegistrationInventory:
    installation_id: int
    repositories: tuple[tuple[int, str], ...]


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
