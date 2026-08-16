---
code: CV17.DS3
level: Delivery Story
status: Complete
status_reason: Selected V5 converges across publication, inline-effect, timer-wake, and durable webhook host-restart cuts without duplicate effects
updated: 2026-08-16
---

# CV17.DS3 — Durable V5 recovery

## Scope

Prove that the selected non-sharded V5 topology recovers from process death
using canonical Petrus History and the host's durable custody stores. Recovery
must converge from retained evidence without silently repeating an external
effect. Production remains untouched and default.

## Delivered slice

### DS3.0 — Durable publication claim expiry

Reply, dashboard, and readiness-announcement Activities now freeze their
provider operation as Motus correlation and idempotency and explicitly permit
one attempt. If a worker dies after claiming that attempt, LocalDispatch's
`DeadlineExceeded` terminal projects from the original immutable request to
`ReplyBlocked`, `DashBlocked`, or `ABlocked`. The original occurrence completes
through its typed terminal and is never automatically requeued. Every other
failure kind stays projection-pending and fails loudly.

The owning actor loop retains the exact request. Only an authorized
`recover_publication` command creates a fresh occurrence; that occurrence
preserves the same provider identity and full original authority claim, so the
existing gate performs lookup-first reconciliation before any fence or write.
Repeated restart before recovery is history-stable.

Tests exercise all three gates through real SQLite LocalDispatch claim expiry,
JSONL History reload, typed folding, a second stable reload, and explicit
recovery. `scripts/check full` passes with 1,015 Python tests, nine Bun relay
tests, formatting, Ruff, typing, and package builds. Oracle boundary review
returned `clear to commit`.

### DS3.1 — Inline effect crash recovery

Review-agent execution, findings publication, rerun issuance, and mutation now
remain on `InlineDispatch` while their canonical `ActivityRequested` records
freeze one provider operation and `ExecutionPolicy(attempts=1)`. Restart
redispatches the unresolved occurrence from History. Each provider or Agenticus
ledger reconciles the stable operation before repeating an effect; unexpected
failures remain loud. Review execution and findings publication are separate
crash boundaries, while mutation evidence covers both agent-before-push and
post-push cuts.

Operation identities are validated before dispatch against the grammar and
bound of the ledger that must settle them. Comment-backed operations use the
strict GitHub marker grammar; review and git operations permit bounded
non-whitespace printable ASCII supported by Agenticus and commit trailers.
The review fold also derives a deterministic marker-safe findings identity for
non-provider-shaped test heads; ordinary production SHA identities are
unchanged.

`RoundOpen` remains provider-neutral and frozen in Petrus History. Before the
first Agenticus submission, the host composes the credential-free
`ReviewRequest` and commits its canonical JSON plus digest to an
operation-keyed SQLite custody store. Restart looks up that snapshot before
reading current comments or check evidence, validates it against the retained
round, and submits the exact original request. Reusing the operation for a
different round or loading a damaged snapshot fails loudly rather than
becoming `RoundUnable`.

The kill/restart suite covers pre-effect replay, landed effects with a lost
Activity terminal, repeated restart convergence, exact Activity identity and
policy payloads, provider movement, unreadable review context, Agenticus
request conflict avoidance, and malformed identity rejection. `scripts/check
full` passes with 1,046 Python tests, nine Bun relay tests, formatting, Ruff,
typing, and package builds. Oracle boundary review traced both prior blockers
and the complete replay path, then returned `clear to commit`.

### DS3.2 — Reminder and timer-wake crash recovery

Reminder publication now uses the same identified inline recovery boundary as
the other provider effects. Petrus History freezes the immutable
`reminder:{timer_id}` correlation and idempotency under a one-attempt policy.
On redispatch after a lost Activity terminal, the publication gate reconciles
that marker before reading the current authority claim or recipients, so an
already-landed reminder is not posted again. Marker grammar and size are
validated before dispatch.

Canonical timer custody remains the typed `TimerCommandApplied` and `TimerDue`
deliveries in Petrus History. The per-Instance `V5TimerStore` and host-wide
`RunnableIndex` remain rebuildable projections. The selected-V5 host crash
test cuts after timer maturity, reminder publication, rearm, and History
settlement but before `RunnableIndex.replace_timer`. It then removes both
projections, restarts the host, and proves startup reconstructs the next wake,
does not repeat the landed reminder, and publishes exactly once at the rebuilt
deadline.

The focused recovery, timer, runnable, and host portfolio passes with 178
tests. `scripts/check full` passes with 1,054 Python tests, nine Bun relay
tests, formatting, Ruff, typing, and package builds. Oracle boundary review
traced the inline replay and projection-rebuild paths, then returned `clear to
commit`.

### DS3.3 — Durable webhook host-restart composition

The final slice proves the outer host crash gap without changing production
code. A real selected-V5 `HostService` accepts a webhook into durable pending
custody, stages its immutable manifest and authority grant, executes one
identified Agenticus review, commits its Petrus History and timer posture, and
then dies before `WebhookCustody.acknowledge`.

Restart uses the real startup sweep. Even after provider head truth changes,
the host replays the frozen webhook manifest without another provider read,
Agenticus call, History delivery, or synthetic reconciliation. It terminally
acknowledges the original delivery with zero retries, retains the original
webhook-sourced authority revision, and keeps one timer wake hint. Graceful
resource cleanup between the simulated processes also leaves the retained
state unchanged.

The focused selected-host, ingress, and inline-recovery portfolio passes with
147 tests. `scripts/check full` passes with 1,055 Python tests, nine Bun relay
tests, formatting, Ruff, typing, and package builds. Oracle found one stale
root-roadmap status, verified its correction, and returned `clear to commit`.

The complete DS3 portfolio now spans durable publication claim expiry,
identified inline effect replay, timer and runnable projection rebuild, frozen
reconciliation replay, and durable webhook acknowledgement recovery through
the selected host route. Torn JSONL repair remains an operator concern and is
not a workflow recovery behavior.

## Done condition

Every durable V5 custody boundary has deterministic restart evidence, no
unproven external effect is repeated automatically, and the selected host route
converges through the complete non-sharded recovery portfolio.

## Boundaries

- Production topology, wiring, and behavior are not modified.
- Unknown terminal failures remain loud; DS3 does not introduce a generic
  requeue or retry API.
- Sharding and the courier remain outside CV17.
