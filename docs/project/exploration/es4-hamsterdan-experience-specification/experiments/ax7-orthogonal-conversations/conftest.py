"""ES-004 AX7 builds directly on the AX6 control states — the point is
that conversations are orthogonal TO that machine, so it imports the
machine rather than redefining it."""

import sys
from pathlib import Path

_AX6 = Path(__file__).resolve().parent.parent / "ax6-unified-quiescence"

if str(_AX6) not in sys.path:
    sys.path.insert(0, str(_AX6))
