---
code: CV18.DS3
level: Delivery Story
status: Active
status_reason: The first bounded generated recovery campaign and exact successful/failure replay are accepted; broader vocabulary, checker coverage, and operations remain
updated: 2026-08-18
related:
  - index.md
  - cv18-ds2-deterministic-host-and-provider-fault-world.md
  - ../../debt/items/readiness-dst-composition-must-split-before-campaign-expansion.md
---

# CV18.DS3 — Generated readiness and recovery campaigns

## Intent

Explore readiness, authority, collaboration, effect, and recovery state space
automatically while an independent expected-readiness model—not the topology or fake provider—
defines the expected semantic outcome.

## Scope

- First split DS2's provider truth/transport/agent adapters from its Petrus
  profile/checker/Timeline composition without changing artifact identity or
  behavior. Do not expand the current 1,495-line vertical module in place.
- Materialize the remaining DS1 fault adapters only beside generated commands
  and properties that exercise them: stale/rate-limited reads,
  History/Dispatch/timer cuts, agent terminal delivery, and Git publication.
  The accepted DS2 vertical is not evidence for those families.
- Add Hypothesis state-machine commands over DS2's normalized event and fault
  vocabulary. Generate valid external actions, stale/duplicate actions, and
  deliberately malformed boundary inputs without directly choosing internal
  transitions.
- Maintain both:
  - broad minimally constrained generation across heads, bases, policy,
    lifecycle, CI, review, conversation, effects, timers, crashes, and provider
    outcomes; and
  - focused profiles for expensive known boundaries such as stale authority,
    effect ambiguity, lifecycle/completion races, retry exhaustion, timer
    acknowledgement/maturity cuts, duplicate custody, and host reconstruction.
- Compare the real composition with the DS1 readiness model after every
  accepted event. Add independent effect-ledger, credential-isolation,
  identity/collision, current-authority, replay/restart, and bound checkers.
- Enter a declared fair phase after generated safety faults and require bounded
  convergence to a current semantic result, explicit wait, terminal, exhaustion,
  or quarantine.
- Shrink failures to the smallest useful expanded scenario. Preserve that
  scenario as an ordinary regression with original discovery metadata and exact
  Hamsterdan/Petrus code identity.
- Report semantic coverage and blind spots: lifecycle phases/generations,
  content and collaboration states, effect classes, fault outcomes, authority
  fences, crash cuts, recovery paths, terminal dispositions, and model/checker
  activations.

## Current progress

The accepted prerequisite slice extracted shared strict contracts and
compatibility identities into `_readiness_contract.py` and modeled provider
truth plus boundary adapters into `_readiness_provider.py`. Petrus profile,
independent checker, Timeline, World, and replay composition remain together in
`readiness_world.py`; exact profile/checker identities and the accepted DS2
vertical remain stable.

The accepted first generated slice now uses that split through a bounded
Hypothesis state machine. A Petrus seed authoritatively chooses effect-response
loss, initial crash order, finish-time redelivery, and scenario identity.
Generated rules interleave one disclosed host action, duplicate webhook
delivery, and abrupt generation reconstruction. The independent readiness
state is inspected after every generated boundary; a declared fair phase then
requires one ready host result and at most one accepted readiness effect. Every
successful expanded schedule exactly replays through Petrus's one interpreter.

A mutation-style checker-sensitivity regression creates a disposed-custody
mismatch, lets Hypothesis reduce the executable story, retains the exact
terminal checker-failure operation as a v3 artifact, and replays that failure
through the same interpreter. Primary counterexamples survive teardown and
artifact-retention diagnostics. Timeline `pending` and one-step `step` are
generation-fenced, so a stale authoring handle cannot reach a replacement host.

The project now pins Petrus commit `5ded726`, API `petrus.testing.dst/v3`,
artifact v3, and replay-result v2. V3 adds seeded provenance; inherited v2/v3
support retains World-owned budget/checker failures. Hypothesis is a bounded
development dependency. No production topology, profile/checker identity, or
V5 selection changed.

This is one focused generated recovery dimension, not broad campaign
completion. Lifecycle/head evolution, timer/retry schedules, remaining DS1
fault adapters, wider checker properties, semantic coverage reporting, and
operational campaign retention remain active DS3/DS4 work.

## Acceptance / Done condition

1. Generated runs combine at least lifecycle/head evolution, provider evidence,
   one external effect, one timer or retry, a crash/restart, and one ambiguity
   or redelivery class.
2. Every CV18 safety property has an executable independent checker or a
   recorded blocked reason and revisit trigger.
3. Fair-phase failure distinguishes host/runtime livelock from legitimate human
   wait, unavailable external prerequisite, bounded exhaustion, and an invalid
   fairness declaration.
4. A deliberately introduced defect or selected mutation is found and shrunk
   to a materially smaller replayable scenario before the legitimate fix.
5. Broad generation reaches a semantic combination absent from CV3/CV17's
   focused historical portfolio.
6. The model and checkers never call the production decision or topology state
   fold they claim to verify.
7. Retained failures contain no credentials, unrestricted provider payloads, or
   agent workspace content.
8. Every generated fault family names its executable adapter and checker;
   contract-only names are reported as blocked rather than counted as coverage.

## Driver QA and evidence plan

- Prove checker sensitivity with selected mutations or temporary test-only
  defects, then remove them and retain legitimate regression scenarios only.
- Inspect command/profile distributions and semantic reach; seed count and line
  coverage alone are insufficient.
- Run fixed replay fixtures, a bounded local campaign, focused host/readiness
  suites, and `scripts/check full`.

## Out of scope

- Exhaustive exploration, formal verification, or bug-absence claims.
- Byte-identical production/V5 traces or comments.
- Full GitHub/model-provider emulation.
- Random scenarios with no model, checker, or replay path.
