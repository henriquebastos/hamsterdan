"""ES-006 AX5 reuses ES-003's proven variant-routing helpers unchanged
(the same pattern ES-004 used) — the experiment is about the kill
residue, not new machinery."""

import sys
from pathlib import Path

_ES3 = Path(__file__).resolve().parents[1] / "es3-workflow-ast-authoring-model" / "experiments"

_path = _ES3 / "ax5-type-branching"
if str(_path) not in sys.path:
    sys.path.insert(0, str(_path))
