"""The workflow's internal mail: loop-to-loop facts (spike, reduced).

Provenance: reduced field sets from src/hamsterdan/contracts/readiness_v5.py
at 0686067.
"""

from __future__ import annotations

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from workflow.observations import RunConclusion
from workflow.values import WorkflowModel


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HeadWork(WorkflowModel):
    """Life -> CI: one admitted head with its authority tuple."""

    head: str
    base: str
    policy: str
    incarnation: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RunWork(WorkflowModel):
    """Life -> CI: one normalized run observation."""

    head: str
    run_id: int
    attempt: int
    conclusion: RunConclusion
    fingerprint: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ChecksFailure(WorkflowModel):
    """CI -> escalation: the newest run failed under this authority."""

    fingerprint: str
    head: str
    base: str
    policy: str
    incarnation: int
    run_id: int
    attempt: int


TOKENS: tuple[type, ...] = (HeadWork, RunWork, ChecksFailure)
