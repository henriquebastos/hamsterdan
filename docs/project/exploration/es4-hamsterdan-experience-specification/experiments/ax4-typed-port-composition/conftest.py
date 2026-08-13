"""ES-004 AX4 composes the accumulated spikes: ES-003 block algebra
and rail, AX2's fence-era leaves (as the drift counterexample), AX3's
attempt-first subnets, and the AX6/AX7 control functions."""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ES4 = _HERE.parent
_ES3 = _ES4.parents[1] / "es3-workflow-ast-authoring-model" / "experiments"

for _sibling in (
    _ES3 / "ax11-real-fragment",
    _ES3 / "ax19-kernel-boundary",
    _ES3 / "ax23-completed-algebra",
    _ES3 / "ax25-failure-rail",
    _ES4 / "ax2-linear-review",
    _ES4 / "ax3-attempt-first",
    _ES4 / "ax6-unified-quiescence",
    _ES4 / "ax7-orthogonal-conversations",
):
    if str(_sibling) not in sys.path:
        sys.path.insert(0, str(_sibling))
