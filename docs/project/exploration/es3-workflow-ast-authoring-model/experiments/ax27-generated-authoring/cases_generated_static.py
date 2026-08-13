"""AX27 static-stage fixture — a generated candidate reviewed WITHOUT execution.

Never imported at runtime (composing it would raise CompositionError);
it exists only to be fed to the pinned pyright over AX26's typed
façade. This is the loop's no-execution stage: a generator gets the
mistake rejected from the source text alone, before `review` ever
executes the authoring code. The mistake is the classic generated one:
chaining a step against the wrong color (parse yields Order; charge
wants the parallel join).
"""

from __future__ import annotations

from ax26_typed import t_then
from cases_good import charge, parse

bad_generated_chain = t_then(parse, charge)  # expect-error
