"""The current-authority claim the V5 gates fence against.

A fenced gate compares EVERY claimed authority field immediately before
its effect (A1.5): the live provider fields (head, base, policy) AND
the host grant (phase, incarnation). The provider fields come from a
fresh read; the grant comes from the host-owned lifecycle record — the
same record the ingress path applies to the world BEFORE the net
observes it (host-before-net ordering). The gates take the claim as a
zero-argument port so the read is fresh per call and the composition
(DS2.2) owns where it comes from.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hamsterdan.contracts.readiness_v5 import Phase


@dataclass(frozen=True)
class CurrentClaim:
    """One fresh observation of the complete current authority."""

    phase: Phase
    incarnation: int
    head: str
    base: str
    policy: str


ClaimReader = Callable[[], CurrentClaim]
