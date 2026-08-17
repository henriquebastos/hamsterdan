---
code: CV18
level: Value
status: Planned
status_reason: Hamsterdan has deterministic scenarios and crash tests, but no generated replayable host/provider fault campaign judged by an independent readiness model
updated: 2026-08-17
related:
  - ../cv17-v5-actor-loop-production-parity/index.md
  - ../../../../tests/unit/readiness/net_v5/harness.py
  - https://github.com/henriquebastos/petrus
  - https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/internals/vopr.md
---

# CV18 — Deterministic readiness simulation

## Intent

Demonstrate that Hamsterdan preserves readiness truth, current authority,
effect identity, credential isolation, and bounded recovery across generated
schedules of GitHub observations, agent outcomes, timers, provider ambiguity,
Activity delivery, host crash, and restart—and that any discovered failure can
be replayed locally from a retained, minimized scenario.

CV18 applies Deterministic Simulation Testing (DST) to Hamsterdan's application
layer. It does not ask a simulator to prove correctness or imitate GitHub in
full. It runs the real host composition and readiness topology against a small
independent domain oracle and explicit provider truth, while Petrus owns the
generic logical event scheduler, runtime fault seams, and process-reconstruction
discipline.

## Existing foundation

Hamsterdan already has strong pieces:

- CV3's deterministic scenario laboratory and live recovery portfolio;
- CV17's semantic parity oracles through the real host composition;
- a V5 fake world with authority, GitHub, agent, publication, mutation, rerun,
  dashboard, and classified-failure modes;
- injected clocks for webhook custody, runnable work, agents, and V5 timer
  custody;
- stable operation identities, lookup-first recovery, current-authority fences,
  typed Activity results, and extensive crash-window tests;
- real GitHub acceptance routes that remain complementary evidence.

These scenarios are largely hand-authored, and the fake world sometimes folds
the same rules as the host. There is no stateful generator that explores event
and failure order, no one seeded schedule spanning webhook/timer/Activity/host
reconstruction, no automated shrinking, and no independent readiness model
that continuously judges current semantic truth.

## Relationship to CV17 and Petrus CV19

CV17 and CV18 ask different questions:

- **CV17:** do production and selected V5 expose the same intended user-visible
  semantics for the controlled parity portfolio?
- **CV18:** does the supported composition remain safe and recoverable across
  generated schedules and faults?

CV18 does not compare internal traces or require two topologies forever. During
coexistence, the independent domain oracle may judge both compositions where
that reduces migration risk, but CV18 neither closes CV17 nor rules V5 as the
default.

Petrus CV19 owns the reusable deterministic event/fault harness. CV18.DS1 can
define Hamsterdan's model and correctness contract independently; execution
stories consume an accepted compatible Petrus test surface. If that surface is
not ready, Hamsterdan records the blocked seam rather than forking a scheduler
or importing private Petrus internals.

## Correctness contract

### Safety properties

At minimum, every generated scenario must continuously check:

1. one accepted GitHub delivery identity is admitted at most once and exact
   redelivery cannot duplicate semantic or provider effects;
2. no GitHub mutation, publication, rerun, or agent-mediated publication occurs
   without the current installation/repository/PR/head/base/policy/lifecycle
   authority required by that effect;
3. every logical external effect retains one stable operation identity across
   retry and restart, recovers an ambiguous accepted outcome lookup-first, and
   rejects identity/content collisions;
4. credentials, installation authority, and private provider payloads never
   enter agent requests, workspaces, canonical History, replay artifacts, or
   unredacted diagnostics;
5. a frozen Activity terminal or accepted provider effect is not re-executed
   merely because settlement, projection, acknowledgement, or the host crashes;
6. stale, draft, closed, superseded, or lifecycle-cancelled work cannot publish
   readiness or mutate the current branch;
7. dashboard, findings, review, CI, conversation, mutation, and readiness
   outcomes describe the current admitted generation rather than a convenient
   stale observation;
8. every retry, reconciliation sweep, runnable item, timer, provider call,
   payload, queue, and drive loop ends under an explicit bound and disposition.

### Liveness condition

Liveness is checked only after the scenario enters a declared fair environment:

- generated faults selected for recovery stop;
- current GitHub authority and provider reads stabilize;
- a required agent/Worker path is available or has returned a terminal result;
- logical time can mature retained timers and retries;
- durable stores remain readable; and
- no human review, clarification, approval, or new provider event remains an
  explicit product prerequisite.

Under those conditions, admitted work must converge within its bounds to a
current ready/not-ready result, a typed blocked/failure result, an explicit
human/external wait, terminal closure, or quarantine. The host must not livelock,
retry programming errors, silently abandon eligible work, or require a restart
accident to progress.

