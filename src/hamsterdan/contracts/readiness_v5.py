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


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CiState(WorkflowModel):
    """The CI loop's baton: newest exact-head evidence plus budget lineage.

    `lineage` scopes the escalation ladder budget: fresh on new or
    superseded code, kept across our own confirmed repair and a resume.
    `best` is `[run_id, attempt]` of the winning run (empty until one
    lands). `parked` holds fingerprints whose escalation MOVED under the
    currently-held authority; the next refresh reissues them.
    """

    head: str
    base: str
    policy: str
    lineage: str
    incarnation: int
    best: tuple[int, int] | tuple[()]
    status: str
    fingerprint: str
    parked: tuple[str, ...]


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


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class ChecksFailure(WorkflowModel):
    """CI -> escalation: the newest run failed under this authority claim.

    The ladder budget is per fingerprint PER LINEAGE: the same flake on
    genuinely new code earns a fresh ladder; our own repair does not
    reset it.
    """

    fingerprint: str
    head: str
    base: str
    policy: str
    lineage: str
    incarnation: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class EscMoved(WorkflowModel):
    """Escalation -> CI echo: an escalation effect classified MOVED.

    Carries the ATTEMPTED authority tuple (head, base, policy, and the
    grant incarnation) so CI can decide between reissuing under an
    already-fresher admitted tuple and parking until the refresh folds.
    """

    fp: str
    head: str
    base: str
    policy: str
    incarnation: int


@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class CiEnded(WorkflowModel):
    """The CI loop's terminal record: final verdict at close."""

    status: str
    reason: str
