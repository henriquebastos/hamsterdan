# Source boundaries — evidence inventory

Starting material for AX0, gathered read-only on 2026-08-12. Everything
here is boundary evidence; no topology internals were consulted. Treat
each item as a claim with a code reference, to be verified when used.

## 1. Inputs

### HTTP door

Authenticated `POST /github/webhooks`; deliveries are durably stored
before processing (`host/api.py:38-50`, `github_app/webhooks.py:161-203`).
Dedupe by GitHub delivery UUID as inbox primary key
(`github_app/webhooks.py:149-155`, `187-195`).

### Webhook event types (11)

Declared in `github_app/webhooks.py:26-40`.

| Event | Fate |
| --- | --- |
| `installation` | Routing-registry mutation; terminal, no workflow token |
| `installation_repositories` | Routing-registry mutation; terminal |
| `ping` | Acknowledged as non-workflow (`host/service.py:420-424`) |
| `pull_request` | Sanitized `Observation` → PR reconciliation |
| `issues` | Same |
| `pull_request_review` | Same |
| `pull_request_review_comment` | Same |
| `workflow_run` | Same |
| `check_run` | Same |
| `check_suite` | Same |
| `issue_comment` | Only new, collaborator-authored `@app …` PR comments admitted as `AdmittedConversation` (`github_app/webhooks.py:75-112`); others terminally ignored |

Reconciliation (`host/application.py`) turns raw provider state into
boundary contracts: `Admission`/authority (`:145-167`), `HumanObservation`
(`:209-263`), `ConversationObservation` (`:269-287`),
`ActionsObservation` (`:289-310`).

### Human intent vocabulary (12 kinds)

`Intent.kind` Literal (`contracts/readiness.py:417-439`); argument and
explicit/mutation requirements at `host/activities.py:645-668`.

```text
reply · status · acknowledge · dismiss · defer · snooze · resume
reassign · change · update_base · resolve_conflict · recover_publication
```

### Other doors

- Startup registration reconciliation (`host/api.py:15-22`) and CLI
  `validate` (`host/__main__.py:238-240`).
- Periodic sweep reconciles every durable PR instance — repairs missed
  events/restarts (`host/service.py:376-406`, `494-510`).
- Durable timers/wake hints, including reminder maturation
  (`host/runnable.py:94-142`; `host/service.py:620-637`).
- CLI `requeue` returns a delivery to the inbox (`host/__main__.py:246-249`).
- Activity terminal callbacks wake the owning instance — internal
  dispatch, not an external door (`host/service.py:212-228`).
- No external agent-callback HTTP endpoint; agent calls are synchronous
  activity effects.

## 2. Outputs — the 11 activities

All registered at `host/activities.py:812-827`. No registered activity is
pure computation: each reads/writes GitHub or invokes an agent.

### Agent effects

| Activity | Signature | World effect |
| --- | --- | --- |
| `review` | `ReviewRequest → ReviewResult` | Review agent over repo/diff, Actions, comments, prior findings, lineage |
| `conversation` | `ConversationClassificationRequest → IntentBatch` | Conversation agent selects exactly one intent |
| `repair` | `RepairRequest → RepairResult` | Coding agent for failed CI; may publish a commit |
| `change` | `ChangeRequest → ChangeResult` | Coding agent for an authorized human mutation; may publish a commit |

### GitHub effects and observations

| Activity | Signature | World effect |
| --- | --- | --- |
| `actions_discovery` | `ActionsDiscoveryRequest → ActionsObservation` | Read exact-head workflow run + required checks |
| `actions_rerun` | `ActionsRerunRequest → ActionsObservation` | Post rerun-broker marker for same-head whole-run rerun |
| `conversation_publish` | `…Request → …Result` | Post immutable reply comment |
| `finding_publish` | `…Request → …Result` | Publish review findings, inline where possible |
| `dashboard_publish` | `…Request → …Result` | Create/update singleton dashboard comment |
| `reminder_publish` | `…Request → …Result` | Post reviewer/author reminder |
| `readiness_publish` | `ReadinessCommand → ReadinessPublicationResult` | Post immutable "gates ready" advisory; never merges |

