"""AX26 — the typed façade: how far can pyright and ty move
composition errors from runtime to edit time?

Composable Functions proves the existence of build-time composition
checking: TypeScript's ``FailToCompose<A, B>`` turns a bad ``pipe``
into a red squiggle before anything runs. The hypothesis under test:

    A thin generic façade over the block algebra — colors as Python
    types, blocks as ``TBlock[I, O]`` values — lets pyright and ty
    reject bad ``then``/``route``/``par``/``disposable`` compositions
    at edit time, while lowering to the exact same AX23/AX24 runtime
    structure with zero bridging code.

Design decisions, each a claim the fixtures test:

- **Types are colors.** A domain type is a ``TypedDict``; its
  ``__name__`` is the AX23 color string. TypedDicts ARE dicts at
  runtime, so token data flows through the frozen engine unchanged —
  the static layer is a shadow, not a translation layer. (This is the
  petrus-speculation "bind types instead of strings" idea, realized
  at the authoring layer with the runtime untouched.)
- **Totality by construction.** ``TBlock[I, O]`` always has exactly
  one exit; the two-outcome ``TChoice[I, A, B]`` is deliberately NOT
  a ``TBlock`` and cannot be passed where one is required — the AX24
  totality precondition becomes a static structural fact instead of a
  runtime refusal.
- **Purity as a subtype.** ``TPure[I, O] <: TBlock[I, O]``;
  ``t_disposable`` accepts only ``TPure``; ``t_then`` overloads
  propagate purity (pure ∘ pure = pure, statically).
- **Explicit convergence.** ``t_route`` demands both handlers and an
  explicit ``returns=`` type, so a merge of incompatible colors is a
  static error, not an inferred union.

Phantom-variance note: ``I`` and ``O`` appear in the ``accepts`` /
``returns`` fields (not only as phantoms), so neither checker infers
bivariance and silently accepts everything.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypedDict, get_args, get_origin, get_type_hints, overload

from ax23_blocks import Block, classify, disposable, merge, rename_exit, then, transform
from ax24_parallel import par


@dataclass(frozen=True)
class TBlock[I, O]:
    """A total typed block: one entry of type I, one exit of type O.
    Wraps the untyped AX23 Block that actually lowers and runs."""

    accepts: type[I]
    returns: type[O]
    inner: Block


@dataclass(frozen=True)
class TPure[I, O](TBlock[I, O]):
    """A total typed block whose interior is pure (disposable-eligible)."""


@dataclass(frozen=True)
class TChoice[I, A, B]:
    """A two-outcome typed step. Deliberately NOT a TBlock: a choice is
    not total, so it cannot enter ``t_then``/``t_par2`` until routed —
    the AX24 totality precondition, enforced by the type system."""

    accepts: type[I]
    yes: type[A]
    no: type[B]
    inner: Block


def _color(tp: object) -> str:
    """The canonical color string for a type — including subscripted
    generics, so ``Join2[Reservation, Taxes]`` and ``Join2[A, B]`` are
    *different* colors and cannot be confused by the runtime either."""
    origin = get_origin(tp)
    if origin is None:
        return tp.__name__  # type: ignore
    return f"{origin.__name__}[{', '.join(_color(arg) for arg in get_args(tp))}]"


def t_step[I, O](name: str, fn: Callable[[I], O], *, accepts: type[I], returns: type[O]) -> TBlock[I, O]:
    """An effectful total leaf: I in, O out. Lowered as a
    single-outcome classify with ``pure=False`` — AX23's ``transform``
    is *always* pure, so using it here would make the runtime flag
    contradict the static story (a lie the purity test caught)."""
    inner = classify(name, lambda data: ("out", fn(data)), accepts=_color(accepts), outcomes={"out": _color(returns)})  # type: ignore
    return TBlock(accepts, returns, inner)


def t_pure[I, O](name: str, fn: Callable[[I], O], *, accepts: type[I], returns: type[O]) -> TPure[I, O]:
    """A pure total leaf — the only door into ``t_disposable``."""
    return TPure(accepts, returns, transform(name, fn, accepts=_color(accepts), returns=_color(returns)))  # type: ignore


@overload
def t_fn[I, O](fn: Callable[[I], O], *, pure: Literal[True]) -> TPure[I, O]: ...
@overload
def t_fn[I, O](fn: Callable[[I], O], *, pure: Literal[False] = False) -> TBlock[I, O]: ...
def t_fn(fn, *, pure=False):
    """The inference-only leaf: ports come from the function signature
    alone — no explicit accepts/returns to contradict, so the
    union-widening hole of the declaration style (cases_bad case 9)
    cannot arise. The signature is the single source of truth for both
    the checker and the runtime colors."""
    hints = get_type_hints(fn)
    returns = hints.pop("return")
    [accepts] = hints.values()
    if pure:
        return TPure(accepts, returns, transform(fn.__name__, fn, accepts=_color(accepts), returns=_color(returns)))
    inner = classify(
        fn.__name__, lambda data: ("out", fn(data)), accepts=_color(accepts), outcomes={"out": _color(returns)}
    )
    return TBlock(accepts, returns, inner)


def t_split[I, A, B](
    name: str,
    fn: Callable[[I], tuple[Literal["yes"], A] | tuple[Literal["no"], B]],
    *,
    accepts: type[I],
    yes: type[A],
    no: type[B],
) -> TChoice[I, A, B]:
    """A typed two-outcome classification: ``fn`` names its exit with a
    Literal, so the checker knows which type leaves through which."""
    inner = classify(
        name,
        fn,  # type: ignore
        accepts=_color(accepts),
        outcomes={"yes": _color(yes), "no": _color(no)},
        pure=True,
    )
    return TChoice(accepts, yes, no, inner)


@overload
def t_then[I, M, O](a: TPure[I, M], b: TPure[M, O]) -> TPure[I, O]: ...
@overload
def t_then[I, M, O](a: TBlock[I, M], b: TBlock[M, O]) -> TBlock[I, O]: ...
def t_then(a, b):
    """Sequential composition. The middle type must agree — this is
    the composition error the fixtures push to edit time."""
    inner = then(a.inner, b.inner, on="out")
    kind = TPure if isinstance(a, TPure) and isinstance(b, TPure) else TBlock
    return kind(a.accepts, b.returns, inner)


def t_route[I, A, B, O](
    choice: TChoice[I, A, B],
    *,
    when_yes: TBlock[A, O],
    when_no: TBlock[B, O],
    returns: type[O],
) -> TBlock[I, O]:
    """Route both outcomes into handlers that must converge on one
    explicit result type — merge with the colors checked statically.
    Exhaustiveness is structural: both keywords are required."""
    step = rename_exit(then(choice.inner, when_yes.inner, on="yes"), "out", "yes_done")
    step = then(step, when_no.inner, on="no")
    inner = merge(step, "yes_done", "out", into="out")
    return TBlock(choice.accepts, returns, inner)


class Join2[A, B](TypedDict):
    """The typed shape of AX24's par aggregate for two named branches:
    ``{branch_name: branch_data}``, exactly as the join produces it."""

    first: A
    second: B


def t_par2[I, A, B](name: str, *, first: TBlock[I, A], second: TBlock[I, B]) -> TBlock[I, Join2[A, B]]:
    """AND-parallel over two total branches (totality already
    guaranteed by TBlock), joining into the typed aggregate whose
    color carries the branch types: ``Join2[Reservation, Taxes]``."""
    aggregate = Join2[first.returns, second.returns]  # type: ignore
    inner = par(name, {"first": first.inner, "second": second.inner}, returns=_color(aggregate))
    return TBlock(first.accepts, aggregate, inner)


def t_disposable[I, O](block: TPure[I, O]) -> TPure[I, O]:
    """The AX20 fenced interior — statically admissible only for pure
    blocks, so ``t_disposable(effectful)`` is an edit-time error where
    AX23 raises CompositionError at composition time."""
    return TPure(block.accepts, block.returns, disposable(block.inner))
