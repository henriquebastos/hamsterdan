"""AX28 — one file to first motion.

This file is the whole authoring experience for the ES-003 inquiry
example: receive an order, reserve inventory and calculate taxes in
parallel, charge, then route by judgment. Domain steps, composition,
and motion — nothing else. Infrastructure appears exactly once, as the
single imported name ``first_motion``; every other import is workflow
vocabulary (general Petri-net primitives, not Hamsterdan structure).

Run it directly to see the artifacts (the spike imports its sibling
experiments, so put them on the path; pytest's conftest does this
automatically)::

    EXP=docs/project/exploration/es3-workflow-ast-authoring-model/experiments
    PYTHONPATH="$EXP/ax11-real-fragment:$EXP/ax19-kernel-boundary:\
    $EXP/ax23-completed-algebra:$EXP/ax24-parallel-blocks:$EXP/ax28-first-motion" \
      .venv/bin/python $EXP/ax28-first-motion/ax28_one_file.py
"""

from __future__ import annotations

from ax23_blocks import Block, classify, then, transform
from ax24_parallel import par
from ax28_motion import Motion, first_motion

# -- domain steps ---------------------------------------------------------------------


def receive() -> Block:
    return transform(
        "receive",
        lambda intent: {"sku": intent["sku"], "amount": intent["amount"]},
        accepts="Intent",
        returns="Order",
    )


def reserve() -> Block:
    return transform(
        "reserve",
        lambda order: {"sku": order["sku"], "reserved": True},
        accepts="Order",
        returns="Reservation",
    )


def taxes() -> Block:
    return transform(
        "taxes",
        lambda order: {"sku": order["sku"], "tax": round(order["amount"] * 0.2, 2)},
        accepts="Order",
        returns="Taxes",
    )


def charge() -> Block:
    return transform(
        "charge",
        lambda quote: {"sku": quote["inventory"]["sku"], "total": quote["taxes"]["tax"] + 10.0},
        accepts="Quote",
        returns="Receipt",
    )


def judge() -> Block:
    return classify(
        "judge",
        lambda receipt: ("settled", receipt) if receipt["total"] <= 15.0 else ("review", receipt),
        accepts="Receipt",
        outcomes={"settled": "Settlement", "review": "Review"},
        pure=True,
    )


# -- composition ----------------------------------------------------------------------


def order_workflow() -> Block:
    gathered = then(receive(), par("gather", {"inventory": reserve(), "taxes": taxes()}, returns="Quote"), on="out")
    charged = then(gathered, charge(), on="out")
    return then(charged, judge(), on="out")


# -- motion ---------------------------------------------------------------------------


def demo(data: dict | None = None) -> Motion:
    return first_motion(
        order_workflow(),
        data if data is not None else {"sku": "sku-1", "amount": 10.0},
        net_name="order",
        instance="order-1",
    )


if __name__ == "__main__":
    motion = demo()
    print(f"net definition: {len(motion.definition)} canonical bytes")
    print(f"history records: {len(motion.records)}")
    print(f"exits: {motion.settled}")
    motion.replay()
    print("replay: rebuilt marking matches, place by place")
