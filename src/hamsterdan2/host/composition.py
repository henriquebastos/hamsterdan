# Copyright (c) 2026 Henrique Bastos

"""Concrete composition admitted by the first CV21 tracer."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from hamsterdan2.host.application import Hamsterdan
from hamsterdan2.host.catalog import HostCatalog
from hamsterdan2.readiness.runtime import build_readiness_runtime


if TYPE_CHECKING:
    from pathlib import Path

    from hamsterdan2.host.values import RegisteredPullRequest
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
