"""The workflow composer (spike): declare all, wire all, validate the
token-class registry, and bind nothing effectful.

Cycle removal: loop modules are imported by full module path (`import
workflow.net.ci as ci`), never through a package initializer, and no
initializer re-exports this module — so the current `net_v5 <-> topology`
strongly connected component cannot form.

Provenance: composition and seed protocol from
src/hamsterdan/readiness/net_v5/topology.py at 0686067.
"""

from __future__ import annotations

import workflow.activities as activities
import workflow.facts as facts
import workflow.net.ci as ci
import workflow.net.escalation as escalation
import workflow.net.life as life
import workflow.observations as observations
import workflow.values as values
from petrus.impetus.dsl import BuiltNet, NetSpec
from petrus.impetus.petrinet import Marking

_LOOPS = (life, ci, escalation)
_VOCABULARY = (values, observations, facts, activities)

MANIFEST = activities.MANIFEST

# transition path -> activity name; variants, lane, identity, and blocked
# synthesis come from the manifest (one source of truth)
GATES: dict[str, str] = {}
for _loop in _LOOPS:
    for _path, _activity in _loop.GATES.items():
        if _path in GATES:
            raise ValueError(f"duplicate gate declaration for {_path}")
        GATES[_path] = _activity


def _token_classes() -> dict[str, type]:
    """The explicit token-class registry: every color the workflow may
    durably record, aggregated from each owner's TOKENS export."""
    registry: dict[str, type] = {}
    for module in (*_VOCABULARY, *_LOOPS):
        for cls in module.TOKENS:
            existing = registry.get(cls.__name__)
            if existing is not None and existing is not cls:
                raise ValueError(
                    f"token color {cls.__name__!r} is owned twice: {existing.__module__} and {cls.__module__}"
                )
            registry[cls.__name__] = cls
    return registry


TOKEN_CLASSES: dict[str, type] = _token_classes()


def _validate(net, registry: dict[str, type], gates: dict[str, str], manifest) -> None:
    """Fail at build time — not at hydration time — when a declared color,
    gate, or manifest entry has no registered owner."""
    for path, place in net.places.items():
        if place.color is not None and place.color not in registry:
            raise ValueError(
                f"place {path} declares color {place.color!r} with no registered "
                f"token class — a rename must update the owning module's TOKENS"
            )
    for path, activity in gates.items():
        declaration = manifest.get(activity)
        if declaration is None:
            raise ValueError(f"gate {path} names activity {activity!r} absent from the manifest")
        for cls in (declaration.request, *declaration.results):
            if registry.get(cls.__name__) is not cls:
                raise ValueError(f"gate {path} uses {cls.__name__!r} which is not the registered token class")


def build_net() -> BuiltNet:
    net = NetSpec("pr_readiness")
    for loop in _LOOPS:
        loop.declare(net.s)
    for loop in _LOOPS:
        loop.wire(net)
    built = net.build()
    _validate(built.net, TOKEN_CLASSES, GATES, MANIFEST)
    return built


def seed_marking(subject: str) -> Marking:
    """The newborn Instance, bound to one globally unique host subject."""
    if (
        not isinstance(subject, str)
        or not subject
        or len(subject.encode()) > 900
        or not subject.isascii()
        or not subject.isprintable()
    ):
        raise ValueError("workflow subject is malformed")
    contributions: dict = {}
    for loop in _LOOPS:
        for path, tokens in loop.seed().items():
            if path in contributions:
                raise ValueError(f"duplicate seed contribution for {path}")
            contributions[path] = tokens
    return Marking(contributions)
