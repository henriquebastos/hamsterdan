"""Shared pure-fold helpers for the V5 actor-loop topology.

Every V5 decision is a pure fold: hydrate the bound tokens into strict
workflow values, compute, and emit strict values on named targets.
"""

from __future__ import annotations

import json

from petrus.impetus.petrinet import Token
from pydantic import TypeAdapter

from hamsterdan.contracts import readiness_v5 as _colors
from hamsterdan.contracts.readiness import WorkflowModel

_TOKEN_ADAPTERS = {
    value.__name__: TypeAdapter(value)
    for value in vars(_colors).values()
    if isinstance(value, type) and issubclass(value, WorkflowModel) and value is not WorkflowModel
}


def values(binding, *types):
    """Hydrate the bound tokens and select one strict value per type."""
    hydrated = []
    for _, selected in (*binding.read, *binding.consumed):
        for token in selected:
            hydrated.append(
                _TOKEN_ADAPTERS[token.color].validate_json(
                    json.dumps(token.data, sort_keys=True, separators=(",", ":"))
                )
            )
    return tuple(next(value for value in hydrated if isinstance(value, kind)) for kind in types)


def route(outputs, mapping):
    """Emit strict values only on the targets named in mapping."""
    return {
        out.target: tuple(Token(out.color, value.dump()) for value in mapping[str(out.target)])
        for out in outputs
        if str(out.target) in mapping
    }
