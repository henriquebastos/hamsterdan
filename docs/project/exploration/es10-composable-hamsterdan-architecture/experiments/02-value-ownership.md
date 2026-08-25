# Experiment 2 — Workflow value ownership

Session S2. Inputs: the ES-010 index, the S1 record's
`contracts/readiness_v5.py` group map and residue findings, and current
source at commit `d959f3b`. Method: a full read of the 116-name vocabulary
(6 `Literal` aliases, 2 union type aliases, 110 dataclasses in
`contracts/readiness_v5.py` plus the four live `contracts/readiness.py`
names) and the AST reference trace at
[`tools/value_trace.py`](tools/value_trace.py), which reports per module
every construction (`C`), other name reference (`R`), and string-literal
occurrence (`S`) of each vocabulary name. String occurrences matter because
token colors are class `__name__`s and `folding.py` hydrates every value
through a `vars(_colors)` registry, so consumers can know values by string
without importing them.

Module shorthand used below: loops are `net_v5/<name>.py`
(`life`, `ci`, `esc`, `review`, `mutation`, `conversation`, `dashboard`,
`reminders`, `readiness`); execution modules are `host/v5/<name>.py`
(`ingress`, `application`, `runtime`, `timers`, `gates`, `rerun.a`
(= `rerun.py`), `mutation.a` (= `mutation.py`), `review.a` (= `review.py`));
`gating` is `net_v5/gating.py`.

## Corrections found by the trace

Three facts the trace exposed that the S1 group map alone would have gotten
wrong:

1. **The workflow `Snapshot` never crosses into readiness execution.**
   `host/v5/runtime.py` imports `Snapshot` from `petrus.engine` — a name
   collision, not a consumer. Every baton, including `Snapshot`, is
   constructed and read by exactly one loop module.
2. **`ChangeResult`/`RepairResult` exist twice under one name.**
   `contracts/readiness.py:546,560` defines the retired workflow values
   (imported only by `host/publication_qualification.py`, operator support),
   while `agents/protocol.py:209` independently defines
   `ChangeResult = RepairResult = CodingResult` and exports both names from
   `agents/__init__.py`. The two shapes are unrelated. No module imports
   both, so nothing is broken today, but the shared names are a live
   misreading hazard and confirm the retired pair is not neutral vocabulary.
3. **`AdmittedConversation` uses no `WorkflowModel` mechanism.** No caller
   invokes `.dump()` or `.validated_update()` on it; the base class is
   inherited strictness only. Its producer is `github_app/webhooks.py:106`
   and its meaning is "one provider comment admitted for classification" —
   a normalized provider value, not a workflow value.

One refinement to the S1 line-range grouping: `ReminderTimer` (line 86) sits
in the observations section but is the identity value of the Net↔host timer
protocol, referenced by observations (`TimerDue`), Activity commands and
results (`ArmReminder`, `CancelReminder`, `TimerArmed`, `TimerCancelled`),
and the reminders baton (`RemState`). It is protocol vocabulary, not an
observation.

## Value ownership map

Classification vocabulary is the experiment's six categories. "Producers →
consumers" lists constructing modules → reading modules from the trace;
target paths use the index's candidate `workflow/` tree plus one proposed
`workflow/values.py` (see module-shape test).

### Normalized observations (host → workflow): 10 values

All producers are readiness-execution custody; all consumers are loops.

| Value | Producers → consumers | Target |
|---|---|---|
| `HeadSeen` | ingress → life | `workflow/observations.py` |
| `DraftSeen` | ingress → life | `workflow/observations.py` |
| `ReadySeen` | ingress → life | `workflow/observations.py` |
| `CloseSeen` | ingress → life | `workflow/observations.py` |
| `HumanSeen` | ingress → life | `workflow/observations.py` |
| `RunSeen` | ingress → life | `workflow/observations.py` |
| `CommentSeen` | application (`_classify`, from `AdmittedConversation`) → life | `workflow/observations.py` |
| `TimerDue` | timers → reminders | `workflow/observations.py` |
| `RoundWake` | application, runtime (deferred-custody wake proof) → review | `workflow/observations.py` |
| `AWake` | application, runtime → readiness | `workflow/observations.py` |

