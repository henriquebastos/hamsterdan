"""AX25 — the failure rail: railway-oriented programming as visible sugar.

Composable Functions makes every function total by absorbing
exceptions into a binary ``Result`` — railway-oriented programming,
the success track and the failure track threaded through every
combinator. Our doctrine refuses hidden channels: nothing may flow
anywhere an author cannot see in the net. The hypothesis under test:

    The failure rail can be authoring SUGAR that expands into visible
    net structure — named failure places, ordinary merges, ordinary
    routing — with zero new kernel or algebra concepts.

Three pieces, all built from AX23 primitives alone:

- ``failure_data`` — the wire-safe envelope. Their ``SerializableError``
  still smuggles a live ``Error`` object whose useful fields evaporate
  under JSON; a durable failure token cannot afford that. This envelope
  is plain data by construction: kind, message, source (the block that
  failed), retryable, cause chain — every field a JSON scalar or
  nested plain structure.
- ``attempt`` — the total leaf, their ``composable()`` translated: run
  ``fn``; an exception becomes an envelope routed to a ``failed`` exit
  instead of crashing the transition. Expands to a plain ``classify``.
  A declared ``retryable`` exception tuple sets the envelope flag —
  the AX21 transient/terminal distinction decided where the exception
  is freshest.
- ``rail_then`` / ``recover`` — their ``pipe`` and ``catchFailure``.
  ``rail_then`` composes on the ok exit and *merges* the two ``failed``
  exits into one rail place (an ordinary AX23 ``merge`` — the rail IS
  a place, inspectable, on-path). ``recover`` routes the rail into a
  total handler block and merges the recovery back into the ok exit.

What the rail is for, stated once: **unexpected exceptions**. Domain
outcomes — Applied, Stale, Rejected — remain first-class typed exits
(AX21); routing them through a generic failure rail would erase
exactly the type information the algebra exists to keep. The rail
carries what nobody modeled; classify carries what somebody did.
"""

from __future__ import annotations

from collections.abc import Callable

from ax23_blocks import Block, CompositionError, classify, merge, rename_exit, then

#: The rail color. One color for every rail place so merges are lawful
#: and one recover handler can serve any upstream.
FAILURE = "Failure"

#: Reserved temporary exit names used while the sugar rearranges rails.
_LEFT, _RIGHT, _OK, _RECOVERED = "rail_left_tmp", "rail_right_tmp", "rail_ok_tmp", "rail_recovered_tmp"


def failure_data(
    kind: str,
    message: str,
    *,
    source: str,
    retryable: bool = False,
    cause: tuple[dict, ...] = (),
) -> dict:
    """The wire-safe failure envelope: plain data, JSON-clean by
    construction, no live exception object anywhere."""
    return {
        "kind": kind,
        "message": message,
        "source": source,
        "retryable": retryable,
        "cause": [dict(one) for one in cause],
    }


def attempt(
    name: str,
    fn: Callable[[dict], dict],
    *,
    accepts: str,
    returns: str,
    retryable: tuple[type[BaseException], ...] = (),
    pure: bool = False,
) -> Block:
    """The total leaf: ``fn`` either returns (ok exit) or raises (the
    exception becomes an envelope on the ``failed`` exit). Nothing
    escapes; the transition always emits exactly one token."""

    def total(data: dict) -> tuple[str, dict]:
        try:
            return ("out", fn(data))
        except Exception as error:  # noqa: BLE001 — absorbing is the leaf's whole job
            return (
                "failed",
                failure_data(
                    kind=type(error).__name__,
                    message=str(error),
                    source=name,
                    retryable=isinstance(error, retryable),
                ),
            )

    return classify(name, total, accepts=accepts, outcomes={"out": returns, "failed": FAILURE}, pure=pure)


def rail_then(a: Block, b: Block, *, on: str = "out") -> Block:
    """Compose on the ok exit and fuse the failure rails: if both sides
    carry a ``failed`` exit, the two rail places merge into one (an
    ordinary AX23 merge — the rail is a visible place, not a channel).
    A side without a rail simply passes the other side's rail through.
    Every other named exit survives untouched."""

    for tmp in (_LEFT, _RIGHT):
        if tmp in a.exits or tmp in b.exits:
            raise CompositionError(f"exit name {tmp!r} is reserved by the rail sugar")
    left = rename_exit(a, "failed", _LEFT) if "failed" in a.exits else a
    right = rename_exit(b, "failed", _RIGHT) if "failed" in b.exits else b
    combined = then(left, right, on=on)
    if _LEFT in combined.exits and _RIGHT in combined.exits:
        rail_color = {combined.exits[_LEFT].color, combined.exits[_RIGHT].color}
        if rail_color != {FAILURE}:
            raise CompositionError(
                f"rails must both be {FAILURE!r} to fuse, got {sorted(rail_color)}: "
                f"a domain outcome does not belong on the failure rail — keep it a typed exit (AX21)"
            )
        return merge(combined, _LEFT, _RIGHT, into="failed")
    if _LEFT in combined.exits:
        return rename_exit(combined, _LEFT, "failed")
    if _RIGHT in combined.exits:
        return rename_exit(combined, _RIGHT, "failed")
    return combined


def recover(block: Block, handler: Block, *, on: str = "out") -> Block:
    """Their ``catchFailure``: route the rail into a total handler and
    merge the recovery back into the ok exit. The handler receives the
    envelope (so it can inspect kind/retryable/source) and must return
    the ok exit's color — recovery means rejoining the success track,
    not inventing a third one."""

    if "failed" not in block.exits:
        raise CompositionError(f"block {block.name!r} has no 'failed' exit to recover from")
    if on not in block.exits:
        raise CompositionError(f"block {block.name!r} has no exit {on!r}; its exits are {sorted(block.exits)}")
    if handler.entry.color != FAILURE:
        raise CompositionError(
            f"recovery handler {handler.name!r} must accept the {FAILURE!r} envelope, got {handler.entry.color!r}"
        )
    if len(handler.exits) != 1:
        raise CompositionError(
            f"recovery handler {handler.name!r} has exits {sorted(handler.exits)}: it must be total — "
            f"a recovery that can itself fail composes as attempt + recover, explicitly"
        )
    ok_color = block.exits[on].color
    [(handler_exit, handler_port)] = handler.exits.items()
    if handler_port.color != ok_color:
        raise CompositionError(
            f"recovery handler {handler.name!r} returns {handler_port.color!r} but the {on!r} exit "
            f"carries {ok_color!r}: recovery rejoins the success track"
        )
    step = then(rename_exit(block, on, _OK), handler, on="failed")
    step = rename_exit(step, handler_exit, _RECOVERED)
    return merge(step, _OK, _RECOVERED, into=on)
