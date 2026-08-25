---
status: Thickening
opened: 2026-08-24
navigator: Henrique
---

# ES-009 — Human ownership of the Hamsterdan codebase

## Inquiry

How can the Navigator gain enough working knowledge of Hamsterdan's current V5
system to explain its behavior, judge its organization, and direct improvements
without reading the repository file by file or accepting another AI-authored
summary on trust?

The exploration treats learning, review, and improvement as one evidence loop:
trace a real behavior through its implementation and tests, state its invariants,
find where understanding or change loses locality, and only then form bounded
improvement candidates.

## Boundary

- Start with the current V5 production path and its tests. Follow historical
  explorations or secondary tooling only when they explain a current choice.
- Learn through vertical journeys rather than package-by-package narration. The
  first journey is one clean-green reconciliation from ingress through readiness
  publication.
- Build maps and explanations that the Navigator can challenge and teach back;
  an agent-generated inventory alone does not satisfy the inquiry.
- Review module depth, interfaces, seams, adapters, locality, leverage,
  correctness, testing, naming, and repository organization from observed code.
- Treat large files as navigation signals, not automatic refactoring targets.
  Apply the deletion test before calling a module shallow.
- Keep findings distinct from conclusions. Production changes begin only after
  the Driver presents evidence-backed candidates and the Navigator selects one.
- Keep CV19 status and the Navigator's independent VM/configuration work outside
  this exploration. The Navigator owns coordination against that lateral work.
- Do not launch the host, exercise authenticated provider operations, or inspect
  credential-bearing local state as part of codebase learning.

## First experiment — trusted baseline and vertical map

1. Run the repository's existing full validation gate without changing
   dependencies or lock state.
2. Map current source modules, import direction, executable architecture rules,
   and test layers.
3. Trace the clean-green journey through host custody, V5 application/runtime,
   readiness topology, typed Activities, and publication.
4. Record invariants, questions, and points where the trace requires excessive
   cross-module knowledge.
5. Present the map as a guided reading route and ask the Navigator to explain the
   journey back before forming architecture candidates.

## Second experiment — automatic agent repair

1. Trace repeated exact-head CI failure through the rerun-once escalation ladder.
2. Follow the typed repair through mutation serialization, credential-free agent
   execution, host-derived patch admission, Git object publication, and exact ref
   compare-and-swap.
3. Distinguish a landed branch mutation from later admission of the repaired head
   as a new workflow generation.
4. Inspect lookup-first recovery, test composition, and navigation cost without
   launching a host or invoking a real provider.
5. Present the route for Navigator teach-back before forming improvement
   candidates.

## Third experiment — ambiguous Git publication recovery

1. Trace an accepted exact ref update whose response and immediate proof are
   unavailable.
2. Distinguish automatic redispatch of an unterminated Activity occurrence from
   explicit human recovery after durable `FaultM`.
3. Admit the provider head before recovery and inspect how global fault state,
   stale per-incarnation facts, and the `from_head` fence converge.
4. Exercise the fixed World recovery, sharp lifecycle race, and generated crash
   schedules without invoking a real provider.
5. Present the route for Navigator teach-back before candidate review.

## Fourth experiment — reminder-timer recovery

1. Trace a running PR which lacks qualifying human readiness from reminder
   eligibility through one durable timer arm.
2. Distinguish canonical timer commands and History facts from the reconstructible
   timer database and disposable runnable wake index.
3. Follow restart before and after timer maturity, including how the host restores
   posture and delivers one timer wake without treating wall-clock time as
   workflow truth.
4. Trace the stable reminder operation through lookup-first publication recovery,
   current recipients, moved authority, and a lost provider response.
5. Exercise focused timer reconstruction and generated reminder schedules without
   launching the host or invoking a real provider, then present the route for
   Navigator teach-back.

Concrete scenario: an active PR has no requested reviewer when its lifecycle-driven
reminder becomes eligible. The host arms the reminder, restarts before the
deadline, reconstructs timer custody from intact canonical History, reaches
maturity, and proves that exactly one reminder operation lands even if the
provider response is lost.

## Current evidence

- [Baseline](baseline.md) records repository shape, test-surface taxonomy, the
  partially completed full gate, the macOS setup-test portability failure, and
  initial navigation signals.
- [Clean-green reconciliation journey](clean-green-journey.md) traces the first
  vertical behavior from durable webhook custody through typed readiness
  publication and records the Navigator teach-back.
- [Missing canonical History finding](history-loss-finding.md) distinguishes
  process reconstruction from destructive History loss and records the current
  trigger-dependent fresh-start behavior.
