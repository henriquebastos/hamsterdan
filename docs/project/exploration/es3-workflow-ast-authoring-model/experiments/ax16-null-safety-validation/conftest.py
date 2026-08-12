"""AX16 validates predicates over AX11's node vocabulary and proves the
absorption semantics against AX15's real recovery guards, so those spike
modules are shared vocabulary. Pytest inserts each collected test directory
into sys.path on full-suite runs; this bridge makes AX16 runnable
standalone."""

import sys
from pathlib import Path

for _sibling in (
    "ax11-real-fragment",
    "ax13-sibling-amortization",
    "ax14-fragment-composition",
    "ax15-recovery-concern",
):
    _path = Path(__file__).resolve().parent.parent / _sibling
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
