---
status: Candidate
captured: 2026-08-25
navigator: Henrique
source: rs-029-broaden-non-blocking-quality-evidence.md
---

# RS-030 — Review the maintained complexity baseline

## Existing field to refine

The non-blocking Ruff `C901` audit at complexity 10 reports 47 functions: 39 in
production and 8 in tests. The highest are `operator.qualification_setup` at 52,
the V5 test `make_activities` harness at 46, readiness World validation at 39,
World application at 32, readiness coverage operation signals at 31, the
scenario journey runner at 26, and `workflow_wait` at 25.

Complexity is a review signal, not proof that one function has multiple owners.
Some workflow, parsing, state-machine, and lifecycle folds may justify a narrow
exception after review. Adding 47 suppressions or splitting functions by line
count would erase the evidence without improving the code.

## Candidate boundary

Review production functions above 15 first. For each, identify its semantic
responsibilities, focused behavioral evidence, likely extraction seams, and
whether a cohesive-algorithm exception is more honest. Pull separate Change
Requests for accepted refactorings; do not make repository-wide `C901` blocking
until the maintained baseline has explicit dispositions.

## Change Request

### CR-001 — Classify production functions above complexity 15

Status: Parked

Validation must preserve focused behavior and compare the audit count before and
after each accepted change. Test-only complexity follows after production
classification and should preserve scenario readability rather than optimize a
number.
