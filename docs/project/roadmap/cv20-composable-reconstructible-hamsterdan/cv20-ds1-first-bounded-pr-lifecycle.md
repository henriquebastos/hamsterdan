---
code: CV20.DS1
level: Delivery Story
status: Planned
status_reason: Promoted with CV20; the first tracer is not pulled
updated: 2026-08-28
related:
  - index.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS1 — Establish the first bounded PR lifecycle

## Outcome

Deliver the smallest real vertical pulse of the replacement: a deterministic
command registers one repository/PR subject, the production host composition
opens that subject's real readiness lifecycle, the real workflow is seeded and
advanced once, and host receives and records a detached bounded posture. The
same operation survives fresh-process reconstruction and exactly replays.

This tracer also establishes the strict replacement gate. It does not create an
empty final tree or speculative APIs for later components.

## Vertical path

```text
deterministic register/step command
  -> real host composition and one-subject custody
  -> real readiness subject/root binding
  -> public Petrus construction/replay seam
  -> real minimal workflow seed/fold
  -> detached StepResult and WorkPosture
  -> host posture record and bounded inspection
```

After acceptance, the replacement can construct, step, inspect, crash,
reconstruct and replay one non-selectable PR lifecycle. It accepts no provider
observation and performs no external effect.

## Component Technical Stories

The DS may expand into these independently green units, but none closes the DS:

1. inventory/apply applicable guidance and signed-in Amp skills, then install
   the isolated replacement Ruff/format/ty, verified ast-grep and semantic AST
   architecture/feedback gate over only the modules admitted by this tracer;
2. qualify and pin the minimum public Petrus page-bounded construction/replay
   seam required to reconstruct one seeded lifecycle;
3. implement the minimal workflow topology/seed and one lifecycle fold;
4. implement immutable one-PR subject/root binding and the initial detached
   `StepResult`/`WorkPosture` values;
5. implement the sole production host composition for one subject and bounded
   posture inspection; and
6. implement the minimum semantic-free Timeline, artifact/replay mechanics and
   workflow/readiness/host local simulation modules needed for this pulse.

Later package/file entries in the reviewed initial map remain absent until a
tracer has a real use for them. Positive architecture checks apply to the
implemented graph rather than passing through construction placeholders.

## Initial owned paths

```text
quality/hamsterdan2/** and scripts/check
src/hamsterdan2/workflow/{values,activities}.py
src/hamsterdan2/workflow/net/{life,topology}.py
src/hamsterdan2/readiness/{application,runtime,ports}.py
src/hamsterdan2/readiness/custody/instance.py
src/hamsterdan2/host/{composition,instances,inspection}.py
src/hamsterdan2/simulation/{runtime,clock,scheduling,artifacts,replay,hamsterdan}.py
implemented owner-local simulation modules/checkers
tests2 gate, owner-behavior, integration and tracer tests
Petrus repository public seam and dependency pin, if qualification requires it
```

The DS API review may merge or split these initial paths under the deletion
test. Package ownership and forbidden edges do not change.

## Fixed design

- One readiness lifecycle is immutably bound to one provider route, repository
  and PR; a mismatch fails before workflow execution.
- `host.composition` is the only concrete construction root. Host receives no
  workflow marking, History row, Activity terminal or Petrus runtime object.
- The workflow owner supplies real seed/fold meaning. Neither readiness nor the
  simulation substitutes a fake state machine.
- One production call returns after one named bounded cut. No constructor or
  helper drains to convergence.
- `StepResult` is detached from live runtime objects. The first tracer needs
  only the variants and posture fields its actual call sites prove.
- Timeline owns mechanics only. Workflow, readiness and host local modules own
  their commands, eligibility, evidence, resources and checkers.
- Restart destroys process-local objects and rebuilds from the registered root
  plus retained owner state. Exact replay builds a fresh object graph.
- Every command, retained row, History page, step, journal and artifact has a
  finite tested limit from this tracer onward.
- `hamsterdan2` remains absent from package entry points, service selection,
  deployment and current state roots.
- The gate starts strict and grows with admitted code. No blanket suppression,
  empty final skeleton, compatibility alias or speculative facade is accepted.
- The isolated gate covers only `src/hamsterdan2` and `tests2` through DS12.
  Legacy source/tests retain their current repository gate until DS13 promotes
  the replacement.
