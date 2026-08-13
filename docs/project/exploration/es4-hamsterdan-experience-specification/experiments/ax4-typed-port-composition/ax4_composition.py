"""ES-004 AX4 — two subnets compose through typed named ports, and
the control layer never becomes a place.

The question left planned since AX1: do independently authored
subnets compose at their contract boundary WITHOUT a shared control
place? Production says no — its concerns meet in the marking:
`topology.py` has 28 read arcs, ~19 of them reading `p.authority`,
plus `p.mutation_state`, `p.actions_state`, `p.review_state` — every
concern leans on ambient places to know whether it may act.

The composed answer, using only settled pieces:

    AX3 shape M (mutation)      then(…, on="committed")     AX3 comment gate
    prepare → agent → CAS gate ──────────────────────────▶ announce → post
                                 typed port fusion:
                                 ProvisionalHead → (pure adapter)
                                 → FindingPublicationRequest

and the loop back through control is DATA, not a place:

    AX7 service(Running, "change")      → Execute(epoch, head)   [port in]
    shape M exit "committed"            → CommitGateFired(head)  [port out]
    AX6 step(state, CommitGateFired)    → Quiescent(expected)
    AX6 step(…, ObservedOpen(expected)) → Running(epoch+1) "confirmed"

Where production serializes mutations with `MutationState.
change_in_flight` (a flag in a shared place, read-arced into
authorize_change, topology.py:1426/1672), here the SAME guarantee
falls out of the control state: while Quiescent(expected=…) the AX7
service declines further head-bound work — no place, no read arc,
no flag.

One genuine finding surfaced by composing (not designable in
isolation): port fusion checks COLORS, but downstream handlers also
need PAYLOAD fields. `ProvisionalHead` carries {provisional_head,
reused} and no `operation`, while the comment marker wants (kind,
operation, head). The adapter below derives its marker from the head
alone; the lesson — exit payloads are part of the port contract, and
color-compatibility alone cannot promise field-compatibility — is
recorded in the experiment doc rather than patched over.
"""

from __future__ import annotations

from ax3_attempt_first import fresh_world, mutation_subnet, publish_comment
from ax23_blocks import Block, then, transform

__all__ = ["announce_commit", "fresh_world", "mutation_with_announcement"]


def announce_commit() -> Block:
    """Pure adapter between the two subnets' vocabularies: the
    committed payload becomes a publication request announcing the
    new head. This is the ONLY thing standing between the subnets —
    a function, not a place."""

    def draft(committed: dict) -> dict:
        head = committed["provisional_head"]
        return {"operation": f"announce-{head}", "head": head}

    return transform(
        "announce_commit",
        draft,
        accepts="ProvisionalHead",
        returns="FindingPublicationRequest",
    )


def mutation_with_announcement(world: dict) -> Block:
    """The composed net: shape M's `committed` exit fuses into the
    comment gate through the adapter. Every other exit (`moved`,
    `fault`, `failed`) survives untouched — composition consumes one
    named port and leaves the rest of the contract alone."""

    announced = then(mutation_subnet(world), announce_commit(), on="committed")
    return then(announced, publish_comment(world), on="out")
