# Copyright (c) 2026 Henrique Bastos

"""Owner-local deterministic execution of signed webhook normalization."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import json
from typing import TYPE_CHECKING, Literal, cast

from petrus.testing.dst import (
    ApplyResult,
    BudgetV4,
    CheckResult,
    CheckerIdentity,
    Command,
    Fault,
    GenerationStart,
    Observation,
    ObservationRequest,
    ProfileIdentity,
    ReplayResult,
    ResourceUsage,
    ScenarioArtifact,
    ScenarioArtifactV3,
    ScenarioContext,
    ScenarioRegistry,
    World,
    digest_json,
    replay,
)
from pydantic import BaseModel, ConfigDict

from hamsterdan2.github_app.models import (
    BranchRef,
    BranchTip,
    CommitSha,
    DeliveryId,
    NormalizedPullRequestWebhook,
    ObservationProvenance,
    PositiveIdentifier,
    ProviderRoute,
    PullRequestSnapshot,
    PullRequestSubject,
    RepositoryFullName,
)
from hamsterdan2.github_app.webhooks import GitHubWebhook


if TYPE_CHECKING:
    from petrus.testing.dst import ScenarioProfile
    from pydantic import JsonValue


WEBHOOK_SIGNING_MATERIAL = "simulation-webhook-signing-material"
DELIVERY_ID = DeliveryId("11111111-1111-4111-8111-111111111111")
ORIGINAL_HEAD_SHA = CommitSha("a" * 40)
COLLIDING_HEAD_SHA = CommitSha("c" * 40)


class NormalizeWebhookCommand(BaseModel):
    """One exact owner-local signed webhook fixture."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["normalize_signed_pull_request"] = "normalize_signed_pull_request"


