"""ES-004 AX6 — unified quiescence: one stopped state, with an
optional expectation.

Navigator hunch under test: dormant-for-draft is a special case of a
general control state — "not running". Draft PRs, superseded
authority, and our own just-pushed commits all mean the same thing:
stop the machines, finalize/discard in-flight work, and wait for
ingress to announce the next authority. Resumption is always the same
move: a fresh generation at last_epoch + 1.

The unification claim, concretely:

    today                          proposed
    ─────────────────────────      ───────────────────────────────
    Dormant (draft only)           Quiescent(expected=None)
    MutationState.provisional      Quiescent(expected=head_we_pushed)
    supersession drain (inline)    quiesce → resume in one step
    (impossible: early discard     Quiescent on a CAS 'moved' exit,
     on known-stale authority)      before any webhook arrives

The control layer is modeled as a plain transition function over
values — it is the router, not a work subnet, so no net machinery is
needed here. Generation relations reuse production vocabulary
exactly: new | resumed | confirmed | superseded
(host/application.py:328-353).
"""

from __future__ import annotations

from dataclasses import dataclass

# -- control states (exactly three) --------------------------------------------------


@dataclass(frozen=True)
class Running:
    epoch: int
    head: str


@dataclass(frozen=True)
class Quiescent:
    """Stopped, waiting for ingress. ``expected`` is the one optional
    refinement: the head we ourselves pushed and now wait to observe.
    Draft dormancy and post-stale idling are the expected=None case."""

    last_epoch: int
    last_head: str
    expected: str | None = None


@dataclass(frozen=True)
class Terminal:
    status: str  # "merged" | "closed"
    last_epoch: int
    last_head: str


type State = Running | Quiescent | Terminal


# -- ingress events (the AX0 boundary vocabulary) --------------------------------------


@dataclass(frozen=True)
class ObservedOpen:
    """Reconciliation read the live PR: open, with this head."""

    head: str
    draft: bool = False


@dataclass(frozen=True)
class ObservedClosed:
    merged: bool


@dataclass(frozen=True)
class CommitGateFired:
    """Shape M's committed exit: we pushed; this is the head we expect
    to observe. (AX3: the gate itself was the fence.)"""

    provisional_head: str


@dataclass(frozen=True)
class StaleSignal:
    """We learned we are stale before any webhook: a CAS 'moved' exit.
    We know the world changed; we do not yet know the new authority."""


@dataclass(frozen=True)
class ConversationArrived:
    """An admitted @app comment while we may not be running."""


type Event = ObservedOpen | ObservedClosed | CommitGateFired | StaleSignal | ConversationArrived


# -- actions the control layer emits --------------------------------------------------


@dataclass(frozen=True)
class Drain:
    """Finalize in-flight work; discard everything stale; publish
    nothing new. The one stop ritual, shared by every entry into
    quiescence (today: three separate paths)."""


@dataclass(frozen=True)
class Resume:
    epoch: int
    head: str
    relation: str  # "new" | "resumed" | "confirmed" | "superseded"


@dataclass(frozen=True)
class Hold:
    """Ingress that cannot act now and must not be reinterpreted
    later: park it (the AX0 quarantine doctrine). Open question
    whether held conversations replay on resume or expire."""


@dataclass(frozen=True)
class Ignore:
    pass


type Action = Drain | Resume | Hold | Ignore


# -- admission: every PR enters the same machine ---------------------------------------


def admit(event: ObservedOpen | ObservedClosed) -> tuple[State, tuple[Action, ...]] | None:
    """First observation of a PR with no instance yet.

    Navigator hunch under test: ingress draft PRs too. A born-draft PR
    becomes a Quiescent instance from birth — the same stopped state
    it would reach by going draft later. Today production refuses to
    instantiate a draft (application.py:139-143 requires an existing
    host/seed), which makes 'born draft' and 'went draft' different
    code paths; here they are the same state.

    Consequence: with universal admission the `seed` bootstrap place
    (application.py:151, 380-386) has no role left — every instance is
    Running or Quiescent from its first observation. `new` then means
    exactly 'born ready'; a draft-born PR later marked ready resumes
    as `resumed`, which is honest: the instance did exist.
    """

    match event:
        case ObservedClosed():
            return None  # never admitted; nothing to remember
        case ObservedOpen(head, draft=True):
            return Quiescent(last_epoch=0, last_head=head), ()
        case ObservedOpen(head, draft=False):
            return Running(epoch=1, head=head), (Resume(1, head, "new"),)


# -- the whole control layer ----------------------------------------------------------


def step(state: State, event: Event) -> tuple[State, tuple[Action, ...]]:
    """One transition function; no special cases outside it."""

    match state, event:
        # Terminal absorbs everything (AX0: no boundary reactivation route).
        case Terminal(), _:
            return state, (Ignore(),)

        # Closing wins from any live state.
        case (Running(epoch, head) | Quiescent(epoch, head)), ObservedClosed(merged):
            return Terminal("merged" if merged else "closed", epoch, head), (Drain(),)

        # -- running ------------------------------------------------------------
        case Running(epoch, head), ObservedOpen(seen, draft=False) if seen == head:
            return state, (Ignore(),)  # same head: base/policy deltas stay in-generation (AX0)

        case Running(epoch, head), ObservedOpen(seen, draft=False):
            # supersession = quiesce + resume, one step, same drain ritual
            return Running(epoch + 1, seen), (Drain(), Resume(epoch + 1, seen, "superseded"))

        case Running(epoch, head), ObservedOpen(_, draft=True):
            return Quiescent(epoch, head), (Drain(),)

        case Running(epoch, head), CommitGateFired(expected):
            # provisional = quiescence with an expectation
            return Quiescent(epoch, head, expected), (Drain(),)

        case Running(epoch, head), StaleSignal():
            # early discard: we KNOW we're stale; stop before the webhook
            return Quiescent(epoch, head), (Drain(),)

        case Running(), ConversationArrived():
            return state, (Ignore(),)  # normal path: classify and route

        # -- quiescent ----------------------------------------------------------
        case Quiescent(epoch, head, expected), ObservedOpen(seen, draft=False):
            if seen == expected:
                return Running(epoch + 1, seen), (Resume(epoch + 1, seen, "confirmed"),)
            if seen == head and expected is not None:
                return state, (Ignore(),)  # stale-ordered webhook; our push not yet visible
            if seen == head:
                return Running(epoch + 1, seen), (Resume(epoch + 1, seen, "resumed"),)
            return Running(epoch + 1, seen), (Resume(epoch + 1, seen, "superseded"),)

        case Quiescent(), ObservedOpen(_, draft=True):
            return state, (Ignore(),)

        case Quiescent(), (CommitGateFired() | StaleSignal()):
            return state, (Ignore(),)  # late terminals of drained work change nothing

        case Quiescent(), ConversationArrived():
            return state, (Hold(),)  # parked, never reinterpreted (open: replay or expire)

    raise AssertionError(f"unhandled: {state} × {event}")
