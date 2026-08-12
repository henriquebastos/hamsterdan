"""AX25 builds the failure rail as pure sugar over AX23's algebra and
reuses AX11's engine-driving helpers; this bridge makes the spike
runnable standalone (pytest inserts each collected test directory into
sys.path on full-suite runs)."""

import sys
from pathlib import Path

for _sibling in (
    "ax11-real-fragment",
    "ax19-kernel-boundary",
    "ax23-completed-algebra",
):
    _path = Path(__file__).resolve().parent.parent / _sibling
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
