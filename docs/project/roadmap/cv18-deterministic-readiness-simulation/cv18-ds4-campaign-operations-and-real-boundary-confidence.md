---
code: CV18.DS4
level: Delivery Story
status: Paused
status_reason: Campaign operations are deliberately deferred until after private v0.1 production qualification
updated: 2026-08-23
related:
  - index.md
  - cv18-ds3-generated-readiness-and-recovery-campaigns.md
  - ../cv17-v5-actor-loop-production-parity/cv17-ds4-production-parity-harness.md
---

# CV18.DS4 — Campaign operations and real-boundary confidence

## Intent

Make deterministic readiness simulation routine, bounded, replayable, and
honest about its relationship to real GitHub, Git, agent, persistence, process,
and deployment evidence.

## Scope

- Establish campaign tiers:
  - ordinary changes run the stable minimized regression corpus and a small
    fixed deterministic campaign;
  - scheduled or explicitly requested campaigns rotate broad and targeted
    profiles under a larger bounded budget; and
  - release or live-acceptance preparation names both simulated and real routes
    without treating one as evidence for the other.
- Retain redacted failure artifacts with minimized expanded scenario, discovery
  metadata, exact replay command, failed property, Hamsterdan/Petrus commits and
  dependency identity, shrink lineage, and semantic coverage.
- Require replay before diagnosis, shrinking before acceptance of a fix, and
  promotion of the minimized case into the stable corpus. A fix that only makes
  one seed disappear is not accepted.
- Keep real-boundary tests for signed webhook custody, SQLite/Petrus persistence,
  actual process restart, Git object/ref publication, GitHub lookup-first
  recovery, agent protocol/credential isolation, and selected live GitHub
  journeys. State which behaviors remain outside the model.
- Provide campaign capacity sketches and enforced budgets for event/state size,
  run count, CPU/memory/storage, artifacts, PR latency, scheduled throughput,
  and concurrent provider-free test workers.
- Add the commands, triage documentation, known-blind-spot register, and
  project-level Ariad/AGENTS routing accepted in DS1. Retrieval begins at the
  roadmap and focused owner, not this historical investigation.
- Periodically review quiet profiles and complement targeted generation with
  simpler broad generation rather than assuming a lack of failures means
  completeness.

## Acceptance / Done condition

1. A fresh checkout runs the ordinary campaign and a documented larger
   provider-free campaign with enforced resource and time bounds.
2. A deterministic failure produces a safe useful artifact and exact replay;
   its minimized regression fails before and passes after a legitimate fix.
3. Silent campaign truncation, timeout, unsupported event, artifact overflow,
   or unmodeled provider request fails visibly rather than reporting green.
4. One simulated provider-ambiguity/restart scenario is compared with a focused
   real-boundary counterpart, documenting correspondence and non-equivalence.
5. CI evidence reports profiles, semantic reach, deselections, and known blind
   spots—not only test count or seed count.
6. CV17's completed parity/live acceptance remains truthful and separate; CV18
   neither reopens it nor changes topology default.
7. `scripts/check full`, the documented scheduled campaign, selected actual
   process/persistence routes, and authorized real-provider acceptance pass with
   unexpected skips forbidden where the route requires them.
8. Independent review finds no claim of exactly-once effects, exhaustive state
   coverage, full provider fidelity, or correctness beyond executed evidence.

## Driver QA and evidence plan

- Rehearse green, fail, replay, shrink, regression promotion, and triage from a
  clean checkout.
- Measure campaign budgets on the supported environment instead of choosing an
  arbitrary number of examples.
- Execute one actual host restart/persistence route and one authorized
  GitHub-visible lookup-first/effect route beside their simulated counterparts.
- Run focused suites and `scripts/check full`; preserve real-provider authority
  and cleanup requirements as separate explicit checkpoints.

## Out of scope

- Unbounded swarm tests on every pull request.
- Credentials, private payloads, installation tokens, or agent workspace
  archives in replay artifacts.
- Replacing CV17's live parity campaign, load/security testing, or real provider
  contracts.
- Automatically publishing or enabling production changes from a simulation.
- Claiming exactly-once effects, exhaustive coverage, or absence of bugs.
