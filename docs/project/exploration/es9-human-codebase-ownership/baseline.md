# ES-009 baseline

Captured 2026-08-24 from `main` at `5d4af32` before any production-code
change in this exploration.

## Repository shape

- 61 Python source files, approximately 23,795 lines.
- 43 Python test files, approximately 26,654 lines.
- 418 tracked documentation files.
- The largest files are navigation signals only. Size does not establish that a
  module is shallow or should be split.

The current production reading path is narrower than the repository:

```text
signed webhook or reconciliation wake
  -> host custody and per-PR activation
  -> V5 ingress manifest and host grant
  -> PrReadinessV5Application
  -> V5Runtime / Petrus Engine and History
  -> readiness.net_v5 concern loops
  -> typed Motus Activity
  -> authority-fenced provider effect
  -> typed terminal folded back into History
```

Historical explorations, the demo-video studio, and operator qualification are
followed only when they explain a current choice on this path.

## Validation baseline

`scripts/check full` did not complete in the current macOS shell:

- Ruff lint passed.
- Ruff formatting passed for 104 files.
- `ty check src` passed.
- The gate stopped before Bun tests, package build, and pytest because `bun` was
  not available on `PATH`.

The Python phase was then run independently:

```sh
uv run --frozen pytest -q -m "not real_provider_acceptance"
```

Result: 1,092 passed and 14 failed in 131.32 seconds.

All 14 failures are in `tests/unit/test_orb_setup.py`. Their common cause is that
the sandbox executes `.agents/setup` on macOS, while its private-file checks use
GNU `stat -c` for owner, mode, and size. BSD `stat` rejects `-c`, so setup fails
before each test reaches its intended assertion. This is baseline environment
friction, not evidence that the 14 independently named behaviors regressed.

The focused current-V5 clean-green journey was also exercised independently:

```sh
PYTHONDONTWRITEBYTECODE=1 uv run --frozen pytest -q -p no:cacheprovider \
  tests/integration/host/test_readiness_scenarios.py::test_clean_green_user_journey
```

Result: 1 passed in 3.18 seconds.

No live provider route or host launch was attempted.

## Test surfaces

A maintainer chooses tests by the behavior seam rather than by file size:

1. `tests/test_architecture.py` and `tests/test_distribution.py` own repository
   dependency and artifact rules.
2. `tests/unit/` owns strict values, local stores, provider algorithms, gates,
   and direct Net behavior.
3. `tests/unit/readiness/net_v5/` uses a real Petrus Engine with a test-world
   adapter to exercise topology, folds, held Activities, and recovery.
4. `tests/integration/host/` owns composed custody, host persistence, restart,
   and real local Git/process seams.
5. `tests/integration/host/test_readiness_scenarios.py` owns recognizable
   end-to-end semantic journeys.
6. `tests/integration/testing/` owns independent-model checking, generated event
   schedules, replay, fairness, and resource bounds.
7. Provider-visible changes additionally require separately reported real-route
   evidence; local green tests do not imply live-provider proof.

## Initial navigation signals

These observations are not yet improvement candidates:

- The same sibling-import architecture rule is tested by two partially
  overlapping scanners in `tests/test_architecture.py` and
  `tests/unit/host/test_host_architecture.py`.
- Test-layer selection is encoded mostly in existing examples rather than in the
  development guide; several `unit` tests deliberately use real Engine, JSONL,
  or SQLite implementations.
- Supported test-only modules under `src/hamsterdan/testing` and
  `src/hamsterdan/host/testing` ship in the distribution, while the Net harness
  under `tests/` remains local; the reason is not explained in the short guide.
- The declared `real_provider_acceptance` marker has no current marked test,
  although project policy and historical records still distinguish real-route
  evidence from local simulation.
- The full gate builds once directly and once through the distribution test for
  different purposes; the validation responsibility is overlapping but not
  identical.

Architecture signals require a separate evidence pass and the deletion test
before they become candidates.
