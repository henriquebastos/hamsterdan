# Copyright (c) 2026 Henrique Bastos

"""Concrete composition admitted by the first CV21 tracer."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from hamsterdan2.github_app.webhooks import MAX_BODY_BYTES, GitHubWebhook
from hamsterdan2.host.api import create_webhook_app
from hamsterdan2.host.application import Hamsterdan, ObservationAcceptanceAuthority, StagingAuthority
from hamsterdan2.host.catalog import HostCatalog
from hamsterdan2.host.delivery import MAX_RETAINED_DELIVERIES, DeliveryCustody
from hamsterdan2.readiness.ingress import IngressCustody
from hamsterdan2.readiness.ingress_values import MAX_MANIFESTS, PolicyRevision
from hamsterdan2.readiness.runtime import build_history_acceptance_runtime, build_readiness_runtime


if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI

    from hamsterdan2.github_app.models import DeliveryId, ProviderRouteId
    from hamsterdan2.host.values import ConfiguredProviderRoute, RegisteredPullRequest
    from hamsterdan2.readiness.ingress_values import HistoryAcceptancePosture
    from hamsterdan2.workflow.values import AwaitingObservation


def open_readiness(
    registered: RegisteredPullRequest,
    *,
    state_root: Path,
    dispatch_path: Path,
) -> AwaitingObservation:
    runtime = build_readiness_runtime(
        root_path=state_root / registered.readiness_root,
        dispatch_path=dispatch_path,
        instance_id=registered.instance_id,
    )
    return runtime.open(registered.subject)


def build_hamsterdan(*, state_root: Path) -> Hamsterdan:
    return Hamsterdan(
        catalog=HostCatalog.from_path(state_root / "catalog.sqlite3"),
        open_readiness=partial(
            open_readiness,
            state_root=state_root,
            dispatch_path=state_root / "dispatch.sqlite3",
        ),
    )


def accept_readiness_observation(
    registered: RegisteredPullRequest,
    *,
    provider_route_id: ProviderRouteId,
    delivery_id: DeliveryId,
    state_root: Path,
    dispatch_path: Path,
    ingress_path: Path,
    maximum_manifests: int,
) -> HistoryAcceptancePosture:
    runtime = build_history_acceptance_runtime(
        root_path=state_root / registered.readiness_root,
        dispatch_path=dispatch_path,
        ingress_path=ingress_path,
        instance_id=registered.instance_id,
        maximum_manifests=maximum_manifests,
    )
    return runtime.accept_staged_observation(
        provider_route_id=provider_route_id,
        delivery_id=delivery_id,
        subject=registered.subject,
    )


def build_observation_acceptance_authority(
    *,
    state_root: Path,
    maximum_manifests: int = MAX_MANIFESTS,
) -> ObservationAcceptanceAuthority:
    ingress_path = state_root / "readiness-ingress.sqlite3"
    return ObservationAcceptanceAuthority(
        catalog=HostCatalog.from_path(state_root / "catalog.sqlite3"),
        ingress_custody=IngressCustody.for_reconstruction(
            path=ingress_path,
            maximum_manifests=maximum_manifests,
        ),
        accept_readiness=partial(
            accept_readiness_observation,
            state_root=state_root,
            dispatch_path=state_root / "dispatch.sqlite3",
            ingress_path=ingress_path,
            maximum_manifests=maximum_manifests,
        ),
    )


def build_webhook_app(
    *,
    state_root: Path,
    webhook_secret: str,
    provider_routes: tuple[ConfiguredProviderRoute, ...],
    maximum_body_bytes: int = MAX_BODY_BYTES,
    maximum_deliveries: int = MAX_RETAINED_DELIVERIES,
) -> FastAPI:
    webhook = GitHubWebhook(
        webhook_secret=webhook_secret,
        maximum_body_bytes=maximum_body_bytes,
    )
    custody = DeliveryCustody.from_path(
        path=state_root / "deliveries.sqlite3",
        provider_routes=provider_routes,
        maximum_deliveries=maximum_deliveries,
    )
    return create_webhook_app(webhook=webhook, custody=custody)


def build_staging_authority(
    *,
    state_root: Path,
    provider_routes: tuple[ConfiguredProviderRoute, ...],
    policy_revision: PolicyRevision,
    maximum_deliveries: int = MAX_RETAINED_DELIVERIES,
    maximum_manifests: int = MAX_MANIFESTS,
) -> StagingAuthority:
    return StagingAuthority(
        delivery_custody=DeliveryCustody.from_path(
            path=state_root / "deliveries.sqlite3",
            provider_routes=provider_routes,
            maximum_deliveries=maximum_deliveries,
        ),
        ingress_custody=IngressCustody.from_path(
            path=state_root / "readiness-ingress.sqlite3",
            policy_revision=policy_revision,
            maximum_manifests=maximum_manifests,
        ),
    )
