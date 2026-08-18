---
code: CV18.DS3
level: Delivery Story
status: Active
status_reason: The accepted prerequisite split preserves DS2 compatibility; generated schedules, remaining fault adapters, and shrinking remain
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

The accepted first slice extracted shared strict contracts and compatibility
identities into `_readiness_contract.py` and modeled provider truth plus
boundary adapters into `_readiness_provider.py`. Petrus profile, independent
checker, Timeline, World, and replay composition remain together in
`readiness_world.py`. Characterization fixes the exact profile and checker
identities, and the existing crash/reconstruction artifact still replays
exactly through the one interpreter.

This is the prerequisite structural boundary, not generated semantic coverage.
No command vocabulary, fault adapter, dependency, topology selection, or Petrus
surface changed. The next slice must exercise the boundary with a generated
dimension before the composition debt can close.

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