class WebhookBoundaryState(BaseModel):
    """Detached result of the latest pure provider normalization."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    normalized: NormalizedPullRequestWebhook | None


NORMALIZE_WEBHOOK_COMMAND = NormalizeWebhookCommand()
EXPECTED_WEBHOOK = NormalizedPullRequestWebhook(
    route=ProviderRoute(
        installation_id=PositiveIdentifier(44),
        repository_id=PositiveIdentifier(31),
        repository_full_name=RepositoryFullName("owner/repo"),
    ),
    snapshot=PullRequestSnapshot(
        subject=PullRequestSubject(
            installation_id=PositiveIdentifier(44),
            repository_id=PositiveIdentifier(31),
            pull_request_number=PositiveIdentifier(7),
        ),
        head=BranchTip(
            repository_id=PositiveIdentifier(32),
            ref=BranchRef("feature/custody"),
            sha=ORIGINAL_HEAD_SHA,
        ),
        base=BranchTip(
            repository_id=PositiveIdentifier(31),
            ref=BranchRef("main"),
            sha=CommitSha("b" * 40),
        ),
        state="open",
        draft=False,
        merged=False,
        mergeable=None,
        provider_updated_at=datetime(2026, 8, 30, 12, 34, 56, tzinfo=UTC),
    ),
    provenance=ObservationProvenance(delivery_id=DELIVERY_ID, action="synchronize"),
)


def signed_webhook_body(*, head_sha: CommitSha = ORIGINAL_HEAD_SHA) -> bytes:
    return json.dumps(
        {
            "action": "synchronize",
            "number": 7,
            "installation": {"id": 44},
            "repository": {"id": 31, "full_name": "owner/repo"},
            "pull_request": {
                "number": 7,
                "state": "open",
                "draft": False,
                "merged": False,
                "mergeable": None,
                "updated_at": "2026-08-30T12:34:56Z",
                "head": {"repo": {"id": 32}, "ref": "feature/custody", "sha": str(head_sha)},
                "base": {"repo": {"id": 31}, "ref": "main", "sha": "b" * 40},
            },
            "unretained_provider_field": "simulation-raw-only-marker",
        },
        separators=(",", ":"),
    ).encode()


def signed_webhook_headers(body: bytes) -> list[tuple[bytes, bytes]]:
    signature = hmac.new(WEBHOOK_SIGNING_MATERIAL.encode(), body, hashlib.sha256).hexdigest()
    return [
        (b"content-length", str(len(body)).encode()),
        (b"content-type", b"application/json"),
        (b"x-github-delivery", str(DELIVERY_ID).encode()),
        (b"x-github-event", b"pull_request"),
        (b"x-hub-signature-256", f"sha256={signature}".encode()),
    ]


PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan2.github_app.ds2",
    version=1,
    digest=digest_json(
        {
            "command": NORMALIZE_WEBHOOK_COMMAND.model_dump(mode="json"),
            "body_digest": hashlib.sha256(signed_webhook_body()).hexdigest(),
            "observation": "github_app.webhook_state",
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="hamsterdan2.github_app.ds2.normalization-checker",
    version=1,
    digest=digest_json(EXPECTED_WEBHOOK.model_dump(mode="json")),
)
DEFAULT_BUDGET = BudgetV4(
    actions=4,
    queued_commands=1,
    timer_advances=0,
    logical_instant=0,
    reloads=1,
    predicate_polls=1,
    artifact_bytes=65_536,
    profile_resources={"normalized.github.webhooks": 1},
)


def validate_normalize_webhook(command: Command) -> Command:
    if command.name != "github_app.normalize_webhook":
        raise ValueError("DS2 GitHub boundary accepts only 'github_app.normalize_webhook'")
    parsed = NormalizeWebhookCommand.model_validate(command.payload, strict=True)
    if parsed != NORMALIZE_WEBHOOK_COMMAND or parsed.model_dump(mode="json") != command.payload:
        raise ValueError("DS2 GitHub command must name the exact admitted signed fixture and fields")
    return command


class GitHubWebhookScenarioProfile:
    """Petrus profile over the real GitHub verification boundary."""

    identity = PROFILE_IDENTITY

    def __init__(self) -> None:
        self._normalized: NormalizedPullRequestWebhook | None = None

    def validate(self, command: Command) -> Command:
        return validate_normalize_webhook(command)

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"DS2 GitHub boundary admits no faults; remove {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[GitHubWebhook]:
        del context
        self._normalized = None
        return GenerationStart(GitHubWebhook(webhook_secret=WEBHOOK_SIGNING_MATERIAL))

    def load(self, context: ScenarioContext) -> GenerationStart[GitHubWebhook]:
        return self.create(context)

    def apply(
        self,
        generation: GitHubWebhook,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del command, context
        body = signed_webhook_body()
        self._normalized = generation.normalize(signed_webhook_headers(body), body)
        return ApplyResult(
            disposition="applied",
            value=self._normalized.model_dump(mode="json"),
            scheduled=[],
        )

    def observe(
        self,
        generation: GitHubWebhook,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del generation, context
        if request.name != "github_app.webhook_state" or request.payload != {}:
            raise ValueError("DS2 GitHub boundary exposes only 'github_app.webhook_state'")
        state = WebhookBoundaryState(normalized=self._normalized)
        return cast("JsonValue", state.model_dump(mode="json"))

    def resource_usage(self, generation: GitHubWebhook | None) -> ResourceUsage:
        del generation
        return ResourceUsage(values={"normalized.github.webhooks": 0 if self._normalized is None else 1})

    def drop(self, generation: GitHubWebhook) -> None:
        del generation

    def close(self, generation: GitHubWebhook) -> None:
        del generation


class GitHubWebhookChecker:
    """Check the provider projection against an independently built exact value."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="github_app.webhook_state", payload={})

    def check(self, observation: Observation) -> CheckResult:
        state = WebhookBoundaryState.model_validate_json(json.dumps(observation.value), strict=True)
        empty = state.normalized is None
        normalized = state.normalized == EXPECTED_WEBHOOK
        return CheckResult(
            passed=empty or normalized,
            detail={"empty": empty, "normalized": normalized},
        )


def build_github_webhook_world(*, budget: BudgetV4 = DEFAULT_BUDGET) -> World:
    profile = cast("ScenarioProfile[object]", GitHubWebhookScenarioProfile())
    return World(profile, budget, checkers=(GitHubWebhookChecker(),))


def replay_github_webhook(artifact: ScenarioArtifactV3 | ScenarioArtifact) -> ReplayResult:
    if not isinstance(artifact, ScenarioArtifact):
        raise TypeError("DS2 GitHub replay requires a version-4 resource artifact")
    registry = ScenarioRegistry()
    registry.register_profile(GitHubWebhookScenarioProfile())
    registry.register_checker(GitHubWebhookChecker())
    return cast("ReplayResult", replay(artifact, registry))
