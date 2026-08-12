"""AX14 — the composition scenario: AX11's base fragment, untouched, plus
the change concern as an independent hand-off fragment.

AX13 proved the change concern's *content* (predicate, update function,
lane body) against a production oracle, but delivered it by restating the
whole fragment: `conversation_intents_with_change()` re-authors every
lane, and its `TestFragmentsAreValues` shows the equivalent tree surgery.
Either way, growing a sibling concern meant rebuilding the base AST.

AX14 re-delivers the *same proven content* as a separate fragment value:

- The base is `conversation_intents()` **exactly as committed in AX11** —
  its `change_basis` lane still says `then=EXIT`.
- The change concern is a `handoff_fragment` whose entry *is* the same
  named port (`change_basis`), reusing AX13's `CHANGE_LANE_BODY`,
  `MUTATION_STATE`, and predicate verbatim.
- `compose()` joins them on the two explicitly shared names —
  `change_basis` (the hand-off) and `authority` (the shared read) —
  and on nothing else. Four Intent-colored ports stay distinct places.

If composition works, the AX13 monolith and this composition must be the
same net; that equivalence is the experiment's oracle.
"""

from __future__ import annotations

from ax11_fragment import AUTHORITY, CHANGE_BASIS, conversation_intents
from ax13_fragment import CHANGE_LANE_BODY, MUTATION_STATE
from ax14_compose import ComposedNet, compose, handoff_fragment


def change_concern():
    """The change concern as an independent value: entry is the shared
    hand-off port, context is the shared authority read plus the concern's
    own state. The body is AX13's proven lane body, unchanged."""
    return handoff_fragment(
        "change-intents",
        entry=CHANGE_BASIS,
        reads=(AUTHORITY,),
        states=(MUTATION_STATE,),
        body=CHANGE_LANE_BODY,
    )


def composed_conversation_and_change() -> ComposedNet:
    return compose("conversation-intents-change", conversation_intents(), change_concern())
