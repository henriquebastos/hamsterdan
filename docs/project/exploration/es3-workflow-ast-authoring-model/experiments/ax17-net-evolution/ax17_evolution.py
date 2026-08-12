"""AX17 — net evolution: one instance history, two same-name compositions.

The generic question (any compiled net, not this workflow): when is
``Instance.resume(net', history)`` sound for a net' that is not the net
the history was recorded under? Petrus's resume door audits **live
state only**: the recorded net *name* must match the supplied net's,
live tokens must sit on places the net has, armed registrations on its
source transitions, and in-flight occurrences on its transitions with
binding shapes its arcs could have minted. Ended records are
deliberately not audited (whole-trace auditing is a validation-layer
posture — the door's own docstring, kernel debt
2026-07-09T2310Z).

Two compositions of the committed fragments under ONE name — the name
is what makes them versions of the same process rather than foreign
traces:

- ``narrow()``  — AX11 base + AX14 change concern;
- ``full()``    — the same plus AX15's recovery concern.

Both are ordinary values built from the untouched fragment sources; the
only authored delta between the two process versions is one argument to
``compose``.
"""

from __future__ import annotations

from ax11_fragment import conversation_intents
from ax14_compose import ComposedNet, compose
from ax14_fragments import change_concern
from ax15_recovery import recovery_concern

#: One name, two structures: Petrus records the net name in
#: InstanceCreated and refuses resume under any other — so the name is
#: the process identity and versioning must live elsewhere.
NET_NAME = "conversation-intents"


def narrow() -> ComposedNet:
    """The process before the recovery concern exists."""
    return compose(NET_NAME, conversation_intents(), change_concern())


def full() -> ComposedNet:
    """The same process after the recovery concern is composed in."""
    return compose(NET_NAME, conversation_intents(), change_concern(), recovery_concern())


def renamed_full() -> ComposedNet:
    """The same structure under a different name — a foreign trace to
    any history recorded under ``NET_NAME``."""
    return compose("conversation-intents-v2", conversation_intents(), change_concern(), recovery_concern())
