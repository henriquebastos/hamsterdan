# Copyright (c) 2026 Henrique Bastos

"""Bounded replacement-host operations over durable catalog custody."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hamsterdan2.host.values import CustodiedDelivery, HostDeliveryCompletionReceipt
from hamsterdan2.readiness.ingress_values import ObservationFoldPosture
from hamsterdan2.workflow.values import PullRequestSubject


if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Protocol

    from hamsterdan2.github_app.models import DeliveryId, ProviderRouteId
    from hamsterdan2.host.catalog import HostCatalog
    from hamsterdan2.host.delivery import DeliveryCompletionCustody, DeliveryCustody
    from hamsterdan2.host.values import HostRecord, OpenPullRequestCommand, RegisteredPullRequest
    from hamsterdan2.readiness.ingress import IngressCustody
    from hamsterdan2.readiness.ingress_values import (
        HistoryAcceptancePosture,
        IngressResources,
        StagingAcquisition,
        StagingPosture,
    )
    from hamsterdan2.workflow.values import AwaitingObservation

    class AcceptReadinessObservation(Protocol):
        def __call__(
            self,
            registered: RegisteredPullRequest,
            *,
            provider_route_id: ProviderRouteId,
            delivery_id: DeliveryId,
        ) -> HistoryAcceptancePosture: ...

    class FoldReadinessObservation(Protocol):
        def __call__(
            self,
            registered: RegisteredPullRequest,
            *,
            provider_route_id: ProviderRouteId,
            delivery_id: DeliveryId,
        ) -> ObservationFoldPosture | HistoryAcceptancePosture: ...


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


class StagedObservationNotFoundError(Exception):
    """The requested task-2 identity has no durable readiness staging."""


class ObservationDeliveryNotFoldedError(Exception):
    """Host completion requires the exact successful retained fold."""


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


class ObservationAcceptanceAuthority:
    """Select staged authority by task-2 identity and fence its registered root."""

    def __init__(
        self,
        *,
        catalog: HostCatalog,
        ingress_custody: IngressCustody,
        completion_custody: DeliveryCompletionCustody,
        accept_readiness: AcceptReadinessObservation,
        fold_readiness: FoldReadinessObservation,
        verify_readiness: FoldReadinessObservation,
    ) -> None:
        self._catalog = catalog
        self._ingress_custody = ingress_custody
        self._completion_custody = completion_custody
        self._accept_readiness = accept_readiness
        self._fold_readiness = fold_readiness
        self._verify_readiness = verify_readiness

    def selected_subject(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> PullRequestSubject:
        reconstructed = self._ingress_custody.reconstructed_staging(
            provider_route_id=provider_route_id,
            delivery_id=delivery_id,
        )
        if reconstructed is None:
            raise StagedObservationNotFoundError(
                provider_route_id,
                delivery_id,
                "stage this acquired delivery before requesting observation authority",
            )
        acquisition, _ = reconstructed
        source_subject = acquisition.webhook.snapshot.subject
        return PullRequestSubject(
            installation_id=source_subject.installation_id,
            repository_id=source_subject.repository_id,
            pull_request_number=source_subject.pull_request_number,
        )

    def accept_staged_observation(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> HistoryAcceptancePosture:
        subject = self.selected_subject(provider_route_id=provider_route_id, delivery_id=delivery_id)

        def accept(registered: RegisteredPullRequest) -> HistoryAcceptancePosture:
            return self._accept_readiness(
                registered,
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )

        return self._catalog.run_readiness_authority(subject, accept)

    def fold_accepted_observation(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> ObservationFoldPosture | HistoryAcceptancePosture:
        subject = self.selected_subject(provider_route_id=provider_route_id, delivery_id=delivery_id)

        def fold(registered: RegisteredPullRequest) -> ObservationFoldPosture | HistoryAcceptancePosture:
            return self._fold_readiness(
                registered,
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )

        return self._catalog.run_readiness_authority(subject, fold)

    def complete_observation_delivery(
        self,
        *,
        provider_route_id: ProviderRouteId,
        delivery_id: DeliveryId,
    ) -> HostDeliveryCompletionReceipt:
        subject = self.selected_subject(provider_route_id=provider_route_id, delivery_id=delivery_id)

        def complete(registered: RegisteredPullRequest) -> HostDeliveryCompletionReceipt:
            folded = self._verify_readiness(
                registered,
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )
            if not isinstance(folded, ObservationFoldPosture):
                raise ObservationDeliveryNotFoldedError(
                    provider_route_id,
                    delivery_id,
                    "only a novel History-proven fold can complete host delivery",
                )
            reconstructed = self._ingress_custody.reconstructed_staging(
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
            )
            if reconstructed is None:
                raise StagedObservationNotFoundError(
                    provider_route_id,
                    delivery_id,
                    "staging authority disappeared during host completion",
                )
            acquisition, _ = reconstructed
            expected_delivery = CustodiedDelivery(
                provider_route_id=acquisition.identity.provider_route_id,
                custody_generation=acquisition.custody_generation,
                webhook=acquisition.webhook,
                quarantined=acquisition.quarantined,
            )
            receipt = HostDeliveryCompletionReceipt(
                provider_route_id=provider_route_id,
                delivery_id=delivery_id,
                custody_generation=acquisition.custody_generation,
                subject=folded.subject,
                instance_id=folded.instance_id,
                bridge_identity=folded.bridge_identity,
                manifest_id=str(folded.manifest_id),
                grant_id=str(folded.grant_id),
                manifest_digest=folded.manifest_digest,
                entry_order=folded.entry_order,
                observation_key=str(folded.observation_key),
                history_delivery_identity=str(folded.delivery_identity),
                occurrence=folded.occurrence,
            )
            return self._completion_custody.record_completion(
                receipt,
                expected_delivery=expected_delivery,
            )

        return self._catalog.run_readiness_authority(subject, complete)
