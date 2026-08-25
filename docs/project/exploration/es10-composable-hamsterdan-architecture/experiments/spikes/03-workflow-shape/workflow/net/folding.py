"""Shared pure-fold helpers (spike; hydration redesigned).

Provenance: `route`/`values`/`revive` from
src/hamsterdan/readiness/net_v5/folding.py at 0686067. The redesign: no
`vars()` discovery registry. `values()` hydrates each requested type by
matching its class name against token colors — the color IS the class name,
and every fold names exactly the types its arcs bind — and `revive()` builds
the adapter from the class it is handed.
"""

from __future__ import annotations

import json

from petrus.impetus.petrinet import Token
from pydantic import TypeAdapter

_ADAPTERS: dict[type, TypeAdapter] = {}


def _adapter(cls: type) -> TypeAdapter:
    adapter = _ADAPTERS.get(cls)
    if adapter is None:
        adapter = _ADAPTERS[cls] = TypeAdapter(cls)
    return adapter


def _canonical(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def values(binding, *types):
    """Hydrate one strict value per requested type, matched by token color."""
    tokens = [token for _, selected in (*binding.read, *binding.consumed) for token in selected]
    return tuple(
        _adapter(kind).validate_json(_canonical(next(token for token in tokens if token.color == kind.__name__).data))
        for kind in types
    )


def revive(cls, data: dict):
    """Hydrate a strict workflow value from a JSON-faithful dict."""
    return _adapter(cls).validate_json(_canonical(data))


def route(outputs, mapping):
    """Emit strict values only on the targets named in mapping."""
    return {
        out.target: tuple(Token(out.color, value.dump()) for value in mapping[str(out.target)])
        for out in outputs
        if str(out.target) in mapping
    }
