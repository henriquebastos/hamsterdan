"""ES-004 AX2 reuses the ES-003 block algebra (AX23), failure rail
(AX25), kernel (AX19), and engine-driving helpers (AX11) unchanged —
the point of the experiment is to express an ES-004 subnet contract
with existing primitives, not to grow new ones."""

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
