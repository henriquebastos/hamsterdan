# Actions assessment given one provider owner

Hamsterdan replaced duplicated GitHub Actions job/result interpretation in
application reconciliation and durable Activity discovery with one immutable
provider-owned `ActionsEvidence` assessment. Exact-run selection remains
explicit, preserving the Activity's absent-run-before-policy ordering. Provider
pending state now has one `queued`/`in_progress` normalization, failed required
jobs have one deterministic selection, and unsupported terminal conclusions
fail closed at the provider boundary.

The unused `VerifiedSnapshot` aggregate and `verified_snapshot()` read were
deleted. Workflow identity, current authority, Activity operation context, and
rerun ownership remain with their existing consumers; the Net is unchanged.

Focused evidence passed 194 tests. `scripts/check quick` passed. Full static,
format, type, package, and relay gates passed; the Python suite passed 577 tests
with one external route deselected. Independent adversarial review approved the
provider/application boundary with no release blocker.
