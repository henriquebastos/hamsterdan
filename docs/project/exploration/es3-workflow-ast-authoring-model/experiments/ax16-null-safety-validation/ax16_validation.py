"""AX16 — null-safety validation grounded in CEL's absorption semantics.

AX15 shipped its recovery guards under an *author obligation*: conjoin
`.present()` before any nested read of an optional field, because
`validate_null_safety` (v1) cannot see two of the three risks and
enforces the one it does see by left-to-right ordering. AX16 replaces
the obligation with a validator, after first pinning down what the
runtime actually does.

The runtime facts (proven in the test module on Petrus's own
`compile_guard` path — this is celpy implementing the CEL spec's
commutative logic operators):

- ``error && false == false`` **in both orders** — a failing nested
  read is absorbed whenever any sibling conjunct is false;
- ``error && true`` is an error — absorbed by *nothing*, the guard
  raises and the binding parks silently;
- ``true || error == true`` in both orders; ``false || error`` is an
  error.

So the soundness criterion is not ordering at all. A risky read is safe
iff, in every world where the read errors, some sibling decides the
connective: for ``&&`` a conjunct that is *false whenever the path is
absent* (`.present()`), for ``||`` a disjunct that is *true whenever
the path is absent* (`.is_null()`). Position is irrelevant — AX15's
"ordering obligation" was stronger than the runtime requires.

``validate_guard`` enforces exactly that criterion over the AX11
predicate vocabulary, closing v1's three holes:

1. **parent optionality is inherited** — every optional/map prefix of a
   reference is a risk point, not just the leaf;
2. **both comparison sides are checked** — a cross-token right-hand
   reference carries the same risks as the left;
3. **securing is a sibling-set property, not a position** — computed as
   the union of guarantees of all *other* conjuncts (dually, disjuncts).

Deliberate conservatisms, recorded not hidden:

- ``==``/``!=`` on an optional *leaf* whose prefixes are safe is total
  in celpy (`null == "x"` is `false`, no error) — but `holds()`, the
  Python evaluator used for scatter routing, raises on the same
  predicate. Until the two evaluators agree, the validator keeps v1's
  refusal. This divergence is the experiment's second finding.
- A `Not(...)` guarantees nothing unless it is exactly `~x.is_null()`;
  an `Or` guarantees nothing to an enclosing `And` (its own risks are
  validated in place, but its truth-table contribution is not mined).
"""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import get_origin, get_type_hints

from ax11_predicates import (
    And,
    Compare,
    FieldRef,
    Membership,
    Not,
    NullCheck,
    Or,
    Predicate,
    PredicateTypeError,
    _optional_base,
)

type _Path = tuple[str, ...]  # (root type name, *segments)


def validate_guard(predicate: Predicate, *root_types: type) -> None:
    """Refuse any reference that can make the compiled guard error.

    ``root_types`` are the dataclasses the compiling transition binds —
    the same knowledge the compiler already holds per transition. Raises
    ``PredicateTypeError`` naming the first unsecured risk point and how
    to secure it.
    """
    types = {t.__name__: t for t in root_types}
    _validate(predicate, frozenset(), types)


def _validate(predicate: Predicate, secured: frozenset[_Path], types: dict[str, type]) -> None:
    match predicate:
        case Compare(left=left, right=right):
            _check(left, secured, types, include_leaf=True)
            if isinstance(right, FieldRef):
                _check(right, secured, types, include_leaf=True)
        case Membership(subject=subject):
            _check(subject, secured, types, include_leaf=True)
        case NullCheck(subject=subject):
            # The check itself decides the leaf, but CEL still *selects*
            # through the prefixes to reach it — those must be secured.
            _check(subject, secured, types, include_leaf=False)
        case And(left=left, right=right):
            _validate(left, secured | _false_when_absent(right), types)
            _validate(right, secured | _false_when_absent(left), types)
        case Or(left=left, right=right):
            _validate(left, secured | _true_when_absent(right), types)
            _validate(right, secured | _true_when_absent(left), types)
        case Not(subject=subject):
            _validate(subject, secured, types)


def _check(ref: FieldRef, secured: frozenset[_Path], types: dict[str, type], *, include_leaf: bool) -> None:
    for point, reason in _risk_points(ref, types, include_leaf=include_leaf):
        if point not in secured:
            dotted = ".".join(point[1:])
            raise PredicateTypeError(
                f"reading '{'.'.join(ref.path)}' on {ref.root} can error: {reason} at '{dotted}'. "
                f"Secure it with an `& {dotted}.present()` conjunct (any position) or, in an "
                f"any-of, an `| {dotted}.is_null()` disjunct — an unabsorbed evaluation error "
                f"makes the guard raise and the binding silently never fires"
            )


def _risk_points(ref: FieldRef, types: dict[str, type], *, include_leaf: bool) -> list[tuple[_Path, str]]:
    """Every prefix of ``ref`` whose absence can make evaluation error.

    Optionality is recomputed from the root dataclass — the one piece of
    knowledge v1's leaf-only ``FieldRef.optional`` flag cannot carry.
    """
    if ref.root not in types:
        raise PredicateTypeError(
            f"predicate reads {ref.root}, but the transition binds no such root (roots: {sorted(types)})"
        )
    points: list[tuple[_Path, str]] = []
    current: object = types[ref.root]
    for depth, segment in enumerate(ref.path, start=1):
        prefix: _Path = (ref.root, *ref.path[:depth])
        is_leaf = depth == len(ref.path)
        if isinstance(current, type) and is_dataclass(current):
            hints = get_type_hints(current)
            if segment not in hints:  # unreachable via the proxies; defensive
                raise PredicateTypeError(f"{current.__name__} has no field {segment!r}")
            annotation, optional = _optional_base(hints[segment])
            if optional and (include_leaf or not is_leaf):
                points.append((prefix, "the field is declared optional"))
            current = annotation
        elif current is dict or get_origin(current) is dict or current is object:
            if include_leaf or not is_leaf:
                points.append((prefix, "the map may omit the key"))
            current = object
        else:  # a scalar with further segments — the proxies refuse this too
            raise PredicateTypeError(f"'{'.'.join(ref.path[:depth])}' ({current!r}) has no nested fields")
    return points


def _false_when_absent(predicate: Predicate) -> frozenset[_Path]:
    """Paths whose absence guarantees this predicate is false (never error).

    These are the valid securers inside an ``And``: if the risky sibling
    errors because the path is absent, this conjunct is false and CEL's
    commutative `&&` absorbs the error.
    """
    match predicate:
        case NullCheck(subject=ref, present=True):
            return frozenset({(ref.root, *ref.path)})
        case Not(subject=NullCheck(subject=ref, present=False)):
            return frozenset({(ref.root, *ref.path)})
        case And(left=left, right=right):
            return _false_when_absent(left) | _false_when_absent(right)
        case _:
            return frozenset()


def _true_when_absent(predicate: Predicate) -> frozenset[_Path]:
    """Paths whose absence guarantees this predicate is true — the dual
    securers inside an ``Or`` (``true || error == true``)."""
    match predicate:
        case NullCheck(subject=ref, present=False):
            return frozenset({(ref.root, *ref.path)})
        case Not(subject=NullCheck(subject=ref, present=True)):
            return frozenset({(ref.root, *ref.path)})
        case Or(left=left, right=right):
            return _true_when_absent(left) | _true_when_absent(right)
        case _:
            return frozenset()
