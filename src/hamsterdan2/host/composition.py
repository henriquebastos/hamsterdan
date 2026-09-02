# Copyright (c) 2026 Henrique Bastos

"""The sole concrete composition root for the replacement application."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from hamsterdan2.github_app.webhooks import MAX_BODY_BYTES, GitHubWebhook, GitHubWebhookNormalizer
from hamsterdan2.host.api import create_webhook_app
from hamsterdan2.host.application import Hamsterdan, PullRequestAuthority, WebhookInboxWorker
from hamsterdan2.host.database import MAX_INBOX_DELIVERIES, ApplicationDatabase
from hamsterdan2.host.pr_workflows import PullRequestWorkflows
from hamsterdan2.host.webhook_inbox import WebhookInbox
from hamsterdan2.readiness.runtime import build_readiness_runtime


if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI

    from hamsterdan2.host.values import ConfiguredProviderRoute, PullRequestWorkflow
    from hamsterdan2.readiness.intake_values import PolicyRevision
    from hamsterdan2.readiness.runtime import ReadinessRuntime
    from hamsterdan2.workflow.values import AwaitingObservation


def application_database(
    state_root: Path,
    *,
    maximum_deliveries: int = MAX_INBOX_DELIVERIES,
) -> ApplicationDatabase:
    return ApplicationDatabase.from_path(
        state_root / "hamsterdan.sqlite3",
        maximum_deliveries=maximum_deliveries,
    )


def readiness_for(workflow: PullRequestWorkflow, *, state_root: Path) -> ReadinessRuntime:
    return build_readiness_runtime(
        history_path=state_root / "history.sqlite3",
        dispatch_path=state_root / "dispatch.sqlite3",
        workflow_id=workflow.workflow_id,
    )


def open_readiness(workflow: PullRequestWorkflow, *, state_root: Path) -> AwaitingObservation:
    return readiness_for(workflow, state_root=state_root).open(workflow.pr_identity)


def build_hamsterdan(*, state_root: Path) -> Hamsterdan:
    workflows = PullRequestWorkflows(application_database(state_root))
    return Hamsterdan(
        workflows=workflows,
        open_readiness=partial(open_readiness, state_root=state_root),
    )


def build_webhook_app(
    *,
    state_root: Path,
    webhook_secret: str,
    maximum_body_bytes: int = MAX_BODY_BYTES,
    maximum_deliveries: int = MAX_INBOX_DELIVERIES,
) -> FastAPI:
    database = application_database(
        state_root,
        maximum_deliveries=maximum_deliveries,
    )
    return create_webhook_app(
        webhook=GitHubWebhook(
            webhook_secret=webhook_secret,
            maximum_body_bytes=maximum_body_bytes,
        ),
        inbox=WebhookInbox.from_database(database),
    )


def build_webhook_inbox_worker(
    *,
    state_root: Path,
    provider_routes: tuple[ConfiguredProviderRoute, ...],
    policy_revision: PolicyRevision,
    maximum_deliveries: int = MAX_INBOX_DELIVERIES,
) -> WebhookInboxWorker:
    database = application_database(
        state_root,
        maximum_deliveries=maximum_deliveries,
    )
    return WebhookInboxWorker(
        inbox=WebhookInbox.from_database(
            database,
            provider_routes=provider_routes,
        ),
        normalizer=GitHubWebhookNormalizer(),
        policy_revision=policy_revision,
        readiness_for=partial(readiness_for, state_root=state_root),
    )


def build_pull_request_authority(*, state_root: Path) -> PullRequestAuthority:
    return PullRequestAuthority(
        workflows=PullRequestWorkflows(application_database(state_root)),
        readiness_for=partial(readiness_for, state_root=state_root),
    )
