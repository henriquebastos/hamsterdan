"""ES-004 AX12 — human observation folding: snapshots, notes, and dispositions.

AX5 MISSED #7, the last unspiked concern: approvals, dismissals, and
capability blocks. Production rules mirrored verbatim:

- `fold_human` (topology.py:347-362): a HumanObservation is a FULL
  SNAPSHOT of GitHub's review surface — every field replaced,
  last-write-wins, observation_sequence incremented;
- `fold_intent` for HumanState (topology.py:336-342): snooze/resume/
  reassign are field-level NOTES layered over the snapshots;
- `fold_intent` for ReviewState (topology.py:324-335): acknowledge/
  dismiss/defer rewrite finding dispositions and recompute blocking;
  unauthorized intents are inert; an "unable" review is never
  upgraded by dispositions;
- capability: `human_capability_blocking = not capability_available`
  — a provider-degradation fact (AX8's classification).

Two structural findings this spike is designed to surface:

1. WITHIN a concern, order is load-bearing. AX8 claimed fold
   commutativity only ACROSS independent concerns and noted "exits of
   the same concern are ordered by that concern's subnet" — the human
   concern is where that caveat earns its keep: two HumanObservation
   snapshots folded in opposite orders yield different states by
   design (last-write-wins). The event log's order IS the concern's
   order; refold is still deterministic.

2. Notes and snapshots collide, and production resolves the collision
   INCONSISTENTLY: `reminder_snoozed` (a note) survives the next
   observation — fold_human does not touch it — but
   `reminder_recipient` (also written by the reassign note) is
   CLOBBERED, because fold_human sets it from `value.reviewer`
   (topology.py:359). A human's reassignment silently lasts only
   until GitHub next reports the PR. This spike mirrors production
   exactly and flags the asymmetry as an OPEN product question
   rather than fixing it silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

# -- the human concern: snapshots + notes -----------------------------------------------------


@dataclass(frozen=True)
class Human:
    """HumanState's observation-owned and note-owned fields, phase-free:
    the human concern has no ladder — it is a mirror plus notes."""

    observation_sequence: int = 0
    requested: bool = False
    approved: bool = False
    changes_requested: bool = False
    unresolved_conversations: int = 0
    distinct_required: bool = False
    distinct_approved: bool = False
    mergeable: bool = False
    conflict: bool = False
    capability_blocking: bool = False
    reviewer: str = ""  # written by BOTH observations and the reassign note
    author: str = ""
    snoozed: bool = False  # written ONLY by notes — survives observations


@dataclass(frozen=True)
class HumanObserved:
    """GitHub's full snapshot (HumanObservation, contracts/readiness.py:377-393)."""

    requested: bool = False
    approved: bool = False
    changes_requested: bool = False
    unresolved_conversations: int = 0
    distinct_required: bool = False
    distinct_approved: bool = False
    mergeable: bool = True
    conflict: bool = False
    reviewer: str = ""
    author: str = ""
    capability_available: bool = True


@dataclass(frozen=True)
class Noted:
    """An authorized human intent, already graded by AX7's conversation
    pipeline: snooze | resume | reassign."""

    kind: str
    assignee: str = ""


def fold_human(human: Human, event: HumanObserved | Noted) -> Human:
    match event:
        case HumanObserved() as value:  # fold_human verbatim: replace everything it owns
            return replace(
                human,
                observation_sequence=human.observation_sequence + 1,
                requested=value.requested,
                approved=value.approved,
                changes_requested=value.changes_requested,
                unresolved_conversations=value.unresolved_conversations,
                distinct_required=value.distinct_required,
                distinct_approved=value.distinct_approved,
                mergeable=value.mergeable,
                conflict=value.conflict,
                reviewer=value.reviewer,  # ← clobbers a prior reassign note (production parity)
                author=value.author,
                capability_blocking=not value.capability_available,
                # snoozed untouched: the one note that survives observations
            )
        case Noted("snooze"):
            return replace(human, snoozed=True)
        case Noted("resume"):
            return replace(human, snoozed=False)
        case Noted("reassign", assignee):
            return replace(human, reviewer=assignee)
        case Noted():
            return human  # unknown note kinds are inert


# -- the review concern: dispositions --------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    id: str
    blocking: bool
    disposition: str = "new"  # new | still_open | acknowledge | dismiss | defer


@dataclass(frozen=True)
class Review:
    status: str = "pending"  # pending | clear | blocking | unable
    findings: tuple[Finding, ...] = field(default=())


@dataclass(frozen=True)
class Disposed:
    """An authorized acknowledge/dismiss/defer intent over named findings."""

    kind: str
    finding_ids: frozenset[str]
    authorized: bool = True


def _blocking(findings: tuple[Finding, ...]) -> bool:
    return any(f.blocking and f.disposition in {"new", "still_open"} for f in findings)


def fold_disposition(review: Review, intent: Disposed) -> Review:
    """fold_intent for ReviewState, verbatim (topology.py:324-335)."""
    if not intent.authorized or intent.kind not in {"acknowledge", "dismiss", "defer"}:
        return review
    findings = tuple(
        replace(f, disposition=intent.kind) if f.id in intent.finding_ids else f for f in review.findings
    )
    if _blocking(findings):
        status = "blocking"
    elif review.status in {"blocking", "clear"}:
        status = "clear"
    else:
        status = review.status  # "unable"/"pending" are never upgraded by dispositions
    return replace(review, status=status, findings=findings)


# -- the bridges into AX8's snapshot -----------------------------------------------------------


@dataclass(frozen=True)
class HumanSettled:
    """The concern exit AX8 consumes."""

    approved: bool
    changes_requested: bool
    unresolved_conversations: int


def settled(human: Human) -> HumanSettled:
    return HumanSettled(human.approved, human.changes_requested, human.unresolved_conversations)


def review_settled(review: Review) -> tuple[str, int]:
    """AX8's ReviewSettled payload: status plus blocking count."""
    return review.status, sum(1 for f in review.findings if f.blocking and f.disposition in {"new", "still_open"})
