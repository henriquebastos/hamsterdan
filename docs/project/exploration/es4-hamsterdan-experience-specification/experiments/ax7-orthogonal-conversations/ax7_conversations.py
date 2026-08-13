"""ES-004 AX7 — conversations are orthogonal to the head machine.

Navigator hunch under test: any message to the agent looks at the
current state of the repo and answers — questions ("why is this this
way?", "who did it?") do not depend on the PR head being current, on
draft status, or even on the PR being open. Coupling every intent to
authority is inherited, not necessary.

The inherited coupling, concretely: production stamps EVERY classified
intent with the authority epoch and head (contracts/readiness.py:
417-421 — Intent.epoch, Intent.head), even ``reply`` and ``status``.
A head-stamped question goes stale when authority does, which is the
only reason AX6 needed a Hold.

The claim: the 12 production intent kinds (readiness.py:421-434) split
into three effect grades, and only one grade touches the head machine:

    read_only     answer from the repo as it is NOW; no authority,
                  no epoch stamp, serviceable in ANY control state —
                  including Terminal (GitHub accepts comments on
                  closed PRs; "why did X do Y" outlives the merge)
    durable_note  acts on finding/reminder lineage, which production
                  already carries ACROSS generations
                  (host/application.py:346-347: findings and
                  finding_lineage survive GenerationStart) — so these
                  need a live instance, not a current head
    head_bound    work on a specific head; requires Running, and the
                  Execute is stamped with the epoch/head it ran under

And the resolution of AX6's open question: NOTHING is ever parked.
Read-only intents are answered immediately; a head_bound request that
cannot run gets an immediate explanatory reply (attempt-first — AX3
verified comments always land) and the human re-asks when ready.
Hold, replay-on-resume, and expiry all disappear.

Capability note (Navigator scope choice): the conversation agent gets
READ-ONLY repo access. Write authority lives only in the mutation
subnet (AX1 shape M) that head_bound Execute routes into — a wandering
answer cannot push anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ax6_quiescence import Quiescent, Running, State, Terminal

# -- effect grades over the production intent vocabulary -------------------------------

type Grade = Literal["read_only", "durable_note", "head_bound"]

GRADE: dict[str, Grade] = {
    # answers from the repo as it stands; no durable trace beyond the comment
    "reply": "read_only",
    "status": "read_only",
    # durable finding/reminder state, keyed by lineage that already
    # survives generations — not by head
    "acknowledge": "durable_note",
    "dismiss": "durable_note",
    "defer": "durable_note",
    "snooze": "durable_note",
    "resume": "durable_note",
    "reassign": "durable_note",
    # work on a specific head; only these enter the head machine
    "change": "head_bound",
    "update_base": "head_bound",
    "resolve_conflict": "head_bound",
    "recover_publication": "head_bound",
}


# -- service outcomes (note: no Hold) ---------------------------------------------------


@dataclass(frozen=True)
class Answer:
    """Run the read-only conversation agent against the repo as it is
    now; post the reply attempt-first. Valid in every control state."""

    kind: str


@dataclass(frozen=True)
class Apply:
    """Fold a durable disposition into finding/reminder lineage and
    acknowledge. Needs a live instance; indifferent to head currency."""

    kind: str


@dataclass(frozen=True)
class Execute:
    """Route into the head-bound work subnet (AX1 shape M), stamped
    with the authority it runs under — the ONLY grade that carries an
    epoch/head, where production stamps all twelve kinds."""

    kind: str
    epoch: int
    head: str


@dataclass(frozen=True)
class Decline:
    """Immediate explanatory reply instead of parking. Attempt-first:
    the comment always lands (AX3), the human re-asks when ready.
    This replaces AX6's Hold — no queue, no replay-or-expire choice."""

    kind: str
    reason: str


type Outcome = Answer | Apply | Execute | Decline


# -- the whole conversation service ------------------------------------------------------


def service(state: State, kind: str) -> Outcome:
    """Pure function of (control state, intent kind). It never changes
    the control state and holds nothing — that is the orthogonality."""

    match GRADE[kind], state:
        case "read_only", _:
            return Answer(kind)  # any state, even Terminal

        case _, Terminal(status=status):
            return Decline(kind, f"the pull request is {status}")

        case "durable_note", (Running() | Quiescent()):
            return Apply(kind)

        case "head_bound", Running(epoch=epoch, head=head):
            return Execute(kind, epoch, head)

        case "head_bound", Quiescent(expected=expected):
            if expected is not None:
                return Decline(kind, "a just-pushed commit awaits observation; re-ask once the head updates")
            return Decline(kind, "the pull request is draft or its head was superseded; re-ask when it is active")

    raise AssertionError(f"unhandled: {kind} × {state}")
