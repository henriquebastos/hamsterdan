"""AX28 builds a general motion harness over AX23's completed algebra
and AX24's parallel combinators, both lowered through the AX19 kernel;
this bridge makes the spike runnable standalone (pytest inserts each
collected test directory into sys.path on full-suite runs)."""

import sys
from pathlib import Path

for _sibling in (
    "ax11-real-fragment",
    "ax19-kernel-boundary",
    "ax23-completed-algebra",
    "ax24-parallel-blocks",
):
    _path = Path(__file__).resolve().parent.parent / _sibling
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
