---
code: CV17.DS2
level: Delivery Story
status: Active
status_reason: DS2.2b1 Net-side timer protocol complete; DS2.2b2 host timer custody is next
updated: 2026-08-15
---

# CV17.DS2 — Host composition for the V5 topology

## Scope

Real host composition for V5 as a parallel selectable implementation:
webhook custody feeds the ingress doors, the eight gates bind to real
provider surfaces through the existing dispatcher stack, and one
fail-closed switch selects the topology at composition time. Production
stays untouched and default.

An Oracle boundary review (pre-implementation) found one prerequisite
contract gap and two host-boundary hazards; the slicing reflects them:

- **DS2.0 — Mutation contract closure.** `MutationRequest`/`MutWork`
  carry identity and authority but no requested change: no kind, no
  human instruction (the conversation fold drops `IntentFact.arg`), no
  repair evidence identity. A real `git_gate` (coding agent + CAS push
  as ONE classified activity, production's `_code` shape) cannot exist.
  Also: a clean agent-unable outcome has no variant — `Pushed | MovedM
  | FaultM` forces a dishonest classification. Add the typed payload
  through `MutationRequest -> MutState/FaultM -> MutWork` and a fourth
  `DeclinedM` variant folding to the `declined` settlement escalation
  already consumes. No external host ledger: History stays canonical.
  **Done.** The slice's Oracle review added two rulings, both applied:
  the gate fences authority BEFORE the coding agent runs (a decline
  means the authority the agent began under stood; a close that lands
  before the gate starts classifies moved — the genuine mid-agent
  decline needs a controllable mid-activity seam, deferred to DS2.1),
  and settlements carry the stable `op_key` so readiness's pending gate
  is an identity ledger — an older round's settlement can never clear a
  newer same-kind round regardless of fact fold order (pinned by a pure
  permutation test against `readiness._apply`).
- **DS2.1 — Provider-backed gates.** The eight gate activities against
  GitHubAuthority / CommentPublisher / HostGitPublisher /
  RoutedAgentRunner, declared with VariantPayloadConverter; the host
  grant read fresh from the `life.state` baton via a V5 lease. TDD with
  fake transports per existing host test conventions. Publication
  gates (DS2.1a), rerun (DS2.1b), and the review agent (DS2.1c) are
  complete. DS2.1c gives each round one globally scoped, restart-
  settleable operation; carries prior findings through validated agent
  lineage rather than concatenation; and folds typed clean inability
  into fail-closed readiness/dashboard review status without treating
  it as an effect fault. **Done.** The mutation/git gate reconciles the
  provider operation before any claim or agent read, fences the full
  claim before and after one globally scoped attempt-1 coding operation,
  then publishes through exact ref CAS. Petrus/Pi replays a durably
  settled coding result after a pre-CAS crash; a post-CAS crash finds the
  exact operation commit anywhere on the PR's reachable first-parent
  history by request digest and ordered parents. Clean agent inability
  declines, proven movement reports the full observed claim, and every
  unproven publication terminal retains exact recovery work as `FaultM`.
  Agent-route startup repair deliberately leaves `FaultM` unresolved so
  human recovery can reclaim the same Pi result; known terminals settle
  the route.
- **DS2.2a — Durable ingress and authority ordering.** **Done.** The
  topology-neutral webhook inbox remains the sole custody owner. A
  formal application protocol lets the host pass each full custodied
  observation to either topology. V5 normalizes provider truth once,
  then atomically commits an immutable per-delivery manifest and the
  per-PR host authority grant in the same WAL database before delivering
  canonical identified entries to Petrus. Replay reuses the frozen
  manifest and identities, so an entry committed before a crash
  deduplicates while missing entries continue. Same-PR custody is strict
  row order, authenticated draft/ready edges survive provider-state
  collapse, and each V5 instance has its own durable publication queue.
  The host never claims that queue while the PR has unresolved custody,
  while unrelated PRs and production continue; fresh unstaged custody
  also fences the final provider cut. Comment classification is frozen
  into the manifest; route settlement is idempotently replayed after
  the manifest commit.
  A crash between classification and that commit may rerun the
  classifier; DS3 exercises this retained limitation. V5 remains
  non-selectable in this slice.
- **DS2.2b — Host-owned reminder timers.** **Net-side protocol complete
  (DS2.2b1).** Lifecycle admission/resume and draft mail monotonic,
  incarnation-scoped clock intent to the reminder actor. The actor
  serializes that intent through one persistent typed command token;
  identified acknowledgements settle exact arm/cancel operations, and
  full identified maturity is effective only for the currently armed
  timer generation. Stale maturity remains a durable inert fact,
  snoozed maturity becomes overdue, and close cannot retire before the
  host acknowledges cancellation. Timer and command identities include
  the globally unique workflow subject. Competing lifecycle mail is
  order-safe: pause dominates start at one incarnation and only a newer
  incarnation can reactivate. Human `defer` remains a review finding
  disposition and never becomes a duration or timer command.
  **Host custody remains (DS2.2b2):** apply commands into a durable,
  restart-reconstructible timer store, deliver identified
  acknowledgements and `on_timer` maturities, and rebuild
  `RunnableIndex` strictly as a non-authoritative wake hint.
- **DS2.3 — The fail-closed switch.** A composition descriptor
  (topology identity, application factory, durable activity names,
  unresolved predicate, inactive-route result adapter) instead of the
  production-only module constants; topology-labeled state binding so a
  History can never silently reopen under the other net; unknown
  selection fails startup. Integration test drives a webhook through
  custody into the V5 doors.

## Ruled hazards to pin in tests

- **Announce grant staleness:** a queued draft->ready cycle leaves
  head/base/policy identical while only the grant incarnation moves; a
  durable `announce_gate` holding the instance lock must still classify
  moved. Pin the timeline through the real host before accepting
  durable announce (same-subject custody ordering or a pending-custody
  fence).
- **Durable/inline split mirrors production counterparts:** reply,
  announce, dash durable ("publication" queue); rerun, review, publish,
  git, reminder inline — inline crash recovery is lookup-first
  reconciliation plus engine redispatch of unresolved requests.
- **The V5 publisher fence is NOT the legacy production fence**
  (DS2.1b Oracle ruling): the legacy fence resolves production request
  bases, and operation + epoch/head alone is insufficient — the same
  rerun operation can be reissued after a same-incarnation base/policy
  refresh. The V5 fence must recover the active request's full claim
  and compare phase, incarnation, head, base, AND policy immediately
  before the POST, raising the typed proven-movement refusal
  (RerunRefusedError-style), never a bare boundary error.
- **V5 newest-evidence selection must not use `select_run`:**
  `GitHubAuthority.workflow_runs` sorts by `(attempt, id)` while the V5
  contract orders evidence lexicographically by `(run_id, attempt)`;
  the rerun cut already computes `max((id, attempt))` itself, and DS2.2
  door normalization must do the same.

## Out of scope

- Any change under `readiness/net` or to production wiring/behavior.
- Sharding, the courier, DS3 kill/restart scenarios, DS4 comparison.

## Done condition

V5 is selectable through the fail-closed switch, a webhook flows from
custody through normalization into the doors, all eight gates execute
against provider fakes through the real dispatcher stack, and
`scripts/check full` is green with production defaults unchanged.
