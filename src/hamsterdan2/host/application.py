# Copyright (c) 2026 Henrique Bastos

"""Bounded replacement-host operations over durable catalog custody."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable

    from hamsterdan2.github_app.models import DeliveryId, ProviderRouteId
    from hamsterdan2.host.catalog import HostCatalog
    from hamsterdan2.host.delivery import DeliveryCustody
    from hamsterdan2.host.values import CustodiedDelivery, HostRecord, OpenPullRequestCommand, RegisteredPullRequest
    from hamsterdan2.readiness.ingress import IngressCustody
    from hamsterdan2.readiness.ingress_values import IngressResources, StagingAcquisition, StagingPosture
    from hamsterdan2.workflow.values import AwaitingObservation


class Hamsterdan:
    """Register and advance one PR at a time through host-owned cuts."""

    def __init__(
        self,
        *,
        catalog: HostCatalog,
        open_readiness: Callable[[RegisteredPullRequest], AwaitingObservation],
    ) -> None:
        self._catalog = catalog
        self._open_readiness = open_readiness

    def register(self, command: OpenPullRequestCommand) -> RegisteredPullRequest:
        return self._catalog.register(command)

    def step(self, command: OpenPullRequestCommand) -> HostRecord:
        return self._catalog.step(command, self._open_readiness)

    def open_pull_request(self, command: OpenPullRequestCommand) -> HostRecord:
        self.register(command)
        return self.step(command)


class DeliveryNotFoundError(Exception):
    """The requested acquired delivery does not exist in host custody."""


class StagingAuthority:
    """Run one readiness staging turn from reconstructed host delivery custody."""

    def __init__(self, *, delivery_custody: DeliveryCustody, ingress_custody: IngressCustody) -> None:
        self._delivery_custody = delivery_custody
        self._ingress_custody = ingress_custody

    def stage_delivery(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> StagingPosture:
        def select_delivery() -> CustodiedDelivery:
            delivery = self._delivery_custody.retained_delivery(
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )
            if delivery is None:
                raise DeliveryNotFoundError(
                    provider_route_id,
                    delivery_id,
                    "acquire this delivery before requesting readiness staging",
                )
            return delivery

        return self._ingress_custody.stage_selected(select_delivery)

    def staging_posture(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> StagingPosture | None:
        return self._ingress_custody.staging_posture(
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
        )

    def staging_acquisition(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> StagingAcquisition | None:
        return self._ingress_custody.staging_acquisition(
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
        )

    def ingress_resources(self) -> IngressResources:
        return self._ingress_custody.resources()
