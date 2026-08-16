"""Topology-neutral application boundary owned by the host service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from petrus.motus.activity import Activity, ActivityDefinition

from hamsterdan.contracts.readiness import AdmittedConversation
from hamsterdan.github_app.webhooks import Observation

DurableActivityResolver = Callable[[str, str, ActivityDefinition], Activity]


class ReadinessApplication(Protocol):
    """One PR workflow implementation behind durable webhook custody."""

    def process_observation(
        self,
        observation: Observation,
        *,
        conversation: AdmittedConversation | None = None,
    ) -> Any: ...

    def reconcile(self, reason: str) -> Any: ...

    def settle(self) -> Any: ...

    def activity(self, name: str) -> Any: ...

    def has_unresolved_publication(self) -> bool: ...

    def run_durable_activities(self, limit: int) -> int: ...

    def stop_durable_activities(self) -> None: ...

    def close(self) -> None: ...


__all__ = ["DurableActivityResolver", "ReadinessApplication"]
