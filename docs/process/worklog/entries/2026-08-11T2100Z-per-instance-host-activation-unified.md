# Per-Instance host activation unified

Hamsterdan converged direct webhook work, runnable timers and Activity
terminals, and startup/periodic repair on one per-Instance activation boundary.
The boundary serializes pre-settlement, custody activation or provider
reconciliation, post-settlement, runnable posture, and final custody
acknowledgment. Comments now reconcile provider truth exactly once.

Webhook custody gained subject-filtered due retrieval and an uncapped pending
fence so deferred or bounded batches cannot be overtaken by sweep
reconciliation. Active and strict-bound inactive Instances reconstruct for
terminal settlement; sweep repairs inactive Instances even after a
noncanonical runnable hint is lost. Non-actionable observations still finish
without application construction, and route deactivation permits settlement
without new provider work.

The dependency review retained `ActionsState` as one observation/rerun protocol
and `MutationState` as the change/repair mutual-exclusion owner. The Net remains
46 places, 69 transitions, 309 arcs, and 17 retirements. Focused host evidence
passed 108 tests; the full gate passed all static, package, relay, and type
checks plus 540 Python tests with one external route deselected. Independent
adversarial review approved the final custody and restart boundaries.
