# Local Development Guide

This is Hamsterdan's project-specific Ariad operating contract.

## Commands

Python 3.14 is managed with uv.

- Install: `uv sync --frozen`
- Focused test: `uv run --frozen pytest -q PATH::NODE`
- Static feedback: `scripts/check quick`
- Checkpoint confidence: `scripts/check full`

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

## Documentation and history

Keep roadmap state, decisions, worklog milestones, debt, operator instructions,
and version claims coherent with implementation. Commit after each coherent
change is validated and accepted. Ask before pushing shared history.

Never place credentials, raw private webhook payloads, local runtime state, or
agent territory in project history or evidence.
