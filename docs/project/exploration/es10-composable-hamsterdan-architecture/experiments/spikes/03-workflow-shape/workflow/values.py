"""Workflow value mechanism and cross-group aliases (spike).

Provenance: `WorkflowModel` copied from src/hamsterdan/contracts/readiness.py
at 0686067; `Phase` from src/hamsterdan/contracts/readiness_v5.py.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import TypeAdapter

Phase = Literal["running", "quiescent", "terminal"]


class WorkflowModel:
    """Strict, frozen, JSON-faithful workflow value."""

    def dump(self) -> dict[str, Any]:
        """Return the canonical JSON payload for a workflow value."""
        return TypeAdapter(type(self)).dump_python(self, mode="json")

    def validated_update(self, **changes: object):
        """Return a fully revalidated update rather than an unchecked model copy."""
        payload = self.dump() | {
            key: TypeAdapter(type(value)).dump_python(value, mode="json") if isinstance(value, WorkflowModel) else value
            for key, value in changes.items()
        }
        return TypeAdapter(type(self)).validate_json(json.dumps(payload))


# This module owns mechanism and aliases, no token colors.
TOKENS: tuple[type, ...] = ()