Shared Git commit effect for `repair`/`change`: validate agent patch,
commit with operation/digest trailers, CAS-advance the PR branch
(`host/git_publish.py:70-152`).

## 3. Invariants at the boundary

### Authority and fencing

`Authority` (`contracts/readiness.py:88-100`) carries identity, `epoch`,
`head`, `base_head`, `strict_base`, `base_current`, `policy_digest`,
required checks/approvals, conversation policy. The decisive fence tuple
is `(epoch, head, base_head, policy_digest)` (`host/runtime.py:234-248`).
The fence also requires: non-provisional state with an active durable
activity request (`:249-252`); PR open, non-draft, exact head/base
(`:253-255`); unchanged policy digest (`:256-257`); a second PR read
proving authority did not move during fencing (`:258-267`).

### Identity

One engine per PR: instance ID is deterministically
`github:{installation_id}:{repository_id}:pr:{pull_request_number}`
(`host/service.py:525-529`); one application + lock per tuple
(`:303-306`, `371-374`); Engine loads with that identity and independent
history (`host/runtime.py:324-365`).

### Idempotency doctrine

- Operation identity: publication requests carry a non-empty immutable
  `operation` — both dispatch correlation and idempotency key
  (`host/runtime.py:103-110`).
- Active-request fencing: operation/base/policy recovered from unresolved
  durable `ActivityRequested` records; settled or malformed requests
  cannot authorize an effect (`host/runtime.py:277-305`).
- Comment lookup-first: stable HTML markers (kind, operation, head);
  matching payloads returned, collisions rejected, uncertain POSTs looked
  up before retry (`github_app/effects.py:58-61`, `89-146`).
- Dashboard: lookup before create/update and after uncertain responses
  (`github_app/effects.py:148-208`).
- Git lookup-first: head-commit trailers identify operation + payload
  digest; mismatched reuse or parents fail; fresh authority reread
  immediately before and after ref advance (`host/git_publish.py:134-152`,
  `180-198`).
- Agent route fencing: each operation persistently claimed to one agent
  composition (`host/agenticus.py:245-265`).

Navigator doctrine on the two idempotency kinds (to be exercised in AX3):

```text
Kind 1: "already did this" is detectable from the input → skip.
Kind 2: doing it again FAILS, and the failure must be classified:
        not an error — either "already done" or "preconditions changed".
        These are different outcomes, and neither is a retryable failure.
```

## 4. Domain contract types

All strict, frozen, JSON-faithful (`contracts/readiness.py:13-29`).

| Group | Types |
| --- | --- |
| Admission & generations | `Seed`, `Admission`, `GenerationStart`, `GenerationStop`, `GenerationCommit` |
| Authority | `Authority` |
| Posture | `ReadinessSnapshot`; components `ActionsState`, `ReviewState`, `HumanState`, `MutationState` |
| Publication custody | `FindingPublicationState`, `ConversationPublicationState`, `DashboardPublicationState`, `ReadinessPublicationState` |
| Lifecycle | `Dormant`, `Terminal` |
| Observations | `ActionsObservation`, `HumanObservation`, `AdmittedConversation`, `ConversationObservation` |
| Intents | `Intent`, `IntentBatch` |
| Activity messages | `ReviewRequest/Result`, `ActionsDiscoveryRequest`, `ActionsRerunRequest`, `ConversationClassificationRequest`, `ConversationPublicationRequest`, `FindingPublicationRequest`, `ChangeRequest/Result`, `RepairRequest/Result`, `DashboardPublicationRequest`, `ReminderPublicationRequest`, `ReadinessCommand`, publication results |
| Timers | `Reminder` |

## 5. Scale facts

| Metric | Count |
| --- | --- |
| Activities | 11 |
| Webhook event types | 11 |
| Human intent kinds | 12 |
| `topology.py` | 1,684 lines (not read; deferred to AX5) |
