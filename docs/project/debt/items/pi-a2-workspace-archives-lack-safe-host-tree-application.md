# Pi A2 workspace archives lack safe host-tree application

**Status:** Accepted deterministic blocker

**Raised:** 2026-08-05

**Related:** CV16.DS11

Petrus publishes a bounded, digest-verified opaque workspace archive only after
aggregate cleanup. It restores that archive for native continuation, but does
not apply or merge it into a receiving host tree. Hamsterdan's unchanged coding
contract publishes a strictly correlated binary patch against the current PR
head. Trusting model-emitted patch text independently of the settled workspace,
or extracting over a live checkout, would create an unfenced split source of
truth.

The adapter therefore requires an archive for unchanged coding and rejects
changed coding as non-retryable before `HostGitPublisher`. The next bounded
slice must extract into private staging, prove the recorded and current trees,
derive one canonical binary patch, verify declared paths and modes, and then use
the existing current-authority and idempotent Git publication fences. This is a
receiving-host policy obligation, not Petrus custody or effect machinery.
