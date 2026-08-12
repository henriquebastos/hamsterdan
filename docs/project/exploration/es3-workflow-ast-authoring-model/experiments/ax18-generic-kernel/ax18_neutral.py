"""AX18 neutral net — arbitrary-net shapes the domain AST cannot say.

A deliberately domain-free net, authored *directly* in the kernel IR,
exercising exactly the features the AX11 vocabulary has no words for:

- **two same-color places** (``left`` and ``right``, both ``Slot``) —
  under AX11 every place enters through a typed port bound to a lane,
  state, or read role; a free-standing pair of same-color places with a
  shuttle between them has no authoring form;
- **a cycle** — ``shuttle_right`` and ``shuttle_left`` move one token
  back and forth; the AX11 fragment body is a DAG walk (activity chain
  into a scatter), and choices only ever consume a lane place;
- **pure token-game transitions** — no handler anywhere: frozen Petrus
  default-binds ``passthrough``, which forwards consumed tokens through
  every color-admitting output arc;
- **bounded liveness via marking, not guards** — the cycle terminates
  because ``fuel`` (three ``Pellet`` tokens) is consumed one per lap,
  not because any guard counts iterations;
- **a guard over a read place** — ``meter.enabled`` gates which of two
  competing consumers of ``left`` may fire (shuttle vs drain), the
  kernel's smallest demonstration that guards + read arcs express
  state-dependent competition without any handler;
- **a disconnected place** — ``spare`` has no arcs at all; kernel and
  frozen build both accept it.

No Python model types exist for ``Slot``, ``Pellet``, or ``Meter``:
colors are nominal strings, tokens are seeded as raw data. The kernel
needs Python types only where *handlers* hydrate values — and this net
has no handlers.
"""

from __future__ import annotations

from ax18_kernel import (
    KernelNet,
    KernelPlace,
    KernelTransition,
    consume,
    kernel_net,
    produce,
    read,
)


def shuttle_net() -> KernelNet:
    return kernel_net(
        "ax18-shuttle",
        KernelPlace("left", "Slot"),
        KernelPlace("right", "Slot"),
        KernelPlace("spare", "Slot"),  # disconnected: declared, never touched
        KernelPlace("fuel", "Pellet"),
        KernelPlace("meter", "Meter"),
        KernelTransition(
            name="shuttle_right",
            arcs=(read("meter"), consume("left"), consume("fuel"), produce("right")),
            guard="meter[0].data.enabled == true",
            label="move the slot right while the meter is on, burning one pellet",
        ),
        KernelTransition(
            name="shuttle_left",
            arcs=(consume("right"), produce("left")),
            label="return the slot — the cycle edge",
        ),
        KernelTransition(
            name="drain",
            arcs=(read("meter"), consume("left")),
            guard="meter[0].data.enabled == false",
            label="retire the slot once the meter is off",
        ),
    )