### Loop-owned memory (batons): 9 values + 5 clock states

Every baton's constructions and reads are confined to its own loop module.

| Value | Loop | Target |
|---|---|---|
| `LifeState` | life | `workflow/net/life.py` |
| `CiState` | ci | `workflow/net/ci.py` |
| `Ladder` | esc | `workflow/net/escalation.py` |
| `ReviewMemory` | review | `workflow/net/review.py` |
| `MutState` | mutation | `workflow/net/mutation.py` |
| `ConvMemory` | conversation | `workflow/net/conversation.py` |
| `DashMemory` | dashboard | `workflow/net/dashboard.py` |
| `RemState` | reminders | `workflow/net/reminders.py` |
| `Snapshot` | readiness | `workflow/net/readiness.py` |
| `NoReminderClock`, `ArmingReminderClock`, `ArmedReminderClock`, `CancellingReminderClock`, `OverdueReminderClock` | reminders (`RemState.clock` union members) | `workflow/net/reminders.py` |

### Loop-to-loop facts: 15 values

| Value | Producers → consumers | Target |
|---|---|---|
| `HeadWork` | life → ci, review | `workflow/facts.py` |
| `IntentFact` | life → conversation | `workflow/facts.py` |
| `CloseFact` | life → ci, esc, review, mutation, conversation*, dashboard, reminders, readiness | `workflow/facts.py` |
| `RunWork` | life → ci | `workflow/facts.py` |
| `ProvisionalHead` | mutation → life | `workflow/facts.py` |
| `ChecksFailure` | ci → esc | `workflow/facts.py` |
| `EscMoved` | esc → ci | `workflow/facts.py` |
| `MutationRequest` | esc, conversation → mutation | `workflow/facts.py` |
| `MutationSettled` | mutation → esc (also the body of `MutationSettledFact`) | `workflow/facts.py` |
| `RecoverFact` | conversation → esc, review, mutation, dashboard, reminders, readiness | `workflow/facts.py` |
| `DismissFact` | conversation → review | `workflow/facts.py` |
| `SnoozeFact` | conversation → reminders | `workflow/facts.py` |
| `ReminderCycleStarted` | life → reminders | `workflow/facts.py` |
| `ReminderCyclePaused` | life → reminders | `workflow/facts.py` |
| `GateFact` | conversation, esc, reminders, readiness → dashboard | `workflow/facts.py` (dashboard projection; see shape test) |

*conversation reads `CloseFact` but never closes — the loop is deliberately
permanent.

### Readiness decision facts: 19 values + 2 union aliases

All produced by sibling loops, all consumed by the readiness loop. The
`*Body`/fact pairs are deliberate: the body carries gate evidence, the
envelope stamps the incarnation the readiness fold scopes it to.

| Value | Producers → consumers | Target |
|---|---|---|
| `StateFact`, `StateFactBody` | life → readiness | `workflow/facts.py` |
| `ChecksFact`, `ChecksFactBody` | ci → readiness | `workflow/facts.py` |
| `ReviewFact`, `ReviewStatusFactBody`, `ReviewUnableFactBody`, `ReviewFactBody` (alias) | review → readiness | `workflow/facts.py` |
| `FindingsFact`, `FindingsFactBody` | review → readiness | `workflow/facts.py` |
| `HumanFact`, `HumanFactBody` | life → readiness | `workflow/facts.py` |
| `MutationPendingFact`, `MutationPendingFactBody` | mutation → readiness | `workflow/facts.py` |
| `MutationSettledFact` (body is `MutationSettled`) | mutation → readiness | `workflow/facts.py` |
| `FaultRaisedFact`, `PublicationFaultBody`, `OperationFaultBody`, `FaultRaisedFactBody` (alias) | esc, mutation, review → readiness | `workflow/facts.py` |
| `FaultClearedFact`, `FaultClearedFactBody` | esc, mutation, review → readiness | `workflow/facts.py` |

