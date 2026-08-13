"""ES-004 AX5 measures the production net against the spike blocks,
so it needs the ES-003 algebra and the AX2/AX3/AX4 spikes on the
path (production is imported normally from the installed package)."""

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
    _ES4 / "ax4-typed-port-composition",
):
    if str(_sibling) not in sys.path:
        sys.path.insert(0, str(_sibling))
