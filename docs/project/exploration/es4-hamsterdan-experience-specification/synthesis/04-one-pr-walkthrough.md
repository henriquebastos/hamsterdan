# Lens 4 — One pull request's life through the unified model

Everything below is **real captured output** from
[capture_walkthrough.py](capture_walkthrough.py), which composes the
actual spike code — AX6's control machine, AX7's conversation service,
AX8's projection fold, AX9's timer, AX10's ladder, AX12's human fold,
and (in stage 4) AX3/AX4's subnets compiled and run on the **frozen
Petrus engine** via the ES-003 block algebra. The committed capture is
[walkthrough-capture.txt](walkthrough-capture.txt); re-run with:

```bash
.venv/bin/python docs/project/exploration/es4-hamsterdan-experience-specification/synthesis/capture_walkthrough.py
```

**Fidelity note:** the spikes were built independently, so AX8, AX9,
AX10, and AX12 each carry their own snapshot dataclass restricted to
their concern; the unified spec merges them into one. Each stage below
says whose code is running.

The story: a PR opens; CI fails; the ladder reruns and then repairs
it; the repair is a real CAS-gated push with an announcement comment;
control quiesces on our own push and resumes confirmed; the concerns
settle green; the dashboard publishes; readiness announces; a reminder
timer arms and fires; a human reassigns and dismisses; the PR merges;
the log replays.

---

## Stage 1 — ingress and admission (AX6)

Every observed PR enters one machine. There is no `seed` place and no
born-draft refusal: a draft is an instance, stopped.

```text
  webhook: pull_request opened, head=h1, not draft
  control state              Running(epoch=1, head='h1')
  actions                    (Resume(epoch=1, head='h1', relation='new'),)

  (variant) born as a draft — an instance, stopped, no seed place:
  control state              Quiescent(last_epoch=0, last_head='h9', expected=None)
  actions                    ()
```

The intermediate representation to notice: **control state is a
value**, not a marking. Everything the head machine will ever do is
`step(state, event) → (state, actions)`.

## Stage 2 — the generation snapshot is born (AX8)

Each generation gets one immutable `Snapshot`; decisions are pure
functions of it. Nothing is settled yet, but the dashboard projection
has already drifted from "nothing published":

```text
  snapshot                   Snapshot(epoch=1, head='h1', actions='unknown', review='unknown',
                             blocking_findings=0, findings_published=False, human_approved=False, …)
  work                       DashboardWork(operation='dashboard:1:h1:proj-8f3233', projection='proj-8f3233')
```

The operation string **is** the dedup — the same folded state can only
emit the same operation; no `dashboard_requested` flag exists.

## Stage 3 — CI fails; the escalation ladder climbs (AX10)

GitHub's fact folds into the actions concern; the phase is the
machine; GitHub's `attempt` counter is the loop variable.

```text
  GitHub reports: run-9 attempt 1 concluded failure, fingerprint fp-A
  after fold                 Actions(epoch=1, head='h1', phase='failed', run_id='run-9', attempt=1, …)
  decide →                   RerunWork(operation='actions-rerun:1:h1:run-9:1')

  the same observation is delivered AGAIN (webhook duplicate):
  after fold                 unchanged: True  (monotonic fence — no basis place)

  the rerun happened; attempt 2 fails with the SAME fingerprint:
  after fold                 Actions(…, phase='reproduced', attempt=2, fingerprint='fp-A', …)
  decide →                   RepairWork(operation='repair:1:h1:fp-A', fingerprint='fp-A')
```

No `rerun_requested`, no `rerun_attempt`, no `actions_basis` place:
`failure@attempt=1` is a first failure, `failure@attempt>1` is a
reproduction, and the duplicate is inert by comparison with the folded
`(run_id, attempt, conclusion)`.

## Stage 4 — the repair runs on the real Petrus engine (AX3 + AX4)

`RepairWork` routes into shape M — a *block*: one typed entry, named
typed exits, nothing ambient. The composed block fuses shape M's
`committed` port into a comment gate through one pure adapter:

