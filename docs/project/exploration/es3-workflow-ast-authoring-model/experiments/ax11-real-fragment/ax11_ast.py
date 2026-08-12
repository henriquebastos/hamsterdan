"""AX11 AST — the leading design shaped by a real production fragment.

AX1–AX10 proved the pipeline story: activities as leaves, combinators as
topology, types as local compatibility. The real net
(`src/hamsterdan/readiness/net/topology.py`) is not a pipeline — it is a
long-lived colored state machine: state tokens folded in place, an
Authority token read by nearly every guard, one classified batch
scattered into per-concern lanes, and guarded competition over the same
lane place. AX11 grows the AST by exactly the nodes that reality
demanded, nothing more:

- ``port``/``state_port``/``read_port`` — every place is **named** by
  the author (AX3's ruling: types never identify places; names do).
  Port names must be CEL-safe identifiers because a binding guard's
  whole variable scope is the transition's input place names.
- ``activity_step`` — the AX2 leaf, unchanged: one typed activity
  dispatched through the frozen dispatcher.
- ``scatter`` — one token becomes many, each routed to the single lane
  whose predicate admits it. Routing multiplicity is data-dependent, so
  it cannot be an AND-split duplication (AX4) nor output-arc filters
  (frozen ``Arc.admits`` is color-only on outputs): the compiler
  synthesizes the routing handler from the declared lane predicates,
  which must be *decidably disjoint* (literal sets over one field).
  ``rest=DROP`` is mandatory spelling for what production does silently.
- ``choice`` — guarded competition over one lane place. Cases are
  ordered-exclusive (AX6): the compiler chains negated predecessors into
  each CEL guard, widening scope with read arcs when a predecessor's
  predicate reads a port the case itself does not. The ``otherwise``
  is mandatory and must name the *gap policy*: ``WAIT`` (tokens park
  until state changes — deliberate in production) or ``retire()``.
- ``fold`` / ``update`` — the state-machine steps: consume a state
  token and the lane value, produce the updated state (``fold``), plus
  emitted work requests through named exit ports (``update``).
- ``to_exit`` — a lane that leaves the fragment boundary for the wider
  net to consume.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field
from typing import get_args, get_origin, get_type_hints

from ax11_predicates import (
    Compare,
    Membership,
    Predicate,
    _Boolean,
    roots,
    validate_null_safety,
)
from petrus.motus.activity import ActivityDefinition, AsyncActivityDefinition

type Definition = ActivityDefinition | AsyncActivityDefinition


class WorkflowShapeError(ValueError):
    """A combinator or leaf was constructed with an impossible shape."""


@dataclass(frozen=True)
class Origin:
    filename: str
    line: int

    def __str__(self) -> str:
        return f"{self.filename}:{self.line}"


def _caller_origin(depth: int = 2) -> Origin:
    frame = sys._getframe(depth)
    return Origin(filename=frame.f_code.co_filename, line=frame.f_lineno)


def _named_type(model: object, subject: str) -> type:
    if not isinstance(model, type) or not getattr(model, "__name__", ""):
        raise WorkflowShapeError(f"{subject} needs a nominal type, got {model!r}")
    return model


@dataclass(frozen=True)
class Port:
    """A named, typed place at the fragment surface or between steps."""

    name: str
    model: type

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise WorkflowShapeError(
                f"port name {self.name!r} must be a bare identifier — it becomes "
                f"a root-scope place name, and CEL binding guards can only "
                f"reference identifier-shaped place variables"
            )
        _named_type(self.model, f"port {self.name!r}")

    @property
    def color(self) -> str:
        return self.model.__name__


@dataclass(frozen=True)
class StatePort(Port):
    """A long-lived state token: consumed and re-produced by every fold."""


@dataclass(frozen=True)
class ReadPort(Port):
    """A token read (never consumed) for guard context — e.g. Authority."""


def port(name: str, model: type) -> Port:
    return Port(name, model)


def state_port(name: str, model: type) -> StatePort:
    return StatePort(name, model)


def read_port(name: str, model: type) -> ReadPort:
    return ReadPort(name, model)


class _Wait:
    """The explicit gap policy: unmatched lane tokens park until state changes."""

    def __repr__(self) -> str:
        return "WAIT"


WAIT = _Wait()


class _Drop:
    """The explicit rest policy: scattered items no lane admits are dropped."""

    def __repr__(self) -> str:
        return "DROP"


DROP = _Drop()


@dataclass(frozen=True)
class Retire:
    """A guarded sink: the token is consumed and the concern ends."""

    origin: Origin | None = field(default=None, compare=False)


def retire() -> Retire:
    return Retire(origin=_caller_origin())


@dataclass(frozen=True)
class Fold:
    """Consume the lane value and a state token; produce the updated state."""

    function: object  # (…context…, State, Value) -> State, typed by annotations
    state: StatePort
    origin: Origin | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Update:
    """A fold that also emits work-request tokens through named exit ports."""

    function: object  # (…context…) -> tuple[State, *Emitted]
    state: StatePort
    emits: tuple[Port, ...]
    origin: Origin | None = field(default=None, compare=False)


def _hints(function: object, subject: str) -> tuple[dict[str, type], object]:
    if not callable(function):
        raise WorkflowShapeError(f"{subject} needs a callable, got {function!r}")
    hints = dict(get_type_hints(function))
    result = hints.pop("return", None)
    if result is None:
        raise WorkflowShapeError(f"{subject} ({function.__name__}) needs a return annotation")
    for name, annotation in hints.items():
        _named_type(annotation, f"{subject} parameter {name!r}")
    return hints, result


def fold(function: object, *, state: StatePort) -> Fold:
    _, result = _hints(function, "fold()")
    if result is not state.model:
        raise WorkflowShapeError(
            f"fold({function.__name__}) must return the state type "
            f"{state.color}, but returns {getattr(result, '__name__', result)!r}"
        )
    return Fold(function=function, state=state, origin=_caller_origin())


def update(function: object, *, state: StatePort, emits: tuple[Port, ...]) -> Update:
    _, result = _hints(function, "update()")
    expected = (state.model, *(p.model for p in emits))
    if get_origin(result) is not tuple or get_args(result) != expected:
        wanted = ", ".join(t.__name__ for t in expected)
        raise WorkflowShapeError(
            f"update({function.__name__}) must return tuple[{wanted}] — the "
            f"updated state first, then one value per emitted port — but "
            f"returns {result!r}"
        )
    return Update(function=function, state=state, emits=emits, origin=_caller_origin())


@dataclass(frozen=True)
class Case:
    when: Predicate
    then: Fold | Update | Retire
    origin: Origin | None = field(default=None, compare=False)


def case(*, when: Predicate, then: Fold | Update | Retire) -> Case:
    if not isinstance(when, _Boolean):
        raise WorkflowShapeError(f"case when= needs a predicate expression object, got {type(when).__name__}")
    validate_null_safety(when)
    if not isinstance(then, (Fold, Update, Retire)):
        raise WorkflowShapeError(f"case then= needs fold()/update()/retire(), got {type(then).__name__}")
    return Case(when=when, then=then, origin=_caller_origin())


@dataclass(frozen=True)
class Choice:
    """Ordered-exclusive guarded competition over one lane place."""

    cases: tuple[Case, ...]
    otherwise: _Wait | Retire
    origin: Origin | None = field(default=None, compare=False)


def choice(*cases: Case, otherwise: _Wait | Retire) -> Choice:
    if not cases:
        raise WorkflowShapeError("choice() needs at least one case")
    if not isinstance(otherwise, (_Wait, Retire)):
        raise WorkflowShapeError(
            "choice() must state its gap policy explicitly: otherwise=WAIT "
            "(unmatched tokens park until state changes) or otherwise=retire()"
        )
    return Choice(cases=tuple(cases), otherwise=otherwise, origin=_caller_origin())


class _Exit:
    def __repr__(self) -> str:
        return "EXIT"


EXIT = _Exit()


@dataclass(frozen=True)
class Lane:
    port: Port
    where: Predicate
    then: Choice | _Exit
    origin: Origin | None = field(default=None, compare=False)


def lane(target: Port, *, where: Predicate, then: Choice | _Exit) -> Lane:
    if not isinstance(where, _Boolean):
        raise WorkflowShapeError(f"lane {target.name!r} where= needs a predicate, got {type(where).__name__}")
    validate_null_safety(where)
    if not isinstance(then, (Choice, _Exit)):
        raise WorkflowShapeError(f"lane {target.name!r} then= needs choice(...) or EXIT")
    return Lane(port=target, where=where, then=then, origin=_caller_origin())


def _item_type(result: object, subject: str) -> type:
    origin = get_origin(result)
    if origin is tuple:
        args = get_args(result)
        if len(args) == 2 and args[1] is Ellipsis:
            return _named_type(args[0], subject)
    if origin in (list, SequenceABC):
        [arg] = get_args(result)
        return _named_type(arg, subject)
    raise WorkflowShapeError(
        f"{subject}: a scatter transform must return tuple[V, ...], list[V], or Sequence[V], got {result!r}"
    )


def _routing_atoms(where: Predicate, lane_name: str) -> tuple[tuple[str, ...], frozenset[object]]:
    """The lane's decidable routing set: literal values over one field.

    Frozen Petrus cannot evaluate filters on output arcs, so lane routing
    executes inside a synthesized handler. That is only safe when
    disjointness is *statically decidable* — which this spike bounds to
    the shape every production lane actually has: equality/membership of
    one field against literals.
    """
    match where:
        case Compare(operator="==", left=ref, right=value) if not isinstance(value, tuple):
            return (ref.root, *ref.path), frozenset({value})
        case Membership(subject=ref, values=values):
            return (ref.root, *ref.path), frozenset(values)
    raise WorkflowShapeError(
        f"lane {lane_name!r} routing predicate must be a literal equality or "
        f".one_of(...) over one field, so lane disjointness stays statically "
        f"decidable — value-dependent branching belongs in the lane's choice()"
    )


@dataclass(frozen=True)
class Scatter:
    transform: object  # (Batch) -> Sequence[Item], typed by annotations
    input_model: type
    item_model: type
    lanes: tuple[Lane, ...]
    rest: _Drop
    origin: Origin | None = field(default=None, compare=False)


def scatter(transform: object, *lanes_: Lane, rest: _Drop) -> Scatter:
    hints, result = _hints(transform, "scatter()")
    if len(hints) != 1:
        raise WorkflowShapeError(f"scatter transform {transform.__name__} must take exactly one parameter")
    [input_model] = hints.values()
    item_model = _item_type(result, f"scatter transform {transform.__name__}")
    if not lanes_:
        raise WorkflowShapeError("scatter() needs at least one lane")
    if not isinstance(rest, _Drop):
        raise WorkflowShapeError(
            "scatter() must state what happens to items no lane admits: "
            "rest=DROP is the only policy the frozen runtime can honor, and "
            "it must be written down"
        )
    routing_field: tuple[str, ...] | None = None
    claimed: dict[object, str] = {}
    for entry in lanes_:
        subjects = roots(entry.where)
        if subjects != {item_model.__name__}:
            raise WorkflowShapeError(
                f"lane {entry.port.name!r} routing predicate must read only the "
                f"scattered item type {item_model.__name__}, but reads {sorted(subjects)}"
            )
        atoms_field, values = _routing_atoms(entry.where, entry.port.name)
        if routing_field is None:
            routing_field = atoms_field
        elif atoms_field != routing_field:
            raise WorkflowShapeError(
                f"lane {entry.port.name!r} routes on field {'.'.join(atoms_field[1:])!r}, but earlier "
                f"lanes route on {'.'.join(routing_field[1:])!r} — one scatter routes on one field"
            )
        for value in values:
            if value in claimed:
                raise WorkflowShapeError(
                    f"lanes {claimed[value]!r} and {entry.port.name!r} both claim "
                    f"{value!r} — a scattered item must have exactly one destination"
                )
            claimed[value] = entry.port.name
    names = [entry.port.name for entry in lanes_]
    if len(set(names)) != len(names):
        raise WorkflowShapeError(f"scatter lanes repeat a port name: {names}")
    return Scatter(
        transform=transform,
        input_model=input_model,
        item_model=item_model,
        lanes=tuple(lanes_),
        rest=rest,
        origin=_caller_origin(),
    )


@dataclass(frozen=True)
class ActivityStep:
    """One typed activity dispatched through the frozen dispatcher (AX2)."""

    definition: Definition
    out: Port
    origin: Origin | None = field(default=None, compare=False)


def activity_step(definition: Definition, *, out: Port) -> ActivityStep:
    result = definition.result
    if result is not out.model:
        raise WorkflowShapeError(
            f"activity {definition.declaration.name!r} returns "
            f"{getattr(result, '__name__', result)!r}, but its out port "
            f"{out.name!r} carries {out.color}"
        )
    if len(definition.parameters) != 1:
        raise WorkflowShapeError(
            f"activity {definition.declaration.name!r} must take exactly one parameter in this spike"
        )
    return ActivityStep(definition=definition, out=out, origin=_caller_origin())


@dataclass(frozen=True)
class Fragment:
    name: str
    entry: Port
    reads: tuple[ReadPort, ...]
    states: tuple[StatePort, ...]
    body: tuple[ActivityStep | Scatter, ...]
    origin: Origin | None = field(default=None, compare=False)


def fragment(
    name: str,
    *,
    entry: Port,
    reads: tuple[ReadPort, ...],
    states: tuple[StatePort, ...],
    body: tuple[ActivityStep | Scatter, ...],
) -> Fragment:
    if not body:
        raise WorkflowShapeError("fragment() needs a body")
    surface: list[Port] = [entry, *reads, *states]
    current = entry.model
    for step in body:
        match step:
            case ActivityStep():
                [(parameter, annotation)] = step.definition.parameters.items()
                if annotation is not current:
                    raise WorkflowShapeError(
                        f"activity {step.definition.declaration.name!r} parameter "
                        f"{parameter!r} wants {getattr(annotation, '__name__', annotation)!r}, "
                        f"but the previous step hands over {current.__name__}"
                    )
                surface.append(step.out)
                current = step.out.model
            case Scatter():
                if step.input_model is not current:
                    raise WorkflowShapeError(
                        f"scatter transform {step.transform.__name__} wants "
                        f"{step.input_model.__name__}, but the previous step hands over {current.__name__}"
                    )
                for entry_lane in step.lanes:
                    surface.append(entry_lane.port)
                    if isinstance(entry_lane.then, Choice):
                        for c in entry_lane.then.cases:
                            if isinstance(c.then, Update):
                                surface.extend(c.then.emits)
                current = step.item_model
            case _:
                raise WorkflowShapeError(f"fragment body cannot contain {step!r}")
    names = [p.name for p in surface]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise WorkflowShapeError(f"fragment {name!r} declares duplicate port names: {duplicates}")
    return Fragment(
        name=name,
        entry=entry,
        reads=reads,
        states=states,
        body=tuple(body),
        origin=_caller_origin(),
    )
