---
code: CV18.DS1
level: Delivery Story
status: Completed
status_reason: The Navigator accepted the independent expected-readiness model, debugger-like simulation contract, and review/debt assessment
updated: 2026-08-18
related:
  - index.md
  - cv18-ds2-deterministic-host-and-provider-fault-world.md
  - ../../../process/complex-system-correctness.md
  - ../cv17-v5-actor-loop-production-parity/cv17-ds4-production-parity-harness.md
---

# CV18.DS1 — Readiness correctness model and simulation contract

## What this story delivers

DS1 delivers the **test referee** and the rules of the future simulation, not
the executable simulation itself.

The referee is the `ReadinessModel`. It receives a small snapshot of external
facts—what GitHub currently says, which generation Hamsterdan admitted, CI,
review, human collaboration, mutation, external effects, and timers—and returns
the result Hamsterdan should expose: ready, still progressing, waiting for a
human or external prerequisite, terminal, or quarantined. It also names the
blocking facts and any safety violations.

This is sometimes called an *oracle* in testing literature. Here we use
**expected-readiness model** or **referee** because its role is concrete: it
calculates the expected answer independently, then a checker compares that
answer with the real host's normalized answer.

DS2 will build the debugger-like `ReadinessWorld` and `ReadinessTimeline` around
the real `HostService`. DS3 will generate and shrink schedules over that same
World. DS1 does not claim either capability already exists.

```diagram
pytest story / generated commands / replay artifact
                       │
                       ▼
          ┌──────────────────────────┐
          │ Petrus deterministic     │
          │ World: clock, order,      │
          │ faults, crash, replay     │
          └────────────┬─────────────┘
                       │ one normalized command at a time
                       ▼
          ┌──────────────────────────┐
          │ Hamsterdan profile       │
          │ real HostService +       │
          │ modeled external world   │
          └───────┬───────────┬──────┘
                  │           │
       host observation       │ external facts
                  │           ▼
                  │   ┌────────────────────┐
                  │   │ ReadinessModel     │
                  │   │ expected result    │
                  │   └─────────┬──────────┘
                  │             │
                  └──────┬──────┘
                         ▼
                 independent checker
```

## A concrete state-by-state story

The smallest useful example is an authority race:

| Step | External truth | Expected result | Why |
| --- | --- | --- | --- |
| 1 | head A is admitted; A has green CI, clear review, and approval | `ready` | every gate refers to current authority A |
| 2 | GitHub moves to head B; B's webhook is not yet admitted | `progressing` with `current_authority_admission` | A's evidence cannot authorize effects for B |
| 3 | an old readiness effect for A settles after GitHub moved to B | `quarantined` | a stale-authority effect escaped its fence |
| 4 | B is admitted, but CI and review still refer to A | `progressing` with current-CI and current-review blockers | a new generation needs fresh evidence |
| 5 | green CI and clear review for B arrive | `ready` | all current gates now agree on B |

The executable test for this story is
`test_a_new_provider_head_invalidates_old_readiness_until_fresh_evidence_arrives`.
It does not inspect a Petrus marking, Net path, production fold, or V5 state.

In DS2 the same story should read approximately like this:

```python
with ReadinessWorld() as world:
    timeline = world.timeline("github:44:31:pr:7")
    timeline.set_pull_request(head="A", lifecycle="active")
    timeline.set_ci(head="A", build="success")
    timeline.set_review(head="A", status="clear")
    timeline.approve(reviewer="reviewer-1")
    timeline.emit_webhook("pull_request")
    timeline.deliver_webhook()
    timeline.run_until("host reports ready")

    timeline.set_pull_request(head="B", lifecycle="active")
    timeline.run_until("model waits for B admission")
    timeline.emit_webhook("synchronize")
    timeline.deliver_webhook()
    timeline.run_until("host admitted B")

    assert timeline.expected_readiness().blockers == (
        "current_ci_evidence",
        "current_review_evidence",
    )
```

Every verb above lowers to one strict command through Petrus
`Timeline.command`/`World.submit`; `run_until` repeatedly executes already disclosed work and takes
named observations under a predicate-poll budget. Python control flow and
assertions are authoring conveniences. Replay stores the expanded commands and
named observations, never Python callbacks or predicates.

## Independent expected-readiness model

### Inputs

