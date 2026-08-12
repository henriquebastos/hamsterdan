"""AX20 — a function-like sound subnet: claim, run linearly, fence once.

The Navigator's model: a subnet should behave like a function call.
Entry admits and *claims*; the interior is a linear pipe with no shared-
state reads; one exit fences the moving authority exactly once and
either commits the result or discards the whole run. Work is cheap —
"we don't have to save work; simplicity first" — so a stale run is
thrown away wholesale and the process restarts with fresh inputs.

The shape, in kernel notions only (AX19 boundary kernel):

    submit ──▶ intents                       authority (read at exits only)
                  │  ┌───── state (the concern's one token)
                  ▼  ▼
               [claim]  routing is a per-token ARC FILTER; the mutex is
                  │ │   STRUCTURAL: claim consumes the state token and
                  │ │   holds it, so the empty state place blocks every
                  ▼ ▼   rival entry — no change_in_flight flag anywhere
            accepted claimed
                  │
              [prepare]  the linear interior: pure transform, no guard,
                  │      no authority read, no state read
                  ▼
                draft
                 ╱ ╲
          [commit]  [discard]   the ONLY two authority readers, guards
            │  │      │  │      complementary — fence once, at the exit
            ▼  ▼      ▼  ▼
          work state  rejected state
                       (release unchanged: the run never happened)

Three of five transitions are handler-less token games (submit, claim,
discard route by color through frozen passthrough). Only the domain
transform (prepare) and the effect construction (commit) are code.

No Python model types anywhere: colors are nominal strings, tokens are
plain data — the whole pattern lives at the kernel layer.
"""

from __future__ import annotations

from ax19_kernel import (
    BoundaryNet,
    BoundaryTransition,
    KernelPlace,
    PetriWork,
    boundary_net,
    consume,
    produce,
    read,
)
from petrus.impetus.petrinet import NetPath, Token

#: The exit fence, rendered once and negated for the discard branch:
#: the draft carries the authority snapshot it was built against.
FENCE = "draft[0].data.epoch == authority[0].data.epoch && draft[0].data.head == authority[0].data.head"


def _prepare(binding, outputs):
    """The linear interior: intent -> draft, a pure transform that
    snapshots the authority coordinates the intent was issued under."""
    del outputs
    [token] = binding.tokens
    intent = token.data
    draft = {"epoch": intent["epoch"], "head": intent["head"], "payload": f"change:{intent['kind']}"}
    return {NetPath("draft"): (Token("Draft", draft),)}


def _commit(binding, outputs):
    """The effect construction: emit the work request and release the
    state token updated — the only step that writes concern state."""
    del outputs
    by_color = {}
    for _, selected in (*binding.consumed, *binding.read):
        for token in selected:
            by_color[token.color] = token.data
    draft, state = by_color["Draft"], by_color["State"]
    work = {"operation": draft["payload"], "epoch": draft["epoch"], "head": draft["head"]}
    released = {"committed": state["committed"] + 1}
    return {
        NetPath("work"): (Token("Work", work),),
        NetPath("state"): (Token("State", released),),
    }


def change_subnet() -> BoundaryNet:
    return boundary_net(
        "ax20-change-subnet",
        KernelPlace("intents", "Intent"),
        KernelPlace("state", "State"),
        KernelPlace("authority", "Authority"),
        KernelPlace("accepted", "Intent"),
        KernelPlace("claimed", "State"),
        KernelPlace("draft", "Draft"),
        KernelPlace("work", "Work"),
        KernelPlace("rejected", "Draft"),
        # the delivery door: how fresh intents arrive, including restarts
        BoundaryTransition(name="submit", arcs=(produce("intents"),)),
        # entry gate: ROUTE (per-token arc filter) + CLAIM (structural
        # mutex) — no authority knowledge, no in-flight flags, no
        # handler. The filter is the right routing primitive: a
        # non-matching intent never binds and never blocks the queue.
        BoundaryTransition(
            name="claim",
            arcs=(
                consume("intents", filter='kind == "update_base"'),
                consume("state"),
                produce("accepted"),
                produce("claimed"),
            ),
            label="admit a change intent and take the concern's state token",
        ),
        # linear interior: pure, guardless, reads nothing shared
        BoundaryTransition(
            name="prepare",
            arcs=(consume("accepted"), produce("draft")),
            work=PetriWork(_prepare),
            label="build the change draft — disposable work",
        ),
        # the exits: the only authority readers, complementary guards
        BoundaryTransition(
            name="commit",
            arcs=(read("authority"), consume("draft"), consume("claimed"), produce("work"), produce("state")),
            guard=FENCE,
            work=PetriWork(_commit),
            label="fence once; emit the effect; release the state updated",
        ),
        BoundaryTransition(
            name="discard",
            arcs=(read("authority"), consume("draft"), consume("claimed"), produce("rejected"), produce("state")),
            guard=f"!({FENCE})",
            label="authority moved mid-flight: throw the run away, release the claim unchanged",
        ),
    )


def intent(epoch: str, head: str, kind: str = "update_base") -> Token:
    return Token("Intent", {"epoch": epoch, "head": head, "kind": kind})


def authority(epoch: str, head: str) -> Token:
    return Token("Authority", {"epoch": epoch, "head": head})


def state(committed: int = 0) -> Token:
    return Token("State", {"committed": committed})


def draft(epoch: str, head: str, payload: str = "change:update_base") -> Token:
    return Token("Draft", {"epoch": epoch, "head": head, "payload": payload})