- [Agent-repair journey](agent-repair-journey.md) traces automatic repair from
  failed rerun evidence through one exact branch update, repaired-head admission,
  resolved review lineage, and readiness. It also distinguishes this typed
  `repair` rung from a human-requested `change`.
- [Git-ambiguity recovery journey](git-ambiguity-recovery-journey.md) traces one
  accepted-but-unproven branch update through durable `FaultM`, host restart,
  head-first admission, explicit operation-scoped recovery, and final readiness.
- [Reminder-timer recovery journey](reminder-timer-recovery-journey.md) traces a
  lifecycle-driven reminder through one persistent timer command, canonical
  maturity, reconstructible custody, disposable wakes, lookup-first publication,
  host restart, and the next cycle.
- [Candidate review](candidate-review.md) applies the deletion test across all
  three journeys. It retains the current production module seams, rejects broad
  reorganization, and presents three correctness/operator candidates, two
  test-locality candidates, and one maintainer-navigation candidate for
  Navigator ruling.
- [RS-019 — Improve V5 test reading locality](../../workbench/rs-019-improve-v5-test-reading-locality.md)
  captures three parked Change Requests from the candidate review: state the
  head-first ambiguity blocker directly, replace positional shared journey
  aggregates with keyword arguments, and make two reminder tests name the cuts
  they actually exercise. The story is not pulled.
- [RS-020 — Fail closed on missing canonical History](../../workbench/rs-020-fail-closed-on-missing-canonical-history.md)
  captures the committed destructive-History-loss finding as a separate parked
  correctness refinement. Its crash-safe discriminator and operator disposition
  remain intentionally undesigned.
- [RS-021 — Fence inline V5 Activities after route revocation](../../workbench/rs-021-fence-inline-v5-activities-after-route-revocation.md),
  [RS-022 — Retain mutation ambiguity until recovery terminates](../../workbench/rs-022-retain-mutation-fault-until-recovery-terminates.md),
  and [RS-023 — Inspect current V5 Activity identities](../../workbench/rs-023-inspect-current-v5-activity-identities.md)
  capture the candidate review's three correctness and operator findings with
  explicit evidence, correctness obligations, validation seeds, and parked pull
  state.
- [RS-024 — Give import architecture rules one test owner](../../workbench/rs-024-consolidate-import-architecture-rules.md),
  [RS-025 — Make the current V5 maintainer route explicit](../../workbench/rs-025-make-v5-maintainer-route-explicit.md),
  and [RS-026 — Clarify full-gate build ownership](../../workbench/rs-026-clarify-full-gate-build-ownership.md)
  capture the remaining actionable locality, terminology, navigation, and
  validation findings. All Change Requests are parked.
- [RS-027 — Define reminder eligibility and stopping policy](../../workbench/rs-027-define-reminder-eligibility-and-stopping-policy.md)
  records that current reminders are lifecycle-driven while product intent does
  not yet say whether every active PR or only a human-blocked PR should receive
  them. Its policy decision is parked.
- The focused clean-green and agent-repair semantic journeys pass. The fixed Git
  recovery and late pending-head race pass together, and the generated Git
  recovery campaign passes its four anchors plus five deterministic examples.
  The reminder experiment passes 59 focused Net, timer, host, World, gate, and
  publisher tests plus one generated campaign with four anchors and five
  deterministic examples. The wider baseline Python suite reports 1,092 passes
  and 14 setup-test failures with one common precondition failure: GNU `stat -c`
  is unavailable on macOS. Bun-dependent checks could not start because `bun`
  is unavailable in the current shell.
- The Navigator completed the second, third, and fourth journey teach-backs. The
  fourth established reconstructible wakes versus the unacknowledged-arm
  fail-closed boundary, `TimerDue` in History as workflow truth,
  operation-scoped reminder settlement across heads, and lifecycle rather than
  approval control of reminder cycles.
- Candidate review found no evidence for broad production reorganization. The
  Navigator ruled that every actionable finding must be captured for later
  sessions while ES-009 remains dedicated to human learning. RS-021 through
  RS-026 now own those findings, all Change Requests remain parked, and no
  implementation story is pulled.
- The fourth experiment found no evidence for production reorganization. The
  Navigator accepted the learning evidence and approved two parked follow-ups:
  test-evidence naming under RS-019 and the reminder eligibility policy question
  under RS-027. No implementation story is pulled.

## Candidate gate

This story may produce several independent candidates for Refinement or Delivery.
Each candidate must identify concrete files, observed friction, the proposed
change in plain language, expected locality and leverage, test impact, change
radius, and any conflict with a settled decision. Promotion remains a separate
Navigator decision.