`ReadinessFacts` is strict, frozen, JSON-faithful data containing:

- the PR subject and full authority claim: installation, repository, PR, head,
  base, policy, lifecycle, strict-base currency, and mergeability;
- current provider authority beside the latest admitted generation;
- admitted delivery identities, so duplicate semantic admission is visible;
- the provider-required CI check list and the current state of every check;
- current-head review status and blocking finding dispositions;
- approval, changes-requested, conversation, and distinct-reviewer facts;
- the admitted human change grant—delivery identity, exact operation, full
  authority, intent kind/digest—beside mutation progress;
- effect obligations with stable operation, content digest, full authority,
  and acceptance/settlement status; and
- timer obligations and whether each one blocks readiness.

The model does not accept an aggregate “CI green” or “host says ready” input.
It derives readiness from the individual external facts.

### Outputs

`ReadinessExpectation` contains:

- `ready`: the expected boolean answer;
- `disposition`: `ready`, `progressing`, `human_wait`, `external_wait`,
  `terminal`, or `quarantined`;
- ordered blockers, suitable for a semantic comparison and diagnostics; and
- ordered safety violations.

Named rule groups keep policy reviewable: authority boundary and gates, CI,
review, human collaboration, outstanding work, duplicate admission, exact
change-grant binding, and external-effect safety. The conditionals implement those
named product rules; they are not a second workflow or a copy of the Net.

### Independence rule

The model and its normalizer may import neutral strict values only. They must
not import or call:

- a readiness Net, topology, marking, transition, or Net navigation path;
- `Engine`, `Coordinator`, History folds, or production projection helpers;
- `HostService` or provider fake methods that calculate desired state; or
- CV17's topology-specific parity assertions.

The checker may observe host output separately, but expected facts are derived
from authored external-world truth and admitted event identities. Raw marking
or History may appear in timeout diagnostics, never as expected truth.

### Safety checks

After every accepted atomic command, fault activation, and fresh load, DS2/DS3
must run independent checkers for:

1. one delivery identity admitted at most once;
2. current installation/repository/PR/head/base/policy/lifecycle authority on
   every agent, publication, rerun, and mutation effect;
3. an admitted human grant with the exact operation, full current authority,
   and grant identity referenced by every coding or Git mutation effect;
4. one stable operation identity and content digest across retry/restart, with
   identity/content collisions quarantined;
5. no duplicate provider acceptance when an ambiguous effect is retried;
6. no readiness publication with closed gates or outside active lifecycle;
7. no repeated execution of frozen Motus terminals or provider-accepted
   effects after settlement/projection/acknowledgement failure;
8. current-generation CI, review, findings, conversation, mutation, dashboard,
   and readiness facts; and
9. no credential, webhook secret, installation token, private payload, agent
   workspace, closure, client, or live runtime object in commands,
   observations, diagnostics, journals, or artifacts.

The current model executes checks 1–4 and 6 directly. DS2 owns detached provider
acceptance/attempt and host-observation normalizers needed for checks 5, 7–9;
DS3 must not claim those properties until their independent checkers execute.

## Fair-environment liveness

A scenario may test liveness only after explicitly beginning a **fair phase**.
For example, repeatedly making GitHub unavailable and then blaming Hamsterdan
for not becoming ready is invalid. The fair phase means:

- generated faults have stopped and all activated faults were consumed;
- GitHub authority and reads are stable;
- required Workers/agents are available or have returned a terminal result;
- logical time may mature every admitted timer/retry;
- durable stores remain readable; and
- no human approval, clarification, review, or new provider event remains a
  product prerequisite.

Petrus fairness covers all profile-disclosed queued work. The Hamsterdan profile
must therefore disclose every currently eligible bounded follow-up after
create, load, and apply; it may not hide a background loop. It must not invent
external GitHub, human, or agent responses.

Within the declared action/time/retry budgets, fair work must converge to
ready, a current not-ready/typed blocked result, terminal closure, or
quarantine. Exhaustion while the model says `human_wait` or `external_wait` is
not livelock. Exhaustion while the model says `progressing` in a genuinely fair
environment is `livelock`.

## One command interpreter and closed vocabulary

Hand-authored Timeline stories, DS3-generated schedules, and strict replay all
use the same Petrus `World` interpreter. There is no separate replay runner.

