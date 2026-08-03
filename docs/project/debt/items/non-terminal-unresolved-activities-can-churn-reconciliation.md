---
status: Resolved
owner: CV3.DS3
observed: 2026-08-02
resolved: 2026-08-03
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
effect and no later append. This closed the source-code uncertainty; live
custody evidence was still required because a drained inbox alone was
insufficient.

After deploying CV3.DS3 commit `c67e777`, the bounded PR20 inspection reported
756 records, 33 requested Activities, 32 completed, one terminal
`ActivityFailed`/`FiringFailed` pair, and zero unresolved Activities. Its inbox
entries were all terminal. This is compatible with the new recovery contract,
but the initial report had not yet retained the before-deployment projection
needed to prove stability across deployment. The later custody pass recovered
that baseline and completed the comparison recorded below.

## Resolution

The source condition is now bounded by a real persisted-History integration
regression: recovery accepts only an unchanged canonical prefix followed by the
exact terminal pair for a previously unresolved occurrence, atomically replaces
both Engine custodians, continues sibling work, publishes one visible effect,
and makes no later append. Divergent or unproven replacement History remains
closed.

PR20's projection was captured before deployment and remained byte-count and
instant stable after deployment, normal sweep, supervised restart, and the full
PR39-44 qualification: 756 records, 33 requested, 32 completed, one explicit
`ActivityFailed`/`FiringFailed` pair, and zero unresolved Activities. Its 31
deliveries remained terminal with no retry churn. Fresh DS3 lifecycle and fault
Instances drained with no unresolved Activity or duplicate effect. The exact
historical four-request intermediate state no longer exists and was not
manufactured by editing History; the corrected regression plus unchanged live
terminal projection satisfy the recovery obligation without a cache-eviction
or synthetic no-progress heuristic.
