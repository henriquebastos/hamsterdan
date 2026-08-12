"""AX15 composes the recovery concern with AX11's base and AX14's change
concern, so those spike modules are shared vocabulary. Pytest inserts each
collected test directory into sys.path on full-suite runs; this bridge
makes AX15 runnable standalone."""

import sys
from pathlib import Path

for _sibling in ("ax11-real-fragment", "ax13-sibling-amortization", "ax14-fragment-composition"):
    _path = Path(__file__).resolve().parent.parent / _sibling
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
