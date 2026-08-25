---
status: Completed
captured: 2026-08-24
pulled: 2026-08-24
completed: 2026-08-25
navigator: Henrique
source: direct Navigator request
---

# RS-028 — Align engineering feedback with Petrus practice

## Existing field to refine

Hamsterdan already runs Ruff lint and formatting, `ty`, Bun and TypeScript
checks, distribution builds, Python tests, and hosted CI. Its feedback command
is less bounded and less self-describing than Petrus's, and the local engineering
conventions state architecture rules without the reusable boundary, durability,
Activity, retry, and evidence practices that Hamsterdan already depends on.

Petrus's exact package graph, structural rules, mutation targets, complexity
baseline, and test harness do not define this application. Hamsterdan needs an
adaptation around its own `host`, `github_app`, `agents`, `readiness`, and
`contracts` ownership.

## Accepted boundary

This first alignment keeps the maintained lint surface at `src` and `tests`,
gives `scripts/check` repository-root and frozen execution, adds path-scoped
quick checks and help, and runs the fast architecture contract in that profile.
It adds project tests for the command interface.

The engineering-conventions document gains reusable practice for thin adapters,
boundary validation, canonical durable values, complete Activity invocations,
mutation-aware retries, strict fakes, exact evidence, and honest effect claims.
Architecture enforcement remains a Python test owned by RS-024 rather than a
second `ast-grep` system.

Repository-wide linting, cyclomatic-complexity enforcement, randomized or
parallel pytest, selected-test skip rejection, mutation testing, and a release
profile belong to a separately validated broad-alignment change. Existing
findings there will be recorded rather than fixed opportunistically.

## Change Requests

### CR-001 — Make the feedback command bounded and self-describing

Status: Done

Files:

- `scripts/check`
- `tests/test_check_command.py`
- `docs/process/development-guide.md`

### CR-002 — Adapt reusable Petrus engineering conventions

Status: Done

Files:

- `docs/process/engineering-conventions.md`
- `docs/references/index.md`

### CR-003 — Run Orb setup tests only on their Linux command contract

Status: Done

Files:

- `tests/unit/test_orb_setup.py`
- `docs/process/development-guide.md`

The setup script deliberately uses GNU/Linux command behavior. The module now
reports an explicit platform skip on BSD and other non-Linux hosts while the
Linux orb and hosted CI continue to execute all cases.

## Validation

- focused check-command, architecture, and credential-boundary validation passed
  16 tests;
- path-scoped and default quick profiles passed, including Ruff, formatting,
  production typing, and 10 architecture checks;
- distribution build passed;
- the complete routine Python invocation passed 1,100 tests and reported 17
  intentional Orb setup skips on macOS; the Orb module directly reported the
  same 17 platform skips;
- the Amp relay passed all 9 tests;
- TypeScript compilation passed, while the demo-video test run passed 36 tests
  and failed after one Playwright timeout closed the shared browser. The local
  Bun is 1.4.0 rather than the project and CI pin of 1.3.10;
- `git diff --check` passed and independent review findings were corrected.

The maintained Python change is locally qualified. The exact full gate remains
environment-limited until the demo suite runs with Bun 1.3.10; Linux owns the
separate Orb setup evidence. The Navigator accepted this environment-qualified
result on 2026-08-25.
