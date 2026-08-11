# Agent execution identity made explicit

Hamsterdan replaced the host-to-agent `ContextVar` and two-call dispatch
handshake with explicit logical operation and Attempt arguments on every agent
call. A host-owned routed runner now claims durable composition ownership before
qualification or provider execution, while Pi alone derives stable distinct
runtime identities for each Attempt.

Focused evidence passed 209 tests with one external test skipped. Quick and
full static/type/format/package and relay gates passed; the Python suite passed
593 tests with one external route deselected. Final adversarial review approved
route custody, replay/retry identity, qualification ordering, and legacy
behavior with no release blocker.
