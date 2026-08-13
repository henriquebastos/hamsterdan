# Lens 5 — The unified experience specification (candidate)

The cherry-picked result of AX0–AX12: what Hamsterdan essentially is,
expressed as a layered model in which every clause carries the
experiment that proved it. **A candidate for Navigator discussion, not
a decision** — no production work, decision records, or roadmap items
follow from this document until we decide together.

## 1. The layer model

```diagram
        GitHub webhooks      scheduler        humans (@app comments)
              │                  │                    │
              ▼                  ▼                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ INGRESS — typed facts: ObservedOpen/Closed, ActionsObserved,         │
│ HumanObserved, TimerDue, classified Intents            [AX0,AX7,AX9] │
└──────────────┬───────────────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ CONTROL — pure functions, no places, no marking                      │
│   head machine   step(state, event)          Running/Quiescent/      │
│                                              Terminal      [AX6]     │
│   conversations  service(state, kind)        Answer/Apply/Execute/   │
│                                              Decline       [AX7]     │
│   projection     fold(snapshot, exit)        one immutable value per │
│                  decide(snapshot) → work     generation  [AX8–AX10]  │
└──────────────┬───────────────────────────────────────────────────────┘
               │ work items carrying operation identity
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ SUBNETS — linear block chains, one typed entry, named typed exits,   │
│ nothing ambient; composed only through typed named ports [AX2,AX4]   │
│   shape P ×5 (publication)   shape M ×4 (agent mutation)             │
│   review · ci-observe · classify · dashboard-render      [AX1]       │
└──────────────┬───────────────────────────────────────────────────────┘
               │ every world mutation passes exactly one gate
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ TWO GATES — attempt-first, self-classifying                [AX1,AX3] │
│   COMMENT GATE  operation identity + lookup-first + supersession     │
│   GIT GATE      exact CAS; 'moved' is an outcome, not an error       │
└──────────────┬───────────────────────────────────────────────────────┘
               │ typed exits (settled facts)
               └────────────▶ fold back into CONTROL — the loop is data
```

The spine is event-sourced end to end: ingress facts and gate exits
are the log; control state and snapshots are projections — a refold,
never authoritative storage. No generator frame, builder, or live
object is ever durable state [AX8, AX9].

## 2. The control machine [AX6]

```python
Running(epoch, head)
Quiescent(last_epoch, last_head, expected=None)   # the ONE stopped state
Terminal(status, last_epoch, last_head)           # absorbing; no route back
```