The Hamsterdan profile initially accepts the following closed command names.
Every payload is exact strict JSON; extra fields, unknown names, live objects,
and arbitrary raw provider payloads fail validation.

### Authored external-world commands

| Command | Exact payload keys | Per-occurrence outcome |
| --- | --- | --- |
| `readiness.github.pr.set` | `subject, authority` (the complete `AuthorityClaim`) | `applied`, `idempotent`, or `quarantined` for identity conflict |
| `readiness.github.ci.set` | `subject, head, required_checks, checks[{name,run,attempt,status}]` | `applied`, `idempotent`, or malformed/refused before execution |
| `readiness.github.review.set` | `subject, head, status, findings[{identity,blocking,disposition,lineage,digest}]` | `applied`, `idempotent`, or identity conflict |
| `readiness.github.human.review` | `subject, review, reviewer, head, state` | `applied`, `idempotent`, or stale/refused |
| `readiness.github.human.comment` | `subject, comment, author, fixture, digest` | `applied`, `idempotent`, or malformed/refused |
| `readiness.github.human.resolve_thread` | `subject, thread, resolver, resolved` | `applied`, `idempotent`, or unknown/refused |
| `readiness.github.webhook.emit` | `subject, delivery, event, fixture, digest` | `applied`, `idempotent`, or collision/quarantine |
| `readiness.github.webhook.deliver` | `delivery` | delivered, deliberately delayed/dropped/duplicated, or refused if unknown |
| `readiness.agent.terminal` | `subject, operation, attempt, status, fixture, digest` | `applied`, `idempotent`, stale/refused, or collision/quarantine |
| `readiness.github.effect.reveal` | `subject, operation` | `applied`, `idempotent`, or unknown/refused |

“Set, emit, deliver” are separate on purpose. A scenario can change GitHub
truth, create the corresponding webhook, then delay, omit, duplicate, or reorder
delivery without mutating host internals.

The payload schemas use normalized identities and checked-in safe fixtures.
Webhook signatures are generated inside the profile from test-only authority;
the replay artifact records neither the secret nor the raw signed body.
The expected-model normalizer derives `ChangeAuthorization` only from the
authored comment and its admitted delivery identity. It never copies an
`authorized` verdict from HostService, a topology, or a provider fake.
The model rejects a grant unless that exact delivery identity is present in its
independently normalized admitted observations.

### Profile-disclosed host work

These commands are returned as `ScheduledCommand` proposals by the profile;
scenario authors do not call them to overtake eligible work:

| Command | One atomic unit |
| --- | --- |
| `readiness.host.custody_one` | project/process one due custodied delivery |
| `readiness.host.drive_one` | execute one bounded host/Engine action |
| `readiness.host.activity_one` | claim or deliver one Motus Activity terminal |
| `readiness.host.timer_one` | mature or acknowledge one due timer/wake |
| `readiness.host.reconcile_one` | run one subject-scoped repair/reconciliation |
| `readiness.host.project_one` | rebuild one disposable projection/hint |

One profile operation is the checker atomic boundary. If production code does
several synchronous instructions inside it, the schedule cannot interleave in
the middle. Therefore any cut CV18 needs to explore must be either one of these
small public operations or a named synchronous fault cut with an explicit
disposition.

### World operations

Fault activation, observation, crash, restart, fair-phase entry, and finish are
Petrus World operations, not application commands. A crash always revokes the
current generation, rejects stale work, abruptly drops volatile resources
without settlement, then later creates a fresh generation through `load`.
Graceful `close` is teardown and never implements a crash.

## Fault and ambiguity vocabulary

Every fault is occurrence-addressed by profile, name, target, occurrence, one
of Petrus's `refuse|raise|delay|drop|duplicate` dispositions, and strict
payload. The initial Hamsterdan names are:

