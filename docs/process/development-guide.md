# Local Development Guide

This is Hamsterdan's project-specific Ariad operating contract.

## Commands

Python 3.14 is managed with uv.

- Install: `uv sync --frozen`
- Focused test: `uv run --frozen pytest -q PATH::NODE`
- Static feedback: `scripts/check quick`
- Path-scoped static feedback: `scripts/check quick PATH [PATH ...]`
- Checkpoint confidence: `scripts/check full`

The quick profile lints and format-checks maintained Python paths, type-checks
all production source, and runs the fast architecture contract. Its default
paths are `src` and `tests`; historical executable Exploration remains outside
the maintained lint surface. The full profile accepts no paths and adds Bun,
TypeScript, distribution-build, and routine Python-suite evidence.

Orb setup tests exercise the exact GNU/Linux command contract used by the orb,
including GNU `stat`. Pytest skips that module on BSD and other non-Linux hosts;
the Linux orb and hosted CI run it.

Routine commands run frozen and must not rewrite `uv.lock`. A dependency change
is deliberate and includes the lockfile.

## TDD and verification

1. Add one behavioral test and confirm the intended failure.
2. Make the smallest correct implementation pass it.
3. Refactor under the focused test, then run the related test file.
4. Run `scripts/check quick` over the project.
5. Run `scripts/check full` before an Experience Report.

User-visible or provider-visible work also requires the real operation route.
The Driver records expected and observed behavior, pass/fail status, commands,
GitHub identities and links, redacted diagnostics, and confidence limits. The
Navigator receives an Experience Report rather than routine QA assignments.

For durable, concurrent, stateful, or externally effectful work, include the
proportional [complex-system correctness sketch](complex-system-correctness.md)
in the Plan. Local pure changes do not need it.

## Documentation and history

Keep roadmap state, decisions, worklog milestones, debt, operator instructions,
and version claims coherent with implementation. Commit after each coherent
change is validated and accepted. Ask before pushing shared history.

Never place credentials, raw private webhook payloads, local runtime state, or
agent territory in project history or evidence.
