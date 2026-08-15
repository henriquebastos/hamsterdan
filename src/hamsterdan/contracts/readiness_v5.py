"""JSON-faithful values for the V5 actor-loop PR-readiness workflow.

V5 tokens fall into three families, mirroring the ES-007 discipline:

- ingress observations: host-normalized events delivered through doors;
- batons: one private memory value per concern loop;
- directed facts: dedicated colors mailed loop-to-loop through mailbox
  places — the only cross-loop influence that exists.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from hamsterdan.contracts.readiness import WorkflowModel

Phase = Literal["running", "quiescent", "terminal"]
HeadRelation = Literal["new", "superseded", "confirmed", "resumed", "refreshed"]


# -- ingress observations (host-normalized) --------------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HeadSeen(WorkflowModel):
    head: str
    base: str
    mergeable: bool
    policy: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class DraftSeen(WorkflowModel):
    pass


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ReadySeen(WorkflowModel):
    pass


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CloseSeen(WorkflowModel):
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CommentSeen(WorkflowModel):
    id: str
    kind: str
    arg: str
    authorized: bool


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HumanSeen(WorkflowModel):
    approval: bool
    changes_requested: bool
    unresolved: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RunSeen(WorkflowModel):
    head: str
    run_id: int
    attempt: int
    conclusion: str
    fingerprint: str


# -- batons (one private memory value per loop) -----------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class LifeState(WorkflowModel):
    phase: Phase
    incarnation: int
    head: str
    base: str
    mergeable: bool
    policy: str
    expected: str
    expected_op: str
    lineage: str


# -- directed facts (loop -> loop, dedicated colors) -------------------------


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class HeadWork(WorkflowModel):
    incarnation: int
    head: str
    base: str
    policy: str
    relation: HeadRelation
    lineage: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class IntentFact(WorkflowModel):
    id: str
    kind: str
    arg: str
    authorized: bool
    phase: Phase
    provisional: bool
    incarnation: int
    head: str
    base: str
    policy: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CloseFact(WorkflowModel):
    reason: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RunWork(WorkflowModel):
    incarnation: int
    head: str
    run_id: int
    attempt: int
    conclusion: str
    fingerprint: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ProvisionalHead(WorkflowModel):
    expected: str
    op: str
    lineage: str


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class GateFact(WorkflowModel):
    kind: str
    incarnation: int
    body: dict[str, Any]
