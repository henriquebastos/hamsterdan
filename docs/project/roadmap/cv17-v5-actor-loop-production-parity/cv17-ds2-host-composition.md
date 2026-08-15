---
code: CV17.DS2
level: Delivery Story
status: Active
status_reason: Oracle boundary review reshaped the slicing; DS2.0 contract closure first
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
  fake transports per existing host test conventions.
- **DS2.2 — The V5 application.** Implements the application protocol
  HostService already calls; reconciler normalizes provider truth into
  identified door deliveries; host-side comment classification before
  the door (durability limitation recorded: a crash between classify
  and door commit reruns the classifier — DS3 exercises it); host-owned
  reminder timers with restart-reconstructible canonical timer state
  (RunnableIndex stays a reconstructible hint).
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
