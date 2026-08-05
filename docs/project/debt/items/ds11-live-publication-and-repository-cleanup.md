---
status: Open
raised: 2026-08-05
related:
  - CV16
  - CV16.DS11
---

# DS11 live publication rejection and disposable repository cleanup remain unresolved

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
Before another live request, the qualification contract must retain a stable
publisher stage/error category and skip replay assertions after zero
publication.

The qualification identity could still read the disposable repository after
the attempt but could not delete it, change it to private, or archive it. Local
coordinates and identity material were erased as required, leaving no authority
in this executor to complete remote disposal. A separately authorized identity
with repository administration/deletion authority must remove that repository
without disclosing its coordinate into durable evidence.

This observation and cleanup debt blocks DS11 live acceptance. It does not
weaken publication fencing, authorize another provider attempt, or expand
support beyond the selected direct-key Pi native A2 Local profile.
