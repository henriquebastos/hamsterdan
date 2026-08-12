"""AX20 authors its subnet in the AX19 boundary kernel, reuses AX11's
engine-driving helpers, and measures the AX13 baseline's guard smear;
this bridge makes the spike runnable standalone (pytest inserts each
collected test directory into sys.path on full-suite runs)."""

import sys
from pathlib import Path

for _sibling in (
    "ax11-real-fragment",
    "ax13-sibling-amortization",
    "ax19-kernel-boundary",
):
    _path = Path(__file__).resolve().parent.parent / _sibling
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
