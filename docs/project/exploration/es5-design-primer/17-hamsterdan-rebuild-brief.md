# 17 — The Hamsterdan rebuild brief

**Rely on this: the boundary owns safety and is fully specified; the
net owns decisions and is yours to design — this chapter is the
contract, the design space, and the simplifications already proven,
so you can build your own Hamsterdan net with chapter 15's method.**

Everything here is distilled from ES-004, which derived Hamsterdan's
behavior from the *boundary* (webhooks, docs, host code, decision
records) with the production topology deliberately unread. Source of
truth with per-clause code citations:
[experience-map.md](../es4-hamsterdan-experience-specification/experience-map.md).
The layered candidate model:
[05-unified-experience-spec.md](../es4-hamsterdan-experience-specification/synthesis/05-unified-experience-spec.md).

## What Hamsterdan is

A GitHub-native PR-readiness application. It watches pull requests,
reviews them with a credential-less agent, observes CI, converses
through `@app` comments, repairs failing checks within a bounded
budget, and publishes advisories (dashboard, findings, reminders,
readiness). It **never merges**. One PR = one case = one engine
instance.

## The contract — behavior your net must honor

These are CONFIRMED at the boundary (evidence lines in the experience
map). Written as compact Given/When/Then, ready for the chapter 15
mapping.

### Lifecycle

```gherkin
Given no durable instance for PR #N
When any admitted PR-addressable webhook arrives
Then live PR state is read (the webhook action is never trusted)
And an open non-draft PR starts generation 1 (relation "new")

Given an active instance at head H1
When the observed head becomes H2
Then a superseding generation starts: drain work, epoch+1, scope reset
And in-flight H1 effects cannot pass the fence

Given an active instance
When the base branch moves (head unchanged)
Then NO new generation starts and the epoch does NOT advance
But base_head still participates in every effect fence

Given an active instance          | Given a dormant instance
When the PR becomes a draft       | When it is open non-draft again
Then stop, retaining epoch/head   | Then resume with epoch = last+1

Given an active instance
When the PR is closed or merged
Then the case is terminal: no NEW provider effect can pass the fence
And late terminals are still collected or quarantined
And there is no reactivation route
```

### Authority and discard

```gherkin
Given work computed under (epoch, head, base_head, policy, operation)
When authority moved before its effect lands
Then the work is DISCARDED — never forced, inputs never restored
And the next webhook starts fresh work

Given ingress provably targeting a closed generation → acknowledge, drop
Given ingress whose generation is UNCERTAIN → quarantine, never reinterpret

Given a change/repair commit succeeds, returning a provisional head
When further head-bound effects are considered
Then everything is fenced until admission verifies that head
And the confirmed generation preserves repair lineage
```

### Review, CI, and repair

```gherkin
Given a review agent invocation
Then no GitHub credential or repository authority reaches the agent
And agent output alone never authorizes an effect

Given workflow_run / check_* webhooks
Then payload status is not trusted: the newest exact-head run is
     selected and required jobs are assessed

Given a repair attempt producing a patch
Then host-validated patch, commit trailers (operation, payload digest),
     server-side CAS after a fresh PR read
And a moved branch rejects the attempt — discard, not force

Given repeated failure (the escalation ladder, in order)
Then rerun once → repair once per fingerprint per lineage → human
```

### Conversation

```gherkin
Given a PR comment
Then admission is fail-closed: newly created, exact-leading @app
     mention, human OWNER/MEMBER/COLLABORATOR author

Given an admitted comment
Then exactly ONE of 12 intent kinds — zero or several yields a safe
     "no workflow change" reply

Given a mutation intent (change, update_base, resolve_conflict — only 3)
Then explicit+authorized executes immediately under the full fence
And ambiguous → clarification reply; unauthorized → inert

Given any intent reply → immutable, lookup-first, keyed by
     (kind, operation, head); payload collision fails closed
```

### Publication, timers, readiness

```gherkin
Given any durable publication that fails
Then bounded classified retry (3) inside ONE immutable operation;
     recoverable failures stay blocked; unknown terminals fail closed

Given a blocked publication
When an authorized recover_publication intent names the exact target
Then ONE fresh occurrence reuses the same effect identity — nothing
     reopens automatically

Given a reminder deferred until T
Then maturity is a durable folded fact — snooze suppresses the
     decision, never the fact; matured fires when conditions return

Given all readiness gates satisfied (green/flaky checks, findings
     clear, human approval, conversations resolved, base current,
     mergeable, no pending mutations, no blocking faults)
Then the readiness advisory is published — and nothing is merged
```

Also preserved verbatim (spec §12): announce-once-per-generation,
dashboard drift as digest inequality, dismissing the only blocking
finding clears, `unable` never upgraded, both publication species
(mutable singleton dashboard vs immutable operations).

## Your design space — what the boundary does NOT decide

These are NET-DECIDED: the mechanism exists, the policy is the net's.
This is exactly where your design gets to differ from production:

1. Review trigger policy — every head? gated? on demand?
2. Semantics of the 9 non-mutation intent kinds.
3. When the readiness advisory is emitted.
4. Rerun vs repair vs wait vs ask, on failed checks.
5. When the dashboard republishes.
6. Restart policy after a discard (new head arrives).
7. Who schedules reminder timers (defer/snooze → ArmTimer).