### Activity work and results: 52 values in 9 families

Each family is one gate: the loop constructs the work token; exactly one
effect adapter constructs the typed terminals; the loop folds them back.
`gating.py` and `application.py` additionally synthesize the `*Blocked`
terminals when durable-publication retry policy exhausts or custody defers —
execution code producing workflow-owned values, which the dependency rules
permit (readiness → workflow).

| Family | Work (producer) | Results (producer) | Consumer loop | Target |
|---|---|---|---|---|
| Rerun | `RerunReq` (esc) | `RerunLanded`, `RerunMoved`, `RerunFault` (rerun.a) | esc | `workflow/activities.py` |
| Agent round | `RoundOpen` (review) | `RoundDeferred`, `AgentReview`, `RoundUnable`, `RoundMoved` (review.a; runtime re-reads `RoundDeferred` to mint `RoundWake`) | review | `workflow/activities.py` |
| Findings publication | `Publishable` (review) | `ReviewLanded`, `ReviewMoved`, `ReviewBlocked`, `ReviewFault` (gates) | review | `workflow/activities.py` |
| Git mutation | `MutWork` (mutation) | `Pushed`, `MovedM`, `FaultM`, `DeclinedM` (mutation.a) | mutation | `workflow/activities.py` |
| Reply | `ReplyReq` (conversation) | `Replied`, `ReplyFault` (gates); `ReplyBlocked` (gates, gating, application) | conversation | `workflow/activities.py` |
| Dashboard upsert | `DashReq` (dashboard) | `DashLanded`, `DashDeferred`, `DashFault` (gates); `DashBlocked` (gates, gating, application) | dashboard | `workflow/activities.py` |
| Reminder nudge | `RemReq` (reminders) | `RemLanded`, `RemBlocked`, `RemFault` (gates) | reminders | `workflow/activities.py` |
| Announce | `AnnounceReq` (readiness; runtime reconstructs from `ADeferred`) | `ALanded`, `ADeferred`, `AMoved`, `AFault` (gates); `ABlocked` (gates, gating, application) | readiness | `workflow/activities.py` |
| Timer protocol | `TimerCommand`, `ArmReminder`, `CancelReminder` (reminders) | `TimerArmed`, `TimerCancelled`, `TimerCommandApplied` (timers) | reminders | `workflow/activities.py` |
| — protocol identity | `ReminderTimer` (reminders, timers) | shared by `TimerDue`, clocks, commands, results | reminders | `workflow/observations.py` (identity; see shape test) |

### Loop-internal sentinels and terminal records: 10 values

Constructed and consumed by one loop only; they exist for the loop's own
durable protocol (`AnnounceCandidate` is the revocable ready-edge sentinel,
`DashHeal` the drift poke, `EmptyReview` the nothing-to-post round) or as
the loop's close record in History.

| Value | Loop | Target |
|---|---|---|
| `AnnounceCandidate` | readiness | `workflow/net/readiness.py` |
| `DashHeal` | dashboard | `workflow/net/dashboard.py` |
| `EmptyReview` | review | `workflow/net/review.py` |
| `CiEnded` | ci | `workflow/net/ci.py` |
| `LadderEnded` | esc | `workflow/net/escalation.py` |
| `ReviewEnded` | review | `workflow/net/review.py` |
| `MutEnded` | mutation | `workflow/net/mutation.py` |
| `DashEnded` | dashboard | `workflow/net/dashboard.py` |
| `RemEnded` | reminders | `workflow/net/reminders.py` |
| `ReadyEnded` | readiness | `workflow/net/readiness.py` |

