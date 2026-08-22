"""V5 actor-loop executable topology for one PR-readiness Instance.

The V5 discipline (ES-007, CV17): one concern = one loop = one memory
baton plus mailbox places; cross-loop influence is mailed facts only;
zero guards, zero read arcs, zero unowned places. CEL filters exist only
on readiness's input-only migration branches for pre-promotion envelope
facts. Readiness also carries LOOP-INTERNAL inhibit arcs on its own
mailboxes: they make authority and producer ordering explicit and allow
an announce only from a snapshot that has folded every fact already
mailed to it. These are structural preconditions, not cross-loop control
places.
Every decision is a pure fold on token data. Ingress doors are the only
no-input transitions; the engine's identified delivery is the only
deduplication anywhere.

Each actor loop lives in its own module and owns three surfaces:
`declare(s)` for its places, `wire(net)` for its transitions, and
`seed()` for its baton's contribution to the newborn marking. This
composer declares all places first, then wires all loops, so any loop
may mail into any sibling mailbox.
"""

from __future__ import annotations

from petrus.impetus.dsl import BuiltNet, NetSpec
from petrus.impetus.petrinet import Marking

from hamsterdan.readiness.net_v5 import ci, conversation, dashboard, esc, life, mutation, readiness, reminders, review

_LOOPS = (life, ci, esc, review, mutation, conversation, dashboard, reminders, readiness)

# transition path -> (activity name, declared variant colors), for every
# gate in the composed topology; the host (or a test world) binds these
# with gating.wire_gates
GATES: dict = {}
for _loop in _LOOPS:
    GATES.update(getattr(_loop, "GATES", {}))

# transition path -> activity name, for single-output (derived) gates
DERIVED: dict = {}
for _loop in _LOOPS:
    DERIVED.update(getattr(_loop, "DERIVED", {}))


def build_net_v5() -> BuiltNet:
    net = NetSpec("pr_v5")
    for loop in _LOOPS:
        loop.declare(net.s)
    for loop in _LOOPS:
        loop.wire(net)
    return net.build()


def seed_marking(subject: str, *, reminder_delay_s: int = 3 * 24 * 60 * 60) -> Marking:
    """The newborn Instance, bound to one globally unique host subject."""
    if (
        not isinstance(subject, str)
        or not subject
        or len(subject.encode()) > 900
        or not subject.isascii()
        or not subject.isprintable()
    ):
        raise ValueError("V5 workflow subject is malformed")
    contributions: dict = {}
    for loop in _LOOPS:
        if loop in (review, reminders):
            seeded = loop.seed(subject)
        elif loop is life:
            seeded = loop.seed(reminder_delay_s)
        else:
            seeded = loop.seed()
        for path, tokens in seeded.items():
            if path in contributions:
                raise ValueError(f"duplicate seed contribution for {path}")
            contributions[path] = tokens
    return Marking(contributions)
