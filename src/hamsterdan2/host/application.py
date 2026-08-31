# Copyright (c) 2026 Henrique Bastos

"""Bounded replacement-host operations over durable catalog custody."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable

    from hamsterdan2.host.catalog import HostCatalog
    from hamsterdan2.host.values import HostRecord, OpenPullRequestCommand, RegisteredPullRequest
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