### Literal aliases: 6 values

| Alias | Consumers beyond the vocabulary | Target |
|---|---|---|
| `Phase` | claim (`CurrentClaim.phase`), values across all groups | `workflow/values.py` |
| `ReviewStatus` | review loop, `testing/readiness.py` (independent model) | `workflow/values.py` |
| `ReviewUnableCategory` | review.a (classifies adapter failures into it) | `workflow/values.py` |
| `RunConclusion` | `RunSeen`/`RunWork` fields only | `workflow/observations.py` |
| `ChecksStatus` | ci loop | `workflow/facts.py` |
| `HeadRelation` | `HeadWork` field only | `workflow/facts.py` |

### Live `contracts/readiness.py` names: 4 values

| Value | Verdict | Target |
|---|---|---|
| `WorkflowModel` | Workflow-owned mechanism (canonical dump, revalidated update) and base of all 110 values; also annotates generic values in ingress and gating — both readiness execution, allowed importers of workflow | `workflow/values.py` |
| `AdmittedConversation` | Normalized provider value; produced by `github_app/webhooks.py`, carried through `host/protocol.py` and `host/service.py` to `application._classify`. Drop the unused `WorkflowModel` base so `github_app` never imports workflow | `github_app/models.py` |
| `ChangeResult`, `RepairResult` | Retired residue. Only live consumer is `host/publication_qualification.py` (operator support). The replacement tree's qualification support owns its own record shape or consumes `agents.CodingResult`; the retired pair dies with `contracts/readiness.py` | none (delete) |

**The minimal neutral residue in `contracts` is empty.** Every value in the
current vocabulary has exactly one meaning-owner among `workflow`,
`github_app`, and (for the retired pair) deletion. Under the index rule
"crossing a seam does not make a value neutral", nothing qualifies:
`WorkflowModel` is workflow mechanism, `AdmittedConversation` is provider
meaning, and every other value is workflow language consumed by readiness
execution through the permitted readiness → workflow direction.

## Module shape test

### Are `observations`, `facts`, and `activities` deep and acyclic?

Proposed import graph, including one new `workflow/values.py` owning
`WorkflowModel` plus the cross-group aliases (`Phase`, `ReviewStatus`,
`ReviewUnableCategory`):

```text
workflow/values.py        (WorkflowModel, cross-group aliases)
workflow/observations.py  -> values          (host -> workflow seam)
workflow/facts.py         -> values          (loop -> loop language)
workflow/activities.py    -> values, observations (ReminderTimer)
workflow/net/<concern>.py -> values, observations, facts, activities
```

Acyclic by construction; the only cross-group value compositions found are
facts wrapping facts (`MutationSettledFact` → `MutationSettled`), everything
using aliases, and the timer protocol's shared `ReminderTimer` identity.
No activity value embeds a fact; no fact embeds an observation; batons ride
through gates as `mem: dict[str, Any]`, never as typed imports.

Each module has a one-sentence interface, which is the depth test:

- `observations.py` — everything the host may assert to the workflow. All
  ten producers are readiness-execution custody (ingress normalization,
  comment classification, timer maturity, deferred-custody wakes); all
  consumers are loops. Deleting it would smear the host-before-net custody
  seam into the loop files.
- `facts.py` — the workflow's internal mail. No production consumer outside
  the loops exists (the string-coupled readers below are drift, not
  interface). Deleting it into per-loop files would force every loop to
  import sibling loop modules to name its mail, recreating today's
  facade-cycle pressure.
- `activities.py` — the work the workflow requests and the only terminals
  that may answer it. Each effect adapter imports exactly its family
  (rerun.a one family, mutation.a one, review.a one, gates five publication
  families, timers the timer protocol). Deleting it would couple adapters
  to loop fold code.

### Locality rulings

