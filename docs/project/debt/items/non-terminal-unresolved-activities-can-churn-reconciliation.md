---
status: Accepted
owner: CV3.DS3
observed: 2026-08-02
---

# Non-terminal unresolved activities can churn reconciliation

An older, excluded demo PR20 Instance retains four unresolved Activities while
the pull request is non-terminal. Periodic sweep and webhook retries continue
to return `RuntimeError`; the delivery remains pending under backoff. The
terminal-Instance guard delivered in `a958a32` correctly stopped the equivalent
churn after PR16 closed, but intentionally does not resolve a still-active
Instance with durable in-flight work.

The issue did not block the fresh CV3.DS1 portfolio: PR23-28 drained with no
pending deliveries or runtime failures. It nevertheless needs a bounded,
tested recovery contract under CV3.DS3. Completion requires proving that a
restart with unresolved ActivityRequested records reaches an external wait or
an explicit terminal failure, preserves operation identity and lookup-first
provider recovery, drains custody without duplicate effects, and does not
weaken per-Instance synchronization. Cache eviction and synthetic no-progress
heuristics are not accepted solutions without that evidence.

CV3.DS3 now provides the bounded local recovery contract: an Engine replacement
is accepted only when canonical History preserves the exact prior prefix and
adds the terminal failure pair for a previously unresolved occurrence. The
replacement is installed atomically in both host and authority lease, after
which sibling Activities continue draining. Integration coverage reproduces
the terminal failure with a sibling dashboard effect and proves one visible
effect and no later append. This closes the source-code uncertainty but not the
live debt: PR20 must still be inspected through deployment custody before and
after a normal corrected sweep. A drained inbox alone remains insufficient.

After deploying CV3.DS3 commit `c67e777`, the bounded PR20 inspection reported
756 records, 33 requested Activities, 32 completed, one terminal
`ActivityFailed`/`FiringFailed` pair, and zero unresolved Activities. Its inbox
entries were all terminal. This is compatible with the new recovery contract,
but there is no retained before-deployment History projection proving the exact
transition from the historically churning state. Keep the debt open: current
drainage proves neither that earlier retries used this correction nor that the
same source condition has been live-reproduced without duplicate effects.
