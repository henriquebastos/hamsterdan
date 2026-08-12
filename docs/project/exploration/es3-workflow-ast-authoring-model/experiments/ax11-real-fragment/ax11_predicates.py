"""AX11 predicates — the AX6 expression DSL grown to real-fragment scope.

The production fragment's guards are *binding* predicates: they read the
Authority token, a state token, and the lane value together
(``_current(a, v) and v.authorized and ...``). AX6 compiled single-token
arc filters (bare data fields); AX11 compiles the same expression trees
to Petrus **CEL transition guards**, where each consume/read input place
binds as a bare variable to the binding's selected ``{color, data}``
token structs (``authority[0].data.epoch``).

Three extensions over AX6, each demanded by a real production guard:

- **cross-root comparison** — ``a.epoch == v.epoch`` compares fields of
  two different tokens; sound in a binding guard, still refused wherever
  a single-token scope is compiled.
- **map-key access** — ``Intent.arguments`` is an open ``dict``;
  ``intent.arguments["message"]`` builds a key reference whose presence
  check renders as CEL ``has(...)`` (a plain ``!= null`` would raise on
  a missing key and silently park the binding).
- **scoped rendering** — ``cel(scope)`` takes a mapping from root type
  name to CEL prefix, so the same tree can serve any transition whose
  input places carry those types.

``holds()`` evaluates a predicate in Python with CEL's short-circuit
semantics — the compiler uses it to route scatter lanes, whose
predicates cannot live on output arcs (frozen ``Arc.admits`` is
color-only on outputs).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints


class PredicateTypeError(TypeError):
    """The predicate contradicts the declared shape of the data type."""


class PredicateEvaluationError(ValueError):
    """A predicate could not be decided over concrete values."""


type Predicate = Compare | NullCheck | Membership | And | Or | Not
type Scope = dict[str, str]  # root type name -> CEL prefix ("" for bare fields)

_ORDERINGS = {">", ">=", "<", "<="}
_MISSING = object()


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
    root: str  # root type name; bound to a place by the compiling transition
    path: tuple[str, ...]
    annotation: object = field(compare=False)
    optional: bool = field(compare=False, default=False)
    via_map: bool = field(compare=False, default=False)  # path crosses a dict key

    def cel(self, scope: Scope) -> str:
        prefix = _prefix(scope, self.root)
        joined = ".".join(self.path)
        return f"{prefix}.{joined}" if prefix else joined


def _prefix(scope: Scope, root: str) -> str:
    if root not in scope:
        raise PredicateTypeError(
            f"predicate reads {root}, but the compiling transition binds no "
            f"input place of that type (scope: {sorted(scope)})"
        )
    return scope[root]


@dataclass(frozen=True)
class Compare(_Boolean):
    operator: str
    left: FieldRef
    right: object  # constant or a FieldRef of another root (binding guards only)

    def cel(self, scope: Scope) -> str:
        right = self.right.cel(scope) if isinstance(self.right, FieldRef) else _literal(self.right)
        return f"({self.left.cel(scope)} {self.operator} {right})"


@dataclass(frozen=True)
class NullCheck(_Boolean):
    subject: FieldRef
    present: bool  # True: value exists (has()/!= null)

    def cel(self, scope: Scope) -> str:
        if self.subject.via_map:
            rendered = f"has({self.subject.cel(scope)})"
            return rendered if self.present else f"!{rendered}"
        return f"({self.subject.cel(scope)} {'!=' if self.present else '=='} null)"


@dataclass(frozen=True)
class Membership(_Boolean):
    subject: FieldRef
    values: tuple[object, ...]

    def cel(self, scope: Scope) -> str:
        rendered = ", ".join(_literal(value) for value in self.values)
        return f"({self.subject.cel(scope)} in [{rendered}])"


@dataclass(frozen=True)
class And(_Boolean):
    left: Predicate
    right: Predicate

    def cel(self, scope: Scope) -> str:
        return f"({self.left.cel(scope)} && {self.right.cel(scope)})"


@dataclass(frozen=True)
class Or(_Boolean):
    left: Predicate
    right: Predicate

    def cel(self, scope: Scope) -> str:
        return f"({self.left.cel(scope)} || {self.right.cel(scope)})"


@dataclass(frozen=True)
class Not(_Boolean):
    subject: Predicate

    def cel(self, scope: Scope) -> str:
        return f"!{self.subject.cel(scope)}"


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
    if get_origin(base) is Literal:
        allowed = get_args(base)
        if operator in _ORDERINGS:
            raise PredicateTypeError(f"field '{'.'.join(reference.path)}' is a Literal; ordering is meaningless")
        if value not in allowed:
            raise PredicateTypeError(
                f"field '{'.'.join(reference.path)}' can never equal {value!r}; "
                f"declared literals: {sorted(str(a) for a in allowed)}"
            )
        return
    if reference.via_map or base in (object, None) or base is dict:
        return  # open map values: structurally untyped, checked at runtime
    if operator in _ORDERINGS and base not in (int, float, str):
        raise PredicateTypeError(
            f"field '{'.'.join(reference.path)}' ({base!r}) does not support ordering comparison {operator!r}"
        )
    if isinstance(base, type) and not isinstance(value, bool) and isinstance(value, (int, float, str)):
        widened = (int, float) if base in (int, float) else (base,)
        if not isinstance(value, widened):
            raise PredicateTypeError(
                f"field '{'.'.join(reference.path)}' is {base.__name__}, but the "
                f"comparison constant {value!r} is {type(value).__name__}"
            )


class _FieldProxy:
    """A typed path into a root model; comparisons build predicate nodes."""

    def __init__(self, reference: FieldRef) -> None:
        object.__setattr__(self, "_reference", reference)

    def __getattr__(self, name: str) -> _FieldProxy:
        reference: FieldRef = self._reference
        base, _ = _optional_base(reference.annotation)
        if not (isinstance(base, type) and is_dataclass(base)):
            raise PredicateTypeError(f"field '{'.'.join(reference.path)}' ({base!r}) has no nested fields")
        return _FieldProxy(_child(reference.root, base, reference.path, name))

    def __getitem__(self, key: str) -> _FieldProxy:
        reference: FieldRef = self._reference
        base, _ = _optional_base(reference.annotation)
        if not (base is dict or get_origin(base) is dict):
            raise PredicateTypeError(
                f"field '{'.'.join(reference.path)}' ({base!r}) is not a mapping; [] needs a dict field"
            )
        if not isinstance(key, str) or not key.isidentifier():
            raise PredicateTypeError(f"map key {key!r} must be a CEL-addressable identifier")
        return _FieldProxy(
            FieldRef(
                root=reference.root,
                path=(*reference.path, key),
                annotation=object,
                optional=True,  # an open map may omit any key
                via_map=True,
            )
        )

    def _compare(self, operator: str, value: object) -> Compare:
        if isinstance(value, _FieldProxy):
            other: FieldRef = value._reference
            mine: FieldRef = self._reference
            if other.root == mine.root:
                raise PredicateTypeError(
                    "field-to-field comparison within one token is not supported; compare against constants"
                )
            left_base, _ = _optional_base(mine.annotation)
            right_base, _ = _optional_base(other.annotation)
            if not (mine.via_map or other.via_map) and left_base is not right_base:
                raise PredicateTypeError(
                    f"cross-token comparison mixes {left_base!r} ('{'.'.join(mine.path)}') "
                    f"with {right_base!r} ('{'.'.join(other.path)}')"
                )
            return Compare(operator, mine, other)
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

    def present(self) -> NullCheck:
        return NullCheck(self._reference, present=True)

    def one_of(self, *values: object) -> Membership:
        for value in values:
            _check_constant(self._reference, "==", value)
        return Membership(self._reference, values)

    def __bool__(self) -> bool:
        raise PredicateTypeError(
            f"field '{'.'.join(self._reference.path)}' is not a predicate by itself; "
            "compare it or use .present()/.is_null()"
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


def roots(predicate: Predicate) -> set[str]:
    """Every root type name referenced by the predicate tree."""
    match predicate:
        case Compare(left=ref, right=right):
            found = {ref.root}
            if isinstance(right, FieldRef):
                found.add(right.root)
            return found
        case NullCheck(subject=ref) | Membership(subject=ref):
            return {ref.root}
        case And(left=left, right=right) | Or(left=left, right=right):
            return roots(left) | roots(right)
        case Not(subject=subject):
            return roots(subject)


def validate_null_safety(predicate: Predicate, secured: frozenset[tuple[str, ...]] = frozenset()) -> None:
    """Refuse comparisons over optional fields without a preceding presence check.

    A CEL guard that evaluates a missing map key raises — and the runtime
    reads a raising guard as *not satisfied*, so the binding would
    silently never fire. In an `And`, a left-side `.present()` secures
    the right side (CEL `&&` short-circuits the same way).
    """
    match predicate:
        case Compare(left=ref) | Membership(subject=ref):
            if ref.optional and (ref.root, *ref.path) not in secured:
                raise PredicateTypeError(
                    f"field '{'.'.join(ref.path)}' may be absent; guard it first with "
                    f".present() & (...) — a missing value makes the guard raise "
                    f"and the binding silently never fires"
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
            return frozenset({(ref.root, *ref.path)})
        case And(left=left, right=right):
            return _secured_by(left) | _secured_by(right)
        case _:
            return frozenset()


def _resolve(ref: FieldRef, values: dict[str, object]) -> object:
    if ref.root not in values:
        raise PredicateEvaluationError(f"no value bound for root {ref.root}")
    current: object = values[ref.root]
    for segment in ref.path:
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING
            current = current[segment]
        elif current is None or current is _MISSING:
            return _MISSING
        else:
            current = getattr(current, segment)
    return current


def holds(predicate: Predicate, values: dict[str, object]) -> bool:
    """Evaluate in Python with CEL's short-circuit semantics.

    ``values`` maps root type names to hydrated models. Used only where
    the frozen runtime cannot evaluate CEL for us — scatter lane routing
    inside a synthesized handler (output arcs admit by color alone).
    """
    match predicate:
        case Compare(operator=op, left=left, right=right):
            lhs = _resolve(left, values)
            rhs = _resolve(right, values) if isinstance(right, FieldRef) else right
            if lhs is _MISSING or rhs is _MISSING:
                raise PredicateEvaluationError(
                    f"'{'.'.join(left.path)}' is absent; the comparison is undecidable (guard with .present())"
                )
            table = {
                "==": lhs == rhs,
                "!=": lhs != rhs,
                ">": lhs > rhs,
                ">=": lhs >= rhs,
                "<": lhs < rhs,
                "<=": lhs <= rhs,
            }
            return bool(table[op])
        case NullCheck(subject=ref, present=present):
            value = _resolve(ref, values)
            exists = value is not _MISSING and value is not None
            return exists if present else not exists
        case Membership(subject=ref, values=constants):
            value = _resolve(ref, values)
            if value is _MISSING:
                raise PredicateEvaluationError(
                    f"'{'.'.join(ref.path)}' is absent; membership is undecidable (guard with .present())"
                )
            return value in constants
        case And(left=left, right=right):
            return holds(left, values) and holds(right, values)
        case Or(left=left, right=right):
            return holds(left, values) or holds(right, values)
        case Not(subject=subject):
            return not holds(subject, values)
