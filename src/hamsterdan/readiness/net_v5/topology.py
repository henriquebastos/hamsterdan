"""V5 actor-loop executable topology for one PR-readiness Instance.

The V5 discipline (ES-007, CV17): one concern = one loop = one memory
baton plus mailbox places; cross-loop influence is mailed facts only;
zero guards, zero read arcs, zero CEL filters, zero unowned places.
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

from hamsterdan.contracts.readiness_v5 import (
    CloseFact,
    GateFact,
    IntentFact,
    MutationRequest,
)
from hamsterdan.readiness.net_v5 import ci, esc, life, review

_LOOPS = (life, ci, esc, review)

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


def _declare_pending_mailboxes(s) -> None:
    """Mailboxes owned by loops that have not landed yet (CV17.DS1).

    This section shrinks as each loop module arrives and declares its
    own places; it exists so already-landed loops can mail complete
    facts from the first slice on.
    """
    s.conv.p.intents(IntentFact)
    s.mut.p.requests(MutationRequest)
    s.mut.p.closed(CloseFact)
    s.dash.p.facts(GateFact)
    s.dash.p.closed(CloseFact)
    s.rem.p.closed(CloseFact)
    s.ready.p.facts(GateFact)
    s.ready.p.closed(CloseFact)


def build_net_v5() -> BuiltNet:
    net = NetSpec("pr_v5")
    for loop in _LOOPS:
        loop.declare(net.s)
    _declare_pending_mailboxes(net.s)
    for loop in _LOOPS:
        loop.wire(net)
    return net.build()


def seed_marking() -> Marking:
    """The newborn Instance: every loop starts with its baton in place."""
    contributions: dict = {}
    for loop in _LOOPS:
        for path, tokens in loop.seed().items():
            if path in contributions:
                raise ValueError(f"duplicate seed contribution for {path}")
            contributions[path] = tokens
    return Marking(contributions)