- `quick` includes replacement Ruff lint/format, ty, verified ast-grep,
  fast AST architecture/feedback checks and fast pytest. `full` inherits quick
  and adds complete deterministic pytest/Hypothesis, Timeline/DST replay with
  domain-aware shrinking, semantic coverage, accepted focused mutation evidence
  and accepted real seams. `release` inherits full and adds accepted serial and
  revision-bound suites.
- Exact ty configuration; mutation tool, targets, threshold/survival policy and
  cadence; numeric coverage policy; real/live markers, environment and
  skip/fail policy; and calibrated resource limits remain Plan refinements.

## API-strengthening checkpoint

Before implementation, review one focused packet containing:

- **guidance and skills:** applicable root/nested `AGENTS.md`, Ariad Process/
  Project/Product owners, engineering conventions and signed-in personal/global
  Amp skills, with conflicts or justified non-application recorded;
- **behavior and call tree:** exact register, open, step, posture-record and
  inspect sequence;
- **types/signatures:** subject/root representation, lifecycle factory/calls,
  minimal `StepResult`, `WorkPosture`, Timeline and artifact results;
- **identity/authority:** immutable subject, root and process-generation
  identities; no protected-effect authority exists yet;
- **errors:** subject mismatch, malformed command, stale generation,
  reconstruction and budget failures;
- **cuts/recovery:** root registered, lifecycle opened, workflow advanced and
  posture recorded, with the chosen durable side of each cut;
- **observations/limits:** detached inspection fields, checker reports, journal
  fields and exact row/page/byte/step limits; and
- **unresolved names:** gate commands, factory methods, result fields and
  artifact diagnostics.

The packet must show producer and consumer call sites together. Resolved names
and signatures are written into [the API contract](api-contracts.md) before
code. The one-PR ownership, bounded-call, fresh-reconstruction, simulation
ownership and non-selectability rules are fixed.

## Tracer acceptance

Given a fresh replacement root and one valid subject, when the deterministic
command registers and steps it, then production host composition opens the real
readiness/workflow path and records one bounded detached posture. Crashing after
the durable root or posture cut and rebuilding generation 2 produces the same
posture without duplicate root or workflow creation.

Acceptance requires:

- owner-local workflow, readiness and host checkers plus one cross checker whose
  subject/root substitution leaves locals green and fails only the boundary;
- named pre/post durable cuts, exact fresh-object replay and lowered-budget
  counterexamples;
- operation, History, retained-row, loaded-instance, journal and artifact-byte
  peaks in the evidence report;
- direct correspondence for public Petrus replay/reconstruction and fresh
  filesystem/SQLite reopen; and
- `tests2/test_feedback.py` proof that every replacement path is covered only by
  the intended profile, with no final-tree placeholder;
- TDD, pytest/Hypothesis, Timeline/DST replay/shrink, semantic coverage,
  focused mutation sensitivity and accepted real-seam evidence; and
- the strict target gate, quick/full checks, distribution invisibility and
  current-runtime regression tests.

## Done condition

The real vertical path—not merely its six components—passes its behavioral,
recovery, checker-sensitivity, replay, correspondence and finite-bound evidence.
The current runtime remains the only selectable application.

## Stop conditions

Stop for Navigator review if the pulse requires a final-tree placeholder,
private Petrus state, an unbounded constructor/drain, a host dependency on
workflow internals, a process-local recovery authority, or an API without both
its first real producer and consumer.

## Rollback

Remove the admitted replacement modules, fresh roots, isolated gate and any
qualified dependency pin. No installed application or current state refers to
them.

## Validation

Run guidance/skill inventory and target-profile path-isolation fixtures; target
Ruff/format/ty/ast-grep/AST architecture/feedback checks; TDD owner behavior and
Hypothesis; Timeline/DST replay, domain-aware shrinking and semantic coverage;
focused mutation sensitivity; accepted real seams; real Petrus integration;
fresh reopen and generation-loss cuts; subject substitution sensitivity; every
limit at −1 / limit / +1; distribution checks; and project quick/full gates.

## Expansion boundary

Expand into the component Technical Stories above, then implement them in the
order needed to keep the tracer executable. A component commit may be green;
the DS remains open until the Navigator can inspect the complete vertical
artifact and posture.