```diagram
┌─ shape M (AX3) ────────────────────┐        ┌─ comment gate (AX3) ─┐
│ prepare → agent → CAS gate         │        │                      │
│                     ├─ committed ──┼─▶ announce ─▶ post ─ ack ─────┼─▶ acknowledged
│                     ├─ moved ──────┼───────────────────────────────┼─▶ moved
│                     └─ fault ──────┼───────────────────────────────┼─▶ fault
│ (rail) ─────────────── failed ─────┼───────────────────────────────┼─▶ failed
└────────────────────────────────────┘        └──────────────────────┘
```

The pre-runtime intermediate representations — the block's contract
and the compiled net — before anything executes:

```text
  entry port                 prepare_change_in (ChangeRequest)
  exit ports                 {'acknowledged': 'FindingPublicationResult', 'failed': 'Failure',
                              'fault': 'NonrecoverableFault', 'moved': 'BranchMoved'}
  context places             {} — nothing ambient
  transitions                ['prepare_change', 'agent_patch', 'commit_gate', 'announce_commit', 'publish_comment']
  compiled net               9 places
```

Then the execution, seeded with the exact operation AX10 emitted:

```text
  seeding ChangeRequest {operation: 'repair:1:h1:fp-A', expected_head: 'h1'}
  exit 'acknowledged'        {'comment_id': 1, 'reused': False}
  branch head now            commit-of-repair:1:h1:fp-A
  comment marker             ['finding', 'announce-commit-of-repair:1:h1:fp-A', 'commit-of-repair:1:h1:fp-A']

  (variant) someone pushed first — the CAS gate classifies itself:
  exit 'moved'               {'expected': 'h1', 'actual': 'h2-someone-pushed'}
  comments posted            []
  branch touched by us       no
```

In the raced variant the agent still ran (money spent) — but the CAS
rejected, the announcement subnet **never fired**, and the branch is
untouched. Attempt-first: no authority pre-check anywhere, and the
discard is a classified exit, not an error.

## Stage 5 — the control loop closes as data (AX6 + AX7), lineage carried (AX10)

The repair's settled exit routes the *control layer*, not the net:

```text
  actions concern            Actions(…, phase='awaiting_confirm', provisional_head='commit-of-repair:1:h1:fp-A',
                                     repair_used=True, repair_fingerprint='fp-A')
  control_move               Quiesce(expected='commit-of-repair:1:h1:fp-A')
  control state              Quiescent(last_epoch=1, last_head='h1', expected='commit-of-repair:1:h1:fp-A')

  while quiescent, a human asks for another change — and a question:
  service('change')          Decline(kind='change', reason='a just-pushed commit awaits observation; re-ask once the head updates')
  service('reply')           Answer(kind='reply')

  the webhook arrives: head is 'commit-of-repair:1:h1:fp-A' — our own push, confirmed:
  control state              Running(epoch=2, head='commit-of-repair:1:h1:fp-A')
  actions                    (Resume(epoch=2, head='commit-of-repair:1:h1:fp-A', relation='confirmed'),)
  actions after resume       Actions(epoch=2, …, phase='observing', repair_used=True, repair_fingerprint='fp-A')
```

Three production mechanisms in one screen: `provisional` is just
`Quiescent(expected=…)`; `change_in_flight` is just the Decline;
`confirmed` is a pattern match, and the resume carries exactly two
lineage fields. Then the budget fence earns its keep:

```text
  next generation: CI fails AGAIN with the same fingerprint fp-A —
  after folds                Actions(epoch=2, …, phase='reproduced', fingerprint='fp-A',
                                     repair_used=True, repair_fingerprint='fp-A')
  decide →                   ()
  needs_human                True
```

The same fingerprint is never repaired twice; the ladder ends at the
human, structurally.

## Stage 6 — the green path to readiness (AX8)

Suppose instead the repair fixed it. Concern exits fold one by one;
`decide` runs after every fold — watch `gates_ready` flip and the
dashboard-before-announce ordering enforce itself:

```text
  fold ActionsSettled           gates_ready=False  decide=(DashboardWork(…proj-7d40b7…),)
  fold ReviewSettled            gates_ready=False  decide=(DashboardWork(…proj-3f76ca…),)
  fold FindingsPublished        gates_ready=False  decide=(DashboardWork(…proj-c7d7fd…),)
  fold HumanSettled             gates_ready=True   decide=(DashboardWork(…proj-5fc984…),)

  emitted                    DashboardWork(operation='dashboard:2:commit-of-repair:1:h1:fp-A:proj-5fc984', …)
  fold DashboardAcknowledged is_ready=True  decide=(AnnounceWork(operation='readiness:2:…:proj-5fc984'),)
  fold AnnouncementAck…      decide=()  — settled; announce-once = snapshot lifetime

  commutativity across independent concerns (same four exits, reversed arrival order):
  same snapshot              True
```

