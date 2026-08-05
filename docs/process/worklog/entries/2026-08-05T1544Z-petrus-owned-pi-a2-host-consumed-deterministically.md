# Petrus-owned Pi A2 host consumed deterministically

Hamsterdan now pins Petrus exactly to
`aa5a9152f0c9b36358c0a3019716f47511f64802` and consumes the public owned Pi A2
host boundary. The unchanged `AgentRunner` creates credential-free stable starts
and loads output and settled workspace archives from that one host. Exact A2
READY remains mandatory; AgentNet/A5, subscription profiles, automatic Amp
fallback, and ambient authority remain excluded.

The host supplies immutable read/search policy, a stable direct-key connection
identity, persistent authenticated per-connection key operations, and a one-shot
erasable supplier. Production does not inject Petrus's provider or client-factory
conformance seams, and its supplier deliberately has no authority loader.
Composition and probe do not invoke it.

Synthetic public-seam tests prove fresh execution, output and workspace loading,
continuation session/workspace carry-forward, close-before-History replay without
probe or authority, changed-work conflict, subprocess-death recovery to
indeterminate, cancellation, partial rollback, and idempotent host close. The
unchanged adapter also replays a closed terminal review without authority.

Receiving-host policy is deliberately narrower than the runtime: unchanged
coding requires a published archive, while changed coding is refused before Git
publication because no safe archive-to-current-tree reconciliation exists yet.

Focused suites passed 116 tests. `scripts/check full` passed formatting, Ruff,
ty, nine Bun relay tests, source and wheel builds, and 296 Python tests; the one
explicitly opt-in provider test remained skipped. No ambient credential, direct
authority, paid provider, or live operation was used.

The Local provider's process-memory registry cannot reconcile an active lease
after provider-process death. This slice does not claim exactly-once execution,
forensic erasure, complete migration, or live support.
