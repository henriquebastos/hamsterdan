"""ES-004 AX3 reuses the ES-003 block algebra and helpers unchanged,
exactly as AX2 did — the experiment is about gate discipline, not new
primitives."""

import sys
from pathlib import Path

_ES3 = Path(__file__).resolve().parents[3] / "es3-workflow-ast-authoring-model" / "experiments"

for _sibling in (
    "ax11-real-fragment",
    "ax19-kernel-boundary",
    "ax23-completed-algebra",
    "ax25-failure-rail",
):
    _path = _ES3 / _sibling
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