- **Batons, sentinels, and terminal records stay in their loop modules**,
  not in a shared values file. The trace shows zero cross-module readers;
  moving them to a category module would advertise loop-private state as
  shared vocabulary. Consequence for S3: the token hydration registry
  (today `vars(_colors)` in `folding.py`) must aggregate token classes
  across `values`/`observations`/`facts`/`activities` and the nine loop
  modules — the topology composition point already imports all of them.
- **The timer protocol stays one readable cluster.** `ReminderTimer` is the
  identity: placing it in `observations.py` (as the identity `TimerDue`
  proves matured) keeps `activities → observations` one-directional. The
  commands, results, and `TimerDue` remain in their category modules with
  the cluster documented as one protocol. The alternative — one
  `workflow/timers.py` value module — was rejected because it would be the
  only per-concern value module and would still need importing from both
  category seams.
- **`activities.py` keeps per-concern sections rather than nine files.**
  ~52 values across nine families is one coherent adapter-facing seam; the
  index warns against one file per noun.
- **`GateFact` survives the deletion test, barely, as dashboard
  projection.** It is the only open `dict` envelope in the vocabulary. Its
  producers (conversation, esc, reminders, readiness) feed the dashboard's
  deliberately open projection log; its legacy role as the readiness
  envelope is already input-only migration support, and the index lists the
  `ready.facts` compatibility lane as deletable. Recommendation: keep the
  value, rename it to say what it is (for example `DashboardEvent`), and
  let the legacy readiness lane die with the replacement tree.

### Exit-criterion check: types that exist merely because several callers need them

Candidates examined and verdicts:

- `WorkflowModel` — mechanism with one owner (workflow); not a
  convenience type. Keep.
- `GateFact` — earns its place only as the dashboard's open projection;
  keep under that single meaning (rename).
- The nine `*FactBody` envelope pairs — deliberate promotion pattern
  (evidence body vs. incarnation-scoped envelope), one meaning each. Keep.
- `MutationSettledFact` reusing `MutationSettled` as its body — one
  settlement meaning in two routing contexts, not duplication. Keep.
- `ChangeResult`/`RepairResult` (contracts) — exist only because one
  operator-support module still imports them. Delete with the residue.
- `agents` aliases `ChangeResult = RepairResult = CodingResult` — two
  names for an existing type, created so callers can name the kind; the
  replacement tree should export only `CodingResult` (or kind-specific
  types if the protocol ever diverges).

Every value in the vocabulary now has exactly one defining owner; no
remaining type exists merely for caller convenience.

## String-coupled consumers (interface fact for S3/S7)

Token colors are class `__name__`s, and History records carry them, so the
class-name namespace is part of the workflow's durable interface even where
no import exists:

- `host/agenticus.py` knows eight result names as strings (`AgentReview`,
  `RoundDeferred`, `RoundMoved`, `RoundUnable`, `Pushed`, `MovedM`,
  `FaultM`, `DeclinedM`) to encode settlement policy — S1's mixed-owner
  finding, now with the exact value list.
- `host/testing/readiness_world.py` and `readiness_coverage.py` know
  `Pushed` and `FaultM` as strings in checkers.
- `folding.py` discovers every token class via `vars(_colors)`; the
  replacement registry must be explicit, or renames will fail only at
  hydration time.

Since ES-010 carries no compatibility obligation, the replacement tree may
rename any of these freely, but each rename touches the color namespace,
History expectations, and these string sites together.

## Exit assessment

Every one of the 116 vocabulary names plus the four live retired names has
one defining owner and one target import path in the map above. The
proposed `observations`/`facts`/`activities` decomposition is acyclic and
each module states a one-sentence interface; batons, sentinels, and
terminal records are loop-owned; the neutral residue in `contracts` is
empty. Open items handed to Phase B: the explicit token-class registry
(S3), the `GateFact` rename and legacy-lane deletion (S3), and whether
`publication_qualification`'s replacement consumes `agents.CodingResult` or
owns its own record (S6).