| Exact fault name | Closed target/cut payload | Required modeled truth |
| --- | --- | --- |
| `readiness.webhook.delivery` | target delivery; `cut=before_custody|after_custody_before_wake|redelivery` | no admission; durable pending delivery; exact duplicate identity |
| `readiness.github.read` | target `authority|ci|review|conversation|effect:<operation>`; `outcome=unavailable|rate_limited|stale`, optional safe snapshot identity | unavailable/delayed or one explicitly identified stale snapshot |
| `readiness.github.effect` | target operation; `cut=before_acceptance|after_acceptance_before_response|before_visibility|identity_collision` | definitely rejected; accepted-visible; accepted-but-response-lost; accepted-hidden; quarantine |
| `readiness.agent.operation` | target operation/attempt; `cut=before_acceptance|after_acceptance_before_terminal|terminal_delivery` | no operation; retained operation; delayed/dropped/duplicate typed terminal |
| `readiness.history.append` | target record kind; `cut=before_append|after_append_before_return` | absent record or one canonical durable record, never guessed |
| `readiness.dispatch.request` | target Activity operation; `cut=before_freeze|after_freeze` | exact absent/frozen request truth |
| `readiness.dispatch.terminal` | target Activity operation/attempt; `cut=after_provider_effect|after_freeze|before_projection` | exact terminal/provider-ledger truth at each cut |
| `readiness.timer.custody` | target timer; `cut=before_arm|after_arm|after_maturity|after_acknowledgement|drop_hint` | reconstruct from canonical History/custody or remain explicitly pending |
| `readiness.git.publish` | target operation; `cut=object_write|ref_cas|pr_projection|identity_collision` | no objects; objects/no ref; ref advanced with delayed PR projection; quarantine |
| `readiness.host.lifecycle` | target subject; `cut=after_custody|after_history|after_request|after_effect|after_terminal|after_projection|after_acknowledgement` | revoke generation and reconstruct only from durable state |

The important ambiguity is **accepted-but-response-lost**. Example: GitHub
accepts readiness operation `ready:A:i1`, then the response disappears. The
external-world ledger records one accepted effect; the host sees an uncertain
outcome. After crash/reload, lookup by the same operation must find and settle
that effect. Retrying may perform another lookup but must not create a second
provider effect.

Fault activation itself is journaled before the affected command executes.
The command's detached result records `applied`, `idempotent`,
`refused_expected`, or `quarantined`; provider truth records whether acceptance
actually occurred. Unsupported requests and undeclared fault targets are
`harness_failure`, never silent success.

## Bounds and ending dispositions

Every scenario carries Petrus's strict `Budget`: actions, queued commands,
timer advances, maximum logical instant, reloads, predicate polls, and artifact
bytes. The Hamsterdan profile configuration additionally declares positive
limits for:

- subjects and authority generations;
- provider truth changes, webhook emissions, and delivery attempts;
- checks/runs/attempts, reviews, findings, comments, and threads;
- agent operations and attempts;
- provider calls and logical external effects per kind;
- timers, retries, reconciliation passes, and host follow-ups;
- pending custody, runnable, Dispatch, and provider-ledger entries;
- normalized payload, History, observation, journal, and diagnostic bytes; and
- wall-clock test watchdog, which is diagnostic only and never simulated time.

Every authored command, generated command, scheduled follow-up, fault,
observation, poll, crash/reload, and provider request spends its matching
generic and profile bound. No command or fault family has an unbounded default.
DS2 will measure and publish the small vertical profile's numeric limits beside
its executable profile; DS3 may add larger explicit campaign profiles without
silently widening DS2.

Normal endings are `converged`, `quiescent`, `external_wait`, or `quarantined`.
Interpreter endings are `budget_exhausted` and `invariant_failure`; a
`harness_failure` is a loud test error rather than an authored finish
disposition. A wall watchdog, artifact overflow, undeclared provider
operation, unsupported command/fault, hidden eligible work, or stale-generation
use fails visibly.

## Nondeterminism and crash-cut inventory

The World owns every modeled choice that can change a result:

- stable IDs, logical time, total event order, and simultaneous-event ties;
- provider truth changes versus webhook emission and delivery order;
- duplicate, omitted, delayed, and reordered deliveries;
- GitHub read freshness and provider acceptance/visibility outcomes;
- agent terminal kind, attempt, delay, and delivery;
- timer arm/maturity/acknowledgement and disposable wake loss;
- Motus request, provider effect, terminal, settlement, and projection cuts;
- Git object/ref/PR-projection cuts;
- host crash position and fresh runtime generation; and
- generated command choice in DS3.

Direct wall time, random UUIDs, unordered set/dict iteration used for choices,
background workers, ambient task scheduling, network timing, and process reuse
must not decide a simulation result. Cryptographic signing bytes may vary only
inside a boundary where the normalized observation is fixed and replay does not
compare bytes.

