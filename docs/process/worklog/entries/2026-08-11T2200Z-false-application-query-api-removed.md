# False application query API removed

Hamsterdan made `PrReadinessApplication.activate(...) -> None` its sole
application reconciliation command. Public `reconcile`, `route_comment`, and
the lossy dictionary `projection` were removed after repository analysis proved
that production ignored their results.

Application tests now drive the production command and inspect canonical typed
snapshots, lifecycle places, derived waits, and observable conversation effects.
Provider call order, generation lifecycle repair, authority fencing, comment
admission, and Activity composition remain unchanged. The refinement removed
44 net production lines without adding a replacement abstraction or changing the
46-place, 69-transition, 309-arc Net.

Focused host evidence passed 108 tests, static and format checks passed, and an
independent adversarial review approved the result. The next potential
simplification—one provider-ingress comment-admission policy—is deliberately a
separate security-boundary decision.
