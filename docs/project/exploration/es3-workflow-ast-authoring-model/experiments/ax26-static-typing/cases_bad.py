"""AX26 fixture — compositions that MUST be rejected at edit time.

Never imported at runtime (it would raise CompositionError); it exists
only to be fed to pyright and ty. Every line carrying an intentional
mistake ends with an ``# expect-error`` marker; the test asserts each
checker reports an error on exactly the marked lines and nowhere else.

Each case is the static twin of a runtime CompositionError in AX23/24:
the question is whether the checker fires before the engine would.
"""

from __future__ import annotations

from ax26_typed import t_disposable, t_par2, t_pure, t_route, t_then
from cases_good import Order, Raw, Receipt, charge, escalate, judge, parse, reserve, settle

# 1. Sequence with a broken middle: parse yields Order, charge wants the join.
bad_sequence = t_then(parse, charge)  # expect-error

# 2. Route with a handler off its outcome type: when_yes receives Receipt, not Review.
bad_handler = t_route(judge, when_yes=escalate, when_no=escalate, returns=Order)  # expect-error

# 3. Route whose handlers do not converge on the declared result type.
bad_merge = t_route(judge, when_yes=settle, when_no=escalate, returns=Receipt)  # expect-error

# 4. Route missing an outcome: exhaustiveness is structural.
bad_partial = t_route(judge, when_yes=settle, returns=Receipt)  # expect-error

# 5. Parallel branches that disagree on the entry type.
bad_par = t_par2("bad", first=reserve, second=parse)  # expect-error

# 6. A choice is not total: it cannot enter sequence until routed (AX24 totality).
bad_total = t_then(judge, settle)  # expect-error

# 7. Disposable interior containing an effect (reserve is t_step, not t_pure).
bad_fence = t_disposable(reserve)  # expect-error

# 8. Purity is compositional: pure ∘ effectful is not pure, so not disposable.
pure_leaf = t_pure("noop", lambda o: o, accepts=Order, returns=Order)
bad_fence_composed = t_disposable(t_then(pure_leaf, reserve))  # expect-error


# 9. A leaf whose function contradicts its declared ports. KNOWN HOLE:
# neither checker rejects this — pyright widens O to `Raw | Order` (TypeVar
# union-widening across two independent sources), ty solves the generics to
# Unknown. The inference-only leaf `t_fn` closes the hole by removing the
# second source of truth. Marked expect-hole, not expect-error.
def _wrong(raw: Raw) -> Raw:
    return raw


bad_leaf = t_pure("wrong", _wrong, accepts=Raw, returns=Order)  # expect-hole