- `expected` is the single refinement: `None` for draft dormancy and
  post-CAS-loss idling; the head we pushed while awaiting its webhook
  (production's entire `provisional` mechanism).
- One drain ritual on every entry into quiescence; one resume move at
  **`epoch+1`, always** — stale completions of drained work carry an
  old epoch and are inert without bookkeeping.
- Generation relations survive verbatim: `new | resumed | confirmed |
  superseded`, with `confirmed` a pattern match (`seen == expected`).
- Universal admission: every observed PR is `Running` or `Quiescent`
  from its first observation; no seed place, no born-draft special
  case.
- Mutation serialization is a consequence: while
  `Quiescent(expected=…)`, head-bound work is Declined [AX4] — no
  `change_in_flight` flag.

## 3. Concerns: fold + decide [AX8, AX9, AX10, AX12]

Each concern owns a frozen dataclass folded from typed settled exits,
and decisions are pure functions emitting identity-carrying work:

```python
snapshot = fold(snapshot, exit_value)   # per-generation; fresh at every resume
work     = decide(snapshot)             # e.g. DashboardWork("dashboard:{epoch}:{head}:{digest}")
```

Rules proven across four concerns:

- **Only settled facts fold.** In-flight work is an unfolded exit;
  no `*_in_flight` guard exists [AX8].
- **Operation identity replaces dedup flags.** Same folded state →
  same operation; gates absorb replays lookup-first [AX8].
- **Fences are data comparisons at the fold boundary:** epoch/head
  (generation), sequence (timers), monotonic `(run_id, attempt,
  conclusion)` (actions) [AX9, AX10].
- **Concern shapes may differ** — a phase ladder with budget fences
  (actions), a last-write-wins mirror plus notes (human), pure
  disposition rewrites (review). The pattern hosts all three [AX10,
  AX12].
- **Cross-concern folds commute; within-concern order is the log's
  order** — load-bearing for mirrors, by design [AX8, AX12].
- **Lineage that must survive resumes is carried explicitly** by the
  concern's `resume(prior, epoch, head)` — today exactly two fields
  (`repair_used`, `repair_fingerprint`) [AX10].

## 4. Subnets: linear blocks behind contracts [AX1, AX2, AX3]

A subnet is a function-like block: one typed entry, linear interior,
named typed exits; entered only with a work item, returning only
domain outcomes. Two fractal shapes cover 9 of the 11 activities:

```python
shape Publication[Req, Res](            # ×5: conversation, finding, dashboard,
    entry=Port("request", Req),         #     reminder, readiness
    work=[lookup_first(marker=(kind, operation, head)), post_or_update()],
    exits={"acknowledged": Port(Res), "blocked": Port(RecoverableFault),
           "fault": Port(NonrecoverableFault)},
    retry="internal, bounded, classified",
)

shape AgentMutation(                    # ×4: change, repair, update_base,
    entry=Port("request", ChangeRequest | RepairRequest),   #  resolve_conflict
    work=[agent(isolated, no_credentials), validate_patch(),
          git_gate(cas(expected_head), commit_trailers=(operation, digest))],
    exits={"committed": Port(ProvisionalHead),   # → control: Quiescent(expected)
           "moved": Port(BranchMoved),           # preconditions changed — discard
           "fault": Port(NonrecoverableFault)},
)
```

Shared exit vocabulary: `completed(T)`, `discarded`, `blocked`,
`fault` — with `retryable` strictly internal to subnets, never
crossing a boundary. Measured linearity: ≈1.1 arcs/node, fan-in
nowhere [AX2, AX4].

## 5. The two gates and the idempotency doctrine [AX1, AX3]

- **Authority pre-checks are never correctness** — redundant at the
  git gate (exact CAS), insufficient at the comment gate (a stale
  comment cannot fail; it lands "outdated"). They survive only as an
  optional per-gate *economy level* (0 none / 1 local / 2 provider
  re-read), chosen by noise economics.
- **Kind-1 idempotency** (did it before → skip): lookup-first at both
  gates — comment markers `(kind, operation, head)`, git head-commit
  trailers `(operation, payload_digest)`.
- **Kind-2 idempotency** (doing it again fails → classify): CAS loss =
  `moved` = preconditions changed → discard and wait for the webhook,
  never force. Marker collision with different payload → `fault`,
  fails closed.
- Stale comments are tolerated (supersession downstream); recovery
  from `blocked` is an explicit `recover_publication` intent entering
  a fresh occurrence with the *same* effect identity.

## 6. Ports, types, adapters, guards [AX4, AX11]

```python
Port(name, payload_type)     # names: topology · nominal type: identity
                             # shape: diagnostics · signature: adapter contract
```

- **Fusion is nominal.** Same shape is not same meaning
  (`ChangeResult`/`RepairResult` are field-identical twins). Crossing
  types requires an explicit adapter whose contract is *inferred from
  its signature* — a single source cannot lie.
- **Refusals are field-level:** a bad fusion lists exactly the
  missing/mistyped consumer fields at composition time.
- **Guard field paths are validated** against the payload type,
  nested (`comment.actor_login` ok; `risk_score` on `RepairResult`
  refused).
- **Never infer connectivity globally by type.** Topology comes from
  named ports and explicit composition only.
- Static layer today: ty (already in CI) and pyright both catch every
  structural mistake — adapter bodies, arguments, returns — with zero
  annotation burden beyond ordinary signatures.
- Petrus needs no change: the engine's string colors become a derived
  projection of the payload type.

## 7. Time [AX9]

The scheduler is a provider. `ArmTimer(operation, due_at)` is emitted
work; `TimerDue(epoch, head, sequence, at)` is typed ingress; maturity
is a durable folded fact (snooze suppresses the decision, never the
fact — matured fires the moment conditions return). Instants live in
events; `fold`/`decide` never read a clock. Petrus's `Delay`/watermark
purity is the same discipline and is preserved, not displaced.

## 8. Conversations [AX7]

Three effect grades; one pure service; nothing parked, ever:

```text
read_only     reply, status                          → Answer, in ANY state
durable_note  acknowledge dismiss defer snooze
              resume reassign                        → Apply, head-indifferent
head_bound    change update_base resolve_conflict
              recover_publication                    → Execute(epoch, head) | Decline(reason)
```

Only `Execute` carries an epoch/head stamp. The conversation agent is
read-only (Navigator scope choice); write authority lives solely in
shape M.

## 9. Effect grades [AX2, AX7]

```text
pure < spendable < committing
```

`spendable` (agent calls that only cost money) is the missing middle
the ES-003 algebra needs: `disposable(…)` admits everything below
`committing`; gates are the only `committing` leaves; classification
is spendable and thus runs in any control state.

## 10. Explicit, inferred, never inferred

```text
EXPLICIT   exit names · payload types · operation identities · adapters
           between differing payloads · lineage carried across resumes ·
           economy levels per gate · the control transition table
INFERRED   adapter contracts (from signatures) · colors (from payload
           types) · staleness (from epoch/sequence/attempt comparisons —
           never checked ambiently) · dedup (from operation identity)
NEVER      connectivity from type matching · meaning from shape ·
           readiness from a live marking · durable state from any live
           object (generator, builder, scheduler)
```

## 11. Validation and error strategy [AX4, AX11]

```text
edit time     ty / pyright: structural mistakes in adapters and payloads
compose time  deterministic: nominal fusion refusals with field-level
              diffs naming both ports; guard-path validation; soundness
              (every exit reachable, no orphan ports)
run time      frozen engine semantics unchanged; gate outcomes classify
              provider failures into domain exits (recoverable waits for
              explicit recovery; unknown terminal fails closed)
```

## 12. What production keeps, verbatim

The model displaces mechanism, not rules. Preserved and re-tested in
the spikes: the readiness gate predicate (`workflow_gates_ready`),
dashboard drift as digest inequality, announce-once-per-generation,
the reminder cadence predicate, matured-fires-on-conditions-return,
the escalation ladder (rerun once, repair once per fingerprint and
per lineage, human last), repair lineage across confirmed resumes,
generation relations, quarantine-never-reinterpret, failure
classification (recoverable vs nonrecoverable), the disposition
subtleties (dismissing the only blocking finding clears; `unable`
never upgraded; unauthorized intents inert), and both publication
species (mutable singleton dashboard vs immutable operations).

## 13. Open product choices for the Navigator

| # | Choice | Where it surfaced |
| --- | --- | --- |
| 1 | Finding/disposition lineage through quiescence: production drops findings on dormant resume; the unified model implies they survive like supersession | AX7 finding 5, AX5 #6 |
| 2 | `reminder_recipient` ownership: observation clobbers a reassign note while snooze survives — intended authority or a bug to fix by making reassign note-owned? | AX12 |
| 3 | CAS-moved repair: burn the repair budget (production parity) or refund it (doctrine reads it as "preconditions changed")? | AX10 |
| 4 | Reminder re-arm anchor: at acknowledgment (model: ≥ delay between reminders the reviewer *saw*) or at firing (production)? | AX9 |
| 5 | Universal draft admission: storage per draft PR vs the deleted special cases | AX6 |
| 6 | Economy levels per publication kind (a stale finding comment is arguably informative; a stale readiness advisory is not) | AX3 |
| 7 | Reproduction counted regardless of rerun requester (model) vs only own reruns (production) | AX10 |

## 14. Rejected alternatives

See [02-what-did-not-work.md](02-what-did-not-work.md): authority
pre-checks as correctness, conversation parking (Hold/replay/expire),
two-valued purity, color-string-only ports, structural shape fusion,
flags/basis places as loop state, one-mold concern shapes.

## 15. Risks, and what this spec is not

- **Not a production plan.** ES-004 committed to no redesign; this is
  the specification and evidence base for a future decision.
- **The merge is design work.** AX8/AX9/AX10/AX12 each carry a
  per-concern snapshot; unifying them (and wiring `decide` outputs to
  real dispatch) was never spiked as one artifact — the walkthrough
  composes them side by side, not merged.
- **The projection's home is a lean, not a law.** "Control owns the
  fold" followed AX1's structure; a dedicated projection subnet
  remains expressible if control grows fat.
- **Scale untested beyond the fragments.** Linearity (≈1.1 arcs/node)
  is measured on two fragments and one walkthrough, not on a full
  regenerated Hamsterdan.
- **Petrus stayed frozen.** Everything runs on today's engine; the
  only speculated change (payload-typed authoring ports) needs no
  engine edit, but that claim is proven only at spike scale.
