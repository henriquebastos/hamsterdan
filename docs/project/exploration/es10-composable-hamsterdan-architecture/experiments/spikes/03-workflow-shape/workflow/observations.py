"""Everything the host may assert to the workflow (spike, reduced).

Provenance: reduced field sets from src/hamsterdan/contracts/readiness_v5.py
at 0686067.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from workflow.values import WorkflowModel

RunConclusion = Literal["queued", "in_progress", "success", "failure"]


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HeadSeen(WorkflowModel):
    head: str
    base: str
    policy: str
    incarnation: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RunSeen(WorkflowModel):
    head: str
    run_id: int
    attempt: int
    conclusion: RunConclusion
    fingerprint: str


TOKENS: tuple[type, ...] = (HeadSeen, RunSeen)