Plus seven open *product* choices (spec §13) — e.g. do findings
survive dormancy, does a CAS-moved repair burn its budget — that you
rule as Navigator while designing.

## The simplifications already proven

Production's control places, flags, and read arcs largely dissolve
into three mechanisms. Each row ran on the frozen engine in ES-004:

| Production mechanism | Replacement | Proof |
|---|---|---|
| Dormant place, provisional flag, inline drain, seed place, born-draft case | one 3-state machine: `Running(epoch, head)` · `Quiescent(last_epoch, last_head, expected=None)` · `Terminal(...)`, one pure `step(state, event)` | AX6 |
| Staleness *checked* via read arcs (42 of 94) | **epoch+1 on every resume** — stale completions carry an old epoch and are inert; staleness unexpressible | AX6 |
| `change_in_flight` flag | `Quiescent(expected=pushed_head)` declines head-bound work until admission confirms | AX6/AX4 |
| `*_in_flight` guards, dedup flags, basis places | fold **only settled facts** into a per-generation snapshot; `decide(snapshot)` emits identity-carrying work; gates absorb replays lookup-first | AX8 |
| Fences as topology (places + read arcs) | data comparisons at the fold boundary: epoch/head, timer sequence, monotonic `(run_id, attempt, conclusion)` | AX9/AX10 |
| The repair cycle in the net | the escalation ladder with **provider-owned loop state** — GitHub's run/attempt data is the loop variable; "iteration" is the next generation arriving | AX10 |
| Authority pre-checks before effects | attempt-first gates: `committed / moved / fault` — `moved` is an outcome meaning "preconditions changed, discard", never an error | AX1/AX3 |
| Conversation coupled to lifecycle | effect grades `pure < spendable < committing`: read-only answers in ANY state; notes head-indifferent; only `Execute` carries epoch/head | AX7 |

## The target shape

```diagram
 GitHub webhooks          scheduler            humans (@app)
      ▼                       ▼                     ▼
┌────────────────────────────────────────────────────────────┐
│ INGRESS   typed facts with identity: ObservedOpen/Closed,  │
│           ActionsObserved, HumanObserved, TimerDue, Intent │
└──────────────────────────┬─────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│ CONTROL   pure functions, no places:                       │
│           step(state, event)   → Running/Quiescent/Terminal│
│           fold(snapshot, exit) → per-concern snapshot      │
│           decide(snapshot)     → work items w/ identity    │
└──────────────────────────┬─────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│ SUBNETS   linear blocks, one typed entry, named typed exits│
│           shape P ×5 (publication: lookup-first → post)    │
│           shape M ×4 (agent → validate → git CAS gate)     │
│           + review · ci-observe · classify · render        │
└──────────────────────────┬─────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│ TWO GATES  COMMENT: identity + lookup-first + supersession │
│            GIT: exact CAS; "moved" is an outcome           │
└──────────────────────────┬─────────────────────────────────┘
                           └──▶ typed settled exits fold back
```

Shared exit vocabulary: `completed(T) | discarded | blocked | fault`
— `retryable` never crosses a subnet boundary. Concerns (one snapshot
each): actions (phase ladder + budgets), review (disposition
rewrites), human (last-write-wins mirror + notes), conversation,
dashboard, reminder, readiness. Measured linearity of the proven
fragments: ≈1.1 arcs/node, fan-in nowhere.

## How to build yours

1. Write the stories above in your own words; add your rulings on the
   NET-DECIDED list — those rulings *are* your design.
2. Apply chapter 15's checklist: colors first, ingress identities,
   gates, one exit per Then-clause (including `discarded`), routing,
   parallelism, repetition, the rail, lifecycle, coordination, purity
   audit.
3. Keep the doctrine: only settled facts fold; every world change
   passes one gate with an operation identity; staleness by epoch
   comparison, never by checking; the agent never holds credentials.
4. Count `arcs/(P+T)` — near 1 means state isn't spread.
5. Compare against the former production
   `src/hamsterdan/readiness/net/topology.py` in pre-consolidation Git history
   and ES-004's divergence sweep
   ([ax5](../es4-hamsterdan-experience-specification/experiments/ax5-divergence-sweep.md)),
   which classified all 94 production read arcs — your net should need
   very few of them.

## Where the depth lives

| Question | Read |
|---|---|
| the full behavioral map with code citations | [experience-map.md](../es4-hamsterdan-experience-specification/experience-map.md) |
| the layered candidate model, clause by clause | [05-unified-experience-spec.md](../es4-hamsterdan-experience-specification/synthesis/05-unified-experience-spec.md) |
| one PR traced through the whole experience | [04-one-pr-walkthrough.md](../es4-hamsterdan-experience-specification/synthesis/04-one-pr-walkthrough.md) |
| what worked, with the proving code | [03-what-worked.md](../es4-hamsterdan-experience-specification/synthesis/03-what-worked.md) |
| rejected alternatives (don't retry these) | [02-what-did-not-work.md](../es4-hamsterdan-experience-specification/synthesis/02-what-did-not-work.md) |
| subnet boundary candidates | [subnet-candidates.md](../es4-hamsterdan-experience-specification/subnet-candidates.md) |
