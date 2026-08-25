---
status: Candidate
captured: 2026-08-24
navigator: Henrique
source: ../exploration/es9-human-codebase-ownership/candidate-review.md
---

# RS-026 — Clarify full-gate build ownership

## Existing field to refine

`scripts/check full` currently builds the package directly, then the pytest phase
runs `tests/test_distribution.py`, which builds a wheel and source distribution
again so it can inspect their contents.

The two builds have different stated purposes, but the distribution test already
fails if either artifact cannot build. The direct build also leaves `dist/` in
the working tree. No repository script or documented workflow was found that
consumes that directory after `scripts/check full`.

The ES-009 shell could not execute the full gate because Bun was unavailable, so
this review did not measure the duplicate cost or prove that no external manual
workflow relies on the `dist/` postcondition.

## Candidate boundary

Determine whether the full gate promises to leave release artifacts in `dist/`.
If it does not, give build success and artifact safety one owner in the
distribution test. If it does, document that postcondition and keep the direct
build deliberately.

Do not optimize based on assumed duration. Measure or at least record command
ownership in an environment with Python, uv, and Bun available.

## Change Request

### CR-001 — Select and document one full-gate build contract

Status: Parked

Likely files:

- `scripts/check`
- `tests/test_distribution.py`
- `docs/process/development-guide.md`, if the `dist/` postcondition is retained

Validation seeds:

- run the complete gate from a clean checkout with Bun available;
- verify both wheel and source distribution are built and inspected once under
  the selected owner;
- confirm whether `dist/` is intentionally present or absent afterward;
- search CI, operator, and release scripts for consumers before changing the
  postcondition;
- run `scripts/check full` after the change.

## Pull state

This candidate is captured but not pulled. No validation command, artifact
postcondition, distribution test, commit, or release action is authorized by
this record. ES-009 remains a learning session.
