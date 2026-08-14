"""ES-007 reuses ES-003's proven variant-routing helpers unchanged
(same as ES-006) — the experiments are about the complete V5 topology
and the courier, not new dispatch machinery."""

import sys
from pathlib import Path

_ES3 = Path(__file__).resolve().parents[1] / "es3-workflow-ast-authoring-model" / "experiments"

_path = _ES3 / "ax5-type-branching"
if str(_path) not in sys.path:
    sys.path.insert(0, str(_path))
