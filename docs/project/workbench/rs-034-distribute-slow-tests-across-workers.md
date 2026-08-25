---
status: Completed
captured: 2026-08-25
pulled: 2026-08-25
completed: 2026-08-25
navigator: Henrique
source: direct Navigator request
---

# RS-034 — Distribute slow tests across routine workers

## Existing field to refine

Hamsterdan's routine Python gate uses four xdist workers with `--dist loadscope`.
The five deterministic readiness campaigns in
`tests/integration/testing/test_readiness_campaign.py` therefore run as one
module-scoped queue on one worker. Local profiling on macOS ARM64 with Python
3.14.0 measured 108.12 seconds for the current parallel command, while the five
campaign calls accounted for 92.31 seconds on that worker.

Two complete local runs using item scheduling with one-test chunks passed all
1,104 selected tests in 65.55 and 67.60 seconds. The average 66.58-second wall
time is 38.4% lower than the current parallel baseline, with higher aggregate
CPU use from overlapping the campaigns.

## Accepted boundary

Change only the routine parallel scheduler from module-scoped distribution to
item distribution with one-test scheduling chunks. Preserve four workers, fixed
seed 1729, routine marker selection, strict selected-skip handling, campaign
example counts, continuous checking, exact replay, and the separate serial
release run.

Simulation-harness performance work, campaign evidence reduction, provider
acceptance, Linux Orb setup tests, and ES-009 remain outside this refinement.

## Change Request

### CR-001 — Schedule routine tests as individual one-test chunks

Status: Done

Files:

- `scripts/check`
- `tests/test_check_command.py`
- `tests/test_pytest_policy.py`

Done condition:

- the command contract requires `-n 4 --dist load --maxschedchunk=1`;
- focused command tests and quick checks pass;
- the complete local routine Python selection passes with the changed scheduler;
- observed wall time and resource trade-offs are retained as bounded local evidence.

## Validation

- the command-contract test failed before implementation because `scripts/check`
  still selected `loadscope`, then passed after the scheduler changed;
- all 9 feedback-command and selected-skip policy tests passed;
- `scripts/check quick` passed Ruff, formatting, production typing, and 10
  architecture tests;
- the complete local routine Python selection passed 1,104 tests after the
  change in 78.44 seconds;
- two equivalent pre-implementation command probes passed the same 1,104 tests
  in 65.55 and 67.60 seconds. Across observed machine contention, item scheduling
  remained 27.4% to 39.4% below the 108.12-second `loadscope` baseline;
- `scripts/check full` passed quick and all 9 Amp relay tests, then stopped in the
  demo-video suite after the known Bun 1.4.0 Playwright timeout produced eight
  failures. RS-033 already owns this mismatch from the required Bun 1.3.10;
- `git diff --check` and changed-file diagnostics passed.

The Navigator accepted the observed experience. Refinement Review then found
that the selected-skip policy probe still used the retired `loadscope` shape.
CR-001 was reopened, the probe was aligned with item scheduling and one-test
chunks, and all 9 focused feedback-policy tests plus `scripts/check quick`
passed again.

## Refinement Review

Item scheduling preserves test-process isolation and the existing routine
selection while allowing the five long campaign tests to overlap. The suite
uses temporary paths for ordinary writes; generated failure artifacts have
separate retained paths and are not written by successful schedules. Three
complete item-scheduled runs passed all 1,104 tests.

No implementation refactoring or new durable debt is warranted. Improving the
simulation World's repeated History and SQLite observation scans remains a
separate possible refinement rather than hidden RS-034 scope. The Bun 1.4.0
full-gate limitation remains owned by RS-033.

## Coherence

- Process: `scripts/check`, its command contract, and the selected-skip policy
  probe agree on four-worker item scheduling with one-test chunks.
- Project: RS-034 owns the bounded performance evidence and closes outside the
  roadmap and independently of ES-009.
- Product: no runtime, provider, workflow, campaign-evidence, or user-visible
  behavior changed.
- Debt: no new obligation was introduced; RS-033 remains the owner of local
  toolchain drift.

## Outcome

RS-034 is complete. The routine Python gate retains its existing evidence and
uses the available workers more effectively on the measured local workload.
