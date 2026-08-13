"""AX27 reviews generated authoring source against the composition
authority (AX23/AX24 lowered through the AX19 kernel), uses AX26's
typed façade for the no-execution static stage, and demonstrates the
explicitly separate motion stage with AX28's harness; this bridge
makes the spike runnable standalone (pytest inserts each collected
test directory into sys.path on full-suite runs)."""

import sys
from pathlib import Path

for _sibling in (
    "ax11-real-fragment",
    "ax19-kernel-boundary",
    "ax23-completed-algebra",
    "ax24-parallel-blocks",
    "ax26-static-typing",
    "ax28-first-motion",
):
    _path = Path(__file__).resolve().parent.parent / _sibling
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
