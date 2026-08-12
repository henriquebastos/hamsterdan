"""AX13 imports AX11's spike modules (predicates, AST, compiler, fragment)
as shared vocabulary. Pytest inserts each collected test directory into
sys.path, so full-suite runs resolve them already; this bridge makes the
AX13 directory runnable standalone too."""

import sys
from pathlib import Path

_AX11 = Path(__file__).resolve().parent.parent / "ax11-real-fragment"
if str(_AX11) not in sys.path:
    sys.path.insert(0, str(_AX11))
