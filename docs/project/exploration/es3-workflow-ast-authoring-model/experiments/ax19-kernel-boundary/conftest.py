"""AX19 reuses AX11's engine-driving helpers; this bridge makes the
spike runnable standalone (pytest inserts collected test directories
into sys.path on full-suite runs)."""

import sys
from pathlib import Path

_path = Path(__file__).resolve().parent.parent / "ax11-real-fragment"
if str(_path) not in sys.path:
    sys.path.insert(0, str(_path))
