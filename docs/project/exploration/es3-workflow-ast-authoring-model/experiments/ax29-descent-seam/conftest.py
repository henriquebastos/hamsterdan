"""AX29 mixes AX23/AX24 algebra blocks with hand-written AX19 kernel
authoring in one file, driven through AX28's harness where the algebra
governs and by hand where it honestly cannot; this bridge makes the
spike runnable standalone (pytest inserts each collected test
directory into sys.path on full-suite runs)."""

import sys
from pathlib import Path

for _sibling in (
    "ax11-real-fragment",
    "ax19-kernel-boundary",
    "ax23-completed-algebra",
    "ax24-parallel-blocks",
    "ax28-first-motion",
):
    _path = Path(__file__).resolve().parent.parent / _sibling
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
