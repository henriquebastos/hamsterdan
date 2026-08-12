"""AX21 — typed effect outcomes: the at-least-once boundary classified.

The Navigator's two idempotencies, made net structure. Kind one — "if
I did this before, don't do it again" — is the delivery door's
operation-identity dedup (AX19). Kind two — "if I did this before, it
will now *fail*, so how do I know?" — is lookup-first classification
at the effect itself, and the answer is not an exception: it is a
**typed outcome routed by color** (the AX5 finding, aimed at failure).

The external effect returns one of four outcomes, and each is a place:

    Applied          the effect landed now — proceed
    AlreadyApplied   lookup found my earlier attempt — a success
                     wearing an error's clothes; adopt it, proceed
    Stale            preconditions changed — not an error either:
                     discard the run (the AX20 ruling), restart fresh
    Transient        a real fault, worth retrying — the only outcome
                     that loops

The shape (one entry, three typed exits — a function signature,
`apply : Work → Done | Rejected | Exhausted` — the fractal again):

    submit ──▶ requests ◀────────────┐
                  │                  │ retry (attempts < 3)
               [apply]  the ONLY ledger toucher; classifies via
                  │     lookup-first: already? stale? faulted? applied.
      ┌────────┬──┴─────┬─────────┐
      ▼        ▼        ▼         ▼
   applied  already_  stale   transient
      │     applied     │        │ │
   [finish] [adopt] [abandon] [retry] [give_up]  (guards complementary)
      │        │        │        │        │
      ▼        ▼        ▼        ▼        ▼
     done     done   rejected requests exhausted

Classification order is the doctrine, stated as code: **lookup answers
before preconditions**. An operation applied under an old base and
redelivered after the base moved is AlreadyApplied, not Stale — the
work exists; the world merely moved on afterward.

No Python model types: colors are nominal strings, tokens plain dicts,
the whole boundary lives at the kernel layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ax19_kernel import (
    BoundaryNet,
    BoundaryTransition,
    KernelPlace,
    PetriWork,
    boundary_net,
    consume,
    produce,
)
from petrus.impetus.petrinet import NetPath, Token

MAX_RETRIES = 3

#: The retry guard, rendered once and negated for exhaustion — the
#: AX20 complement discipline: exclusivity constructive, not policed.
RETRY = f"transient[0].data.attempts < {MAX_RETRIES}"


@dataclass
class Ledger:
    """A fake external system with the three real behaviors: a
    compare-and-swap base, an operation-identity record (the lookup
    target), and a scheduled run of transient faults."""

    base: str = "e1"
    faults: int = 0
    applied: dict[str, str] = field(default_factory=dict)
    invocations: int = 0

    def apply(self, op: str, base: str, payload: str) -> str:
        self.invocations += 1
        if op in self.applied:  # lookup-first: before any precondition
            return "already"
        if base != self.base:  # compare-and-swap: the moved base
            return "stale"
        if self.faults > 0:  # a genuine, retryable fault
            self.faults -= 1
            return "transient"
        self.applied[op] = payload
        return "applied"


_ROUTES = {
    "applied": ("applied", "Applied"),
    "already": ("already_applied", "AlreadyApplied"),
    "stale": ("stale", "Stale"),
    "transient": ("transient", "Transient"),
}


def _apply(ledger: Ledger):
    def handler(binding, outputs):
        del outputs
        [token] = binding.tokens
        work = token.data
        outcome = ledger.apply(work["op"], work["base"], work["payload"])
        place, color = _ROUTES[outcome]
        return {NetPath(place): (Token(color, dict(work)),)}

    return handler


def _recolor(place: str, color: str, **extra):
    """A pure transform: same data, new color — the typed exits."""

    def handler(binding, outputs):
        del outputs
        [token] = binding.tokens
        return {NetPath(place): (Token(color, {**token.data, **extra}),)}

    return handler


def _retry(binding, outputs):
    del outputs
    [token] = binding.tokens
    return {NetPath("requests"): (Token("Work", {**token.data, "attempts": token.data["attempts"] + 1}),)}


def effect_boundary(ledger: Ledger) -> BoundaryNet:
    return boundary_net(
        "ax21-effect-boundary",
        KernelPlace("requests", "Work"),
        KernelPlace("applied", "Applied"),
        KernelPlace("already_applied", "AlreadyApplied"),
        KernelPlace("stale", "Stale"),
        KernelPlace("transient", "Transient"),
        KernelPlace("done", "Done"),
        KernelPlace("rejected", "Rejected"),
        KernelPlace("exhausted", "Exhausted"),
        # the delivery door: kind-one idempotency lives here (identity dedup)
        BoundaryTransition(name="submit", arcs=(produce("requests"),)),
        # the boundary: the only transition that touches the outside world
        BoundaryTransition(
            name="apply",
            arcs=(
                consume("requests"),
                produce("applied"),
                produce("already_applied"),
                produce("stale"),
                produce("transient"),
            ),
            work=PetriWork(_apply(ledger)),
            label="execute the effect; classify the outcome — never raise",
        ),
        # the typed exits: two successes converge, one discard, one loop
        BoundaryTransition(
            name="finish",
            arcs=(consume("applied"), produce("done")),
            work=PetriWork(_recolor("done", "Done", mode="applied")),
            label="the effect landed now",
        ),
        BoundaryTransition(
            name="adopt",
            arcs=(consume("already_applied"), produce("done")),
            work=PetriWork(_recolor("done", "Done", mode="adopted")),
            label="a success wearing an error's clothes: adopt the prior result",
        ),
        BoundaryTransition(
            name="abandon",
            arcs=(consume("stale"), produce("rejected")),
            work=PetriWork(_recolor("rejected", "Rejected")),
            label="preconditions changed: not an error — discard, restart fresh",
        ),
        BoundaryTransition(
            name="retry",
            arcs=(consume("transient"), produce("requests")),
            guard=RETRY,
            work=PetriWork(_retry),
            label="the only looping outcome: a genuine transient fault",
        ),
        BoundaryTransition(
            name="give_up",
            arcs=(consume("transient"), produce("exhausted")),
            guard=f"!({RETRY})",
            work=PetriWork(_recolor("exhausted", "Exhausted")),
            label="retries spent: surface the fault, stop looping",
        ),
    )


def work(op: str, base: str = "e1", payload: str = "change", attempts: int = 0) -> Token:
    return Token("Work", {"op": op, "base": base, "payload": payload, "attempts": attempts})
