---
status: Completed
captured: 2026-08-25
pulled: 2026-08-25
completed: 2026-08-25
navigator: Henrique
source: direct Navigator request
---

# RS-029 — Broaden non-blocking quality evidence

## Existing field to refine

RS-028 established one blocking feedback interface for maintained Python,
architecture, Bun, TypeScript, build, and routine test evidence. Petrus also
uses randomized and parallel tests, strict skip handling, cyclomatic-complexity
measurement, ast-grep convention scans, a second release order, and curated
mutation testing.

Hamsterdan has no accepted baseline for those checks. Repository-wide Ruff and
complexity probes already report findings in historical experiments and current
maintained code. Turning every new probe into a commit gate would silently turn
tooling adoption into a large refactoring campaign.

## Accepted boundary

Add the broader tools and execute them against the current repository. Existing
quick checks remain blocking. Randomized and parallel tests become blocking only
if the current suite proves stable. Repository-wide lint, complexity, ast-grep,
and mutation results are audit evidence: their commands return success after
printing a clear finding summary, and unresolved results receive a Workbench or
debt owner.

Do not fix production complexity, historical Exploration lint, reflective-access
findings, mutation survivors, or unrelated test design merely to make the new
audits green. Do not duplicate the Python architecture contract in ast-grep.

## Change Requests

### CR-001 — Exercise deterministic randomized and parallel test orders

Status: Done

Add `pytest-randomly`, `pytest-xdist`, explicit seed and strict selected-test skip
handling, then run the routine suite in parallel. Add a release profile with one
additional fixed seed only if its command contract is testable and current tests
support it.

### CR-002 — Add non-blocking structural and complexity audits

Status: Done

Add an audit profile for repository-wide Ruff, maintained-code `C901`, and one
ast-grep practice rule outside architecture ownership. Record rather than repair
its baseline findings.

### CR-003 — Add a curated mutation probe

Status: Done

Add an explicitly optional mutation profile over a small pure-semantic target.
The profile has no score threshold and does not enter quick, full, or release.
Record surviving and uncovered mutants for later refinement.

## Observed evidence

- frozen dependency sync and the project-owned resolver cutoff passed; adding the
  four tools re-resolved Hypothesis from 6.165.10 to 6.165.9 under that cutoff;
- command-interface, skip-policy, and architecture validation passed 19 tests,
  including serial and two-worker skip aggregation;
- quick passed over 107 maintained Python files and 10 architecture checks;
- seed 1729 passed 1,102 routine tests on four xdist workers with no selected
  skips in 111.13 seconds;
- seed 20260825 passed the same 1,102 tests serially with 17 non-Linux Orb tests
  deselected in 153.45 seconds;
- repository-wide Ruff reported 38 diagnostics, all outside maintained runtime
  and tests: 37 historical Exploration findings and one vendored Ariad finding;
- repository-wide format-check reported 72 files, including historical
  experiments, documentation code blocks, closed Workbench examples, and the
  vendored skill;
- `C901` at 10 reported 47 functions, split between 39 production and 8 test
  functions; RS-030 owns classification;
- the ast-grep fixture passed and its scan reported two reflective V5 topology
  reads; RS-031 owns their disposition;
- the curated rerun mutation probe generated three mutants and all survived;
  mutmut disables `pytest-randomly` for its internal runner, while this selected
  fixed-data test file uses no random or Hypothesis behavior. RS-032 owns mutant
  classification;
- the distribution build and all 9 Amp relay tests passed; TypeScript compilation
  passed before the unsupported local Bun 1.4.0 reproduced the known demo timeout
  and seven cascading browser-closure failures. RS-033 owns a fail-fast preflight;
- audit findings return success, while broken probes preserve their nonzero
  status; mutation survivors have no threshold, while a broken mutation probe
  fails its optional profile;
- independent review found no high-severity issue. Its probe-failure, resolver
  cutoff, mutmut seed classification, xdist skip-test, lifecycle, and wording
  findings were resolved and revalidated.

The new audit baseline is evidence, not a quick, full, release, CI, or commit
gate. The Navigator accepted the result on 2026-08-25. The unresolved baseline
is retained in the dedicated technical-debt item
[`non-blocking-quality-audit-baseline-remains-unresolved`](../debt/items/non-blocking-quality-audit-baseline-remains-unresolved.md).