## Ownership boundary

Hamsterdan owns:

- the independent readiness/authority model and semantic checkers;
- normalized GitHub, agent, human, timer, and provider event vocabularies;
- provider truth and effect-ledger models, including definite rejection,
  accepted-but-response-lost ambiguity, delayed visibility, stale reads,
  rate-limit/unavailability, and identity collision;
- product-specific scenario profiles and semantic coverage;
- real GitHub and agent/provider contract evidence.

Petrus owns generic History, Dispatch, logical clock, event ordering, runtime
crash/reload, lifecycle, Activity, and replay machinery. GitHub types and
readiness policy never enter Petrus.

## Delivery

1. [CV18.DS1 — Readiness correctness model and simulation contract](cv18-ds1-readiness-correctness-model-and-simulation-contract.md)
   freezes the independent oracle, safety/liveness assumptions, event/fault
   vocabulary, bounds, Petrus compatibility seam, and project-level agent
   guidance.
2. [CV18.DS2 — Deterministic host and provider fault world](cv18-ds2-deterministic-host-and-provider-fault-world.md)
   runs the real host composition under Petrus-owned logical scheduling with
   controlled GitHub, agent, timer, effect, crash, and restart behavior.
3. [CV18.DS3 — Generated readiness and recovery campaigns](cv18-ds3-generated-readiness-and-recovery-campaigns.md)
   adds stateful generation, broad and targeted profiles, shrinking, independent
   semantic checks, fair-phase convergence, and regression promotion.
4. [CV18.DS4 — Campaign operations and real-boundary confidence](cv18-ds4-campaign-operations-and-real-boundary-confidence.md)
   establishes bounded PR/scheduled campaigns and preserves real GitHub,
   process, persistence, and provider evidence as distinct complementary gates.

## Done condition

CV18 is complete when a fresh checkout can generate, run, shrink, retain, and
replay bounded scenarios through the real supported host composition and prove:

- current-authority, effect-identity, credential-isolation, replay/restart, and
  bounded-progress checkers run throughout each scenario;
- generated portfolios cross lifecycle, CI, review, conversation, mutation,
  publication, timer, duplicate delivery, provider ambiguity, crash, and
  recovery boundaries;
- an intentionally seeded defect or selected mutation is detected and reduced
  to an ordinary stable regression;
- broad generation reaches semantic combinations omitted by the focused
  historical scenario portfolio;
- ordinary and scheduled campaign costs, artifacts, retention, and triage are
  documented and enforced;
- real host/process/provider routes remain green and no simulated claim is
  presented as evidence for behavior outside its model;
- project guidance lets a future Driver discover the correctness contract,
  replay before fixing, and promote durable evidence without loading this
  investigation or burdening unrelated work.

## Evidence strategy

Report semantic reach rather than seed totals alone: lifecycle phases and
generations, CI/review/conversation states, effect kinds, authority fences,
provider ambiguity classes, timer/retry states, crash cuts, restart repairs,
terminal dispositions, checker activations, fair-phase convergence, and known
ungenerated dimensions.

Every retained failure records the Hamsterdan and Petrus commits, scenario and
oracle versions, expanded event/fault schedule, relevant runtime/dependency
identity, failing property, shrink lineage, and exact replay route. Seed is
discovery metadata, not the sole durable reproduction key.

## Out of scope

- Replacing or completing CV17 parity and fresh selected-V5 acceptance.
- Making V5 the default topology.
- Full emulation of GitHub, Actions, Git, Pi, model providers, networks,
  filesystems, or CPython scheduling.
- Exactly-once external-effect claims.
- Random chaos without deterministic replay and executable properties.
- Reusing the production readiness topology or host folds as the independent
  oracle.
- Replacing real GitHub acceptance, process-kill, persistence, contract, load,
  security, or credential-isolation testing.
- Global user AGENTS.md changes.

## Grounding and cautions

TigerBeetle's VOPR demonstrates the reusable pattern: production logic runs
with nondeterministic environment seams replaced, seeded faults explore safety,
a separately fair phase checks liveness, and seed plus code identity enables
replay. [D]

TigerBeetle also documented a real defect hidden from several fuzzers because
their workload constrained reachable state. CV18 therefore requires a small
independent model and minimally structured generation beside scenario profiles
derived from known Hamsterdan journeys. [D]

Sources:

- <https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/internals/vopr.md>
- <https://tigerbeetle.com/blog/2023-07-06-simulation-testing-for-liveness/>
- <https://tigerbeetle.com/blog/2025-06-06-fuzzer-blind-spots-meet-jepsen/>
