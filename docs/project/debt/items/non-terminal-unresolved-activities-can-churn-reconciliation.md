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