Crash/reload retains only strict reconstructable profile configuration, the
Petrus journal, modeled external-system truth, and production durable custody.
It drops the complete `HostService`/Engine/Worker/client runtime graph. No stale
generation handle reaches Timeline, predicates, checkers, observations, or
artifacts.

## Strict replay contract

Hamsterdan pins Petrus commit `44cac5ff48ac371ebae56323941983f30db13c0d`
and consumes only `petrus.testing.dst`:

- API compatibility: `petrus.testing.dst/v4`;
- artifact format: `petrus-dst-world`, version 4;
- replay-result format: version 2; and
- public values/protocols include `Command`, `Fault`, `BudgetV4`,
  `ResourceUsage`, `ResourceScenarioProfile`, `ScheduledCommand`, `ApplyResult`,
  `GenerationStart`, `ObservationRequest`, `Observation`, `CheckResult`,
  `Checker`, `World`, `Timeline`, `ScenarioArtifact`, `ReplayResult`, and
  `ScenarioRegistry`.

Petrus's separately versioned `petrus.testing.dst.runner/v1` owns outer-process
wall-clock containment. A killed call retains its acknowledged prefix and
unfinished attempt but deliberately produces no deterministic artifact.

Hamsterdan neither constructs a private Petrus `Coordinator` nor retains
mutable Petrus Instance/History/Dispatch handles. The generic World sees one
opaque profile generation. The profile may compose the real `HostService` over
multiple public resources.

An artifact records:

```text
format/version/API
scenario identity
exact profile name/version/digest
ordered checker name/version/digests
all generic bounds
dense expanded operations:
  command source + instant + generation + total-order sequence
  exact strict command and detached result/follow-ups
  activated faults and named observations
  crash/restart/fair/finish operations
expected checker entries + ending disposition + journal digest
```

Profile API compatibility, profile semantics, checker semantics, and artifact
format are separately versioned and fail closed on mismatch. A discovery seed
is optional metadata; the expanded schedule plus code/profile/checker identities
is authoritative. Artifacts contain no closures, predicates, clients, runtime
handles, credentials, raw private payloads, or mutable aliases.

Petrus retains strict v1/v2 artifact decode and replay. V2/v3 artifacts retain
the exact terminal attempted operation for World-owned `budget_exhausted` and
checker `invariant_failure`; v3 adds seeded provenance. DS3 may therefore
promote and exactly replay those failures through the same interpreter.
Profile/runtime implementation exceptions remain harness failures rather than
modeled counterexamples; Hamsterdan must not invent a second failure runner.

## Hamsterdan profile and real-host seam for DS2

`ReadinessScenarioProfile` will implement Petrus `ScenarioProfile` with one
opaque generation. Its only lifecycle is:

| Profile door | Hamsterdan responsibility |
| --- | --- |
| `create` | construct modeled provider truth, deterministic adapters, and one fresh real HostService generation; disclose initial eligible work |
| `load` | reconstruct a fresh HostService generation from durable custody/History and retained external truth; disclose repair work |
| `apply` | validate and execute one closed command; return detached result and all newly eligible follow-ups |
| `observe` | return strict normalized provider/model/host/History/Motus/custody views; never a live object |
| `drop` | after World revocation, kill/release volatile resources without settlement, observation, or new work |
| `close` | graceful final test cleanup only |

The existing HostService remains the real application under test. DS2 needs the
smallest test-facing composition seam necessary to make it deterministic:

1. construction accepts the World clock and boundary-faithful GitHub/agent/Git
   adapters without selecting a different readiness topology;
2. signed ingress still crosses the real HTTP normalization and durable custody
   route;
3. host processing exposes bounded one-item doors for custody, due work,
   Activity execution/terminal delivery, reconciliation, timer wakes, and
   projection repair, rather than a private background worker or unbounded
   drain;
4. detached observation reads public host health plus normalized durable
   custody, canonical History/records, Motus requests/terminals, and published
   provider truth; and
5. the profile can abruptly terminate the generation without calling graceful
   settlement, then reconstruct from the same durable root.