Note what is *absent*: no in-flight guards (an in-flight repair is an
unfolded exit), no `readiness_requested`/`announced` reset logic (a
fresh generation gets a fresh snapshot), and the digest in the
operation identity changes as facts fold — each intermediate
`DashboardWork` is a *different* operation, and the gate's
lookup-first absorbs whichever ones actually dispatched.

## Stage 7 — time as typed ingress (AX9)

The scheduler is a provider: `ArmTimer` out, `TimerDue` in, maturity a
durable folded fact.

```text
  decide →                   (ArmTimer(operation='timer:2:…:0', due_at=260200.0),)

  the scheduler delivers TimerDue — early (its fault), then on time:
  early delivery             unchanged: True  (at < due_at — our truth, not the scheduler's)
  on-time delivery           timer_matured=True
  decide →                   (RemindWork(operation='reminder:2:…:0', sequence=0, reviewer=''),)

  the reviewer snoozes (AX7 durable note): the DECISION is off, the maturity FACT keeps:
  snoozed decide             ()
  resumed decide             (RemindWork(operation='reminder:2:…:0', …),)   ← fires immediately

  the reminder publishes; the ack re-arms sequence 1 from the instant the reviewer actually saw:
  after ack                  sequence=1 matured=False
  decide →                   (ArmTimer(operation='timer:2:…:1', due_at=519900.0),)
```

No clock is ever read by `fold` or `decide` — the instants live in the
events, so replay has zero wall-clock nondeterminism.

## Stage 8 — the human concern is a mirror plus notes (AX12)

```text
  after observation 1        reviewer='alice' seq=1
  after reassign note        reviewer='bob'
  after observation 2        reviewer='alice' approved=True  ← the reassign was CLOBBERED
```

That clobber is **production parity, flagged OPEN**: `snooze` survives
observations (the fold never touches it), `reassign` does not (the
observation writes `reviewer`). A field-ownership collision surfaced
by the spike, left for the Navigator. Dispositions are pure review
folds:

```text
  review                     Review(status='blocking', findings=(Finding(id='F1', blocking=True, disposition='new'),))
  after dismiss F1           status='clear'  → ReviewSettled('clear', 0)
```

## Stage 9 — terminal, conversations that outlive it, and replay

```text
  control state              Terminal(status='merged', last_epoch=2, last_head='commit-of-repair:1:h1:fp-A')
  service('reply')           Answer(kind='reply')     ← "why did X do Y" outlives merge
  service('change')          Decline(kind='change', reason='the pull request is merged')

  replay is a refold — the same exit events rebuild the same snapshot:
  refold == original         True
```

## What the walkthrough demonstrates, in one table

| Production mechanism | Where it went in the walkthrough |
| --- | --- |
| `seed` place, born-draft refusal | stage 1: `admit()` — Running or Quiescent from birth |
| `dashboard_requested` flag | stage 2/6: operation identity |
| `rerun_requested`, `rerun_attempt`, `actions_basis` + retire | stage 3: attempt counter + monotonic fence |
| authority pre-check fences | stage 4: the CAS gate's `moved` exit |
| `MutationState.provisional` + scattered fence checks | stage 5: `Quiescent(expected=…)` |
| `change_in_flight` flag + read arcs | stage 5: `Decline` while quiescent |
| generation relation `confirmed` | stage 5: a pattern match on the observed head |
| repair lineage places | stage 5: two fields carried by `resume()` |
| 25 projection read arcs + in-flight/dedup guards | stage 6: `fold` + `decide` |
| `Reminder` token cycle + 9 read arcs | stage 7: `ArmTimer`/`TimerDue`/sequence fence |
| `fold_human` / `fold_intent` | stage 8: mirror + notes + dispositions (verbatim rules) |
| quarantine/Hold of conversations | stages 5/9: immediate Answer/Decline in any state |

Zero ambient places, zero flags, zero read arcs — and every
production *rule* (gate predicate, cadence predicate, disposition
subtleties, announce-once) preserved verbatim where the spikes mirror
it.
