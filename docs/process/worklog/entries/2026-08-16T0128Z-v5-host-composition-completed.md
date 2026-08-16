# V5 host composition completed

CV17.DS2 completed production-capable host composition for the non-sharded V5
actor-loop topology while leaving production untouched and default. V5 now has
provider-backed review, mutation, publication, and rerun gates; durable
identified webhook ingress and reminder-timer custody; host-before-net
authority ordering; and fail-closed topology selection with isolated durable
state and workers.

The final slice added one contiguous per-subject authority lineage for
custodied webhooks and synthetic reconciliation. Immutable globally identified
manifests commit atomically with their authority grant, canonical Petrus History
governs replay, pending webhook custody fences reconciliation, and the selected
V5 HostService route is exercised end to end. Startup and periodic provider
projections reuse unchanged identities, advance changed or post-webhook truth,
and recover committed partial delivery after restart.

Focused ingress and host-service suites, quick checks, and the full project gate
passed. Oracle boundary review found and verified fail-closed migration,
lineage, corruption, and replay hardening, then returned `clear to commit`.
CV17 remains active; durable V5 kill/restart/converge recovery is next in DS3.
