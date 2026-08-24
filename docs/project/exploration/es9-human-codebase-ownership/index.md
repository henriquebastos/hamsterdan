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
- The focused clean-green semantic journey passes. The wider Python suite reports
  1,092 passes and 14 setup-test failures with one common precondition failure:
  GNU `stat -c` is unavailable on macOS. Bun-dependent checks could not start
  because `bun` is unavailable in the current shell.
- The architecture inspection has produced evidence-backed friction signals, but
  they remain exploratory until the Navigator completes the first journey
  teach-back and reviews the interpretations.

## Candidate gate

This story may produce several independent candidates for Refinement or Delivery.
Each candidate must identify concrete files, observed friction, the proposed
change in plain language, expected locality and leverage, test impact, change
radius, and any conflict with a settled decision. Promotion remains a separate
Navigator decision.
