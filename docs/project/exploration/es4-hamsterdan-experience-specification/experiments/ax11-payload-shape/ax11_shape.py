"""ES-004 AX11 — payload shape contracts: ports carry types, not color strings.

AX4's one genuine finding, MISSED in production AND the spike algebra
(AX5 #5): port fusion checked COLORS, but the downstream handler
needed FIELDS. `ProvisionalHead {provisional_head, reused}` fused
into a consumer wanting `(kind, operation, head)` because the color
strings matched — the adapter had to invent its marker from the head
alone, silently. Petrus itself is no stricter: `Arc.color` is a
string, "a typed arc admits its color only (nominal match)"
(petrus/impetus/petrinet/schema.py) — the name matches, the payload
is unchecked.

This spike gives ports a payload TYPE and tests three deterministic
rules plus one static claim:

1. NOMINAL FUSION. Identical payload type fuses silently; anything
   else refuses. Structural-subset matching is rejected as a fusion
   rule — production proves why: `ChangeResult` and `RepairResult`
   have IDENTICAL field lists (contracts/readiness.py:546-570), yet a
   repair result flowing into a change consumer would corrupt lineage
   semantics (`repair_used`, `repair_fingerprint`). Same shape,
   different meaning: shape must never be identity. (The settled
   doctrine again: types validate compatibility; named ports define
   topology.)
2. SHAPE AS DIAGNOSTIC. When fusion refuses, the structural diff is
   the explanation: which required fields of the consumer's type the
   producer's type cannot provide. The AX4 mystery becomes a named,
   field-level error at composition time.
3. ADAPTERS FROM SIGNATURES. Crossing types requires an explicit
   adapter whose contract is INFERRED from its annotations
   (`get_type_hints`) — single source of truth, AX26's sharpened
   lesson: inference is safer than declaration because the leaf
   cannot lie. Untyped adapters are refused.

Plus the AX26 limit this closes: GUARD-FIELD VALIDATION. A guard
referencing `risk_score` on a port whose payload cannot have that
field fails at composition time, naming the port, the type, the
failing path segment, and the fields that do exist. Nested paths
traverse nested dataclasses (`comment.actor_login` on
`ConversationClassificationRequest`).

Static claim (tested by running both checkers over the fixtures):
because shape errors are STRUCTURAL — attribute access, argument
type, return type — they sit in ty's sweet spot, unlike AX26's
generic-parameter constraints (ty 0.0.63 caught 5/9 there). Here the
project's own CI checker catches every marked mistake today, and
pyright agrees. The adapter layer is where the type checker earns
its keep with zero annotation burden beyond ordinary signatures.

Everything works on the production `WorkflowModel` pydantic
dataclasses unchanged — read-only imports, no production edits.
"""

from __future__ import annotations

import dataclasses
from dataclasses import MISSING
from typing import Any, Callable, get_type_hints


class ShapeError(Exception):
    """A refused composition, explained in fields."""


@dataclasses.dataclass(frozen=True)
class Port:
    """A named exit or entry with a payload type. The name is the
    topology; the type is the contract."""

    name: str
    payload: type


def shape(payload: type) -> dict[str, type]:
    """Field name → annotation, for any (pydantic) dataclass."""
    if not dataclasses.is_dataclass(payload):
        raise ShapeError(f"{payload.__name__} is not a dataclass; ports need field-typed payloads")
    hints = get_type_hints(payload)
    return {field.name: hints[field.name] for field in dataclasses.fields(payload)}


def required(payload: type) -> set[str]:
    """Fields a constructor must be given — no default, no factory."""
    return {
        field.name
        for field in dataclasses.fields(payload)
        if field.default is MISSING and field.default_factory is MISSING
    }


def missing_fields(producer: type, consumer: type) -> dict[str, str]:
    """The structural diff powering refusal messages: required consumer
    fields the producer cannot provide (absent, or annotated
    incompatibly)."""
    have, want = shape(producer), shape(consumer)
    problems: dict[str, str] = {}
    for name in sorted(required(consumer)):
        if name not in have:
            problems[name] = f"missing (producer has {', '.join(sorted(have)) or 'no fields'})"
        elif have[name] != want[name]:
            problems[name] = f"is {_name(have[name])}, consumer wants {_name(want[name])}"
    return problems


def fuse(producer: Port, consumer: Port) -> None:
    """Rule 1: nominal identity or refusal — with the shape diff as
    the explanation, never as the rule."""
    if producer.payload is consumer.payload:
        return
    diff = missing_fields(producer.payload, consumer.payload)
    detail = (
        "; ".join(f"{field}: {why}" for field, why in diff.items())
        if diff
        else "shapes are compatible, but same shape is not same meaning — adapt explicitly"
    )
    raise ShapeError(
        f"cannot fuse port {producer.name!r} ({producer.payload.__name__}) into "
        f"port {consumer.name!r} ({consumer.payload.__name__}): {detail}"
    )


@dataclasses.dataclass(frozen=True)
class Adapter:
    accepts: type
    returns: type
    fn: Callable[[Any], Any]


def adapter(fn: Callable[[Any], Any]) -> Adapter:
    """Rule 3: the adapter's contract is its signature — one source of
    truth for the checker, the fuse rule, and the runtime."""
    hints = get_type_hints(fn)
    returns = hints.pop("return", None)
    if returns is None or len(hints) != 1:
        raise ShapeError(
            f"adapter {fn.__name__!r} must annotate exactly one parameter and its return; "
            f"the signature IS the contract"
        )
    [accepts] = hints.values()
    return Adapter(accepts=accepts, returns=returns, fn=fn)


def fuse_through(producer: Port, via: Adapter, consumer: Port) -> None:
    """An adapted fusion is two nominal fusions."""
    fuse(producer, Port(f"{producer.name}→{via.fn.__name__}", via.accepts))
    fuse(Port(f"{via.fn.__name__}→{consumer.name}", via.returns), consumer)


def guard_fields(port: Port, *paths: str) -> None:
    """Closes AX26's named limit: every dotted path a guard references
    must exist on the port's payload type, traversing nested
    dataclasses."""
    for path in paths:
        current: type = port.payload
        walked: list[str] = []
        for segment in path.split("."):
            if not dataclasses.is_dataclass(current):
                raise ShapeError(
                    f"guard on port {port.name!r}: {'.'.join(walked)} is "
                    f"{_name(current)}, which cannot have field {segment!r}"
                )
            fields = shape(current)
            if segment not in fields:
                raise ShapeError(
                    f"guard on port {port.name!r}: {current.__name__} has no field "
                    f"{segment!r} (has {', '.join(sorted(fields))})"
                )
            current = fields[segment]
            walked.append(segment)


def _name(annotation: object) -> str:
    return getattr(annotation, "__name__", str(annotation))
