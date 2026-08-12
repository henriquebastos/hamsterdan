"""AX7 copy of the AX6 predicate DSL compiled to Petrus CEL filters.

Explicit expression objects with operator overloading (the preferred
implementation): `on(Application).score > 700` builds a small predicate
AST, validated against the dataclass at construction, rendered to the
CEL dialect Petrus arc filters actually evaluate — token data fields as
bare variables, so the root is elided (`score > 700`, never
`application.score > 700`).

Lambda support is *tracing*, not inspection: `trace(Application,
lambda a: a.score > 700)` calls the lambda with the typed root proxy and
receives the same expression objects. Python's `and`/`or`/`not` keywords
cannot be traced (bool coercion) and fail with an explicit remedy —
which is precisely why source/AST inspection was rejected: it would have
to reimplement Python semantics to keep those keywords, and the result
would still not be serializable evidence the way an expression tree is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass
from types import UnionType
from typing import get_args, get_type_hints


class PredicateTypeError(TypeError):
    """The predicate contradicts the declared shape of the data type."""


type Predicate = Compare | NullCheck | Membership | And | Or | Not

_ORDERINGS = {">", ">=", "<", "<="}


def _optional_base(annotation: object) -> tuple[object, bool]:
    """Split `X | None` into (X, True); anything else is (annotation, False)."""
    if isinstance(annotation, UnionType):
        members = [m for m in get_args(annotation) if m is not type(None)]
        if len(members) == 1 and len(get_args(annotation)) == 2:
            return members[0], True
    return annotation, False


class _Boolean:
    """Combinators shared by every predicate node; `bool()` is refused."""

    def __and__(self, other: Predicate) -> And:
        return And(self, _require_predicate(other, "&"))

    def __or__(self, other: Predicate) -> Or:
        return Or(self, _require_predicate(other, "|"))

    def __invert__(self) -> Not:
        return Not(self)

    def __bool__(self) -> bool:
        raise PredicateTypeError(
            "predicates cannot be used with Python's `and`/`or`/`not` "
            "keywords (they coerce to bool); use `&`, `|`, `~` instead"
        )


def _require_predicate(value: object, operator: str) -> Predicate:
    if not isinstance(value, _Boolean):
        raise PredicateTypeError(f"`{operator}` needs another predicate, got {value!r}")
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class FieldRef:
    root: str
    path: tuple[str, ...]
    annotation: object = field(compare=False)
    optional: bool = field(compare=False, default=False)

    def cel(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class Compare(_Boolean):
    operator: str
    left: FieldRef
    right: object

    def cel(self) -> str:
        return f"({self.left.cel()} {self.operator} {_literal(self.right)})"


@dataclass(frozen=True)
class NullCheck(_Boolean):
    subject: FieldRef
    present: bool  # True: `!= null`

    def cel(self) -> str:
        return f"({self.subject.cel()} {'!=' if self.present else '=='} null)"


@dataclass(frozen=True)
class Membership(_Boolean):
    subject: FieldRef
    values: tuple[object, ...]

    def cel(self) -> str:
        rendered = ", ".join(_literal(value) for value in self.values)
        return f"({self.subject.cel()} in [{rendered}])"


@dataclass(frozen=True)
class And(_Boolean):
    left: Predicate
    right: Predicate

    def cel(self) -> str:
        return f"({self.left.cel()} && {self.right.cel()})"


@dataclass(frozen=True)
class Or(_Boolean):
    left: Predicate
    right: Predicate

    def cel(self) -> str:
        return f"({self.left.cel()} || {self.right.cel()})"


@dataclass(frozen=True)
class Not(_Boolean):
    subject: Predicate

    def cel(self) -> str:
        return f"!{self.subject.cel()}"


def _literal(value: object) -> str:
    match value:
        case bool():
            return "true" if value else "false"
        case int() | float():
            return repr(value)
        case str():
            return json.dumps(value)
        case None:
            return "null"
    raise PredicateTypeError(f"{value!r} has no CEL literal form")


def _check_constant(reference: FieldRef, operator: str, value: object) -> None:
    base, _ = _optional_base(reference.annotation)
    if operator in _ORDERINGS and base not in (int, float, str):
        raise PredicateTypeError(
            f"field '{reference.cel()}' ({base!r}) does not support ordering comparison {operator!r}"
        )
    if isinstance(base, type) and not isinstance(value, bool) and isinstance(value, (int, float, str)):
        widened = (int, float) if base in (int, float) else (base,)
        if not isinstance(value, widened):
            raise PredicateTypeError(
                f"field '{reference.cel()}' is {base.__name__}, but the "
                f"comparison constant {value!r} is {type(value).__name__}"
            )


class _FieldProxy:
    """A typed path into the root dataclass; comparisons build predicate nodes."""

    def __init__(self, reference: FieldRef) -> None:
        object.__setattr__(self, "_reference", reference)

    def __getattr__(self, name: str) -> _FieldProxy:
        reference: FieldRef = self._reference
        base, _ = _optional_base(reference.annotation)
        if not (isinstance(base, type) and is_dataclass(base)):
            raise PredicateTypeError(f"field '{reference.cel()}' ({base!r}) has no nested fields")
        return _FieldProxy(_child(reference.root, base, (*reference.path,), name))

    def _compare(self, operator: str, value: object) -> Compare:
        if isinstance(value, _FieldProxy):
            raise PredicateTypeError(
                "field-to-field comparison is not supported by single-token arc filters; compare against constants"
            )
        _check_constant(self._reference, operator, value)
        return Compare(operator, self._reference, value)

    def __gt__(self, value: object) -> Compare:
        return self._compare(">", value)

    def __ge__(self, value: object) -> Compare:
        return self._compare(">=", value)

    def __lt__(self, value: object) -> Compare:
        return self._compare("<", value)

    def __le__(self, value: object) -> Compare:
        return self._compare("<=", value)

    def __eq__(self, value: object) -> Compare:  # type: ignore[override]
        return self._compare("==", value)

    def __ne__(self, value: object) -> Compare:  # type: ignore[override]
        return self._compare("!=", value)

    def is_null(self) -> NullCheck:
        return NullCheck(self._reference, present=False)

    def is_not_null(self) -> NullCheck:
        return NullCheck(self._reference, present=True)

    def one_of(self, *values: object) -> Membership:
        for value in values:
            _check_constant(self._reference, "==", value)
        return Membership(self._reference, values)

    def __bool__(self) -> bool:
        raise PredicateTypeError(
            f"field '{self._reference.cel()}' is not a predicate by itself; compare it or use .is_null()/.is_not_null()"
        )


def _child(root: str, owner: type, path: tuple[str, ...], name: str) -> FieldRef:
    hints = get_type_hints(owner)
    known = {f.name for f in fields(owner)}
    if name not in known:
        raise PredicateTypeError(f"{owner.__name__} has no field {name!r}; available: {sorted(known)}")
    annotation = hints[name]
    _, optional = _optional_base(annotation)
    return FieldRef(root=root, path=(*path, name), annotation=annotation, optional=optional)


class _Root:
    def __init__(self, data_type: type) -> None:
        if not is_dataclass(data_type):
            raise PredicateTypeError(f"on() needs a dataclass, got {data_type!r}")
        object.__setattr__(self, "_type", data_type)

    def __getattr__(self, name: str) -> _FieldProxy:
        data_type: type = self._type
        return _FieldProxy(_child(data_type.__name__, data_type, (), name))


def on(data_type: type) -> _Root:
    """The typed root proxy: attribute access builds validated field paths."""
    return _Root(data_type)


def trace(data_type: type, build) -> Predicate:
    """Trace a lambda by calling it with the typed root proxy.

    The lambda must use `&`, `|`, `~` — Python's boolean keywords coerce
    to bool and are refused with a remedy by `_Boolean.__bool__`.
    """
    result = build(on(data_type))
    if not isinstance(result, _Boolean):
        raise PredicateTypeError(f"traced lambda must return a predicate, got {type(result).__name__}")
    return result  # type: ignore[return-value]


def roots(predicate: Predicate) -> set[str]:
    """Every root type name referenced by the predicate tree."""
    match predicate:
        case Compare(left=ref) | NullCheck(subject=ref) | Membership(subject=ref):
            return {ref.root}
        case And(left=left, right=right) | Or(left=left, right=right):
            return roots(left) | roots(right)
        case Not(subject=subject):
            return roots(subject)


def validate_null_safety(predicate: Predicate, secured: frozenset[tuple[str, ...]] = frozenset()) -> None:
    """Refuse comparisons over optional fields without a preceding null check.

    A CEL filter that evaluates `null > 700` raises — and the runtime
    reads a raising filter as *not admitted*, so the token would silently
    park instead of routing. In an `And`, a left-side `is_not_null()`
    secures the right side (CEL `&&` short-circuits the same way).
    """
    match predicate:
        case Compare(left=ref) | Membership(subject=ref):
            if ref.optional and ref.path not in secured:
                raise PredicateTypeError(
                    f"field '{ref.cel()}' is optional; guard it first: "
                    f"(x.{ref.cel()}.is_not_null()) & (...) — a null would "
                    f"make the filter raise and the token silently park"
                )
        case NullCheck():
            pass
        case And(left=left, right=right):
            validate_null_safety(left, secured)
            validate_null_safety(right, secured | _secured_by(left))
        case Or(left=left, right=right):
            validate_null_safety(left, secured)
            validate_null_safety(right, secured)
        case Not(subject=subject):
            validate_null_safety(subject, secured)


def _secured_by(predicate: Predicate) -> frozenset[tuple[str, ...]]:
    match predicate:
        case NullCheck(subject=ref, present=True):
            return frozenset({ref.path})
        case And(left=left, right=right):
            return _secured_by(left) | _secured_by(right)
        case _:
            return frozenset()
