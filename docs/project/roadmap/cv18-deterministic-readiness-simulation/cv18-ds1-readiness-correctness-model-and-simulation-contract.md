---
code: CV18.DS1
level: Delivery Story
status: Planned
status_reason: Hamsterdan's independent readiness oracle, generated-scenario contract, and project guidance are not yet defined
updated: 2026-08-17
related:
  - index.md
  - ../cv17-v5-actor-loop-production-parity/cv17-ds4-production-parity-harness.md
---

# CV18.DS1 — Readiness correctness model and simulation contract

## Intent

Define what Hamsterdan DST will judge before adding more fake infrastructure or
random scenarios, preserving one independent source of expected readiness truth.

## Scope

- Specify a small pure readiness model in domain terms: current generation and
  authority, admitted observations, required CI, review/finding state, human
  collaboration state, requested changes, effect obligations, timers, and
  terminal/wait disposition.
- Keep the model independent: it must not import the readiness Net, Engine,
  production host folds, topology-specific state, or helpers that make the
  production decision under test. It may consume normalized neutral contracts.
- Freeze the CV18 safety properties, fair-environment liveness condition,
  scenario/event schema, provider fault taxonomy, bounds, semantic coverage,
  and relationship to CV17 parity.
- Map nondeterminism and irreversible cuts across webhook custody, ingress
  normalization, runnable scheduling, timer custody, Petrus History/Dispatch,
  agent operation custody, GitHub reads/effects, Git publication, settlement,
  acknowledgement, host close, and restart.
- Define a compatibility contract with Petrus CV19. Name the accepted public or
  test surface Hamsterdan needs; prohibit private runtime imports and a local
  fork of event scheduling or crash reconstruction.
- Decide where the project-level **complex-system correctness sketch** belongs
  in Ariad/Hamsterdan guidance. For durable, concurrent, stateful, or externally
  effectful stories, future plans must identify:
  - authoritative state and current authority;
  - safety invariants;
  - fair-environment liveness assumptions;
  - queue/retry/timer/payload/concurrency/work bounds and dispositions;
  - nondeterministic inputs;
  - costly crash and ambiguity cuts; and
  - an independent oracle/checker or the reason one is impractical.
- Route that requirement concisely from AGENTS/development guidance to one
  focused owner. Do not add Tiger Style or a duplicate lifecycle to every task.

## Acceptance / Done condition

1. The model can judge clean green, transient and persistent CI failure,
   finding, conversation/mutation, draft/resume/close, stale authority, and
   human-wait scenarios without inspecting a topology trace.
2. At least one deliberately different production and V5 internal path maps to
   the same model outcome, preserving semantic rather than structural judgment.
3. Every initial event/fault kind has an explicit bound, accepted/rejected/
   ambiguous outcome, and strict-data replay representation.
4. Safety and liveness are separately executable in shape; infinite provider
   failure or missing human input is not mislabeled runtime livelock.
5. A known Hamsterdan crash/recovery scenario fits the schema without storing
   credentials, raw private payloads, clients, closures, or live objects.
6. The Petrus dependency and CV17 boundary are explicit enough that a future
   Driver cannot accidentally duplicate either workstream.
7. Project guidance is conditionally routed and consistent with Ariad's
   progressive retrieval and existing Driver/Navigator authority.

## Driver QA and evidence plan

- Walk the oracle through current CV17 semantic scenarios and representative
  authority, timer, ingress, Activity, publication, mutation, and restart tests.
- Run differential probes where production/V5 behavior is already expected to
  agree semantically, without requiring identical traces or bytes.
- Audit direct time, randomness, UUID, sleep, provider, subprocess, and task
  scheduling calls for the simulation inventory.
- Validate documentation and execute the smallest related existing suites; this
  story does not claim a functioning generated campaign.

## Out of scope

- Implementing the Petrus harness or Hamsterdan provider world.
- Replacing CV17's parity oracle or live acceptance.
- Choosing V5 as production default.
- Global user AGENTS.md changes.
