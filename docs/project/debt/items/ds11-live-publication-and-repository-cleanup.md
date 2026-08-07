---
status: Resolved
raised: 2026-08-05
resolved: 2026-08-07
related:
  - CV16
  - CV16.DS11
---

# DS11 publication observation and disposable repository cleanup resolved

The first authority-bearing Pi native A2 Local qualification returned one
controlled mutation candidate to the production host, but the real
`HostGitPublisher` rejected it before ref advancement. Sanitized evidence does
not distinguish a product publication defect from a mismatch in the bounded
synthetic GitHub authority used to target the disposable repository.

Credential-free follow-up proved the complete production receiver, publisher,
object-write, exact-CAS, and idempotent replay path succeeds against a bounded
local authority. It also proved the retained `GitPublishError` was a secondary
empty-patch replay error raised by the harness after the original publication
rejection had already become a failed typed Activity result. The original
sanitized reason was not retained. The exact rejection is therefore
classification C—not deterministically reproducible from retained safe evidence.
The follow-up slice resolves that observation gap. Canonical Activity results
retain one closed publisher stage category, and a one-shot qualification state
machine skips schema/tree/replay after zero or failed publication while keeping
replay and cleanup failures separate. Arbitrary/private diagnostics cannot enter
the retained shape. The deterministic code is eligible to request a fresh
separately authorized attempt; the erased first-attempt reason remains
classification C and is not retroactively inferred.

The qualification identity could still read the disposable repository after
the attempt but could not delete it, change it to private, or archive it. The
Navigator later authorized and performed exact-target deletion. Qualification
checked only that target, observed not-found, erased the mode-`0600` coordinate
handoff, and did not enumerate or mutate another repository.

The later authorized provider attempt completed one production operation but no
changed coding result crossed admission, so publication assertions remained
suppressed. That live-admission gap is delivery evidence rather than orphaned
remote cleanup debt. This item is resolved; it does not mark DS11 Done,
authorize another provider attempt, or expand support beyond the selected
direct-key Pi native A2 Local profile.
