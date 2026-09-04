---
status: Accepted
raised: 2026-09-04
revisit: Before the CV19 production proof package is declared complete
related:
  - ../../decisions/records/2026-09-02T0320Z-findings-publish-as-per-finding-inline-suggestions.md
  - ../../roadmap/cv17-v5-actor-loop-production-parity/cv17-ds3-durable-recovery.md
---

# Blocked publication results omit the provider failure class

The discarded PR #64 production run retained all three review findings and the
stable publication operation after only the first inline comment landed. The
explicit recovery operation later published the other two findings unchanged
and without duplicating the first. This proves the durable recovery contract,
but the `ReviewBlocked` Activity result retained no bounded provider reason, so
the original HTTP status or transport failure cannot be distinguished from
History.

The inline publisher now retries recognized transient HTTP outcomes once after
lookup-first reconciliation, GitHub's documented 60-second secondary-limit
pause, and a fresh authority fence. The remaining diagnostic obligation is to
carry a secret-safe failure class through the blocked Activity result and
operator inspection without storing provider payloads.

PR #67 showed that the remaining rejection does not enter that transient path:
the third inline comment was absent and `review.publish` completed immediately.
The blocked terminal now retains a closed failure class, HTTP status, and a
bounded structural error shape made only from validated field/code atoms. It
does not retain GitHub's message or response body. A fresh production run is
still required to identify and remove the rejected request shape.

That fresh diagnostic on PR #68 retained `transport_ambiguity`, no HTTP status,
and no provider detail after the first finding landed. The HTTP retry had been
paced, but the transport-exception branch still retried immediately after its
absent-marker lookup. The publisher now gives that branch the same bounded
60-second pause before its fresh fence and only retry.

Resolve this item when a blocked publication report distinguishes at least a
transport ambiguity, a transient HTTP rejection, and a capability denial; the
classification survives restart and export; and tests prove no credential or
unbounded provider body enters History.
