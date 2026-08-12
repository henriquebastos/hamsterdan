"""AX26 fixture — compositions that must produce ZERO diagnostics from
both pyright and ty. Any error here is a false positive: annotation
burden the façade would impose on every author.

Also the shared domain vocabulary for the other fixtures: TypedDicts,
because they are plain dicts at runtime — the engine sees exactly this
data, no bridging.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from ax26_typed import (
    Join2,
    TBlock,
    TPure,
    t_disposable,
    t_fn,
    t_par2,
    t_pure,
    t_route,
    t_split,
    t_step,
    t_then,
)


class Raw(TypedDict):
    payload: str


class Order(TypedDict):
    sku: str
    amount: int


class Reservation(TypedDict):
    sku: str
    hold_id: str


class Taxes(TypedDict):
    tax: int


class Receipt(TypedDict):
    total: int


class Review(TypedDict):
    reason: str


class Done(TypedDict):
    ok: bool


# -- typed leaves --------------------------------------------------------------------


def _parse(raw: Raw) -> Order:
    return {"sku": raw["payload"], "amount": len(raw["payload"])}


def _reserve(order: Order) -> Reservation:
    return {"sku": order["sku"], "hold_id": f"H-{order['sku']}"}


def _taxes(order: Order) -> Taxes:
    return {"tax": order["amount"] // 10}


def _charge(joined: Join2[Reservation, Taxes]) -> Receipt:
    return {"total": len(joined["first"]["hold_id"]) + joined["second"]["tax"]}


def _judge(receipt: Receipt) -> tuple[Literal["yes"], Receipt] | tuple[Literal["no"], Review]:
    if receipt["total"] < 100:
        return ("yes", receipt)
    review: Review = {"reason": "too expensive"}
    return ("no", review)


def _settle(receipt: Receipt) -> Done:
    return {"ok": receipt["total"] > 0}


def _escalate(review: Review) -> Done:
    return {"ok": False}


parse = t_pure("parse", _parse, accepts=Raw, returns=Order)
reserve = t_step("reserve", _reserve, accepts=Order, returns=Reservation)
taxes = t_pure("taxes", _taxes, accepts=Order, returns=Taxes)
charge = t_step("charge", _charge, accepts=Join2[Reservation, Taxes], returns=Receipt)
judge = t_split("judge", _judge, accepts=Receipt, yes=Receipt, no=Review)
settle = t_step("settle", _settle, accepts=Receipt, returns=Done)
escalate = t_step("escalate", _escalate, accepts=Review, returns=Done)


# -- valid compositions, all statically accepted ---------------------------------------

# sequence: middle types agree
prepared: TBlock[Raw, Reservation] = t_then(parse, reserve)

# parallel: both branches accept Order, aggregate is the typed join shape
both: TBlock[Order, Join2[Reservation, Taxes]] = t_par2("both", first=reserve, second=taxes)

# route: both outcomes converge on Done, explicitly
routed: TBlock[Receipt, Done] = t_route(judge, when_yes=settle, when_no=escalate, returns=Done)

# purity propagates: pure ∘ pure is pure, and only then disposable
halve_a = t_pure("halve_a", lambda o: o, accepts=Order, returns=Order)
halve_b = t_pure("halve_b", lambda o: o, accepts=Order, returns=Order)
fenced: TPure[Raw, Order] = t_disposable(t_then(parse, t_then(halve_a, halve_b)))

# the whole ES-003 inquiry example, typed end to end
workflow: TBlock[Raw, Done] = t_then(t_then(t_then(parse, both), charge), routed)

# inference-only leaves: ports derived from the signature, nothing declared twice
parse_fn: TPure[Raw, Order] = t_fn(_parse, pure=True)
reserve_fn: TBlock[Order, Reservation] = t_fn(_reserve)
prepared_fn: TBlock[Raw, Reservation] = t_then(parse_fn, reserve_fn)
