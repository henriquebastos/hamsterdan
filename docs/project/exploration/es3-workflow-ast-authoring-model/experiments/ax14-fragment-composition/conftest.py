"""AX14 composes fragments authored in AX11 and AX13, so their spike
modules are shared vocabulary. Pytest inserts each collected test directory
into sys.path on full-suite runs; this bridge makes AX14 runnable standalone."""

import sys
from pathlib import Path

for _sibling in ("ax11-real-fragment", "ax13-sibling-amortization"):
    _path = Path(__file__).resolve().parent.parent / _sibling
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
