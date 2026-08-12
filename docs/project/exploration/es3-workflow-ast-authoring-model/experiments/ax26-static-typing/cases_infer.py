"""AX26 fixture — inference probes: what does each checker deduce
without any annotation from the author? ``reveal_type`` diagnostics are
parsed by the test; the quality of these strings is the quality of the
IDE hover an author would live with."""

from __future__ import annotations

from typing import reveal_type

from ax26_typed import t_disposable, t_fn, t_pure, t_then
from cases_good import Order, _parse, both, charge, parse, reserve, routed

halve = t_pure("halve", lambda o: o, accepts=Order, returns=Order)
double = t_pure("double", lambda o: o, accepts=Order, returns=Order)

reveal_type(t_then(parse, reserve))  # I1: sequence composes I and O
reveal_type(both)  # I2: par aggregate carries both branch types
reveal_type(t_then(halve, double))  # I3: purity overload resolves to TPure
reveal_type(t_then(parse, t_then(both, charge)))  # I4: nested composition stays precise
reveal_type(t_disposable(halve))  # I5: disposable preserves the pure type
reveal_type(routed)  # I6: routed choice is an ordinary total block
reveal_type(t_fn(_parse, pure=True))  # I7: leaf ports inferred from the signature alone