Today `HostService` already exposes the real composition and synchronous
`process`, `pump`, `project_pending`, `run_due`, `sweep`, `health`, and `close`
doors. DS2 must narrow their aggregate work where interleaving requires one
item and inject one shared simulation clock where production currently reads
wall time. This is a public Hamsterdan test seam, not permission to expose or
retain Petrus internals. Process isolation is the preferred proof that no
generation object survived a crash.

## Semantic coverage contract

One elaborate scenario will prove that the plumbing connects across signed
ingress, custody, History, Motus, provider acceptance, crash, reload, and
lookup-first settlement. It is not coverage of mutually exclusive states.

Campaign reports must cross and count these dimensions rather than report only
seeds or lines:

- active/draft/resumed/merged/closed lifecycle and authority generations;
- head/base/policy movement, mergeability, and stale authority;
- CI missing/queued/running/success/failure/canceled/unavailable, attempts, and
  automatic versus human-authorized recovery;
- review pending/clear/blocking/unable, finding lineage/disposition, approvals,
  changes requested, conversation, and distinct reviewer;
- conversation, dashboard, findings, rerun, readiness, agent, coding, and Git
  mutation effects;
- definite rejection, accepted-visible, accepted-response-lost, delayed
  visibility, stale reads, rate limits/unavailability, and identity collision;
- timer, retry, runnable, terminal, acknowledgement, and projection states;
- duplicate/omitted/delayed/reordered delivery;
- every named crash cut and repeated fresh reload; and
- ready/progressing/human wait/external wait/terminal/quarantine, bound
  exhaustion, checker activation, and fair-phase convergence.

Broad minimally constrained generation and targeted profiles are both
required. Shrinking owns exploration in DS3. A quiet focused profile is not
evidence that an unreachable combination is correct.

## Verified baseline and boundaries

Repository reality at the start of DS1:

- `origin/main` includes accepted CV17 commit `d8ab562`;
- existing host and parity scenarios are hand-authored;
- no one scenario spans signed ingress/History/Motus/timers/duplicates/provider
  ambiguity/crash/restart together;
- the closest journey is agent repair: it crosses provider truth, review,
  findings, rerun, coding, real Git publication, repaired-head ingress, and
  readiness, but deliberately has no timer, duplicate/redelivery,
  accepted-response-lost outcome, or crash/reconstruction schedule; and
- focused CV17 recovery tests cover those omitted cuts separately. CV18 does
  not reopen or replace that accepted evidence.

At DS1 acceptance, the former production topology remained the default and DS1
did not select V5. The Navigator's subsequent topology ruling supersedes that
operational constraint: non-sharded V5 is now the sole production composition,
while sharded V5 remains excluded. Instant Offer is the authoring precedent for World, Timeline,
business verbs, and run-until diagnostics—not the completeness bar. CV18 adds
independent expected truth, deterministic IDs/order, true generation drop and
reload, strict expanded replay, fair liveness, generation, shrinking, and
campaign operations.

## Validation route

The semantic acceptance surface is:

1. read the five-step authority story above;
2. inspect `src/hamsterdan/testing/readiness.py` as the independent referee;
3. inspect `tests/unit/testing/test_readiness_model.py` for its domain stories;
4. inspect the V5 World integration stories and CV17's historical
   `test_clean_green_user_journey` parity evidence;
5. confirm that the World/Timeline pseudocode matches the desired debugger-like
   authoring experience; and
6. confirm that DS2—not this story—owns implementation of that World/Timeline
   and the first vertical crash/replay scenario.

Pass means the model's domain vocabulary and outcomes are understandable, its
independence is credible, and the DS2 contract preserves the original DST
intent. Fail means the referee embeds workflow structure, the command/fault
surface cannot express an intended scenario, or the proposed Timeline would
still require low-level Petrus/HostService knowledge from scenario authors.

## Out of scope

- Implementing `ReadinessWorld`, `ReadinessTimeline`, the provider adapters, or
  generated campaigns.
- Modifying Petrus, forking its scheduler, importing private Petrus runtime
  internals, or consuming Petrus code outside `petrus.testing.dst`.
- Replacing CV17's parity checks or live acceptance.
- The later choice of V5 as production default was outside DS1 and is now owned
  by its superseding decision; sharded V5 remains out of scope.
- Claiming exhaustive coverage, exactly-once external effects, or correctness
  beyond executed evidence.
