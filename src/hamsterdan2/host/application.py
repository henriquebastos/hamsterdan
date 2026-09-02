# Copyright (c) 2026 Henrique Bastos

"""Host-owned operations over PR workflows, Webhook Inbox, and Readiness."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hamsterdan2.github_app.webhooks import GitHubWebhookNormalizer, WebhookRefusalError
from hamsterdan2.host.values import InboxAuthorization, InboxDelivery
from hamsterdan2.host.webhook_inbox import (
    ProviderRouteNotConfiguredError,
    WebhookInbox,
    WebhookInboxDeliveryNotFoundError,
)
from hamsterdan2.readiness.intake_values import IntakeResult, ObservationCompletion, PolicyRevision
from hamsterdan2.readiness.runtime import prepare_intake
from hamsterdan2.readiness.workflow_bridge import UnsupportedHeadObservationError, WorkflowBridgeError


if TYPE_CHECKING:
    from collections.abc import Callable

    from hamsterdan2.github_app.models import DeliveryId, NormalizedPullRequestWebhook, ProviderRouteId
    from hamsterdan2.host.pr_workflows import PullRequestWorkflows
    from hamsterdan2.host.values import OpenPullRequestCommand, PullRequestWorkflow
    from hamsterdan2.readiness.intake_values import PreparedIntake
    from hamsterdan2.readiness.runtime import HistoryAcceptance, ReadinessRuntime
    from hamsterdan2.workflow.values import AwaitingObservation, PullRequestIdentity


class Hamsterdan:
    """Open one PR workflow through the concrete host composition."""

    def __init__(
        self,
        *,
        workflows: PullRequestWorkflows,
        open_readiness: Callable[[PullRequestWorkflow], AwaitingObservation],
    ) -> None:
        self._workflows = workflows
        self._open_readiness = open_readiness

    def open_pull_request(self, command: OpenPullRequestCommand) -> PullRequestWorkflow:
        return self._workflows.open(command, self._open_readiness)


class WebhookInboxWorker:
    """Normalize and offer one selected inbox delivery without running in HTTP."""

    def __init__(
        self,
        *,
        inbox: WebhookInbox,
        normalizer: GitHubWebhookNormalizer,
        policy_revision: PolicyRevision,
        readiness_for: Callable[[PullRequestWorkflow], ReadinessRuntime],
    ) -> None:
        self._inbox = inbox
        self._normalizer = normalizer
        self._policy_revision = policy_revision
        self._readiness_for = readiness_for

    def process_delivery(self, delivery_id: DeliveryId) -> IntakeResult:
        prior = self._inbox.result(delivery_id)
        if prior is not None:
            return prior
        selected = self.selected_delivery(delivery_id)
        authorized = self.authorized_delivery(selected)
        if isinstance(authorized, IntakeResult):
            return authorized
        return self._inbox.record_in_history(delivery_id, self.accept_to_history)

    def authorized_delivery(self, selected: InboxDelivery) -> InboxDelivery | IntakeResult:
        if selected.intake_authorized:
            return selected
        authorization = self.authorization_for(selected)
        if isinstance(authorization, IntakeResult):
            return authorization
        return self._inbox.authorize(authorization)

    def accept_to_history(
        self,
        workflow: PullRequestWorkflow,
        exact_prepared: PreparedIntake,
    ) -> HistoryAcceptance:
        return self._readiness_for(workflow).accept(workflow, exact_prepared)

    def selected_delivery(self, delivery_id: DeliveryId) -> InboxDelivery:
        delivery = self._inbox.delivery(delivery_id)
        if delivery is None:
            raise WebhookInboxDeliveryNotFoundError(delivery_id)
        return delivery

    def normalize_or_reject(self, delivery: InboxDelivery) -> NormalizedPullRequestWebhook | IntakeResult:
        try:
            return self._normalizer.normalize(delivery.verified)
        except WebhookRefusalError as error:
            return self._inbox.reject(delivery.verified.delivery_id, reason=error.reason)

    def route_or_reject(
        self,
        delivery: InboxDelivery,
        normalized: NormalizedPullRequestWebhook,
    ) -> ProviderRouteId | IntakeResult:
        try:
            return self._inbox.provider_route_id(normalized)
        except ProviderRouteNotConfiguredError:
            return self._inbox.reject(
                delivery.verified.delivery_id,
                reason="route_not_configured",
                normalized=normalized,
            )

    def prepare_or_reject(
        self,
        delivery: InboxDelivery,
        normalized: NormalizedPullRequestWebhook,
    ) -> PreparedIntake | IntakeResult:
        try:
            return prepare_intake(
                normalized,
                policy_revision=self._policy_revision,
            )
        except UnsupportedHeadObservationError:
            return self._inbox.reject(
                delivery.verified.delivery_id,
                reason="unsupported_head_lifecycle",
                normalized=normalized,
            )
        except WorkflowBridgeError:
            return self._inbox.reject(
                delivery.verified.delivery_id,
                reason="workflow_projection_rejected",
                normalized=normalized,
            )

    def authorization_for(self, delivery: InboxDelivery) -> InboxAuthorization | IntakeResult:
        normalized = self.normalize_or_reject(delivery)
        if isinstance(normalized, IntakeResult):
            return normalized
        route = self.route_or_reject(delivery, normalized)
        if isinstance(route, IntakeResult):
            return route
        prepared = self.prepare_or_reject(delivery, normalized)
        if isinstance(prepared, IntakeResult):
            return prepared
        return InboxAuthorization(
            delivery_id=delivery.verified.delivery_id,
            body_digest=delivery.body_digest,
            provider_route_id=route,
            normalized=normalized,
            prepared=prepared,
        )


class PullRequestAuthority:
    """Drive one History-owned observation occurrence for one PR identity."""

    def __init__(
        self,
        *,
        workflows: PullRequestWorkflows,
        readiness_for: Callable[[PullRequestWorkflow], ReadinessRuntime],
    ) -> None:
        self._workflows = workflows
        self._readiness_for = readiness_for

    def complete_next_observation(self, pr_identity: PullRequestIdentity) -> ObservationCompletion:
        def complete(workflow: PullRequestWorkflow) -> ObservationCompletion:
            return self._readiness_for(workflow).complete_next(workflow)

        return self._workflows.run_authority(pr_identity, complete)
